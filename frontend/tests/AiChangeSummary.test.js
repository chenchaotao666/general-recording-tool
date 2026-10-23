import { expect, test } from 'vitest'
import { aiChangeSummary } from '../src/views/whiteboard/aiChangeSummary.js'

test('continuation identifies the existing parent and promises preservation', () => {
  const lines = aiChangeSummary({ mode: 'append', attachTo: 'root', nodes: [{ id: 'a', label: '子节点' }], edges: [] }, [{ id: 'root', text: '机器人' }])
  expect(lines[0]).toContain('在「机器人」下方新增分支并连接到该节点')
  expect(lines[0]).toContain('保留原有节点和连线')
})

test('explains exact target edits, colors and deletions from the actual result', () => {
  const lines = aiChangeSummary({ edits: [{ id: 'a', backgroundColor: '#ff0000', text: '申请提交', opacity: 0 }, { id: 'b', delete: true }] },
    [{ id: 'a', text: '开始' }, { id: 'b', text: '结束' }]).join('\n')
  expect(lines).toContain('修改 1 个元素，删除 1 个元素')
  expect(lines).toContain('「开始」：文字改为「申请提交」')
  expect(lines).toContain('填充色：#ff0000')
  expect(lines).toContain('不透明度：0')
  expect(lines).toContain('删除 「结束」及其附属文字')
})

test('new content and append both have an actionable summary', () => {
  const drawing = { type: 'drawing', elements: [{ type: 'ellipse', backgroundColor: '#0000ff' }] }
  expect(aiChangeSummary({ mode: 'replace', ...drawing }).join('\n')).toContain('空画布中新增')
  const lines = aiChangeSummary({ mode: 'append', ...drawing }, [{ id: 'a' }]).join('\n')
  expect(lines).toContain('保留原有画布')
  expect(lines).toContain('圆形 1 个')
  expect(lines).toContain('填充色：#0000ff')
})

test('distinguishes replacing selection from replacing the full canvas', () => {
  const result = { mode: 'modify', nodes: [{ label: 'A' }], edges: [] }
  expect(aiChangeSummary(result, [{ selected: true }])[0]).toContain('选中的 1 个元素')
  expect(aiChangeSummary(result, [{}])[0]).toContain('替换整张画布')
})

test('mixed results describe every part including table columns and edge colors', () => {
  const lines = aiChangeSummary({ mode: 'append', parts: [
    { nodes: [{ label: '开始' }, { label: '结束' }], edges: [{ strokeColor: '#ff0000' }] },
    { headers: ['姓名', '角色'], rows: [['张三', '开发']] },
  ] }).join('\n')
  expect(lines).toContain('2 个节点，1 条连线')
  expect(lines).toContain('连线样式：边框/线条颜色：#ff0000')
  expect(lines).toContain('2 列、1 行数据；表头：姓名、角色')
})
