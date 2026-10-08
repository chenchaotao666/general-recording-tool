// Luckysheet 懒加载：按需注入 css/script（~6MB，只在打开 Excel 模板编辑器时加载一次）。
const BASE = '/luckysheet'

const CSS = [
  `${BASE}/plugins/css/pluginsCss.css`,
  `${BASE}/plugins/plugins.css`,
  `${BASE}/css/luckysheet.css`,
  `${BASE}/assets/iconfont/iconfont.css`,
]
// plugin.js 必须先于 luckysheet.umd.js（内含 jQuery 等依赖）
const JS = [`${BASE}/plugins/js/plugin.js`, `${BASE}/luckysheet.umd.js`]

let promise = null

function loadCss(href) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('link')
    el.rel = 'stylesheet'
    el.href = href
    el.onload = resolve
    el.onerror = () => reject(new Error(`样式加载失败：${href}`))
    document.head.appendChild(el)
  })
}

function loadJs(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script')
    el.src = src
    el.onload = resolve
    el.onerror = () => reject(new Error(`脚本加载失败：${src}`))
    document.body.appendChild(el)
  })
}

export function loadLuckysheet() {
  if (window.luckysheet) return Promise.resolve(window.luckysheet)
  if (!promise) {
    promise = (async () => {
      await Promise.all(CSS.map(loadCss))
      for (const src of JS) await loadJs(src)
      if (!window.luckysheet) throw new Error('luckysheet 初始化失败')
      patchInputBoxFocus()
      return window.luckysheet
    })().catch((e) => { promise = null; throw e })
  }
  return promise
}

// 修补：luckysheet 2.1.x 的已知缺陷——选中单元格直接打字时，文字进入停在屏幕外
// （top:-10000px）的隐藏输入框，既不显示光标、提交/双击还容易触发 updatecell 崩溃。
//
// 方案：拦截"选区存在且未在编辑"时的可打印按键/中文 IME 输入，向选中单元格合成
// 一次 dblclick——走 luckysheet 原生"双击进入编辑"路径（定位/样式/提交/守卫全部原生），
// 再把首个字符补进编辑器。体验和 Excel 一致：打字即在单元格内原位编辑。
let inputBoxPatched = false
function patchInputBoxFocus(containerId = 'ptSheetBox') {
  if (inputBoxPatched) return
  inputBoxPatched = true

  const box = () => document.getElementById('luckysheet-input-box')
  // 提交/取消后焦点常留在已停靠（top:-10000）的编辑器里——那是"假编辑"状态，不算在编辑
  const isEditing = () => {
    if (document.activeElement?.id !== 'luckysheet-rich-text-editor') return false
    const b = box()
    return !!b && Number.parseFloat(getComputedStyle(b).top) > 0
  }
  const hasSelection = () => !!document.querySelector(`#${containerId} .luckysheet-cell-selected`)

  // 在选中单元格中心合成 dblclick，触发原生编辑启动；firstChar 为需要补入的首字符
  function startNativeEdit(firstChar) {
    const sel = document.querySelector(`#${containerId} .luckysheet-cell-selected`)
    if (!sel) return
    // 清掉"假编辑"焦点（提交后残留在停靠编辑器上），避免 IME 会话绑错元素
    if (document.activeElement?.id === 'luckysheet-rich-text-editor') {
      document.activeElement.blur()
    }
    const r = sel.getBoundingClientRect()
    const x = r.left + r.width / 2
    const y = r.top + r.height / 2
    const target = document.elementFromPoint(x, y) || sel
    target.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, clientX: x, clientY: y }))
    // 本函数只由"打字"触发，打字=覆盖：打开后全选（后续 insertText/IME 组合自然替换）
    setTimeout(() => {
      if (!isEditing()) return
      document.execCommand('selectAll')
      if (firstChar) document.execCommand('insertText', false, firstChar)
    }, 0)
  }

  // 可打印字符：拦截默认行为（否则会输进屏幕外的隐藏框），转原生编辑
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.altKey || e.metaKey || e.key.length !== 1) return
    if (isEditing() || !hasSelection()) return
    const ae = document.activeElement
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA')) return
    // luckysheet 编辑器"假聚焦"（焦点在停靠的隐藏输入框上）不免除拦截
    if (ae?.isContentEditable && ae.id !== 'luckysheet-rich-text-editor') return
    e.preventDefault()
    e.stopPropagation()
    startNativeEdit(e.key)
  }, true)

  // 中文 IME：compositionstart 时同样先拉起原生编辑，拼音/候选字直接进单元格编辑框
  document.addEventListener('compositionstart', () => {
    if (isEditing() || !hasSelection()) return
    const ae = document.activeElement
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA')) return
    startNativeEdit(null)
  }, true)

  // IME 提交/insertText 落在停靠编辑器（提交后的"假编辑"焦点）时：转到当前选区重放
  document.addEventListener('beforeinput', (e) => {
    if (isEditing() || !hasSelection()) return
    if (document.activeElement?.id !== 'luckysheet-rich-text-editor') return
    if (!['insertText', 'insertCompositionText', 'insertFromPaste'].includes(e.inputType)) return
    e.preventDefault()
    const text = e.data || ''
    startNativeEdit(null)
    setTimeout(() => {
      if (isEditing() && text) document.execCommand('insertText', false, text)
    }, 0)
  }, true)

  // 工具栏下拉选中态同步（luckysheet 原生 bug：菜单创建时永远勾选第一项——对齐勾
  // 「左对齐」、换行勾「截断」、旋转勾「无」，重开也不同步）。工具栏按钮的 type 属性
  // 才是当前单元格的真实状态（选区变化时会同步过去），以它为准打勾。
  // 四类下拉同构：#luckysheet-icon-{align,valign,textwrap,rotation}-menu，
  // 主按钮 #luckysheet-icon-{...}，菜单 #...-menuButton，菜单项带 itemvalue + span.icon
  document.addEventListener('click', (e) => {
    const btn = e.target?.closest?.(
      '#luckysheet-icon-align-menu, #luckysheet-icon-valign-menu,'
      + ' #luckysheet-icon-textwrap-menu, #luckysheet-icon-rotation-menu',
    )
    if (!btn) return
    setTimeout(() => {
      const mainBtn = document.getElementById(btn.id.replace('-menu', ''))
      const menu = document.getElementById(`${btn.id}-menuButton`)
      if (!mainBtn || !menu) return
      const cur = mainBtn.getAttribute('type')
      menu.querySelectorAll('.luckysheet-cols-menuitem span.icon')
        .forEach((el) => { el.innerHTML = '' })
      const target = (cur && menu.querySelector(`.luckysheet-cols-menuitem[itemvalue='${cur}'] span.icon`))
        || menu.querySelector('.luckysheet-cols-menuitem span.icon')
      if (target) target.innerHTML = '<i class="fa fa-check luckysheet-mousedown-cancel"></i>'
    }, 0)
  }, true)
}
