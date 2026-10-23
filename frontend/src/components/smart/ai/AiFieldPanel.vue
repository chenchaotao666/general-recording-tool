<template>
  <AiFieldEditor v-bind="$attrs" />
</template>

<script setup>
// Creation and editing share one form and one floating panel.
import AiFieldEditor from './AiFieldEditor.vue'
defineOptions({ inheritAttrs: false })
</script>
