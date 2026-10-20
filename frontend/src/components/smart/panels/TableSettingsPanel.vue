<template>
  <!-- 表格设置面板（参照 docs/智慧表格/表格上方按钮/表格设置.png）：
       字段行 = 56px，类型图标 + 名称 + 眼睛(显隐) + ⋯；编组为可折叠节（▾ 组名，成员带竖向层级线）。
       列顺序即表格显示顺序，整行可拖（落点指示同记事本目录：上/下沿蓝线、组头中部虚线框=移入编组）。
       长字段列表独立滚动，新增字段固定在下方；成员拖出编组范围即退出编组（父级处理）。 -->
  <el-popover :hide-after="0" trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="420" popper-class="st-tbpanel st-ts-pop">
    <template #reference><slot /></template>
    <div class="tbp-title ts-title">表格设置</div>
    <div class="settings">
      <div class="settings-list">
        <template v-for="row in flatRows" :key="row.key">
          <div v-if="row.divider" class="ts-divider" />
          <!-- 编组组头：可折叠、可整组拖动（成员作为整体移动）；拖拽落点（字段中部虚线框 = 移入该组） -->
          <div v-else-if="row.isGroup" class="group-head tree-item" :class="dndIndicator(row)"
               draggable="true" @dragstart="dndStartGroup(row.group, $event)"
               @dragover="dndOver(row, $event)" @drop="dndDrop(row, $event)" @dragend="dndEnd"
               @click="toggleGroup(row.group.id)">
            <span class="ts-drag st-icon-action"><StIcon name="drag" :size="14" /></span>
            <span class="g-caret st-icon-action"><StIcon :name="collapsed.has(row.group.id) ? 'chevron-right' : 'chevron-down'" :size="16" /></span>
            <span class="g-name">{{ row.group.name }}</span>
            <span class="f-eye st-icon-action" :data-smart-tip="groupHidden(row) ? '显示' : '隐藏'" @click.stop="toggleGroupVisible(row)">
              <StIcon :name="groupHidden(row) ? 'eye-off' : 'eye'" :size="20" :stroke-width="1.2" />
            </span>
            <span class="f-more f-more-ph" />
          </div>
          <!-- 字段行（编组成员缩进 + 竖向层级线）：整行可拖 -->
          <div v-else class="field-row tree-item" :class="[{ member: row.member, off: isHidden(row.field) }, dndIndicator(row)]"
               draggable="true" @dragstart="dndStart(row.field, $event)"
               @dragover="dndOver(row, $event)" @drop="dndDrop(row, $event)" @dragend="dndEnd">
            <span class="ts-drag st-icon-action"><StIcon name="drag" :size="14" /></span>
            <StIcon :name="fieldIconName(row.field)" :size="16" class="ts-ico" />
            <span class="f-name">{{ row.field.label }}</span>
            <span class="f-eye st-icon-action" :data-smart-tip="isHidden(row.field) ? '显示' : '隐藏'"
                  @click.stop="$emit('toggle-visible', row.field, isHidden(row.field))">
              <StIcon :name="isHidden(row.field) ? 'eye-off' : 'eye'" :size="20" :stroke-width="1.2" />
            </span>
            <el-dropdown :hide-after="0" trigger="click" @command="(cmd) => $emit('field-action', cmd, row.field)">
              <span class="f-more st-icon-action" @click.stop><StIcon name="more-h" :size="18" /></span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">修改字段</el-dropdown-item>
                  <el-dropdown-item command="duplicate">创建副本</el-dropdown-item>
                  <el-dropdown-item command="newGroup">新建编组</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </template>
      </div>
      <div class="add-field" @click="(e) => $emit('add-field', e)"><StIcon name="plus" :size="16" />新增字段</div>
    </div>
  </el-popover>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  view: { type: Object, default: () => ({ config: {} }) },
  columnGroups: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'update:visible', 'toggle-visible', 'reorder', 'field-action',
                          'add-field', 'set-field-group'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

// 字段显示顺序 = 视图 fieldOrder（与网格 visibleFields 同源）
const orderedFields = computed(() => {
  const order = props.view?.config?.fieldOrder
  const fs = [...props.fields]
  if (order?.length) {
    const idx = new Map(order.map((n, i) => [n, i]))
    fs.sort((a, b) => (idx.get(a.field_name) ?? 999) - (idx.get(b.field_name) ?? 999))
  }
  return fs
})

// 编组折叠（面板内临时状态，默认展开）
const collapsed = ref(new Set())
function toggleGroup(id) {
  const s = new Set(collapsed.value)
  s.has(id) ? s.delete(id) : s.add(id)
  collapsed.value = s
}

// 显示节点：与网格 headerTree 同构——散列字段 + 编组节（成员聚合到组下，折叠时隐藏成员）
const displayNodes = computed(() => {
  const groups = props.columnGroups.filter(g => (g.field_names || []).length)
  const emitted = new Set()
  const nodes = []
  for (const f of orderedFields.value) {
    const g = groups.find(x => x.field_names.includes(f.field_name))
    if (!g) {
      nodes.push({ key: f.field_name, isGroup: false, field: f })
    } else if (!emitted.has(g.id)) {
      emitted.add(g.id)
      nodes.push({ key: `g_${g.id}`, isGroup: true, group: g,
                   fields: orderedFields.value.filter(x => g.field_names.includes(x.field_name)) })
    }
  }
  return nodes
})

// 扁平行序列：组头行 + 成员字段行/散列字段行（折叠组不出成员行）；
// 冻结列之后插一条分隔线（参照稿：冻结区与滚动区分隔）
const flatRows = computed(() => {
  const rows = displayNodes.value.flatMap(n =>
    n.isGroup
      ? [{ key: n.key, isGroup: true, group: n.group, fields: n.fields },
         ...(collapsed.value.has(n.group.id) ? []
             : n.fields.map(f => ({ key: f.field_name, isGroup: false, field: f, member: true })))]
      : [{ key: n.field.field_name, isGroup: false, field: n.field }])
  const frozen = props.view?.config?.frozenFieldId
  if (!frozen) return rows
  let at = rows.findIndex(r => (!r.isGroup && r.field.field_name === frozen) || (r.isGroup && r.fields.some(f => f.field_name === frozen)))
  if (at < 0) return rows
  // 冻结列在编组内：分隔线放在该编组最后一个成员之后
  if (rows[at].isGroup || rows[at].member) while (rows[at + 1]?.member) at++
  if (at < rows.length - 1) rows.splice(at + 1, 0, { key: '__divider', divider: true })
  return rows
})
const groupHidden = (row) => row.fields.length > 0 && row.fields.every(isHidden)
function toggleGroupVisible(row) {
  const hidden = groupHidden(row)
  for (const f of row.fields) if (isHidden(f) === hidden) emit('toggle-visible', f, hidden)
}

const isHidden = (f) => (props.view?.config?.fieldVisibility || {})[f.field_name] === false

// ---------- 拖拽（交互约定同 useTreeDnd：上/下半区 = 前/后排序，组头中部 = 字段拖入编组） ----------
// 两种拖拽：字段（dragName）与整组（dragGroupId，成员作为整体移动）
const dragOver = ref({ key: null, zone: null, lineKey: null, lineZone: null })
let dragName = null
let dragGroupId = null

const groupOf = (fieldName) => props.columnGroups.find(g => g.field_names?.includes(fieldName)) || null
const rowInGroup = (row, gid) => row.isGroup ? row.group.id === gid : groupOf(row.field.field_name)?.id === gid

function dndStart(f, e) {
  dragName = f.field_name
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', f.field_name)   // Firefox 必须 setData 才会触发拖拽
  e.stopPropagation()
}

function dndStartGroup(g, e) {
  dragGroupId = g.id
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', `g_${g.id}`)
  e.stopPropagation()
}

function dndOver(row, e) {
  if (!dragName && !dragGroupId) return
  // 整组拖拽：落在本组的行上无意义；字段拖拽：落在自身上忽略
  if (dragGroupId && rowInGroup(row, dragGroupId)) return
  if (dragName && !row.isGroup && row.field.field_name === dragName) return
  const r = e.currentTarget.getBoundingClientRect()
  const ratio = (e.clientY - r.top) / r.height
  let zone = ratio < 0.5 ? 'before' : 'after'
  // into（移入编组）只对字段拖拽开放：编组不能嵌套
  if (!dragGroupId && row.isGroup && ratio >= 0.3 && ratio <= 0.7) zone = 'into'
  e.preventDefault()   // 不 preventDefault 浏览器不允许 drop
  e.dataTransfer.dropEffect = 'move'
  // dragover 触发极频繁：只有落点变化才写响应式状态
  if (dragOver.value.key === row.key && dragOver.value.zone === zone) return
  let lineKey = row.key
  let lineZone = zone
  if (zone === 'after') {
    const list = flatRows.value
    const i = list.findIndex(x => x.key === row.key)
    // 下一可见行（跳过被拖字段/被拖组的行）：线画在它的上沿
    const next = list.slice(i + 1).find(x => {
      if (dragGroupId) return !rowInGroup(x, dragGroupId)
      return x.isGroup || x.field.field_name !== dragName
    })
    if (next) { lineKey = next.key; lineZone = 'before' }
  }
  dragOver.value = { key: row.key, zone, lineKey, lineZone }
}

function dndDrop(row, e) {
  e.preventDefault()
  const zone = dragOver.value.key === row.key ? dragOver.value.zone : null
  const name = dragName
  const gid = dragGroupId
  dndEnd()
  if (!zone || (!name && !gid)) return

  if (gid) {
    // 整组移动：成员保持组内相对顺序，作为整体插到锚点位置
    const g = props.columnGroups.find(x => x.id === gid)
    if (!g) return
    const members = orderedFields.value.filter(f => g.field_names.includes(f.field_name)).map(f => f.field_name)
    const order = orderedFields.value.map(f => f.field_name).filter(n => !members.includes(n))
    const anchor = row.isGroup
      ? (zone === 'before' ? row.fields[0] : row.fields[row.fields.length - 1])?.field_name
      : row.field.field_name
    let idx = anchor ? order.indexOf(anchor) : -1
    if (idx < 0) idx = order.length
    else if (zone === 'after') idx += 1
    order.splice(idx, 0, ...members)
    emit('reorder', order)
    return
  }

  // 编组成员归属：落点是组头(中部) → 移入该组；落点是某组成员行 → 加入该组；
  // 否则移出所在组（"拖出去就没编组"；最后成员拖出后父级解散空组）
  if (zone === 'into') {
    if (!row.group.field_names?.includes(name)) emit('set-field-group', name, row.group)
    return
  }
  const dragGroup = groupOf(name)
  const targetGroup = row.isGroup ? null : groupOf(row.field.field_name)
  if ((targetGroup?.id ?? null) !== (dragGroup?.id ?? null)) emit('set-field-group', name, targetGroup)
  // 排序：组头行 before = 首成员之前，after = 末成员之后
  const order = orderedFields.value.map(f => f.field_name).filter(n => n !== name)
  const anchor = row.isGroup
    ? (zone === 'before' ? row.fields[0] : row.fields[row.fields.length - 1])?.field_name
    : row.field.field_name
  let idx = anchor ? order.indexOf(anchor) : -1
  if (idx < 0) idx = order.length
  else if (zone === 'after') idx += 1
  order.splice(idx, 0, name)
  emit('reorder', order)
}

function dndEnd() {
  dragName = null
  dragGroupId = null
  dragOver.value = { key: null, zone: null, lineKey: null, lineZone: null }
}

function dndIndicator(row) {
  const d = dragOver.value
  if (d.key === row.key && d.zone === 'into') return 'dnd-into'
  if (d.zone && d.zone !== 'into' && d.lineKey === row.key) return d.lineZone === 'before' ? 'dnd-before' : 'dnd-after'
  return ''
}
</script>

<style scoped>
.ts-title { margin-bottom: 12px; }
.settings { display: flex; flex-direction: column; margin: 0 -10px; padding: 0 10px; }
/* 列表左移 16px，行内留 18px 左内边距放拖动手柄（参照稿：悬停行左侧 ⋮⋮），图标仍与标题/新增字段对齐；
   手柄须在行内——放在行外会被列表 overflow 裁掉 */
.settings-list { display: flex; flex-direction: column; min-height: 0; max-height: calc(100vh - 220px); overflow: auto; margin-left: -16px; }
.field-row { position: relative; display: flex; align-items: center; flex: none; gap: 8px; height: 42px; padding: 0 4px 0 18px; border-radius: 6px; cursor: grab; }
.field-row:hover, .group-head:hover { background: var(--st-bg-hover); }
.field-row.member { margin-left: 26px; padding-left: 22px; border-radius: 0 6px 6px 0; }
.field-row.member::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; border-left: 1px solid #DCDEE0; }
.ts-drag { position: absolute; left: 2px; top: 50%; transform: translateY(-50%); color: var(--st-text-3); display: none; pointer-events: none; }
.field-row:hover .ts-drag, .group-head:hover .ts-drag { display: inline-flex; }
.field-row.member .ts-drag { left: 5px; }
/* 字段图标/名称与右侧详情面板同一套：图标 16px 灰（--st-text-2）、名称 15px 深色、间距 8px */
.ts-ico { color: var(--st-text-2); flex: none; }
.field-row.off .f-name, .field-row.off .ts-ico { opacity: .4; }
.f-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; color: var(--st-text-1); }
/* 显隐眼睛：与字段类型图标同色（--st-text-2）；20px 配 1.2 描边，实际线宽 1.5px 与 16px 字段图标一致 */
.f-eye { cursor: pointer; color: var(--st-text-2); display: inline-flex; align-items: center; justify-content: center;
         flex: none; width: 32px; height: 32px; border-radius: 6px; }
.f-eye:hover { color: var(--st-primary); background: var(--st-bg-active); }
.f-more { cursor: pointer; color: var(--st-text-1); display: inline-flex; align-items: center; justify-content: center;
          flex: none; width: 32px; height: 32px; border-radius: 6px; }
.f-more:hover { color: var(--st-primary); background: var(--st-bg-active); }
.f-more-ph { cursor: default; }
.f-more-ph:hover { background: transparent; }
/* 编组组头：可折叠节标题（∨ 组名），与字段行同为 56px */
.group-head { position: relative; display: flex; align-items: center; flex: none; gap: 8px; height: 42px; padding: 0 4px 0 18px; border-radius: 6px; cursor: pointer; user-select: none; }
.g-caret { display: inline-flex; color: var(--st-text-1); }
.g-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; color: var(--st-text-1); }
.ts-divider { height: 1px; background: var(--st-border); margin: 8px 0; flex: none; }
/* 底部新增字段：不随长字段列表滚动 */
.add-field { display: flex; align-items: center; flex: none; gap: 8px; height: 42px; margin-top: 4px; padding: 0 2px;
             cursor: pointer; color: var(--st-text-1); font-size: 15px; border-radius: 6px; }
.add-field:hover { background: var(--st-bg-hover); }
</style>

<style>
.st-ts-pop.el-popover.el-popper { padding: 22px 20px 12px; }
</style>
