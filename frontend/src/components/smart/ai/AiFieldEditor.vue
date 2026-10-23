<template>
  <!-- 新建、生成与编辑共用表单；AI 结果直接更新草稿，保存时选择生成范围。 -->
  <div ref="layerRef" class="afe-mask">
    <div ref="panelRef" v-panel-drag="{ handle: '.afe-head' }" class="afe" @keydown.esc="emit('close')">
      <!-- 头部：名称即标题，直接可改 -->
      <div class="afe-head">
        <span class="afe-logo"><StIcon name="sparkle" :size="13" /></span>
        <input v-model="draft.label" class="st-control st-control--native afe-name" placeholder="字段名称" maxlength="30" />
        <AiBadge plain />
        <span class="afe-flex" />
        <span v-if="!isNew" class="afe-more-wrap">
          <span class="afe-icon st-icon-action" aria-label="更多" @click="moreOpen = !moreOpen"><StIcon name="more-h" :size="18" /></span>
          <div v-if="moreOpen" class="afe-menu" @mouseleave="moreOpen = false">
            <div class="afe-mi" role="button" @click="run('all')"><StIcon name="sparkle" :size="14" />重新生成全部</div>
            <div class="afe-mi" role="button" @click="run('empty')"><StIcon name="row-add" :size="14" />仅生成空白行</div>
            <div class="afe-mi" role="button" @click="run('failed')"><StIcon name="sync" :size="14" />重新生成失败行</div>
          </div>
        </span>
        <span class="afe-icon st-icon-action" aria-label="关闭" @click="emit('close')"><StIcon name="close" :size="16" /></span>
      </div>
      <div class="afe-body">
        <div class="afe-card">
          <div class="afe-row2">
            <div class="afe-col">
            <div class="afe-l">AI 场景<span class="afe-hint">选择模板，或描述自己的处理规则</span></div>
            <el-select :model-value="sceneKey" filterable class="st-control afe-sel" :disabled="running || trying" :popper-options="selectPopperOptions" @change="chooseScene">
              <el-option-group v-for="group in sceneGroups" :key="group.key" :label="group.label">
                <el-option v-for="s in group.scenes" :key="s.key" :value="s.key" :label="s.label" :disabled="s.disabled" />
              </el-option-group>
            </el-select>
            </div>
            <div class="afe-col narrow">
              <div class="afe-l">输出类型</div>
              <el-select v-model="draft.outputType" :teleported="true" :popper-options="selectPopperOptions" class="st-control afe-sel" @change="onTypeChange">
                <template #prefix><StIcon :name="draft.outputType" :size="15" /></template>
                <el-option v-for="t in OUT_TYPES" :key="t.v" :value="t.v" :label="t.l">
                  <span class="afe-opt"><StIcon :name="t.v" :size="15" />{{ t.l }}</span>
                </el-option>
              </el-select>
            </div>
          </div>
            <div v-if="scene?.desc" class="afe-scene-desc">{{ scene.desc.replace('{input}', selectedInput?.label || '所选字段') }}</div>
      <div class="afe-ai">
        <div class="afe-l">处理要求<span class="afe-hint">描述你希望得到的结果</span></div>
        <div v-if="running" class="afe-running">
          <span class="afe-spin" />AI 正在生成配置和预览…
          <span class="afe-stop st-icon-action" aria-label="停止" @click="stopRun"><StIcon name="stop" :size="16" /></span>
        </div>
        <AiComposer v-show="!running" :key="sceneKey" ref="composerRef" :initial-text="initialInstruction" :initial-fields="initialFields" :fields="composeFields" :send-label="triedPreview || !isNew ? '更新预览' : '生成预览'" :allow-empty="!trying && (inputList.length > 0 || NO_INPUT.includes(sceneKey))" placeholder="描述处理规则、分类方式或输出长度；留空则使用场景默认规则。"
                    @change="onRequirementsChange" @send="onAiModify" />
        <div v-if="!inputList.length && !NO_INPUT.includes(sceneKey)" class="afe-field-hint">请插入要处理的字段</div>
        <div v-if="undoSnap" class="afe-banner">
          <StIcon name="check" :size="14" />预览已更新，确认效果后保存
          <span class="afe-link" @click="undo">撤销</span>
        </div>
        <div v-if="error" class="afe-error"><StIcon name="warn" :size="14" />{{ error }}</div>
        <div v-else-if="warning" class="afe-warning">{{ warning }}</div>
      </div>
          <!-- 效果预览 -->
          <div class="afe-sec">
            <div class="afe-l">效果预览
              <span v-if="stale" class="afe-stale">设置已修改</span>
            </div>
            <AiSceneCard bare :fields="fields" :preview="preview" :out-label="draft.label" :output-type="draft.outputType" />
          </div>

          <details class="afe-advanced">
            <summary>高级设置<span class="afe-hint">AI 指令、选项管理</span></summary>
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
                <input v-model="o.label" class="st-control st-control--small st-control--native afe-opt-in" />
                <span class="afe-del st-icon-action" aria-label="删除" @click="removeOption(i)"><StIcon name="close" :size="13" /></span>
              </div>
              <div class="st-button afe-add" @click="addOption"><StIcon name="plus" :size="14" />添加选项</div>
            </div>
          </div>

            <button class="st-button afe-btn afe-advanced-preview" :disabled="!canSave" @click="tryRun">{{ trying ? '试算中…' : '按高级设置更新预览' }}</button>
          </details>

          <div class="afe-auto">
            <el-checkbox v-model="draft.autoUpdate" size="small">自动更新</el-checkbox>
            <span class="afe-hint">新增记录或依据字段变化时，自动重新生成该行</span>
          </div>
        </div>

      </div>
      <div class="afe-foot">
        <el-select v-model="saveScope" class="st-control afe-save-scope" :disabled="running || trying" :popper-options="selectPopperOptions" aria-label="保存后生成范围">
          <el-option label="仅保存配置" value="none" />
          <el-option label="保存并生成前 5 行" value="first5" />
          <el-option label="保存并生成全部" value="all" />
        </el-select>
        <span class="afe-flex" />
        <button class="st-button st-button--large afe-btn" @click="emit('close')">取消</button>
        <button class="st-button st-button--large st-button--primary afe-btn primary" :disabled="!canSave" @click="save(saveScope)">{{ isNew ? '创建字段' : '保存' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { vReorderFeedback } from '../../../smart/utils/reorderFeedback.js'
import { vPanelDrag } from '../../../smart/utils/panelDrag.js'
import { useFloatingPanel } from '../../../smart/utils/floatingPanel.js'
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import AiBadge from './AiBadge.vue'
import AiComposer from './AiComposer.vue'
import AiSceneCard from './AiSceneCard.vue'
import { OPTION_COLORS, optionColor } from '../../../smart/registry/fieldRegistry.js'
import { smartAiConfigure, smartAiPreview, smartAiScenes } from '../../../api/index.js'

const props = defineProps({
  at: { type: Object, default: null },
  x: { type: Number, default: 200 },
  y: { type: Number, default: 100 },
  tableId: { type: Number, required: true },
  fields: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  field: { type: Object, default: () => ({}) },
  presetLabel: { type: String, default: '' },
  totalRows: { type: Number, default: 0 },
})
const emit = defineEmits(['close', 'save', 'run', 'write-formula'])
const isNew = computed(() => !props.field.field_name)
const saveScope = ref(isNew.value ? 'first5' : 'none')

const OUT_TYPES = [{ v: 'text', l: '文本' }, { v: 'number', l: '数字' }, { v: 'singleSelect', l: '单选' },
                   { v: 'multiSelect', l: '多选' }, { v: 'checkbox', l: '复选框' }]
const NO_INPUT = ['cvRandom', 'cvUuid', 'cvPassword']
const selectPopperOptions = { strategy: 'fixed', modifiers: [{ name: 'preventOverflow', options: { padding: 12, altAxis: true, tether: false } }] }

const scenes = ref([])
const categories = ref([])
const sceneGroups = computed(() => [...categories.value.map(c => ({ ...c, scenes: scenes.value.filter(s => s.category === c.key && s.key !== 'custom') })),
  { key: 'custom', label: '自定义', scenes: scenes.value.filter(s => s.key === 'custom') }].filter(c => c.scenes.length))
const sceneKey = ref('custom')
const scene = computed(() => scenes.value.find(s => s.key === sceneKey.value) || null)
const moreOpen = ref(false)
const promptEdit = ref(false)
const promptOpen = ref(false)
const running = ref(false)
const trying = ref(false)
const error = ref('')
const warning = ref('')
const undoSnap = ref(null)
const triedPreview = ref(null)   // 试算 / AI 修改得到的预览
const stale = ref(false)
const composerRef = ref(null)
const initialInstruction = ref('')
const initialFields = ref([])
let abortCtl = null

const draft = reactive({ label: '', title: '', desc: '', inputLabel: '', systemPrompt: '', inputFields: null,
                         outputType: 'text', options: [], autoUpdate: true, allowNewOptions: true, instruction: '' })
const originalOptionIds = new Set((props.field.options?.options || []).map(o => o.id))

const iconOf = fieldIconName
const panelRef = ref(null)
const layerRef = ref(null)
const refreshPanel = useFloatingPanel(() => panelRef.value, () => layerRef.value)
function placePanel() {
  if (panelRef.value) Object.assign(panelRef.value.style, {
    left: `${Math.max(12, props.at ? props.at.x + 4 : props.x - 600)}px`,
    top: `${Math.max(12, props.at ? props.at.y + 4 : props.y)}px`,
  })
  return refreshPanel()
}
onMounted(placePanel)
watch(() => [props.at?.x, props.at?.y, props.x, props.y], placePanel, { flush: 'post' })

// 点面板以外关闭（排除下拉/提示等挂到 body 的浮层）
function onDocDown(e) {
  if (e.target.closest?.('.afe, .el-popper, .el-select-dropdown, .el-message-box, .el-overlay')) return
  emit('close')
}
onMounted(() => setTimeout(() => document.addEventListener('mousedown', onDocDown, true), 0))
onBeforeUnmount(() => { document.removeEventListener('mousedown', onDocDown, true); abortCtl?.abort() })

onMounted(async () => {
  const r = await smartAiScenes().catch(() => ({ scenes: [] }))
  scenes.value = r.scenes
  categories.value = r.categories || []
  const c = props.field.options || {}
  initialInstruction.value = c.instruction || ''
  initialFields.value = [...(c.inputFields || [])]
  sceneKey.value = scenes.value.some(s => s.key === c.scene) ? c.scene : 'custom'
  const sc = scene.value
  const firstIn = props.fields.find(f => f.field_name === (c.inputFields || [])[0])
  Object.assign(draft, {
    label: props.field.label || props.presetLabel || 'AI 字段', title: c.title || props.field.label || '',
    desc: c.desc || (sc?.desc || '').replace('{input}', `[${firstIn?.label || '文本'}]`),
    inputLabel: c.inputLabel || '',
    systemPrompt: c.systemPrompt || (c.scene === 'custom' || !c.scene ? (c.prompt || '') : (sc?.prompt || '')),
    inputFields: [...(c.inputFields || [])],
    outputType: c.outputType || sc?.outputType || 'text', options: JSON.parse(JSON.stringify(c.options || [])),
    autoUpdate: c.autoUpdate !== false, allowNewOptions: c.allowNewOptions !== false, instruction: c.instruction || '',
  })
  await nextTick()
  stale.value = false
})

function chooseScene(key) {
  const next = scenes.value.find(s => s.key === key)
  if (!next || next.disabled) return
  if (next.action === 'formula') { emit('write-formula'); return }
  sceneKey.value = key
  draft.desc = next.desc || ''
  draft.systemPrompt = next.prompt || ''
  draft.outputType = next.outputType || 'text'
  draft.inputFields = []
  draft.options = []
  draft.instruction = ''
  initialInstruction.value = ''
  initialFields.value = []
  if (isNew.value && !props.presetLabel) draft.label = next.label
  onTypeChange(draft.outputType)
  triedPreview.value = null
  undoSnap.value = null
  error.value = ''
  warning.value = ''
}

// 说明：[字段名] → chip
const inputCandidates = computed(() => {
  const t = scene.value?.input
  if (t === 'image') return props.fields.filter(f => f.field_type === 'image')
  if (t === 'file') return props.fields.filter(f => f.field_type === 'file')
  return props.fields.filter(f => f.field_name !== props.field.field_name && f.field_type !== 'ai')
})
const composeFields = computed(() => inputCandidates.value.filter(f => f.field_name !== props.field.field_name))
const selectedInput = computed(() => props.fields.find(f => f.field_name === inputList.value[0]))
const inputList = computed(() => (Array.isArray(draft.inputFields) ? draft.inputFields : (draft.inputFields ? [draft.inputFields] : [])))
// 指令超过 3 行（或很长）才折叠
const longPrompt = computed(() => (draft.systemPrompt || '').split('\n').length > 3 || (draft.systemPrompt || '').length > 120)
const isSelectOut = computed(() => ['singleSelect', 'multiSelect'].includes(draft.outputType))
const onlyExisting = computed({ get: () => !draft.allowNewOptions, set: (v) => { draft.allowNewOptions = !v } })
const canSave = computed(() => !running.value && !trying.value && !!draft.label.trim() && (scene.value?.local || !!draft.systemPrompt.trim()) && (inputList.value.length > 0 || NO_INPUT.includes(sceneKey.value)))

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
watch(() => [draft.inputFields, draft.instruction, draft.outputType, draft.systemPrompt, draft.allowNewOptions], () => {
  if (triedPreview.value || !isNew.value) stale.value = true
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
  if (running.value || trying.value || (!instruction && !inputFields.length && !inputList.value.length && !NO_INPUT.includes(sceneKey.value))) return
  error.value = ''
  if (!inputFields.length && !NO_INPUT.includes(sceneKey.value)) {
    error.value = '请插入要处理的字段'
    return
  }
  warning.value = ''
  const snap = { draft: JSON.parse(JSON.stringify(draft)), preview: triedPreview.value }
  running.value = true
  const ctl = new AbortController()
  abortCtl = ctl
  try {
    const r = await smartAiConfigure(props.tableId, {
      scene: sceneKey.value, instruction, input_fields: inputFields,
      base: currentConfig(), field_name: props.field.field_name,
    }, { signal: ctl.signal })
    if (ctl.signal.aborted) return
    warning.value = r.warning || ''
    const c = r.config
    Object.assign(draft, {
      label: isNew.value && !props.presetLabel ? (c.title || draft.label) : draft.label,
      desc: c.desc || draft.desc, inputLabel: c.inputLabel || draft.inputLabel, systemPrompt: c.systemPrompt || draft.systemPrompt,
      inputFields: [...inputFields],
      outputType: c.outputType, options: JSON.parse(JSON.stringify(c.options || [])),
      instruction: instruction || draft.instruction,
    })
    triedPreview.value = { config: { ...c }, rows: r.preview }
    undoSnap.value = snap
    await nextTick()
    stale.value = false
  } catch (e) {
    if (!ctl.signal.aborted) error.value = e.message || 'AI 修改失败，请重试'
  } finally {
    if (abortCtl === ctl) { running.value = false; abortCtl = null }
  }
}
function stopRun() { abortCtl?.abort(); running.value = false }
function onRequirementsChange({ inputFields, instruction }) {
  draft.inputFields = inputFields
  draft.instruction = instruction
}
function undo() {
  const s = undoSnap.value
  if (!s) return
  Object.assign(draft, s.draft)
  composerRef.value?.setContent(s.draft.instruction, s.draft.inputFields || [])
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
  if (!canSave.value) return
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
.afe-save-scope { width: 220px; max-width: 100%; }
.afe-warning { margin: 8px 4px 0; font-size: var(--st-font-size); color: #B7791F; }
.afe-scene-desc { font-size: var(--st-font-size); color: var(--st-text-3); line-height: 1.6; }
/* 非模态：遮罩层不拦截鼠标（表格仍可滚动/点击），只有面板本身可交互 */
.afe-mask { position: fixed; inset: 0; pointer-events: none; }
.afe { pointer-events: auto; max-width: calc(100vw - 24px); max-height: calc(100vh - 24px); overflow: auto; }
.afe-head, .afe-sub, .afe-foot { flex: none; }
.afe { position: fixed; width: 600px; display: flex; flex-direction: column; border-radius: 18px; box-sizing: border-box;
       background: linear-gradient(170deg, #ECE6FF 0%, #F8EEF3 70px, #F4F5F7 150px); box-shadow: 0 8px 32px rgba(0, 0, 0, .16);
       --el-color-primary: var(--st-primary); }
.afe-head { display: flex; align-items: center; gap: 8px; padding: 16px 16px 4px 20px; cursor: move; touch-action: none; }
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
.afe-ai { min-width: 0; }
.afe-field-hint { margin-top: 8px; font-size: var(--st-font-size); color: var(--st-text-3); }
.afe-head { padding-bottom: 16px; }
.afe-advanced { border-top: 1px solid #EBECEE; padding-top: 12px; }
.afe-advanced > summary { cursor: pointer; color: var(--st-text-2); font-size: var(--st-font-size); }
.afe-advanced > summary .afe-hint { margin-left: 12px; }
.afe-advanced > .afe-sec { margin-top: 16px; }
.afe-advanced-preview { margin-top: 16px; }
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
.afe-name { min-width: 0; flex-shrink: 1; }
.afe-icon, .afe-more-wrap { flex: none; }
.afe-prompt, .afe-sub, .afe-error { overflow-wrap: anywhere; }
.afe-foot { flex-wrap: wrap; }
@media (max-width: 540px) {
  .afe-head { padding: 12px 10px 4px; gap: 4px; }
  .afe-card { padding: 14px 12px; }
  .afe-row2 { flex-direction: column; }
  .afe-col.narrow { flex: auto; }
  .afe-l, .afe-auto, .afe-banner { flex-wrap: wrap; }
  .afe-foot { padding: 12px; gap: 8px; }
  .afe-btn { padding: 0 12px; }
}
@media (max-height: 600px) {
  /* 极矮视口改为整个表单滚动，保留底部操作的可达性。 */
  .afe-body { flex: none; overflow: visible; }
}
</style>
