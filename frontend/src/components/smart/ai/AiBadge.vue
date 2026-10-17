<template>
  <!-- AI 字段角标（参照图「AI✦」）：紫→粉渐变小胶囊；plain = 标题旁的灰字版 -->
  <span class="aib" :class="{ plain }">AI<svg viewBox="0 0 10 10" width="8" height="8"><path d="M5 0l1.2 3.8L10 5 6.2 6.2 5 10 3.8 6.2 0 5l3.8-1.2z" fill="currentColor" /></svg></span>
</template>

<script setup>
defineProps({ plain: { type: Boolean, default: false } })
</script>

<style scoped>
.aib { display: inline-flex; align-items: center; gap: 1px; flex: none; height: 16px; padding: 0 4px; border-radius: 4px;
       background: linear-gradient(90deg, #8B6CF6, #E96BD8); color: #fff; font-size: 11px; font-weight: 700; line-height: 1;
       letter-spacing: .2px; font-family: Arial, sans-serif; }
.aib.plain { background: none; color: #A8ADB5; font-size: 14px; height: auto; padding: 0; font-weight: 600; }
.aib.plain svg { width: 10px; height: 10px; }
</style>
