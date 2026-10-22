<template>
  <!-- 编辑 AI 字段（单面板）：把「配置说明卡」和「字段设置」合并成一张从上到下的表单——
       名称 → 依据字段 / 输出类型 → AI 指令 → 选项 → 效果预览（可按当前设置试算）→ 自动更新；
       底部「让 AI 修改」直接改写上面的设置（可撤销），最后统一 保存 / 保存并生成全部。 -->
  <div class="afe-mask">
    <div class="afe" :style="posStyle" @keydown.esc="emit('close')">
      <!-- 头部：名称即标题，直接可改 -->
      <div class="afe-head">
        <span class="afe-logo"><StIcon name="sparkle" :size="13" /></span>
        <input v-model="draft.label" class="afe-name" placeholder="字段名称" maxlength="30" />
        <AiBadge plain />
        <span class="afe-flex" />
        <span class="afe-more-wrap">
          <span class="afe-icon st-icon-action" data-smart-tip="更多" @click="moreOpen = !moreOpen"><StIcon name="more-h" :size="18" /></span>
          <div v-if="moreOpen" class="afe-menu" @mouseleave="moreOpen = false">
            <div class="afe-mi" @click="run('all')"><StIcon name="sparkle" :size="14" />重新生成全部</div>
            <div class="afe-mi" @click="run('empty')"><StIcon name="row-add" :size="14" />仅生成空白行</div>
            <div class="afe-mi" @click="run('failed')"><StIcon name="sync" :size="14" />重新生成失败行</div>
          </div>
        </span>
        <span class="afe-icon st-icon-action" data-smart-tip="关闭" @click="emit('close')"><StIcon name="close" :size="16" /></span>
      </div>
      <div class="afe-sub">
        <template v-for="(seg, i) in descSegments" :key="i">
          <span v-if="seg.chip" class="afe-chip"><StIcon :name="seg.icon" :size="13" />{{ seg.text }}</span>
          <span v-else>{{ seg.text }}</span>
        </template>
        <span v-if="scene" class="afe-scene">· {{ scene.label }}</span>
      </div>

      <div class="afe-body">
        <div class="afe-card">
          <!-- 依据字段 + 输出类型 -->
          <div class="afe-row2">
            <div class="afe-col">
              <div class="afe-l">依据字段<span v-if="draft.inputLabel" class="afe-hint">{{ draft.inputLabel }}</span></div>
              <el-select v-model="draft.inputFields" :multiple="scene?.input === 'multi'" filterable collapse-tags collapse-tags-tooltip
                         :teleported="false" placeholder="选择 AI 依据的字段" class="afe-sel">
                <template v-if="scene?.input !== 'multi' && selectedInput" #prefix><StIcon :name="iconOf(selectedInput)" :size="15" /></template>
                <el-option v-for="f in inputCandidates" :key="f.field_name" :value="f.field_name" :label="f.label">
                  <span class="afe-opt"><StIcon :name="iconOf(f)" :size="15" />{{ f.label }}</span>
                </el-option>
              </el-select>
            </div>
            <div class="afe-col narrow">
              <div class="afe-l">输出类型</div>
              <el-select v-model="draft.outputType" :teleported="false" class="afe-sel" @change="onTypeChange">
                <template #prefix><StIcon :name="draft.outputType" :size="15" /></template>
                <el-option v-for="t in OUT_TYPES" :key="t.v" :value="t.v" :label="t.l">
                  <span class="afe-opt"><StIcon :name="t.v" :size="15" />{{ t.l }}</span>
                </el-option>
              </el-select>
            </div>
          </div>

          <!-- AI 指令 -->
          <div class="afe-sec">
            <div class="afe-l">AI 指令
              <span v-if="!scene?.local" class="afe-link" @click="promptEdit = !promptEdit">{{ promptEdit ? '完成' : '编辑' }}</span>
            </div>
            <div v-if="scene?.local" class="afe-prompt muted">本地计算，不调用大模型、不消耗 AI 次数</div>
            <el-input v-else-if="promptEdit" v-model="draft.systemPrompt" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }"
                      placeholder="你是一个……&#10;任务：……&#10;输入：……" />
            <div v-else class="afe-prompt" :class="{ folded: longPrompt && !promptOpen }" @click="promptOpen = !promptOpen">
              {{ draft.systemPrompt || '（未设置）' }}
              <span v-if="longPrompt && !promptOpen" class="afe-prompt-more">展开</span>
            </div>
          </div>

          <!-- 选项（单选/多选） -->
          <div v-if="isSelectOut" class="afe-sec">
            <div class="afe-l">选项
              <span class="afe-flex" />
              <el-checkbox v-model="onlyExisting" size="small">仅使用已有选项</el-checkbox>
              <el-tooltip :hide-after="0" content="勾选后 AI 只从这些选项中选择；不勾选时遇到都不合适的情况会自动新建选项" placement="top">
                <StIcon name="info" :size="14" class="afe-tip" /></el-tooltip>
            </div>
            <div class="afe-opts">
              <div v-for="(o, i) in draft.options" :key="o.id" v-reorder-feedback="{ indicator: dropCls(i), horizontal: true }" class="afe-opt-row" :class="dropCls(i)" draggable="true"
                   @dragstart="dragI = i" @dragover.prevent="overI = i" @drop.prevent="dropOpt(i)" @dragend="dragI = overI = null">
                <span class="afe-drag st-icon-action"><StIcon name="drag" :size="14" /></span>
                <span class="afe-color" :style="{ background: optionColor(o.color).value }" data-smart-tip="切换颜色" @click="cycleColor(o)" />
                <input v-model="o.label" class="afe-opt-in" />
                <span class="afe-del st-icon-action" data-smart-tip="删除" @click="removeOption(i)"><StIcon name="close" :size="13" /></span>
              </div>
              <div class="afe-add" @click="addOption"><StIcon name="plus" :size="14" />添加选项</div>
            </div>
          </div>

          <!-- 效果预览 -->
          <div class="afe-sec">
            <div class="afe-l">效果预览
              <span v-if="stale" class="afe-stale">设置已修改</span>
              <span class="afe-flex" />
              <span class="afe-link" :class="{ off: trying }" @click="tryRun">
                <StIcon name="sync" :size="13" :class="{ spin: trying }" />{{ trying ? '试算中…' : '按当前设置试算' }}</span>
            </div>
            <AiSceneCard bare :fields="fields" :preview="preview" :out-label="draft.label" :output-type="draft.outputType" feedback />
          </div>

          <div class="afe-auto">
            <el-checkbox v-model="draft.autoUpdate" size="small">自动更新</el-checkbox>
            <span class="afe-hint">新增记录或依据字段变化时，自动重新生成该行</span>
          </div>
        </div>

      </div>
      <!-- 让 AI 修改（固定在底部，不随表单滚走） -->
      <div class="afe-ai">
        <div v-if="running" class="afe-running">
          <span class="afe-spin" />AI 正在调整设置…
          <span class="afe-stop st-icon-action" data-smart-tip="停止" @click="stopRun"><StIcon name="stop" :size="16" /></span>
        </div>
        <AiComposer v-else ref="composerRef" compact :fields="composeFields" placeholder="让 AI 修改：描述你的要求，如「只分 3 类」「输出不超过 20 字」"
                    @send="onAiModify" />
        <div v-if="undoSnap" class="afe-banner">
          <StIcon name="check" :size="14" />AI 已按要求更新了上面的设置，确认无误后保存
          <span class="afe-link" @click="undo">撤销</span>
        </div>
        <div v-if="error" class="afe-error"><StIcon name="warn" :size="14" />{{ error }}</div>
      </div>
      <div class="afe-foot">
        <span class="afe-genall" :class="{ off: !canSave }" @click="canSave && save('all')">
          <span class="afe-logo sm"><StIcon name="sparkle" :size="10" /></span>保存并生成全部</span>
        <span class="afe-flex" />
        <button class="afe-btn" @click="emit('close')">取消</button>
        <button class="afe-btn primary" :disabled="!canSave" @click="save(null)">保存</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { vReorderFeedback } from '../../../smart/utils/reorderFeedback.js'
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import AiBadge from './AiBadge.vue'
import AiComposer from './AiComposer.vue'
import AiSceneCard from './AiSceneCard.vue'
import { OPTION_COLORS, optionColor } from '../../../smart/registry/fieldRegistry.js'
import { smartAiConfigure, smartAiPreview, smartAiScenes } from '../../../api/index.js'

const props = defineProps({
  x: { type: Number, default: 200 },
  y: { type: Number, default: 100 },
  tableId: { type: Number, required: true },
  fields: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  field: { type: Object, required: true },
})
const emit = defineEmits(['close', 'save', 'run'])

const OUT_TYPES = [{ v: 'text', l: '文本' }, { v: 'number', l: '数字' }, { v: 'singleSelect', l: '单选' },
                   { v: 'multiSelect', l: '多选' }, { v: 'checkbox', l: '复选框' }]
const NO_INPUT = ['cvRandom', 'cvUuid', 'cvPassword']

const scenes = ref([])
const sceneKey = ref('custom')
const scene = computed(() => scenes.value.find(s => s.key === sceneKey.value) || null)
const moreOpen = ref(false)
const promptEdit = ref(false)
const promptOpen = ref(false)
const running = ref(false)
const trying = ref(false)
const error = ref('')
const undoSnap = ref(null)
const triedPreview = ref(null)   // 试算 / AI 修改得到的预览
const stale = ref(false)
const composerRef = ref(null)
let abortCtl = null

const draft = reactive({ label: '', title: '', desc: '', inputLabel: '', systemPrompt: '', inputFields: null,
                         outputType: 'text', options: [], autoUpdate: true, allowNewOptions: true, instruction: '' })
const originalOptionIds = new Set((props.field.options?.options || []).map(o => o.id))

const iconOf = fieldIconName
const posStyle = computed(() => {
  const top = Math.max(8, Math.min(props.y, window.innerHeight - 760))
  return { left: `${Math.max(8, Math.min(props.x - 600, window.innerWidth - 612))}px`, top: `${top}px`,
           maxHeight: `${window.innerHeight - top - 12}px` }
})

// 点面板以外关闭（排除下拉/提示等挂到 body 的浮层）
function onDocDown(e) {
  if (e.target.closest?.('.afe, .el-popper, .el-select-dropdown, .el-message-box, .el-overlay')) return
  emit('close')
}
onMounted(() => setTimeout(() => document.addEventListener('mousedown', onDocDown, true), 0))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocDown, true))

onMounted(async () => {
  const r = await smartAiScenes().catch(() => ({ scenes: [] }))
  scenes.value = r.scenes
  const c = props.field.options || {}
  sceneKey.value = scenes.value.some(s => s.key === c.scene) ? c.scene : 'custom'
  const sc = scene.value
  const firstIn = props.fields.find(f => f.field_name === (c.inputFields || [])[0])
  Object.assign(draft, {
    label: props.field.label, title: c.title || props.field.label,
    desc: c.desc || (sc?.desc || '').replace('{input}', `[${firstIn?.label || '文本'}]`),
    inputLabel: c.inputLabel || '',
    systemPrompt: c.systemPrompt || (c.scene === 'custom' || !c.scene ? (c.prompt || '') : (sc?.prompt || '')),
    inputFields: sc?.input === 'multi' ? [...(c.inputFields || [])] : ((c.inputFields || [])[0] || null),
    outputType: c.outputType || sc?.outputType || 'text', options: JSON.parse(JSON.stringify(c.options || [])),
    autoUpdate: c.autoUpdate !== false, allowNewOptions: c.allowNewOptions !== false, instruction: c.instruction || '',
  })
  await nextTick()
  stale.value = false
})

// 说明：[字段名] → chip
const descSegments = computed(() => {
  const byLabel = new Map(props.fields.map(f => [f.label, f]))
  const out = []
  const re = /\[([^\]]+)\]/g
  const d = draft.desc || ''
  let last = 0
  let m
  while ((m = re.exec(d))) {
    if (m.index > last) out.push({ text: d.slice(last, m.index) })
    out.push({ chip: true, text: m[1], icon: iconOf(byLabel.get(m[1])) })
    last = m.index + m[0].length
  }
  if (last < d.length) out.push({ text: d.slice(last) })
  return out
})

const inputCandidates = computed(() => {
  const t = scene.value?.input
  if (t === 'image') return props.fields.filter(f => f.field_type === 'image')
  if (t === 'file') return props.fields.filter(f => f.field_type === 'file')
  return props.fields.filter(f => f.field_name !== props.field.field_name && f.field_type !== 'ai')
})
const composeFields = computed(() => props.fields.filter(f => f.field_name !== props.field.field_name))
const selectedInput = computed(() => props.fields.find(f => f.field_name === draft.inputFields))
const inputList = computed(() => (Array.isArray(draft.inputFields) ? draft.inputFields : (draft.inputFields ? [draft.inputFields] : [])))
// 指令超过 3 行（或很长）才折叠
const longPrompt = computed(() => (draft.systemPrompt || '').split('\n').length > 3 || (draft.systemPrompt || '').length > 120)
const isSelectOut = computed(() => ['singleSelect', 'multiSelect'].includes(draft.outputType))
const onlyExisting = computed({ get: () => !draft.allowNewOptions, set: (v) => { draft.allowNewOptions = !v } })
const canSave = computed(() => !!draft.label.trim() && (inputList.value.length > 0 || NO_INPUT.includes(sceneKey.value)))

function currentConfig() {
  return {
    ...(props.field.options || {}),
    scene: sceneKey.value, inputFields: inputList.value, title: draft.label.trim() || draft.title, desc: draft.desc,
    inputLabel: draft.inputLabel, systemPrompt: draft.systemPrompt, outputType: draft.outputType,
    options: draft.options.filter(o => String(o.label || '').trim()).map((o, i) => ({ ...o, label: String(o.label).trim(), order: i })),
    autoUpdate: draft.autoUpdate, allowNewOptions: draft.allowNewOptions, instruction: draft.instruction,
  }
}

// ---------- 效果预览：默认取真实数据的当前值（优先已生成的行）；试算 / AI 修改后换成试算结果 ----------
const filled = (v) => v != null && v !== '' && !(Array.isArray(v) && !v.length)
const preview = computed(() => {
  if (triedPreview.value) return triedPreview.value
  const fn = props.field.field_name
  const inputs = inputList.value
  const withInput = props.rows.filter(r => !r.__rowType && inputs.some(x => filled(r[x])))
  const rows = [...withInput.filter(r => filled(r[fn])), ...withInput.filter(r => !filled(r[fn]))].slice(0, 3)
  return {
    config: { ...currentConfig(), options: [...draft.options, ...(props.field.options?.options || []).filter(o => !draft.options.some(d => d.id === o.id))] },
    rows: rows.map(r => ({ inputs: Object.fromEntries(inputs.map(x => [x, r[x]])), output: r[fn],
                           loading: ['pending', 'running'].includes(r.__ai?.[fn]?.status), error: r.__ai?.[fn]?.error || null })),
  }
})
watch(() => [draft.inputFields, draft.outputType, draft.systemPrompt, draft.allowNewOptions], () => {
  if (triedPreview.value || props.field) stale.value = true
}, { deep: true })

function adoptOptions(opts) {
  // 试算 / AI 修改提出的新选项并入草稿（保存后落库）
  for (const o of opts || []) if (!draft.options.some(d => d.id === o.id || d.label === o.label)) draft.options.push({ ...o })
}

async function tryRun() {
  if (trying.value || !canSave.value) return
  trying.value = true
  error.value = ''
  const cfg = currentConfig()
  triedPreview.value = { config: cfg, rows: preview.value.rows.map(r => ({ ...r, loading: true })) }
  try {
    const r = await smartAiPreview(props.tableId, { config: cfg, field_name: props.field.field_name })
    adoptOptions(r.config.options)
    triedPreview.value = { config: { ...r.config, options: draft.options }, rows: r.preview }
    await nextTick()
    stale.value = false
  } catch (e) {
    triedPreview.value = null
    error.value = e.message || '试算失败'
  } finally {
    trying.value = false
  }
}

// ---------- 让 AI 修改：直接改写设置，可撤销 ----------
async function onAiModify({ inputFields, instruction }) {
  if (!instruction && !inputFields.length) return
  error.value = ''
  const snap = { draft: JSON.parse(JSON.stringify(draft)), preview: triedPreview.value }
  running.value = true
  const ctl = new AbortController()
  abortCtl = ctl
  try {
    const r = await smartAiConfigure(props.tableId, {
      scene: sceneKey.value, instruction, input_fields: inputFields.length ? inputFields : inputList.value,
      base: currentConfig(), field_name: props.field.field_name,
    }, { signal: ctl.signal })
    if (ctl.signal.aborted) return
    const c = r.config
    Object.assign(draft, {
      desc: c.desc || draft.desc, inputLabel: c.inputLabel || draft.inputLabel, systemPrompt: c.systemPrompt || draft.systemPrompt,
      inputFields: scene.value?.input === 'multi' ? [...c.inputFields] : (c.inputFields[0] || null),
      outputType: c.outputType, options: JSON.parse(JSON.stringify(c.options || [])),
      instruction: [draft.instruction, instruction].filter(Boolean).join('；'),
    })
    triedPreview.value = { config: { ...c }, rows: r.preview }
    undoSnap.value = snap
    composerRef.value?.clear()
    await nextTick()
    stale.value = false
  } catch (e) {
    if (!ctl.signal.aborted) error.value = e.message || 'AI 修改失败，请重试'
  } finally {
    if (abortCtl === ctl) { running.value = false; abortCtl = null }
  }
}
function stopRun() { abortCtl?.abort(); running.value = false }
function undo() {
  const s = undoSnap.value
  if (!s) return
  Object.assign(draft, s.draft)
  triedPreview.value = s.preview
  undoSnap.value = null
}

// ---------- 选项编辑 ----------
function onTypeChange(t) {
  if (['singleSelect', 'multiSelect'].includes(t) && !draft.options.length && scene.value?.defaultOptions) {
    draft.options = scene.value.defaultOptions.map((l, i) => ({ id: `opt_${i + 1}`, label: l, color: OPTION_COLORS[i % OPTION_COLORS.length].key, order: i }))
  }
}
function addOption() {
  const n = draft.options.length
  draft.options.push({ id: `opt_${Date.now().toString(36)}`, label: `选项${n + 1}`, color: OPTION_COLORS[n % OPTION_COLORS.length].key, order: n })
}
function removeOption(i) { draft.options.splice(i, 1) }
function cycleColor(o) {
  const i = OPTION_COLORS.findIndex(c => c.key === o.color)
  o.color = OPTION_COLORS[(i + 1) % OPTION_COLORS.length].key
}
const dragI = ref(null)
const overI = ref(null)
const dropCls = (i) => (dragI.value === null || overI.value !== i || dragI.value === i ? '' : dragI.value > i ? 'drop-before' : 'drop-after')
function dropOpt(i) {
  const from = dragI.value
  dragI.value = overI.value = null
  if (from === null || from === i) return
  const [m] = draft.options.splice(from, 1)
  draft.options.splice(i, 0, m)
}

function save(runMode) {
  const cfg = currentConfig()
  if (isSelectOut.value) {   // 明确删掉的旧选项：告诉后端别补回（未出现在这里的旧选项若仍被单元格使用会被保留）
    const now = new Set(cfg.options.map(o => o.id))
    cfg.removedOptionIds = [...originalOptionIds].filter(id => !now.has(id))
  }
  emit('save', { label: draft.label.trim(), config: cfg, run: runMode })
}
function run(scope) { moreOpen.value = false; emit('run', { scope }) }
</script>

<style scoped>
/* 非模态：遮罩层不拦截鼠标（表格仍可滚动/点击），只有面板本身可交互 */
.afe-mask { position: fixed; inset: 0; z-index: 3000; pointer-events: none; }
.afe { pointer-events: auto; }
.afe { position: fixed; width: 600px; display: flex; flex-direction: column; border-radius: 18px; box-sizing: border-box;
       background: linear-gradient(170deg, #ECE6FF 0%, #F8EEF3 70px, #F4F5F7 150px); box-shadow: 0 8px 32px rgba(0, 0, 0, .16);
       --el-color-primary: var(--st-primary); }
.afe-head { display: flex; align-items: center; gap: 8px; padding: 16px 16px 4px 20px; }
.afe-logo { width: 22px; height: 22px; border-radius: 6px; background: linear-gradient(135deg, #8B6CF6, #E96BD8); color: #fff;
            display: inline-flex; align-items: center; justify-content: center; flex: none; }
.afe-logo.sm { width: 16px; height: 16px; border-radius: 4px; }
.afe-name { min-width: 4em; max-width: 380px; field-sizing: content; font-size: var(--st-font-size-title); font-weight: 700; color: var(--st-text-1); border: 1px solid transparent;
            border-radius: 6px; padding: 3px 6px; background: transparent; outline: none; }
.afe-name:hover { border-color: rgba(31, 35, 41, .12); background: rgba(255, 255, 255, .6); }
.afe-name:focus { border-color: var(--st-primary); background: #fff; }
.afe-flex { flex: 1; }
.afe-icon { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 6px; cursor: pointer; color: var(--st-text-2); }
.afe-icon:hover { background: rgba(31, 35, 41, .08); color: var(--st-text-2); }
.afe-more-wrap { position: relative; }
.afe-menu { position: absolute; right: 0; top: 34px; z-index: 5; background: #fff; border-radius: 8px; box-shadow: 0 6px 24px rgba(0, 0, 0, .14); padding: 6px; width: 170px; }
.afe-mi { display: flex; align-items: center; gap: 8px;  padding: 0 10px; border-radius: 6px; font-size: var(--st-font-size); cursor: pointer; color: var(--st-text-2);  height: var(--st-list-item-height); box-sizing: border-box; }
.afe-mi:hover { background: #F2F3F5; }
.afe-sub { padding: 0 24px 12px 56px; font-size: var(--st-font-size); line-height: 24px; color: var(--st-text-3); }
.afe-chip { display: inline-flex; align-items: center; gap: 3px; height: 20px; line-height: 20px; padding: 0 5px; margin: 0 2px;
            background: rgba(255, 255, 255, .8); border-radius: 4px; color: var(--st-text-2); vertical-align: 1px; }
.afe-scene { margin-left: 6px; color: #B5B9C0; }
.afe-body { flex: 1; min-height: 0; overflow-y: auto; padding: 0 12px; }
.afe-card { background: #fff; border-radius: 14px; padding: 18px 20px 16px; display: flex; flex-direction: column; gap: 18px; }
.afe-row2 { display: flex; gap: 12px; }
.afe-col { flex: 1; min-width: 0; }
.afe-col.narrow { flex: 0 0 150px; }
.afe-l { display: flex; align-items: center; gap: 8px; font-size: var(--st-font-size); font-weight: 600; color: var(--st-text-1); margin-bottom: 8px; }
.afe-hint { font-size: var(--st-font-size); font-weight: 400; color: #A8ADB5; }
.afe-sel { width: 100%; }
.afe-sel :deep(.el-select__wrapper) { min-height: 38px; border-radius: 8px; }
.afe-sel :deep(.el-select__prefix) { color: var(--st-text-2); }
.afe-opt { display: inline-flex; align-items: center; gap: 8px; }
.afe-opt .st-icon { color: var(--st-text-2); }
.afe-link { display: inline-flex; align-items: center; gap: 4px; font-size: var(--st-font-size); font-weight: 400; color: var(--st-primary); cursor: pointer; }
.afe-link:hover { text-decoration: underline; }
.afe-link.off { color: var(--st-text-3); cursor: default; text-decoration: none; }
.afe-link .spin { animation: afe-rot .8s linear infinite; }
.afe-prompt { position: relative; background: #F5F6F7; border-radius: 8px; padding: 10px 14px; font-size: var(--st-font-size); line-height: 1.75;
              color: var(--st-text-2); white-space: pre-wrap; cursor: pointer; }
.afe-prompt.folded { max-height: 70px; overflow: hidden; }
.afe-prompt.folded::after { content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 28px; border-radius: 0 0 8px 8px;
                            background: linear-gradient(rgba(245, 246, 247, 0), #F5F6F7 80%); }
.afe-prompt-more { position: absolute; right: 12px; bottom: 6px; z-index: 1; font-size: var(--st-font-size); color: var(--st-primary); }
.afe-prompt.muted { color: var(--st-text-3); cursor: default; }
.afe-tip { color: var(--st-text-3); cursor: help; }
.afe-l :deep(.el-checkbox__label) { font-weight: 400; color: var(--st-text-2); font-size: var(--st-font-size); }
.afe-opts { display: flex; flex-wrap: wrap; gap: 8px; }
.afe-opt-row { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 6px 0 4px; border: 1px solid #E5E6E8; border-radius: 8px;
               background: #fff; border-left-width: 1px; }
.afe-drag { color: #C9CDD4; cursor: grab; display: inline-flex; }
.afe-color { width: 14px; height: 14px; border-radius: 3px; cursor: pointer; flex: none; }
.afe-opt-in { width: 7em; min-width: 3em; border: none; outline: none; font-size: var(--st-font-size); color: var(--st-text-2); background: transparent; field-sizing: content; }
.afe-del { display: inline-flex; color: #B5B9C0; cursor: pointer; padding: 2px; border-radius: 4px; }
.afe-del:hover { color: var(--el-color-danger); background: #FDECEC; }
.afe-add { display: inline-flex; align-items: center; gap: 4px; height: 32px; padding: 0 10px; border: 1px dashed #C9CDD4; border-radius: 8px;
           font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.afe-add:hover { border-color: var(--st-primary); color: var(--st-primary); }
.afe-stale { font-size: var(--st-font-size); font-weight: 400; color: #B7791F; background: #FFF7E6; border-radius: 4px; padding: 0 6px; }
.afe-auto { display: flex; align-items: center; gap: 8px; }
.afe-auto :deep(.el-checkbox__label) { font-size: var(--st-font-size); color: var(--st-text-2); }
.afe-ai { flex: none; padding: 10px 12px 0; }
.afe-running { display: flex; align-items: center; gap: 10px; height: 58px; padding: 0 12px 0 18px; background: #fff; border-radius: 16px;
               font-size: var(--st-font-size); color: var(--st-text-2); }
.afe-spin { width: 16px; height: 16px; border-radius: 50%; border: 2.5px solid #D9DBDF; border-top-color: #8F959E; animation: afe-rot .8s linear infinite; }
@keyframes afe-rot { to { transform: rotate(360deg); } }
.afe-stop { margin-left: auto; width: 36px; height: 36px; border-radius: 8px; background: #F2F3F5; display: inline-flex; align-items: center;
            justify-content: center; cursor: pointer; }
.afe-banner { display: flex; align-items: center; gap: 6px; margin: 8px 4px 0; font-size: var(--st-font-size); color: #2BA471; }
.afe-banner .afe-link { margin-left: auto; }
.afe-error { display: flex; align-items: center; gap: 6px; margin: 8px 4px 0; font-size: var(--st-font-size); color: var(--el-color-danger); }
.afe-foot { display: flex; align-items: center; gap: 10px; padding: 12px 20px 16px; }
.afe-genall { display: inline-flex; align-items: center; gap: 6px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.afe-genall:hover { color: var(--st-text-2); }
.afe-genall.off { opacity: .5; cursor: not-allowed; }
.afe-btn { height: 34px; padding: 0 20px; border-radius: 8px; border: 1px solid #E3E5E8; background: #fff; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.afe-btn:hover { background: #F5F6F7; }
.afe-btn.primary { background: var(--st-primary); border-color: var(--st-primary); color: #fff; }
.afe-btn.primary:hover { background: #255BD0; }
.afe-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
