export function person(value) {
  return { id: value.user_id ?? value.id, name: value.name || value.username || `#${value.id}`, avatar: value.avatar || '' }
}
export function selectedIds(value) {
  return [...new Set((Array.isArray(value) ? value : value == null || value === '' ? [] : [value]).map(Number))]
}
export function togglePerson(ids, id, multiple) {
  return ids.includes(id) ? ids.filter(x => x !== id) : multiple ? [...ids, id] : [id]
}
