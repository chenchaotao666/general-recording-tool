<template>
  <component :is="tag" class="st-list-item" :class="{ 'is-selected': selected, 'is-disabled': disabled }"
             :disabled="tag === 'button' ? disabled : undefined" :aria-disabled="disabled || undefined">
    <slot />
  </component>
</template>

<script setup>
// Keep native events/attributes on the root so drag sorting, checkboxes and
// nested actions can share the same row without changing their interaction.
defineProps({ tag: { type: String, default: 'div' }, selected: Boolean, disabled: Boolean })
</script>

<style scoped>
.st-list-item {
  display: flex; align-items: center; flex: none; gap: 8px;
  box-sizing: border-box; height: var(--st-list-item-height, 32px); min-height: var(--st-list-item-height, 32px);
  padding: 0 8px; border-radius: var(--st-radius-sm, 4px);
  font-size: var(--st-font-size, 14px); line-height: var(--st-line-height, 22px);
  color: var(--st-text-2, #646A73); cursor: pointer;
}
.st-list-item:hover, .st-list-item:focus-within { background: var(--st-bg-hover, #F2F3F5); }
.st-list-item.is-selected { color: var(--st-primary, #267EF0); background: var(--st-primary-weak, #E8F1FF); }
.st-list-item:focus-visible { outline: 2px solid var(--st-primary, #267EF0); outline-offset: -2px; }
.st-list-item.is-disabled { color: var(--st-disabled); cursor: not-allowed; }
.st-list-item.is-disabled:hover { background: transparent; }
</style>
