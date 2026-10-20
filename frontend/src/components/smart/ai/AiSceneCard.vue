<template>
  <!-- AI 场景 / 配置结果卡（参照 添加列/AI字段）：说明（字段以 chip 内嵌）→「使用模型生成」提示词
       （box = 灰底展开；collapse = 下拉折叠）→ 效果表（场景示例数据或真实数据试算结果）→ 可选反馈行 -->
  <div class="asc" :class="{ dim, bare }">
    <div v-if="desc" class="asc-desc">
      <template v-for="(seg, i) in descSegments" :key="i">
        <span v-if="seg.chip" class="asc-chip"><StIcon :name="seg.icon" :size="14" />{{ seg.text }}</span>
        <span v-else>{{ seg.text }}</span>
      </template>
    </div>

    <div v-if="prompt && promptMode === 'box'" class="asc-prompt">
      <div class="asc-prompt-t">使用模型生成</div>
      <div class="asc-prompt-b">{{ prompt }}</div>
    </div>
    <div v-else-if="prompt || promptMode === 'collapse'" class="asc-pfold" :class="{ open: promptOpen }">
      <div class="asc-pfold-h" @click="promptOpen = !promptOpen">
        <span>使用模型生成</span><StIcon name="chevron-down" :size="16" class="asc-pfold-caret" />
      </div>
      <div v-if="promptOpen" class="asc-pfold-b">{{ prompt || '本地计算，不调用大模型' }}</div>
    </div>

    <template v-if="table">
      <div v-if="!bare" class="asc-eff">效果：</div>
      <div class="asc-table">
        <div class="asc-tr asc-th">
          <div class="asc-td"><StIcon :name="table.inIcon" :size="15" class="asc-hico" /><span class="asc-ell">{{ table.inLabel }}</span></div>
          <div class="asc-td"><StIcon :name="table.outIcon" :size="15" class="asc-hico" /><span class="asc-ell">{{ table.outLabel }}</span><AiBadge /></div>
        </div>
        <div v-for="(r, i) in table.rows" :key="i" class="asc-tr">
          <div class="asc-td asc-in">
            <SmartCell v-if="r.inField" :field="r.inField" :record="r.inRecord" />
            <span v-else-if="r.image" class="asc-img"><StIcon name="image" :size="14" /></span>
            <span v-else class="asc-ell">{{ r.inText }}</span>
          </div>
          <div class="asc-td">
            <span v-if="r.loading" class="asc-gen">正在生成…</span>
            <span v-else-if="r.error" class="asc-err" :data-smart-tip="r.error">生成失败：{{ r.error }}</span>
            <SmartCell v-else-if="r.outField" :field="r.outField" :record="r.outRecord" />
            <span v-else class="asc-ell">{{ r.outText }}</span>
          </div>
        </div>
        <div v-if="!table.rows.length" class="asc-empty">表格里还没有可试算的数据，保存后新增记录会自动生成</div>
      </div>
    </template>

    <div v-if="feedback" class="asc-fb">
      <span>提交反馈帮助提升效果</span>
      <span class="asc-fb-btn st-icon-action" :class="{ on: fb === 'up' }" data-smart-tip="有帮助" @click="vote('up')"><StIcon name="thumb-up" :size="16" /></span>
      <span class="asc-fb-btn st-icon-action" :class="{ on: fb === 'down' }" data-smart-tip="不准确" @click="vote('down')"><StIcon name="thumb-down" :size="16" /></span>
    </div>
    <slot />
  </div>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import SmartCell from '../grid/SmartCell.vue'
import AiBadge from './AiBadge.vue'

const props = defineProps({
  desc: { type: String, default: '' },          // 字段写作 [字段名] 或 {input}
  inputField: { type: Object, default: null },  // {input} 占位的字段（缺省显示「文本」）
  fields: { type: Array, default: () => [] },
  prompt: { type: String, default: '' },
  promptMode: { type: String, default: 'box' }, // box | collapse
  sample: { type: Object, default: null },      // 场景示例 {in, inType, out, rows:[[in, out]]}
  outputType: { type: String, default: 'text' },
  preview: { type: Object, default: null },     // 真实试算 {rows, config}
  outLabel: { type: String, default: '' },
  dim: { type: Boolean, default: false },
  feedback: { type: Boolean, default: false },
  bare: { type: Boolean, default: false },      // 嵌入表单：只要效果表（无卡片底/内边距/「效果」标题）
})

const promptOpen = ref(false)
const fb = ref(null)
function vote(v) {
  fb.value = fb.value === v ? null : v
  if (fb.value) ElMessage.success(v === 'up' ? '感谢反馈！' : '感谢反馈，我们会持续改进')
}

const iconOf = fieldIconName

const descSegments = computed(() => {
  const byLabel = new Map(props.fields.map(f => [f.label, f]))
  const out = []
  const re = /\{input\}|\[([^\]]+)\]/g
  let last = 0
  let m
  while ((m = re.exec(props.desc))) {
    if (m.index > last) out.push({ text: props.desc.slice(last, m.index) })
    if (m[0] === '{input}') {
      out.push({ chip: true, text: props.inputField?.label || '文本', icon: iconOf(props.inputField) })
    } else {
      const f = byLabel.get(m[1])
      out.push({ chip: true, text: m[1], icon: f ? iconOf(f) : 'text' })
    }
    last = m.index + m[0].length
  }
  if (last < props.desc.length) out.push({ text: props.desc.slice(last) })
  return out
})

// 示例数据的选项着色：同一标签同一颜色（参照图 分类1/2/4 各一色）
const SAMPLE_COLORS = ['red', 'orange', 'cyan', 'green', 'purple', 'pink', 'blue']
function sampleOptions(rows) {
  const labels = [...new Set(rows.map(r => r[1]).filter(Boolean))]
  return labels.map((l, i) => ({ id: `s${i}`, label: l, color: SAMPLE_COLORS[i % SAMPLE_COLORS.length] }))
}

const table = computed(() => {
  const outType = props.preview?.config?.outputType || props.outputType
  const outIcon = outType
  if (props.preview) {
    const cfg = props.preview.config || {}
    const inFn = (cfg.inputFields || [])[0]
    const inField = props.fields.find(f => f.field_name === inFn)
    const outField = { field_name: '__out', field_type: outType, options: { options: cfg.options || [] } }
    return {
      inLabel: inField?.label || '输入', inIcon: iconOf(inField), outLabel: props.outLabel || cfg.title || '结果', outIcon,
      rows: (props.preview.rows || []).map(r => ({
        inField, inRecord: { ...(r.inputs || {}) },
        outField, outRecord: { __out: r.output }, error: r.error, loading: r.loading,
      })),
    }
  }
  if (!props.sample) return null
  const s = props.sample
  const isSel = ['singleSelect', 'multiSelect'].includes(outType)
  const opts = isSel ? sampleOptions(s.rows) : []
  const outField = isSel || outType === 'checkbox'
    ? { field_name: '__out', field_type: outType, options: { options: opts } } : null
  return {
    inLabel: s.in, inIcon: s.inType || 'text', outLabel: props.outLabel || s.out, outIcon,
    rows: s.rows.map(([a, b]) => ({
      inText: a, image: s.inType === 'image',
      outField, outRecord: { __out: isSel ? (opts.find(o => o.label === b)?.id ?? null) : b }, outText: b,
    })),
  }
})
</script>

<style scoped>
.asc { background: #fff; border-radius: 16px; padding: 22px 22px 20px; transition: opacity .2s; }
.asc.dim > :not(.asc-keep) { opacity: .45; }
.asc.bare { padding: 0; background: none; border-radius: 0; }
.asc.bare .asc-tr { min-height: 44px; }
.asc.bare .asc-td { font-size: 14px; }
.asc.bare .asc-fb { margin-top: 8px; padding-top: 0; border-top: none; font-size: 12px; }
.asc-desc { font-size: 16px; line-height: 30px; color: var(--st-text-1); }
.asc-chip { display: inline-flex; align-items: center; gap: 4px; height: 26px; line-height: 26px; padding: 0 8px; margin: 0 4px;
            background: #F2F3F5; border-radius: 4px; font-size: 15px; vertical-align: 1px; }
.asc-chip .st-icon { color: var(--st-text-2); }
.asc-prompt { background: #F5F6F7; border-radius: 10px; padding: 14px 18px; margin: 16px 0 12px; }
.asc-prompt-t { font-size: 14px; color: var(--st-text-3); margin-bottom: 6px; }
.asc-prompt-b { font-size: 15px; line-height: 1.75; color: var(--st-text-1); white-space: pre-wrap; max-height: 150px; overflow: hidden; }
.asc-pfold { background: #F5F6F7; border-radius: 10px; margin: 16px 0 12px; }
.asc-pfold-h { display: flex; align-items: center; justify-content: space-between; height: 54px; padding: 0 18px; cursor: pointer;
               font-size: 15px; color: var(--st-text-3); }
.asc-pfold-caret { color: var(--st-text-3); transition: transform .15s; }
.asc-pfold.open .asc-pfold-caret { transform: rotate(180deg); }
.asc-pfold-b { padding: 0 18px 14px; font-size: 14px; line-height: 1.75; color: var(--st-text-1); white-space: pre-wrap; }
.asc-eff { font-size: 15px; color: var(--st-text-1); margin: 4px 0 10px; }
.asc-table { border: 1px solid #E5E6E8; border-radius: 8px; overflow: hidden; }
.asc-tr { display: grid; grid-template-columns: 1fr 1fr; border-top: 1px solid #E5E6E8; min-height: 54px; }
.asc-tr:first-child { border-top: none; }
.asc-td { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 0 12px; font-size: 15px; color: var(--st-text-1); }
.asc-td + .asc-td { border-left: 1px solid #E5E6E8; }
.asc-th .asc-td { color: var(--st-text-1); }
.asc-hico { color: var(--st-text-3); flex: none; }
.asc-in { background: #F8F9FA; }
.asc-td :deep(.smart-cell) { min-width: 0; overflow: hidden; font-size: 15px; }
.asc-ell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.asc-img { width: 30px; height: 30px; border-radius: 4px; background: #EDEEF0; color: #B5B9C0; display: inline-flex; align-items: center; justify-content: center; }
.asc-gen { color: var(--st-text-3); background: linear-gradient(90deg, #C9CDD4 0%, #8F959E 40%, #C9CDD4 80%); background-size: 200% 100%;
           -webkit-background-clip: text; background-clip: text; color: transparent; animation: asc-shine 1.4s linear infinite; }
@keyframes asc-shine { from { background-position: 200% 0; } to { background-position: 0 0; } }
.asc-err { color: var(--el-color-danger); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.asc-empty { padding: 18px; text-align: center; font-size: 13px; color: var(--st-text-3); border-top: 1px solid #E5E6E8; }
.asc-fb { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 14px; padding-top: 12px;
          border-top: 1px solid #EBECEE; font-size: 14px; color: #B5B9C0; }
.asc-fb-btn { display: inline-flex; padding: 3px; border-radius: 4px; color: var(--st-text-2); cursor: pointer; }
.asc-fb-btn:hover { background: #F2F3F5; }
.asc-fb-btn.on { color: var(--st-primary); }
</style>
