<template>
  <view class="page">
    <view class="logo">通用记录工具</view>
    <view class="card">
      <input v-model="username" class="input" placeholder="用户名（至少 2 个字符）" />
      <input v-model="password" class="input" password :placeholder="isRegister ? '密码（至少 6 位）' : '密码'" @confirm="submit" />
      <input v-if="isRegister" v-model="password2" class="input" password placeholder="确认密码" @confirm="submit" />
      <button class="login-btn" :disabled="loading" @click="submit">{{ loading ? '请稍候…' : isRegister ? '注 册' : '登 录' }}</button>
      <view v-if="error" class="error">{{ error }}</view>
      <view class="switch-mode" @click="switchMode">
        {{ isRegister ? '已有账号？去登录' : '没有账号？注册一个' }}
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { login, register } from '../../api'

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
    uni.setStorageSync('grt_token', r.token)
    uni.setStorageSync('grt_user', r.user)
    uni.reLaunch({ url: '/pages/tables/index' })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style>
.page { padding: 120rpx 48rpx; }
.logo {
  text-align: center; font-size: 40rpx; font-weight: 600;
  color: #303133; margin-bottom: 60rpx;
}
.card { background: #fff; border-radius: 16rpx; padding: 40rpx 32rpx; }
.input {
  font-size: 30rpx; color: #303133; border: 1rpx solid #e4e7ed;
  border-radius: 12rpx; padding: 20rpx 24rpx; margin-bottom: 24rpx;
}
.login-btn {
  background: linear-gradient(135deg, #7c3aed, #a855f7); color: #fff;
  border-radius: 48rpx; font-size: 32rpx; margin-top: 16rpx;
}
.login-btn[disabled] { background: #c4b5fd; }
.error { color: #f56c6c; font-size: 24rpx; text-align: center; margin-top: 20rpx; }
.switch-mode {
  text-align: center; font-size: 26rpx; color: #7c3aed; margin-top: 28rpx;
}
</style>
