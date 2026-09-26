<template>
  <div>
    <div class="page-header">
      <h2>好友</h2>
    </div>

    <!-- 添加好友：admin 可搜索全站用户下拉选择；普通用户输入完整用户名 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <div style="display: flex; gap: 10px; align-items: center">
        <el-select
          v-if="isAdmin" v-model="addUserId" filterable remote :remote-method="searchAll"
          :loading="searching" placeholder="搜索用户名，添加好友" style="width: 260px"
        >
          <el-option v-for="u in userOptions" :key="u.id" :label="u.username" :value="u.id" />
        </el-select>
        <el-input
          v-else v-model="addUsername" placeholder="输入完整用户名，添加好友" style="width: 260px"
          @keyup.enter="addFriend"
        />
        <el-button type="primary" :loading="adding" @click="addFriend">发送申请</el-button>
        <span style="color: #909399; font-size: 12px">对方接受后成为好友，之后才能互相分享数据表</span>
      </div>
    </el-card>

    <el-tabs v-model="tab">
      <el-tab-pane :label="`我的好友（${friends.length}）`" name="friends">
        <el-table :data="friends" size="small" border>
          <el-table-column label="用户名" prop="username" min-width="160" />
          <el-table-column label="成为好友时间" prop="since" width="180" />
          <el-table-column label="操作" width="100" align="center">
            <template #default="{ row }">
              <el-popconfirm title="删除后不再能互相分享，确定？" width="220" @confirm="removeFriend(row)">
                <template #reference>
                  <el-button text type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!friends.length" description="还没有好友，搜索用户名发送申请" :image-size="70" />
      </el-tab-pane>

      <el-tab-pane name="requests">
        <template #label>
          收到的申请
          <el-badge v-if="requests.length" :value="requests.length" style="margin-left: 6px" />
        </template>
        <el-table :data="requests" size="small" border>
          <el-table-column label="用户名" prop="username" min-width="160" />
          <el-table-column label="申请时间" prop="created_at" width="180" />
          <el-table-column label="操作" width="130" align="center">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="respond(row, 'accept')">接受</el-button>
              <el-button text type="danger" size="small" @click="respond(row, 'reject')">拒绝</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!requests.length" description="暂无待处理的申请" :image-size="70" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  acceptFriend, deleteFriend, listFriendRequests, listFriends,
  rejectFriend, requestFriend, searchUsers,
} from '../api'

// 全站用户搜索下拉仅 admin 可用（后端 /users/search scope=all 也只对 admin 开放）
const isAdmin = computed(() => JSON.parse(localStorage.getItem('grt_user') || 'null')?.role === 'admin')

const tab = ref('friends')
const friends = ref([])
const requests = ref([])
const addUserId = ref(null)
const addUsername = ref('')
const userOptions = ref([])
const searching = ref(false)
const adding = ref(false)

async function load() {
  try {
    [friends.value, requests.value] = await Promise.all([listFriends(), listFriendRequests()])
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function searchAll(q) {
  searching.value = true
  try {
    userOptions.value = await searchUsers(q, 'all')
  } catch {
    userOptions.value = []
  } finally {
    searching.value = false
  }
}

async function addFriend() {
  // admin 从下拉选；普通用户用完整用户名直接申请
  const username = isAdmin.value
    ? userOptions.value.find((x) => x.id === addUserId.value)?.username
    : addUsername.value.trim()
  if (!username) return ElMessage.warning(isAdmin.value ? '请先搜索并选择用户' : '请输入完整用户名')
  adding.value = true
  try {
    const r = await requestFriend(username)
    ElMessage.success(r.status === 'accepted' ? '对方也申请了你，已自动成为好友' : '申请已发送')
    addUserId.value = null
    addUsername.value = ''
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    adding.value = false
  }
}

async function respond(row, action) {
  try {
    await (action === 'accept' ? acceptFriend(row.id) : rejectFriend(row.id))
    ElMessage.success(action === 'accept' ? '已接受' : '已拒绝')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function removeFriend(row) {
  try {
    await deleteFriend(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => {
  load()
  if (isAdmin.value) searchAll('')
})
</script>
