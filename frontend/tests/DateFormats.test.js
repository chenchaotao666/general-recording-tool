import { expect, test } from 'vitest'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { DATE_FORMATS, dayjsDateFormat, formatDate } from '../src/smart/utils/format.js'

test('all nine date format examples match cell and editor display', () => {
  expect(DATE_FORMATS).toHaveLength(9)
  for (const { v, l } of DATE_FORMATS) {
    expect(formatDate('2018-04-20 14:00:00', { format: v })).toBe(l)
    expect(dayjs('2018-04-20T14:00:00').locale('zh-cn').format(dayjsDateFormat({ format: v }))).toBe(l)
  }
})

test('weekday and unpadded month/day work beyond the preview date', () => {
  expect(formatDate('2026-02-01T09:05:00', { format: 'yyyy年M月d日 EEEE' })).toBe('2026年2月1日 星期日')
  expect(formatDate('2026-02-01T09:05:00', { format: 'd/M/yyyy' })).toBe('1/2/2026')
  expect(formatDate(null, { format: 'M月d日' })).toBe('')
})
