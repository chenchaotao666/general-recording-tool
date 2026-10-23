<template>
  <div class="st-control st-control--native st-multi-trigger" :class="{ open }" role="button" tabindex="0"
       :aria-expanded="open" :aria-label="placeholder" @keydown.enter.prevent="emit('toggle')" @keydown.space.prevent="emit('toggle')">
    <div ref="content" class="smt-content">
      <span v-if="!items.length" class="smt-placeholder">{{ placeholder }}</span>
      <span v-for="item in items.slice(0, visibleCount)" :key="item.value" class="smt-tag" :style="item.style">
        <span class="smt-label">{{ item.label }}</span>
        <button type="button" class="smt-close" :aria-label="`移除${item.label}`" @click.stop="emit('remove', item.value)" @keydown.stop>×</button>
      </span>
      <span v-if="hiddenCount" class="smt-tag smt-count" :title="items.slice(visibleCount).map(item => item.label).join('、')">+{{ hiddenCount }}</span>
    </div>
    <SmartSelectArrow :open="open" />
    <div ref="measure" class="smt-measure" aria-hidden="true">
      <span v-for="item in items" :key="item.value" class="smt-tag"><span class="smt-label">{{ item.label }}</span><span class="smt-close">×</span></span>
      <span v-for="n in items.length" :key="`count-${n}`" class="smt-tag smt-count">+{{ n }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SmartSelectArrow from './SmartSelectArrow.vue'
const props = defineProps({ items: { type: Array, default: () => [] }, open: Boolean, placeholder: { type: String, default: '请选择' } })
const emit = defineEmits(['remove', 'toggle'])
const content = ref(null), measure = ref(null), visibleCount = ref(0)
const hiddenCount = computed(() => props.items.length - visibleCount.value)
let observer
function fit() {
  if (!content.value || !measure.value) return
  const available = content.value.clientWidth
  const nodes = measure.value.children, length = props.items.length
  let used = 0, count = 0
  for (let i = 0; i < length; i++) {
    used += nodes[i].getBoundingClientRect().width + (i ? 4 : 0)
    const remaining = length - i - 1
    const extra = remaining ? 4 + nodes[length + remaining - 1].getBoundingClientRect().width : 0
    if (used + extra <= available) count = i + 1
  }
  visibleCount.value = count
}
watch(() => props.items, async () => { await nextTick(); fit() }, { deep: true })
onMounted(() => { fit(); observer = new ResizeObserver(fit); observer.observe(content.value) })
onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.st-multi-trigger { position: relative; display: flex; align-items: center; gap: 8px; padding-inline: 8px !important; min-width: 0; cursor: pointer; }
.smt-content { display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; overflow: hidden; }
.smt-tag { display: inline-flex; align-items: center; gap: 4px; flex: none; box-sizing: border-box; height: 24px; padding: 0 6px; border-radius: 4px; background: var(--st-bg-hover); color: var(--st-text-2); font-size: var(--st-font-size); line-height: 22px; white-space: nowrap; }
.smt-close { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 12px; width: 12px; height: 18px; border: 0; padding: 0; color: inherit; background: transparent; font: inherit; cursor: pointer; }
.smt-close:hover { opacity: .65; }
.smt-placeholder { color: var(--el-text-color-placeholder); }
.smt-measure { position: absolute; visibility: hidden; pointer-events: none; display: flex; width: max-content; height: 0; overflow: hidden; }
</style>
