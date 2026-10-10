<template>
  <div>
    <div class="page-header">
      <h2>成员管理</h2>
      <el-button type="primary" @click="inviteVisible = true">邀请成员</el-button>
    </div>

    <el-alert
      v-if="seatTip" :type="seatTip.type" :closable="false" class="seat-tip" :title="seatTip.text" />

    <el-table :data="members" v-loading="loading" border>
      <el-table-column prop="username" label="用户名" min-width="140" />
      <el-table-column label="角色" width="200">
        <template #default="{ row }">
          <el-select
            :model-value="row.role" size="small" style="width: 170px"
            :disabled="row.user_id === ownerId"
            @change="(v) => changeRole(row, v)"
          >
            <el-option v-for="r in roles" :key="r.code" :label="`${r.name}（${r.code}）`" :value="r.code" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="{ active: 'success', invited: 'warning', disabled: 'info' }[row.status] || 'info'" size="small">
            {{ { active: '已加入', invited: '待接受', disabled: '已停用' }[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="加入时间" width="170" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button
            v-if="row.user_id !== ownerId" type="danger" link size="small"
            @click="remove(row)"
          >移除</el-button>
          <el-tag v-else size="small" effect="plain">所有者</el-tag>
        </template>
      </el-table-column>
      <template #empty>暂无成员</template>
    </el-table>

    <!-- 邀请 -->
    <el-dialog v-model="inviteVisible" title="邀请成员" width="420px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="inviteForm.username" placeholder="对方需已注册账号" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="inviteForm.role" style="width: 100%">
            <el-option v-for="r in roles" :key="r.code" :label="`${r.name}（${r.code}）`" :value="r.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inviteVisible = false">取消</el-button>
        <el-button type="primary" :loading="inviting" @click="invite">邀请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCurrentTenant, inviteMember, listMembers, listRoles, removeMember, setMemberRole } from '../api'

const members = ref([])
const roles = ref([])
const loading = ref(false)
const inviting = ref(false)
const inviteVisible = ref(false)
const inviteForm = reactive({ username: '', role: 'user' })
const tenant = ref(null)
const ownerId = ref(0)

const seatTip = computed(() => {
  const seats = tenant.value?.usage?.seats
  if (!seats?.limit) return null
  if (seats.percent >= 100) return { type: 'error', text: `席位已满（${seats.used}/${seats.limit}），邀请将进入宽限期或被拒绝，请升级套餐` }
  if (seats.percent >= 80) return { type: 'warning', text: `席位即将用完（${seats.used}/${seats.limit}）` }
  return { type: 'info', text: `席位：${seats.used}/${seats.limit}` }
})

async function load() {
  loading.value = true
  try {
    const [m, r, t] = await Promise.all([listMembers(), listRoles(), getCurrentTenant()])
    members.value = m
    roles.value = r
    tenant.value = t
    ownerId.value = t?.tenant?.owner_user_id || m.find((x) => x.role === 'admin' && x.status === 'active')?.user_id || 0
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function invite() {
  if (!inviteForm.username.trim()) return ElMessage.warning('请输入用户名')
  inviting.value = true
  try {
    await inviteMember(inviteForm.username.trim(), inviteForm.role)
    ElMessage.success('已发出邀请，对方接受后加入')
    inviteVisible.value = false
    inviteForm.username = ''
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    inviting.value = false
  }
}

async function changeRole(row, role) {
  try {
    await setMemberRole(row.id, role)
    row.role = role
    ElMessage.success('角色已调整')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定把 ${row.username} 移出本工作空间？其账号与数据不受影响。`, '移除成员', { type: 'warning' })
    await removeMember(row.id)
    ElMessage.success('已移除')
    load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
}
</script>

<style scoped>
.seat-tip { margin-bottom: 12px; }
</style>
