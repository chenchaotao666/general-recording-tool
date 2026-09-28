<template>
  <div class="share-page" v-loading="loading">
    <!-- 密码验证 -->
    <el-card v-if="needPassword" class="pwd-card">
      <div class="title">此内容受密码保护</div>
      <el-input v-model="password" type="password" show-password placeholder="请输入访问密码" @keyup.enter="load" />
      <el-button type="primary" style="width: 100%; margin-top: 12px" @click="load">访问</el-button>
      <div v-if="error" class="error">{{ error }}</div>
    </el-card>

    <template v-else-if="data">
      <!-- 表 -->
      <template v-if="data.resource_type === 'table'">
        <div class="page-header">
          <h2>{{ data.label }}</h2>
          <span class="total">共 {{ data.total }} 条</span>
        </div>
        <el-table :data="data.records" border stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column
            v-for="f in data.fields" :key="f.field_name"
            :prop="f.field_name" :label="f.label" show-overflow-tooltip min-width="110"
          >
            <template #default="{ row }">{{ fmt(f, row[f.field_name]) }}</template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="data.total > data.page_size"
          v-model:current-page="page" :page-size="data.page_size" :total="data.total"
          layout="prev, pager, next" style="margin-top: 14px" @current-change="load"
        />
      </template>

      <!-- 报表 -->
      <template v-else>
        <div class="page-header"><h2>{{ data.label }}</h2></div>
        <div class="meta">{{ data.report.range.label }} · 生成于 {{ data.report.generated_at }}</div>
        <ReportDashboard :blocks="data.report.blocks" :layout="data.report.layout" :filterable="false" />
      </template>
    </template>

    <el-result v-else-if="error" icon="warning" :title="error" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ReportDashboard from '../components/ReportDashboard.vue'

const route = useRoute()
const token = route.params.token

const loading = ref(false)
const needPassword = ref(false)
const password = ref('')
const error = ref('')
const data = ref(null)
const page = ref(1)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ page: page.value, page_size: 50 })
    if (password.value) params.set('password', password.value)
    const res = await fetch(`/api/share/${token}?${params}`)
    if (res.status === 401) {
      needPassword.value = true
      return
    }
    if (!res.ok) {
      const d = await res.json().catch(() => ({}))
      error.value = d.detail || `加载失败（${res.status}）`
      return
    }
    needPassword.value = false
    data.value = await res.json()
  } catch (e) {
    error.value = '无法连接服务器'
  } finally {
    loading.value = false
  }
}

function fmt(f, val) {
  if (val === null || val === undefined || val === '') return '—'
  if (f.data_type === 'bool') return val ? '是' : '否'
  if (f.widget === 'select') {
    const opts = f.options?.options || []
    const hit = opts.find((o) => (typeof o === 'object' ? o.value : o) === val)
    return typeof hit === 'object' ? hit.label : (hit ?? val)
  }
  return String(val)
}

onMounted(load)
</script>

<style scoped>
.share-page { max-width: 1200px; margin: 0 auto; padding: 24px; }
.pwd-card { max-width: 360px; margin: 120px auto; text-align: center; }
.pwd-card .title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.error { color: #f56c6c; font-size: 13px; margin-top: 12px; }
.total { color: #909399; font-size: 13px; }
.meta { color: #909399; font-size: 12px; margin-bottom: 14px; }
.block { margin-bottom: 16px; }
</style>
