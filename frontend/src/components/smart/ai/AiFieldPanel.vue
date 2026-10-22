<template>
  <!-- AI 字段（§10.1，对齐参照 docs/智慧表格/添加列/AI字段）。
       新建：场景市场（左详情 hover 预览 + 右市场）→ 选场景 →「添加 AI 字段」输入框（插入字段/补充描述）
             → 正在配置…（AI 生成标题/提示词/选项，并在真实数据前 3 行试算）→ 结果确认（使用 / 修改）
             → 使用：生成前 5 行 / 生成全部 / 仅保存配置。
       编辑已有 AI 字段见 AiFieldEditor（单面板表单）。 -->
  <div class="aip-mask" @mousedown.self="tryClose">
    <div class="aip" :style="posStyle" @keydown="onKey">
      <!-- ================= 左侧主面板 ================= -->
      <div class="aip-main" :class="{ wide: step === 'market' }">
        <!-- 头部 -->
        <div class="aip-head">
          <span v-if="showBack" class="aip-icon-btn st-icon-action" data-smart-tip="返回" @click="goBack"><StIcon name="back" :size="18" /></span>
          <span class="aip-logo"><StIcon name="sparkle" :size="13" /></span>
          <span class="aip-title">{{ headTitle }}</span>
          <AiBadge v-if="step === 'market'" plain />
        </div>

        <div class="aip-body">
          <!-- 自定义 AI 字段：空态引导 -->
          <div v-if="isCustom && !result" class="aip-custom-empty">
            <div class="aip-ce-t"><span class="aip-logo"><StIcon name="sparkle" :size="12" /></span>创建自定义 AI 字段</div>
            <div class="aip-ce-d">描述数据处理规则，AI 帮你完成提取和计算</div>
          </div>
          <!-- 结果确认：配置卡 -->
          <AiSceneCard v-else-if="result" :key="cardKey"
                       :desc="cardCfg.desc || (scene?.desc || '')" :input-field="defaultInput" :fields="fields"
                       :prompt="cardCfg.systemPrompt || scene?.prompt || ''" prompt-mode="collapse"
                       :preview="cardPreview" :out-label="cardCfg.title"
                       :output-type="cardCfg.outputType" feedback>
            <div v-if="result" class="aip-res-ops">
              <button class="aip-btn primary" @click="useResult">使用</button>
              <button class="aip-btn" @click="reviseResult">修改</button>
            </div>
          </AiSceneCard>
          <!-- 市场 hover 预览 / 输入阶段：场景卡 -->
          <template v-else-if="scene">
            <AiSceneCard :key="scene.key" :desc="scene.desc" :input-field="defaultInput" :fields="fields"
                         :prompt="scene.prompt" :prompt-mode="step === 'market' ? 'box' : 'collapse'"
                         :sample="scene.sample" :output-type="scene.outputType" :dim="step !== 'market'" />
            <div v-if="scene.disabled" class="aip-soon"><StIcon name="info" :size="14" />该场景需要联网或图像处理能力，即将上线</div>
            <div v-else-if="scene.local && step === 'market'" class="aip-soon ok"><StIcon name="check" :size="14" />本地计算，不消耗 AI 次数</div>
          </template>
        </div>

        <!-- 底部：输入框 / 配置中 -->
        <div v-if="step !== 'market' && !result" class="aip-bottom">
          <div v-if="running" class="aip-running">
            <span class="aip-spin" /><span>正在配置...</span>
            <span class="aip-stop st-icon-action" data-smart-tip="停止" @click="stopRun"><StIcon name="stop" :size="18" /></span>
          </div>
          <AiComposer v-else ref="composerRef" :fields="fields"
                      :hint="revising || isCustom ? '' : `请提供要「${scene?.label}」的内容`"
                      :placeholder="revising ? '描述修改要求' : '选择字段或补充描述'"
                      :allow-empty="revising" @send="onSend" />
          <div v-if="error" class="aip-error"><StIcon name="warn" :size="14" />{{ error }}</div>
          <div v-else-if="warning" class="aip-warn">{{ warning }}</div>
        </div>
      </div>

      <!-- ================= 右侧：场景市场 ================= -->
      <div v-if="step === 'market'" class="aip-market">
        <div class="aip-search"><span class="aip-icon-btn st-icon-action" data-smart-tip="关闭" @click="emit('close')"><StIcon name="back" :size="18" /></span>
          <input ref="searchRef" v-model="kw" class="aip-search-in" placeholder="搜索场景" /></div>
        <div class="aip-tabs-wrap">
          <div ref="tabsRef" class="aip-tabs">
            <span v-for="c in categories" :key="c.key" class="aip-tab" :class="{ on: tab === c.key }" @click="jumpTo(c.key)">
              <StIcon :name="c.icon || 'star'" :size="14" />{{ c.label }}</span>
          </div>
          <span class="aip-tabs-more st-icon-action" data-smart-tip="更多分类" @click="scrollTabs"><StIcon name="caret-down" :size="12" class="rot" /></span>
        </div>
        <div ref="gridRef" class="aip-grid-wrap" @scroll="onGridScroll">
          <div v-for="sec in sections" :key="sec.key" class="aip-sec-wrap" :data-cat="sec.key">
            <div class="aip-sec">{{ sec.label }}</div>
            <div class="aip-grid">
              <div v-for="s in sec.scenes" :key="s.key" class="aip-scene" :class="{ on: hoverKey === s.key, off: s.disabled }"
                   :data-key="s.key" @mouseenter="hoverKey = s.key" @click="choose(s)">
                <span class="aip-scene-l">{{ s.label }}</span>
                <span v-if="s.disabled" class="aip-scene-tag">即将上线</span>
              </div>
            </div>
          </div>
          <div v-if="!sections.length" class="aip-none">没有匹配的场景，试试「自定义 AI 字段」</div>
        </div>
        <div class="aip-custom" :class="{ on: hoverKey === 'custom' }" @mouseenter="hoverKey = 'custom'" @click="choose(sceneOf('custom'))">自定义 AI 字段</div>
        <div class="aip-foot"><span><b>↑↓</b> 选择</span><span><b>↵</b> 完成</span>
          <span v-if="quota && quota.limit != null" class="aip-quota">本月 AI 次数 {{ quota.used }} / {{ quota.limit }}</span></div>
      </div>

    </div>

    <!-- 使用确认（参照 AI-分类-使用后选择.png） -->
    <div v-if="useDlg" class="aip-use-mask" @mousedown.self="useDlg = false">
      <div class="aip-use">
        <div class="aip-use-h"><StIcon name="info" :size="20" class="aip-use-ico" /><span>使用 AI 字段生成内容</span>
          <span class="aip-icon-btn st-icon-action" @click="useDlg = false"><StIcon name="close" :size="16" /></span></div>
        <div class="aip-use-d">将使用 AI 生成并替换当前内容，生成全部 {{ totalRows }} 行可能需要较长时间。</div>
        <button class="aip-btn primary block" @click="finishNew('first5')">生成前 5 行</button>
        <button class="aip-btn block" @click="finishNew('all')">生成全部</button>
        <button class="aip-btn block" @click="finishNew('none')">仅保存配置</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import AiBadge from './AiBadge.vue'
import AiComposer from './AiComposer.vue'
import AiSceneCard from './AiSceneCard.vue'
import { smartAiConfigure, smartAiQuota, smartAiScenes } from '../../../api/index.js'

const props = defineProps({
  x: { type: Number, default: 200 },
  y: { type: Number, default: 100 },
  tableId: { type: Number, required: true },
  fields: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  totalRows: { type: Number, default: 0 },
  presetLabel: { type: String, default: '' },
})
const emit = defineEmits(['close', 'save', 'write-formula'])

const scenes = ref([])
const categories = ref([])
const quota = ref(null)
const kw = ref('')
const tab = ref('recommend')
const hoverKey = ref(null)
const chosenKey = ref(null)
const step = ref('market')      // market | compose（结果确认用 result 区分）
const running = ref(false)
const result = ref(null)        // 配置结果 {config, preview, warning}
const revising = ref(false)     // 「修改」：在上一轮配置上继续调
const error = ref('')
const warning = ref('')
const useDlg = ref(false)
const searchRef = ref(null)
const tabsRef = ref(null)
const gridRef = ref(null)
const composerRef = ref(null)
let abortCtl = null

const sceneOf = (k) => scenes.value.find(s => s.key === k)
const scene = computed(() => sceneOf(step.value === 'market' ? (hoverKey.value || 'classify') : chosenKey.value))
const isCustom = computed(() => chosenKey.value === 'custom' && step.value !== 'market')

// 顶部尽量贴近触发位置，但保证面板（约 700px）完整落在视口内
const top = computed(() => Math.max(8, Math.min(props.y, window.innerHeight - 720)))
const posStyle = computed(() => {
  const w = step.value === 'market' ? 1032 : 500
  return {
    left: `${Math.max(8, Math.min(props.x - (step.value === 'market' ? 540 : 500), window.innerWidth - w - 12))}px`,
    top: `${top.value}px`,
    '--aip-maxh': `${window.innerHeight - top.value - 12}px`,
  }
})
const headTitle = computed(() => {
  if (step.value === 'market') return scene.value?.label || 'AI 字段'
  if (result.value) return result.value.config.title
  if (running.value) return scene.value?.label
  return '添加 AI 字段'
})
const showBack = computed(() => step.value !== 'market')

onMounted(async () => {
  const r = await smartAiScenes()
  scenes.value = r.scenes
  categories.value = r.categories
  quota.value = await smartAiQuota().catch(() => null)
  await nextTick()
  searchRef.value?.focus()
})

// ---------- 场景市场 ----------
const filtered = computed(() => {
  const k = kw.value.trim()
  return scenes.value.filter(s => s.key !== 'custom' && (!k || s.label.includes(k) || (s.desc || '').includes(k)))
})
const sections = computed(() => categories.value
  .map(c => ({ ...c, scenes: filtered.value.filter(s => s.category === c.key) })).filter(c => c.scenes.length))
const flatList = computed(() => [...sections.value.flatMap(s => s.scenes), sceneOf('custom')].filter(Boolean))

let syncPause = 0
function jumpTo(key) {
  tab.value = key
  syncPause = Date.now() + 700   // 平滑滚动期间不反向同步 Tab（末尾分区滚不到顶会被同步成上一个）
  const el = gridRef.value?.querySelector(`[data-cat="${key}"]`)
  if (el) gridRef.value.scrollTo({ top: el.offsetTop - gridRef.value.offsetTop - 4, behavior: 'smooth' })
}
function onGridScroll() {
  const g = gridRef.value
  if (!g || Date.now() < syncPause) return
  let cur = sections.value[0]?.key
  for (const el of g.querySelectorAll('[data-cat]')) {
    if (el.offsetTop - g.offsetTop - 20 <= g.scrollTop) cur = el.dataset.cat
  }
  if (cur && cur !== tab.value) {
    tab.value = cur
    tabsRef.value?.querySelector('.aip-tab.on')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }
}
function scrollTabs() { tabsRef.value?.scrollBy({ left: 200, behavior: 'smooth' }) }
watch(kw, () => { tab.value = sections.value[0]?.key || 'recommend'; gridRef.value?.scrollTo({ top: 0 }) })

function choose(s) {
  if (!s || s.disabled) return
  if (s.action === 'formula') { emit('write-formula'); return }
  chosenKey.value = s.key
  step.value = 'compose'
  error.value = ''
  nextTick(() => composerRef.value?.focus())
}
function goBack() {
  if (running.value) stopRun()
  if (result.value || revising.value) { result.value = null; revising.value = false; return }   // 结果 → 回到输入
  step.value = 'market'
  chosenKey.value = null
  nextTick(() => searchRef.value?.focus())
}

// ---------- 输入字段候选（场景卡 {input} chip 的默认字段） ----------
const inputCandidates = computed(() => {
  const t = scene.value?.input
  if (t === 'image') return props.fields.filter(f => f.field_type === 'image')
  if (t === 'file') return props.fields.filter(f => f.field_type === 'file')
  return props.fields.filter(f => f.field_type !== 'ai')
})
const defaultInput = computed(() => inputCandidates.value[0] || null)

// ---------- 发送：AI 配置 + 试算 ----------
async function onSend({ inputFields, instruction }) {
  error.value = ''
  warning.value = ''
  const base = revising.value ? lastConfig : null
  const payload = {
    scene: chosenKey.value, instruction,
    input_fields: inputFields.length ? inputFields : (base?.inputFields || []),
    base: base || undefined,
  }
  running.value = true
  const ctl = new AbortController()
  abortCtl = ctl
  try {
    const r = await smartAiConfigure(props.tableId, payload, { signal: ctl.signal })
    if (ctl.signal.aborted) return
    result.value = r
    warning.value = r.warning || ''
    if (r.quota) quota.value = r.quota
    revising.value = false
  } catch (e) {
    if (!ctl.signal.aborted) error.value = e.message || 'AI 配置失败，请重试'
  } finally {
    if (abortCtl === ctl) { running.value = false; abortCtl = null }
  }
}
function stopRun() { abortCtl?.abort(); running.value = false }

let resultSeq = 0
const cardKey = computed(() => (result.value ? `r${++resultSeq}` : 'none'))
const cardCfg = computed(() => result.value?.config || {})
const cardPreview = computed(() => (result.value ? { config: result.value.config, rows: result.value.preview } : null))

function useResult() {
  if (scene.value?.local) { finishNew('all'); return }   // 本地计算：直接全部生成
  useDlg.value = true
}
// 修改：回到输入框（「描述修改要求」），上一轮配置作为 base 继续调整
let lastConfig = null
function reviseResult() {
  lastConfig = result.value?.config || null
  revising.value = true
  result.value = null
  nextTick(() => composerRef.value?.focus())
}

function finishNew(run) {
  useDlg.value = false
  const cfg = result.value?.config
  emit('save', { label: (props.presetLabel || cfg.title || scene.value?.label || 'AI 字段').slice(0, 30), config: cfg, run })
}

// 有未确认的结果时关闭需确认
async function tryClose() {
  if (result.value) {
    try { await ElMessageBox.confirm('AI 已生成配置但尚未使用，确定放弃吗？', '提示', { type: 'warning', confirmButtonText: '放弃', cancelButtonText: '继续编辑' }) } catch { return }
  }
  emit('close')
}

// 键盘：市场内 ↑↓←→ 移动，↵ 选定；Esc 关闭/返回
function onKey(e) {
  if (e.key === 'Escape') {
    if (useDlg.value) { useDlg.value = false; return }
    if (step.value === 'market') tryClose(); else goBack()
    return
  }
  if (step.value !== 'market' || e.target.closest?.('.aic')) return
  const list = flatList.value
  const i = Math.max(0, list.findIndex(s => s.key === hoverKey.value))
  const move = { ArrowDown: 2, ArrowUp: -2, ArrowRight: 1, ArrowLeft: -1 }[e.key]
  if (move) {
    e.preventDefault()
    hoverKey.value = list[Math.min(list.length - 1, Math.max(0, i + move))]?.key
    nextTick(() => gridRef.value?.querySelector(`[data-key="${hoverKey.value}"]`)?.scrollIntoView({ block: 'nearest' }))
  } else if (e.key === 'Enter') { e.preventDefault(); choose(sceneOf(hoverKey.value) || scene.value) }
}
</script>

<style scoped>
.aip-mask { position: fixed; inset: 0; z-index: 3000; }
.aip { position: fixed; display: flex; align-items: flex-start; gap: 8px; --el-color-primary: var(--st-primary); }
/* 左侧主面板：顶部紫粉渐变 → 浅灰底，内含白色圆角卡 */
.aip-main { width: 500px; max-height: var(--aip-maxh, calc(100vh - 24px)); display: flex; flex-direction: column; border-radius: 18px;
            background: linear-gradient(170deg, #ECE6FF 0%, #F8EEF3 70px, #F4F5F7 150px); box-shadow: 0 8px 32px rgba(0, 0, 0, .14);
            padding: 0 10px 10px; box-sizing: border-box; }
.aip-main.wide { width: 540px; }
.aip-head { display: flex; align-items: center; gap: 8px; height: 62px; padding: 0 10px; flex: none; }
.aip-logo { width: 22px; height: 22px; border-radius: 6px; background: linear-gradient(135deg, #8B6CF6, #E96BD8); color: #fff;
            display: inline-flex; align-items: center; justify-content: center; flex: none; }
.aip-logo.sm { width: 16px; height: 16px; border-radius: 4px; }
.aip-title { font-size: var(--st-font-size-title); font-weight: 700; color: var(--st-text-1); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.aip-icon-btn { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 6px;
                color: var(--st-text-2); cursor: pointer; flex: none; }
.aip-icon-btn:hover { background: rgba(31, 35, 41, .08); }
.aip-body { flex: 1; min-height: 0; overflow-y: auto; }
.aip-bottom { flex: none; margin-top: 10px; }
.aip-running { display: flex; align-items: center; gap: 12px; height: 76px; padding: 0 16px 0 22px; background: #fff; border-radius: 16px;
               font-size: var(--st-font-size); color: var(--st-text-2); }
.aip-spin { width: 18px; height: 18px; border-radius: 50%; border: 2.5px solid #D9DBDF; border-top-color: #8F959E; animation: aip-rot .8s linear infinite; }
@keyframes aip-rot { to { transform: rotate(360deg); } }
.aip-stop { margin-left: auto; width: 40px; height: 40px; border-radius: 8px; background: #F2F3F5; color: var(--st-text-2);
            display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
.aip-stop:hover { background: #E6E8EA; }
.aip-error { display: flex; align-items: center; gap: 6px; margin: 8px 6px 0; font-size: var(--st-font-size); color: var(--el-color-danger); }
.aip-warn { margin: 8px 6px 0; font-size: var(--st-font-size); color: #B7791F; }
.aip-soon { display: flex; align-items: center; gap: 6px; margin: 10px 8px 2px; font-size: var(--st-font-size); color: var(--st-text-3); }
.aip-soon.ok { color: #2BA471; }
.aip-res-ops { display: flex; gap: 10px; margin-top: 16px; }
.aip-res-ops .aip-btn { flex: 1; height: 44px; font-size: var(--st-font-size); }
.aip-btn { height: 34px; padding: 0 16px; border-radius: 8px; border: 1px solid #E3E5E8; background: #fff; font-size: var(--st-font-size);
           color: var(--st-text-2); cursor: pointer; }
.aip-btn:hover { background: #F5F6F7; }
.aip-btn.primary { background: var(--st-primary); border-color: var(--st-primary); color: #fff; }
.aip-btn.primary:hover { background: #255BD0; }
.aip-btn:disabled { opacity: .5; cursor: not-allowed; }
.aip-btn.sm { height: 34px; padding: 0 18px; }
.aip-btn.block { display: block; width: 100%; height: 44px; margin-top: 12px; font-size: var(--st-font-size); background: #F2F3F5; border-color: #F2F3F5; }
.aip-btn.block.primary { background: var(--st-primary); border-color: var(--st-primary); }
.aip-btn.block:not(.primary):hover { background: #E8E9EB; }
.aip-custom-empty { background: #fff; border-radius: 16px; height: 240px; display: flex; flex-direction: column; align-items: center;
                    justify-content: center; gap: 22px; }
.aip-ce-t { display: flex; align-items: center; gap: 8px; font-size: var(--st-font-size-title); font-weight: 700; color: var(--st-text-1); }
.aip-ce-d { font-size: var(--st-font-size); color: var(--st-text-3); }
/* 右侧场景市场 */
.aip-market { width: 484px; background: #fff; border-radius: 14px; box-shadow: 0 8px 32px rgba(0, 0, 0, .14); display: flex; flex-direction: column;
              height: min(640px, var(--aip-maxh, calc(100vh - 24px))); overflow: hidden; }
.aip-search { display: flex; align-items: center; gap: 10px; padding: 16px 18px 4px; }
.aip-search-in { flex: 1; border: none; outline: none; font-size: var(--st-font-size); color: var(--st-text-2); }
.aip-search-in::placeholder { color: #B5B9C0; }
.aip-tabs-wrap { display: flex; align-items: flex-end; border-bottom: 1px solid #EBECEE; padding: 0 0 0 20px; }
.aip-tabs { flex: 1; display: flex; gap: 22px; overflow-x: auto; scrollbar-width: none; padding-top: 12px; }
.aip-tabs::-webkit-scrollbar { display: none; }
.aip-tab { position: relative; display: inline-flex; align-items: center; gap: 5px; font-size: var(--st-font-size); padding-bottom: 12px; cursor: pointer;
           white-space: nowrap; color: var(--st-text-2); flex: none; }
.aip-tab .st-icon { color: var(--st-text-2); }
.aip-tab:hover { color: var(--st-text-2); }
.aip-tab.on { color: var(--st-text-1); font-weight: 600; }
.aip-tab.on::after { content: ''; position: absolute; left: 2px; right: 2px; bottom: 0; height: 3px; border-radius: 2px; background: var(--st-primary); }
.aip-tabs-more { width: 32px; height: 38px; display: inline-flex; align-items: center; justify-content: center; color: var(--st-text-3);
                 cursor: pointer; flex: none; background: linear-gradient(90deg, rgba(255, 255, 255, 0), #fff 40%); }
.aip-tabs-more .rot { transform: rotate(-90deg); }
.aip-tabs-more:hover { color: var(--st-text-2); }
.aip-grid-wrap { flex: 1; overflow-y: auto; margin: 12px 12px 8px; border: 1px solid #EBECEE; border-radius: 12px; padding: 4px 8px 8px; }
.aip-sec { font-size: var(--st-font-size); color: var(--st-text-3); padding: 12px 12px 6px; }
.aip-sec-wrap + .aip-sec-wrap { border-top: 1px solid #EBECEE; margin-top: 6px; }
.aip-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 12px; }
.aip-scene { display: flex; align-items: center; gap: 6px;  padding: 0 12px; border-radius: 8px; font-size: var(--st-font-size); cursor: pointer;
             color: var(--st-text-2); min-width: 0;  height: var(--st-list-item-height); box-sizing: border-box; }
.aip-scene-l { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.aip-scene.on { background: #F2F3F5; }
.aip-scene.off { color: #B5B9C0; cursor: default; }
.aip-scene-tag { flex: none; font-size: 11px; color: #A8ADB5; background: #F2F3F5; border-radius: 3px; padding: 0 4px; line-height: 16px; }
.aip-none { padding: 40px 20px; text-align: center; color: var(--st-text-3); font-size: var(--st-font-size); }
.aip-custom { margin: 0 12px 10px; border: 1px solid #EBECEE; border-radius: 12px; padding: 0 20px; height: 54px; display: flex; align-items: center;
              font-size: var(--st-font-size); cursor: pointer; color: var(--st-text-2); }
.aip-custom.on { background: #F2F3F5; }
.aip-foot { display: flex; align-items: center; gap: 22px; padding: 0 20px; height: 44px; background: #F7F8FA; border-top: 1px solid #EBECEE;
            font-size: var(--st-font-size); color: #A8ADB5; flex: none; }
.aip-foot b { font-weight: 400; color: var(--st-text-3); }
.aip-quota { margin-left: auto; font-size: var(--st-font-size); }
/* 使用确认 */
.aip-use-mask { position: fixed; inset: 0; z-index: 3001; background: rgba(0, 0, 0, .3); }
.aip-use { position: fixed; left: 50%; top: 32%; transform: translate(-50%, -50%); width: 420px; background: #fff; border-radius: 14px;
           padding: 24px 32px 28px; box-shadow: 0 12px 40px rgba(0, 0, 0, .2); box-sizing: border-box; }
.aip-use-h { display: flex; align-items: center; gap: 10px; font-size: var(--st-font-size-title); font-weight: 700; color: var(--st-text-1); }
.aip-use-h .aip-icon-btn { margin-left: auto; color: var(--st-text-2); }
.aip-use-ico { color: var(--st-primary); }
.aip-use-d { font-size: var(--st-font-size); line-height: 1.7; color: var(--st-text-2); margin: 8px 0 10px 30px; }
</style>
