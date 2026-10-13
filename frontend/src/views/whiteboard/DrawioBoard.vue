<template>
  <div class="drawio-host">
    <!-- iframe 始终可见：drawio 启动时会量容器尺寸，display:none 会按 0×0 初始化，恢复显示后内部布局塌陷 -->
    <!-- referrerpolicy=no-referrer：diagrams.net 会拦 localhost 的 Referer（403），不发 Referer 即可；顺带保护隐私 -->
    <iframe
      ref="frameEl" class="drawio-frame" :src="frameSrc"
      referrerpolicy="no-referrer" title="drawio 画板"
    />
    <!-- 加载/失败态用遮罩盖在上面，而不是隐藏 iframe -->
    <div v-if="!ready && !failed" v-loading="true" element-loading-text="drawio 编辑器加载中…" class="drawio-overlay" />
    <div v-else-if="failed" class="drawio-overlay">
      <el-result icon="warning" title="drawio 编辑器加载失败" sub-title="embed.diagrams.net 需要外网访问，请检查网络/代理后重试">
        <template #extra><el-button type="primary" @click="retry">重试</el-button></template>
      </el-result>
    </div>
  </div>
</template>

<script setup>
// drawio 画布编辑器：iframe 嵌入 embed.diagrams.net，postMessage proto=json 协议
// props.initial = 存库的 JSON 字符串（{"xml": "<mxfile...>"}）；change 事件回传同格式
// 协议要点：iframe 就绪发 init → 我们回 {action:'load', autosave:1, xml}
// → 之后每次画布变动 iframe 自动发 autosave（带 xml）
import { onBeforeUnmount, onMounted, ref } from 'vue'

const ORIGIN = 'https://embed.diagrams.net'
// ui=kennedy 经典全套界面；libraries=1 开图形库侧栏；关掉保存/退出按钮（保存由画板页自动保存接管）
const EMBED_URL = ORIGIN + '/?embed=1&proto=json&spin=1&stealth=1&lang=zh&libraries=1'
  + '&noSaveBtn=1&saveAndExit=0&noExitBtn=1'
const INIT_TIMEOUT = 30000   // embed 首包 ~2MB，慢网/代理下给足余量

const props = defineProps({
  initial: { type: String, default: '' },   // 上次保存的画布 JSON（{"xml": ...}，空 = 新画布）
})
const emit = defineEmits(['change'])

const frameEl = ref(null)
const frameSrc = ref(EMBED_URL)
const ready = ref(false)
const failed = ref(false)

let latestXml = ''       // 最近一次 autosave 的 mxfile XML
let emitTimer = null
let initTimer = null

function parseInitialXml() {
  if (!props.initial) return ''
  try {
    const d = JSON.parse(props.initial)
    return typeof d?.xml === 'string' ? d.xml : ''
  } catch { /* 损坏数据按空画布处理 */ }
  return ''
}

function currentJson() {
  return JSON.stringify({ xml: latestXml })
}

function post(msg) {
  frameEl.value?.contentWindow?.postMessage(JSON.stringify(msg), ORIGIN)
}

function scheduleEmit() {
  clearTimeout(emitTimer)
  emitTimer = setTimeout(() => emit('change', currentJson()), 500)
}

function onMessage(e) {
  if (e.origin !== ORIGIN || e.source !== frameEl.value?.contentWindow) return
  let msg = e.data
  if (typeof msg === 'string') {
    try { msg = JSON.parse(msg) } catch { return }
  }
  if (!msg || typeof msg !== 'object') return
  if (msg.event === 'init') {
    clearTimeout(initTimer)
    post({ action: 'load', autosave: 1, xml: parseInitialXml() })
  } else if (msg.event === 'load') {
    ready.value = true
    // load 事件不带 xml，画布初始内容以我们发下去的为准
  } else if (msg.event === 'autosave' || msg.event === 'save') {
    latestXml = msg.xml || ''
    scheduleEmit()
  } else if (msg.event === 'exit') {
    // noExitBtn=1 后理论上不会触发；兜底按当前内容存一次
    emit('change', currentJson())
  }
}

function armInitTimeout() {
  clearTimeout(initTimer)
  initTimer = setTimeout(() => { if (!ready.value) failed.value = true }, INIT_TIMEOUT)
}

function retry() {
  failed.value = false
  ready.value = false
  frameSrc.value = `${EMBED_URL}&_r=${Date.now()}`   // 换 src 强制 iframe 重载
  armInitTimeout()
}

// 对外：切页/卸载前取最新内容（不经过防抖）
function getContent() {
  clearTimeout(emitTimer)
  return currentJson()
}

onMounted(() => {
  window.addEventListener('message', onMessage)
  armInitTimeout()
})

onBeforeUnmount(() => {
  clearTimeout(emitTimer)
  clearTimeout(initTimer)
  window.removeEventListener('message', onMessage)
})

defineExpose({ getContent })
</script>

<style scoped>
.drawio-host { height: 100%; position: relative; }
.drawio-frame { width: 100%; height: 100%; border: none; border-radius: 6px; }
.drawio-overlay {
  position: absolute; inset: 0; background: #fff; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
}
</style>
