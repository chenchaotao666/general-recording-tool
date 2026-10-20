// Preset IDs are stored alongside existing uploaded image IDs.
export const FORM_COVERS = [
  { id: 'geometry', name: '蓝色几何' },
  { id: 'snow', name: '雪山' },
  { id: 'desert', name: '沙丘' },
  { id: 'forest', name: '青山' },
  { id: 'lake', name: '云雾山谷' },
  { id: 'nebula', name: '星云' },
  { id: 'earth', name: '星球' },
].map(item => ({ ...item, value: `preset:${item.id}`, src: `/form-covers/${item.id}.${item.id === 'geometry' ? 'svg' : 'jpg'}` }))

export function presetCoverUrl(value) {
  return FORM_COVERS.find(item => item.value === value)?.src || ''
}
