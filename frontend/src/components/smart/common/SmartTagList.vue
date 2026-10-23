<template>
  <div class="st-tag-list">
    <span v-if="!items.length" class="st-tag-list__placeholder">{{ placeholder }}</span>
    <span v-for="item in items" :key="item.value" class="st-tag-list__item" @click.stop>
      <span class="st-tag-list__label" :title="item.label">{{ item.label }}</span>
      <button v-if="closable" type="button" class="st-tag-list__close" :aria-label="`移除${item.label}`"
              @click.stop="$emit('remove', item.value)" @keydown.stop>
        <StIcon name="close" :size="12" />
      </button>
    </span>
  </div>
</template>

<script setup>
import StIcon from '../icons/StIcon.vue'
defineProps({
  items: { type: Array, default: () => [] }, // { value, label }
  placeholder: { type: String, default: '请选择' },
  closable: { type: Boolean, default: true },
})
defineEmits(['remove'])
</script>

<style scoped>
.st-tag-list { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; flex: 1; min-width: 0; }
.st-tag-list__item { display: inline-flex; align-items: center; gap: 4px; flex: 0 1 auto; min-width: 0; max-width: 100%; height: 24px; box-sizing: border-box; padding: 0 6px; border: 1px solid var(--st-border); border-radius: 4px; background: var(--st-bg-hover); color: var(--st-text-2); font-size: var(--st-font-size); line-height: 22px; }
.st-tag-list__label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st-tag-list__close { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 16px; width: 16px; height: 16px; padding: 0; border: none; border-radius: 3px; background: transparent; color: inherit; cursor: pointer; }
.st-tag-list__close:hover { background: var(--st-button-gray-hover); }
.st-tag-list__close:focus-visible { outline: 1px solid var(--st-primary); }
.st-tag-list__placeholder { color: var(--el-text-color-placeholder); font-size: var(--st-font-size); line-height: 24px; }
</style>
