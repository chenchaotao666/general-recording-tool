<template>
  <!-- 字段类型图标：统一代理到 StIcon（fieldIcons.js 单一数据源，差距文档 §1.1 三套并存治理） -->
  <StIcon :name="fieldIconName(field)" :size="15" class="ft-icon" />
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import StIcon from '../icons/StIcon.vue'

defineProps({ field: { type: Object, required: true } })
</script>

<style scoped>
.ft-icon { color: var(--st-text-2); }
</style>
