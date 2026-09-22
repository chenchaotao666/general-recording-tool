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
        <template v-for="b in data.report.blocks" :key="b.id">
          <el-card v-if="b.type === 'stat'" class="block" shadow="never">
            <div class="stat-title">{{ b.title }}</div>
            <div class="stat-value">{{ b.value }}</div>
          </el-card>
          <el-card v-else-if="b.type === 'chart'" class="block" shadow="never">
            <div class="block-title">{{ b.title }}</div>
            <div v-for="(l, i) in b.labels" :key="i" class="bar-row">
              <span class="bar-label">{{ l }}</span>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: barWidth(b.values, i) }" />
              </div>
              <span class="bar-value">{{ b.values[i] }}</span>
            </div>
          </el-card>
          <el-card v-else-if="b.type === 'table'" class="block" shadow="never">
            <div class="block-title">{{ b.title }}</div>
            <el-table :data="b.rows" size="small" border>
              <el-table-column
                v-for="c in b.columns" :key="c.prop" :prop="c.prop" :label="c.label" show-overflow-tooltip
              />
            </el-table>
          </el-card>
          <el-card v-else-if="b.type === 'text'" class="block" shadow="never">
            <div class="text-block">{{ b.content }}</div>
          </el-card>
        </template>
      </template>
    </template>

    <el-result v-else-if="error" icon="warning" :title="error" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

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

function barWidth(values, i) {
  const max = Math.max(...values.map((v) => Number(v) || 0), 1)
  return `${Math.round(((Number(values[i]) || 0) / max) * 100)}%`
}

onMounted(load)
</script>

<style scoped>
.share-page { max-width: 960px; margin: 0 auto; padding: 24px; }
.pwd-card { max-width: 360px; margin: 120px auto; text-align: center; }
.pwd-card .title { font-size: 18px; font-weight: 600; margin-bottom: 16px; }
.error { color: #f56c6c; font-size: 13px; margin-top: 12px; }
.total { color: #909399; font-size: 13px; }
.meta { color: #909399; font-size: 12px; margin-bottom: 14px; }
.block { margin-bottom: 16px; }
.stat-title { font-size: 13px; color: #909399; }
.stat-value { font-size: 30px; font-weight: 600; margin-top: 4px; }
.block-title { font-weight: 600; margin-bottom: 12px; }
.bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.bar-label { width: 140px; font-size: 13px; color: #606266; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1; background: #f0f2f5; border-radius: 4px; height: 16px; }
.bar-fill { background: #409eff; height: 100%; border-radius: 4px; min-width: 2px; }
.bar-value { width: 70px; text-align: right; font-size: 13px; }
.text-block { white-space: pre-wrap; line-height: 1.7; color: #606266; }
</style>
