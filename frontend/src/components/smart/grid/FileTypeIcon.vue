<template><span class="file-type-icon" :style="{ background: kind.color, fontSize: kind.text.length > 1 ? '9px' : undefined }">{{ kind.text }}</span></template>
<script setup>
import { computed } from 'vue'
import { fileKind } from './fileDisplay.js'
const props = defineProps({ file: Object })
const kind = computed(() => fileKind(props.file))
</script>
<style scoped>
.file-type-icon { display: inline-flex; flex: none; width: 18px; height: 18px; border-radius: 3px; align-items: center; justify-content: center; color: white; font-size: 11px; font-weight: 600; }
</style>
