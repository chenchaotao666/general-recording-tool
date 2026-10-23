const shapes = { rectangle: '矩形', rect: '矩形', ellipse: '圆形', diamond: '菱形', line: '线条', curve: '曲线笔触', arrow: '箭头', text: '文字' }
const properties = { strokeColor: '边框/线条颜色', backgroundColor: '填充色', textColor: '文字颜色',
  fillStyle: '填充样式', strokeStyle: '线型', strokeWidth: '线宽', roughness: '手绘程度', opacity: '不透明度', fontSize: '字号' }
const values = { transparent: '无填充', solid: '实线/纯色', dashed: '虚线', dotted: '点线', hachure: '斜线填充', 'cross-hatch': '交叉线填充' }
const styles = item => Object.entries(properties).filter(([key]) => item[key] != null)
  .map(([key, label]) => `${label}：${values[item[key]] || item[key]}`).join('，')

// Summarize the actual validated result, not an additional model's promise.
export function aiChangeSummary(result, context = []) {
  if (result.mode === 'append' && result.parts?.some(part => part.attachTo)) {
    return [`将分别展开 ${result.parts.length} 个已有节点，保留原图，不复制已有层级。`,
      ...result.parts.flatMap(part => aiChangeSummary({ ...part, mode: 'append' }, context))]
  }
  const lines = []
  if (result.edits?.length) {
    const byId = new Map(context.map(item => [item.id, item]))
    const removed = result.edits.filter(edit => edit.delete).length
    lines.push(`将修改 ${result.edits.length - removed} 个元素${removed ? `，删除 ${removed} 个元素` : ''}。`)
    for (const edit of result.edits) {
      const item = byId.get(edit.id)
      const name = item?.text ? `「${item.text}」` : `${shapes[item?.type] || '元素'}（${edit.id}）`
      if (edit.delete) lines.push(`删除 ${name}及其附属文字。`)
      else {
        const details = []
        if (edit.text != null) details.push(`文字改为「${edit.text}」`)
        if (styles(edit)) details.push(styles(edit))
        lines.push(`${name}：${details.join('；')}`)
      }
    }
    lines.push('其余元素保持不变。')
    return lines
  }
  const selectedCount = context.filter(item => item.selected).length
  if (result.mode === 'append' && result.attachTo) {
    const target = context.find(item => item.id === result.attachTo)
    lines.push(`在「${target?.text || '目标节点'}」下方新增分支并连接到该节点，保留原有节点和连线。`)
  }
  else if (result.mode === 'append') lines.push('在现有内容旁追加以下内容，保留原有画布。')
  else if (result.mode === 'modify' && selectedCount) lines.push(`替换选中的 ${selectedCount} 个元素，其余内容保留。`)
  else lines.push(context.length ? '替换整张画布，原有内容将被以下结果替代。' : '在空画布中新增以下内容。')
  for (const part of result.parts?.length ? result.parts : [result]) {
    if (part.title) lines.push(`内容：${part.title}`)
    if (part.nodes?.length) {
      lines.push(`流程/关系图：${part.nodes.length} 个节点，${part.edges?.length || 0} 条连线。`)
      part.nodes.forEach(node => lines.push(`节点「${node.label}」${styles(node) ? `：${styles(node)}` : ''}`))
      const edgeStyles = [...new Set((part.edges || []).map(styles).filter(Boolean))]
      edgeStyles.forEach(style => lines.push(`连线样式：${style}`))
    } else if (part.elements?.length) {
      const counts = {}
      part.elements.forEach(e => { const label = shapes[e.type] || e.type; counts[label] = (counts[label] || 0) + 1 })
      lines.push(`图形：${Object.entries(counts).map(([name, count]) => `${name} ${count} 个`).join('、')}。`)
      for (const e of part.elements) {
        const detail = [e.text || e.label?.text ? `文字「${e.text || e.label.text}」` : '', styles(e)].filter(Boolean).join('；')
        if (detail) lines.push(`${shapes[e.type] || e.type}：${detail}`)
      }
    } else if (part.headers?.length) {
      lines.push(`表格：${part.headers.length} 列、${part.rows?.length || 0} 行数据；表头：${part.headers.join('、')}。`)
      if (styles(part)) lines.push(styles(part))
    }
  }
  return lines
}
