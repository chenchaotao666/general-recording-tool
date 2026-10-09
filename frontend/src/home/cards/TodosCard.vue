<template>
  <div class="hc list-card">
    <div v-if="rows === null" class="hc-loading" v-loading="true" />
    <template v-else>
      <div
        v-for="t in rows" :key="t.node_run_id" class="lc-row"
        @click="router.push(`/workflows/runs/${t.run_id}`)"
      >
        <el-icon class="lc-todo-icon"><Clock /></el-icon>
        <span class="lc-title" :title="t.title">{{ t.title }}</span>
        <span class="lc-wf">{{ t.workflow_name }}</span>
      </div>
      <div v-if="!rows.length" class="hc-empty">没有待办事项，很好</div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Clock } from '@element-plus/icons-vue'
import { listPendingApprovals } from '../../api'
import { useAutoRefresh } from '../useAutoRefresh'

const props = defineProps({
  config: { type: Object, default: () => ({}) },
})
const router = useRouter()
const all = ref(null)
const rows = computed(() => (all.value || []).slice(0, Number(props.config.limit) || 5))

async function reload() {
  try { all.value = await listPendingApprovals() } catch { all.value = [] }
}
onMounted(reload)
useAutoRefresh(() => props.config, reload)
</script>
