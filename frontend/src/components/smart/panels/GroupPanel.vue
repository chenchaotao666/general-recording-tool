<template>
  <!-- 分组面板（§5.2，对齐参照 docs/智慧表格/表格上方按钮/分组.png）：
       规则行（⋮⋮ 拖拽 + 字段下拉 + 方向两段切换 + ⊖）→「＋ 添加分组字段」（最多 3 级，满额置灰）。即时生效 -->
  <el-popover trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="500" popper-class="st-tbpanel">
    <template #reference><slot /></template>
    <div class="gp">
      <div class="gp-head"><span class="tbp-title">分组</span></div>
      <div v-for="(g, i) in draft" :key="g._k" class="gp-row" :class="dropClass(i)"
           @dragover.prevent="overIdx = i" @drop.prevent="dropRow(i)">
        <span class="tbp-drag st-icon-action" draggable="true" @dragstart="dragIdx = i" @dragend="dragIdx = overIdx = null"><StIcon name="drag" :size="15" /></span>
        <TbFieldSelect :model-value="g.fieldId" :fields="fields" placeholder="选择分组字段" class="gp-field"
                       @update:model-value="(v) => update(i, { fieldId: v })" />
        <DirToggle :model-value="g.direction" :labels="labelsOf(g)" @update:model-value="(v) => update(i, { direction: v })" />
        <span class="tbp-del st-icon-action" data-smart-tip="删除" @click="remove(i)"><StIcon name="minus-circle" :size="20" /></span>
      </div>
      <el-tooltip :disabled="draft.length < 3" content="最多支持 3 级分组" placement="top">
        <span class="gp-add-wrap"><button class="tbp-add" :disabled="draft.length >= 3" @click="add"><StIcon name="plus" :size="15" />添加分组字段</button></span>
      </el-tooltip>
    </div>
  </el-popover>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import TbFieldSelect from './TbFieldSelect.vue'
import DirToggle from './DirToggle.vue'
import { sortDirectionLabels } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:visible', 'change'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

let seq = 0
const draft = ref([])
watch(() => props.visible, (v) => { if (v) draft.value = props.groups.map(g => ({ ...g, _k: ++seq })) }, { immediate: true })
function commit() { emit('change', draft.value.filter(g => g.fieldId).map(({ _k, ...g }) => g)) }

const labelsOf = (g) => sortDirectionLabels(props.fields.find(f => f.field_name === g.fieldId))
function update(i, patch) { draft.value = draft.value.map((g, j) => (j === i ? { ...g, ...patch } : g)); commit() }
function add() { draft.value = [...draft.value, { fieldId: null, direction: 'asc', _k: ++seq }] }
function remove(i) { draft.value = draft.value.filter((_, j) => j !== i); commit() }

const dragIdx = ref(null)
const overIdx = ref(null)
function dropClass(i) {
  if (dragIdx.value === null || overIdx.value !== i || dragIdx.value === i) return ''
  return dragIdx.value > i ? 'drop-before' : 'drop-after'
}
function dropRow(i) {
  const from = dragIdx.value
  dragIdx.value = overIdx.value = null
  if (from === null || from === i) return
  const arr = [...draft.value]
  const [m] = arr.splice(from, 1)
  arr.splice(i, 0, m)
  draft.value = arr
  commit()
}
</script>

<style scoped>
.gp { display: flex; flex-direction: column; gap: 6px; }
.gp-head { margin-bottom: 6px; }
.gp-row { display: flex; align-items: center; gap: 12px; border-top: 2px solid transparent; border-bottom: 2px solid transparent; }
.gp-row.drop-before { border-top-color: var(--st-primary); }
.gp-row.drop-after { border-bottom-color: var(--st-primary); }
.gp-field { flex: 1; min-width: 0; }
.gp-add-wrap { margin-left: 27px; align-self: flex-start; display: inline-flex; }
</style>
