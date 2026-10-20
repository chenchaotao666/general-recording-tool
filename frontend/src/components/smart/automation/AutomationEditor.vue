<template>
  <!-- 自动化完整版编辑器（§11.3）：「当满足以下条件」第 1 步触发器 →「就执行以下操作」第 2..N 步动作链。
       对齐参照 右上角工具栏-新建自动化提醒(2).png / 表头-记录变更提醒-详细配置(2).png -->
  <div class="ae">
    <div class="ae-sec-title">当满足以下条件</div>
    <div class="ae-step-label"><span class="ae-dot" />第1步</div>
    <div class="ae-card">
      <el-dropdown trigger="click" @command="setTriggerType">
        <span class="ae-type"><span class="ae-type-ico" :style="{ background: trigMeta.color }"><StIcon :name="trigMeta.icon" :size="13" /></span>
          {{ trigMeta.label }}<StIcon name="chevron-down" :size="14" class="ae-caret" /></span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="t in TRIGGERS" :key="t.type" :command="t.type">
              <span class="ae-dd"><span class="ae-type-ico" :style="{ background: t.color }"><StIcon :name="t.icon" :size="12" /></span>{{ t.label }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 定时重复 -->
      <div v-if="trig.type === 'schedule'" class="ae-line">
        <el-select :model-value="trig.schedule.freq" class="ae-sel-s" :teleported="false"
                   @update:model-value="(v) => patchSchedule({ freq: v })">
          <el-option value="daily" label="每天" /><el-option value="weekly" label="每周" /><el-option value="monthly" label="每月" />
        </el-select>
        <el-select v-if="trig.schedule.freq === 'weekly'" :model-value="trig.schedule.weekdays" multiple collapse-tags
                   class="ae-sel-m" :teleported="false" @update:model-value="(v) => patchSchedule({ weekdays: v })">
          <el-option v-for="(w, i) in WEEKDAYS" :key="i" :value="i + 1" :label="w" />
        </el-select>
        <el-select v-if="trig.schedule.freq === 'monthly'" :model-value="trig.schedule.monthDays" multiple collapse-tags
                   class="ae-sel-m" :teleported="false" @update:model-value="(v) => patchSchedule({ monthDays: v })">
          <el-option v-for="d in 31" :key="d" :value="d" :label="`${d} 日`" />
        </el-select>
        <span>的</span>
        <el-time-select :model-value="trig.schedule.time" start="00:00" step="00:30" end="23:30" class="ae-time"
                        :teleported="false" @update:model-value="(v) => patchSchedule({ time: v })" />
        <span>定时触发</span>
      </div>

      <!-- 添加新记录时 -->
      <template v-else-if="trig.type === 'recordCreated'">
        <div class="ae-line"><span>在</span><TableChip :name="tableName" /><span>里添加新记录时，</span></div>
        <div class="ae-line">
          <span>且同时满足</span>
          <TbFieldSelect :model-value="trig.rowConditions?.[0]?.fieldId" :fields="fields" class="ae-sel-f" clearable
                         @update:model-value="setRowCond" />
          <span>不为空</span>
        </div>
        <div class="ae-info"><StIcon name="info" :size="15" />条件未满足时，任何编辑均不会触发后续操作</div>
      </template>

      <!-- 记录内容变更时 -->
      <div v-else class="ae-line">
        <span>在</span><TableChip :name="tableName" /><span>里，当记录的</span>
        <el-select :model-value="trig.watchFields || []" multiple collapse-tags placeholder="任意列" class="ae-sel-m"
                   :teleported="false" @update:model-value="(v) => patchTrig({ watchFields: v })">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <span>有变更时</span>
      </div>
    </div>

    <!-- 过滤器（事件型） -->
    <div v-if="trig.type !== 'schedule'" class="ae-card ae-filter">
      <div class="ae-line ae-filter-head">
        <span class="ae-type-ico ae-gray"><StIcon name="filter" :size="12" /></span>
        <span>{{ trig.type === 'recordCreated' ? '且被添加的记录满足' : '且被修改的记录满足以下' }}</span>
        <el-select v-if="(trig.filter?.conditions || []).length > 1 || trig.type === 'recordUpdated'"
                   :model-value="trig.filter?.match || 'all'" class="ae-sel-xs" :teleported="false"
                   @update:model-value="(v) => patchTrig({ filter: { ...trig.filter, match: v } })">
          <el-option value="all" label="所有" /><el-option value="any" label="任一" />
        </el-select>
        <span>条件</span>
      </div>
      <PermCondRow v-for="(c, i) in trig.filter?.conditions || []" :key="i" :cond="c" :fields="fields"
                   @update="(nc) => setFilterCond(i, nc)" @remove="removeFilterCond(i)" />
      <a class="ae-add-cond" @click="addFilterCond"><StIcon name="plus" :size="13" />添加条件</a>
    </div>
    <div v-if="trig.type === 'recordCreated'" class="ae-note">如需在添加空白行后再修改时触发，可设置“记录内容变更”触发条件。</div>

    <div class="ae-divider"><StIcon name="chevrons-down" :size="14" /></div>
    <div class="ae-sec-title">就执行以下操作</div>

    <template v-for="(a, i) in modelValue.actions" :key="a.id">
      <div class="ae-step-label"><span class="ae-dot" />第{{ i + 2 }}步</div>
      <div class="ae-card ae-action">
        <div class="ae-action-head">
          <el-dropdown trigger="click" @command="(t) => changeActionType(i, t)">
            <span class="ae-type"><span class="ae-type-ico" :style="{ background: actMeta(a.type).color }"><StIcon :name="actMeta(a.type).icon" :size="13" /></span>
              {{ actMeta(a.type).label }}<StIcon name="chevron-down" :size="14" class="ae-caret" /></span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="t in ACTIONS" :key="t.type" :command="t.type">
                  <span class="ae-dd"><span class="ae-type-ico" :style="{ background: t.color }"><StIcon :name="t.icon" :size="12" /></span>{{ t.label }}</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <span v-if="modelValue.actions.length > 1" class="ae-del st-icon-action" data-smart-tip="删除此操作" @click="removeAction(i)"><StIcon name="trash" :size="16" /></span>
        </div>

        <!-- 发送消息 -->
        <template v-if="a.type === 'sendMessage'">
          <div class="ae-label">发送方式</div>
          <div class="ae-channels">
            <div class="ae-channel" :class="{ on: a.channel !== 'groupMessage' }" @click="patchAction(i, { channel: 'docMessage' })">
              <span class="ae-radio" /><div><div class="ae-ch-t">文档消息</div><div class="ae-ch-s">通过文档动态发送</div></div>
            </div>
            <div class="ae-channel" :class="{ on: a.channel === 'groupMessage' }" @click="patchAction(i, { channel: 'groupMessage' })">
              <span class="ae-radio" /><div><div class="ae-ch-t">群消息</div><div class="ae-ch-s">通过应用发送到群</div></div>
            </div>
          </div>
          <template v-if="a.channel === 'groupMessage'">
            <div class="ae-label">群机器人 Webhook</div>
            <el-input :model-value="a.webhookUrl" placeholder="企业微信 / 钉钉 / 飞书群机器人地址 https://…"
                      @update:model-value="(v) => patchAction(i, { webhookUrl: v })" />
          </template>
          <template v-else>
            <div class="ae-label">发送给</div>
            <el-select :model-value="recipientsOf(a)" multiple filterable class="ae-full" placeholder="选择成员，或记录中的人员字段"
                       :teleported="false" @update:model-value="(v) => setRecipients(i, v)">
              <el-option-group label="成员">
                <el-option v-for="m in members" :key="m.id" :value="m.id" :label="m.name" />
              </el-option-group>
              <el-option-group v-if="trig.type !== 'schedule' && memberFields.length" label="记录中的人员字段">
                <el-option v-for="f in memberFields" :key="f.field_name" :value="`field:${f.field_name}`" :label="`字段：${f.label}`" />
              </el-option-group>
            </el-select>
          </template>
          <div class="ae-label">消息内容</div>
          <MessageEditor :title-value="a.title" :content="a.content" :buttons-value="a.buttons" :steps="stepsBefore(i + 2)"
                         :dashboards="dashboards"
                         @change="(m) => patchAction(i, { title: m.title, content: m.content, buttons: m.buttons })" />
        </template>

        <!-- 查找记录 -->
        <template v-else-if="a.type === 'findRecords'">
          <div class="ae-line">
            <span>在</span><TableSelect :model-value="a.tableId" :tables="tables" @update:model-value="(v) => setActionTable(i, v)" />
            <span>里，查找</span><span class="ae-pill">满足条件的记录</span>
          </div>
          <div class="ae-cond-box">
            <PermCondRow v-for="(c, ci) in a.conditions" :key="ci" :cond="c" :fields="fieldsOf(a.tableId)" :column-groups="groupsOf(a.tableId)"
                         @update="(nc) => setActCond(i, ci, nc)" @remove="removeActCond(i, ci)" />
            <a class="ae-add-cond" @click="addActCond(i)"><StIcon name="plus" :size="13" />添加条件</a>
          </div>
          <div class="ae-label">未查找到记录时</div>
          <el-radio-group :model-value="a.onNotFound" @update:model-value="(v) => patchAction(i, { onNotFound: v })">
            <el-radio value="continue">继续执行</el-radio><el-radio value="abort">终止</el-radio>
          </el-radio-group>
        </template>

        <!-- 新增 / 修改记录 -->
        <template v-else>
          <div class="ae-line">
            <span>在</span><TableSelect :model-value="a.tableId" :tables="tables" @update:model-value="(v) => setActionTable(i, v)" />
            <template v-if="a.type === 'createRecord'"><span>里，添加</span><span class="ae-pill">指定内容的记录</span></template>
            <template v-else>
              <span>里，对</span>
              <el-select :model-value="targetValue(a)" class="ae-sel-t" :teleported="false" @update:model-value="(v) => setTarget(i, v)">
                <el-option value="all" label="所有记录" />
                <el-option v-if="trig.type !== 'schedule'" value="triggered" label="触发的记录" />
                <el-option v-for="s in findStepsBefore(i + 2)" :key="s" :value="`found:${s}`" :label="`第${s}步找到的记录`" />
                <el-option value="matching" label="满足条件的记录" />
              </el-select>
              <span>修改</span>
            </template>
          </div>
          <div v-if="a.type === 'updateRecords' && a.target === 'matching'" class="ae-cond-box">
            <PermCondRow v-for="(c, ci) in a.conditions" :key="ci" :cond="c" :fields="fieldsOf(a.tableId)" :column-groups="groupsOf(a.tableId)"
                         @update="(nc) => setActCond(i, ci, nc)" @remove="removeActCond(i, ci)" />
            <a class="ae-add-cond" @click="addActCond(i)"><StIcon name="plus" :size="13" />添加条件</a>
          </div>
          <div class="ae-values">
            <div v-if="a.type === 'updateRecords'" class="ae-pill ae-pill-block">指定内容</div>
            <div v-for="(v, vi) in a.values" :key="vi" class="ae-value-row">
              <el-select :model-value="v.fieldId" class="ae-sel-f" placeholder="字段" :teleported="false"
                         @update:model-value="(fn) => setValue(i, vi, { fieldId: fn, value: undefined })">
                <el-option v-for="f in writableFields(a.tableId)" :key="f.field_name" :value="f.field_name" :label="f.label" />
              </el-select>
              <span class="ae-eq">=</span>
              <ValueInput :model-value="v.value" :field="fieldsOf(a.tableId).find(f => f.field_name === v.fieldId)"
                          :steps="stepsBefore(i + 2)" @update:model-value="(nv) => setValue(i, vi, { ...v, value: nv })" />
              <span class="ae-rm st-icon-action" @click="removeValue(i, vi)"><StIcon name="minus-circle" :size="16" /></span>
            </div>
            <a class="ae-add-cond" @click="addValue(i)"><StIcon name="plus" :size="13" />添加要{{ a.type === 'createRecord' ? '填写' : '修改' }}的字段</a>
          </div>
        </template>
      </div>
    </template>

    <el-dropdown trigger="click" @command="addAction">
      <a class="ae-add-action"><StIcon name="plus" :size="16" />添加操作</a>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item v-for="t in ACTIONS" :key="t.type" :command="t.type">
            <span class="ae-dd"><span class="ae-type-ico" :style="{ background: t.color }"><StIcon :name="t.icon" :size="12" /></span>{{ t.label }}</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, defineComponent, h, reactive, watch } from 'vue'
import { ElOption, ElSelect } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import TbFieldSelect from '../panels/TbFieldSelect.vue'
import PermCondRow from '../perms/PermCondRow.vue'
import MessageEditor from './MessageEditor.vue'
import ValueInput from './ValueInput.vue'

const props = defineProps({
  modelValue: { type: Object, required: true },   // {name, enabled, trigger, actions}
  tableId: Number,
  tableName: { type: String, default: '' },
  fields: { type: Array, default: () => [] },
  tables: { type: Array, default: () => [] },     // [{id, label}]
  members: { type: Array, default: () => [] },
  dashboards: { type: Array, default: () => [] },
  loadFields: { type: Function, required: true }, // tid → Promise<fields>
})
const emit = defineEmits(['update:modelValue'])

const TRIGGERS = [
  { type: 'schedule', label: '定时重复', color: '#22B35E', icon: 'automation' },
  { type: 'recordCreated', label: '添加新记录时', color: '#14B8A6', icon: 'plus' },
  { type: 'recordUpdated', label: '记录内容变更时', color: '#F77B2D', icon: 'pencil' },
]
const ACTIONS = [
  { type: 'sendMessage', label: '发送消息', color: '#F5B400', icon: 'comment' },
  { type: 'findRecords', label: '查找记录', color: '#9B6BF2', icon: 'search' },
  { type: 'createRecord', label: '新增记录', color: '#14B8A6', icon: 'plus' },
  { type: 'updateRecords', label: '修改记录', color: '#F77B2D', icon: 'pencil' },
]
const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const READONLY = ['formula', 'lookup', 'autoNumber', 'ai', 'createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime']
const MEMBER_TYPES = ['member', 'createdBy', 'lastModifiedBy']

const trig = computed(() => props.modelValue.trigger)
const trigMeta = computed(() => TRIGGERS.find(t => t.type === trig.value.type) || TRIGGERS[0])
const actMeta = (t) => ACTIONS.find(x => x.type === t) || ACTIONS[0]
// 其他表的字段不套用本表编组（字段名 f_N 跨表重名）
const groupsOf = (tid) => (!tid || tid === props.tableId ? null : [])
const rowCondField = computed(() => props.fields.find(f => f.field_name === trig.value.rowConditions?.[0]?.fieldId))
const memberFields = computed(() => props.fields.filter(f => MEMBER_TYPES.includes(f.field_type)))

// ---------- 他表字段缓存 ----------
const fieldsCache = reactive({})
function fieldsOf(tid) {
  if (!tid || tid === props.tableId) return props.fields
  if (!fieldsCache[tid]) {
    fieldsCache[tid] = []
    props.loadFields(tid).then(fs => { fieldsCache[tid] = fs || [] }).catch(() => {})
  }
  return fieldsCache[tid]
}
function writableFields(tid) { return fieldsOf(tid).filter(f => !READONLY.includes(f.field_type)) }
watch(() => props.modelValue.actions, (acts) => { for (const a of acts || []) if (a.tableId) fieldsOf(a.tableId) }, { immediate: true })

// ---------- 修改工具 ----------
const uid = () => `a${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
function emitV(next) { emit('update:modelValue', next) }
function patchTrig(obj) { emitV({ ...props.modelValue, trigger: { ...trig.value, ...obj } }) }
function patchSchedule(obj) { patchTrig({ schedule: { ...trig.value.schedule, ...obj } }) }
function setTriggerType(type) {
  const base = { type, filter: { match: 'all', conditions: [] } }
  if (type === 'schedule') base.schedule = { freq: 'daily', time: '09:00', weekdays: [1], monthDays: [1] }
  if (type === 'recordCreated') base.rowConditions = []
  if (type === 'recordUpdated') base.watchFields = []
  const actions = props.modelValue.actions.map(a => (type === 'schedule' && a.type === 'updateRecords' && a.target === 'triggered'
    ? { ...a, target: 'all' } : a))
  emitV({ ...props.modelValue, trigger: base, actions })
}
function setRowCond(fn) { patchTrig({ rowConditions: fn ? [{ fieldId: fn, operator: 'isNotEmpty' }] : [] }) }
function addFilterCond() {
  patchTrig({ filter: { ...trig.value.filter, conditions: [...(trig.value.filter?.conditions || []), { fieldId: null, operator: 'eq' }] } })
}
function setFilterCond(i, c) {
  const list = [...(trig.value.filter?.conditions || [])]; list[i] = c
  patchTrig({ filter: { ...trig.value.filter, conditions: list } })
}
function removeFilterCond(i) {
  patchTrig({ filter: { ...trig.value.filter, conditions: trig.value.filter.conditions.filter((_, j) => j !== i) } })
}

function newAction(type) {
  if (type === 'sendMessage') return { id: uid(), type, channel: 'docMessage', to: [], toFields: [], webhookUrl: '', title: props.modelValue.name || '', content: [], buttons: [] }
  if (type === 'findRecords') return { id: uid(), type, tableId: props.tableId, match: 'all', conditions: [], onNotFound: 'continue' }
  if (type === 'createRecord') return { id: uid(), type, tableId: props.tableId, values: [] }
  return { id: uid(), type, tableId: props.tableId, target: trig.value.type === 'schedule' ? 'all' : 'triggered', foundStep: null, match: 'all', conditions: [], values: [] }
}
function setActions(list) { emitV({ ...props.modelValue, actions: list }) }
function addAction(type) { setActions([...props.modelValue.actions, newAction(type)]) }
function removeAction(i) { setActions(props.modelValue.actions.filter((_, j) => j !== i)) }
function changeActionType(i, type) {
  if (props.modelValue.actions[i].type === type) return
  const list = [...props.modelValue.actions]; list[i] = { ...newAction(type), id: list[i].id }
  setActions(list)
}
function patchAction(i, obj) {
  const list = [...props.modelValue.actions]; list[i] = { ...list[i], ...obj }
  setActions(list)
}
function setActionTable(i, tid) { patchAction(i, { tableId: tid, conditions: [], values: [] }); fieldsOf(tid) }
function addActCond(i) { patchAction(i, { conditions: [...(props.modelValue.actions[i].conditions || []), { fieldId: null, operator: 'eq' }] }) }
function setActCond(i, ci, c) { const l = [...props.modelValue.actions[i].conditions]; l[ci] = c; patchAction(i, { conditions: l }) }
function removeActCond(i, ci) { patchAction(i, { conditions: props.modelValue.actions[i].conditions.filter((_, j) => j !== ci) }) }
function addValue(i) { patchAction(i, { values: [...(props.modelValue.actions[i].values || []), { fieldId: null, value: undefined }] }) }
function setValue(i, vi, v) { const l = [...props.modelValue.actions[i].values]; l[vi] = v; patchAction(i, { values: l }) }
function removeValue(i, vi) { patchAction(i, { values: props.modelValue.actions[i].values.filter((_, j) => j !== vi) }) }
function targetValue(a) { return a.target === 'found' ? `found:${a.foundStep}` : a.target }
function setTarget(i, v) {
  if (String(v).startsWith('found:')) patchAction(i, { target: 'found', foundStep: Number(v.slice(6)) })
  else patchAction(i, { target: v, foundStep: null })
}
function recipientsOf(a) { return [...(a.to || []), ...(a.toFields || []).map(fn => `field:${fn}`)] }
function setRecipients(i, vals) {
  patchAction(i, { to: vals.filter(v => typeof v === 'number'), toFields: vals.filter(v => typeof v === 'string' && v.startsWith('field:')).map(v => v.slice(6)) })
}

// ---------- 变量描述（第 N 步的…） ----------
function fieldVars(step, tid) {
  return fieldsOf(tid).map(f => ({ key: f.field_name, label: f.label, icon: fieldIconName(f),
                                   var: { kind: 'step', step, key: 'field', field: f.field_name } }))
}
function stepsBefore(stepNo) {
  const out = []
  const t = trig.value.type
  out.push({
    step: 1, name: { schedule: '定时触发', recordCreated: '添加新记录', recordUpdated: '修改记录' }[t],
    vars: t === 'schedule'
      ? [{ key: 'time', label: '触发时间', icon: 'createdTime', var: { kind: 'step', step: 1, key: 'time' } }]
      : [...fieldVars(1, props.tableId),
         { key: 'operator', label: '操作人', icon: 'member', var: { kind: 'step', step: 1, key: 'operator' } },
         { key: 'time', label: '操作时间', icon: 'createdTime', var: { kind: 'step', step: 1, key: 'time' } }],
  })
  props.modelValue.actions.forEach((a, idx) => {
    const step = idx + 2
    if (step >= stepNo) return
    if (a.type === 'findRecords') {
      out.push({ step, name: '查找记录', vars: [{ key: 'count', label: '记录数', icon: 'number', var: { kind: 'step', step, key: 'count' } },
                                                 ...fieldVars(step, a.tableId)] })
    } else if (a.type === 'createRecord') {
      out.push({ step, name: '新增记录', vars: [...fieldVars(step, a.tableId),
                                                 { key: 'time', label: '操作时间', icon: 'createdTime', var: { kind: 'step', step, key: 'time' } }] })
    } else if (a.type === 'updateRecords') {
      out.push({ step, name: '修改记录', vars: [
        { key: 'count', label: '修改记录数', icon: 'number', var: { kind: 'step', step, key: 'count' } },
        { key: 'operator', label: '操作人', icon: 'member', var: { kind: 'step', step, key: 'operator' } },
        { key: 'time', label: '操作时间', icon: 'createdTime', var: { kind: 'step', step, key: 'time' } }] })
    }
  })
  return out
}
function findStepsBefore(stepNo) {
  return props.modelValue.actions.map((a, idx) => (a.type === 'findRecords' && idx + 2 < stepNo ? idx + 2 : null)).filter(Boolean)
}

// ---------- 小组件：表名胶囊 / 表选择 ----------
const TableChip = defineComponent({
  props: { name: String },
  setup(p) { return () => h('span', { class: 'ae-table-chip' }, [h(StIcon, { name: 'view-grid', size: 14 }), p.name]) },
})
const TableSelect = defineComponent({
  props: { modelValue: Number, tables: Array },
  emits: ['update:modelValue'],
  setup(p, { emit: em }) {
    return () => h(ElSelect, {
      modelValue: p.modelValue, filterable: true, teleported: false, class: 'ae-sel-table',
      'onUpdate:modelValue': (v) => em('update:modelValue', v),
    }, {
      prefix: () => h(StIcon, { name: 'view-grid', size: 14 }),
      default: () => (p.tables || []).map(t => h(ElOption, { key: t.id, value: t.id, label: t.label })),
    })
  },
})
</script>

<style scoped>
.ae { padding: 6px 0 20px; }
.ae-sec-title { font-size: 16px; font-weight: 700; color: var(--st-text-1); margin: 14px 0 10px; }
.ae-step-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--st-text-2); margin: 8px 0 8px 2px; }
.ae-dot { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--st-text-4); }
.ae-card { background: #fff; border: 1px solid var(--st-border); border-radius: 8px; padding: 18px 22px; margin-bottom: 10px; display: flex; flex-direction: column; gap: 14px; }
.ae-type { display: inline-flex; align-items: center; gap: 10px; font-size: 16px; color: var(--st-text-1); cursor: pointer; }
.ae-type-ico { width: 20px; height: 20px; border-radius: 4px; display: inline-flex; align-items: center; justify-content: center; color: #fff; flex: none; }
.ae-gray { background: #7A7F87; }
.ae-caret { color: var(--st-text-2); }
.ae-dd { display: inline-flex; align-items: center; gap: 8px; }
.ae-dd .ae-type-ico { width: 18px; height: 18px; }
.ae-line { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 15px; color: var(--st-text-1); }
.ae-sel-s { width: 96px; }
.ae-sel-xs { width: 84px; }
.ae-sel-m { width: 200px; }
.ae-sel-f { width: 190px; }
.ae-sel-t { width: 170px; }
.ae-time { width: 120px; }
:deep(.ae-sel-table) { width: 220px; }
.ae-full { width: 100%; }
:deep(.ae-table-chip) { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--st-border); border-radius: 6px; padding: 5px 12px; font-size: 14px; background: #fff; }
.ae-info { display: flex; align-items: center; gap: 8px; background: #F2F3F5; border-radius: 6px; padding: 9px 14px; font-size: 14px; color: var(--st-text-1); }
.ae-info .st-icon { color: var(--st-primary); }
.ae-filter-head { gap: 10px; }
.ae-add-cond { display: inline-flex; align-items: center; gap: 6px; color: var(--st-text-2); cursor: pointer; font-size: 14px; align-self: flex-start; }
.ae-add-cond:hover { color: var(--st-primary); }
.ae-note { font-size: 13px; color: var(--st-text-2); margin: -2px 0 6px; }
.ae-divider { border-top: 1px solid var(--st-border); margin: 18px -24px 0; position: relative; display: flex; justify-content: flex-start; padding-left: 4px; color: var(--st-text-4); }
.ae-divider .st-icon { margin-top: 4px; }
.ae-action-head { display: flex; justify-content: space-between; align-items: center; }
.ae-del { color: var(--st-text-3); cursor: pointer; display: inline-flex; visibility: hidden; }
.ae-action:hover .ae-del { visibility: visible; }
.ae-del:hover { color: var(--el-color-danger); }
.ae-label { font-size: 14px; color: var(--st-text-2); margin-bottom: -6px; }
.ae-channels { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.ae-channel { display: flex; align-items: center; gap: 12px; border: 1px solid var(--st-border); border-radius: 8px; padding: 12px 16px; cursor: pointer; }
.ae-channel.on { border-color: var(--st-primary); }
.ae-radio { width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid var(--st-text-4); flex: none; box-sizing: border-box; }
.ae-channel.on .ae-radio { border: 5px solid var(--st-primary); }
.ae-ch-t { font-size: 16px; color: var(--st-text-1); }
.ae-ch-s { font-size: 13px; color: var(--st-text-2); }
.ae-pill { display: inline-flex; align-items: center; border: 1px solid var(--st-border); border-radius: 6px; padding: 5px 12px; font-size: 14px; color: var(--st-text-1); background: #fff; }
.ae-pill::after { content: ''; border: 4px solid transparent; border-top-color: var(--st-text-4); margin: 4px 0 0 8px; }
.ae-pill-block { align-self: flex-start; }
.ae-cond-box { display: flex; flex-direction: column; gap: 10px; }
.ae-values { display: flex; flex-direction: column; gap: 10px; }
.ae-value-row { display: flex; align-items: center; gap: 8px; }
.ae-eq { color: var(--st-text-3); }
.ae-rm { color: var(--st-text-4); cursor: pointer; display: inline-flex; }
.ae-rm:hover { color: var(--el-color-danger); }
.ae-add-action { display: inline-flex; align-items: center; gap: 8px; font-size: 16px; color: var(--st-text-2); cursor: pointer; margin: 10px 0 0 6px; }
.ae-add-action:hover { color: var(--st-primary); }
</style>
