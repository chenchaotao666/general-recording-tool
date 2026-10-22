<template>
  <el-popover :hide-after="0" v-model:visible="visible" trigger="click" placement="bottom-end" :width="400"
              :popper-style="{ maxWidth: 'calc(100vw - 24px)', borderRadius: '8px' }" :show-arrow="false" popper-class="st-pop form-share-pop">
    <template #reference>
      <button class="share-trigger" :disabled="!canManage"><StIcon name="link" :size="15" />分享表单</button>
    </template>
    <div class="fs-panel" v-loading="loading">
      <div class="fs-enable" :class="{ enabled: link }">
        <div><div class="fs-heading">启用表单链接</div><p>启用后，成员可通过表单链接添加记录，无需加入文档。</p></div>
        <el-switch :model-value="!!link" :disabled="loading || busy || failed" :loading="busy" aria-label="启用表单链接" @change="toggle" />
      </div>
      <div v-if="failed" class="fs-error">链接加载失败<button @click="load">重试</button></div>
      <div v-if="link" class="fs-body">
        <div class="fs-section">填写范围</div>
        <div class="fs-row"><span>谁可以填写</span>
          <el-select :model-value="access" :disabled="!link || busy || loading || failed" :teleported="false" aria-label="谁可以填写" @change="changeAccess">
            <el-option value="public" label="任何人（无需登录）" />
            <el-option value="password" label="凭密码访问" />
          </el-select>
        </div>
        <div v-if="access === 'password'" class="fs-password">
          <div class="fs-password-state">{{ link?.has_password ? '已启用密码保护，留空保留原密码' : '设置密码后，填写者需输入密码才能访问' }}</div>
          <div class="fs-row">
            <el-input v-model="password" type="password" show-password autocomplete="new-password"
                      placeholder="输入访问密码（至少 4 位）" :disabled="!link || busy" @keyup.enter="savePassword" />
            <el-button :disabled="!link || busy || password.length < 4" :loading="busy" @click="savePassword">{{ link?.has_password ? '更新' : '保存' }}</el-button>
          </div>
        </div>
        <div class="fs-section fs-invite">邀请填写</div>
        <div class="fs-actions">
          <button class="fs-copy" :disabled="!ready" @click="copyLink"><StIcon name="link" :size="18" />复制链接</button>
          <button class="fs-icon st-icon-action" :disabled="!ready" aria-label="打开表单" data-smart-tip="打开表单" @click="openForm"><StIcon name="open-form" :size="19" /></button>
          <button class="fs-icon st-icon-action" :disabled="!ready" aria-label="表单二维码" data-smart-tip="表单二维码" @click="showQr"><StIcon name="qr-code" :size="18" /></button>
          <button class="fs-icon st-icon-action" :disabled="!ready" aria-label="分享到微信" data-smart-tip="分享到微信" @click="showWechat"><StIcon name="wechat" :size="19" /></button>
        </div>
      </div>
    </div>
  </el-popover>
  <el-dialog v-model="qrVisible" title="获取二维码" width="348px" align-center append-to-body
             :style="{ maxWidth: 'calc(100vw - 24px)' }" class="fs-qr-dialog">
    <div class="fs-qr">
      <div class="fs-qr-card">
        <span class="fs-form-mark"><StIcon name="form-sheet" :size="24" /></span>
        <h3>{{ title || '收集表单' }}</h3>
        <p>使用微信或企业微信扫码填写</p>
        <img v-if="qrSrc" :src="qrSrc" width="220" height="220" alt="扫码填写表单" />
        <p v-if="link?.has_password" class="fs-qr-password">此表单需输入访问密码</p>
      </div>
      <el-button :loading="downloading" @click="downloadQr">保存二维码</el-button>
    </div>
  </el-dialog>
  <el-dialog v-model="wechatVisible" title="分享到微信" width="320px" align-center append-to-body
             :style="{ maxWidth: 'calc(100vw - 24px)' }" class="fs-wechat-dialog">
    <p class="fs-wechat-help">请复制链接并前往微信分享</p>
    <template v-if="wechatCopyFailed">
      <p class="fs-copy-help">自动复制失败，请手动复制下方链接后打开微信。</p>
      <el-input :model-value="url" readonly aria-label="微信分享链接" @focus="$event.target.select()" />
    </template>
    <p v-if="wechatCopied" class="fs-copy-help fs-wechat-result">链接已复制。如未唤起微信，请手动打开微信粘贴分享。</p>
    <template #footer>
      <div class="fs-wechat-actions">
        <el-button type="primary" :loading="wechatCopying" @click="copyAndOpenWechat">复制链接并打开微信</el-button>
        <el-button @click="wechatVisible = false">取消</el-button>
      </div>
    </template>
  </el-dialog>
  <el-dialog v-model="copyVisible" title="复制表单链接" width="420px" align-center append-to-body
             :style="{ maxWidth: 'calc(100vw - 24px)' }">
    <p class="fs-copy-help">浏览器未允许自动复制，请选中下方链接手动复制。</p>
    <el-input :model-value="url" readonly aria-label="表单链接" @focus="$event.target.select()" />
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import { smartGetFormLink, smartCreateFormLink, smartDeleteFormLink } from '../../../api/index.js'

const props = defineProps({ viewId: { type: Number, required: true }, title: String, canManage: Boolean })
const visible = ref(false)
const loading = ref(false)
const busy = ref(false)
const failed = ref(false)
const link = ref(null)
const access = ref('public')
const password = ref('')
const qrVisible = ref(false)
const qrSrc = ref('')
const copyVisible = ref(false)
const wechatVisible = ref(false)
const wechatCopying = ref(false)
const wechatCopied = ref(false)
const wechatCopyFailed = ref(false)
const downloading = ref(false)
const url = computed(() => link.value ? `${location.origin}/sf/${link.value.token}` : '')
const ready = computed(() => !!link.value && !loading.value && !busy.value && !failed.value && (access.value !== 'password' || link.value.has_password))
let version = 0
watch(visible, value => { if (value) load() })
watch(() => props.viewId, () => {
  version++
  visible.value = qrVisible.value = copyVisible.value = wechatVisible.value = false
  link.value = null
  password.value = ''
  busy.value = loading.value = failed.value = false
})
async function load() {
  const current = ++version
  loading.value = true
  failed.value = false
  password.value = ''
  try {
    const result = await smartGetFormLink(props.viewId)
    if (current !== version) return
    link.value = result.link
    access.value = link.value?.has_password ? 'password' : 'public'
  } catch (error) {
    if (current === version) { failed.value = true; ElMessage.error(error.message || '加载失败') }
  } finally { if (current === version) loading.value = false }
}
async function mutate(action) {
  if (busy.value) return
  const current = version
  busy.value = true
  try {
    const result = await action()
    if (current !== version) return false
    link.value = result?.link || null
    access.value = link.value?.has_password ? 'password' : 'public'
    password.value = ''
    return true
  } catch (error) {
    if (current === version) ElMessage.error(error.message || '操作失败，请重试')
    return false
  } finally { if (current === version) busy.value = false }
}
async function toggle(enabled) {
  if (await mutate(() => enabled ? smartCreateFormLink(props.viewId) : smartDeleteFormLink(props.viewId))) {
    qrVisible.value = false
    ElMessage.success(enabled ? '表单链接已启用' : '表单链接已关闭')
  }
}
async function changeAccess(value) {
  if (value === 'password') { access.value = value; return }
  if (!link.value?.has_password) { access.value = value; password.value = ''; return }
  if (await mutate(() => smartCreateFormLink(props.viewId, { password: '' }))) ElMessage.success('已取消密码保护')
}
async function savePassword() {
  if (!link.value || password.value.length < 4 || busy.value) return
  if (await mutate(() => smartCreateFormLink(props.viewId, { password: password.value }))) ElMessage.success('访问密码已保存')
}
async function copyLink() {
  if (!ready.value) return
  try { await navigator.clipboard.writeText(url.value); ElMessage.success('链接已复制') }
  catch { visible.value = false; copyVisible.value = true }
}
function openForm() { if (ready.value) window.open(url.value, '_blank', 'noopener,noreferrer') }
async function showQr() {
  if (!ready.value) return
  const currentUrl = url.value
  try {
    const { default: QRCode } = await import('qrcode')
    const image = await QRCode.toDataURL(currentUrl, { width: 464, margin: 2, errorCorrectionLevel: 'M' })
    if (url.value !== currentUrl || !ready.value) return
    qrSrc.value = image
    visible.value = false
    qrVisible.value = true
  } catch { ElMessage.error('二维码生成失败，请重试') }
}
async function downloadQr() {
  if (downloading.value || !qrSrc.value) return
  downloading.value = true
  try {
    // Export the entire invitation card at 2x resolution, including its title.
    const img = new Image()
    img.src = qrSrc.value
    await img.decode()
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    const titleLines = []
    canvas.width = 600
    ctx.font = 'bold 40px "Microsoft YaHei", sans-serif'
    let line = ''
    for (const char of props.title || '收集表单') {
      if (ctx.measureText(line + char).width > 504 && line) { titleLines.push(line); line = '' }
      line += char
    }
    if (line) titleLines.push(line)
    const titleHeight = titleLines.length * 52
    canvas.height = 712 + titleHeight + (link.value?.has_password ? 40 : 0)
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = '#4094ff'
    ctx.beginPath()
    ctx.roundRect(48, 48, 64, 64, 10)
    ctx.fill()
    ctx.strokeStyle = '#fff'
    ctx.lineWidth = 3
    ctx.strokeRect(64, 60, 30, 40)
    ctx.beginPath()
    ctx.moveTo(70, 70); ctx.lineTo(88, 70)
    ctx.moveTo(70, 79); ctx.lineTo(80, 79)
    ctx.moveTo(74, 89); ctx.lineTo(80, 95); ctx.lineTo(90, 84)
    ctx.stroke()
    ctx.fillStyle = '#18202b'
    ctx.font = 'bold 40px "Microsoft YaHei", sans-serif'
    ctx.textBaseline = 'top'
    titleLines.forEach((text, i) => ctx.fillText(text, 48, 142 + i * 52))
    ctx.font = '26px "Microsoft YaHei", sans-serif'
    ctx.fillText('使用微信或企业微信扫码填写', 48, 150 + titleHeight)
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(img, 80, 210 + titleHeight, 440, 440)
    if (link.value?.has_password) {
      ctx.fillStyle = '#7A8491'
      ctx.font = '24px "Microsoft YaHei", sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('此表单需输入访问密码', 300, 660 + titleHeight)
    }
    const a = document.createElement('a')
    a.href = canvas.toDataURL('image/png')
    a.download = '表单二维码.png'
    a.click()
  } catch { ElMessage.error('保存二维码失败，请重试') }
  finally { downloading.value = false }
}
function showWechat() {
  if (!ready.value) return
  visible.value = false
  wechatCopied.value = wechatCopyFailed.value = false
  wechatVisible.value = true
}
async function copyAndOpenWechat() {
  if (wechatCopying.value || !ready.value) return
  const currentUrl = url.value
  wechatCopying.value = true
  wechatCopyFailed.value = false
  try {
    await navigator.clipboard.writeText(currentUrl)
    if (!wechatVisible.value || url.value !== currentUrl) return
    wechatCopied.value = true
    // The installed WeChat client handles this URI. The user chooses a recipient there.
    window.location.href = 'weixin://'
  } catch { wechatCopyFailed.value = true }
  finally { wechatCopying.value = false }
}
</script>

<style scoped>
.share-trigger { display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 10px; background: var(--st-primary); color: #fff; border: 0; border-radius: 4px; cursor: pointer; font-size: var(--st-font-size); }
.share-trigger:hover { filter: brightness(1.06); }
.share-trigger:disabled { opacity: .45; cursor: not-allowed; }
.fs-panel { padding: 8px; color: var(--st-text-2); font-size: var(--st-font-size); }
.fs-enable { display: flex; align-items: center; gap: 12px; }
.fs-enable.enabled { padding-bottom: 16px; border-bottom: 1px solid #E1E3E6; }
.fs-enable > div:first-child { flex: 1; }
.fs-enable > .el-switch { flex: none; }
.fs-heading { line-height: 20px; }
.fs-enable p { margin: 0; color: #8D96A3; font-size: var(--st-font-size); line-height: 18px; }
.fs-section { margin-top: 16px; margin-bottom: 10px; }
.fs-row { display: flex; align-items: center; gap: 8px; justify-content: space-between; }
.fs-row > span { flex: none; }
.fs-row > .el-select { width: 190px; }
.fs-password { margin-top: 12px; }
.fs-password-state { font-size: var(--st-font-size); color: #8D96A3; margin-bottom: 8px; }
.fs-invite { margin-top: 18px; }
.fs-actions { display: flex; gap: 8px; }
.fs-actions button { display: inline-flex; align-items: center; justify-content: center; gap: 5px; height: 36px; border: 0; background: #EFF0F1; border-radius: 4px; color: var(--st-text-2); cursor: pointer; }
.fs-actions button:hover:not(:disabled) { background: #E6E8E8; }
.fs-actions button:disabled { color: #ADB3BC; cursor: not-allowed; }
.fs-copy { flex: 1; font-size: var(--st-font-size); }
.fs-icon { flex: none; width: 36px; }
.fs-error { color: #D94848; padding-top: 12px; }
.fs-error button { border: 0; background: transparent; color: var(--st-primary); cursor: pointer; }
.fs-qr { display: flex; flex-direction: column; gap: 20px; padding: 0 8px 8px; }
.fs-qr-card { padding: 32px 24px; border-radius: 6px; background: #fff; box-shadow: 0 4px 12px #0000001f; color: #18202B; }
.fs-form-mark { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 5px; background: #4094FF; color: #fff; }
.fs-qr-card h3 { font-size: var(--st-font-size); line-height: 28px; margin: 12px 0 2px; overflow-wrap: anywhere; }
.fs-qr-card p { font-size: var(--st-font-size); margin: 0; line-height: 20px; }
.fs-qr img { display: block; max-width: 100%; height: auto; margin: 24px auto 12px; }
.fs-qr-card .fs-qr-password { text-align: center; color: #7A8491; font-size: var(--st-font-size); }
.fs-qr > .el-button { width: 100%; height: 40px; margin: 0; }
.fs-copy-help { margin: 0 0 12px; color: #7A8491; font-size: var(--st-font-size); line-height: 20px; }
.fs-wechat-help { margin: 0 0 12px; color: var(--st-text-2); font-size: var(--st-font-size); }
.fs-wechat-result { margin-top: 12px; }
.fs-wechat-actions { display: flex; gap: 12px; }
.fs-wechat-actions .el-button { margin: 0; border-radius: 4px; }
.fs-wechat-actions .el-button--primary { flex: 1; }
</style>

<style>
.fs-qr-dialog,.fs-wechat-dialog { border-radius: 8px; max-height: calc(100vh - 24px); overflow-y: auto; }
.fs-qr-dialog { background: #F8F9FA; }
.fs-qr-dialog .el-dialog__title,.fs-wechat-dialog .el-dialog__title { color: #18202B; font-weight: 600; font-size: var(--st-font-size-title); }
.fs-qr-dialog .el-dialog__headerbtn:hover,.fs-wechat-dialog .el-dialog__headerbtn:hover { background: #E6E8E8; border-radius: 4px; }
</style>
