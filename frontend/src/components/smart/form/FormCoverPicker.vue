<template>
  <el-dialog v-model="visible" title="选择封面" width="486px" align-center append-to-body
             class="st-cover-dialog" :style="{ maxWidth: 'calc(100vw - 24px)' }" @open="reset">
    <div class="cover-grid" role="group" aria-label="封面选项">
      <button class="cover-option cover-none" :class="{ selected: !selected }"
              :aria-pressed="!selected" @click="selected = null">不使用封面</button>
      <button v-for="cover in FORM_COVERS" :key="cover.value" class="cover-option"
              :class="{ selected: selected === cover.value }" :aria-label="cover.name"
              :aria-pressed="selected === cover.value" @click="selected = cover.value">
        <img :src="cover.src" :alt="cover.name" />
      </button>
      <button v-if="custom" class="cover-option" :class="{ selected: selected === custom }"
              aria-label="自定义封面" :aria-pressed="selected === custom" @click="selected = custom">
        <img :src="imageUrl(custom)" alt="自定义封面" />
      </button>
    </div>
    <div class="cover-upload">
      <button :disabled="uploading" @click="fileInput?.click()">{{ uploading ? '正在上传…' : '上传自定义封面' }}</button>
      <span>建议使用横向图片</span>
      <input ref="fileInput" type="file" accept="image/*" hidden @change="upload" />
    </div>
    <template #footer>
      <div class="cover-actions">
        <el-button type="primary" :disabled="uploading" @click="confirm">确定</el-button>
        <el-button @click="visible = false">取消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { imageUrl, uploadImageFile } from '../../../api/index.js'
import { FORM_COVERS, presetCoverUrl } from './covers.js'
const props = defineProps({ cover: { type: String, default: null } })
const visible = defineModel({ type: Boolean, default: false })
const emit = defineEmits(['select'])
const selected = ref(null)
const custom = ref(null)
const fileInput = ref(null)
const uploading = ref(false)
let generation = 0
function reset() {
  generation++
  selected.value = props.cover || null
  custom.value = props.cover && !presetCoverUrl(props.cover) ? props.cover : null
}
async function upload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || uploading.value) return
  if (!file.type.startsWith('image/')) return ElMessage.error('请选择图片文件')
  const current = generation
  uploading.value = true
  try {
    const result = await uploadImageFile(file)
    const id = result.files?.[0]?.id
    if (!id) throw new Error('上传失败，请重试')
    if (current === generation && visible.value) custom.value = selected.value = String(id)
  } catch (error) {
    ElMessage.error(error.message || '上传失败')
  } finally {
    uploading.value = false
  }
}
function confirm() {
  emit('select', selected.value)
  visible.value = false
}
</script>

<style scoped>
.cover-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; max-height: min(300px, 48vh); overflow-y: auto; padding: 2px; scrollbar-width: thin; }
.cover-option { height: 54px; padding: 0; border: 1px solid #E1E3E6; border-radius: 8px; background: #fff; overflow: hidden; cursor: pointer; }
.cover-option img { width: 100%; height: 100%; display: block; object-fit: cover; }
.cover-option:hover { border-color: #8CB9FA; }
.cover-option.selected { outline: 2px solid var(--st-primary, #287CF5); outline-offset: -2px; padding: 2px; }
.cover-option.selected img { border-radius: 5px; }
.cover-option:focus-visible { outline: 2px solid var(--st-primary, #287CF5); outline-offset: -2px; }
.cover-none { font-size: 13px; color: #7A8491; }
.cover-upload { display: flex; align-items: center; gap: 12px; margin: 16px 2px 0; font-size: 12px; color: #9098A3; }
.cover-upload button { border: 0; border-radius: 4px; padding: 6px 8px; background: #F1F2F3; color: #30343B; cursor: pointer; }
.cover-upload button:hover { background: #E6E8E8; }
.cover-upload button:disabled { opacity: .5; cursor: wait; }
.cover-actions { display: flex; gap: 18px; padding-top: 4px; }
.cover-actions .el-button { flex: 1; margin: 0; border-radius: 4px; }
.cover-actions .el-button:not(.el-button--primary) { border-color: transparent; background: #F2F3F5; color: #30343B; }
.cover-actions .el-button:not(.el-button--primary):hover { background: #E6E8E8; }
</style>

<style>
.st-cover-dialog { border-radius: 8px; }
.st-cover-dialog .el-dialog__title { font-size: 16px; color: #30343B; }
.st-cover-dialog .el-dialog__headerbtn:hover { background: #E6E8E8; border-radius: 4px; }
</style>
