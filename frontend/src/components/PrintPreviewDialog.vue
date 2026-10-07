<template>
  <el-dialog
    :model-value="modelValue" :title="title" width="min(1080px, 96vw)" top="3vh"
    destroy-on-close append-to-body
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="pv-bar">
      <el-radio-group v-model="paper" size="small">
        <el-radio-button value="a4">A4</el-radio-button>
        <el-radio-button value="half">2等分</el-radio-button>
        <el-radio-button value="third">3等分</el-radio-button>
      </el-radio-group>
      <span class="muted">{{ hint || `每条记录一张单据${paper === 'a4' ? '，一单一页' : (paper === 'half' ? '，一张 A4 排 2 单' : '，一张 A4 排 3 单')}` }}</span>
    </div>
    <div v-loading="loading" element-loading-text="正在填充模板…" class="pv-body">
      <iframe v-if="html" ref="frameRef" class="pv-frame" :srcdoc="html" />
    </div>
    <template #footer>
      <el-button v-if="downloadUrl" @click="download">下载 xlsx</el-button>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
      <el-button type="primary" :disabled="!html" @click="doPrint">打印</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '打印预览' },
  hint: { type: String, default: '' },           // 纸张旁的提示（默认按记录分页说明）
  viewUrl: { type: String, default: '' },        // 后端填充 HTML 打印页（带筛选参数与 token）
  downloadUrl: { type: String, default: '' },    // 同口径填充 xlsx 下载
  // 自定义数据源：(paper) => Promise<html>，给了它就代替 viewUrl（如编辑器即时预览）
  loader: { type: Function, default: null },
})
const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const html = ref('')
const frameRef = ref(null)
const paper = ref('a4')

async function loadPreview() {
  html.value = ''
  loading.value = true
  try {
    if (props.loader) {
      html.value = await props.loader(paper.value)
    } else {
      // 同接口拉一次文本塞 iframe srcdoc：错误时能把后端的 detail 提出来，而不是 iframe 白屏
      const res = await fetch(`${props.viewUrl}&paper=${paper.value}`)
      if (!res.ok) {
        let msg = `填充失败（${res.status}）`
        try { msg = (await res.json()).detail || msg } catch { /* 非 JSON 响应用默认信息 */ }
        throw new Error(msg)
      }
      html.value = await res.text()
    }
  } catch (e) {
    ElMessage.error(e.message)
    emit('update:modelValue', false)
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (v) => {
  if (v) {
    paper.value = 'a4'
    loadPreview()
  } else {
    html.value = ''
  }
})

// 切换纸张：同一份数据重排，重新拉取对应版式
watch(paper, () => {
  if (props.modelValue) loadPreview()
})

function doPrint() {
  const w = frameRef.value?.contentWindow
  if (!w) return
  w.focus()
  w.print()
}

function download() {
  window.open(props.downloadUrl, '_blank')
}
</script>

<style scoped>
.pv-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.pv-bar .muted { color: #909399; font-size: 12px; }
.pv-body { height: 74vh; background: #e8e8e8; border: 1px solid #dcdfe6; }
.pv-frame { width: 100%; height: 100%; border: none; display: block; }
</style>
