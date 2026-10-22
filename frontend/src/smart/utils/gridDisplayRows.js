import { shallowReactive, toRaw } from 'vue'
import { sameRecordValue } from './reconcileRows.js'

// VXE reloads its data when the array changes. Keep display rows reactive and
// patch values in place when the visible row order is unchanged.
export function updateGridDisplayRows(previous, incoming) {
  const oldRows = new Map(previous.map(row => [toRaw(row).__key, row]))
  const next = incoming.map(data => {
    const row = oldRows.get(data.__key)
    if (!row) return shallowReactive({ ...data })
    const raw = toRaw(row)
    for (const key of Object.keys(raw)) {
      if (!Object.prototype.hasOwnProperty.call(data, key)) delete row[key]
    }
    for (const key of Object.keys(data)) {
      if (!sameRecordValue(raw[key], data[key])) row[key] = data[key]
    }
    return row
  })
  return next.length === previous.length && next.every((row, i) => row === previous[i]) ? previous : next
}
