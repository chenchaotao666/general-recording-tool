// Render in an isolated editor instance; never load a draft into the user's canvas.
export function renderDrawioPreview(xml) {
  return new Promise((resolve, reject) => {
    const frame = document.createElement('iframe')
    frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:1200px;height:800px;border:0'
    frame.setAttribute('aria-hidden', 'true')
    frame.tabIndex = -1
    const origin = 'https://embed.diagrams.net'
    const cleanup = () => { clearTimeout(timer); window.removeEventListener('message', receive); frame.remove() }
    const send = data => frame.contentWindow?.postMessage(JSON.stringify(data), origin)
    const receive = event => {
      if (event.source !== frame.contentWindow || event.origin !== origin) return
      let data
      try { data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data } catch { return }
      if (data?.event === 'init') send({ action: 'load', xml, autosave: 0 })
      if (data?.event === 'load') send({ action: 'export', format: 'png', xml, background: '#ffffff' })
      if (data?.event === 'export') {
        cleanup()
        if (typeof data.data === 'string' && data.data.startsWith('data:image/')) resolve(data.data)
        else reject(new Error('画布预览导出失败'))
      }
    }
    const timer = setTimeout(() => { cleanup(); reject(new Error('画布预览加载超时，请重试')) }, 30000)
    window.addEventListener('message', receive)
    frame.src = origin + '/?embed=1&proto=json&spin=1&noSaveBtn=1&noExitBtn=1'
    document.body.appendChild(frame)
  })
}
