// Excalidraw 的 React 组件封装（createElement 写法，无需 JSX/额外构建配置）
import React from 'react'
import { Excalidraw } from '@excalidraw/excalidraw'
import { ElMessageBox } from 'element-plus'
import '@excalidraw/excalidraw/index.css'

const h = React.createElement

// 素材库面板精简（官方没有 props 开关，用 CSS 隐藏）：
// 1) 底部「浏览素材库」按钮（跳在线库浏览页）
// 2) 「个人素材库」区块——面板结构为 [个人区标题, 个人区内容, Excalidraw素材库标题, Excalidraw素材库网格]，
//    隐藏 Excalidraw 素材库标题之前的所有兄弟块即整个个人区（含其 ⋮ 菜单）
// 3) 「Excalidraw素材库」标题上方的大间距（官方 margin-top: 2rem，个人区隐藏后显得格外空）
// 4) 素材项的多选 checkbox（我们不需要素材多选模式）
// 5) 右下角帮助按钮（help-icon）
// 6) 「更多工具」下拉触发器（其内容平铺到工具栏，见 injectExtraTools）
// 7) 左上角主菜单汉堡钮（原菜单项 导出图片/查找/重置画布/画布背景 已全部平铺到工具栏）
const LIB_CSS = `
  .wb-excalidraw .library-menu-browse-button { display: none !important; }
  .wb-excalidraw .library-menu-dropdown-container--in-heading { display: none !important; }
  .wb-excalidraw .library-menu-items-container__items > *:has(~ .library-menu-items-container__header--excal) {
    display: none !important;
  }
  .wb-excalidraw .library-menu-items-container__header--excal { margin-top: 0 !important; }
  .wb-excalidraw .library-unit__checkbox-container,
  .wb-excalidraw .library-unit__checkbox { display: none !important; }
  .wb-excalidraw .help-icon { display: none !important; }
  .wb-excalidraw .HintViewer { display: none !important; }   /* 工具栏下方的操作提示文字（"要移动画布…"） */
  .wb-excalidraw .main-menu-trigger { display: none !important; }
  /* 主菜单隐藏后补足左侧顶部空间，让设置面板避开悬浮标题栏（top:18px + height:36px）。 */
  .wb-excalidraw .App-menu_top__left { padding-top: 24px; }
  .wb-excalidraw .App-toolbar__extra-tools-trigger { display: none !important; }
  .wb-excalidraw .App-toolbar__extra-tools-trigger + .App-toolbar__divider,
  .wb-excalidraw .App-toolbar__divider:has(+ .App-toolbar__extra-tools-trigger) { display: none !important; }
  .wb-excalidraw .wb-extra-tool {
    display: inline-flex; align-items: center; justify-content: center;
    height: 36px; padding: 0 6px; border: none; background: transparent; border-radius: 6px;
    cursor: pointer; color: var(--icon-fill-color); font-size: 12px; white-space: nowrap;
  }
  .wb-excalidraw .wb-extra-tool:hover { background: var(--button-hover-bg, #f1f0ff); }
  .wb-excalidraw .wb-extra-tool svg { width: 20px; height: 20px; display: block; }
  .wb-extra-divider { width: 1px; height: 20px; margin: 0 4px; background: var(--default-border-color, #e0e0e0); }
  /* AI 生成入口：注入工具栏最左侧（样式与记事本工具栏的「AI 写作」一致：
     MagicStick 图标 + 紫色文字、透明底，hover 用 excalidraw 原生 hover 色，右侧带分隔线） */
  .wb-excalidraw .wb-ai-tool {
    display: inline-flex; align-items: center; gap: 4px;
    height: 40px; padding: 0 10px; margin-right: 2px;
    border: none; border-radius: 8px; background: transparent;
    color: #7c5cff; font-size: 16px; font-weight: 600; cursor: pointer; white-space: nowrap;
  }
  .wb-excalidraw .wb-ai-tool:hover { background: var(--button-hover-bg, #f1f0ff); }
  .wb-excalidraw .wb-ai-tool svg { width: 18px; height: 18px; display: block; flex-shrink: 0; }
  .wb-excalidraw .wb-ai-tool span { line-height: 1; }
  /* 画布背景色板弹层（fixed 定位，逃出画布的 overflow:hidden） */
  .wb-bg-pop {
    position: fixed; z-index: 999; display: flex; align-items: center; gap: 6px; padding: 8px 10px;
    background: #fff; border: 1px solid #dcdfe6; border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,.14);
  }
  .wb-bg-swatch {
    width: 26px; height: 26px; padding: 0; border: 2px solid #dcdfe6; border-radius: 6px; cursor: pointer;
  }
  .wb-bg-swatch.active { border-color: #6965db; }
  .wb-bg-swatch:hover { transform: scale(1.08); }
  .wb-bg-custom { width: 28px; height: 28px; padding: 0; border: 1px dashed #c0c4cc; border-radius: 6px; background: none; cursor: pointer; }
  /* 右键拖动平移中：画布光标改成抓取手型 */
  .wb-excalidraw.wb-panning .excalidraw__canvas { cursor: grabbing !important; }
`

// 右键拖动平移视图（excalidraw 原生平移只有中键/空格+左键/抓手工具；与思维导图"右键拖动视图"习惯一致）。
// 按下右键未移动仍算右键单击 → 官方右键菜单（复制/粘贴/图层等）照常弹出；
// 移动超过阈值才进入平移，并吞掉抬手后的那次 contextmenu，避免平移完又弹菜单。
// 平移靠 updateScene 写 scrollX/scrollY（scroll 增大 = 内容向屏幕右/下移，跟手方向一致）
const PAN_THRESHOLD = 4
function bindRightDragPan(host, apiRef) {
  let pan = null   // { startX, startY, scrollX, scrollY, moved }
  const onPointerDown = (e) => {
    if (e.button !== 2 || !apiRef.current) return
    if (!(e.target instanceof HTMLCanvasElement)) return   // 只在画布上生效，不抢 UI 控件的右键
    const st = apiRef.current.getAppState()
    pan = { startX: e.clientX, startY: e.clientY, scrollX: st.scrollX, scrollY: st.scrollY, moved: false }
  }
  const onPointerMove = (e) => {
    if (!pan || !apiRef.current) return
    const dx = e.clientX - pan.startX
    const dy = e.clientY - pan.startY
    if (!pan.moved && Math.hypot(dx, dy) < PAN_THRESHOLD) return
    pan.moved = true
    host.classList.add('wb-panning')
    const zoom = apiRef.current.getAppState().zoom?.value || 1
    apiRef.current.updateScene({
      appState: { scrollX: pan.scrollX + dx / zoom, scrollY: pan.scrollY + dy / zoom },
    })
  }
  const onPointerUp = (e) => {
    if (e.button !== 2 || !pan) return
    if (pan.moved) {
      const swallow = (ce) => {
        ce.preventDefault(); ce.stopPropagation()
        host.removeEventListener('contextmenu', swallow, true)
      }
      host.addEventListener('contextmenu', swallow, true)
      setTimeout(() => host.removeEventListener('contextmenu', swallow, true), 400)   // 兜底自清
    }
    pan = null
    host.classList.remove('wb-panning')
  }
  host.addEventListener('pointerdown', onPointerDown, true)
  // move/up 挂 window：拖出画布范围也能继续平移、正常结束
  window.addEventListener('pointermove', onPointerMove, true)
  window.addEventListener('pointerup', onPointerUp, true)
  return () => {
    host.removeEventListener('pointerdown', onPointerDown, true)
    window.removeEventListener('pointermove', onPointerMove, true)
    window.removeEventListener('pointerup', onPointerUp, true)
  }
}

// 「更多工具」仅保留激光笔，平铺到主工具栏。
const EXTRA_TOOLS = [
  {
    key: 'laser', title: '激光笔 — K',
    svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 20L16 8M14 6l4 4M18 4l2 2"/><circle cx="5" cy="19" r="1.4" fill="currentColor" stroke="none"/></svg>',
    action: (api) => api.setActiveTool({ type: 'laser' }),
  },
]

// ---------- 画布操作（原左上角主菜单项，平铺到工具栏，分隔线后与绘制工具区分） ----------

// 画布背景预设色（与官方画布底色板同风格）
const BG_PRESETS = ['#ffffff', '#f8f9fa', '#f5faff', '#fffce8', '#fdf2f2']

function closeBgPopover(host) {
  host.querySelector('.wb-bg-pop')?.remove()
}

// 画布背景：色板弹层（fixed 定位逃出画布 overflow:hidden；点外部/选色后关闭）
function toggleBgPopover(api, host, btn) {
  if (host.querySelector('.wb-bg-pop')) { closeBgPopover(host); return }
  const cur = (api.getAppState().viewBackgroundColor || '').toLowerCase()
  const pop = document.createElement('div')
  pop.className = 'wb-bg-pop'
  for (const c of BG_PRESETS) {
    const sw = document.createElement('button')
    sw.type = 'button'
    sw.className = 'wb-bg-swatch' + (cur === c ? ' active' : '')
    sw.style.background = c
    sw.title = c
    sw.addEventListener('click', () => {
      api.updateScene({ appState: { viewBackgroundColor: c } })
      closeBgPopover(host)
    })
    pop.appendChild(sw)
  }
  const custom = document.createElement('input')
  custom.type = 'color'
  custom.className = 'wb-bg-custom'
  custom.title = '自定义颜色'
  custom.value = /^#[0-9a-f]{6}$/.test(cur) ? cur : '#ffffff'
  custom.addEventListener('input', () => api.updateScene({ appState: { viewBackgroundColor: custom.value } }))
  custom.addEventListener('change', () => closeBgPopover(host))
  pop.appendChild(custom)
  const r = btn.getBoundingClientRect()
  pop.style.left = Math.max(8, r.left - 40) + 'px'
  pop.style.top = (r.bottom + 6) + 'px'
  host.appendChild(pop)
  const away = (e) => {
    if (!pop.contains(e.target) && e.target !== btn) {
      closeBgPopover(host)
      document.removeEventListener('mousedown', away, true)
    }
  }
  document.addEventListener('mousedown', away, true)
}

// 查找文本：与官方 SearchMenu 的 perform 一致——打开默认侧边栏的 search tab，再聚焦输入框
function openSearch(api, host) {
  api.updateScene({ appState: { openSidebar: { name: 'default', tab: 'search' }, openDialog: null } })
  setTimeout(() => {
    const inp = host.querySelector('input[placeholder="Find text on canvas..."]')
      || host.querySelector(`input[placeholder="${SEARCH_PLACEHOLDER}"]`)
    patchSearchInput(inp)
    inp?.focus()
    inp?.select()
  }, 150)
}

// 0.18 的 zh-CN 语言包缺 search 段翻译（placeholder 等仍是英文），打补丁改成中文
function patchSearchInput(inp) {
  if (inp && inp.placeholder !== SEARCH_PLACEHOLDER) inp.placeholder = SEARCH_PLACEHOLDER
}
const SEARCH_PLACEHOLDER = '在画布中查找文本…'

async function resetCanvas(api) {
  try {
    await ElMessageBox.confirm('确定清空整个画布？此操作不可恢复。', '重置画布',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' })
  } catch { return }
  api.resetScene({ resetFiles: true })
}

const EXTRA_ACTIONS = [
  {
    key: 'export-image', title: '导出图片',
    svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3v12m0 0l-4-4m4 4l4-4"/><path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg>',
    // 官方导出对话框（PNG/SVG、倍数、背景开关）。
    // 注意 0.18 的公开 API 没有 setOpenDialog（内部方法），对话框经 updateScene 的 appState.openDialog 打开
    action: (api) => api.updateScene({ appState: { openDialog: { name: 'imageExport' } } }),
  },
  {
    key: 'search', title: '查找文本 — Ctrl+F',
    svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>',
    action: openSearch,
  },
  {
    key: 'reset-canvas', title: '重置画布',
    svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13a1 1 0 001 1h8a1 1 0 001-1l1-13M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3"/></svg>',
    action: resetCanvas,
  },
  {
    key: 'canvas-bg', title: '画布背景',
    svg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3l5.5 5.5a7.2 7.2 0 11-11 0L12 3z"/><path d="M8.5 14a3.5 3.5 0 007 0" stroke-linecap="round"/></svg>',
    action: toggleBgPopover,
  },
]

// 工具栏就绪后把工具按钮 + 画布操作注入「更多工具」触发器原位（官方无 flatten 开关，只能注入 DOM）
function injectExtraTools(api, host) {
  if (!api || !host || host.querySelector('.wb-extra-tools')) return
  const anchor = host.querySelector('.App-toolbar__extra-tools-trigger')
  const container = anchor?.parentElement
  if (!container) return
  const wrap = document.createElement('div')
  wrap.className = 'wb-extra-tools'
  wrap.style.display = 'inline-flex'
  wrap.style.alignItems = 'center'
  const addBtn = (t) => {
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.className = 'wb-extra-tool'
    btn.title = t.title
    btn.innerHTML = t.svg
    btn.addEventListener('click', () => t.action(api, host, btn))
    wrap.appendChild(btn)
  }
  for (const t of EXTRA_TOOLS) addBtn(t)
  const divider = document.createElement('span')
  divider.className = 'wb-extra-divider'
  wrap.appendChild(divider)
  for (const t of EXTRA_ACTIONS) addBtn(t)
  container.insertBefore(wrap, anchor)
}

// 「AI 生成」按钮注入工具栏最左侧（与平铺工具同一容器，prepend 到首位，右侧补分隔线）。
// 图标与记事本「AI 写作」/全局 AI 按钮统一为 Element Plus MagicStick（内联 SVG）
const AI_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="14" height="14"><path fill="currentColor" d="M512 64h64v192h-64zm0 576h64v192h-64zM160 480v-64h192v64zm576 0v-64h192v64zM249.856 199.04l45.248-45.184L430.848 289.6 385.6 334.848 249.856 199.104zM657.152 606.4l45.248-45.248 135.744 135.744-45.248 45.248zM114.048 923.2 68.8 877.952l316.8-316.8 45.248 45.248zM702.4 334.848 657.152 289.6l135.744-135.744 45.248 45.248z"/></svg>'
function injectAiButton(host, onAiClick) {
  if (!host || host.querySelector('.wb-ai-tool')) return
  const anchor = host.querySelector('.App-toolbar__extra-tools-trigger')
  const container = anchor?.parentElement
  if (!container) return
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.className = 'wb-ai-tool'
  btn.title = 'AI 生成'
  btn.innerHTML = AI_SVG + '<span>AI 生成</span>'
  btn.addEventListener('click', () => onAiClick?.())
  container.insertBefore(btn, container.firstChild)
  const divider = document.createElement('span')
  divider.className = 'wb-extra-divider'
  container.insertBefore(divider, btn.nextSibling)
}

// props: initialData / onChange(elements, appState, files) / onApi(excalidrawAPI) / onReady(工具栏注入完成) / onAiClick(工具栏 AI 按钮)
export default function ExcalidrawBoard({ initialData, onChange, onApi, onReady, onAiClick }) {
  // 工具栏锁定按钮默认锁定（画完图形后工具保持，不弹回选择工具）
  const merged = initialData
    ? {
        ...initialData,
        appState: {
          ...(initialData.appState || {}),
          activeTool: {
            type: initialData.appState?.activeTool?.type || 'selection',
            customType: initialData.appState?.activeTool?.customType ?? null,
            locked: true,
            lastActiveTool: initialData.appState?.activeTool?.lastActiveTool ?? null,
          },
        },
      }
    : { appState: { activeTool: { type: 'selection', customType: null, locked: true, lastActiveTool: null } } }
  const hostRef = React.useRef(null)
  const apiRef = React.useRef(null)
  React.useEffect(() => {
    // 工具栏异步渲染：轮询等「更多工具」触发器就绪后原位注入平铺按钮（最多 ~10s）。
    // 注入完成后通知外层（延迟 200ms 让图标/字体渲染落地），外层再撤掉加载遮罩——
    // 否则用户会先看到官方工具栏、再看到我们的按钮"后出来"的闪动
    let tries = 0
    const timer = setInterval(() => {
      tries++
      if (hostRef.current && apiRef.current
          && hostRef.current.querySelector('.App-toolbar__extra-tools-trigger')) {
        injectExtraTools(apiRef.current, hostRef.current)
        injectAiButton(hostRef.current, onAiClick)
        clearInterval(timer)
        setTimeout(() => onReady?.(), 200)
      } else if (tries > 100) {
        clearInterval(timer)
        onReady?.()   // 兜底：注入失败也要撤遮罩，编辑器本体可用
      }
    }, 100)
    return () => clearInterval(timer)
  }, [])
  React.useEffect(() => {
    // 搜索输入框的 placeholder 汉化补丁：搜索框按需渲染（侧栏打开才出现），
    // 用 MutationObserver 盯着 DOM，一出现就替换（Ctrl+F 唤起的路径也覆盖）
    const host = hostRef.current
    if (!host) return undefined
    const patch = () => {
      host.querySelectorAll('input[placeholder="Find text on canvas..."]')
        .forEach((el) => { el.placeholder = SEARCH_PLACEHOLDER })
    }
    patch()
    const ob = new MutationObserver(patch)
    ob.observe(host, { childList: true, subtree: true })
    return () => ob.disconnect()
  }, [])
  React.useEffect(() => {
    if (!hostRef.current) return undefined
    return bindRightDragPan(hostRef.current, apiRef)
  }, [])
  return h(
    'div',
    { ref: hostRef, className: 'wb-excalidraw', style: { height: '100%', border: '1px solid #dcdfe6', borderRadius: 4, overflow: 'hidden' } },
    h('style', null, LIB_CSS),
    h(Excalidraw, {
      initialData: merged,
      langCode: 'zh-CN',   // 内置简体中文语言包，工具栏/菜单/面板全翻译
      onChange: (elements, appState, files) => onChange?.(elements, appState, files),
      excalidrawAPI: (api) => { apiRef.current = api; onApi?.(api) },
    })
    // 原左上角主菜单项（导出图片/查找/重置画布/画布背景）已平铺到中间工具栏，
    // 见 EXTRA_ACTIONS；汉堡钮由 CSS 隐藏
  )
}
