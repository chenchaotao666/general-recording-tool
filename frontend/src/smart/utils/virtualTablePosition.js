// Horizontal transforms rasterize cell borders at fractional pixels under zoom.
// Keep VXE's vertical translation, but apply its virtual column offset as layout
// position. Only virtual-window changes update styles; native scrolling does not.
export function installVirtualTablePosition(root) {
  const selector = '.vxe-table--body'
  const update = table => {
    const match = table.style.transform.match(/^translate\(\s*(-?[\d.]+px),\s*(-?[\d.]+px)\s*\)$/)
    if (!match) return
    for (const [name, value] of [['--st-virtual-x', match[1]], ['--st-virtual-y', match[2]]]) {
      if (table.style.getPropertyValue(name) !== value) table.style.setProperty(name, value)
    }
    table.classList.add('st-virtual-position')
  }
  const observer = new MutationObserver(records => {
    new Set(records.map(record => record.target)).forEach(update)
  })
  // Watch only table styles and the surrounding shell. Rows/cells can be replaced
  // freely without delivering mutation records or scanning their descendants.
  const structureObserver = new MutationObserver(connect)
  function connect() {
    observer.disconnect()
    structureObserver.disconnect()
    function visit(node) {
      if (node.matches(selector)) {
        update(node)
        observer.observe(node, { attributes: true, attributeFilter: ['style'] })
        return
      }
      if (node.tagName === 'TABLE') return
      structureObserver.observe(node, { childList: true })
      for (const child of node.children) visit(child)
    }
    visit(root)
  }
  connect()
  return () => {
    observer.disconnect()
    structureObserver.disconnect()
    root.querySelectorAll(selector).forEach(table => {
      table.classList.remove('st-virtual-position')
      table.style.removeProperty('--st-virtual-x')
      table.style.removeProperty('--st-virtual-y')
    })
  }
}
