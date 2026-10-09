<template>
  <div class="hc list-card">
    <div v-if="rows === null" class="hc-loading" v-loading="true" />
    <template v-else>
      <div
        v-for="n in rows" :key="n.id" class="lc-row" :class="{ unread: !n.read }"
        @click="open(n)"
      >
        <span class="lc-dot" />
        <span class="lc-title" :title="n.title">{{ n.title }}</span>
        <span class="lc-time">{{ shortTime(n.created_at) }}</span>
      </div>
      <div v-if="!rows.length" class="hc-empty">暂无通知</div>
      <div class="lc-more" @click="router.push('/notifications')">全部通知 →</div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listNotifications } from '../../api'
import { useAutoRefresh } from '../useAutoRefresh'

const props = defineProps({
  config: { type: Object, default: () => ({}) },
})
const router = useRouter()
const all = ref(null)
const rows = computed(() => (all.value || []).slice(0, Number(props.config.limit) || 5))

async function reload() {
  try { all.value = await listNotifications() } catch { all.value = [] }
}
onMounted(reload)
useAutoRefresh(() => props.config, reload)

function open(n) {
  router.push(n.link || '/notifications')
}

function shortTime(t) {
  return (t || '').slice(5, 16)   // "2026-10-09 08:30:00" → "10-09 08:30"
}
</script>
