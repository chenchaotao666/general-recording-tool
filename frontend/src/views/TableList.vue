<template>
  <div>
    <div class="page-header">
      <h2>数据表</h2>
      <el-button type="primary" :icon="Upload" @click="$router.push('/import')">导入 Excel 建表</el-button>
    </div>

    <el-empty v-if="!loading && tables.length === 0" description="还没有数据表，点击右上角导入 Excel 开始" />

    <el-row :gutter="16" v-loading="loading">
      <el-col v-for="t in tables" :key="t.id" :span="8" style="margin-bottom: 16px">
        <el-card shadow="hover">
          <div class="card-title">{{ t.label }}</div>
          <div class="card-sub">{{ t.name }} · {{ t.record_count }} 条记录</div>
          <div class="card-sub">创建于 {{ t.created_at }}</div>
          <div style="margin-top: 12px">
            <el-button type="primary" @click="$router.push(`/t/${t.id}`)">打开</el-button>
            <el-popconfirm title="将删除该表及全部数据，确定？" width="240" @confirm="del(t)">
              <template #reference>
                <el-button type="danger" text>删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { deleteTable, listTables } from '../api'

const tables = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    tables.value = await listTables()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function del(t) {
  try {
    await deleteTable(t.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.card-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
.card-sub { font-size: 12px; color: #909399; margin-top: 4px; }
</style>
