<template>
  <div>
    <div class="page-header"><h2>用户管理（全站）</h2></div>
    <!-- 搜索（客户端过滤 用户名/空间名） -->
    <div v-if="users.length > 10" class="users-filter">
      <el-input v-model="kw" placeholder="搜索用户名 / 空间名" clearable size="small" :prefix-icon="SearchIcon" style="width: 220px" />
      <span class="hint">{{ filtered.length }} 个用户</span>
    </div>
    <el-table :data="paged" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" width="160" />
      <el-table-column label="平台超管" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.is_platform_admin" type="danger" size="small">超管</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="工作空间 / 角色" min-width="320">
        <template #default="{ row }">
          <div v-for="t in row.tenants" :key="t.id" class="tenant-row">
            <span class="tenant-name">{{ t.name }}</span>
            <el-tag size="small" effect="plain" class="tenant-type">{{ typeLabel(t.type) }}</el-tag>
            <el-select
              :model-value="t.role" size="small" style="width: 150px"
              :disabled="t.status !== 'active'"
              @change="(v) => changeRole(row, t, v)"
            >
              <el-option v-for="r in roles" :key="r.code" :label="`${r.name}（${r.code}）`" :value="r.code" />
            </el-select>
            <el-tag v-if="t.status !== 'active'" size="small" type="info">{{ statusLabel(t.status) }}</el-tag>
          </div>
          <span v-if="!row.tenants?.length">—</span>
        </template>
      </el-table-column>
      <el-table-column label="注册时间" width="150" :formatter="(r) => fmtTime(r.created_at)" />
      <template #empty>暂无用户</template>
    </el-table>
    <el-pagination
      v-if="filtered.length > pageSize" v-model:current-page="page" :page-size="pageSize"
      :total="filtered.length" layout="total, prev, pager, next"
      style="margin-top: 12px; justify-content: flex-end"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search as SearchIcon } from '@element-plus/icons-vue'
import { listRoles, listUsers, setUserRole } from '../api'
import { fmtTime } from '../utils/format'

const users = ref([])
const roles = ref([])
const loading = ref(false)
const kw = ref('')
const page = ref(1)
const pageSize = 20

const typeLabel = (t) => ({ personal: '个人', enterprise: '企业', private: '私有化' }[t] || t)
// 成员状态中文（与组织与成员页一致，不裸显英文原值）
const statusLabel = (s) => ({ active: '已加入', invited: '待接受', disabled: '已停用' }[s] || s)

const filtered = computed(() => {
  const k = kw.value.trim().toLowerCase()
  if (!k) return users.value
  return users.value.filter((u) => u.username.toLowerCase().includes(k)
    || (u.tenants || []).some((t) => (t.name || '').toLowerCase().includes(k)))
})
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))

onMounted(async () => {
  loading.value = true
  try {
    const [u, r] = await Promise.all([listUsers(), listRoles()])
    users.value = u
    roles.value = r
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
})

async function changeRole(row, tenant, role) {
  try {
    await setUserRole(row.id, tenant.id, role)
    tenant.role = role
    ElMessage.success(`已将 ${row.username} 在「${tenant.name}」的角色调整为 ${role}`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>

<style scoped>
.users-filter { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.users-filter .hint { font-size: 12px; color: #909399; }
.tenant-row { display: flex; align-items: center; gap: 8px; padding: 2px 0; }
.tenant-name { min-width: 120px; }
.tenant-type { flex-shrink: 0; }
</style>
