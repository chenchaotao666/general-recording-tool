<template>
  <div class="relation-anchor" @mousedown.stop @click.stop @dblclick.stop @mouseenter="ensureLoaded">
    <div ref="anchor" class="relation-trigger" :class="{ selected }" @click="toggle">
      <CompactCellTags v-if="!selected" :tags="compactTags" />
      <div v-else class="relation-chips">
        <el-popover v-for="id in ids" :key="id" trigger="hover" :show-after="450" :width="270" placement="right" :show-arrow="false">
          <template #reference><span class="relation-chip" @click.stop="clickRecord(id)"><StIcon name="relation" :size="14" class="relation-symbol" /><span class="relation-title">{{ label(id) }}</span><button v-if="selected && !readonly" class="relation-icon" aria-label="移除关联" @click.stop="remove(id)">×</button></span></template>
          <div class="relation-preview" @mousedown.stop><strong @click="showDetail(id)">{{ label(id) }} <button class="relation-icon" aria-label="展开记录">↗</button></strong><div v-for="f in previewFields" :key="f.id"><label>{{ f.label }}</label><SmartCell :field="f" :record="records.get(id) || {}" /></div></div>
        </el-popover>
      </div>
      <CellDropdown v-if="selected" overlay bordered :open="opened" label="关联记录" @click="toggle" />
    </div>
    <el-popover v-if="opened" :visible="opened" virtual-triggering :virtual-ref="anchor" placement="bottom-start" :width="420" :show-arrow="false" popper-class="relation-pop">
      <div ref="panel" class="relation-panel" @mousedown.stop @click.stop>
        <div v-if="error" class="relation-error">{{ error }}</div>
        <div class="relation-cards" v-loading="loading">
          <article v-for="id in ids" :key="id" class="relation-card" @click="showDetail(id)">
            <strong>{{ label(id) }}<button v-if="!readonly" class="relation-icon" aria-label="移除关联" @click.stop="remove(id)">×</button></strong>
            <div class="relation-card-fields"><div v-for="f in previewFields" :key="f.id"><label>{{ f.label }}</label><SmartCell :field="f" :record="records.get(id) || {}" /></div></div>
          </article>
        </div>
        <button v-if="!readonly" class="relation-add" @click="openPicker">＋ {{ ids.length ? '请重新选择' : '添加' }}</button>
        <div v-else-if="!ids.length" class="relation-add">暂无关联记录</div>
      </div>
    </el-popover>
    <el-dialog v-if="picker" v-model="picker" :title="`${sourceTitle} · ${field.label}`" width="900px" append-to-body class="relation-picker" @mousedown.stop @click.stop>
      <div class="relation-source">来自 ▦ {{ tableName || '关联表' }}</div>
      <el-input v-model="search" clearable placeholder="搜索关联记录" class="relation-search" @input="searchChanged" />
      <div v-if="error" class="relation-error">{{ error }}</div>
      <el-table v-loading="listLoading" :data="rows" border height="390" row-key="id" @row-click="row => choose(row.id)">
        <el-table-column width="46" fixed><template #default="{ row }"><el-checkbox :model-value="chosen.includes(row.id)" @click.stop @change="choose(row.id)" /></template></el-table-column>
        <el-table-column v-for="f in fields" :key="f.id" :label="f.label" :min-width="180"><template #default="{ row }"><SmartCell :field="f" :record="row" /></template></el-table-column>
      </el-table>
      <div class="relation-list-footer"><span>已选择 {{ chosen.length }} 条</span><el-pagination size="small" layout="prev, pager, next" :total="total" :page-size="50" v-model:current-page="page" @current-change="loadPage" /></div>
      <template #footer><div class="relation-actions"><el-button type="primary" :disabled="listLoading" @click="confirm">确定</el-button><el-button @click="picker = false">取消</el-button></div></template>
    </el-dialog>
    <RecordDetailFloating v-if="detailOpen && detail" visible :source="tableName" :record="detail" :fields="fields" :view="view"
      :title-field="view?.config?.recordTitleField" :readonly="!permissions.can_edit || detail.__readonly"
      :can-edit-cell="canEditDetail" :can-create="false" :can-delete="false" :can-set-title="canSetTitle && !!view?.id"
      :has-prev="detailIndex > 0" :has-next="detailIndex >= 0 && detailIndex < ids.length - 1"
      @close="detailOpen = false" @nav="navigate" @cell-commit="saveDetail" @set-title-field="setTitleField" />
  </div>
</template>
<script setup>
import { useGridScrollCollapse } from '../../../smart/utils/useGridScrollCollapse.js'
import { computed, defineAsyncComponent, inject, onBeforeUnmount, provide, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { smartRelationRecords, smartUpdateView, smartUpdateRecord } from '../../../api/index.js'
import CellDropdown from './CellDropdown.vue'
import SmartCell from './SmartCell.vue'
import StIcon from '../icons/StIcon.vue'
import CompactCellTags from './CompactCellTags.vue'
const RecordDetailFloating = defineAsyncComponent(() => import('../panels/RecordDetailFloating.vue'))
const props = defineProps({ value: [Array, Number, String], field: { type: Object, required: true }, record: Object, selected: Boolean, readonly: Boolean })
const emit = defineEmits(['select', 'open', 'collapse', 'cancel', 'commit'])
const target = computed(() => props.field.options?.targetTableId)
provide('smartTableId', target)
const directory = inject('smartRelationRows', ref(new Map()))
const ids = computed(() => (Array.isArray(props.value) ? props.value : props.value ? [props.value] : []).map(Number))
const compactTags = computed(() => ids.value.map(id => ({ key: id, label: label(id), icon: 'relation', style: { background: '#F0F1F3', color: '#646A73' } })))
const fields = ref([]), records = ref(new Map()), rows = ref([]), permissions = ref({}), rights = ref({}), view = ref({ config: {} })
const tableName = ref(''), opened = ref(false), picker = ref(false), loading = ref(false), listLoading = ref(false), error = ref('')
const anchor = ref(), panel = ref(), search = ref(''), chosen = ref([]), page = ref(1), total = ref(0), canSetTitle = ref(false)
const detailOpen = ref(false), detailId = ref(null), detail = computed(() => records.value.get(detailId.value)), detailIndex = computed(() => ids.value.indexOf(detailId.value))
const titleField = computed(() => fields.value.find(f => f.field_name === view.value?.config?.recordTitleField) || fields.value.find(f => f.field_type === 'text') || fields.value[0])
const previewFields = computed(() => fields.value.filter(f => f !== titleField.value).slice(0, 4))
const sourceTitle = computed(() => Object.entries(props.record || {}).find(([key, v]) => !key.startsWith('__') && typeof v === 'string' && v.trim())?.[1] || '关联记录')
function label(id) { const row = records.value.get(id); if (row?.__relation_label != null) return row.__relation_label; const value = row?.[titleField.value?.field_name]; return typeof value === 'string' || typeof value === 'number' ? String(value === '' ? `#${id}` : value) : directory.value.get(target.value)?.find(r => r.id === id)?.label || `#${id}` }
function remember(data) {
  canSetTitle.value = !!data.content_perm?.viewManage
  fields.value = data.fields; tableName.value = data.table_name; permissions.value = data.my_perms; rights.value = data.content_perm?.fieldRights || {}; view.value = data.view
  const next = new Map(records.value); data.items.forEach(r => next.set(r.id, r)); records.value = next
  const cached = new Map((directory.value.get(target.value) || []).map(r => [r.id, r])); data.items.forEach(r => cached.set(r.id, { id: r.id, label: label(r.id) }))
  directory.value = new Map(directory.value).set(target.value, [...cached.values()])
}
let epoch = 0, listEpoch = 0, timer
async function loadSelected() {
  const version = ++epoch; if (!target.value) return
  loading.value = true; error.value = ''
  try { const data = await smartRelationRecords(target.value, { ids: ids.value.join(','), view_id: props.field.options?.viewId }); if (version === epoch) remember(data) }
  catch { if (version === epoch) error.value = '关联记录加载失败，请重试' }
  finally { if (version === epoch) loading.value = false }
}
function ensureLoaded() { if (!loading.value && (!fields.value.length || ids.value.some(id => !records.value.has(id)))) loadSelected() }
watch(() => [target.value, ids.value.join(','), props.selected], () => { if (props.selected || opened.value) loadSelected() })
watch(target, () => { records.value = new Map(); fields.value = [] })
async function loadPage() {
  const version = ++listEpoch; listLoading.value = true; error.value = ''
  try { const data = await smartRelationRecords(target.value, { page: page.value, page_size: 50, search: search.value, view_id: props.field.options?.viewId }); if (version !== listEpoch) return; remember(data); rows.value = data.items; total.value = data.total }
  catch { if (version === listEpoch) { rows.value = []; error.value = '无法加载关联表，请重试' } }
  finally { if (version === listEpoch) listLoading.value = false }
}
function searchChanged() { clearTimeout(timer); timer = setTimeout(() => { page.value = 1; loadPage() }, 250) }
function focus() { opened.value = true; emit('open'); ensureLoaded() }
function toggle() { const active = props.selected || opened.value; emit('select'); if (!active) return; if (opened.value) close(true); else focus() }
function close(keep) { opened.value = false; emit(keep ? 'collapse' : 'cancel') }
function commit(values) { emit('commit', props.field.options?.multiple === false ? values[0] ?? null : values) }
function remove(id) { commit(ids.value.filter(v => v !== id)) }
function openPicker() { if (!target.value) { ElMessage.warning('请先设置关联表'); return }; chosen.value = [...ids.value]; search.value = ''; page.value = 1; picker.value = true; opened.value = false; loadPage() }
function choose(id) { chosen.value = chosen.value.includes(id) ? chosen.value.filter(v => v !== id) : props.field.options?.multiple === false ? [id] : [...chosen.value, id] }
function confirm() { commit(chosen.value); picker.value = false; close(true) }
function clickRecord(id) { if (!props.selected) emit('select'); else showDetail(id) }
function showDetail(id) { if (!records.value.has(id)) return; detailId.value = id; detailOpen.value = true; opened.value = false }
function navigate(direction) { const index = detailIndex.value + (direction === 'prev' || direction === -1 ? -1 : 1); if (ids.value[index]) detailId.value = ids.value[index] }
function canEditDetail(row, field) { return permissions.value.can_edit && !row.__readonly && rights.value[field.field_name]?.edit !== false }
async function saveDetail({ row, field, value }) { try { await smartUpdateRecord(target.value, row.id, { data: { [field.field_name]: value } }); records.value = new Map(records.value).set(row.id, { ...row, [field.field_name]: value }); await loadSelected() } catch { ElMessage.error('保存失败，请重试') } }
let titleSaveVersion = 0
async function setTitleField(fieldName) {
  if (!canSetTitle.value || !view.value?.id) return
  const version = ++titleSaveVersion
  const currentView = view.value
  try {
    await smartUpdateView(currentView.id, { config: { ...currentView.config, recordTitleField: fieldName } })
    if (version !== titleSaveVersion) return
    view.value = { ...currentView, config: { ...currentView.config, recordTitleField: fieldName } }
    await loadSelected()
  } catch { ElMessage.error('记录标题保存失败，请重试') }
}
function outside(event) { if (opened.value && !anchor.value?.contains(event.target) && !panel.value?.contains(event.target)) close(false) }
watch(opened, (visible, _, onCleanup) => {
  if (!visible) return
  document.addEventListener('mousedown', outside, true)
  onCleanup(() => document.removeEventListener('mousedown', outside, true))
}, { flush: 'sync' })
onBeforeUnmount(() => { epoch++; listEpoch++; clearTimeout(timer); document.removeEventListener('mousedown', outside, true) })
defineExpose({ focus })
useGridScrollCollapse(() => opened.value, () => {
  opened.value = false
  emit('collapse')
})
</script>
<style>
.el-popper.relation-pop { padding: 0; border-radius: 8px; border: 1px solid #e0e2e6; box-shadow: 0 4px 16px #0002; max-width: calc(100vw - 24px); }
.relation-picker { max-width: calc(100vw - 32px); border-radius: 10px; }
</style>
<style scoped>
.relation-anchor, .relation-trigger { width: 100%; height: auto; min-width: 0; min-height: 0; }
.relation-trigger { position: relative; display: flex; align-items: center; cursor: default; }
.relation-trigger.selected { height: auto; min-height: var(--file-row-height, 36px); box-sizing: border-box; background: white; border: 2px solid var(--st-primary, #3370ff); border-radius: 0; padding: 3px 26px 3px 6px; z-index: 2; align-self: flex-start; box-shadow: 0 4px 16px #0000001f; cursor: pointer; }
.relation-chips { display: flex; flex-wrap: wrap; align-items: center; align-content: safe center; gap: 4px; width: 100%; min-width: 0; box-sizing: border-box; container: relation-tags / inline-size; }
.relation-chip { display: inline-flex; align-items: center; max-width: 100%; box-sizing: border-box; background: #f0f1f3; color: #646a73; border-radius: 4px; padding: 1px 8px; margin: 0; line-height: 22px; font-size: 12px; gap: 4px; }
.relation-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.relation-symbol { color: #969ca5; flex: none; }
.relation-icon { flex: none; border: 0; border-radius: 4px; background: transparent; color: #9298a1; cursor: pointer; padding: 0 4px; font-size: 16px; }
.relation-icon:not([aria-label="移除关联"]):hover { background: #e5e7e9; }
@container relation-tags (max-width: 64px) {
  .relation-chip { padding-left: 4px; padding-right: 4px; }
  .relation-symbol { display: none; }
  .relation-chip .relation-icon { padding: 0; width: 16px; }
}
.relation-cards { max-height: 340px; overflow: auto; }
.relation-card { border-bottom: 1px solid #eceef1; padding: 14px 18px; cursor: pointer; }
.relation-card:hover { background: #f8f9fa; }
.relation-card strong, .relation-preview strong { display: flex; justify-content: space-between; font-weight: 500; margin-bottom: 14px; color: #30343b; }
.relation-card-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 20px; }
.relation-card-fields > div { min-width: 0; }
.relation-card-fields label, .relation-preview label { display: block; color: #969ca5; font-size: 12px; margin-bottom: 6px; }
.relation-preview > div { margin-top: 12px; }
.relation-add { display: block; width: 100%; border: 0; background: white; color: #9298a1; padding: 13px; cursor: pointer; }
.relation-add:hover { background: #f2f3f5; }
.relation-source { color: #9298a1; margin-bottom: 16px; font-size: 13px; }
.relation-search { width: 280px; margin-bottom: 16px; }
.relation-list-footer { display: flex; align-items: center; gap: 14px; padding: 10px 0; color: #9298a1; }
.relation-list-footer .el-pagination { margin-left: auto; }
.relation-actions { display: flex; justify-content: flex-end; gap: 18px; }
.relation-actions .el-button { width: 160px; height: 38px; margin: 0; }
.relation-error { color: #e45656; padding: 12px; }
</style>
