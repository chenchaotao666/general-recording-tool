<template>
  <div>
    <div class="page-header"><h2>用户管理</h2></div>
    <el-table :data="users" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" width="180" />
      <el-table-column label="角色" width="200">
        <template #default="{ row }">
          <el-select
            :model-value="row.role" style="width: 160px"
            :disabled="row.id === myId"
            @change="(v) => changeRole(row, v)"
          >
            <el-option v-for="r in roles" :key="r.code" :label="`${r.name}（${r.code}）`" :value="r.code" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="注册时间" min-width="160" />
      <template #empty>暂无用户</template>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listRoles, listUsers, setUserRole } from '../api'

const myId = JSON.parse(localStorage.getItem('grt_user') || '{}').id
const users = ref([])
const roles = ref([])
const loading = ref(false)

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

async function changeRole(row, role) {
  try {
    await setUserRole(row.id, role)
    row.role = role
    ElMessage.success(`已将 ${row.username} 调整为 ${role}`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>
