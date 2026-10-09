<template>
  <div class="hc menu-card" @click="go">
    <template v-if="entry">
      <div class="mc-icon"><el-icon :size="22"><component :is="entry.icon" /></el-icon></div>
      <div class="tc-main">
        <div class="tc-name">{{ entry.title }}</div>
        <div class="tc-sub">{{ entry.desc }}</div>
      </div>
    </template>
    <div v-else class="hc-invalid">功能不可用（无权限或已下线）</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { menuEntriesFor } from '../cardTypes'

const props = defineProps({
  config: { type: Object, default: () => ({}) },
})
const router = useRouter()
const user = JSON.parse(localStorage.getItem('grt_user') || 'null')

const entry = computed(() =>
  menuEntriesFor(user).find((e) => e.path === props.config.path) || null)

function go() {
  if (entry.value) router.push(entry.value.path)
}
</script>
