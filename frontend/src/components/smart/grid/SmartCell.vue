<template>
  <!-- 展示态单元格：按 field_type 分发渲染（存原始值/ID，渲染层格式化，设计文档 §3.1 原则 2/3） -->
  <span class="smart-cell" :class="`cell-${ft}`" :style="cellStyle">
    <!-- AI 字段计算状态（V3）：生成中 / 失败（悬停看原因）；完成后按输出类型渲染 -->
    <span v-if="aiState && aiState.status !== 'error'" class="ai-state">正在生成…</span>
    <span v-else-if="aiState" class="ai-state err" :data-smart-tip="aiState.error || ''">生成失败 · {{ aiState.error || '原因未知' }}</span>
    <!-- 单选/多选：彩色标签胶囊；一行放不下时只渲染放得下的，末尾 +N 表示隐藏个数 -->
    <template v-else-if="ft === 'singleSelect' || ft === 'multiSelect'">
      <span v-if="enumTags.length === 1" class="opt-tag" :class="{ raw: enumTags[0].raw }" :style="enumTags[0].style">{{ enumTags[0].label }}</span>
      <CompactCellTags v-else-if="enumTags.length > 1" :tags="enumTags" />
    </template>
    <!-- 进度条 -->
    <ProgressCell v-else-if="ft === 'progress'" :value="value" :config="cfg" />
    <!-- 人员：头像+姓名 -->
    <template v-else-if="ft === 'member'">
      <span v-for="m in members" :key="m.id" class="member-chip">
        <span class="avatar">{{ (m.name || '?')[0] }}</span>{{ m.name }}
      </span>
    </template>
    <!-- 系统人员字段 -->
    <template v-else-if="ft === 'createdBy' || ft === 'lastModifiedBy'">
      <span v-if="sysUser" class="member-chip">
        <span class="avatar" :class="{ 'avatar-ai': sysActor }">{{ sysActor === 'ai' ? '✦' : sysUser[0] }}</span>{{ sysUser }}
      </span>
    </template>
    <!-- 链接 -->
    <a v-else-if="ft === 'url' && value" class="link" :href="value.url" target="_blank" rel="noopener"
       @click.stop><StIcon v-if="cfg.displayStyle !== 'text'" name="link" :size="13" class="link-ico" />{{ value.text || value.url }}</a>
    <!-- 图片：缩略图 -->
    <span v-else-if="ft === 'image'" class="imgs">
      <el-image v-for="(img, i) in imageList.slice(0, 3)" :key="i" :src="imgSrc(img)"
                :preview-src-list="imageList.map(imgSrc)" :initial-index="i"
                fit="cover" class="thumb" @click.stop />
      <span v-if="imageList.length > 3" class="more">+{{ imageList.length - 3 }}</span>
    </span>
    <!-- 文件：chip 列表 -->
    <span v-else-if="ft === 'file'" class="files">
      <a v-for="(f, i) in fileList" :key="i" class="file-chip" :href="fileHref(f)" target="_blank" rel="noopener"
         @click.stop>📄 {{ f.name || f }}</a>
    </span>
    <!-- 关联：记录徽标 -->
    <span v-else-if="ft === 'relation'" class="rels">
      <span v-for="(r, i) in relationLabels" :key="i" class="rel-chip">🔗 {{ r }}</span>
    </span>
    <!-- 查找引用 -->
    <template v-else-if="ft === 'lookup' && lookupDisplayField">
      <template v-for="(item, i) in lookupValues" :key="i">
        <span v-if="i" class="lookup-separator">、</span>
        <SmartCell :field="lookupDisplayField" :record="{ [lookupDisplayField.field_name]: item }" class="lookup-value" />
      </template>
    </template>
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
import StIcon from '../icons/StIcon.vue'
import { resolveEnumTags } from '../../../smart/utils/enumTags.js'
import ProgressCell from './ProgressCell.vue'
import CompactCellTags from './CompactCellTags.vue'
import { imageUrl } from '../../../api/index.js'
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

// AI 字段按输出类型渲染（标签/复选框/数字/文本）
const ft = computed(() => props.field.field_type === 'ai'
  ? (props.field.options?.outputType || 'text') : (props.field.field_type || 'text'))
const aiState = computed(() => props.field.field_type === 'ai' ? props.record.__ai?.[props.field.field_name] || null : null)
const cfg = computed(() => props.field.options || {})
const value = computed(() => props.record[props.field.field_name])
const isDate = computed(() => ['date', 'createdTime', 'lastModifiedTime'].includes(ft.value))

const cellStyle = computed(() => props.fillColor ? { background: props.fillColor } : {})

// 单选/多选一行放不下时 +N。容器是 nowrap + overflow 裁剪，测量用 scrollWidth
// （截断标签的自然宽度）；先按全量宽度判断能否全放下，放不下再预留徽标位
// （ghost 实测）重算容量，只渲染放得下的 + 徽标（否则徽标自身会被挤出裁剪区）
const enumTags = computed(() => resolveEnumTags(cfg.value.options, value.value))

const members = computed(() => {
  const ids = Array.isArray(value.value) ? value.value : (value.value ? [value.value] : [])
  return ids.map(id => memberDir.value.get(Number(id)) || { id, name: `#${id}` })
})
// 最后编辑人为非人主体（V3 留痕）：__ai__ → AI 生成，__automation__ → 自动化
const sysActor = computed(() => ({ __ai__: 'ai', __automation__: 'automation' })[value.value] || null)
const sysUser = computed(() => {
  const id = value.value
  if (id == null) return ''
  if (sysActor.value) return sysActor.value === 'ai' ? 'AI 生成' : '自动化'
  return memberDir.value.get(Number(id))?.name || `#${id}`
})

const imageList = computed(() => Array.isArray(value.value) ? value.value : [])
// 图片值存图片库 id（历史数据可能是完整 URL）
function imgSrc(img) {
  const v = img?.url || img
  return typeof v === 'string' && (v.startsWith('http') || v.startsWith('/') || v.startsWith('data:')) ? v : imageUrl(v)
}
function fileHref(f) {
  if (!f?.id || !/^[0-9a-f]{32}$/.test(f.id)) return undefined
  return `/api/smart/files/${f.id}?token=${localStorage.getItem('grt_token')}&tenant_id=${localStorage.getItem('grt_tenant_id') || ''}`
}
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
const lookupDisplayField = computed(() => {
  if (ft.value !== 'lookup') return null
  const agg = cfg.value.aggregation || 'raw'
  if (!['raw', 'rawDistinct'].includes(agg)) return { field_name: '_lookup', field_type: 'number', options: {} }
  const source = props.field.lookupDisplayField
  return source && source.field_type !== 'lookup' ? source : null
})
const lookupValues = computed(() => {
  if (value.value == null) return []
  if (!['raw', 'rawDistinct'].includes(cfg.value.aggregation || 'raw')) return [value.value]
  const values = Array.isArray(value.value) ? value.value : [value.value]
  const type = lookupDisplayField.value?.field_type
  // List-valued source fields share one renderer (tags, members, images/files).
  return ['singleSelect', 'multiSelect', 'member', 'image', 'file', 'relation'].includes(type) ? [values.flat()] : values
})
</script>

<style scoped>
.smart-cell { display: flex; align-items: center; gap: 4px; flex-wrap: nowrap; overflow: hidden; white-space: nowrap; font-size: 13px; min-height: 20px; width: 100%; }
/* 纯文本单行省略号（flex 容器里的文本节点吃不到 ellipsis，须包一层） */
.txt { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lookup-value { width: auto; flex: 0 1 auto; min-width: 0; }
.lookup-separator { flex: none; }
/* 单选/多选查看态：一行展示，放不下的由 +N 徽标报数（只渲染放得下的）；
   单个标签超宽时自身省略号截断；有徽标时标签再让出徽标位 */
.enum-box { position: relative; display: flex; align-items: center; gap: 4px; flex-wrap: nowrap; overflow: hidden; max-height: 22px; width: 100%; }
.enum-box.has-more .opt-tag { max-width: calc(100% - 32px); }
.enum-more { flex: none; color: var(--el-text-color-secondary); font-size: 12px; white-space: nowrap; }
.enum-ghost { position: absolute; visibility: hidden; pointer-events: none; }
.opt-tag { padding: 1px 8px; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; flex: none; }
.opt-tag.raw { background: var(--el-fill-color-light); color: var(--el-text-color-regular); border: 1px dashed var(--el-border-color); }
.member-chip { display: inline-flex; align-items: center; gap: 4px; }
/* 方形圆角头像（对齐参照 单元格输入-人员.png） */
.avatar { width: 20px; height: 20px; border-radius: 4px; background: var(--el-color-primary-light-5); color: #fff; font-size: 11px; display: inline-flex; align-items: center; justify-content: center; }
.link { color: var(--el-color-primary); text-decoration: none; display: inline-flex; align-items: center; gap: 4px; min-width: 0; }
.link-ico { flex: none; }
.imgs { display: flex; gap: 4px; }
.thumb { width: 28px; height: 28px; border-radius: 4px; }
.more { font-size: 12px; color: var(--el-text-color-secondary); }
.file-chip { text-decoration: none; color: inherit; }
.file-chip, .rel-chip { background: var(--el-fill-color-light); border-radius: 4px; padding: 1px 6px; font-size: 12px; white-space: nowrap; }
.smart-cell.cell-checkbox { justify-content: center; }
.checkbox { width: 18px; height: 18px; flex: none; border: 1px solid var(--el-border-color); border-radius: 4px; display: inline-flex; align-items: center; justify-content: center; color: #fff; cursor: pointer; }
.checkbox.checked { background: var(--st-success); border-color: var(--st-success); }
.cell-currency, .cell-number, .cell-percent, .cell-progress { justify-content: flex-end; }
/* AI 字段状态 */
/* AI 生成中（参照 AI-分类-使用后选择-单元格内容生成中.png）：灰字 + 流光扫过 */
.ai-state { display: inline-block; font-size: 13px; color: transparent; white-space: nowrap;
            background: linear-gradient(90deg, #B5B9C0 0%, #B5B9C0 35%, #E6E8EB 50%, #B5B9C0 65%, #B5B9C0 100%);
            background-size: 220% 100%; -webkit-background-clip: text; background-clip: text; animation: ai-shine 1.6s linear infinite; }
.ai-state.err { color: var(--el-color-danger); background: none; animation: none; cursor: help; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
@keyframes ai-shine { from { background-position: 110% 0; } to { background-position: -110% 0; } }
.avatar.avatar-ai { background: linear-gradient(135deg, #7F3FF1, #4C8DFF); color: #fff; }
</style>
