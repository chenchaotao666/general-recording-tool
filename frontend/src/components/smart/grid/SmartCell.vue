<template>
  <!-- 展示态单元格：按 field_type 分发渲染（存原始值/ID，渲染层格式化，设计文档 §3.1 原则 2/3） -->
  <span class="smart-cell" :class="`cell-${ft}`" :style="cellStyle">
    <!-- 单选/多选：彩色标签胶囊 -->
    <template v-if="ft === 'singleSelect' || ft === 'multiSelect'">
      <span v-for="o in selectedOptions" :key="o.id" class="opt-tag"
            :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">{{ o.label }}</span>
      <!-- 未匹配到选项的原始值（如改类型前录入的文本）原样兜底显示，不消失 -->
      <span v-for="(v, i) in unmatchedValues" :key="`raw-${i}`" class="opt-tag raw">{{ v }}</span>
    </template>
    <!-- 进度条 -->
    <span v-else-if="ft === 'progress'" class="progress-wrap">
      <span class="progress-bar"><span class="progress-fill" :style="progressStyle"></span></span>
      <span v-if="cfg.showNumber !== false" class="progress-num">{{ progressText }}</span>
    </span>
    <!-- 人员：头像+姓名 -->
    <template v-else-if="ft === 'member'">
      <span v-for="m in members" :key="m.id" class="member-chip">
        <span class="avatar">{{ (m.name || '?')[0] }}</span>{{ m.name }}
      </span>
    </template>
    <!-- 系统人员字段 -->
    <template v-else-if="ft === 'createdBy' || ft === 'lastModifiedBy'">
      <span v-if="sysUser" class="member-chip"><span class="avatar">{{ sysUser[0] }}</span>{{ sysUser }}</span>
    </template>
    <!-- 链接 -->
    <a v-else-if="ft === 'url' && value" class="link" :href="value.url" target="_blank" rel="noopener"
       @click.stop>{{ value.text || value.url }}</a>
    <!-- 图片：缩略图 -->
    <span v-else-if="ft === 'image'" class="imgs">
      <el-image v-for="(img, i) in imageList.slice(0, 3)" :key="i" :src="img.url || img"
                :preview-src-list="imageList.map(x => x.url || x)" :initial-index="i"
                fit="cover" class="thumb" @click.stop />
      <span v-if="imageList.length > 3" class="more">+{{ imageList.length - 3 }}</span>
    </span>
    <!-- 文件：chip 列表 -->
    <span v-else-if="ft === 'file'" class="files">
      <span v-for="(f, i) in fileList" :key="i" class="file-chip">📄 {{ f.name || f }}</span>
    </span>
    <!-- 关联：记录徽标 -->
    <span v-else-if="ft === 'relation'" class="rels">
      <span v-for="(r, i) in relationLabels" :key="i" class="rel-chip">🔗 {{ r }}</span>
    </span>
    <!-- 查找引用 -->
    <span v-else-if="ft === 'lookup'">{{ lookupText }}</span>
    <!-- 复选框 -->
    <span v-else-if="ft === 'checkbox'" class="checkbox" :class="{ checked: !!value }">{{ value ? '✓' : '' }}</span>
    <!-- 日期/系统时间 -->
    <template v-else-if="isDate">{{ formatDate(value, cfg) }}</template>
    <!-- 货币/百分数/数字 -->
    <template v-else-if="ft === 'currency'">{{ formatCurrency(value, cfg) }}</template>
    <template v-else-if="ft === 'percent'">{{ value != null && value !== '' ? `${value}%` : '' }}</template>
    <template v-else-if="ft === 'number'">{{ formatNumber(value, cfg) }}</template>
    <!-- 公式/自动编号/文本等（.txt 单行省略） -->
    <span v-else class="txt">{{ value ?? '' }}</span>
  </span>
</template>

<script setup>
import { computed, inject } from 'vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'
import { formatCurrency, formatDate, formatNumber } from '../../../smart/utils/format.js'

const props = defineProps({
  field: { type: Object, required: true },
  record: { type: Object, required: true },
  fillColor: { type: String, default: null },     // 填色规则命中色
})

// 成员目录由 SmartTablePage 注入（userId → {id, name}）
const memberDir = inject('smartMemberDir', { value: new Map() })
// 关联记录标签目录：SmartTablePage 加载目标表记录后注入 {tableId: Map(recordId → label)}
const relationDir = inject('smartRelationDir', { value: new Map() })

const ft = computed(() => props.field.field_type || 'text')
const cfg = computed(() => props.field.options || {})
const value = computed(() => props.record[props.field.field_name])
const isDate = computed(() => ['date', 'createdTime', 'lastModifiedTime'].includes(ft.value))

const cellStyle = computed(() => props.fillColor ? { background: props.fillColor } : {})

const selectedOptions = computed(() => {
  const opts = cfg.value.options || []
  const v = value.value
  if (v == null) return []
  const ids = Array.isArray(v) ? v : [v]
  return ids.map(id => opts.find(o => o.id === id)).filter(Boolean)
})

// 未匹配到选项的原始值（改类型/导入场景）兜底原样展示
const unmatchedValues = computed(() => {
  if (!['singleSelect', 'multiSelect'].includes(ft.value)) return []
  const opts = cfg.value.options || []
  const v = value.value
  if (v == null) return []
  const ids = Array.isArray(v) ? v : [v]
  return ids.filter(id => id != null && id !== '' && !opts.some(o => o.id === id))
    .map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x)))
})

const progressStyle = computed(() => {
  const range = cfg.value.range || { min: 0, max: 100 }
  const pct = Math.min(1, Math.max(0, ((Number(value.value) || 0) - range.min) / (range.max - range.min)))
  return { width: `${pct * 100}%`, background: cfg.value.color || 'green' }
})
const progressText = computed(() => {
  if (value.value == null) return ''
  if (cfg.value.numberFormat === 'percent') {
    const range = cfg.value.range || { min: 0, max: 100 }
    return `${Math.round(((Number(value.value) - range.min) / (range.max - range.min)) * 100)}%`
  }
  return String(value.value)
})

const members = computed(() => {
  const ids = Array.isArray(value.value) ? value.value : (value.value ? [value.value] : [])
  return ids.map(id => memberDir.value.get(Number(id)) || { id, name: `#${id}` })
})
const sysUser = computed(() => {
  const id = value.value
  if (id == null) return ''
  return memberDir.value.get(Number(id))?.name || `#${id}`
})

const imageList = computed(() => Array.isArray(value.value) ? value.value : [])
const fileList = computed(() => Array.isArray(value.value) ? value.value : [])
const relationLabels = computed(() => {
  const ids = Array.isArray(value.value) ? value.value : (value.value ? [value.value] : [])
  const dir = relationDir.value.get(cfg.value.targetTableId)
  return ids.map(id => dir?.get(Number(id)) ?? `#${id}`)
})
const lookupText = computed(() => {
  const v = value.value
  if (v == null) return ''
  return Array.isArray(v) ? v.join('、') : String(v)
})
</script>

<style scoped>
.smart-cell { display: flex; align-items: center; gap: 4px; flex-wrap: nowrap; overflow: hidden; white-space: nowrap; font-size: 13px; min-height: 20px; width: 100%; }
/* 纯文本单行省略号（flex 容器里的文本节点吃不到 ellipsis，须包一层） */
.txt { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.opt-tag { padding: 1px 8px; border-radius: 6px; font-size: 12px; white-space: nowrap; }
.opt-tag.raw { background: var(--el-fill-color-light); color: var(--el-text-color-regular); border: 1px dashed var(--el-border-color); }
.progress-wrap { display: flex; align-items: center; gap: 6px; width: 100%; }
.progress-bar { flex: 1; height: 8px; background: var(--el-fill-color); border-radius: 4px; overflow: hidden; }
.progress-fill { display: block; height: 100%; border-radius: 4px; }
.progress-num { font-size: 12px; color: var(--el-text-color-secondary); }
.member-chip { display: inline-flex; align-items: center; gap: 4px; }
.avatar { width: 18px; height: 18px; border-radius: 50%; background: var(--el-color-primary-light-5); color: #fff; font-size: 11px; display: inline-flex; align-items: center; justify-content: center; }
.link { color: var(--el-color-primary); text-decoration: none; }
.imgs { display: flex; gap: 4px; }
.thumb { width: 28px; height: 28px; border-radius: 4px; }
.more { font-size: 12px; color: var(--el-text-color-secondary); }
.file-chip, .rel-chip { background: var(--el-fill-color-light); border-radius: 4px; padding: 1px 6px; font-size: 12px; white-space: nowrap; }
.checkbox { width: 18px; height: 18px; border: 1px solid var(--el-border-color); border-radius: 4px; display: inline-flex; align-items: center; justify-content: center; color: #fff; }
.checkbox.checked { background: var(--el-color-success); border-color: var(--el-color-success); }
.cell-currency, .cell-number, .cell-percent, .cell-progress { justify-content: flex-end; }
</style>
