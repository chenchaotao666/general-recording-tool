<template>
  <!-- 看板视图（§18 V3 数据可视化入口「新建看板：按选项分类查看」）：按单选字段分列，卡片拖拽改分类 -->
  <div class="kb">
    <div class="kb-bar">
      <span class="kb-label">分组字段</span>
      <TbFieldSelect :model-value="groupField" :fields="selectFields" class="kb-sel" placeholder="选择单选字段"
                     :class="{ 'kb-disabled': !canManage }" @update:model-value="(v) => canManage && emit('config', { groupField: v })" />
      <span class="kb-label">卡片显示</span>
      <el-select :model-value="cardFields" size="small" multiple collapse-tags class="kb-sel-m" placeholder="自动"
                 :disabled="!canManage" @update:model-value="(v) => emit('config', { cardFields: v })">
        <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
      </el-select>
    </div>
    <div v-if="!gField" class="kb-empty">请选择一个单选字段作为看板分组依据</div>
    <div v-else class="kb-cols">
      <div v-for="col in columns" :key="col.key" class="kb-col" :class="{ over: overCol === col.key }"
           @dragover.prevent="overCol = col.key" @dragleave="overCol = null" @drop="onDrop(col)">
        <div class="kb-col-head">
          <span v-if="col.option" class="kb-tag" :style="{ background: optionColor(col.option.color).value, color: optionColor(col.option.color).text }">{{ col.label }}</span>
          <span v-else class="kb-tag kb-tag-none">{{ col.label }}</span>
          <span class="kb-count">{{ col.rows.length }}</span>
        </div>
        <div class="kb-cards">
          <div v-for="r in col.rows" :key="r.id" class="kb-card" :draggable="canEdit(r, gField)" @dragstart="dragRow = r"
               @click="emit('open', r)">
            <div class="kb-card-title">{{ titleOf(r) }}</div>
            <div v-for="f in shownFields.filter(x => !isEmptyVal(r[x.field_name]))" :key="f.field_name" class="kb-card-field">
              <span class="kb-f-label">{{ f.label }}</span>
              <SmartCell :field="f" :record="r" class="kb-f-val" />
            </div>
          </div>
        </div>
        <div v-if="canAdd" class="kb-add" @click="emit('add', col.option ? col.option.id : null)"><StIcon name="plus" :size="13" />添加记录</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'
import TbFieldSelect from '../panels/TbFieldSelect.vue'
import SmartCell from '../grid/SmartCell.vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  fields: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  config: { type: Object, default: () => ({}) },   // view.config.kanban
  canEditCell: { type: Function, default: () => true },
  canAdd: Boolean,
  canManage: Boolean,
})
const emit = defineEmits(['move', 'add', 'open', 'config'])

const selectFields = computed(() => props.fields.filter(f => f.field_type === 'singleSelect'))
const groupField = computed(() => props.config?.groupField || null)
const gField = computed(() => props.fields.find(f => f.field_name === groupField.value) || null)
const cardFields = computed(() => props.config?.cardFields || [])
const primary = computed(() => props.fields[0])
const shownFields = computed(() => {
  const chosen = cardFields.value.length ? cardFields.value : props.fields.slice(1).filter(f => f.field_name !== groupField.value).slice(0, 3).map(f => f.field_name)
  return chosen.map(fn => props.fields.find(f => f.field_name === fn)).filter(Boolean)
})
const columns = computed(() => {
  if (!gField.value) return []
  const opts = gField.value.options?.options || []
  const cols = opts.map(o => ({ key: o.id, label: o.label, option: o, rows: [] }))
  const none = { key: '__none', label: '未分类', option: null, rows: [] }
  const byId = new Map(cols.map(c => [c.key, c]))
  for (const r of props.rows) {
    const v = r[gField.value.field_name]
    ;(byId.get(v) || none).rows.push(r)
  }
  return [none, ...cols]   // 「未分类」列常驻：可把卡片拖回未分类
})
const isEmptyVal = (v) => v == null || v === '' || (Array.isArray(v) && !v.length)
function titleOf(r) {
  const v = r[primary.value?.field_name]
  return v == null || v === '' ? '未命名记录' : (typeof v === 'object' ? JSON.stringify(v) : String(v))
}
function canEdit(r, fn) { return props.canEditCell(r, props.fields.find(f => f.field_name === fn)) }

const dragRow = ref(null)
const overCol = ref(null)
function onDrop(col) {
  overCol.value = null
  const r = dragRow.value
  dragRow.value = null
  if (!r) return
  const target = col.option ? col.option.id : null
  if ((r[gField.value.field_name] ?? null) === target) return
  emit('move', r, gField.value, target)
}
</script>

<style scoped>
.kb { flex: 1; display: flex; flex-direction: column; min-height: 0; background: var(--st-bg-canvas); }
.kb-bar { display: flex; align-items: center; gap: 8px; padding: 8px 14px; background: #fff; border-bottom: 1px solid var(--st-border); font-size: 13px; }
.kb-label { color: var(--st-text-2); }
.kb-sel { width: 160px; }
.kb-sel-m { width: 220px; margin-right: auto; }
.kb-empty { padding: 60px; text-align: center; color: var(--st-text-3); }
.kb-cols { flex: 1; display: flex; gap: 12px; padding: 14px; overflow: auto; align-items: flex-start; }
.kb-col { width: 272px; flex: none; background: #F0F1F3; border-radius: 10px; padding: 10px; display: flex; flex-direction: column; max-height: 100%; border: 2px solid transparent; }
.kb-col.over { border-color: var(--st-primary); }
.kb-col-head { display: flex; align-items: center; gap: 8px; padding: 2px 4px 10px; }
.kb-tag { border-radius: 4px; padding: 1px 8px; font-size: 13px; }
.kb-tag-none { background: #E3E5E8; color: var(--st-text-2); }
.kb-count { font-size: 12px; color: var(--st-text-3); }
.kb-cards { display: flex; flex-direction: column; gap: 8px; overflow: auto; }
.kb-card { background: #fff; border-radius: 8px; padding: 10px 12px; cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.kb-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.1); }
.kb-card-title { font-size: 14px; font-weight: 600; color: var(--st-text-1); margin-bottom: 6px; word-break: break-all; }
.kb-card-field { display: flex; flex-direction: column; gap: 2px; margin-top: 6px; }
.kb-f-label { font-size: 11px; color: var(--st-text-3); }
.kb-f-val { font-size: 13px; min-height: 18px; }
.kb-f-val:deep(.smart-cell), .kb-card-field :deep(.smart-cell) { justify-content: flex-start; text-align: left; }
.kb-add { display: flex; align-items: center; gap: 4px; padding: 8px 6px 2px; color: var(--st-text-2); font-size: 13px; cursor: pointer; }
.kb-add:hover { color: var(--st-primary); }
</style>
