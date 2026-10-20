<template>
  <!-- 筛选勾选清单（工具栏「筛选」面板 / 列头漏斗面板 / 工具栏固定条件胶囊 三处共用，行高、文字、复选框、搜索框完全一致）：
       搜索框 +「已选择 N 项 · 清空」+ 清单（复选框 + 单选/多选彩色标签 / 人员头像胶囊 / 「我 (根据查看者动态变化)」）。
       searchMode：always = 搜索框常显（单字段面板）；toggle = 点计数行的 🔍 才展开（多条件面板，省空间） -->
  <div class="fol">
    <!-- 搜索框：always 模式常显在最上方；toggle 模式点 🔍 后展开在计数行下方（参照 PixPin_2026-10-18_00-35-43） -->
    <input v-if="searchMode === 'always'" ref="kwRef" v-model="kw" class="fol-search"
           :placeholder="kind === 'member' ? '搜索成员' : '搜索'" />
    <!-- 计数行：未选时「请选择」（参照 PixPin_2026-10-18_00-27-29），已选时「已选择 N 项 · 清空」 -->
    <div class="fol-count">
      <span v-if="selected.length">已选择 {{ selected.length }} {{ kind === 'member' ? '人' : '项' }}</span>
      <span v-else>请选择</span>
      <span class="fol-acts">
        <span v-if="selected.length" class="fol-clear" @click="$emit('clear')">清空</span>
        <template v-if="searchMode === 'toggle'">
          <span v-if="selected.length" class="fol-vsep" />
          <span class="fol-act st-icon-action" :class="{ on: searchOpen }" data-smart-tip="搜索" @click="toggleSearch"><StIcon name="search" :size="14" /></span>
        </template>
      </span>
    </div>
    <input v-if="searchMode === 'toggle' && searchOpen" ref="kwRef" v-model="kw" class="fol-search"
           :placeholder="kind === 'member' ? '搜索成员' : '搜索'" />
    <div class="fol-list" :style="maxHeight ? { maxHeight: `${maxHeight}px` } : {}">
      <label v-for="o in filtered" :key="o.id" class="fol-item">
        <el-checkbox :model-value="selected.includes(o.id)" class="fol-ck" @change="$emit('toggle', o.id)" />
        <span v-if="o.viewer" class="fol-me">我<span class="fol-me-hint">(根据查看者动态变化)</span></span>
        <span v-else-if="kind === 'member'" class="fol-member"><span class="fol-av">{{ (o.label || '?')[0] }}</span>{{ o.label }}</span>
        <span v-else class="fol-tag" :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">{{ o.label }}</span>
      </label>
      <div v-if="!filtered.length" class="fol-empty">无匹配{{ kind === 'member' ? '成员' : '选项' }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'
import { optionColor } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  options: { type: Array, default: () => [] },   // [{id, label, color?, viewer?}]
  selected: { type: Array, default: () => [] },
  kind: { type: String, default: 'enum' },       // enum | member
  searchMode: { type: String, default: 'always' },
  maxHeight: { type: Number, default: 320 },
})
defineEmits(['toggle', 'clear'])

const kw = ref('')
const searchOpen = ref(false)
const kwRef = ref(null)
const filtered = computed(() => {
  const k = kw.value.trim().toLowerCase()
  return k ? props.options.filter(o => String(o.viewer ? '我' : o.label || '').toLowerCase().includes(k)) : props.options
})
function toggleSearch() {
  searchOpen.value = !searchOpen.value
  if (!searchOpen.value) kw.value = ''
  else nextTick(() => kwRef.value?.focus())
}
function focusSearch() {
  if (props.searchMode === 'toggle') searchOpen.value = true
  nextTick(() => kwRef.value?.focus())
}
defineExpose({ focusSearch })
</script>

<style scoped>
.fol { display: flex; flex-direction: column; gap: 8px; --el-color-primary: var(--st-primary); }
/* 尺寸/取色参照 PixPin_2026-10-18_00-27-29：搜索框 38px 灰底 #EDEFEF、选项行 38px、复选框 18px、标签 15px */
.fol-search { width: 100%; box-sizing: border-box; height: 38px; border: 1px solid transparent; border-radius: 6px; background: #EDEFEF;
              padding: 0 12px; font-size: 15px; color: var(--st-text-1); outline: none; }
.fol-search::placeholder { color: #B5B9C0; }
.fol-search:focus { border-color: var(--st-primary); }
.fol-count { display: flex; justify-content: space-between; align-items: center; min-height: 24px; font-size: 15px; color: #6B6F74; padding: 0 0 0 6px; }
.fol-acts { display: inline-flex; align-items: center; gap: 10px; }
.fol-clear { cursor: pointer; }
.fol-clear:hover { color: var(--st-primary); }
.fol-clear.dim { color: #C9CDD4; cursor: default; }
.fol-vsep { width: 1px; height: 14px; background: #E5E6EB; }
/* 搜索按钮：24px 灰底方块 */
.fol-act { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 4px;
  cursor: pointer; color: var(--st-text-2); background: #E2E3E4; }
.fol-act:hover, .fol-act.on { background: #D8DADC; color: var(--st-text-1); }
.fol-list { display: flex; flex-direction: column; overflow-y: auto; }
.fol-item { display: flex; align-items: center; gap: 12px; min-height: 38px; padding: 0 6px; border-radius: 6px; cursor: pointer; user-select: none; flex: none; }
.fol-item:hover { background: #EDEFEF; }
/* 复选框：16px 圆角方框，主色勾选 */
.fol-ck { height: auto; margin-right: 0; }
.fol-ck :deep(.el-checkbox__inner) { width: 18px; height: 18px; border-radius: 3px; border-color: #C9CDD4; background: #fff; }
/* 勾：沿用 EP 2.14 的居中方式（top/left 50% + translate），只调大小与粗细——改 left/top 会和 translate 叠加导致勾偏左上 */
.fol-ck :deep(.el-checkbox__inner::after) { width: 4px; height: 8.5px; border-width: 0 1.8px 1.8px 0; }
.fol-ck :deep(.el-checkbox__input.is-checked .el-checkbox__inner) { background: var(--st-primary); border-color: var(--st-primary); }
/* 选项文字：15px；标签 4px 圆角、27px 高 */
.fol-tag { display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
           border-radius: 4px; padding: 2px 8px; font-size: 15px; line-height: 23px; }
.fol-member { display: inline-flex; align-items: center; gap: 6px; background: #EFF0F1; border-radius: 4px; padding: 2px 8px 2px 3px;
              font-size: 15px; line-height: 23px; color: var(--st-text-1); }
.fol-av { width: 18px; height: 18px; border-radius: 3px; background: #F6903D; color: #fff; font-size: 11px; display: inline-flex; align-items: center; justify-content: center; }
.fol-me { font-size: 15px; line-height: 23px; color: var(--st-text-1); }
.fol-me-hint { margin-left: 4px; color: var(--st-text-3); }
.fol-empty { font-size: 13px; color: var(--st-text-3); text-align: center; padding: 12px 0; }
</style>
