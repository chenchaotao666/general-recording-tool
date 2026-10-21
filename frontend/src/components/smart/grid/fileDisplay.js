export function fileUrl(file, preview = false) {
  if (file?.url && /^https?:\/\//i.test(file.url)) return file.url
  if (!/^[a-f0-9]{32}$/.test(file?.id || '')) return ''
  return `/api/smart/files/${file.id}?token=${localStorage.getItem('grt_token') || ''}&tenant_id=${localStorage.getItem('grt_tenant_id') || ''}${preview ? '&preview=true' : ''}`
}
export function fileKind(file) {
  const ext = (file?.name || '').split('.').pop().toLowerCase()
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].includes(ext)) return { text: '▧', color: '#23a8f2', image: true }
  if (['xls', 'xlsx', 'csv'].includes(ext)) return { text: 'X', color: '#128444' }
  if (['doc', 'docx'].includes(ext)) return { text: 'W', color: '#337ce0' }
  if (['ppt', 'pptx'].includes(ext)) return { text: 'P', color: '#ef8736' }
  if (ext === 'pdf') return { text: 'PDF', color: '#e85d56' }
  if (['zip', 'rar', '7z'].includes(ext)) return { text: 'ZIP', color: '#9871d7' }
  return { text: file?.url ? '↗' : 'F', color: '#8b95a5' }
}
export function fileSize(size) {
  if (size == null) return ''
  if (size < 1024) return `${size}B`
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)}KB`
  return `${(size / 1024 ** 2).toFixed(2)}MB`
}
