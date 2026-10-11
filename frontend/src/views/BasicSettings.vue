<template>
  <div>
    <!-- 与全站统一的页头范式（原来用面包屑，是全站唯一不统一的页面） -->
    <div class="page-header"><h2>基础设置</h2></div>

    <el-card v-loading="loading" class="basic-card" shadow="never">
      <el-form label-width="90px" style="max-width: 520px">
        <el-form-item label="租户 ID">
          <el-input :model-value="tenantId" disabled />
        </el-form-item>
        <el-form-item label="公司名称" required>
          <el-input v-model="name" maxlength="64" placeholder="请输入公司名称" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getCurrentTenant, updateCurrentTenant } from '../api'

const tenantId = ref('')
const name = ref('')
const loading = ref(false)
const saving = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const t = await getCurrentTenant()
    tenantId.value = t.tenant?.id ?? ''
    name.value = t.tenant?.name ?? ''
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
})

async function save() {
  if (!name.value.trim()) return ElMessage.warning('公司名称不能为空')
  saving.value = true
  try {
    const r = await updateCurrentTenant({ name: name.value.trim() })
    // 顶栏/工作空间切换器读取 grt_user.tenant.name，同步后刷新生效
    const user = JSON.parse(localStorage.getItem('grt_user') || '{}')
    if (user.tenant && user.tenant.id === r.tenant.id) user.tenant.name = r.tenant.name
    localStorage.setItem('grt_user', JSON.stringify(user))
    // 通知顶栏重读用户信息（空间名/标签即时更新），不整页刷新
    window.dispatchEvent(new Event('grt-user-refresh'))
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.basic-card { max-width: 720px; }
</style>
