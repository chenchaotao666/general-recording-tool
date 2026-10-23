<template>
  <span class="st-control-caret" :class="{ 'is-reverse': open }" aria-hidden="true" />
</template>

<script setup>
defineProps({ open: Boolean })
</script>
