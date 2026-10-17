<template>
  <!-- 工具栏面板通用字段下拉（排序 / 分组 / 填色）：带边框选择框（字段类型图标 + 名称 + ▾），
       点开为统一的「选择字段」面板（FieldPickList：编组为可折叠节点，参照 docs/PixPin_2026-10-18_01-05-36.png）。
       :teleported="false"：面板渲染在外层工具栏面板内部，点选字段不会被当成"点击外部"而关掉外层面板；
       strategy fixed：不被外层面板的滚动区裁剪 -->
  <el-popover v-model:visible="open" trigger="click" placement="bottom-start" :width="324" :teleported="false"
              :show-arrow="false" :popper-options="{ strategy: 'fixed' }" popper-class="st-tbpanel st-pick-pop">
    <template #reference>
      <div class="tbfs" :class="{ borderless, open }">
        <StIcon v-if="current" :name="fieldIconName(current)" :size="16" class="tbfs-ico" />
        <span class="tbfs-label" :class="{ ph: !current }">{{ current ? current.label : placeholder }}</span>
        <span v-if="clearable && current" class="tbfs-clear" title="清除" @click.stop="emit('update:modelValue', null)"><StIcon name="close" :size="12" /></span>
        <StIcon :name="open ? 'chevron-up' : 'chevron-down'" :size="14" class="tbfs-caret" />
      </div>
    </template>
    <FieldPickList :fields="fields" :column-groups="columnGroups" :selected="modelValue" @pick="pick" />
  </el-popover>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'
import FieldPickList from './FieldPickList.vue'

const props = defineProps({
  modelValue: { type: String, default: null },
  fields: { type: Array, default: () => [] },
  placeholder: { type: String, default: '选择字段' },
  borderless: Boolean,
  clearable: Boolean,
  // 编组：默认取当前表编组（inject）；字段来自其他表时传 []（智能表字段名 f_N 跨表重名，不能套用本表编组）
  columnGroups: { type: Array, default: null },
})
const emit = defineEmits(['update:modelValue'])
const open = ref(false)
const current = computed(() => props.fields.find(f => f.field_name === props.modelValue))
function pick(f) {
  open.value = false
  if (f.field_name !== props.modelValue) emit('update:modelValue', f.field_name)
}
</script>

<style scoped>
.tbfs { display: flex; align-items: center; gap: 8px; min-height: 36px; padding: 0 10px 0 12px; box-sizing: border-box;
  border-radius: 6px; box-shadow: 0 0 0 1px var(--el-border-color) inset; background: #fff; cursor: pointer; font-size: 14px; }
.tbfs:hover { box-shadow: 0 0 0 1px var(--el-border-color-hover) inset; }
.tbfs.open { box-shadow: 0 0 0 1px var(--st-primary) inset; }
.tbfs.borderless { box-shadow: none !important; background: transparent; padding-left: 0; }
.tbfs-ico { color: var(--st-text-1); flex: none; }
.tbfs-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--st-text-1); }
.tbfs-label.ph { color: var(--el-text-color-placeholder); }
.tbfs-caret { flex: none; color: var(--st-text-3); }
.tbfs-clear { display: none; flex: none; color: var(--st-text-3); }
.tbfs:hover .tbfs-clear { display: inline-flex; }
.tbfs-clear:hover { color: var(--st-text-1); }
</style>
