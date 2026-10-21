import { expect, test, vi } from 'vitest'
import { applyColumnWidths } from '../src/smart/utils/applyColumnWidths.js'

test('auto fit overrides manual widths in one layout refresh, preserving other columns and viewport', async () => {
  const columns = { check: { resizeWidth: 250 }, date: { resizeWidth: 310 }, text: { resizeWidth: 220 } }
  const table = {
    getScroll: () => ({ scrollLeft: 480, scrollTop: 720 }),
    getColumnByField: name => columns[name],
    refreshColumn: vi.fn().mockResolvedValue(), scrollTo: vi.fn().mockResolvedValue(),
  }
  await applyColumnWidths(table, { check: 80, date: 120, hidden: 100 })
  expect(columns.check.resizeWidth).toBe(80)
  expect(columns.date.resizeWidth).toBe(120)
  expect(columns.text.resizeWidth).toBe(220)
  expect(table.refreshColumn).toHaveBeenCalledTimes(1)
  expect(table.scrollTo).toHaveBeenCalledWith(480, 720)
  columns.check.resizeWidth = 290
  await applyColumnWidths(table, { check: 80 })
  expect(columns.check.resizeWidth).toBe(80)
})
