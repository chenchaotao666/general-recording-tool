<template>
  <span ref="box" class="compact-cell-tags" :class="{ 'has-more': hiddenCount > 0 }">
    <span v-for="tag in visibleTags" :key="tag.key" class="compact-tag" :style="tag.style" :class="{ raw: tag.raw }">
      <StIcon v-if="tag.icon" :name="tag.icon" :size="14" /><span class="compact-label">{{ tag.label }}</span>
    </span>
    <span v-if="hiddenCount" class="compact-more">+{{ hiddenCount }}</span>
    <span ref="ghost" class="compact-more compact-ghost">+99</span>
  </span>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
const props = defineProps({ tags: { type: Array, default: () => [] } })
const box = ref(), ghost = ref(), count = ref(Infinity)
const visibleTags = computed(() => props.tags.slice(0, count.value))
const hiddenCount = computed(() => Math.max(0, props.tags.length - visibleTags.value.length))
let observer, revision = 0
function countFit(tags, width) {
  let used = 0, fit = 0
  for (const tag of tags) {
    used += Math.min(tag.scrollWidth, width) + (fit ? 4 : 0)
    if (used > width + 1) break
    fit++
  }
  return fit
}
async function measure() {
  const current = ++revision
  count.value = Infinity
  await nextTick()
  if (!box.value || current !== revision) return
  const tags = [...box.value.querySelectorAll('.compact-tag')]
  if (countFit(tags, box.value.clientWidth) >= tags.length) return
  count.value = Math.max(1, countFit(tags, box.value.clientWidth - (ghost.value?.offsetWidth || 24) - 4))
}
onMounted(() => { measure(); observer = new ResizeObserver(measure); observer.observe(box.value) })
watch(() => props.tags, measure, { deep: true })
onBeforeUnmount(() => { revision++; observer?.disconnect() })
</script>
<style scoped>
.compact-cell-tags { position: relative; display: flex; align-items: center; gap: 4px; flex-wrap: nowrap; overflow: hidden; max-height: 22px; width: 100%; min-width: 0; }
.compact-tag { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; max-width: 100%; flex: none; }
.compact-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.compact-cell-tags.has-more .compact-tag { max-width: calc(100% - 32px); }
.compact-tag.raw { background: var(--el-fill-color-light); color: var(--el-text-color-regular); border: 1px dashed var(--el-border-color); }
.compact-more { flex: none; color: var(--el-text-color-secondary); font-size: 12px; white-space: nowrap; }
.compact-ghost { position: absolute; visibility: hidden; pointer-events: none; }
</style>
