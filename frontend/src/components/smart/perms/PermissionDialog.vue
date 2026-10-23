<template>
  <!-- 全员权限 / 指定成员额外权限 对话框（设计文档 §13.2、§13.7）：
       左列条目（名称 + 当前等级摘要）｜ 右侧该条目的权限配置；底部 保存 / 取消（一次保存所有改动的条目）。
       指定成员模式：顶部黄条「因全员权限高于 X 权限，额外权限未生效」+ 摘要卡「恢复至全员权限」（§13.2 三层预警） -->
  <el-dialog :model-value="visible" width="1000px" top="4vh" class="st-perm-dlg" :show-close="false"
             append-to-body destroy-on-close @update:model-value="close">
    <template #header>
      <div class="pd-head">
        <div>
          <div class="pd-title">{{ mode === 'group' ? group?.name : '全员权限' }}<span class="st-free-tag">限时免费</span></div>
          <div v-if="mode === 'group'" class="pd-sub">
            <el-tooltip :hide-after="0" :content="`包含 ${memberNames}`" placement="bottom"><span>对指定成员生效 <StIcon name="chevron-right" :size="12" /></span></el-tooltip>
          </div>
          <div v-else class="pd-sub">全员权限对所有可编辑、仅浏览成员生效。仅浏览成员编辑前仍需申请文档编辑权限。</div>
        </div>
        <div class="pd-head-r">
          <el-dropdown :hide-after="0" v-if="mode === 'group'" trigger="click" @command="(c) => emit('group-action', c, group)">
            <span class="pd-ico st-icon-action"><StIcon name="more-h" :size="18" /></span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">修改指定成员</el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <span class="pd-ico st-icon-action" @click="close"><StIcon name="close" :size="18" /></span>
        </div>
      </div>
    </template>

    <div class="pd-body">
      <div class="pd-left">
        <div v-for="e in entries" :key="e.entry_id" class="pd-entry" :class="{ on: e.entry_id === currentId }"
             @click="select(e.entry_id)">
          <StIcon :name="entryIcon(e.type)" :size="16" class="pd-eicon" />
          <div class="pd-ename">
            <div class="pd-n">{{ e.name }}</div>
            <div class="pd-s">{{ leftSummary(e) }}</div>
          </div>
        </div>
      </div>
      <div v-loading="loading" class="pd-right">
        <template v-if="cur">
          <!-- 指定成员模式：冲突预警 + 摘要卡 -->
          <template v-if="mode === 'group'">
            <div v-if="overridden" class="pd-warn">
              <StIcon name="warn" :size="18" />因全员权限高于{{ group?.name }}权限，额外权限未生效。
              <a class="pd-warn-link" @click="emit('open-base', currentId)">查看全员权限</a>
            </div>
            <div class="pd-grant-card">
              <span class="pd-avatars">
                <span v-for="m in (group?.members || []).slice(0, 3)" :key="m.id" class="pd-av">{{ m.name[0] }}</span>
              </span>
              <div class="pd-gc-text">
                <div class="pd-gc-t">{{ group?.name }} {{ hasGrant ? '已添加额外权限' : '无额外权限' }}</div>
                <div class="pd-gc-s">全员权限为“{{ LEVEL_LABELS[cur.base.level] }}”，{{ group?.name }}{{ hasGrant ? '还有下方额外权限。' : '可在下方添加额外权限。' }}</div>
              </div>
              <el-button v-if="hasGrant" class="st-button st-button--large pd-restore" @click="restore"><StIcon name="restore" :size="16" />恢复至全员权限</el-button>
            </div>
            <div class="pd-divider" />
          </template>
          <ProfileEditor v-model="drafts[currentId]" :entry-name="cur.entry.name" :entry-type="cur.entry.type"
                         :fields="mergedFields" :record-total="cur.record_total" :level-options="levelOptions"
                         :warn-text="overridden ? `因全员权限高于${group?.name}权限，额外权限未生效。` : ''" />
          <div v-if="!cur.can_manage" class="pd-readonly-tip">你不是该表的所有者或管理员，只能查看权限配置。</div>
        </template>
      </div>
    </div>

    <template #footer>
      <el-button type="primary" class="st-button st-button--large st-button--primary pd-btn" :loading="saving" :disabled="!dirtyIds.length" @click="save">保存</el-button>
      <el-button class="st-button st-button--large pd-btn pd-cancel" @click="close">取消</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import ProfileEditor from './ProfileEditor.vue'
import { getTable, smartDeleteGroupGrant, smartEntryPermission, smartPutBasePermBatch, smartPutGroupGrant } from '../../../api/index.js'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'base' },          // base | group
  entries: { type: Array, default: () => [] },     // 总览 entries
  group: { type: Object, default: null },          // 指定成员组（mode=group）
  initialEntryId: { type: Number, default: null },
})
const emit = defineEmits(['close', 'saved', 'open-base', 'group-action'])

const LEVEL_LABELS = { NONE: '无权限', VIEW: '仅浏览', EDIT: '可编辑', FULL: '全部权限' }
const LEVEL_RANK = { NONE: 0, VIEW: 1, EDIT: 2, FULL: 3 }

const currentId = ref(null)
const details = reactive({})      // entry_id → 权限详情（含 base / grants / fields）
const tableFields = reactive({})  // table_id → 完整字段（条件值编辑需 options）
const drafts = reactive({})       // entry_id → 编辑中的 profile
const originals = reactive({})    // entry_id → 加载时快照（JSON）
const loading = ref(false)
const saving = ref(false)

const cur = computed(() => details[currentId.value] || null)
const memberNames = computed(() => (props.group?.members || []).map(m => m.name).join('、'))
const isDashboard = computed(() => cur.value?.entry.type === 'dashboard')
const levelOptions = computed(() => {
  const none = props.mode === 'group' ? '无额外权限' : '无权限'
  if (isDashboard.value) return [{ value: 'NONE', label: none }, { value: 'VIEW', label: '仅浏览' }, { value: 'FULL', label: '全部权限' }]
  return [{ value: 'NONE', label: none }, { value: 'VIEW', label: '仅浏览' }, { value: 'EDIT', label: '可编辑' }, { value: 'FULL', label: '全部权限' }]
})
const hasGrant = computed(() => !!(cur.value && props.group && cur.value.grants?.[props.group.id]))
// 全员等级 ≥ 组等级（且组有额外权限）→ 额外权限未生效
const overridden = computed(() => {
  if (props.mode !== 'group' || !cur.value) return false
  const d = drafts[currentId.value]
  return d && d.level !== 'NONE' && LEVEL_RANK[cur.value.base.level] >= LEVEL_RANK[d.level]
})
const mergedFields = computed(() => {
  if (!cur.value) return []
  const full = tableFields[cur.value.entry.table_id] || []
  const byName = new Map(full.map(f => [f.field_name, f]))
  return cur.value.fields.map(m => ({ ...(byName.get(m.field_name) || {}), ...m }))
})
const dirtyIds = computed(() => Object.keys(drafts).map(Number)
  .filter(id => JSON.stringify(drafts[id]) !== originals[id]))

function entryIcon(t) { return { dashboard: 'dashboard', form: 'form', sheet: 'view-grid' }[t] || 'view-grid' }
function leftSummary(e) {
  const d = drafts[e.entry_id]
  if (d && JSON.stringify(d) !== originals[e.entry_id]) return `${levelOptions.value.find(o => o.value === d.level)?.label || ''}（未保存）`
  if (props.mode === 'group') return props.group?.grants?.find(g => g.entry_id === e.entry_id)?.summary || '无额外权限'
  return e.summary
}

function emptyProfile() {
  return { level: 'NONE', viewManage: false, schemaEdit: false,
           record: { viewScope: 'ALL', viewConditions: [], editScope: 'ALL', editConditions: [], editFallback: 'VIEW_ONLY', add: false, delete: false },
           fields: { mode: 'ALL', newFieldDefault: { view: false, firstSubmit: false, edit: false }, items: {} } }
}

async function select(id) {
  currentId.value = id
  if (details[id]) return
  loading.value = true
  try {
    const d = await smartEntryPermission(id)
    if (d.entry.table_id && !tableFields[d.entry.table_id]) {
      tableFields[d.entry.table_id] = (await getTable(d.entry.table_id).catch(() => ({ fields: [] }))).fields || []
    }
    details[id] = d
    const prof = props.mode === 'group' ? (d.grants?.[props.group.id] || emptyProfile()) : d.base
    drafts[id] = JSON.parse(JSON.stringify(prof))
    originals[id] = JSON.stringify(drafts[id])
  } catch (e) {
    ElMessage.error(e.message || '加载权限失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, (v) => {
  if (!v) return
  for (const k of Object.keys(details)) delete details[k]
  for (const k of Object.keys(drafts)) delete drafts[k]
  for (const k of Object.keys(originals)) delete originals[k]
  const first = props.initialEntryId || props.entries[0]?.entry_id
  if (first) select(first)
}, { immediate: true })

async function save() {
  saving.value = true
  try {
    const ids = dirtyIds.value
    if (props.mode === 'group') {
      for (const id of ids) {
        if (drafts[id].level === 'NONE') await smartDeleteGroupGrant(props.group.id, id)
        else await smartPutGroupGrant(props.group.id, id, drafts[id])
      }
    } else {
      await smartPutBasePermBatch(ids.map(id => ({ entry_id: id, profile: drafts[id] })))
    }
    ElMessage.success('权限已保存')
    emit('saved')
    emit('close')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function restore() {
  try {
    await smartDeleteGroupGrant(props.group.id, currentId.value)
    details[currentId.value] = { ...cur.value, grants: { ...cur.value.grants, [props.group.id]: undefined } }
    delete details[currentId.value].grants[props.group.id]
    drafts[currentId.value] = emptyProfile()
    originals[currentId.value] = JSON.stringify(drafts[currentId.value])
    ElMessage.success('已恢复至全员权限')
    emit('saved')
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  }
}

function close() { emit('close') }
</script>

<style>
.st-perm-dlg { --el-color-primary: var(--st-primary); border-radius: 12px; padding: 0; background: #FAFAFA; }
.st-perm-dlg .el-dialog__header { padding: 22px 28px 12px; margin: 0; }
.st-perm-dlg .el-dialog__body { padding: 0; }
.st-perm-dlg .el-dialog__footer { padding: 14px 28px 18px; border-top: 1px solid var(--st-border); }
.st-free-tag { display: inline-block; margin-left: 10px; padding: 1px 6px; font-size: var(--st-font-size); font-weight: 400; color: #C98A1B; background: #FDF3DC; border-radius: 4px; vertical-align: middle; }
</style>
<style scoped>
.pd-head { display: flex; justify-content: space-between; align-items: flex-start; }
.pd-title { font-size: var(--st-font-size-title); font-weight: 700; color: var(--st-text-1); display: flex; align-items: center; }
.pd-sub { font-size: var(--st-font-size); color: var(--st-text-2); margin-top: 6px; display: inline-flex; align-items: center; gap: 2px; cursor: default; }
.pd-head-r { display: flex; gap: 14px; }
.pd-ico { display: inline-flex; cursor: pointer; color: var(--st-text-2); padding: 2px; border-radius: 4px; }
.pd-ico:hover { background: var(--st-bg-hover); }
.pd-body { display: flex; height: 72vh; border-top: 1px solid transparent; }
.pd-left { width: 300px; flex: none; overflow: auto; padding: 4px 12px 12px; border-right: 1px solid var(--st-border); }
.pd-entry { display: flex; gap: 10px; align-items: center; padding: 8px 12px; border-radius: 8px; cursor: pointer; margin-bottom: 2px; }
.pd-entry:hover { background: var(--st-bg-hover); }
.pd-entry.on { background: #E6EEFC; }
.pd-eicon { color: var(--st-text-2); }
.pd-ename { min-width: 0; }
.pd-n { font-size: var(--st-font-size); color: var(--st-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-s { font-size: var(--st-font-size); color: var(--st-text-3); }
.pd-right { flex: 1; overflow: auto; padding: 4px 28px 20px 24px; }
.pd-warn { display: flex; align-items: center; gap: 8px; background: #FDF3D5; border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; font-size: var(--st-font-size); color: #6B4D00; }
.pd-warn .st-icon { color: #F5B400; }
.pd-warn-link { margin-left: auto; color: var(--st-text-2); cursor: pointer; }
.pd-grant-card { display: flex; align-items: center; gap: 14px; background: #fff; border-radius: 10px; padding: 14px 20px; }
.pd-avatars { display: inline-flex; }
.pd-av { width: 26px; height: 26px; border-radius: 50%; background: #5B8FF9; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: var(--st-font-size); border: 2px solid #fff; margin-left: -8px; }
.pd-av:first-child { margin-left: 0; background: #F6903D; }
.pd-gc-text { flex: 1; }
.pd-gc-t { font-weight: 600; font-size: var(--st-font-size); color: var(--st-text-1); }
.pd-gc-s { font-size: var(--st-font-size); color: var(--st-text-3); margin-top: 2px; }
.pd-restore { display: inline-flex; gap: 6px; }
.pd-restore .st-icon { margin-right: 6px; }
.pd-divider { height: 1px; background: var(--st-border); margin: 16px 0 16px; }
.pd-readonly-tip { font-size: var(--st-font-size); color: var(--st-text-3); padding: 4px; }
.pd-btn { width: 130px; height: 40px; font-size: var(--st-font-size); }
.pd-cancel { background: #EEEFF1; border-color: #EEEFF1; }
</style>
