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
          <span class="ev-x" title="移除" @click.stop="removeOpt(o.id)">✕</span>
        </span>
      </template>
      <span v-else class="ev-ph">请选择</span>
    </div>
    <span class="ev-caret">{{ open ? '▴' : '▾' }}</span>

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
  <el-input-number v-else-if="isNumber" v-model="val" size="small" class="val-editor"
                   @change="$emit('update', val)" />
  <!-- :teleported="false"：日历弹层渲染在面板内部——teleport 到 body 时点日历会被
       外层 el-popover 视为"点击外部"而关掉整个筛选/填色面板 -->
  <el-date-picker v-else-if="isDate" v-model="val" type="date" value-format="YYYY-MM-DD" size="small"
                  :teleported="false" class="val-editor" @change="$emit('update', val)" />
  <el-input-number v-else-if="isRelativeDate" v-model="val" size="small" class="val-editor"
                   :min="1" placeholder="天数" @change="$emit('update', val)" />
  <el-input v-else v-model="val" size="small" class="val-editor" placeholder="请输入"
            @input="$emit('update', val)" />
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({ field: Object, operator: String, value: [String, Number, Array] })
const emit = defineEmits(['update'])

const members = inject('smartMembers', { value: [] })
const ENUM_LIKE = ['singleSelect', 'multiSelect', 'member', 'createdBy', 'lastModifiedBy']
const initVal = (v, ft) => v ?? (ENUM_LIKE.includes(ft) ? [] : null)
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
const isRelativeDate = computed(() => isDate.value && ['pastDays', 'withinDays'].includes(props.operator))

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
