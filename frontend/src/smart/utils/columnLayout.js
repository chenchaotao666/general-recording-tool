// A grouped header must not span the frozen and scrolling panes.
export function buildColumnLayout(fields, groups, frozenFieldId) {
  const nodes = []
  const emitted = new Set()
  for (const field of fields) {
    const group = groups.find(g => g.field_names?.includes(field.field_name))
    if (!group) nodes.push({ key: field.field_name, isGroup: false, field })
    else if (!emitted.has(group.id)) {
      emitted.add(group.id)
      nodes.push({ key: `g_${group.id}`, isGroup: true, name: group.name, group,
        fields: fields.filter(f => group.field_names.includes(f.field_name)) })
    }
  }
  const displayed = nodes.flatMap(n => n.isGroup ? n.fields : [n.field])
  const boundary = displayed.findIndex(f => f.field_name === frozenFieldId)
  const frozen = new Set(displayed.slice(0, boundary + 1).map(f => f.field_name))
  return nodes.flatMap(node => {
    if (!node.isGroup) return [{ ...node, fixed: frozen.has(node.field.field_name) ? 'left' : undefined }]
    return [true, false].flatMap(fixed => {
      const members = node.fields.filter(f => frozen.has(f.field_name) === fixed)
      return members.length ? [{ ...node, key: `${node.key}_${fixed ? 'left' : 'main'}`,
        fields: members, fixed: fixed ? 'left' : undefined }] : []
    })
  })
}
