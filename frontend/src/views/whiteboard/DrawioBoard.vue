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
import { buildMxfile, mergeMxfile, partUnits, shiftUnits, unitsBBox, xmlBBox, xmlContext } from './drawioAi'
import { renderDrawioPreview } from './drawioPreview'

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

// ---------- AI 生成：parts（结构图/绘画）→ units → drawio mxfile，通过 load 动作下发 ----------

// 对外：把 AI 生成的内容应用到画布。replace=全新 mxfile（视口居中内容）；
// append=解析现有 XML 合并新 cells（保留原视口，新内容放右侧），解析失败回退替换。
// 注意：drawio embed 协议拿不到 iframe 内的选区（跨域 + 协议无此消息），
// 所以 modify 只能是整画布重新生成，不像 excalidraw 侧支持选中局部替换。
// 返回是否真正写入（编辑器未就绪/无内容时 false，调用方据此提示）
let previewDraft = null
let previewXml = null
function applyAiContent(d, { append = false } = {}) {
  if (!ready.value) return false
  const xml = previewDraft === d && previewXml ? previewXml : prepareAiXml(d, append)
  if (!xml) return false
  loadXml(xml)
  previewDraft = null
  previewXml = null
  return true
}

function prepareAiXml(d, append = d.mode === 'append') {
  const parts = d?.parts?.length ? d.parts : [d]
  const stamp = Date.now().toString(36)
  // 逐部分转 units：id 带时间戳前缀（与画布已有元素、跨部分都隔离），横向排开
  let units = []
  parts.forEach((part, i) => {
    const us = partUnits(part, `ai-${stamp}-p${i}-`)
    const bb = unitsBBox(us)
    if (!bb) return
    const cur = unitsBBox(units)
    units = units.concat(cur ? shiftUnits(us, cur.maxX + 160 - bb.minX, 0) : us)
  })
  if (!units.length) return false

  if (append) {
    const merged = mergeMxfile(latestXml, shiftToRight(units))
    if (merged) {
      return merged
    }
    // 现有 XML 为空/损坏：按替换处理
  }
  return buildMxfile(units, frameEl.value?.clientWidth || 960, frameEl.value?.clientHeight || 640)
}

// 下发 load 动作并同步 latestXml + 触发保存：load 本身不会让 drawio 标脏，
// 不主动回发 autosave，不更新的话切页/卸载时 AI 内容会丢
function loadXml(xml) {
  post({ action: 'load', autosave: 1, xml })
  latestXml = xml
  scheduleEmit()
}

// 追加时的偏移：现有内容右侧 120px、顶对齐；无现有内容保持原坐标
function shiftToRight(units) {
  const bb = unitsBBox(units)
  const ex = xmlBBox(latestXml)
  if (!bb || !ex) return units
  return shiftUnits(units, ex.maxX + 120 - bb.minX, ex.minY - bb.minY)
}

// 对外：提取画布概要（供 AI 追加/修改/汇总参考）
function getContext() {
  return xmlContext(latestXml)
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

async function renderAiDraft(d, { focusChanges = false } = {}) {
  const xml = prepareAiXml(d)
  if (!xml) throw new Error('没有可预览的内容')
  const image = await renderDrawioPreview(focusChanges && d.mode === 'append' ? prepareAiXml(d, false) : xml)
  previewDraft = d
  previewXml = xml
  return image
}
defineExpose({ getContent, applyAiContent, getContext, renderAiDraft })
</script>

<style scoped>
.drawio-host { height: 100%; position: relative; }
.drawio-frame { width: 100%; height: 100%; border: none; border-radius: 6px; }
.drawio-overlay {
  position: absolute; inset: 0; background: #fff; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
}
</style>
