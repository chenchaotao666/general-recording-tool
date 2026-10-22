<template>
  <!-- 工具栏面板通用字段下拉（排序 / 分组 / 填色）：带边框选择框（字段类型图标 + 名称 + ▾），
       点开为统一的「选择字段」面板（FieldPickList：编组为可折叠节点，参照 docs/PixPin_2026-10-18_01-05-36.png）。
       :teleported="false"：面板渲染在外层工具栏面板内部，点选字段不会被当成"点击外部"而关掉外层面板；
       strategy fixed：不被外层面板的滚动区裁剪 -->
  <el-popover :hide-after="0" v-model:visible="open" trigger="click" :placement="placement" :width="324" :teleported="false"
              :show-arrow="false" :popper-options="popperOptions" popper-class="st-tbpanel st-pick-pop">
    <template #reference>
      <div ref="trigger" class="tbfs" :class="{ borderless, open }">
        <StIcon v-if="current" :name="fieldIconName(current)" :size="16" class="tbfs-ico" />
        <span class="tbfs-label" :class="{ ph: !hasSelection }">{{ selectionLabel || placeholder }}</span>
        <span v-if="clearable && hasSelection" class="tbfs-clear st-icon-action" data-smart-tip="清除" @click.stop="emit('update:modelValue', multiple ? [] : null)"><StIcon name="close" :size="12" /></span>
        <StIcon :name="open ? 'chevron-up' : 'chevron-down'" :size="14" class="tbfs-caret" />
      </div>
    </template>
    <FieldPickList :fields="fields" :column-groups="columnGroups" :selected="modelValue" :max-height="listHeight" @pick="pick" />
  </el-popover>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import StIcon from '../icons/StIcon.vue'
import FieldPickList from './FieldPickList.vue'

const props = defineProps({
  modelValue: { type: [String, Array], default: null },
  fields: { type: Array, default: () => [] },
  placeholder: { type: String, default: '选择字段' },
  borderless: Boolean,
  clearable: Boolean,
  // 编组：默认取当前表编组（inject）；字段来自其他表时传 []（智能表字段名 f_N 跨表重名，不能套用本表编组）
  columnGroups: { type: Array, default: null },
})
const emit = defineEmits(['update:modelValue'])
const open = ref(false)
const trigger = ref(null)
const placement = ref('bottom-start')
const listHeight = ref(420)
const popperOptions = {
  strategy: 'fixed',
  modifiers: [
    { name: 'flip', enabled: false },
    { name: 'preventOverflow', options: { boundary: [], rootBoundary: 'viewport', padding: 12, altAxis: true, tether: false } },
  ],
}
// 两侧都放不下完整列表时，选可用空间较大的一侧，列表内部滚动。
function fitToViewport() {
  if (!trigger.value) return
  const rect = trigger.value.getBoundingClientRect()
  const viewport = window.visualViewport
  const top = viewport?.offsetTop || 0
  const bottom = top + (viewport?.height || window.innerHeight)
  const below = bottom - rect.bottom
  const above = rect.top - top
  placement.value = below >= 490 || below >= above ? 'bottom-start' : 'top-start'
  // 面板内边距、标题、触发框间距和视口安全间距共预留 70px。
  listHeight.value = Math.max(0, Math.min(420, (placement.value === 'bottom-start' ? below : above) - 70))
}
function stopTracking() {
  window.removeEventListener('resize', fitToViewport)
  window.removeEventListener('scroll', fitToViewport, true)
  window.visualViewport?.removeEventListener('resize', fitToViewport)
  window.visualViewport?.removeEventListener('scroll', fitToViewport)
}
watch(open, visible => {
  stopTracking()
  if (!visible) return
  fitToViewport()
  window.addEventListener('resize', fitToViewport)
  window.addEventListener('scroll', fitToViewport, true)
  window.visualViewport?.addEventListener('resize', fitToViewport)
  window.visualViewport?.addEventListener('scroll', fitToViewport)
}, { flush: 'post' })
onBeforeUnmount(stopTracking)
const current = computed(() => props.fields.find(f => f.field_name === props.modelValue))
const multiple = computed(() => Array.isArray(props.modelValue))
const hasSelection = computed(() => multiple.value ? props.modelValue.length > 0 : !!current.value)
const selectionLabel = computed(() => multiple.value
  ? props.fields.filter(f => props.modelValue.includes(f.field_name)).map(f => f.label).join('、')
  : current.value?.label)
function pick(f) {
  if (multiple.value) {
    emit('update:modelValue', props.modelValue.includes(f.field_name)
      ? props.modelValue.filter(name => name !== f.field_name) : [...props.modelValue, f.field_name])
    return
  }
  open.value = false
  if (f.field_name !== props.modelValue) emit('update:modelValue', f.field_name)
}
</script>

<style scoped>
.tbfs { display: flex; align-items: center; gap: 8px; min-height: 36px; padding: 0 10px 0 12px; box-sizing: border-box;
  border-radius: 6px; box-shadow: 0 0 0 1px var(--el-border-color) inset; background: #fff; cursor: pointer; font-size: var(--st-font-size); }
.tbfs:hover { box-shadow: 0 0 0 1px var(--el-border-color-hover) inset; }
.tbfs.open { box-shadow: 0 0 0 1px var(--st-primary) inset; }
.tbfs.borderless { box-shadow: none !important; background: transparent; padding-left: 0; }
.tbfs-ico { color: var(--st-text-2); flex: none; }
.tbfs-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--st-text-2); }
.tbfs-label.ph { color: var(--el-text-color-placeholder); }
.tbfs-caret { flex: none; color: var(--st-text-3); }
.tbfs-clear { display: none; flex: none; color: var(--st-text-3); }
.tbfs:hover .tbfs-clear { display: inline-flex; }
.tbfs-clear:hover { color: var(--st-text-2); }
</style>
