<template>
  <!-- 分组面板（§5.2）：多级分组字段列表 + 方向（类型自适应文案）。
       草稿模式：面板内自由编辑，点「确定」才落库 -->
  <el-popover trigger="click" v-model:visible="visibleModel" placement="bottom-start" :width="380">
    <template #reference><slot /></template>
    <div class="panel">
      <div class="panel-head"><b>分组</b></div>
      <div v-for="(g, i) in draft" :key="i" class="rule-row">
        <span class="drag">⋮⋮</span>
        <el-select :teleported="false" :model-value="g.fieldId" size="small" class="r-field" placeholder="选择分组字段"
                   @change="(v) => update(i, { fieldId: v })">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
        <el-radio-group :model-value="g.direction" size="small" @change="(v) => update(i, { direction: v })">
          <el-radio-button value="asc">{{ labelsOf(g)[0] }}</el-radio-button>
          <el-radio-button value="desc">{{ labelsOf(g)[1] }}</el-radio-button>
        </el-radio-group>
        <span class="r-del" @click.stop="remove(i)">⊖</span>
      </div>
      <el-button link type="primary" size="small" :disabled="draft.length >= 3" @click="add">
        ＋ 添加分组字段{{ draft.length >= 3 ? '（最多 3 级）' : '' }}
      </el-button>
      <div class="panel-foot">
        <el-button size="small" @click="cancel">取消</el-button>
        <el-button size="small" type="primary" @click="confirm">确定</el-button>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { sortDirectionLabels } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:visible', 'change'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

// 草稿：打开时从 props 复制，确定才 emit（一次落库，避免防抖保存吞掉不完整行）
const draft = ref([])
watch(() => props.visible, (v) => {
  if (v) draft.value = props.groups.map((g) => ({ ...g }))
})

function labelsOf(g) {
  return sortDirectionLabels(props.fields.find(f => f.field_name === g.fieldId))
}
function update(i, patch) { draft.value = draft.value.map((g, j) => (j === i ? { ...g, ...patch } : g)) }
function add() { draft.value = [...draft.value, { fieldId: null, direction: 'asc' }] }
function remove(i) { draft.value = draft.value.filter((_, j) => j !== i) }

function cancel() { emit('update:visible', false) }
function confirm() {
  emit('change', draft.value.filter((g) => g.fieldId))
  emit('update:visible', false)
}
</script>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 8px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-foot { display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid #ebeef5; padding-top: 8px; }
.rule-row { display: flex; align-items: center; gap: 6px; }
.drag { color: var(--el-text-color-placeholder); cursor: grab; }
.r-field { width: 150px; }
.r-del { cursor: pointer; color: var(--el-color-danger); }
</style>
