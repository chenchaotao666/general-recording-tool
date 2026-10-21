import { computed } from 'vue'
import { optionColor } from '../registry/fieldRegistry.js'

// Shared by all cells using the same option list, including remounted virtual cells.
// A computed index also invalidates on in-place option edits.
const indexes = new WeakMap()
const emptyOptions = []
export function resolveEnumTags(options, value) {
  if (value == null) return []
  options = options || emptyOptions
  let index = indexes.get(options)
  if (!index) {
    index = computed(() => {
      const tags = new Map()
      for (const option of options) {
        if (tags.has(option.id)) continue
        const color = optionColor(option.color)
        tags.set(option.id, { key: option.id, label: option.label,
          style: { background: color.value, color: color.text } })
      }
      return tags
    })
    indexes.set(options, index)
  }
  const tags = [], raw = []
  for (const id of Array.isArray(value) ? value : [value]) {
    const tag = index.value.get(id)
    if (tag) tags.push(tag)
    else if (id != null && id !== '') raw.push({ key: `raw-${raw.length}`,
      label: typeof id === 'object' ? JSON.stringify(id) : String(id), raw: true })
  }
  return tags.concat(raw)
}
