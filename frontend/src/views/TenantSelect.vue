<template>
  <div class="select-page">
    <div class="select-panel">
      <div class="logo">通用记录工具</div>
      <h2 class="welcome">欢迎！</h2>
      <p class="hint">您的账号属于多个公司，请选择要登录的公司</p>

      <div class="tenant-list" v-loading="switching" element-loading-text="正在进入空间…">
        <div
          v-for="t in sortedTenants" :key="t.id"
          class="tenant-row" :class="{ disabled: switching }" @click="choose(t)"
        >
          <span class="avatar" :class="{ personal: t.type === 'personal' }">
            {{ t.type === 'personal' ? '个' : (t.name?.[0] || '企') }}
          </span>
          <span class="name">
            {{ t.type === 'personal' ? '个人空间' : t.name }}
            <span v-if="t.type === 'personal'" class="sub">{{ t.name }}</span>
          </span>
          <el-tag v-if="t.type === 'personal'" size="small" effect="plain">个人</el-tag>
          <el-tag v-else size="small" type="success" effect="plain">企业</el-tag>
        </div>
      </div>

      <div class="logout" @click="logout">退出登录</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { switchTenant } from '../api'

const router = useRouter()
const user = JSON.parse(localStorage.getItem('grt_user') || 'null')
const tenants = computed(() => user?.tenants || [])
// 企业与个人空间分开列：企业在前按加入顺序，个人空间固定沉底
const sortedTenants = computed(() => [
  ...tenants.value.filter((t) => t.type !== 'personal'),
  ...tenants.value.filter((t) => t.type === 'personal'),
])
const switching = ref(false)

// 只有 0/1 个公司时无需选择，直接进首页
if (tenants.value.length <= 1) {
  router.replace('/')
}

async function choose(t) {
  if (switching.value) return
  switching.value = true
  try {
    const payload = await switchTenant(t.id)
    localStorage.setItem('grt_user', JSON.stringify(payload))
    localStorage.setItem('grt_tenant_id', payload.tenant?.id || t.id)
    sessionStorage.setItem('grt_tenant_picked', '1')   // 本会话已选择，不再拦截
    router.push('/')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    switching.value = false
  }
}

async function logout() {
  // 误触即退出代价太小，加一次确认
  try {
    await ElMessageBox.confirm('确定退出登录？', '退出登录', {
      type: 'warning', confirmButtonText: '退出', cancelButtonText: '取消',
    })
  } catch { return }
  sessionStorage.removeItem('grt_tenant_picked')
  localStorage.removeItem('grt_token')
  localStorage.removeItem('grt_user')
  localStorage.removeItem('grt_tenant_id')
  router.push('/login')
}
</script>

<style scoped>
.select-page {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background: #f0f2f5;
}
.select-panel { width: 420px; }
.logo { font-size: 20px; font-weight: 600; color: #303133; margin-bottom: 32px; }
.welcome { font-size: 28px; margin: 0 0 8px; color: #303133; }
.hint { color: #909399; font-size: 14px; margin: 0 0 24px; }
.tenant-list {
  background: #fff; border-radius: 8px; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, .06);
}
.tenant-row {
  display: flex; align-items: center; gap: 14px;
  padding: 16px 20px; cursor: pointer; transition: background .15s;
}
.tenant-row:hover { background: #f5f7fa; }
.tenant-row.disabled { pointer-events: none; opacity: .6; }
.tenant-row + .tenant-row { border-top: 1px solid #f0f0f0; }
.avatar {
  width: 44px; height: 44px; border-radius: 50%;
  background: #2563eb; color: #fff; font-size: 17px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.avatar.personal { background: #67c23a; }
.name { font-size: 15px; color: #303133; flex: 1; }
.sub { font-size: 12px; color: #909399; margin-left: 8px; }
.logout {
  margin-top: 24px; text-align: center; font-size: 13px;
  color: #909399; cursor: pointer;
}
.logout:hover { color: #f56c6c; }
</style>
