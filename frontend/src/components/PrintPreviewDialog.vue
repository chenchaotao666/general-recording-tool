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
      <span class="muted">{{ hint || `${paper === 'a4' ? '一单一页' : (paper === 'half' ? '一张 A4 排 2 单' : '一张 A4 排 3 单')}` }}</span>
    </div>
    <div v-loading="loading" element-loading-text="正在填充模板…" class="pv-body">
      <!-- 错误内嵌展示（不关对话框，可重试） -->
      <div v-if="errorMsg" class="pv-error">
        <el-result icon="error" title="预览生成失败" :sub-title="errorMsg">
          <template #extra>
            <el-button type="primary" @click="loadPreview">重试</el-button>
          </template>
        </el-result>
      </div>
      <iframe v-else-if="html" ref="frameRef" class="pv-frame" :srcdoc="html" />
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
import { getPaper, setPaper } from '../utils/printPrefs'

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
const errorMsg = ref('')
const frameRef = ref(null)
const paper = ref(getPaper())   // 纸张偏好全局共享（picker/直接打印同口径）；打开对话框时再同步一次

async function loadPreview() {
  html.value = ''
  errorMsg.value = ''
  loading.value = true
  try {
    if (props.loader) {
      html.value = await props.loader(paper.value)
    } else {
      // 同接口拉一次文本塞 iframe srcdoc：错误时能把后端的 detail 提出来，而不是 iframe 白屏
      // no-store：模板/数据是会变的，预览绝不能吃到旧缓存
      const res = await fetch(`${props.viewUrl}&paper=${paper.value}`, { cache: 'no-store' })
      if (!res.ok) {
        let msg = `填充失败（${res.status}）`
        try { msg = (await res.json()).detail || msg } catch { /* 非 JSON 响应用默认信息 */ }
        throw new Error(msg)
      }
      html.value = await res.text()
    }
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (v) => {
  if (v) {
    // 每次打开同步全局纸张偏好（picker 里可能刚改过）：
    // 值有变化 → 由 paper watcher 触发加载；无变化 → 这里直接加载，避免双重请求
    const p = getPaper()
    if (p !== paper.value) paper.value = p
    else loadPreview()
  } else {
    html.value = ''
    errorMsg.value = ''
  }
})

// 切换纸张：记住偏好，同一份数据重排，重新拉取对应版式
watch(paper, (v) => {
  setPaper(v)
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
.pv-error { height: 100%; display: flex; align-items: center; justify-content: center; background: #fff; }
.pv-error :deep(.el-result__subtitle) { word-break: break-all; padding: 0 24px; }
</style>
