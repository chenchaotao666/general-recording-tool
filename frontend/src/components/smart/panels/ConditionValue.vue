<template>
  <!-- 条件值编辑器：按字段类型分发。
       单选/多选/人员=标签锚点 + 浮动选项面板（查找/✓勾选/✕移除，设计稿 PixPin_2026-10-15_20-39-09）；
       数字=数字框，日期=日期，其余=文本 -->
  <div v-if="isEnum || isMember" class="enum-val" @click.stop="openPop">
    <div class="ev-tags">
      <template v-if="selectedOptions.length">
        <span v-for="o in selectedOptions" :key="o.id" class="ev-tag"
              :style="isEnum ? { background: optionColor(o.color).value, color: optionColor(o.color).text } : {}">
          {{ o.label }}
          <span class="ev-x" data-smart-tip="移除" @click.stop="removeOpt(o.id)">✕</span>
        </span>
      </template>
      <span v-else class="ev-ph">请选择</span>
    </div>
    <span class="ev-caret st-icon-action"><StIcon :name="open ? 'caret-up' : 'caret-down'" :size="10" /></span>

    <!-- 浮动选项面板 -->
    <div v-if="open" class="ev-pop" @click.stop @mousedown.stop>
      <el-input v-model="kw" size="small" :placeholder="isMember ? '查找成员' : '查找选项'" clearable />
      <div class="ev-sub">多选</div>
      <div class="ev-list">
        <div v-for="o in filteredOptions" :key="o.id" class="ev-item" @click="toggle(o.id)">
          <span class="ev-check">{{ val.includes(o.id) ? '✓' : '' }}</span>
          <span v-if="isEnum" class="opt-tag"
                :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">{{ o.label }}</span>
          <span v-else class="opt-name">{{ o.label }}</span>
        </div>
        <div v-if="!filteredOptions.length" class="opt-empty">无匹配{{ isMember ? '成员' : '选项' }}</div>
      </div>
    </div>
  </div>
  <el-input-number v-else-if="isNumber" v-model="val" size="small" class="val-editor" :controls="numberControls"
                   @change="$emit('update', val)" />
  <!-- 日期（参照 PixPin_2026-10-18_00-16-20）：左侧日期模式（具体日期 / 今天 / 本周 / 过去 7 天内…），
       选「具体日期」时右侧出日期选择。值 = { mode, date? }，相对模式查询时按当天换算（后端 pyquery.date_mode_range）。
       :teleported="false"：弹层渲染在面板内部——teleport 到 body 时点选项会被外层 el-popover 视为"点击外部"
       而关掉整个筛选/填色面板；strategy fixed：不被筛选面板的滚动区裁剪 -->
  <div v-else-if="isDate" class="date-val">
    <el-select :model-value="dateMode" size="small" class="dv-mode" :teleported="false" clearable placeholder="请选择"
               popper-class="dv-mode-pop" :popper-options="FIXED_POPPER" @change="onModeChange" @clear="onModeClear">
      <el-option v-for="o in modeOptions" :key="o.value" :value="o.value" :label="o.label"
                 :class="{ 'dv-exact': o.value === 'exact' }">
        <span class="dv-ck">{{ o.value === dateMode ? '✓' : '' }}</span>{{ o.label }}
      </el-option>
    </el-select>
    <el-date-picker v-if="dateMode === 'exact'" :model-value="exactDate" type="date" value-format="YYYY-MM-DD"
                    :format="dateFormat" placeholder="选择日期" size="small" class="dv-date" :teleported="false"
                    :popper-options="FIXED_POPPER" @update:model-value="onExactDate" />
  </div>
  <el-input-number v-else-if="isRelativeDate" v-model="val" size="small" class="val-editor" :controls="numberControls"
                   :min="1" placeholder="天数" @change="$emit('update', val)" />
  <el-input v-else v-model="val" size="small" class="val-editor" placeholder="请输入"
            @input="$emit('update', val)" />
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'
import { dateModesFor, dayjsDateFormat, isDateModeValue } from '../../../smart/utils/format.js'

const props = defineProps({ field: Object, operator: String, value: [String, Number, Array], numberControls: { type: Boolean, default: true } })
const emit = defineEmits(['update'])

const members = inject('smartMembers', { value: [] })
const ENUM_LIKE = ['singleSelect', 'multiSelect', 'member', 'createdBy', 'lastModifiedBy']
// 日期模式值只给日期编辑器用（dateValue）；切到「过去 N 天」等运算符时不能把对象喂给数字框
const initVal = (v, ft) => (isDateModeValue(v) ? null : v ?? (ENUM_LIKE.includes(ft) ? [] : null))
const val = ref(initVal(props.value, props.field?.field_type))
// 外部 value 变化、或切换字段（value 会重置为 undefined）时归一化：
// 枚举/人员类必须是数组，否则模板 val.length 会在 null 上炸
watch([() => props.value, () => props.field?.field_type], ([v, ft]) => { val.value = initVal(v, ft) })

const ft = computed(() => props.field?.field_type)
const isEnum = computed(() => ['singleSelect', 'multiSelect'].includes(ft.value))
const isMember = computed(() => ['member', 'createdBy', 'lastModifiedBy'].includes(ft.value))
const isNumber = computed(() => ['number', 'percent', 'currency', 'progress'].includes(ft.value))
const isDate = computed(() => ['date', 'createdTime', 'lastModifiedTime'].includes(ft.value)
  && !['today', 'pastDays', 'withinDays'].includes(props.operator))
const isRelativeDate = computed(() => ['date', 'createdTime', 'lastModifiedTime'].includes(ft.value)
  && ['pastDays', 'withinDays'].includes(props.operator))

// ---------- 日期模式值 { mode, date? }；旧数据为 'YYYY-MM-DD' 字符串，视为「具体日期」 ----------
const FIXED_POPPER = { strategy: 'fixed' }
const dateValue = computed(() => {
  const v = props.value
  if (isDateModeValue(v)) return v
  if (typeof v === 'string' && v) return { mode: 'exact', date: v.slice(0, 10) }
  return { mode: null, date: null }   // 未选：显示整宽「请选择」
})
const modeOptions = computed(() => dateModesFor(props.operator))
// 当前模式不在本运算符的可选范围内（如「晚于 本周」）视为未选
const dateMode = computed(() => (modeOptions.value.some(o => o.value === dateValue.value.mode) ? dateValue.value.mode : null))
const exactDate = computed(() => dateValue.value.date || null)
const dateFormat = computed(() => dayjsDateFormat({ ...(props.field?.options || {}), includeTime: false }).split(' ')[0])
function onModeChange(mode) {
  // 切到具体日期：沿用已选日期（没有则待选）；其余相对模式不带日期
  emit('update', mode === 'exact' ? { mode, date: exactDate.value } : { mode })
}
function onModeClear() { emit('update', null) }
function onExactDate(d) { emit('update', { mode: 'exact', date: d || null }) }

// 选项清单：枚举取字段选项（带颜色标签），人员取成员列表
const listOptions = computed(() => {
  if (isEnum.value) return (props.field?.options?.options || []).map(o => ({ id: o.id, label: o.label, color: o.color }))
  if (isMember.value) return (members.value || []).map(m => ({ id: m.id, label: m.name }))
  return []
})
const selectedOptions = computed(() => {
  const ids = new Set(Array.isArray(val.value) ? val.value : [val.value])
  return listOptions.value.filter(o => ids.has(o.id))
})

// 浮动面板：查找过滤 + 外点关闭
const open = ref(false)
const kw = ref('')
const filteredOptions = computed(() => {
  const k = kw.value.trim().toLowerCase()
  return k ? listOptions.value.filter(o => String(o.label).toLowerCase().includes(k)) : listOptions.value
})
function openPop() {
  if (open.value) return
  open.value = true
  const close = (e) => {
    if (e.target.closest?.('.ev-pop') || e.target.closest?.('.enum-val')) return
    open.value = false
    document.removeEventListener('mousedown', close)
  }
  setTimeout(() => document.addEventListener('mousedown', close), 0)
}
// 切换字段时收起面板（选项集已变）
watch(() => props.field?.field_name, () => { open.value = false; kw.value = '' })

function toggle(id) {
  const v = val.value.includes(id) ? val.value.filter(x => x !== id) : [...val.value, id]
  val.value = v
  emit('update', v)
}
function removeOpt(id) {
  const v = val.value.filter(x => x !== id)
  val.value = v
  emit('update', v)
}
</script>

<style scoped>
.val-editor { flex: 1; min-width: 120px; }

/* 日期：模式下拉 + 具体日期（各占一半，参照稿） */
.date-val { flex: 1; min-width: 0; display: flex; gap: 12px; }
.date-val :deep(.dv-mode), .date-val :deep(.dv-date.el-date-editor) { flex: 1 1 0; min-width: 0; width: auto; }
.date-val :deep(.el-date-editor .el-input__prefix) { display: none; }
/* 参照稿：两个框为白底细边（筛选面板 .fp-val 给输入框统一灰底，这里覆盖） */
.date-val :deep(.el-select__wrapper), .date-val :deep(.el-input__wrapper) { background: #fff !important; }

/* 枚举/人员值：标签锚点（选中项彩色标签 + ✕ + ▾），点击展开浮动面板。
   单行不换行：选中项放不下就在 .ev-tags 内截断（.enum-val 自身不能 overflow:hidden——
   绝对定位的浮动面板 .ev-pop 是它的子元素，会被一并裁掉） */
.enum-val {
  flex: 1; min-width: 120px; height: 26px; box-sizing: border-box; position: relative;
  display: flex; align-items: center; flex-wrap: nowrap; gap: 4px;
  border: 1px solid var(--el-border-color); border-radius: 4px; padding: 2px 6px; cursor: pointer;
}
.enum-val:hover { border-color: var(--el-color-primary); }
.ev-tags { flex: 1; min-width: 0; display: flex; align-items: center; gap: 4px; overflow: hidden; }
.ev-tag { flex: none; display: inline-flex; align-items: center; gap: 2px; border-radius: 4px; padding: 1px 6px; font-size: 12px; white-space: nowrap; }
.ev-x { cursor: pointer; opacity: .6; font-size: 10px; }
.ev-x:hover { opacity: 1; }
.ev-ph { color: var(--el-text-color-placeholder); font-size: 13px; }
.ev-caret { flex: none; color: var(--el-text-color-placeholder); font-size: 10px; }

/* 浮动选项面板：查找框 + ✓ 勾选清单 */
.ev-pop {
  position: absolute; left: 0; top: calc(100% + 4px); z-index: 20; width: 240px;
  background: #fff; border-radius: 8px; box-shadow: var(--el-box-shadow);
  padding: 8px; display: flex; flex-direction: column; gap: 6px; cursor: default;
}
.ev-sub { font-size: 12px; color: var(--el-text-color-secondary); }
.ev-list { display: flex; flex-direction: column; max-height: 220px; overflow: auto; }
.ev-item { display: flex; align-items: center; gap: 6px; padding: 4px 6px; border-radius: 4px; cursor: pointer; }
.ev-item:hover { background: var(--el-fill-color-light); }
.ev-check { flex: none; width: 14px; color: var(--el-color-primary); font-size: 12px; }
.opt-tag { border-radius: 4px; padding: 1px 8px; font-size: 12px; }
.opt-name { font-size: 13px; }
.opt-empty { color: var(--el-text-color-placeholder); font-size: 12px; padding: 8px 0; text-align: center; }
</style>

<style>
/* 日期模式下拉（:teleported=false 渲染在面板内，类名不带作用域）：✓ 当前项；「具体日期」与相对日期之间分隔线 */
.dv-mode-pop .el-select-dropdown__item { display: flex; align-items: center; font-weight: 400; color: var(--st-text-1); }
.dv-mode-pop .el-select-dropdown__item.is-selected { color: var(--st-text-1); background: var(--st-bg-hover); }
.dv-mode-pop .dv-ck { width: 22px; flex: none; color: var(--st-primary); }
.dv-mode-pop .el-select-dropdown__item.dv-exact { margin-bottom: 9px; position: relative; overflow: visible; }
.dv-mode-pop .el-select-dropdown__item.dv-exact::after { content: ''; position: absolute; left: 0; right: 0; bottom: -5px; height: 1px; background: var(--st-border); }
</style>
