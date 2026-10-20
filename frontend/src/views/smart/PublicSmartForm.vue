<template>
  <!-- 智能表公开表单（§12.3 公开收集，免登录）：/sf/:token —— 密码校验 → 填写 → 提交成功页 -->
  <div class="psf">
    <div v-if="loading" v-loading="true" class="psf-loading" />
    <div v-else-if="error" class="psf-card psf-msg">
      <div class="psf-msg-t">{{ error }}</div>
    </div>
    <div v-else-if="needPassword" class="psf-card psf-pw">
      <div class="psf-msg-t">请输入访问密码</div>
      <el-input v-model="password" show-password placeholder="访问密码" @keyup.enter="load" />
      <el-button type="primary" :loading="loading" @click="load">确定</el-button>
    </div>
    <div v-else-if="done" class="psf-card psf-msg">
      <div class="psf-ok">✓</div>
      <div class="psf-msg-t">{{ successText }}</div>
      <el-button v-if="def?.submit?.allowMultiple !== false" @click="again">再填一份</el-button>
    </div>
    <FormFill v-else-if="def" :def="def" :cover-src="def.cover ? coverUrl : ''" :uploader="upload"
              :submitting="submitting" @submit="submit" />
    <div class="psf-foot">由 智能表 提供表单服务</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import FormFill from '../../components/smart/form/FormFill.vue'
import { presetCoverUrl } from '../../components/smart/form/covers.js'
import { smartPublicForm, smartPublicSubmit, smartPublicUpload } from '../../api/index.js'
import '../../smart/tokens.css'

const route = useRoute()
const token = route.params.token
const def = ref(null)
const loading = ref(true)
const error = ref('')
const needPassword = ref(false)
const password = ref('')
const submitting = ref(false)
const done = ref(false)
const successText = ref('提交成功，感谢你的填写！')
const coverUrl = computed(() => presetCoverUrl(def.value?.cover) || `/api/smart-public/forms/${token}/cover${password.value ? `?password=${encodeURIComponent(password.value)}` : ''}`)

async function load() {
  loading.value = true
  error.value = ''
  try {
    def.value = await smartPublicForm(token, password.value || undefined)
    document.title = def.value.title || '表单'
    needPassword.value = false
  } catch (e) {
    if (e.code === 'password_required') {
      needPassword.value = true
      if (password.value) ElMessage.error('密码错误')
    } else {
      error.value = e.message || '表单不存在或已关闭'
    }
  } finally {
    loading.value = false
  }
}

async function upload(file, kind) {
  return smartPublicUpload(token, file, kind === 'image' ? 'image' : 'file', password.value || undefined)
}

async function submit(data, reset) {
  submitting.value = true
  try {
    const r = await smartPublicSubmit(token, data, password.value || undefined)
    successText.value = r.successText || successText.value
    reset()
    done.value = true
  } catch (e) {
    ElMessage.error(e.message || '提交失败')
  } finally {
    submitting.value = false
  }
}
function again() { done.value = false }

onMounted(load)
</script>

<style scoped>
.psf { min-height: 100vh; background: #EFF0F1; padding: 40px 16px 24px; box-sizing: border-box; --el-color-primary: var(--st-primary); }
.psf-loading { height: 300px; }
.psf-card { max-width: 760px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 48px; }
.psf-msg { display: flex; flex-direction: column; align-items: center; gap: 16px; }
.psf-msg-t { font-size: 17px; color: var(--st-text-1); }
.psf-ok { width: 56px; height: 56px; border-radius: 50%; background: #E8F7EE; color: #22B35E; font-size: 30px; display: flex; align-items: center; justify-content: center; }
.psf-pw { display: flex; flex-direction: column; gap: 14px; max-width: 360px; }
.psf-foot { text-align: center; font-size: 12px; color: var(--st-text-4); margin-top: 24px; }
@media (max-width: 600px) {
  .psf { padding: 0 0 16px; }
  .psf :deep(.ff-paper) { padding: 24px 16px 28px; border-radius: 0; }
  .psf-card { padding: 32px 16px; border-radius: 0; }
}
</style>
