<template>
  <div class="hc table-card" @click="go">
    <template v-if="table">
      <div class="tc-icon"><el-icon><Grid /></el-icon></div>
      <div class="tc-main">
        <div class="tc-name" :title="table.label">{{ table.label }}</div>
        <div class="tc-sub">
          <span v-if="config.show_count !== false">{{ table.record_count ?? 0 }} 条记录</span>
          <span v-if="!table.is_owner" class="tc-shared">共享</span>
        </div>
      </div>
    </template>
    <div v-else-if="invalid" class="hc-invalid">数据表已删除或无权访问</div>
    <div v-else class="hc-loading" v-loading="true" />
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
const tables = ref(null)

const table = computed(() =>
  (tables.value || []).find((t) => t.id === Number(props.config.table_id)) || null)
const invalid = computed(() => tables.value && !table.value)

async function reload() { tables.value = await loadTablesShared(true) }
onMounted(reload)
useAutoRefresh(() => props.config, reload)

function go() {
  if (table.value) router.push(`/t/${table.value.id}`)
}
</script>
