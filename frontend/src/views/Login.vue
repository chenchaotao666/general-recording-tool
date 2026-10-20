<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="logo"><img src="/wantong-logo.svg" alt="" style="width: 40px; height: 40px; display: block; margin: 0 auto 12px" />万通AI助手</div>
      <!-- el-form rules 即时校验（与全站表单体系一致），错误随输入自动清除 -->
      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent>
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名（至少 2 个字符）" size="large" @keyup.enter="submit" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" :placeholder="isRegister ? '密码（至少 6 位）' : '密码'" size="large" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-form-item v-if="isRegister" prop="password2">
          <el-input v-model="form.password2" type="password" placeholder="确认密码" size="large" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="submit">
          {{ isRegister ? '注 册' : '登 录' }}
        </el-button>
      </el-form>
      <div v-if="error" class="error">{{ error }}</div>
      <div class="login-links">
        <span class="switch-mode" @click="switchMode">
          {{ isRegister ? '已有账号？去登录' : '没有账号？注册一个' }}
        </span>
        <el-tooltip content="暂不支持自助找回，请联系管理员在「用户管理」协助处理" placement="top">
          <span class="forgot-link">忘记密码？</span>
        </el-tooltip>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { login, register } from '../api'

const router = useRouter()
const isRegister = ref(false)
const formRef = ref(null)
const form = reactive({ username: '', password: '', password2: '' })
const loading = ref(false)
const error = ref('')

// 服务端返回的错误提示随输入自动清除（不用重新提交才消失）
watch(form, () => { error.value = '' })

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, message: '用户名至少 2 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  password2: [{
    validator: (r, v, cb) => {
      if (!isRegister.value) return cb()
      if (!v) cb(new Error('请再次输入密码'))
      else if (v !== form.password) cb(new Error('两次输入的密码不一致'))
      else cb()
    },
    trigger: 'blur',
  }],
}

function switchMode() {
  isRegister.value = !isRegister.value
  error.value = ''
  formRef.value?.clearValidate()
}

async function submit() {
  error.value = ''
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const api = isRegister.value ? register : login
    const r = await api(form.username.trim(), form.password)
    sessionStorage.removeItem('grt_tenant_picked')
    localStorage.setItem('grt_token', r.token)
    localStorage.setItem('grt_user', JSON.stringify(r.user))
    localStorage.setItem('grt_tenant_id', r.user.tenant?.id || '')
    // 账号属于多个公司时先选公司（销售易式选择页）；
    // 单空间无可选——直接打上「已选择」标记，否则会话中接受邀请变多空间后 F5 会被守卫拦去选择页
    if ((r.user.tenants?.length || 0) > 1) {
      router.push('/select-tenant')
    } else {
      sessionStorage.setItem('grt_tenant_picked', '1')
      router.push('/')
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh; display: flex; align-items: center; justify-content: center;
  background: #f0f2f5;
}
.login-card { width: 360px; }
.logo {
  text-align: center; font-size: 20px; font-weight: 600;
  color: #303133; margin-bottom: 24px;
}
.login-btn { width: 100%; }
.error { color: #f56c6c; font-size: 13px; text-align: center; margin-top: 12px; }
.login-links {
  display: flex; justify-content: space-between; align-items: center; margin-top: 16px;
}
.switch-mode { font-size: 13px; color: var(--grt-primary); cursor: pointer; }
.forgot-link { font-size: 13px; color: #909399; cursor: help; }
</style>
