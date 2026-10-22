<template>
  <!-- 排序方向两段切换（对齐参照 表格上方按钮/排序.png）：选中段白底描边，未选段浅灰底 -->
  <span class="dt">
    <span class="dt-seg" :class="{ on: modelValue !== 'desc' }" @click="emit('update:modelValue', 'asc')">{{ labels[0] }}</span>
    <span class="dt-seg" :class="{ on: modelValue === 'desc' }" @click="emit('update:modelValue', 'desc')">{{ labels[1] }}</span>
  </span>
</template>

<script setup>
defineProps({ modelValue: { type: String, default: 'asc' }, labels: { type: Array, default: () => ['A → Z', 'Z → A'] } })
const emit = defineEmits(['update:modelValue'])
</script>

<style scoped>
.dt { display: inline-flex; background: #F2F3F5; border-radius: 6px; flex: none; }
.dt-seg { min-width: 108px; height: 36px; box-sizing: border-box; padding: 0 12px; display: inline-flex; align-items: center; justify-content: center;
          font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; border-radius: 6px; border: 1px solid transparent; white-space: nowrap; }
.dt-seg.on { background: #fff; border-color: var(--st-border); }
.dt-seg:not(.on):hover { background: #E8E9EB; }
</style>
