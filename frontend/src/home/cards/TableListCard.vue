<template>
  <div class="hc table-list-card">
    <div v-if="rows === null" class="hc-loading" v-loading="true" />
    <template v-else>
      <div
        v-for="t in rows" :key="t.id" class="tlc-row"
        @click="router.push(`/t/${t.id}`)"
      >
        <el-icon class="tlc-icon"><Grid /></el-icon>
        <span class="tlc-name" :title="t.label">{{ t.label }}</span>
        <span class="tlc-count">{{ t.record_count ?? 0 }}</span>
      </div>
      <div v-if="!rows.length" class="hc-empty">暂无数据表</div>
      <div v-if="more > 0" class="tlc-more" @click="router.push('/tables')">
        查看全部 {{ total }} 张 →
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Grid } from '@element-plus/icons-vue'
import { loadTablesShared } from '../tableCache'
import { useAutoRefresh } from '../useAutoRefresh'

const props = defineProps({
  config: { type: Object, default: () => ({}) },
})
const router = useRouter()
const all = ref(null)

const limit = computed(() => Number(props.config.limit) || 6)
const rows = computed(() => (all.value || []).slice(0, limit.value))
const total = computed(() => (all.value || []).length)
const more = computed(() => total.value - limit.value)

async function reload() { all.value = await loadTablesShared(true) }
onMounted(reload)
useAutoRefresh(() => props.config, reload)
</script>
