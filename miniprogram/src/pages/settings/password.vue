<template>
  <view class="page">
    <view class="card">
      <input v-model="oldPassword" class="input" password placeholder="原密码" />
      <input v-model="newPassword" class="input" password placeholder="新密码（至少 6 位）" />
      <input v-model="confirm" class="input" password placeholder="确认新密码" @confirm="submit" />
      <button class="save-btn" :disabled="saving" @click="submit">{{ saving ? '提交中…' : '确认修改' }}</button>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { changePassword } from '../../api'

const oldPassword = ref('')
const newPassword = ref('')
const confirm = ref('')
const saving = ref(false)

async function submit() {
  if (!oldPassword.value || !newPassword.value) return uni.showToast({ title: '请填写完整', icon: 'none' })
  if (newPassword.value.length < 6) return uni.showToast({ title: '新密码至少 6 位', icon: 'none' })
  if (newPassword.value !== confirm.value) return uni.showToast({ title: '两次输入的新密码不一致', icon: 'none' })
  saving.value = true
  try {
    await changePassword(oldPassword.value, newPassword.value)
    uni.showToast({ title: '密码已修改', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 800)
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    saving.value = false
  }
}
</script>

<style>
.page { padding: 24rpx; }
.card { background: #fff; border-radius: 16rpx; padding: 40rpx 32rpx; }
.input {
  font-size: 30rpx; color: #303133; border: 1rpx solid #e4e7ed;
  border-radius: 12rpx; padding: 20rpx 24rpx; margin-bottom: 24rpx;
}
.save-btn { background: #409eff; color: #fff; border-radius: 48rpx; font-size: 32rpx; margin-top: 16rpx; }
.save-btn[disabled] { background: #a0cfff; }
</style>
