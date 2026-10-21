<template>
  <span class="person-avatar"><img v-if="person.avatar && !failed" :src="person.avatar" alt="" @error="failed = true" /><span v-else>{{ person.name?.slice(0, 1) || '?' }}</span></span>
</template>
<script setup>
import { ref } from 'vue'
defineProps({ person: { type: Object, required: true } })
const failed = ref(false)
</script>
<style scoped>
.person-avatar { display: inline-flex; flex: none; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 4px; background: #e4edff; color: #3978da; font-size: 14px; overflow: hidden; }
.person-avatar img { width: 100%; height: 100%; object-fit: cover; }
</style>
