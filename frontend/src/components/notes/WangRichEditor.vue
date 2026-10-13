<template>
  <div ref="wrapRef" class="rich-editor wang-editor-wrap" :class="{ 'brush-armed': brushActive, 'brush-locked': brushLocked }">
    <Toolbar class="re-toolbar" :editor="editorRef" :default-config="toolbarConfig" mode="default" />
    <Editor
      v-model="html" class="re-body" :default-config="editorConfig" mode="default"
      @onCreated="onCreated" @onChange="onChange"
    />

    <!-- 查找替换面板（自定义菜单「🔍 查找」/ Ctrl+F 唤起） -->
    <div v-if="fr.visible" class="fr-panel" @keydown.stop @mousedown.stop>
      <div class="fr-row">
        <input
          ref="frFindRef" v-model="fr.keyword" class="fr-input" placeholder="查找"
          @input="refreshMatches" @keydown.enter.prevent="findNext" @keydown.esc.prevent="closeFr"
        />
        <span class="fr-count">{{ fr.matches.length ? `${fr.current + 1}/${fr.matches.length}` : '0/0' }}</span>
        <button class="fr-btn" title="上一个" :disabled="!fr.matches.length" @click="findPrev">↑</button>
        <button class="fr-btn" title="下一个 (Enter)" :disabled="!fr.matches.length" @click="findNext">↓</button>
        <button class="fr-btn fr-close" title="关闭 (Esc)" @click="closeFr">×</button>
      </div>
      <div class="fr-row">
        <input
          v-model="fr.replacement" class="fr-input" placeholder="替换为"
          @keydown.enter.prevent="replaceCurrent" @keydown.esc.prevent="closeFr"
        />
        <button class="fr-btn fr-text" :disabled="!fr.matches.length" @click="replaceCurrent">替换</button>
        <button class="fr-btn fr-text" :disabled="!fr.matches.length" @click="replaceAll">全部替换</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import '@wangeditor/editor/dist/css/style.css'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'
import { Boot, DomEditor, SlateEditor, SlateElement, SlateNode, SlateRange, SlateText, SlateTransforms } from '@wangeditor/editor'
import { ElMessage } from 'element-plus'
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef } from 'vue'
import { imageUrl, uploadImageFile } from '../../api'

// ---------- 自定义菜单与组件实例的通信总线 ----------
// 关键：状态必须挂 window 全局。vite HMR/重复加载会让本模块出现多个实例，
// 而 Boot.registerMenu 只有首次注册生效（菜单闭包引用首次模块的变量）——
// 模块级 bus 会导致"菜单读到旧模块的空 handler，点击没反应"（悬浮栏 AI/格式刷失效的根因）
const G = (window.__grtNotes ??= {
  aiHandler: null, frHandler: null,
  brush: null, brushTimer: null, brushMouseDown: false, markerDrag: null, editorDrag: null, menusRegistered: false,
  brushListeners: new Set(),   // brush 状态变化通知（组件据此切换刷子光标）
})

function notifyBrush() {
  G.brushListeners.forEach((fn) => fn())
}

class FindReplaceMenu {
  constructor() {
    this.title = '查找替换'
    this.iconSvg = '<svg viewBox="0 0 1024 1024"><path d="M945.066667 898.133333l-189.866667-189.866666c55.466667-64 87.466667-149.333333 87.466667-241.066667 0-204.8-168.533333-373.333333-373.333334-373.333333S96 264.533333 96 469.333333 264.533333 842.666667 469.333333 842.666667c91.733333 0 174.933333-34.133333 241.066667-87.466667l189.866667 189.866667c6.4 6.4 14.933333 8.533333 23.466666 8.533333s17.066667-2.133333 23.466667-8.533333c8.533333-12.8 8.533333-32 0-44.8zM469.333333 778.666667c-170.666667 0-309.333333-138.666667-309.333333-309.333334s138.666667-309.333333 309.333333-309.333333 309.333333 138.666667 309.333334 309.333333-138.666667 309.333333-309.333334 309.333334z"/></svg>'
    this.tag = 'button'
  }

  getValue() { return '' }
  isActive() { return false }
  isDisabled() { return false }
  exec() { G.frHandler?.() }
}

// 「AI 写作」选中悬浮栏菜单（纯文字按钮；主工具栏的 AI 按钮是注入 DOM 的，见 injectAiButton）
class AiWriteMenu {
  constructor() {
    this.title = '✨ AI 写作'
    this.tag = 'button'
  }

  getValue() { return '' }
  isActive() { return false }
  isDisabled() { return false }
  exec() { G.aiHandler?.() }
}

// ---------- 格式刷（wangEditor 无内置，自实现：捕获选区格式 → 下次选中文字即套用一次） ----------
const BRUSH_MARK_KEYS = ['bold', 'italic', 'underline', 'through', 'color', 'bgColor', 'fontSize', 'fontFamily', 'code', 'sup', 'sub']
// brush 状态在全局 G 上（G.brush = { marks, blockProps } | null）

class FormatPainterMenu {
  constructor() {
    this.title = '格式刷'
    this.iconSvg = '<svg viewBox="0 0 24 24"><path d="M18 4V3c0-.55-.45-1-1-1H5c-.55 0-1 .45-1 1v4c0 .55.45 1 1 1h12c.55 0 1-.45 1-1V6h1v4H9v11c0 .55.45 1 1 1h2c.55 0 1-.45 1-1v-9h8V4h-3z" fill="currentColor"/></svg>'
    this.tag = 'button'
  }

  getValue() { return '' }
  isActive() { return !!G.brush }
  isDisabled(editor) { return !editor?.selection }
  exec(editor) {
    const now = Date.now()
    if (G.brush) {
      // 启用中快速再点（双击）= 切连续模式；已锁定或间隔久 = 取消
      if (!G.brush.locked && now - G.brushAt < 800) {
        G.brush.locked = true
      } else {
        G.brush = null
      }
      notifyBrush()
      return
    }
    // 行内格式：加粗/斜体/下划线/删除线/颜色/背景色/字号/字体/行内代码等
    const marks = SlateEditor.marks(editor) || {}
    const picked = {}
    for (const k of BRUSH_MARK_KEYS) {
      if (marks[k] !== undefined) picked[k] = marks[k]
    }
    // 块级格式：段落/标题类型 + 对齐 + 缩进
    const blockProps = { type: 'paragraph', textAlign: undefined, indent: undefined }
    const entry = SlateEditor.above(editor, {
      match: (n) => SlateElement.isElement(n) && SlateEditor.isBlock(editor, n),
    })
    if (entry) {
      const [node] = entry
      if (/^header[1-5]$/.test(node.type)) blockProps.type = node.type
      if (node.textAlign) blockProps.textAlign = node.textAlign
      if (node.indent) blockProps.indent = node.indent
    }
    G.brush = { marks: picked, blockProps, locked: false }
    G.brushAt = now
    notifyBrush()
  }
}

// 应用格式刷到当前选区（单击模式用一次即失效，连续模式保持）
// 逐文本节点套用：整选区 addMark/removeMark 遇到空行会抛 slate 内部错误（Cannot find a descendant）
// 导致"中间失效"；逐节点 + try/catch 跳过异常节点（空行）不中断整体
const LIST_BLOCK_TYPES = ['numbered-list', 'bulleted-list', 'list-item']

function applyBrush(editor) {
  if (!G.brush || !editor?.selection || SlateRange.isCollapsed(editor.selection)) return
  const at = editor.selection
  // 行内格式：加粗/斜体/颜色等，逐文本节点套用
  const entries = [...SlateEditor.nodes(editor, { at, match: (n) => SlateText.isText(n) })]
  for (const [, path] of entries) {
    try {
      const props = {}
      for (const k of BRUSH_MARK_KEYS) props[k] = undefined   // 清旧行内格式（undefined=删键）
      Object.assign(props, G.brush.marks)
      SlateTransforms.setNodes(editor, props, { at: path, match: (n) => SlateText.isText(n) })
    } catch { /* 空行等异常节点跳过 */ }
  }
  // 块级格式：对齐/缩进所有块可套；类型只在源是标题时套用，且跳过列表项（不毁列表结构）
  const blockProps = { ...G.brush.blockProps }
  if (blockProps.type === 'paragraph') delete blockProps.type   // 源是普通段落时不强制改类型
  if (Object.keys(blockProps).some((k) => blockProps[k] !== undefined)) {
    try {
      SlateTransforms.setNodes(editor, blockProps, {
        match: (n) => SlateElement.isElement(n) && SlateEditor.isBlock(editor, n)
          && !LIST_BLOCK_TYPES.includes(n.type),
      })
    } catch { /* 块级套用失败不影响行内结果 */ }
  }
  if (!G.brush.locked) G.brush = null
  notifyBrush()
}

// 应用时机：鼠标拖动选择时 selectionchange 会持续触发——移动慢一点（停顿 >80ms）就会
// 中途套用到半成品选区（"格式化中间失效"）。改为：鼠标按下期间不套用，松开才套用；
// 键盘选择（Shift/Ctrl+A 无鼠标按下）走 80ms 防抖套用。
function tryApplyBrush(getEditor) {
  const ed = getEditor()
  if (!G.brush || !ed) return
  // 选区必须在当前编辑器内（防止选中页面别处文字也触发）
  const container = ed.getEditableContainer()
  const sel = window.getSelection()
  if (!sel?.rangeCount || !container.contains(sel.anchorNode)) return
  let slateSel = ed.selection
  if ((!slateSel || SlateRange.isCollapsed(slateSel)) && !sel.isCollapsed) {
    // 慢拖丢 mouseup 的场景下 slate 与 DOM 选区会脱节（slate 塌了、DOM 还在）——以 DOM 为准先同步
    try {
      const anchor = DomEditor.toSlatePoint(ed, [sel.anchorNode, sel.anchorOffset], { suppressThrow: true })
      const focus = DomEditor.toSlatePoint(ed, [sel.focusNode, sel.focusOffset], { suppressThrow: true })
      if (anchor && focus) ed.select({ anchor, focus })
    } catch { /* 同步失败按无选区处理 */ }
    slateSel = ed.selection
  }
  if (!slateSel || SlateRange.isCollapsed(slateSel)) return
  applyBrush(ed)
}

function onBrushSelectionChange(getEditor) {
  if (!G.brush) return
  if (G.brushMouseDown) return   // 拖动中不套用，等 mouseup
  clearTimeout(G.brushTimer)
  G.brushTimer = setTimeout(() => tryApplyBrush(getEditor), 80)
}

function onBrushDocDown(e) {
  G.brushMouseDown = true
  // 兜底自愈：mouseup 若因任何原因丢失（目标元素在拖拽中被重绘脱离 DOM 等），
  // 2s 后自动复位，格式刷不会永久卡死在"拖动中"状态
  clearTimeout(G.brushMouseDownTimer)
  G.brushMouseDownTimer = setTimeout(() => {
    if (G.brushMouseDown) {
      G.brushMouseDown = false
      onBrushDocUp()
    }
  }, 2000)
}

function onBrushDocUp(e) {
  G.brushMouseDown = false
  clearTimeout(G.brushMouseDownTimer)
  if (!G.brush) return
  // 松开后选区已定，但 wangEditor 的 editor.selection 可能滞后一拍
  clearTimeout(G.brushTimer)
  G.brushTimer = setTimeout(() => {
    const ed = G.editor
    if (ed) tryApplyBrush(() => ed)
  }, 50)
}

// 列表序号（data-w-e-reserve 的 contenteditable=false span）上按下鼠标：
// 该区域不参与选区定位（slate selection 为 null），拖选从序号区起/经过会清掉选区。
// 把序号上的按下映射到该列表项文本开头；之后的拖动由我们手动用 caretRangeFromPoint 扩展选区
//（preventDefault 后浏览器不再进入原生拖选模式，必须自己续拖）。

// 跨浏览器的 坐标→DOM文本点：Chrome/Edge 用 caretRangeFromPoint，Firefox 用 caretPositionFromPoint
function caretPointAt(x, y) {
  if (document.caretRangeFromPoint) {
    const r = document.caretRangeFromPoint(x, y)
    return r ? [r.startContainer, r.startOffset] : null
  }
  if (document.caretPositionFromPoint) {
    const p = document.caretPositionFromPoint(x, y)
    return p ? [p.offsetNode, p.offset] : null
  }
  return null
}

function onMarkerDown(e, getEditor) {
  const ed = getEditor()
  if (!ed) return
  // 序号 span 已 pointer-events:none，按下点落在序号区时 target 是块 div 本身（而非文本节点后代）
  const block = e.target.closest?.('[data-slate-node="element"]')
  let marker = e.target.closest?.('span[data-w-e-reserve="true"]')
  if (!marker && block && e.target === block) {
    // 兜底：只有按下点确实落在序号/符号矩形内才重定向到文本开头；
    // 点在行尾空白、ul/ol 容器边缘时交给浏览器默认定位（否则点击列表任意空白都会跳到行首/列表首项）
    const m = block.querySelector('span[data-w-e-reserve="true"]')
    if (m) {
      const r = m.getBoundingClientRect()
      if (e.clientX >= r.left - 2 && e.clientX <= r.right + 2 &&
          e.clientY >= r.top - 2 && e.clientY <= r.bottom + 2) {
        marker = m
      }
    }
  }
  if (marker) {
    // 按下点在序号上：映射到该列表项文本开头（preventDefault 后浏览器不再进入原生拖选，
    // 后续拖动由 onMarkerDragMove 手动续拖）
    // stopImmediatePropagation：wangEditor 自己的 mousedown 处理器在不可编辑区做 DOM→slate
    // 映射会抛 "Cannot resolve a Slate point from DOM point"，一并拦掉
    e.preventDefault()
    e.stopImmediatePropagation()
    try {
      const block = marker.closest('[data-slate-node="element"]')
      const node = DomEditor.toSlateNode(ed, block)
      const path = DomEditor.findPath(ed, node)
      const firstText = SlateEditor.nodes(ed, { at: path, match: (n) => SlateText.isText(n) })
      const [, textPath] = firstText.next().value || []
      if (textPath) {
        G.markerDrag = { editor: ed, anchor: { path: textPath, offset: 0 } }
        SlateTransforms.select(ed, { path: textPath, offset: 0 })
      }
    } catch { /* 定位失败则交给默认行为 */ }
    return
  }
  // 按下点必须在正文文本区（防止按下点在悬浮栏等覆盖层上时算出错误锚点）
  if (!e.target.closest?.('[data-slate-editor]')) return
  // 按下点在正文：记录拖拽锚点。之后拖动经过序号区时（原生选区扩展会在那里塌陷，
  // 尤其是从下往上拖到首行序号），由 onMarkerDragMove 手动把焦点续到该列表项文本开头
  try {
    const cp = caretPointAt(e.clientX, e.clientY)
    if (cp) {
      const pt = DomEditor.toSlatePoint(ed, cp, { suppressThrow: true })
      if (pt) G.editorDrag = { editor: ed, anchor: pt }
    }
  } catch { /* 记录失败不影响原生拖选 */ }
}

function _markerTextStart(ed, marker) {
  const block = marker.closest('[data-slate-node="element"]')
  const node = DomEditor.toSlateNode(ed, block)
  const path = DomEditor.findPath(ed, node)
  const firstText = SlateEditor.nodes(ed, { at: path, match: (n) => SlateText.isText(n) })
  const [, textPath] = firstText.next().value || []
  return textPath ? { path: textPath, offset: 0 } : null
}

function onMarkerDragMove(e) {
  // 序号起拖：全程手动续拖
  if (G.markerDrag && e.buttons) {
    const { editor: ed, anchor } = G.markerDrag
    const cp = caretPointAt(e.clientX, e.clientY)
    if (cp) {
      try {
        const pt = DomEditor.toSlatePoint(ed, cp, { suppressThrow: true })
        if (pt) {
          G.markerDrag.lastFocus = pt
          SlateTransforms.setSelection(ed, { anchor, focus: pt })
        }
      } catch { /* 落在不可映射区域时忽略本帧 */ }
    }
    return
  }
  // 正文起拖、经过序号区：原生扩展会塌陷，手动把焦点续到该序号所在行的文本开头
  if (G.editorDrag && e.buttons) {
    const marker = e.target.closest?.('span[data-w-e-reserve="true"]')
    if (!marker) return
    const { editor: ed, anchor } = G.editorDrag
    try {
      const focus = _markerTextStart(ed, marker)
      if (focus) {
        G.editorDrag.lastFocus = focus
        SlateTransforms.setSelection(ed, { anchor, focus })
      }
    } catch { /* 忽略本帧 */ }
  }
}

function onMarkerDragUp(e) {
  const marker = e?.target?.closest?.('span[data-w-e-reserve="true"]')
  const drag = G.markerDrag || G.editorDrag
  if (marker && drag) {
    // 松开点在序号区：浏览器/wangEditor 会把选区塌掉且无法拦截（preventDefault 无效）。
    // 记录此刻应有的选区，塌掉后下一帧重新落定
    const { editor: ed, anchor } = drag
    const focus = drag.lastFocus
      || (() => { try { return _markerTextStart(ed, marker) } catch { return null } })()
    if (anchor && focus) {
      // 塌选区发生在 mouseup 后 30~120ms（wangEditor 的异步收尾），无法拦截；
      // 塌之前选区看似完好，不能用"选区为空才补"的判断——直接按塌窗节奏强制落定几帧
      for (const delay of [50, 150, 300]) {
        setTimeout(() => {
          try {
            SlateTransforms.setSelection(ed, { anchor, focus })
            ed.focus()
          } catch { /* 编辑器已卸载等场景忽略 */ }
        }, delay)
      }
    }
  }
  G.markerDrag = null
  G.editorDrag = null
}

if (!G.menusRegistered) {
  Boot.registerMenu({ key: 'findReplace', factory: () => new FindReplaceMenu() })
  Boot.registerMenu({ key: 'aiWrite', factory: () => new AiWriteMenu() })
  Boot.registerMenu({ key: 'formatPainter', factory: () => new FormatPainterMenu() })
  G.menusRegistered = true
}

// content 只在挂载时读取一次：父组件用 :key 控制切换笔记时整体重建
const props = defineProps({ content: { type: String, default: '' } })
const emit = defineEmits(['change', 'ai'])

const html = ref(props.content)
const editorRef = shallowRef(null)
const wrapRef = ref(null)

// 具名 handler：卸载时按引用清理——切笔记时新实例先挂载、旧实例后卸载，
// 无条件清空会把新实例刚注册的 handler 抹掉
const aiHandler = () => emit('ai')
const brushSelectionHandler = () => onBrushSelectionChange(() => editorRef.value)
const markerDownHandler = (e) => onMarkerDown(e, () => editorRef.value)
// 格式刷启用状态 → 根节点 class（切换刷子光标；连续模式用紫色刷子区分）
const brushActive = ref(false)
const brushLocked = ref(false)
const syncBrushCursor = () => {
  brushActive.value = !!G.brush
  brushLocked.value = !!G.brush?.locked
}

const toolbarConfig = {
  toolbarKeys: [
    'headerSelect', 'fontFamily', 'fontSize', '|',
    'bold', 'italic', 'underline', 'through', 'color', 'bgColor', 'clearStyle', 'formatPainter', '|',
    'bulletedList', 'numberedList', 'todo', 'justifyLeft', 'justifyCenter', 'justifyRight', 'indent', 'delIndent', '|',
    'blockquote', 'codeBlock', 'insertLink', 'uploadImage', 'insertImage', 'insertTable', 'divider', 'findReplace', '|',
    'undo', 'redo',
  ],
}
const editorConfig = {
  placeholder: '写点什么… 顶部工具栏可排版，点「✨ AI 写作」让 AI 帮你写',
  // 选中内容弹出的悬浮栏：「AI 写作」「格式刷」在前，其余为 wangEditor 默认项
  hoverbarKeys: {
    text: {
      menuKeys: ['aiWrite', 'formatPainter', 'headerSelect', 'insertLink', 'bulletedList', 'bold', 'through', 'color', 'bgColor', 'clearStyle'],
    },
  },
  MENU_CONF: {
    // 链接：用户输入裸域名（www.baidu.com）时自动补 https://，避免被当站内相对路径
    insertLink: {
      parseLinkUrl(url) {
        const u = (url || '').trim()
        if (/^(https?:\/\/|mailto:)/i.test(u)) return u
        if (/^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(u)) return 'https://' + u
        return u
      },
    },
    // 网络图片：图片地址同样补协议（站内上传路径 / 外链 http(s) 放行）
    insertImage: {
      parseImageSrc(src) {
        const u = (src || '').trim()
        if (/^(https?:\/\/|\/api\/uploads\/)/i.test(u)) return u
        if (/^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(u)) return 'https://' + u
        return u
      },
    },
    uploadImage: {
      maxFileSize: 5 * 1024 * 1024,
      // 走站内图片接口（登录态 + 配额闸），<img> 用 ?token= 直链
      async customUpload(file, insertFn) {
        try {
          const res = await uploadImageFile(file)
          insertFn(imageUrl(res.files[0].id), file.name, '')
        } catch (e) {
          ElMessage.error(e.message || '图片上传失败')
        }
      },
    },
  },
}

// ---------- 查找替换 ----------

const fr = reactive({ visible: false, keyword: '', replacement: '', matches: [], current: -1 })
const frFindRef = ref(null)

function openFr() {
  fr.visible = true
  nextTick(() => {
    frFindRef.value?.focus()
    if (fr.keyword) refreshMatches()
  })
}

function closeFr() {
  fr.visible = false
  editorRef.value?.focus()
}

// 收集所有命中（文本节点路径 + 偏移），文档序
function collectMatches() {
  const ed = editorRef.value
  const kw = fr.keyword
  if (!ed || !kw) return []
  const out = []
  for (const [node, path] of SlateEditor.nodes(ed, { at: [], match: (n) => SlateText.isText(n) })) {
    let i = node.text.indexOf(kw)
    while (i !== -1) {
      out.push({ path, offset: i })
      i = node.text.indexOf(kw, i + kw.length)
    }
  }
  return out
}

function refreshMatches() {
  fr.matches = collectMatches()
  fr.current = -1
  if (fr.matches.length) gotoMatch(0)
}

function pathCompare(a, b) {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] !== b[i]) return a[i] - b[i]
  }
  return a.length - b.length
}

// 命中点是否严格在 (path, offset) 之后
function matchAfter(m, path, offset) {
  const c = pathCompare(m.path, path)
  return c > 0 || (c === 0 && m.offset >= offset)
}

function gotoMatch(i) {
  const ed = editorRef.value
  const m = fr.matches[i]
  if (!ed || !m) return
  fr.current = i
  const range = { anchor: { path: m.path, offset: m.offset }, focus: { path: m.path, offset: m.offset + fr.keyword.length } }
  SlateTransforms.select(ed, range)
  try {
    const dom = DomEditor.toDOMNode(ed, SlateNode.get(ed, m.path))
    dom?.scrollIntoView({ block: 'center' })
  } catch { /* 节点已失效时忽略 */ }
}

function findNext() {
  const ed = editorRef.value
  if (!ed || !fr.keyword) return
  fr.matches = collectMatches()
  if (!fr.matches.length) { fr.current = -1; return }
  // 从当前选区终点之后找下一个（光标不在文档里则从开头找）
  const focus = ed.selection?.focus
  const idx = focus ? fr.matches.findIndex((m) => matchAfter(m, focus.path, focus.offset)) : 0
  gotoMatch(idx === -1 ? 0 : idx)
}

function findPrev() {
  const ed = editorRef.value
  if (!ed || !fr.keyword) return
  fr.matches = collectMatches()
  if (!fr.matches.length) { fr.current = -1; return }
  const anchor = ed.selection?.anchor
  let idx = -1
  if (anchor) {
    for (let i = fr.matches.length - 1; i >= 0; i--) {
      if (!matchAfter(fr.matches[i], anchor.path, anchor.offset) &&
          !(pathCompare(fr.matches[i].path, anchor.path) === 0 && fr.matches[i].offset === anchor.offset)) {
        idx = i
        break
      }
    }
  }
  gotoMatch(idx === -1 ? fr.matches.length - 1 : idx)
}

// 当前选区是否正好选中某个命中
function selectedMatchIndex() {
  const ed = editorRef.value
  const sel = ed?.selection
  if (!ed || !sel) return -1
  return fr.matches.findIndex((m) =>
    pathCompare(m.path, sel.anchor.path) === 0 && m.offset === sel.anchor.offset &&
    pathCompare(m.path, sel.focus.path) === 0 && sel.focus.offset === m.offset + fr.keyword.length)
}

function replaceCurrent() {
  const ed = editorRef.value
  if (!ed || !fr.keyword) return
  fr.matches = collectMatches()
  const i = selectedMatchIndex()
  if (i === -1) { findNext(); return }  // 没选中命中时先定位到下一个
  const m = fr.matches[i]
  SlateTransforms.select(ed, {
    anchor: { path: m.path, offset: m.offset },
    focus: { path: m.path, offset: m.offset + fr.keyword.length },
  })
  ed.insertText(fr.replacement)   // 选区展开时 insertText 即替换
  ElMessage.success(`已替换第 ${i + 1} 处`)
  findNext()
}

function replaceAll() {
  const ed = editorRef.value
  if (!ed || !fr.keyword) return
  const matches = collectMatches()
  if (!matches.length) return
  // 逆序替换：前面命中的 path/offset 不受后面文本长度变化影响
  for (let i = matches.length - 1; i >= 0; i--) {
    const m = matches[i]
    SlateTransforms.select(ed, {
      anchor: { path: m.path, offset: m.offset },
      focus: { path: m.path, offset: m.offset + fr.keyword.length },
    })
    ed.insertText(fr.replacement)
  }
  ElMessage.success(`已替换 ${matches.length} 处`)
  refreshMatches()
}

// ---------- 生命周期 ----------

// 「✨ AI 写作」按钮：wangEditor 注册菜单只显示图标不支持文字，直接注入 DOM 到工具栏最左侧
function injectAiButton() {
  const bar = wrapRef.value?.querySelector('.w-e-toolbar')
  if (!bar || bar.querySelector('.ai-write-item')) return
  const item = document.createElement('div')
  item.className = 'w-e-bar-item ai-write-item'
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.className = 'ai-write-btn'
  btn.textContent = '✨ AI 写作'
  btn.title = 'AI 写作'
  btn.addEventListener('mousedown', (e) => e.preventDefault())
  btn.addEventListener('click', (e) => {
    e.preventDefault()
    emit('ai')
  })
  item.appendChild(btn)
  bar.insertBefore(item, bar.firstChild)
  const divider = document.createElement('div')
  divider.className = 'w-e-bar-divider'
  bar.insertBefore(divider, item.nextSibling)
}

function onCreated(editor) {
  editorRef.value = editor
  G.editor = editor   // 调试/自动化测试入口（卸载时清理）
  G.frHandler = openFr
  G.aiHandler = aiHandler
  G.brushListeners.add(syncBrushCursor)
  // Toolbar 组件在 editor 就绪后才渲染，等下一拍再注入；拿不到就再等等
  nextTick(() => {
    injectAiButton()
    setTimeout(injectAiButton, 200)
  })
  // Ctrl+F 唤起查找替换（拦掉浏览器默认的页面查找）
  editor.getEditableContainer()?.addEventListener('keydown', onCtrlF)
  // 格式刷：选区落定后套用；Esc 取消；鼠标按下/松开跟踪（拖动中不套用）
  document.addEventListener('selectionchange', brushSelectionHandler)
  document.addEventListener('mousedown', onBrushDocDown, true)
  document.addEventListener('mouseup', onBrushDocUp, true)
  editor.getEditableContainer()?.addEventListener('mousedown', markerDownHandler, true)
  document.addEventListener('mousemove', onMarkerDragMove, true)
  document.addEventListener('mouseup', onMarkerDragUp, true)
  editor.getEditableContainer()?.addEventListener('keydown', onBrushEsc)
}

function onBrushEsc(e) {
  if (e.key === 'Escape' && G.brush) {
    G.brush = null
    notifyBrush()
  }
}

function onCtrlF(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
    e.preventDefault()
    openFr()
  }
}

// 禁用浏览器原生右键菜单（编辑区内右键不弹系统菜单）
function onContextMenu(e) {
  e.preventDefault()
}

function onChange(editor) {
  emit('change', editor.getHtml())
}

onMounted(() => {
  wrapRef.value?.addEventListener('contextmenu', onContextMenu)
})

onBeforeUnmount(() => {
  G.brush = null
  notifyBrush()
  clearTimeout(G.brushTimer)
  G.brushListeners.delete(syncBrushCursor)
  wrapRef.value?.removeEventListener('contextmenu', onContextMenu)
  editorRef.value?.getEditableContainer()?.removeEventListener('keydown', onCtrlF)
  document.removeEventListener('selectionchange', brushSelectionHandler)
  document.removeEventListener('mousedown', onBrushDocDown, true)
  document.removeEventListener('mouseup', onBrushDocUp, true)
  editorRef.value?.getEditableContainer()?.removeEventListener('keydown', onBrushEsc)
  editorRef.value?.getEditableContainer()?.removeEventListener('mousedown', markerDownHandler, true)
  document.removeEventListener('mousemove', onMarkerDragMove, true)
  document.removeEventListener('mouseup', onMarkerDragUp, true)
  if (G.frHandler === openFr) G.frHandler = null
  if (G.aiHandler === aiHandler) G.aiHandler = null
  if (G.editor === editorRef.value) G.editor = null
  editorRef.value?.destroy()
  editorRef.value = null
})

defineExpose({
  getHtml: () => editorRef.value?.getHtml() ?? html.value,
  getText: () => editorRef.value?.getText() ?? '',
  // 当前选区文本（无选区/光标态返回 ''）；AI 写作打开面板前由父组件抓取（面板聚焦后选区丢失）
  getSelectionText: () => {
    const ed = editorRef.value
    if (!ed?.selection || SlateRange.isCollapsed(ed.selection)) return ''
    return ed.getSelectionText() || ''
  },
  // 是否处于选区展开态（供「替换选中」判断）
  hasSelection: () => !!(editorRef.value?.selection && !SlateRange.isCollapsed(editorRef.value.selection)),
  insertHtml(fragment, { replaceSelection = false } = {}) {
    const ed = editorRef.value
    if (!ed) return
    ed.focus()
    ed.restoreSelection?.()   // 面板输入后选区丢失，先恢复最后的光标位置
    if (ed.selection && !SlateRange.isCollapsed(ed.selection)) {
      if (replaceSelection) {
        ed.deleteFragment()     // 替换选中：先删选区内容，再插入
      } else {
        SlateTransforms.collapse(ed, { edge: 'end' })   // 插入：折叠到选区末尾，保留选中内容
      }
    }
    ed.dangerouslyInsertHtml(fragment)
  },
  focus: () => editorRef.value?.focus(),
})
</script>

<style scoped>
.rich-editor { display: flex; flex-direction: column; flex: 1; min-height: 0; position: relative; }

/* 格式刷启用期间：编辑区内鼠标变成刷子光标（一眼可见，不靠文字提示） */
.brush-armed :deep(.w-e-text-container),
.brush-armed :deep(.w-e-text-container [data-slate-editor]) {
  cursor: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24"><path d="M18 4V3c0-.55-.45-1-1-1H5c-.55 0-1 .45-1 1v4c0 .55.45 1 1 1h12c.55 0 1-.45 1-1V6h1v4H9v11c0 .55.45 1 1 1h2c.55 0 1-.45 1-1v-9h8V4h-3z" fill="%23303133"/></svg>') 3 19, text;
}
/* 连续模式（双击格式刷）：紫色刷子区分 */
.brush-locked :deep(.w-e-text-container),
.brush-locked :deep(.w-e-text-container [data-slate-editor]) {
  cursor: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24"><path d="M18 4V3c0-.55-.45-1-1-1H5c-.55 0-1 .45-1 1v4c0 .55.45 1 1 1h12c.55 0 1-.45 1-1V6h1v4H9v11c0 .55.45 1 1 1h2c.55 0 1-.45 1-1v-9h8V4h-3z" fill="%237c5cff"/></svg>') 3 19, text;
}
.re-toolbar { border-bottom: 1px solid #ebeef5; flex-shrink: 0; }
/* 工具栏放大一号且单行不换行（窗口过窄时裁切右侧低频按钮，undo/redo 有快捷键兜底）；
   overflow-x: clip 不会把 overflow-y 变成 auto，下拉面板（字号/颜色等）不会被纵向裁掉 */
.re-toolbar :deep(.w-e-toolbar) { flex-wrap: nowrap; overflow-x: clip; overflow-y: visible; }
.re-toolbar :deep(.w-e-bar-item) { height: 40px; padding: 2px 1px; flex-shrink: 0; }
.re-toolbar :deep(.w-e-bar-item button) { height: 36px; padding: 0 6px; font-size: 15px; }
.re-toolbar :deep(.w-e-bar-item button svg) { width: 1.15em; height: 1.15em; }
.re-toolbar :deep(.w-e-bar-divider) { height: 40px; flex-shrink: 0; margin-left: 2px; margin-right: 2px; }
.re-toolbar :deep(.w-e-select-list) { margin-top: 40px; }
.re-body { flex: 1; min-height: 0; overflow-y: hidden !important; }

/* 编辑区留白：左侧与页面对齐（标题栏 padding 24px），底部留足滚动余量 */
.re-body :deep(.w-e-text-container [data-slate-editor]) { padding: 8px 24px 120px; }
.re-body :deep(.w-e-text-placeholder) { left: 24px; top: 17px; }

/* 列表序号/符号列穿透：拖选经过序号区时浏览器直接命中正文文本（原生选区扩展不再塌陷）；
   序号区按下由 onMarkerDown 重定向到文本开头接管。待办 checkbox 容器无此属性，不受影响 */
.re-body :deep(.w-e-text-container span[data-w-e-reserve="true"]) { pointer-events: none; }

/* 行距收紧（wangEditor 默认 p margin 15px 偏大） */
.re-body :deep(.w-e-text-container [data-slate-editor]) { line-height: 1.2; }
.re-body :deep(.w-e-text-container [data-slate-editor] p) { margin: 2px 0; }
.re-body :deep(.w-e-text-container [data-slate-editor] h1),
.re-body :deep(.w-e-text-container [data-slate-editor] h2),
.re-body :deep(.w-e-text-container [data-slate-editor] h3) { margin: 12px 0 6px; }
.re-body :deep(.w-e-text-container [data-slate-editor] blockquote),
.re-body :deep(.w-e-text-container [data-slate-editor] ul),
.re-body :deep(.w-e-text-container [data-slate-editor] ol) { margin: 6px 0; }
.re-body :deep(.w-e-text-container [data-slate-editor] pre) { margin: 6px 0; }

/* 表格默认列宽加大（wangEditor 默认 min-width 30px → 120px，约 4 倍） */
.re-body :deep(.w-e-text-container [data-slate-editor] table td),
.re-body :deep(.w-e-text-container [data-slate-editor] table th) { min-width: 120px; }

/* 工具栏最左侧的 AI 写作按钮（与工具栏同高） */
.re-toolbar :deep(.ai-write-item) { display: flex; align-items: center; }
.re-toolbar :deep(.ai-write-btn) {
  height: 36px; padding: 0 10px; border: none; border-radius: 4px; background: transparent;
  color: var(--grt-ai); font-size: 14px; font-weight: 600; cursor: pointer; white-space: nowrap;
}
.re-toolbar :deep(.ai-write-btn:hover) { background-color: var(--w-e-toolbar-active-bg-color); }

/* 查找替换面板 */
.fr-panel {
  position: absolute; top: 52px; right: 16px; z-index: 200; width: 340px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, .12); padding: 10px;
  display: flex; flex-direction: column; gap: 8px;
}
.fr-row { display: flex; align-items: center; gap: 6px; }
.fr-input {
  flex: 1; min-width: 0; height: 30px; padding: 0 10px; font-size: 13px; color: #303133;
  border: 1px solid #dcdfe6; border-radius: 6px; outline: none;
}
.fr-input:focus { border-color: #409eff; }
.fr-count { font-size: 12px; color: #909399; min-width: 34px; text-align: center; }
.fr-btn {
  height: 30px; min-width: 30px; padding: 0 6px; border: 1px solid #dcdfe6; border-radius: 6px;
  background: #fff; color: #606266; font-size: 13px; cursor: pointer;
}
.fr-btn:hover:not(:disabled) { border-color: #409eff; color: #409eff; }
.fr-btn:disabled { color: #c0c4cc; cursor: not-allowed; }
.fr-text { padding: 0 10px; }
.fr-close { border: none; font-size: 16px; }
</style>
