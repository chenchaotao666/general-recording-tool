<template>
  <div>
    <div class="page-header"><h2>用户管理（全站）</h2></div>
    <el-table :data="users" v-loading="loading" border>
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
            <el-tag v-if="t.status !== 'active'" size="small" type="info">{{ t.status }}</el-tag>
          </div>
          <span v-if="!row.tenants?.length">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="注册时间" width="170" />
      <template #empty>暂无用户</template>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listRoles, listUsers, setUserRole } from '../api'

const users = ref([])
const roles = ref([])
const loading = ref(false)

const typeLabel = (t) => ({ personal: '个人', enterprise: '企业', private: '私有化' }[t] || t)

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
.tenant-row { display: flex; align-items: center; gap: 8px; padding: 2px 0; }
.tenant-name { min-width: 120px; }
.tenant-type { flex-shrink: 0; }
</style>
