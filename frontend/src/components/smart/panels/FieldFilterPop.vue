<template>
  <!-- 单字段筛选面板（参照 docs/智慧表格/表头工具栏/表头-过滤按钮点击-多选.png / -文本.png）：
       头部「筛选 + 作用范围胶囊」+ 右侧 📌 固定到工具栏 / ⋯ 更多；
       下方圆角卡：运算符（文字下拉「包含 ▾」）+ 🔍 → 枚举/人员：搜索框 + 已选择 N 项/清空 + 勾选清单；其余类型：值输入框。
       即时生效；列头漏斗与工具栏固定条件胶囊共用。值为空时：已固定的条件保留为「未填值」（不生效），未固定的移除 -->
  <div class="ffp" @click.stop @mousedown.stop>
    <div class="ffp-head">
      <b>筛选</b>
      <span class="ffp-scope">{{ scopeText }}</span>
      <span class="ffp-flex" />
      <el-tooltip :hide-after="0" :content="pinned ? '取消固定' : '固定到工具栏'" placement="top" :show-after="300">
        <span class="ffp-icon st-icon-action" :class="{ on: pinned }" @click="$emit('pin', !pinned)"><StIcon name="pin" :size="16" /></span>
      </el-tooltip>
      <el-popover v-model:visible="moreOpen" trigger="click" :hide-after="0" placement="bottom-end" :width="180"
                  :teleported="true" :show-arrow="false" :popper-options="MENU_POPPER" :popper-style="MENU_STYLE" popper-class="ffp-more-pop">
        <template #reference>
          <span class="ffp-icon st-icon-action" :class="{ on: moreOpen }" aria-label="更多"><StIcon name="more-h" :size="16" /></span>
        </template>
        <div class="ffp-menu" @click.stop @mousedown.stop>
          <div class="ffp-mi" @click="moreOpen = false; $emit('open-panel')"><StIcon name="filter" :size="14" />打开筛选面板</div>
          <div class="ffp-mi danger" :class="{ off: !hasCondition }" @click="hasCondition && remove()"><StIcon name="trash" :size="14" />删除条件</div>
        </div>
      </el-popover>
    </div>

    <div class="ffp-card">
      <div class="ffp-oprow">
        <el-popover v-model:visible="opOpen" trigger="click" :hide-after="0" placement="bottom-start" :width="180"
                    :teleported="true" :show-arrow="false" :popper-options="MENU_POPPER" :popper-style="MENU_STYLE" popper-class="ffp-operator-pop">
          <template #reference>
            <span class="ffp-op">{{ opLabel(field, op) }}<StIcon name="chevron-down" :size="13" /></span>
          </template>
          <div class="ffp-menu ffp-op-menu" @click.stop @mousedown.stop>
            <div v-for="o in ops" :key="o" class="ffp-mi" :class="{ cur: o === op }" @click="pickOp(o)">
              {{ opLabel(field, o) }}<StIcon v-if="o === op" name="check" :size="13" class="ffp-mi-ck" />
            </div>
          </div>
        </el-popover>
        <span v-if="needsValue && (isEnum || isMember)" class="ffp-icon sq st-icon-action" aria-label="搜索" @click="focusSearch"><StIcon name="search" :size="15" /></span>
      </div>

      <template v-if="needsValue">
        <!-- 枚举/人员：搜索 + 勾选清单 -->
        <template v-if="isEnum || isMember">
          <div class="ffp-sep" />
          <FilterOptionList ref="listRef" :options="listOptions" :selected="selected" :kind="isMember ? 'member' : 'enum'"
                            search-mode="always" @toggle="toggle" @clear="setSelected([])" />
        </template>
        <!-- 文本类：灰底输入框 + ✕ 清除 -->
        <div v-else-if="isTextLike" class="ffp-text">
          <input ref="textRef" v-model="textVal" class="st-control st-control--native ffp-input" placeholder="请输入" @input="onText" />
          <span v-if="textVal" class="ffp-x st-icon-action" @click="clearText"><StIcon name="close" :size="14" /></span>
        </div>
        <!-- 数字/日期等：通用值编辑器 -->
        <div v-else class="ffp-generic"><ConditionValue :field="field" :operator="op" :value="value" @update="onValue" /></div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import ConditionValue from './ConditionValue.vue'
import { isCondValueEmpty } from '../../../smart/utils/format.js'
import FilterOptionList from './FilterOptionList.vue'
import StIcon from '../icons/StIcon.vue'
import { filterOpsOf, NO_VALUE_OPS, opLabel } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  field: { type: Object, required: true },
  condition: { type: Object, default: null },   // 该字段的现有条件（无则 null）
  scopeText: { type: String, default: '' },
  pinned: { type: Boolean, default: false },
})
const emit = defineEmits(['change', 'pin', 'open-panel'])
const members = inject('smartMembers', { value: [] })
// 菜单独立挂到 body，使用视口边界翻转；低视口保留菜单内部滚动。
const MENU_POPPER = { strategy: 'fixed', modifiers: [
  { name: 'preventOverflow', options: { boundary: [], rootBoundary: 'viewport', padding: 12, altAxis: true, tether: false } },
] }
const MENU_STYLE = { padding: '6px', maxWidth: 'calc(100vw - 24px)', boxSizing: 'border-box' }

// AI 字段按输出类型筛选
const ftype = computed(() => (props.field.field_type === 'ai' ? (props.field.options?.outputType || 'text') : props.field.field_type))
const ops = computed(() => filterOpsOf(props.field))
const isEnum = computed(() => ['singleSelect', 'multiSelect'].includes(ftype.value))
const isMember = computed(() => ['member', 'createdBy', 'lastModifiedBy'].includes(ftype.value))
const isTextLike = computed(() => ['text', 'url', 'barcode', 'location', 'autoNumber', 'formula', 'lookup'].includes(ftype.value)
  && !['isEmpty', 'isNotEmpty'].includes(op.value))

const op = ref('contains')
const value = ref(undefined)
const textVal = ref('')
const selected = ref([])
const opOpen = ref(false)
const moreOpen = ref(false)
const listRef = ref(null)
const textRef = ref(null)

watch(() => [props.field, props.condition], () => {
  op.value = props.condition?.operator || ops.value[0] || 'contains'
  const v = props.condition?.value
  if (isEnum.value || isMember.value) selected.value = Array.isArray(v) ? [...v] : (v != null ? [v] : [])
  else { value.value = v; textVal.value = v == null ? '' : String(v) }
}, { immediate: true, deep: true })

onMounted(() => nextTick(() => (listRef.value ? listRef.value.focusSearch() : textRef.value?.focus())))

const needsValue = computed(() => !NO_VALUE_OPS.includes(op.value))
const hasCondition = computed(() => !!props.condition)

const listOptions = computed(() => {
  if (isEnum.value) return (props.field.options?.options || []).map(o => ({ id: o.id, label: o.label, color: o.color }))
  // 人员：首项「我（根据查看者动态变化）」，与工具栏筛选面板一致
  if (isMember.value) return [{ id: '$viewer', label: '我', viewer: true }, ...(members.value || []).map(m => ({ id: m.id, label: m.name }))]
  return []
})

function focusSearch() { listRef.value?.focusSearch() }
function pickOp(o) { op.value = o; opOpen.value = false; commit(); nextTick(() => (listRef.value ? listRef.value.focusSearch() : textRef.value?.focus())) }
function toggle(id) { setSelected(selected.value.includes(id) ? selected.value.filter(x => x !== id) : [...selected.value, id]) }
function setSelected(v) { selected.value = v; commit() }
function onValue(v) { value.value = v; commit() }
let textTimer = null
function onText() {
  clearTimeout(textTimer)
  textTimer = setTimeout(() => { value.value = textVal.value; commit() }, 300)   // 输入防抖，避免每个字都重查
}
function clearText() { textVal.value = ''; value.value = ''; commit(); textRef.value?.focus() }
const isEmpty = isCondValueEmpty   // 含日期模式「具体日期」未选日期

function commit() {
  const v = needsValue.value ? ((isEnum.value || isMember.value) ? selected.value : value.value) : undefined
  const cond = { fieldId: props.field.field_name, operator: op.value, value: isEmpty(v) ? undefined : v }
  // 值空：已固定的保留为未填值条件（不生效），未固定的移除
  if (needsValue.value && isEmpty(v) && !props.pinned) { emit('change', null); return }
  emit('change', cond)
}
function remove() { moreOpen.value = false; emit('change', null, { unpin: true }) }
</script>

<style scoped>
.ffp { width: 100%; display: flex; flex-direction: column; gap: 12px; --el-color-primary: var(--st-primary); }
.ffp-head { display: flex; align-items: center; gap: 10px; }
.ffp-head b { font-size: var(--st-font-size); color: var(--st-text-2); }
.ffp-scope { font-size: var(--st-font-size); color: var(--st-text-2); border: 1px solid #E3E5E8; border-radius: 999px; padding: 2px 12px; background: #fff; }
.ffp-flex { flex: 1; }
.ffp-icon { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 6px; color: var(--st-text-2); cursor: pointer; }
.ffp-icon:hover, .ffp-icon.on { background: #F2F3F5; color: var(--st-text-2); }
.ffp-icon.on :deep(svg) { color: var(--st-text-2); }
.ffp-icon.sq { width: 30px; height: 30px; background: #F2F3F5; }
.ffp-icon.sq:hover { background: #E6E8EA; }
.ffp-menu { min-width: 0; max-height: min(280px, calc(100dvh - 40px)); overflow-y: auto; }
.ffp-mi { min-height: 32px; }
.ffp-mi { display: flex; align-items: center; gap: 8px;  padding: 0 10px; border-radius: 6px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; white-space: nowrap;  height: var(--st-list-item-height); box-sizing: border-box; }
.ffp-mi:hover { background: #F2F3F5; }
.ffp-mi.cur { color: var(--st-primary); }
.ffp-mi-ck { margin-left: auto; }
.ffp-mi.danger { color: var(--el-color-danger); }
.ffp-mi.off { opacity: .4; cursor: default; }
.ffp-card { border: 1px solid #EBECEE; border-radius: 12px; padding: 12px 14px 10px; display: flex; flex-direction: column; gap: 10px; }
.ffp-oprow { display: flex; align-items: center; justify-content: space-between; min-height: 30px; }
.ffp-op { display: inline-flex; align-items: center; gap: 3px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; padding: 2px 4px; border-radius: 4px; }
.ffp-op:hover { background: #F2F3F5; color: var(--st-text-2); }
.ffp-sep { height: 1px; background: #EBECEE; margin: 0 -2px; }
.ffp-input { width: 100%; box-sizing: border-box; height: 44px; border: 1px solid transparent; border-radius: 8px; background: #F2F3F5; padding: 0 14px;
             font-size: var(--st-font-size); color: var(--st-text-2); outline: none; }
.ffp-input::placeholder { color: #B5B9C0; }
.ffp-input:focus { border-color: var(--st-primary); background: #F2F3F5; }
.ffp-text { position: relative; }
.ffp-text .ffp-input { padding-right: 38px; }
.ffp-x { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); display: inline-flex; color: var(--st-text-2); cursor: pointer; padding: 2px; border-radius: 4px; }
.ffp-x:hover { background: #E3E5E8; }
.ffp-generic :deep(.el-input__wrapper), .ffp-generic :deep(.el-input-number), .ffp-generic :deep(.el-date-editor) { width: 100%; }
.ffp-generic :deep(.el-input__wrapper) { min-height: 40px; background: #F2F3F5; box-shadow: none; border-radius: 8px; }
</style>
