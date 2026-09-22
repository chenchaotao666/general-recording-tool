<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="logo">通用记录工具</div>
      <el-form @submit.prevent>
        <el-form-item>
          <el-input v-model="username" placeholder="用户名（至少 2 个字符）" size="large" @keyup.enter="submit" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" :placeholder="isRegister ? '密码（至少 6 位）' : '密码'" size="large" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-form-item v-if="isRegister">
          <el-input v-model="password2" type="password" placeholder="确认密码" size="large" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="submit">
          {{ isRegister ? '注 册' : '登 录' }}
        </el-button>
      </el-form>
      <div v-if="error" class="error">{{ error }}</div>
      <div class="switch-mode" @click="switchMode">
        {{ isRegister ? '已有账号？去登录' : '没有账号？注册一个' }}
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login, register } from '../api'

const router = useRouter()
const isRegister = ref(false)
const username = ref('')
const password = ref('')
const password2 = ref('')
const loading = ref(false)
const error = ref('')

function switchMode() {
  isRegister.value = !isRegister.value
  error.value = ''
}

async function submit() {
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  if (isRegister.value && password.value !== password2.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const api = isRegister.value ? register : login
    const r = await api(username.value.trim(), password.value)
    localStorage.setItem('grt_token', r.token)
    localStorage.setItem('grt_user', JSON.stringify(r.user))
    router.push('/')
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
.switch-mode {
  text-align: center; font-size: 13px; color: #7c3aed;
  margin-top: 16px; cursor: pointer;
}
</style>
