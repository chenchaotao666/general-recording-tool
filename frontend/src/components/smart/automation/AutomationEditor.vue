<template>
  <!-- 自动化完整版编辑器（§11.3）：「当满足以下条件」第 1 步触发器 →「就执行以下操作」第 2..N 步动作链。
       对齐参照 右上角工具栏-新建自动化提醒(2).png / 表头-记录变更提醒-详细配置(2).png -->
  <div class="ae">
    <div class="ae-sec-title">当满足以下条件</div>
    <div class="ae-step-label"><span class="ae-dot" />第1步</div>
    <div v-if="!trig.type" class="ae-card">
      <div class="ae-choice-label">请选择触发条件：</div>
      <div class="ae-choice-options"><button v-for="t in TRIGGERS" :key="t.type" class="ae-choice" @click="setTriggerType(t.type)"><span class="ae-type-ico" :style="{ background: t.color }"><StIcon :name="t.icon" :size="13" /></span>{{ t.label }}</button></div>
    </div>
    <div v-else class="ae-card">
      <el-dropdown :hide-after="0" trigger="click" @command="setTriggerType">
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
          <el-option value="daily" label="每天" /><el-option value="weekly" label="每周" /><el-option value="monthly" label="每月" /><el-option value="weekdays" label="每工作日" />
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
        <ScheduleTimePicker :model-value="trig.schedule.time" @update:model-value="v => patchSchedule({ time: v })" />
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
        <el-popover trigger="click" placement="bottom-start" :width="480" popper-class="ae-watch-popover" :show-arrow="false" :hide-after="0"
                    :popper-style="{ maxWidth: 'calc(100vw - 24px)' }">
          <template #reference>
            <button type="button" class="ae-pill ae-watch-trigger">{{ watchMode === 'specified' ? '指定列' : '任意列' }}</button>
          </template>
          <div class="ae-watch-panel">
            <el-radio-group :model-value="watchMode" class="ae-watch-modes" @update:model-value="setWatchMode">
              <el-radio value="any">任意列</el-radio>
              <el-radio value="specified">指定列</el-radio>
            </el-radio-group>
            <div v-if="watchMode === 'specified'" class="ae-watch-conditions">
              <div>满足以下任意条件</div>
              <PermCondRow v-for="(c, i) in watchConditions" :key="i" :cond="c" :fields="fields" allow-changed compact
                           @update="c => setWatchCond(i, c)" @remove="removeWatchCond(i)" />
              <button type="button" class="ae-find-add" @click="addWatchCond"><StIcon name="plus" :size="13" />添加条件</button>
            </div>
          </div>
        </el-popover>
        <span>有变更时</span>
      </div>
    </div>

    <!-- 过滤器（事件型） -->
    <div v-if="trig.type && trig.type !== 'schedule'" class="ae-card ae-filter">
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

    <template v-if="!modelValue.actions.length">
      <div class="ae-step-label"><span class="ae-dot" />第2步</div>
      <div class="ae-card"><div class="ae-choice-label">请选择执行操作：</div><div class="ae-choice-options"><button v-for="t in ACTIONS" :key="t.type" :disabled="!trig.type" class="ae-choice" @click="addAction(t.type)"><span class="ae-type-ico" :style="{ background: t.color }"><StIcon :name="t.icon" :size="13" /></span>{{ t.label }}</button></div></div>
    </template>
    <template v-for="(a, i) in modelValue.actions" :key="a.id">
      <div class="ae-step-label"><span class="ae-dot" />第{{ i + 2 }}步</div>
      <div class="ae-card ae-action">
        <div class="ae-action-head">
          <el-dropdown :hide-after="0" trigger="click" @command="(t) => changeActionType(i, t)">
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
            <div class="ae-channel on">
              <span class="ae-radio" /><div><div class="ae-ch-t">通知消息</div><div class="ae-ch-s">发送到接收人的通知列表</div></div>
            </div>
          </div>
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
          <div class="ae-label">消息内容</div>
          <MessageEditor :title-value="a.title" :content="a.content" :buttons-value="a.buttons" :steps="stepsBefore(i + 2)"
                         :dashboards="dashboards"
                         @change="(m) => patchAction(i, { title: m.title, content: m.content, buttons: m.buttons })" />
        </template>

        <!-- 查找记录 -->
        <template v-else-if="a.type === 'findRecords'">
          <div class="ae-line">
            <span>在</span><TableSelect :model-value="a.tableId" :tables="tables" @update:model-value="(v) => setActionTable(i, v)" />
            <span>里，查找</span>
            <el-popover trigger="click" placement="bottom-start" :width="540" :hide-after="0" :show-arrow="false"
                        popper-class="ae-find-pop" :popper-style="{ maxWidth: 'calc(100vw - 24px)' }">
              <template #reference>
                <button type="button" class="ae-pill ae-find-trigger">满足条件的记录<span class="ae-config-count">{{ a.conditions?.length || 0 }}</span></button>
              </template>
              <div class="ae-find-conditions">
                <div class="ae-line">
                  <span>满足以下</span>
                  <el-select :model-value="a.match || 'all'" class="ae-sel-xs" :teleported="false"
                             @update:model-value="v => patchAction(i, { match: v })">
                    <el-option value="all" label="所有" /><el-option value="any" label="任一" />
                  </el-select>
                  <span>条件</span>
                </div>
                <PermCondRow v-for="(c, ci) in a.conditions" :key="ci" :cond="c" :fields="fieldsOf(a.tableId)" :column-groups="groupsOf(a.tableId)"
                             @update="nc => setActCond(i, ci, nc)" @remove="removeActCond(i, ci)" />
                <button type="button" class="ae-add-cond ae-find-add" @click="addActCond(i)"><StIcon name="plus" :size="16" />添加条件</button>
              </div>
            </el-popover>
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
            <template v-if="a.type === 'createRecord'">
              <span>里，添加</span>
              <el-popover trigger="click" placement="bottom-start" :width="560" :hide-after="0" :show-arrow="false"
                          :popper-style="{ maxWidth: 'calc(100vw - 24px)' }">
                <template #reference><button type="button" class="ae-pill ae-create-trigger">{{ createMode(a) === 'blank' ? '空白记录' : '指定内容的记录' }}<span v-if="createMode(a) === 'specified'" class="ae-config-count">{{ a.values?.length || 0 }}</span></button></template>
                <div class="ae-create-options">
                  <label v-for="o in [{ value: 'blank', label: '空白记录' }, { value: 'specified', label: '指定内容的记录' }]" :key="o.value">
                    <input type="radio" :name="`create-${a.id}`" :checked="createMode(a) === o.value" @change="setCreateMode(i, o.value)" />{{ o.label }}
                  </label>
                </div>
                <div v-if="createMode(a) === 'specified'" class="ae-create-values">
                  <div v-for="(v, vi) in a.values" :key="vi" class="ae-value-row">
                    <TbFieldSelect :model-value="v.fieldId" :fields="writableFields(a.tableId)" :column-groups="groupsOf(a.tableId)"
                                   class="ae-create-field" @update:model-value="fn => setValue(i, vi, { fieldId: fn, value: undefined })" />
                    <span class="ae-create-eq">等于</span>
                    <ValueInput :model-value="v.value" :field="fieldsOf(a.tableId).find(f => f.field_name === v.fieldId)"
                                :steps="stepsBefore(i + 2)" @update:model-value="nv => setValue(i, vi, { ...v, value: nv })" />
                    <button type="button" class="ae-create-delete" aria-label="删除指定内容" @click="removeValue(i, vi)"><StIcon name="trash" :size="16" /></button>
                  </div>
                  <button type="button" class="ae-add-cond ae-create-add" @click="addValue(i)"><StIcon name="plus" :size="16" />添加指定内容</button>
                </div>
              </el-popover>
            </template>
            <template v-else>
              <span>里，对</span>
              <el-popover trigger="click" placement="bottom-start" :width="540" :hide-after="0" :show-arrow="false"
                          :popper-style="{ maxWidth: 'calc(100vw - 24px)' }">
                <template #reference>
                  <button type="button" class="ae-pill ae-create-trigger">{{ targetOptions(i).find(o => o.value === targetValue(a))?.label || '选择记录' }}</button>
                </template>
                <div class="ae-create-options ae-target-options">
                  <label v-for="o in targetOptions(i)" :key="o.value" class="ae-target-option">
                    <input type="radio" :name="`target-${a.id}`" :checked="targetValue(a) === o.value" @change="setTarget(i, o.value)" />{{ o.label }}
                  </label>
                </div>
                <div v-if="a.target === 'matching'" class="ae-find-conditions ae-target-conditions">
                  <div class="ae-line">
                    <span>满足以下</span>
                    <el-select :model-value="a.match || 'all'" class="ae-sel-xs" :teleported="false" @update:model-value="v => patchAction(i, { match: v })">
                      <el-option value="all" label="所有" /><el-option value="any" label="任一" />
                    </el-select><span>条件</span>
                  </div>
                  <PermCondRow v-for="(c, ci) in a.conditions" :key="ci" :cond="c" :fields="fieldsOf(a.tableId)" :column-groups="groupsOf(a.tableId)"
                               @update="nc => setActCond(i, ci, nc)" @remove="removeActCond(i, ci)" />
                  <button type="button" class="ae-add-cond ae-find-add" @click="addActCond(i)"><StIcon name="plus" :size="16" />添加条件</button>
                </div>
              </el-popover>
              <div class="ae-update-inline">
                <span>修改</span>
                <el-popover trigger="click" placement="bottom-start" :width="560" :hide-after="0" :show-arrow="false"
                            :popper-style="{ maxWidth: 'calc(100vw - 24px)' }">
                  <template #reference>
                    <button type="button" class="ae-pill ae-create-trigger">指定内容<span class="ae-config-count">{{ a.values?.length || 0 }}</span></button>
                  </template>
                  <div class="ae-update-values">
                    <div v-for="(v, vi) in a.values" :key="vi" class="ae-value-row">
                      <TbFieldSelect :model-value="v.fieldId" :fields="writableFields(a.tableId)" :column-groups="groupsOf(a.tableId)"
                                     class="ae-create-field" @update:model-value="fn => setValue(i, vi, { fieldId: fn, value: undefined })" />
                      <span class="ae-create-eq">修改为</span>
                      <ValueInput :model-value="v.value" :field="fieldsOf(a.tableId).find(f => f.field_name === v.fieldId)"
                                  :steps="stepsBefore(i + 2)" @update:model-value="nv => setValue(i, vi, { ...v, value: nv })" />
                      <button type="button" class="ae-create-delete" aria-label="删除指定内容" @click="removeValue(i, vi)"><StIcon name="trash" :size="16" /></button>
                    </div>
                    <button type="button" class="ae-add-cond ae-create-add" @click="addValue(i)"><StIcon name="plus" :size="16" />添加指定内容</button>
                  </div>
                </el-popover>
              </div>
            </template>
          </div>
        </template>
      </div>
    </template>

    <el-dropdown :hide-after="0" v-if="modelValue.actions.length" trigger="click" @command="addAction">
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
import ScheduleTimePicker from './ScheduleTimePicker.vue'

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
const watchMode = computed(() => trig.value.watchMode || (trig.value.watchFields?.length || trig.value.watchConditions?.length ? 'specified' : 'any'))
const watchConditions = computed(() => trig.value.watchConditions ?? (trig.value.watchFields || []).map(fieldId => ({ fieldId, operator: 'changed' })))
function setWatchMode(mode) {
  patchTrig({ watchMode: mode, watchFields: [], watchConditions: mode === 'specified'
    ? (watchConditions.value.length ? watchConditions.value : [{ fieldId: null, operator: 'eq' }]) : [] })
}
function saveWatchConditions(conditions) { patchTrig({ watchMode: 'specified', watchFields: [], watchConditions: conditions }) }
function addWatchCond() { saveWatchConditions([...watchConditions.value, { fieldId: null, operator: 'eq' }]) }
function setWatchCond(i, condition) { saveWatchConditions(watchConditions.value.map((c, j) => j === i ? condition : c)) }
function removeWatchCond(i) { saveWatchConditions(watchConditions.value.filter((_, j) => j !== i)) }
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
  if (type === 'recordCreated') base.rowConditions = props.fields[0]
    ? [{ fieldId: props.fields[0].field_name, operator: 'isNotEmpty' }] : []
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
  if (type === 'createRecord') return { id: uid(), type, tableId: props.tableId, recordMode: 'specified', values: [] }
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
function createMode(a) { return a.recordMode || (a.values?.length ? 'specified' : 'blank') }
function setCreateMode(i, mode) { patchAction(i, { recordMode: mode, ...(mode === 'blank' ? { values: [] } : {}) }) }
function addValue(i) { patchAction(i, { values: [...(props.modelValue.actions[i].values || []), { fieldId: null, value: undefined }] }) }
function setValue(i, vi, v) { const l = [...props.modelValue.actions[i].values]; l[vi] = v; patchAction(i, { values: l }) }
function removeValue(i, vi) { patchAction(i, { values: props.modelValue.actions[i].values.filter((_, j) => j !== vi) }) }
function targetValue(a) { return a.target === 'found' ? `found:${a.foundStep}` : a.target }
function targetOptions(i) {
  return [
    { value: 'all', label: '所有记录' },
    { value: 'matching', label: '满足条件的记录' },
    ...(trig.value.type === 'schedule' ? [] : [{
      value: 'triggered', label: trig.value.type === 'recordCreated' ? '第1步新增的记录' : '第1步修改的记录',
    }]),
    ...findStepsBefore(i + 2).map(s => ({ value: `found:${s}`, label: `第${s}步找到的记录` })),
  ]
}
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
.ae-sec-title { font-size: 16px; font-weight: 700; color: var(--st-text-1); margin: 16px 0 22px; }
.ae-step-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--st-text-2); margin: 8px 0 8px 2px; }
.ae-dot { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--st-text-4); }
.ae-card { background: #fff; border: 1px solid var(--st-border); border-radius: 5px; padding: 24px 20px; margin-bottom: 10px; display: flex; flex-direction: column; gap: 18px; }
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
.ae-divider { border-top: 1px solid var(--st-border); margin: 28px -28px 26px; position: relative; display: flex; justify-content: flex-start; padding-left: 30px; color: var(--st-text-4); }
.ae-divider .st-icon { margin-top: -7px; }
.ae-action-head { display: flex; justify-content: space-between; align-items: center; }
.ae-del { color: var(--st-text-3); cursor: pointer; display: inline-flex; visibility: hidden; }
.ae-action:hover .ae-del { visibility: visible; }
.ae-del:hover { color: var(--el-color-danger); }
.ae-label { font-size: 14px; color: var(--st-text-2); margin-bottom: -6px; }
.ae-channels { display: grid; grid-template-columns: 1fr; gap: 16px; }
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
.ae-find-trigger { min-height: 36px; cursor: pointer; font-family: inherit; white-space: nowrap; }
.ae-find-trigger:hover { border-color: var(--el-border-color-hover); }
.ae-config-count { margin-left: 8px; color: var(--st-text-3); font-size: 12px; font-variant-numeric: tabular-nums; }
.ae-find-conditions { display: flex; flex-direction: column; gap: 14px; padding: 4px; }
.ae-watch-panel { color: var(--st-text-1); font-size: 14px; padding: 4px; }
.ae-watch-trigger { min-height: 34px; font-family: inherit; cursor: pointer; }
.ae-watch-modes { display: flex; flex-direction: column; align-items: flex-start; padding: 0 4px 8px; }
.ae-watch-modes :deep(.el-radio) { margin-right: 0; height: 36px; }
.ae-watch-conditions { display: flex; flex-direction: column; gap: 12px; border-top: 1px solid var(--st-border); padding: 16px 0 0; }
.ae-watch-conditions :deep(.pcr) { gap: 8px; }
.ae-watch-conditions :deep(.pcr-field) { width: 132px; }
.ae-watch-conditions :deep(.pcr-op) { width: 94px; }
.ae-watch-conditions :deep(.tbfs),
.ae-watch-conditions :deep(.el-input__wrapper),
.ae-watch-conditions :deep(.el-select__wrapper) { min-height: 36px; height: 36px; border-radius: 6px; font-size: 14px; box-sizing: border-box; }
.ae-watch-conditions :deep(.el-input__inner),
.ae-watch-conditions :deep(.el-select__selected-item) { font-size: 14px; }
.ae-watch-conditions :deep(.el-input-number) { width: 100%; height: 36px; }
.ae-watch-conditions :deep(.el-input-number .el-input__inner) { text-align: left; }
.ae-watch-conditions :deep(.enum-val) { min-height: 36px; box-sizing: border-box; }
.ae-watch-conditions :deep(.pcr-del) { width: 28px; height: 28px; padding: 0; border: none; border-radius: 5px; background: transparent; justify-content: center; align-items: center; }
.ae-watch-conditions :deep(.pcr-del:hover) { color: var(--st-text-1); background: var(--st-bg-hover, #f2f3f5); }
.ae-watch-conditions .ae-find-add { display: inline-flex; align-items: center; gap: 6px; color: var(--st-text-2); border-radius: 5px; padding: 6px 8px; margin-left: -8px; cursor: pointer; }
.ae-watch-conditions .ae-find-add:hover { background: var(--st-bg-hover, #f2f3f5); color: var(--st-text-1); }
.ae-target-conditions { border-top: 1px solid var(--st-border); padding-top: 14px; }
.ae-find-add { align-self: flex-start; border: 0; background: transparent; font: inherit; padding: 6px 0; }
.ae-values { display: flex; flex-direction: column; gap: 10px; }
.ae-update-inline { display: inline-flex; align-items: center; gap: 8px; flex: none; white-space: nowrap; }
.ae-update-values { display: flex; flex-direction: column; gap: 10px; padding: 4px; }
.ae-create-trigger { min-height: 36px; cursor: pointer; font-family: inherit; white-space: nowrap; }
.ae-create-options { display: flex; flex-direction: column; gap: 4px; padding: 0 4px 12px; }
.ae-create-options label { display: flex; align-items: center; gap: 10px; padding: 10px 4px; cursor: pointer; font-size: 15px; color: var(--st-text-1); }
.ae-create-options input { width: 18px; height: 18px; margin: 0; accent-color: var(--st-primary); }
.ae-create-values { display: flex; flex-direction: column; gap: 10px; border-top: 1px solid var(--st-border); padding: 12px 4px 0; }
.ae-create-field { width: 128px; flex: none; }
.ae-create-eq { flex: none; color: var(--st-text-2); font-size: 14px; }
.ae-create-delete { display: inline-flex; padding: 6px; border: 0; background: transparent; color: var(--st-text-3); cursor: pointer; }
.ae-create-delete:hover { color: var(--el-color-danger); }
.ae-create-add { align-self: flex-start; border: 0; background: transparent; font: inherit; padding: 8px 0; }
.ae-value-row { display: flex; align-items: center; gap: 8px; }
.ae-eq { color: var(--st-text-3); }
.ae-rm { color: var(--st-text-4); cursor: pointer; display: inline-flex; }
.ae-rm:hover { color: var(--el-color-danger); }
.ae-add-action { display: inline-flex; align-items: center; gap: 8px; font-size: 16px; color: var(--st-text-2); cursor: pointer; margin: 10px 0 0 6px; }
.ae-add-action:hover { color: var(--st-primary); }
.ae-step-label { position: relative; margin: 0 0 12px 4px; }
.ae-step-label::after { content: ''; position: absolute; width: 1px; height: 13px; background: var(--st-border); left: 6px; top: 16px; }
.ae-choice-label { font-size: 15px; color: var(--st-text-2); }
.ae-choice-options { display: flex; flex-wrap: wrap; gap: 8px; }
.ae-choice { display: inline-flex; align-items: center; gap: 7px; padding: 6px 10px; background: #fff; border: 1px solid var(--st-border); border-radius: 3px; cursor: pointer; color: var(--st-text-1); font: inherit; font-size: 14px; }
.ae-choice:hover:not(:disabled) { background: var(--st-bg-hover); border-color: var(--st-primary); }
.ae-choice:disabled { opacity: .4; cursor: not-allowed; }
.ae :deep(.me) { border-radius: 5px; padding: 18px 16px 6px; }
.ae :deep(.me-body) { min-height: 220px; }
.ae :deep(.me-bar) { flex-wrap: wrap; gap: 12px; }
.ae :deep(.el-select__wrapper), .ae :deep(.el-input__wrapper) { min-height: 34px; box-sizing: border-box; }
@media (max-width: 520px) { .ae-card { padding: 18px 14px; } .ae-channels { gap: 8px; } .ae-channel { padding: 10px; } .ae-value-row { flex-wrap: wrap; } }
</style>
