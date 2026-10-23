<template>
  <Teleport to="body">
    <div
      v-if="modelValue" ref="panelEl" class="ai-pp" :style="posStyle"
      @keydown.stop @mousedown.stop
    >
      <!-- 标题栏：按住可拖动（记事本 AI 面板同款交互；Esc/点外部关闭，无右上角叉） -->
      <div class="ai-pp-head" @mousedown="startDrag">
        <span class="ai-pp-title">{{ title }}</span>
        <span class="ai-pp-drag-hint">按住拖动</span>
      </div>

      <!-- 上下文提示条（如：基于选中内容 / 目标表） -->
      <div v-if="contextNote" class="ai-pp-context" :title="contextNote">📌 {{ contextNote }}</div>

      <!-- 模式（可选）：radio-button，第一项默认选中（建议「自动判断」类） -->
      <el-radio-group v-if="modes?.length" v-model="curMode" size="small" class="ai-pp-modes">
        <el-radio-button v-for="m in modes" :key="m.value" :value="m.value">{{ m.label }}</el-radio-button>
      </el-radio-group>

      <textarea
        v-show="!confirmation"
        ref="inputRef" v-model="instruction" class="ai-pp-input" :rows="rows"
        :placeholder="placeholder" :maxlength="maxlength"
        @keydown.enter.exact.prevent="submit"
      />
      <AiImagePicker v-if="image" v-show="!confirmation" v-model="images" />

      <section v-if="confirmation" class="ai-pp-review" aria-label="确认画布修改">
        <div class="ai-pp-result-head">待确认 · 尚未应用到画布</div>
        <div v-if="preview" class="ai-pp-preview">
          <label>缩放 <input v-model.number="previewZoom" type="range" min="25" max="400" step="25" /> {{ previewZoom }}%
            <button type="button" @click="previewZoom = 100">适应窗口</button>
          </label>
          <div class="ai-pp-preview-scroll"><div class="ai-pp-preview-size" :style="{ width: previewZoom + '%', height: previewZoom + '%' }"><img :src="preview" alt="确认应用后的画布效果预览" /></div></div>
        </div>
        <div v-if="!visualOnly" class="ai-pp-review-body">
          <p class="ai-pp-review-summary">{{ confirmation[0] }}</p>
          <div :class="{ 'ai-pp-review-preview': !reviewExpanded }">
            <p v-for="(line, index) in (reviewExpanded ? confirmation.slice(1) : confirmation.slice(1, 3))" :key="index">{{ line }}</p>
          </div>
        </div>
        <button v-if="!visualOnly && confirmation.length > 1" type="button" class="ai-pp-review-toggle" :aria-expanded="reviewExpanded" @click="reviewExpanded = !reviewExpanded">
          {{ reviewExpanded ? '收起详情' : `展开全部详情（${confirmation.length - 1} 项）` }}
        </button>
      </section>

      <!-- 文本类结果（总结/建议）：面板内展示 + 复制，不再弹框 -->
      <div v-if="result" class="ai-pp-result">
        <div class="ai-pp-result-head">
          <span>{{ resultTitle }}</span>
          <button type="button" class="ai-pp-result-copy" @click="copyResult">{{ copied ? '已复制 ✓' : '复制' }}</button>
        </div>
        <div class="ai-pp-result-body">{{ result }}</div>
      </div>

      <!-- 快捷指令 chips：点一下填入并聚焦；immediate=true 直接提交；event=自定义事件（由父级接管） -->
      <div v-if="chips?.length" class="ai-pp-chips">
        <button
          v-for="c in chips" :key="c.label" class="ai-pp-chip" type="button"
          :disabled="loading" @click="clickChip(c)"
        >{{ c.label }}</button>
      </div>

      <!-- 业务自定义内容（如表选择器、汇总入口链接） -->
      <slot />

      <div v-if="confirmation" class="ai-pp-ops">
        <span class="ai-pp-hint" />
        <template v-if="allowModeChange">
          <el-button size="small" :disabled="loading" @click="emit('confirm', 'replace')">确认覆盖</el-button>
          <el-button size="small" type="primary" :disabled="loading" @click="emit('confirm', 'append')">确认添加</el-button>
        </template>
        <template v-else>
          <el-button size="small" @click="emit('cancel-confirmation')">取消</el-button>
          <el-button size="small" type="primary" :disabled="loading" @click="emit('confirm')">{{ applicationMode === 'append' ? '确认添加' : '确认应用' }}</el-button>
        </template>
      </div>
      <div v-else class="ai-pp-ops">
        <span class="ai-pp-hint">{{ loading ? (loadingText || 'AI 生成中，可能需要十几秒…') : (hint || 'Enter 生成 · Esc 取消') }}</span>
        <el-button size="small" type="primary" :loading="loading" @click="submit">{{ submitText }}</el-button>
      </div>
      <div v-if="error" class="ai-pp-error">{{ error }}</div>
    </div>
  </Teleport>
</template>

<script setup>
// 统一 AI 指令面板（记事本 AI 写作面板的通用化）：
// 浮动面板贴触发按钮弹出、标题栏可拖动、点击外部/Esc 关闭、Enter 提交、
// 模式 radio-button / 图片 / 快捷指令 chips / 错误内联，业务差异全部走 props/slot。
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import AiImagePicker from './AiImagePicker.vue'

const props = defineProps({
  modelValue: Boolean,                       // v-model 控制显隐
  title: { type: String, default: '✨ AI 生成' },
  placeholder: { type: String, default: '描述想做的事，或上传图片让 AI 按图生成' },
  anchor: { type: [Object, null], default: null },   // 触发按钮的 DOM 元素（面板贴它下方弹出）
  modes: { type: Array, default: null },             // [{value, label}]
  mode: { type: String, default: '' },               // v-model:mode
  chips: { type: Array, default: null },             // [{label, value?, immediate?}]（value 缺省 = label）
  image: { type: Boolean, default: true },
  contextNote: { type: String, default: '' },
  hint: { type: String, default: '' },
  result: { type: String, default: '' },        // 文本类结果（总结/建议），非空即在面板内展示
  resultTitle: { type: String, default: '结果' },
  submitText: { type: String, default: '生成' },
  loading: Boolean,
  loadingText: { type: String, default: '' },
  preview: { type: String, default: '' },
  visualOnly: Boolean,
  applicationMode: { type: String, default: '' },
  allowModeChange: Boolean,
  preserveDraft: Boolean,
  confirmation: { type: Array, default: null },
  error: { type: String, default: '' },
  rows: { type: Number, default: 3 },
  maxlength: { type: Number, default: 500 },
})
const emit = defineEmits(['update:modelValue', 'update:mode', 'submit', 'close', 'chip', 'confirm', 'cancel-confirmation'])

const panelEl = ref(null)
const inputRef = ref(null)
const instruction = ref('')
const images = ref([])
const curMode = ref('')
const copied = ref(false)
const reviewExpanded = ref(false)
const previewZoom = ref(100)
watch(() => props.preview, () => { previewZoom.value = 100 })
watch(() => props.confirmation, () => { reviewExpanded.value = false })
const pos = ref({ x: null, y: null })
watch([() => props.confirmation, reviewExpanded], async () => {
  await nextTick()
  const rect = panelEl.value?.getBoundingClientRect()
  if (rect && rect.bottom > window.innerHeight - 8) {
    pos.value = { ...pos.value, y: Math.max(8, window.innerHeight - rect.height - 8) }
  }
})

const posStyle = computed(() => (pos.value.x !== null ? { left: pos.value.x + 'px', top: pos.value.y + 'px' } : {}))

// 打开时：定位到触发按钮下方（下方放不下翻到上方），聚焦输入框，挂外部点击/Esc
watch(() => props.modelValue, async (v) => {
  if (!v) { detach(); return }
  if (!props.preserveDraft) {
    instruction.value = ''
    images.value = []
  }
  curMode.value = props.mode || props.modes?.[0]?.value || ''
  await nextTick()
  place()
  inputRef.value?.focus()
  document.addEventListener('mousedown', onDocDown, true)
  document.addEventListener('keydown', onEsc, true)
})

function place() {
  const W = panelEl.value?.offsetWidth || 640
  const H = panelEl.value?.offsetHeight || 220
  // anchor 支持三种：DOM 元素 / ref(DOM) / 组件实例（el-button 等，取 $el）/
  // 虚拟锚点 {left, top, bottom}（屏幕坐标，右键菜单等无 DOM 锚点的场景）
  const raw = props.anchor
  let r = null
  if (raw instanceof Element) r = raw.getBoundingClientRect()
  else if (raw && typeof raw.left === 'number' && typeof raw.top === 'number') r = raw
  else {
    const el = raw?.$el || raw?.value?.$el || raw?.value
    r = el?.getBoundingClientRect?.()
  }
  let x = r ? r.left : (window.innerWidth - W) / 2
  let y = r ? (r.bottom ?? r.top) + 6 : Math.max(72, window.innerHeight * 0.18)
  x = Math.max(8, Math.min(x, window.innerWidth - W - 8))
  if (y + H > window.innerHeight - 8) y = Math.max(8, (r?.top || 200) - H - 6)
  pos.value = { x, y }
}

function detach() {
  document.removeEventListener('mousedown', onDocDown, true)
  document.removeEventListener('keydown', onEsc, true)
}
onBeforeUnmount(detach)
function close() {
  detach()
  emit('update:modelValue', false)
  emit('close')
}

function onDocDown(e) {
  if (panelEl.value && !panelEl.value.contains(e.target)) close()
}

function onEsc(e) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    close()
  }
}

// 标题栏拖动（限制在视口内）
function startDrag(e) {
  const rect = panelEl.value.getBoundingClientRect()
  const offX = e.clientX - rect.left
  const offY = e.clientY - rect.top
  const move = (ev) => {
    pos.value = {
      x: Math.max(0, Math.min(ev.clientX - offX, window.innerWidth - rect.width)),
      y: Math.max(0, Math.min(ev.clientY - offY, window.innerHeight - 60)),
    }
  }
  const up = () => {
    document.removeEventListener('mousemove', move)
    document.removeEventListener('mouseup', up)
  }
  document.addEventListener('mousemove', move)
  document.addEventListener('mouseup', up)
}

function clickChip(c) {
  if (c.event) { emit('chip', c); return }   // 自定义动作（如导图的「总结全文」），父级接管
  instruction.value = c.value ?? c.label
  if (c.mode) curMode.value = c.mode          // chip 可携带模式（如导图的 扩写/改写）
  if (c.immediate) submit()
  else inputRef.value?.focus()
}

function submit() {
  if (props.loading || props.confirmation) return
  emit('submit', { instruction: instruction.value.trim(), images: images.value, mode: curMode.value })
}

// 结果复制：内联反馈，不打断面板
async function copyResult() {
  try {
    await navigator.clipboard.writeText(props.result)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* 剪贴板不可用时静默，用户可手动全选复制 */ }
}
</script>

<style scoped>
/* 样式逐项对齐记事本 AI 写作面板（Notes.vue .ai-panel 系列）：640px 宽、无边框输入区、紫色 AI 色 */
.ai-pp {
  position: fixed; z-index: 3000; width: 640px; max-width: calc(100vw - 16px);
  background: #fff; border: 1px solid #e4e7ed; border-radius: 12px;
  padding: 12px 14px; box-shadow: 0 8px 28px rgba(0, 0, 0, 0.12);
  display: flex; flex-direction: column;
  box-sizing: border-box; max-height: calc(100vh - 16px); overflow-y: auto;
}
.ai-pp-review { margin-top: 4px; border: 1px solid #e4e7ed; border-radius: 8px; background: #fafafa; min-height: 0; }
.ai-pp-preview { padding: 8px 10px; font-size: 12px; color: #606266; }
.ai-pp-preview label { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ai-pp-preview-scroll { height: clamp(180px, 36vh, 360px); overflow: auto; background: white; }
.ai-pp-preview-size { display: flex; align-items: center; justify-content: center; }
.ai-pp-preview img { display: block; width: 100%; height: 100%; object-fit: contain; }
.ai-pp-review-body { padding: 0 10px; max-height: min(280px, 40vh); overflow-y: auto; overflow-wrap: anywhere; font-size: 13px; line-height: 1.7; color: #606266; }
.ai-pp-review-body p { margin: 8px 0; white-space: pre-wrap; }
.ai-pp-review-summary { color: #303133; font-weight: 600; }
.ai-pp-review-preview { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.ai-pp-review-toggle { border: 0; background: none; padding: 8px 10px; color: var(--grt-ai, #7c5cff); font-size: 12px; cursor: pointer; }
.ai-pp-head {
  font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px;
  cursor: move; user-select: none; display: flex; align-items: center; justify-content: space-between;
}
.ai-pp-drag-hint { font-size: 11px; font-weight: 400; color: #c0c4cc; }
.ai-pp-context {
  font-size: 12px; color: var(--grt-ai, #7c5cff); background: #f4f0ff; border-radius: 6px;
  padding: 4px 10px; margin-bottom: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ai-pp-modes { margin-bottom: 4px; }
.ai-pp-input {
  width: 100%; box-sizing: border-box; border: none; outline: none; background: transparent;
  padding: 6px 0; font-size: 14px; line-height: 1.6; resize: none;
  font-family: inherit; color: #303133;
}
.ai-pp-input::placeholder { color: #c0c4cc; }
/* 输入区与图片选择器紧凑排布（AiImagePicker 自带 margin-top 8px，面板内收紧） */
.ai-pp :deep(.ai-images) { margin-top: 2px; }
.ai-pp-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.ai-pp-chip {
  height: 24px; padding: 0 10px; border: 1px solid #dcdfe6; border-radius: 12px;
  background: #fff; color: #606266; font-size: 12px; cursor: pointer;
}
.ai-pp-chip:hover:not(:disabled) { border-color: var(--grt-ai, #7c5cff); color: var(--grt-ai, #7c5cff); }
.ai-pp-chip:disabled { color: #c0c4cc; cursor: not-allowed; }
/* 文本类结果区：灰底圆角框，超长滚动 */
.ai-pp-result {
  margin-top: 8px; border: 1px solid #e4e7ed; border-radius: 8px; background: #fafafa;
}
.ai-pp-result-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px; font-size: 12px; font-weight: 600; color: #303133;
  border-bottom: 1px solid #ebeef5;
}
.ai-pp-result-copy {
  border: none; background: none; font-size: 12px; color: var(--grt-ai, #7c5cff); cursor: pointer; padding: 0;
}
.ai-pp-result-body {
  padding: 8px 10px; font-size: 13px; line-height: 1.7; color: #303133;
  white-space: pre-wrap; max-height: 220px; overflow-y: auto;
}
.ai-pp-ops { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 8px; }
.ai-pp-hint { font-size: 12px; color: #c0c4cc; flex: 1; }
.ai-pp-error { font-size: 12px; color: #f56c6c; margin-top: 6px; }
</style>
