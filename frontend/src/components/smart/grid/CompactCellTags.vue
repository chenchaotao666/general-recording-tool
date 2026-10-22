<template>
  <span ref="box" class="compact-cell-tags" :style="{ maxHeight: expanded ? 'none' : `${availableHeight}px` }">
    <span v-for="(row, rowIndex) in displayedRows" :key="rowIndex" class="compact-row">
      <span v-for="item in row" :key="tags[item.index].key" class="compact-tag" :style="[tags[item.index].style, item.width == null ? {} : { maxWidth: `${item.width}px` }]" :class="{ raw: tags[item.index].raw }" @click="$emit('tag-click', tags[item.index], $event)">
        <slot name="tag" :tag="tags[item.index]">
          <PersonAvatar v-if="tags[item.index].person" :person="tags[item.index].person" class="compact-avatar" /><StIcon v-else-if="tags[item.index].icon" :name="tags[item.index].icon" :size="14" /><span class="compact-label">{{ tags[item.index].label }}</span>
        </slot>
      </span>
      <span v-if="hiddenCount && rowIndex === displayedRows.length - 1" class="compact-more">+{{ hiddenCount }}</span>
    </span>
    <span v-if="tags.length > 1" ref="ghost" class="compact-more compact-ghost">+99</span>
  </span>
</template>
<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createGridLayoutQueue } from '../../../smart/utils/gridLayoutQueue.js'
import StIcon from '../icons/StIcon.vue'
import PersonAvatar from '../../people/PersonAvatar.vue'
import { fitTagRows } from '../../../smart/utils/tagRows.js'
const props = defineProps({ tags: { type: Array, default: () => [] }, stacked: Boolean, expanded: Boolean })
defineEmits(['tag-click'])
const availableHeight = inject('smartCellTagHeight', ref(24))
const box = ref(), ghost = ref(), layout = ref(null)
const displayedRows = computed(() => layout.value || [props.tags.map((_, index) => ({ index }))])
const hiddenCount = computed(() => Math.max(0, props.tags.length - displayedRows.value.flat().length))
const layoutQueue = inject('smartGridLayoutQueue', null) || createGridLayoutQueue()
const tagSignature = computed(() => JSON.stringify(props.tags))
let stopObserving, revision = 0, knownWidth = 0
function cacheKey(width) {
  return JSON.stringify([tagSignature.value, width, availableHeight.value, props.stacked, props.expanded])
}
function restoreLayout(width) {
  const cached = width > 0 && layoutQueue.getTagLayout(cacheKey(width))
  if (!cached) return false
  revision++
  layout.value = cached
  layoutQueue.cancel(measure)
  return true
}
async function measure() {
  if (layoutQueue.paused) { layoutQueue.enqueue(measure); return }
  if (!box.value) return
  knownWidth = box.value.clientWidth
  if (!knownWidth || restoreLayout(knownWidth)) return
  const current = ++revision
  layout.value = null
  await nextTick()
  if (!box.value || current !== revision) return
  if (layoutQueue.paused) { layoutQueue.enqueue(measure); return }
  const tags = [...box.value.querySelectorAll('.compact-tag')]
  if (!box.value.clientWidth) return
  knownWidth = box.value.clientWidth
  layout.value = fitTagRows(tags.map(tag => tag.getBoundingClientRect().width), knownWidth, props.expanded ? Math.max(24, tags.length * 28) : availableHeight.value,
    { stacked: props.stacked, badgeWidth: ghost.value?.offsetWidth || 28 })
  layoutQueue.setTagLayout(cacheKey(knownWidth), layout.value)
}
function scheduleMeasure() {
  if (props.tags.length <= 1) {
    revision++
    layoutQueue.cancel(measure)
    layout.value = null
    stopObserving?.(); stopObserving = null
    return
  }
  if (!stopObserving && box.value) stopObserving = layoutQueue.observeWidth(box.value, width => {
    knownWidth = Math.round(width)
    scheduleMeasure()
  })
  if (restoreLayout(knownWidth)) return
  layoutQueue.enqueue(measure)
}
onMounted(scheduleMeasure)
watch(() => props.tags, () => { layout.value = null; scheduleMeasure() }, { deep: true })
watch([availableHeight, () => props.stacked, () => props.expanded], scheduleMeasure)
onBeforeUnmount(() => { revision++; layoutQueue.cancel(measure); stopObserving?.() })
</script>
<style scoped>
.compact-cell-tags { position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 4px; overflow: hidden; width: 100%; min-width: 0; }
.compact-row { display: flex; align-items: center; gap: 4px; width: 100%; min-width: 0; height: 24px; flex: none; }
.compact-tag { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px 1px 4px; box-sizing: border-box; height: 24px; line-height: 22px; border-radius: 4px; font-size: var(--st-font-size); white-space: nowrap; overflow: hidden; max-width: 100%; flex: none; }
.compact-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.compact-avatar { width: 20px; height: 20px; font-size: var(--st-font-size); }
.compact-tag.raw { background: var(--el-fill-color-light); color: var(--el-text-color-regular); border: 1px dashed var(--el-border-color); }
.compact-more { flex: none; color: var(--el-text-color-secondary); font-size: var(--st-font-size); white-space: nowrap; }
.compact-ghost { position: absolute; visibility: hidden; pointer-events: none; }
</style>
