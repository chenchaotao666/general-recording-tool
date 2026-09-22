<template>
  <view class="page">
    <!-- LLM 供应商 -->
    <view class="sec-head">
      <text class="sec-title">大模型供应商</text>
      <text class="sec-add" @click="openProviderForm(null)">+ 添加</text>
    </view>
    <view v-if="!providers.length" class="hint">未配置，AI 功能不可用</view>
    <view v-for="p in providers" :key="p.id" class="card">
      <view class="card-head">
        <view class="card-title">
          {{ p.name }}
          <text v-if="p.is_default" class="badge">默认</text>
          <text v-if="!p.enabled" class="badge gray">已停用</text>
        </view>
      </view>
      <view class="card-sub">{{ p.type === 'claude' ? 'Claude' : 'OpenAI 兼容' }} · {{ p.model }}</view>
      <view class="actions">
        <text class="act" @click="test(p)">测试</text>
        <text v-if="!p.is_default" class="act" @click="setDefault(p)">设为默认</text>
        <text class="act" @click="openProviderForm(p)">编辑</text>
        <text class="act danger" @click="delProvider(p)">删除</text>
      </view>
    </view>

    <!-- 供应商编辑表单 -->
    <view v-if="providerForm" class="card form-card">
      <view class="card-title" style="margin-bottom: 16rpx">{{ providerForm.id ? '编辑供应商' : '添加供应商' }}</view>
      <input v-model="providerForm.name" class="fc-input" placeholder="名称，如 DeepSeek" />
      <view class="radio-row" style="margin: 12rpx 0">
        <view class="radio sm" :class="{ active: providerForm.type === 'openai_compat' }" @click="providerForm.type = 'openai_compat'">OpenAI 兼容</view>
        <view class="radio sm" :class="{ active: providerForm.type === 'claude' }" @click="providerForm.type = 'claude'">Claude</view>
      </view>
      <input v-model="providerForm.base_url" class="fc-input" placeholder="Base URL，如 https://api.deepseek.com/v1" />
      <input v-model="providerForm.api_key" class="fc-input" :placeholder="providerForm.id ? '留空则不修改密钥' : 'API Key'" password />
      <input v-model="providerForm.model" class="fc-input" placeholder="模型，如 deepseek-chat" />
      <input v-model="providerForm.vision_model" class="fc-input" placeholder="视觉模型（可选，拍照识别用）" />
      <view class="fc-row">
        <text class="lbl-sm">设为默认</text>
        <switch :checked="providerForm.is_default" @change="(e) => (providerForm.is_default = e.detail.value)" style="transform: scale(.8)" />
        <text class="lbl-sm">启用</text>
        <switch :checked="providerForm.enabled" @change="(e) => (providerForm.enabled = e.detail.value)" style="transform: scale(.8)" />
      </view>
      <view class="actions" style="margin-top: 16rpx">
        <text class="act" @click="providerForm = null">取消</text>
        <text class="act primary" @click="saveProvider">保存</text>
      </view>
    </view>

    <!-- SMTP -->
    <view class="sec-head"><text class="sec-title">邮件（SMTP）</text></view>
    <view class="card form-card">
      <input v-model="smtp.host" class="fc-input" placeholder="SMTP 服务器，如 smtp.qq.com" />
      <view class="fc-row">
        <input v-model="smtp.port" type="number" class="fc-input" placeholder="端口" style="max-width: 200rpx" />
        <text class="lbl-sm">SSL</text>
        <switch :checked="smtp.use_ssl" @change="(e) => (smtp.use_ssl = e.detail.value)" style="transform: scale(.8)" />
      </view>
      <input v-model="smtp.username" class="fc-input" placeholder="邮箱账号" />
      <input v-model="smtp.password" class="fc-input" :placeholder="smtp.has_password ? '已配置，留空则不修改' : '密码或授权码'" password />
      <input v-model="smtp.from_addr" class="fc-input" placeholder="发件人地址（留空用账号）" />
      <view class="actions" style="margin-top: 16rpx">
        <text class="act primary" @click="saveSmtp">保存</text>
      </view>
      <view class="fc-row" style="margin-top: 16rpx; border-top: 1rpx solid #f0f0f0; padding-top: 16rpx">
        <input v-model="testEmailTo" class="fc-input" placeholder="测试收件邮箱" />
        <text class="act primary" @click="sendTest">发送测试</text>
      </view>
    </view>

    <!-- 短信网关 -->
    <view class="sec-head"><text class="sec-title">短信网关</text></view>
    <view class="card form-card">
      <textarea v-model="smsGateway.url_template" class="textarea" placeholder="URL 模板，{phone} 和 {content} 会被替换" />
      <view class="actions" style="margin-top: 16rpx">
        <text class="act primary" @click="saveSms">保存</text>
      </view>
    </view>

    <!-- 账号 -->
    <view class="sec-head"><text class="sec-title">账号</text></view>
    <view class="card">
      <view class="fc-row">
        <text class="card-sub" style="flex: 1">当前用户：{{ user?.username || '-' }}（{{ roleLabel }}）</text>
        <text class="act" @click="openPassword">修改密码</text>
        <text class="act danger" @click="logout">退出登录</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  createProvider, deleteProvider, getGeneralSettings, listProviders,
  saveGeneralSettings, setDefaultProvider, testEmail, testProvider, updateProvider,
} from '../../api'

const providers = ref([])
const providerForm = ref(null)
const smtp = ref({})
const smsGateway = ref({})
const testEmailTo = ref('')
const user = uni.getStorageSync('grt_user')
const roleLabel = { admin: '管理员', vip: 'VIP', user: '普通用户' }[user?.role] || '普通用户'

function openPassword() {
  uni.navigateTo({ url: '/pages/settings/password' })
}

function logout() {
  uni.showModal({
    title: '退出登录',
    content: '确定退出当前账号？',
    success: (res) => {
      if (!res.confirm) return
      uni.removeStorageSync('grt_token')
      uni.removeStorageSync('grt_user')
      uni.reLaunch({ url: '/pages/login/index' })
    },
  })
}

async function load() {
  try {
    providers.value = await listProviders()
    const g = await getGeneralSettings()
    smtp.value = g.smtp || {}
    if (smtp.value.use_ssl === undefined) smtp.value.use_ssl = Number(smtp.value.port) === 465
    smsGateway.value = g.sms_gateway || {}
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

function openProviderForm(p) {
  providerForm.value = p
    ? { id: p.id, name: p.name, type: p.type, base_url: p.base_url || '', api_key: '', model: p.model, vision_model: p.vision_model || '', is_default: p.is_default, enabled: p.enabled }
    : { id: null, name: '', type: 'openai_compat', base_url: '', api_key: '', model: '', vision_model: '', is_default: !providers.value.length, enabled: true }
}

async function saveProvider() {
  const f = providerForm.value
  if (!f.name.trim() || !f.model.trim()) return uni.showToast({ title: '名称和模型必填', icon: 'none' })
  try {
    const payload = { ...f, api_key: f.api_key || null }
    delete payload.id
    if (f.id) {
      await updateProvider(f.id, payload)
    } else {
      await createProvider(payload)
    }
    providerForm.value = null
    uni.showToast({ title: '已保存', icon: 'success' })
    load()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  }
}

async function test(p) {
  uni.showLoading({ title: '测试中…', mask: true })
  try {
    const res = await testProvider(p.id)
    uni.showToast({ title: res.ok ? '连接成功' : (res.error || '失败'), icon: 'none', duration: 2500 })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    uni.hideLoading()
  }
}

async function setDefault(p) {
  try {
    await setDefaultProvider(p.id)
    load()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

function delProvider(p) {
  uni.showModal({
    title: '确认删除',
    content: `删除供应商「${p.name}」？`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        await deleteProvider(p.id)
        load()
      } catch (e) {
        uni.showToast({ title: e.message, icon: 'none' })
      }
    },
  })
}

async function saveSmtp() {
  try {
    await saveGeneralSettings({ smtp: smtp.value, sms_gateway: smsGateway.value })
    uni.showToast({ title: '已保存', icon: 'success' })
    load()
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function saveSms() {
  try {
    await saveGeneralSettings({ smtp: smtp.value, sms_gateway: smsGateway.value })
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none' })
  }
}

async function sendTest() {
  if (!testEmailTo.value.trim()) return uni.showToast({ title: '请填写测试邮箱', icon: 'none' })
  uni.showLoading({ title: '发送中…', mask: true })
  try {
    await testEmail(testEmailTo.value.trim())
    uni.showToast({ title: '已发送，请查收', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: e.message, icon: 'none', duration: 3000 })
  } finally {
    uni.hideLoading()
  }
}

onShow(load)
</script>

<style>
.page { padding: 24rpx; padding-bottom: 60rpx; }
.sec-head { display: flex; justify-content: space-between; align-items: center; margin: 16rpx 0 12rpx; }
.sec-title { font-size: 28rpx; font-weight: 600; color: #303133; }
.sec-add { font-size: 26rpx; color: #409eff; padding: 8rpx 16rpx; }
.hint { color: #c0c4cc; font-size: 26rpx; padding: 20rpx 0; }
.card { background: #fff; border-radius: 16rpx; padding: 24rpx 28rpx; margin-bottom: 16rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,.05); }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-size: 30rpx; font-weight: 600; color: #303133; }
.badge { font-size: 20rpx; color: #fff; background: #67c23a; border-radius: 6rpx; padding: 2rpx 10rpx; margin-left: 10rpx; }
.badge.gray { background: #c0c4cc; }
.card-sub { font-size: 24rpx; color: #909399; margin-top: 8rpx; }
.actions { display: flex; gap: 24rpx; margin-top: 16rpx; border-top: 1rpx solid #f0f0f0; padding-top: 16rpx; }
.act { font-size: 26rpx; color: #409eff; }
.act.danger { color: #f56c6c; }
.act.primary { font-weight: 600; }
.form-card .fc-input { margin-bottom: 12rpx; }
.fc-input { font-size: 26rpx; color: #303133; border: 1rpx solid #e4e7ed; border-radius: 8rpx; padding: 14rpx 18rpx; }
.fc-row { display: flex; gap: 16rpx; align-items: center; }
.lbl-sm { font-size: 24rpx; color: #909399; }
.radio-row { display: flex; gap: 12rpx; }
.radio.sm { font-size: 24rpx; color: #606266; border: 1rpx solid #dcdfe6; border-radius: 32rpx; padding: 8rpx 24rpx; }
.radio.sm.active { background: #409eff; border-color: #409eff; color: #fff; }
.textarea { font-size: 26rpx; color: #303133; width: 100%; min-height: 120rpx; border: 1rpx solid #e4e7ed; border-radius: 8rpx; padding: 14rpx 18rpx; box-sizing: border-box; }
</style>
