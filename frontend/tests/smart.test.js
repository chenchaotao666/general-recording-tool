// 智能表纯函数测试：格式化 / 填色求值 / 撤销栈 / 注册表完整性
import { describe, expect, it } from 'vitest'
import { formatCurrency, formatDate, formatNumber, evalFillRules, matchCondition, isRuleComplete, createUndoStack } from '../src/smart/utils/format.js'
import { FIELD_REGISTRY, conditionToRule, sortDirectionLabels } from '../src/smart/registry/fieldRegistry.js'
import { filterLinkageOptions, resolveRefOptions } from '../src/smart/utils/refOptions.js'
import { presetFromFilters } from '../src/smart/utils/newRowPreset.js'

describe('format', () => {
  it('数字千位符与精度', () => {
    expect(formatNumber(1234567.891, { thousandSeparator: true })).toBe('1,234,567.891')
    expect(formatNumber(3.14159, { precision: 2 })).toBe('3.14')
    expect(formatNumber(null)).toBe('')
  })
  it('货币', () => {
    expect(formatCurrency(68000, { currencySymbol: '￥', precision: 2, thousandSeparator: true })).toBe('￥68,000.00')
    expect(formatCurrency(100, { currencySymbol: '$', precision: 'default', thousandSeparator: false })).toBe('$100')
  })
  it('日期格式枚举', () => {
    expect(formatDate('2026-10-13 10:30:00', { format: 'yyyy-MM-dd' })).toBe('2026-10-13')
    expect(formatDate('2026-10-13 10:30:00', { format: 'yyyy年M月d日' })).toBe('2026年10月13日')
    expect(formatDate('2026-10-13 10:30:00', { format: 'yyyy-MM-dd HH:mm' })).toBe('2026-10-13 10:30')
  })
})

describe('填色规则求值', () => {
  const field = { field_name: 'f_1' }
  it('命中与优先级（order 小先生效）', () => {
    const rules = [
      { id: 'a', fieldId: 'f_1', operator: 'contains', value: 'P', color: 'red', order: 1 },
      { id: 'b', fieldId: 'f_1', operator: 'contains', value: 'P0', color: 'blue', order: 0 },
    ]
    expect(evalFillRules(rules, field, 'P001')).toBe('blue')
    expect(evalFillRules(rules, field, 'X')).toBe(null)
  })
  it('条件不完整不生效', () => {
    expect(evalFillRules([{ fieldId: 'f_1', operator: 'contains', color: 'red' }], field, 'P')).toBe(null)
    expect(isRuleComplete({ fieldId: 'f_1', operator: 'contains', value: 'x' })).toBe(true)
    expect(isRuleComplete({ fieldId: 'f_1', operator: 'isEmpty' })).toBe(true)
  })
  it('数组字段 contains=交集', () => {
    expect(matchCondition({ operator: 'contains', value: ['a'] }, ['a', 'b'])).toBe(true)
    expect(matchCondition({ operator: 'contains', value: ['c'] }, ['a', 'b'])).toBe(false)
    expect(matchCondition({ operator: 'isEmpty' }, [])).toBe(true)
  })
})

describe('撤销栈', () => {
  it('do/undo/redo 顺序与上限', async () => {
    const stack = createUndoStack(3)
    const log = []
    for (let i = 1; i <= 5; i++) {
      stack.push({ label: `op${i}`, undo: async () => log.push(`u${i}`), redo: async () => log.push(`r${i}`) })
    }
    expect(stack.canUndo).toBe(true)
    await stack.undo(); await stack.undo()
    expect(log).toEqual(['u5', 'u4'])   // 上限 3：栈里只剩 op3/4/5
    await stack.redo()
    expect(log).toEqual(['u5', 'u4', 'r4'])
    stack.clear()
    expect(stack.canUndo).toBe(false)
  })
})

describe('字段注册表', () => {
  it('支持的字段类型注册完整，已移除电话和邮箱类型', () => {
    expect(FIELD_REGISTRY.phone).toBeUndefined()
    expect(FIELD_REGISTRY.email).toBeUndefined()
    const expected = ['text', 'singleSelect', 'multiSelect', 'number', 'percent', 'currency', 'date',
      'checkbox', 'url', 'member', 'progress', 'image', 'file', 'autoNumber',
      'relation', 'lookup', 'formula', 'createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime']
    for (const ft of expected) {
      const reg = FIELD_REGISTRY[ft]
      expect(reg, ft).toBeTruthy()
      expect(reg.label && reg.icon && reg.editor && reg.filterOps.length, ft).toBeTruthy()
      expect(reg.defaultConfig()).toBeTypeOf('object')
    }
  })
  it('排序方向文案类型自适应', () => {
    expect(sortDirectionLabels({ field_type: 'singleSelect' })).toEqual(['选项正序', '选项逆序'])
    expect(sortDirectionLabels({ field_type: 'number' })).toEqual(['0 → 9', '9 → 0'])
    expect(sortDirectionLabels({ field_type: 'date' })).toEqual(['早 → 晚', '晚 → 早'])
    expect(sortDirectionLabels({ field_type: 'text' })).toEqual(['A → Z', 'Z → A'])
  })
  it('视图 DSL → dyn 运算符映射', () => {
    expect(conditionToRule({ fieldId: 'f_1', operator: 'notContains', value: 'x' }))
      .toEqual({ field: 'f_1', op: 'not_contains', value: 'x' })
    expect(conditionToRule({ fieldId: 'f_1', operator: 'isEmpty' })).toEqual({ field: 'f_1', op: 'empty' })
    expect(conditionToRule({ fieldId: 'f_1', operator: 'bogus' })).toBe(null)
  })
})

describe('引用选项与选项联动（refOptions）', () => {
  const localField = { field_name: 'f_1', options: { options: [{ id: 'opt_1', label: '本地' }] } }
  const refFieldMeta = { field_name: 'priority', field_type: 'singleSelect',
    options: { options: [{ id: 'opt_h', label: '高' }, { id: 'opt_l', label: '低' }] } }

  it('manual 模式取本地选项；reference 模式取引用字段选项', () => {
    expect(resolveRefOptions(localField, null)).toEqual([{ id: 'opt_1', label: '本地' }])
    const refMode = { field_name: 'f_2', options: { optionSource: 'reference', reference: { tableId: 1, fieldId: 'priority' } } }
    expect(resolveRefOptions(refMode, refFieldMeta)).toEqual(refFieldMeta.options.options)
    expect(resolveRefOptions(refMode, null)).toEqual([])   // 引用源缺失兜底空数组
  })

  const options = [{ id: 'opt_h' }, { id: 'opt_l' }, { id: 'opt_m' }]
  const remoteRows = [
    { id: 1, unit: '单位A', priority: 'opt_h' },
    { id: 2, unit: '单位B', priority: 'opt_l' },
    { id: 3, unit: '单位A', priority: 'opt_m' },
  ]
  const linkage = (match) => ({ enabled: true, match, conditions: [{ localFieldId: 'f_unit', operator: 'eq', remoteFieldId: 'unit' }] })

  it('联动 all/any 过滤与空值空集', () => {
    // 本表行 单位=单位A → 命中行 1/3 → opt_h/opt_m
    expect(filterLinkageOptions(options, linkage('all'), { f_unit: '单位A' }, remoteRows, 'priority')
      .map(o => o.id)).toEqual(['opt_h', 'opt_m'])
    // 本表字段值为空 → 空集
    expect(filterLinkageOptions(options, linkage('all'), { f_unit: null }, remoteRows, 'priority')).toEqual([])
    // 未启用联动 → 原样返回
    expect(filterLinkageOptions(options, { enabled: false }, {}, remoteRows, 'priority')).toEqual(options)
  })

  it('多条件 all 与 any 的区别', () => {
    const lk = (match) => ({ enabled: true, match, conditions: [
      { localFieldId: 'f_unit', operator: 'eq', remoteFieldId: 'unit' },
      { localFieldId: 'f_pri', operator: 'eq', remoteFieldId: 'priority' },
    ] })
    const record = { f_unit: '单位A', f_pri: 'opt_l' }
    // all：行需同时满足 单位A 且 priority=opt_l → 无命中 → 空
    expect(filterLinkageOptions(options, lk('all'), record, remoteRows, 'priority')).toEqual([])
    // any：单位A 命中行 1/3，priority=opt_l 命中行 2 → 三者并集
    expect(filterLinkageOptions(options, lk('any'), record, remoteRows, 'priority')
      .map(o => o.id)).toEqual(['opt_h', 'opt_l', 'opt_m'])
  })
})

describe('添加一行：按筛选条件预设初始值（newRowPreset）', () => {
  const fields = [
    { field_name: 'f_t', field_type: 'text' },
    { field_name: 'f_s', field_type: 'singleSelect', options: { options: [{ id: 'o1' }, { id: 'o2' }] } },
    { field_name: 'f_m', field_type: 'multiSelect', options: { options: [{ id: 'm1' }, { id: 'm2' }] } },
    { field_name: 'f_n', field_type: 'number' },
    { field_name: 'f_d', field_type: 'date' },
    { field_name: 'f_u', field_type: 'member', options: { multiple: true } },
    { field_name: 'f_c', field_type: 'checkbox' },
    { field_name: 'f_x', field_type: 'formula' },
  ]
  const now = new Date(2026, 9, 18)   // 2026-10-18（周日）
  const run = (conditions, conjunction = 'and') => presetFromFilters({ conditions, conjunction, fields, viewerId: 7, now })

  it('AND：各类型取满足条件的值', () => {
    expect(run([
      { fieldId: 'f_t', operator: 'contains', value: 'abc' },
      { fieldId: 'f_s', operator: 'eq', value: ['o2'] },
      { fieldId: 'f_m', operator: 'contains', value: ['m1', 'm2'] },
      { fieldId: 'f_u', operator: 'contains', value: ['$viewer'] },
      { fieldId: 'f_c', operator: 'eq', value: true },
    ])).toEqual({ f_t: 'abc', f_s: 'o2', f_m: ['m1'], f_u: [7], f_c: true })
  })
  it('数字区间与日期模式', () => {
    expect(run([{ fieldId: 'f_n', operator: 'gt', value: 5 }, { fieldId: 'f_n', operator: 'lt', value: 10 }])).toEqual({ f_n: 6 })
    expect(run([{ fieldId: 'f_d', operator: 'eq', value: { mode: 'thisWeek' } }])).toEqual({ f_d: '2026-10-12 00:00:00' })
    expect(run([{ fieldId: 'f_d', operator: 'gt', value: { mode: 'today' } }])).toEqual({ f_d: '2026-10-19 00:00:00' })
  })
  it('不等于/不包含：挑条件之外的值；为空：不预设', () => {
    expect(run([{ fieldId: 'f_s', operator: 'neq', value: ['o1'] }])).toEqual({ f_s: 'o2' })
    expect(run([{ fieldId: 'f_t', operator: 'neq', value: '新记录' }])).toEqual({ f_t: '新记录1' })
    expect(run([{ fieldId: 'f_t', operator: 'isEmpty' }])).toEqual({})
  })
  it('只读字段跳过；OR：已天然命中则不预设，否则取第一个可满足的条件', () => {
    expect(run([{ fieldId: 'f_x', operator: 'eq', value: '1' }])).toEqual({})
    expect(run([{ fieldId: 'f_n', operator: 'eq', value: 3 }, { fieldId: 'f_t', operator: 'isEmpty' }], 'or')).toEqual({})
    expect(run([{ fieldId: 'f_x', operator: 'eq', value: '1' }, { fieldId: 'f_n', operator: 'gte', value: 3 }], 'or')).toEqual({ f_n: 3 })
  })
})
