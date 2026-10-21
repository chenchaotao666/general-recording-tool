// 单一委托提示层：支持虚拟表格、动态按钮及 teleport 弹层，不为每个单元格挂载组件。
export function installSmartTooltips() {
  // 第三方表格会在全选框等内部节点自动生成 title；只处理智能表范围内新增/变化的节点。
  const scope = '.smart-home, .st-page, .dash-page, .st-pop, .st-tbpanel, .st-at-dialog'
  function migrateTitle(element) {
    if (!element?.hasAttribute?.('title') || !element.closest(scope)) return
    const value = element.getAttribute('title')
    if (value && !element.closest('.vxe-header--column, .sel-anchor .chev')) element.setAttribute('data-smart-tip', value)
    element.removeAttribute('title')
  }
  function scan(node) {
    if (node.nodeType !== 1) return
    migrateTitle(node)
    node.querySelectorAll('[title]').forEach(migrateTitle)
  }
  const generatedTitles = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes') migrateTitle(record.target)
      else record.addedNodes.forEach(scan)
    }
  })
  scan(document.body)
  generatedTitles.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['title'] })
  let anchor = null
  let tip = null
  let timer = null
  let observer = null
  const id = 'smart-native-replacement-tip'
  function shouldShow(element) {
    if (!element?.dataset.smartTip) return false
    const selector = element.dataset.smartTipOverflow
    if (!selector) return true
    const text = element.querySelector(selector)
    return !!text && (text.scrollWidth > text.clientWidth || text.scrollHeight > text.clientHeight)
  }

  function hide() {
    clearTimeout(timer)
    observer?.disconnect()
    observer = null
    if (anchor) {
      const ids = (anchor.getAttribute('aria-describedby') || '').split(/\s+/).filter(value => value && value !== id)
      if (ids.length) anchor.setAttribute('aria-describedby', ids.join(' '))
      else anchor.removeAttribute('aria-describedby')
    }
    tip?.remove()
    tip = null
    anchor = null
  }
  function place() {
    if (!anchor?.isConnected || !shouldShow(anchor)) { hide(); return }
    if (tip.textContent !== anchor.dataset.smartTip) tip.textContent = anchor.dataset.smartTip
    const rect = anchor.getBoundingClientRect()
    const size = tip.getBoundingClientRect()
    const left = Math.max(8, Math.min(rect.left + (rect.width - size.width) / 2, innerWidth - size.width - 8))
    const above = rect.top - size.height - 8
    const top = above >= 8 ? above : Math.max(8, Math.min(rect.bottom + 8, innerHeight - size.height - 8))
    Object.assign(tip.style, { left: `${left}px`, top: `${top}px`, visibility: 'visible' })
  }
  function show(element) {
    if (element === anchor) return
    hide()
    if (!shouldShow(element) || element.closest('.vxe-header--column, .sel-anchor .chev')) return
    anchor = element
    timer = setTimeout(() => {
      if (!anchor?.isConnected) { hide(); return }
      tip = document.createElement('div')
      tip.id = id
      tip.className = 'st-unified-tooltip'
      tip.setAttribute('role', 'tooltip')
      tip.style.visibility = 'hidden'
      document.body.appendChild(tip)
      const ids = (anchor.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean)
      anchor.setAttribute('aria-describedby', [...ids, id].join(' '))
      place()
      if (!tip) return
      // 虚拟滚动复用节点、动态文案更新或关闭弹层时，刷新提示或及时移除。
      observer = new MutationObserver(() => { if (tip) place() })
      observer.observe(anchor, { attributes: true, attributeFilter: ['data-smart-tip'] })
      observer.observe(document.body, { childList: true, subtree: true })
    }, 250)
  }
  const enter = event => show(event.target.closest?.('[data-smart-tip]'))
  const leave = event => {
    if (anchor?.contains(event.relatedTarget)) return
    hide()
  }
  const key = event => { if (event.key === 'Escape') hide() }
  const events = [
    ['pointerover', enter], ['pointerout', leave], ['focusin', enter], ['focusout', leave],
    ['pointerdown', hide], ['dragstart', hide], ['scroll', hide], ['keydown', key],
  ]
  for (const [name, handler] of events) document.addEventListener(name, handler, true)
  window.addEventListener('resize', hide)
  return () => {
    generatedTitles.disconnect()
    hide()
    for (const [name, handler] of events) document.removeEventListener(name, handler, true)
    window.removeEventListener('resize', hide)
  }
}
