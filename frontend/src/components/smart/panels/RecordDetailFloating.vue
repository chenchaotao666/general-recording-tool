<template>
  <Teleport to="body">
    <section v-if="visible" class="record-detail-floating" :style="{ zIndex }" role="dialog" aria-modal="false" aria-label="记录详情" @mousedown.stop @click.stop>
      <header class="floating-header">
        <span class="floating-source">来自 <StIcon name="table" :size="14" /> {{ source }}</span>
        <nav class="floating-nav" aria-label="记录导航">
          <button class="floating-action" aria-label="上一条" data-smart-tip="上一条" :disabled="!hasPrev" @click="$emit('nav', -1)"><StIcon name="chevron-up" :size="16" /></button>
          <button class="floating-action" aria-label="下一条" data-smart-tip="下一条" :disabled="!hasNext" @click="$emit('nav', 1)"><StIcon name="chevron-down" :size="16" /></button>
          <span class="floating-divider" />
          <button class="floating-action" aria-label="关闭详情" data-smart-tip="关闭" @click="$emit('close')"><StIcon name="close" :size="16" /></button>
        </nav>
      </header>
      <RecordDetailContent v-bind="$attrs" />
    </section>
  </Teleport>
</template>
<script setup>
import { ref, watch } from 'vue'
import { useZIndex } from 'element-plus'
import RecordDetailContent from './RecordDetailContent.vue'
import StIcon from '../icons/StIcon.vue'
defineOptions({ inheritAttrs: false })
const props = defineProps({ visible: Boolean, source: String, hasPrev: Boolean, hasNext: Boolean })
defineEmits(['close', 'nav'])
const { nextZIndex } = useZIndex()
const zIndex = ref(0)
watch(() => props.visible, visible => { if (visible) zIndex.value = nextZIndex() }, { immediate: true })
</script>
<style scoped>
.record-detail-floating { position: fixed; left: 50%; top: 50%; transform: translate(-50%, -50%); display: flex; flex-direction: column; box-sizing: border-box; width: 560px; max-width: calc(100vw - 32px); height: min(800px, calc(100dvh - 32px)); padding: 0 16px 12px; background: #fff; border: 1px solid #e4e7ed; border-radius: 9px; box-shadow: 0 8px 36px #0003; overflow: hidden; }
.floating-header { height: 44px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex: none; border-bottom: 1px solid var(--st-border); }
.floating-source { display: flex; align-items: center; gap: 5px; min-width: 0; color: #30343b; font-size: 12px; }
.floating-nav { display: flex; align-items: center; gap: 4px; flex: none; }
.floating-action { width: 30px; height: 30px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 4px; background: transparent; color: #30343b; cursor: pointer; }
.floating-action:hover:not(:disabled) { background: #e6e8e8; }
.floating-action:disabled { color: #bdc2ca; cursor: default; }
.floating-divider { height: 16px; width: 1px; margin: 0 6px; background: #eceef1; }
</style>
