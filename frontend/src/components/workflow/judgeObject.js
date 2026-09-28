// 条件/多路分支「判断对象」候选构建：SchemaForm 的下拉 与 WorkflowEditor 的 AI 配置上下文共用。
// vars 形状：[{title, items: [{label, expr}]}]（上游节点输出 + 触发器变量分组）
export function buildRecordOptions(vars) {
  const items = []   // {nodes.x.item}：逐条处理的当前条目
  const trig = []    // {trigger.record} / {trigger.old_record}
  const firsts = []  // {nodes.x.records.0} / {nodes.x.groups.0}：列表第一条
  const rest = []    // {nodes.x.record/stats/data} / {nodes.x}（对象输出）
  for (const g of vars || []) {
    for (const it of g.items) {
      // 文案：「组名 · 条目」（去掉「（整体）」后缀），避免「触发记录（整体）（触发器）」这种双层括号
      const o = { label: `${g.title} · ${it.label.replace(/（整体）$/, '')}`, value: it.expr }
      if (/\.item\}$/.test(it.expr)) items.push(o)
      else if (/^\{trigger\.(old_)?record\}$/.test(it.expr)) trig.push(o)
      else if (/\.(records|groups)\}$/.test(it.expr)) {
        // 列表整体不能当判断对象，但它的第一条可以（查询后判断第一条是常见场景）
        firsts.push({ label: `${o.label}·第一条`, value: it.expr.slice(0, -1) + '.0}' })
      } else if (/\.(record|stats|data)\}$/.test(it.expr) || /^\{nodes\.[a-zA-Z0-9_]+\}$/.test(it.expr)) rest.push(o)
    }
  }
  return [...items, ...trig, ...firsts, ...rest]
}
