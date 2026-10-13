<template>
  <!-- AI 附图：点击选择 / 直接 Ctrl+V 粘贴截图；缩略图可单个移除 -->
  <div class="ai-images">
    <div v-for="(img, i) in modelValue" :key="i" class="ai-img-thumb">
      <img :src="img" alt="附图" />
      <span class="ai-img-del" @click="remove(i)">×</span>
    </div>
    <div
      v-if="modelValue.length < max" class="ai-img-add"
      title="点击选择图片，或直接粘贴截图（最多 4 张）"
      @click="fileEl?.click()"
    >＋图片</div>
    <input ref="fileEl" type="file" accept="image/*" multiple hidden @change="onPick" />
  </div>
</template>

<script setup>
// AI 对话框通用附图组件：v-model 为 JPEG data URL 数组（后端 _decode_data_urls 解码，限 4 张/5MB）。
// 客户端先压缩：最长边 1568px + JPEG 0.85（视觉模型推荐尺寸，也避开 5MB 上限）
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  max: { type: Number, default: 4 },
})
const emit = defineEmits(['update:modelValue'])

const MAX_DIM = 1568
const fileEl = ref(null)

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(img.src)
      const scale = Math.min(1, MAX_DIM / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(img.width * scale))
      canvas.height = Math.max(1, Math.round(img.height * scale))
      const ctx = canvas.getContext('2d')
      ctx.fillStyle = '#fff'   // 透明 PNG 转 JPEG 前先铺白底，否则透明区域变黑
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      resolve(canvas.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = () => { URL.revokeObjectURL(img.src); reject(new Error('图片读取失败')) }
    img.src = URL.createObjectURL(file)
  })
}

async function addFiles(files) {
  const imgs = [...(files || [])].filter((f) => f.type?.startsWith('image/'))
  if (!imgs.length) return
  const room = props.max - props.modelValue.length
  if (imgs.length > room) ElMessage.warning(`最多 ${props.max} 张图片`)
  const next = [...props.modelValue]
  for (const f of imgs.slice(0, room)) {
    try { next.push(await fileToDataUrl(f)) } catch { ElMessage.warning(`「${f.name || '图片'}」读取失败`) }
  }
  emit('update:modelValue', next)
}

function onPick(e) {
  addFiles(e.target.files)
  e.target.value = ''   // 允许重复选同一文件
}

// 全局粘贴：剪贴板里有图片才接管（纯文本粘贴不受影响）；
// 富文本编辑区（contenteditable）里的粘贴不接管——那是正文插图，不是 AI 附图
function onPaste(e) {
  if (e.target?.isContentEditable) return
  const files = [...(e.clipboardData?.files || [])].filter((f) => f.type?.startsWith('image/'))
  if (files.length) addFiles(files)
}

function remove(i) {
  const next = [...props.modelValue]
  next.splice(i, 1)
  emit('update:modelValue', next)
}

onMounted(() => document.addEventListener('paste', onPaste))
onBeforeUnmount(() => document.removeEventListener('paste', onPaste))
</script>

<style scoped>
.ai-images { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.ai-img-thumb {
  position: relative; width: 56px; height: 56px;
  border: 1px solid #dcdfe6; border-radius: 6px; overflow: hidden;
}
.ai-img-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ai-img-del {
  position: absolute; top: 0; right: 0; width: 18px; height: 18px; line-height: 16px;
  text-align: center; background: rgba(0, 0, 0, .55); color: #fff; cursor: pointer;
  border-bottom-left-radius: 6px; font-size: 13px;
}
.ai-img-add {
  width: 56px; height: 56px; border: 1px dashed #c0c4cc; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; color: #909399; cursor: pointer; user-select: none;
}
.ai-img-add:hover { border-color: var(--grt-ai, #7c5cff); color: var(--grt-ai, #7c5cff); }
</style>
