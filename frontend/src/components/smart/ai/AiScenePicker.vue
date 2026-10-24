<template>
  <el-popover :visible="open" trigger="click" placement="bottom-start" :width="menuWidth" :disabled="disabled"
              :show-arrow="false" :enterable="false" :hide-after="0" :popper-options="popperOptions" popper-class="st-tbpanel ai-scene-picker-pop" @show="onShow">
    <template #reference>
      <button ref="triggerRef" type="button" class="st-control st-control--native scene-trigger" :disabled="disabled" :aria-expanded="open" aria-label="选择 AI 场景" @click="open = !open">
        <span>{{ selected?.label || '选择 AI 场景' }}</span><StIcon :name="open ? 'chevron-up' : 'chevron-down'" :size="14" />
      </button>
    </template>
    <div ref="menuRef" class="asp-picker" @mouseenter="cancelHide" @mouseleave="scheduleHide" @keydown.esc.stop.prevent="open = false">
      <div class="asp-browser">
      <input ref="searchRef" v-model="query" class="st-control st-control--native scene-search" placeholder="搜索场景名称或用途，如：翻译、客户" aria-label="搜索 AI 场景" @keydown.down.prevent="focusResult()" />
      <div class="scene-columns">
        <nav class="scene-categories" aria-label="场景分类">
          <SmartListItem v-for="c in groups" :key="c.key" tag="button" type="button" :selected="category === c.key && !query.trim()" @click="chooseCategory(c.key)">{{ c.label }}</SmartListItem>
        </nav>
        <div class="scene-results">
          <div class="scene-heading">{{ query.trim() ? '全部分类的搜索结果' : groups.find(c => c.key === category)?.label }} · {{ results.length }}</div>
          <div ref="resultsRef" class="scene-list" role="listbox" aria-label="AI 场景" @keydown.down.prevent="focusResult(resultColumnCount())" @keydown.up.prevent="focusResult(-resultColumnCount())" @keydown.right.prevent="focusResult(1)" @keydown.left.prevent="focusResult(-1)">
            <SmartListItem v-for="s in results" :key="s.key" tag="button" type="button" role="option" :aria-selected="s.key === modelValue"
                           :selected="s.key === modelValue" :aria-disabled="!!s.disabled" @mouseenter="showPreview(s)" @focus="showPreview(s)" @click="pick(s)">
              <span class="scene-label">{{ s.label }}</span>
              <span class="scene-meta">{{ s.formula ? '公式' : s.local ? '代码' : 'LLM' }}</span>
              <StIcon v-if="s.key === modelValue" name="check" :size="14" />
            </SmartListItem>
            <div v-if="!results.length" class="scene-empty">没有匹配的场景，可修改关键词或使用自定义。</div>
          </div>
        </div>
      </div>
      <SmartListItem v-if="custom" tag="button" type="button" class="scene-custom" :disabled="custom.disabled" :selected="modelValue === custom.key" @click="pick(custom)">
        <StIcon name="sparkle" :size="15" /><span>自定义 AI 字段</span><span class="scene-meta">直接描述处理规则</span>
      </SmartListItem>
      </div>
      <el-popover :visible="open && !!preview" virtual-triggering :virtual-ref="menuRef" placement="right-start" :fallback-placements="['left-start']" :popper-options="detailPopperOptions" :width="460" :offset="12" :show-arrow="false" popper-class="st-tbpanel ai-template-detail-pop">
        <aside ref="detailRef" class="asp-detail" aria-label="模板详情" @mouseenter="cancelHide" @mouseleave="scheduleHide" @keydown.esc.stop.prevent="preview = null">
          <AiTemplateIntro v-if="preview" :key="preview.key" :scene="preview" expanded standalone />
        </aside>
      </el-popover>
    </div>
  </el-popover>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import SmartListItem from '../common/SmartListItem.vue'
import AiTemplateIntro from './AiTemplateIntro.vue'
const props = defineProps({ modelValue: String, scenes: { type: Array, default: () => [] }, categories: { type: Array, default: () => [] }, disabled: Boolean, popperOptions: Object })
const emit = defineEmits(['change'])
const open = ref(false), query = ref(''), category = ref(''), preview = ref(null), searchRef = ref(null), resultsRef = ref(null)
const menuRef = ref(null)
const detailPopperOptions = {
  strategy: 'fixed',
  modifiers: [{ name: 'preventOverflow', options: { boundary: 'viewport', rootBoundary: 'viewport', padding: 12, tether: false } }],
}
const triggerRef = ref(null), detailRef = ref(null)
const menuWidth = ref(520)
let triggerObserver
function syncMenuWidth() {
  const width = triggerRef.value?.getBoundingClientRect().width
  if (width) menuWidth.value = width
}
onMounted(() => {
  syncMenuWidth()
  triggerObserver = new ResizeObserver(syncMenuWidth)
  if (triggerRef.value) triggerObserver.observe(triggerRef.value)
})
onBeforeUnmount(() => triggerObserver?.disconnect())
// Both teleported popovers belong to the same interaction area.
function onOutsidePointer(event) {
  if (!open.value) return
  if ([triggerRef.value, menuRef.value, detailRef.value].some(el => el?.contains(event.target))) return
  open.value = false
}
onMounted(() => document.addEventListener('pointerdown', onOutsidePointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onOutsidePointer))
let hideTimer
function cancelHide() { clearTimeout(hideTimer) }
function scheduleHide() { cancelHide(); hideTimer = setTimeout(() => { preview.value = null }, 180) }
function showPreview(scene) { cancelHide(); preview.value = scene }
onBeforeUnmount(cancelHide)
watch(open, value => { if (!value) { cancelHide(); preview.value = null } })
const selected = computed(() => props.scenes.find(s => s.key === props.modelValue))
const custom = computed(() => props.scenes.find(s => s.key === 'custom'))
const groups = computed(() => props.categories.filter(c => props.scenes.some(s => s.category === c.key && s.key !== 'custom' && !s.disabled)))
const results = computed(() => {
  const terms = query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return props.scenes.filter(s => s.key !== 'custom' && !s.disabled && (terms.length
    ? terms.every(term => `${s.label} ${s.desc || ''} ${s.inputHint || ''} ${s.executionLabel || ''} ${props.categories.find(c => c.key === s.category)?.label || ''}`.toLocaleLowerCase().includes(term))
    : s.category === category.value))
})
async function onShow() {
  if (!open.value) return
  syncMenuWidth()
  query.value = ''
  const selectedCategory = !selected.value?.disabled && groups.value.find(c => c.key === selected.value?.category)
  category.value = selectedCategory?.key || groups.value.find(c => c.key === 'recommend')?.key || groups.value[0]?.key || ''
  preview.value = null
  await nextTick()
  if (!open.value) return
  searchRef.value?.focus({ preventScroll: true })
  menuRef.value?.querySelector('.scene-categories .is-selected')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  resultsRef.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
}
function chooseCategory(key) { category.value = key; query.value = ''; preview.value = null }
function pick(scene) { if (props.disabled || scene.disabled) return; emit('change', scene.key); open.value = false }
function resultColumnCount() {
  return resultsRef.value ? getComputedStyle(resultsRef.value).gridTemplateColumns.split(' ').length : 2
}
function focusResult(step = 0) {
  const items = [...(resultsRef.value?.querySelectorAll('button:not(:disabled)') || [])]
  const current = items.indexOf(document.activeElement)
  items[Math.max(0, Math.min(items.length - 1, current < 0 ? 0 : current + step))]?.focus()
}
watch(query, () => { preview.value = null })
watch(() => props.disabled, disabled => { if (disabled) open.value = false })
</script>
<style>
.ai-scene-picker-pop.st-tbpanel.el-popover.el-popper { padding: 0; max-width: calc(100vw - 24px); max-height: calc(100vh - 24px); overflow: hidden; box-sizing: border-box; }
.ai-template-detail-pop.st-tbpanel.el-popover.el-popper { padding: 0; max-width: calc(100vw - 24px); box-sizing: border-box; overflow: hidden; }
</style>
<style scoped>
.scene-trigger { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; text-align: left; cursor: pointer; }
.scene-trigger > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scene-trigger:disabled { cursor: not-allowed; opacity: .6; }
.asp-picker { display: block; width: 100%; min-width: 0; }
.asp-picker > .asp-browser { padding: 12px; display: flex; flex-direction: column; height: min(430px, calc(100vh - 48px)); min-width: 0; min-height: 0; box-sizing: border-box; }
.scene-search { width: 100%; margin-bottom: 8px; padding-left: 12px; padding-right: 12px; }
.scene-columns { display: flex; flex: 1; min-height: 0; }
.scene-categories { width: 112px; flex: none; overflow-y: auto; padding-right: 8px; border-right: 1px solid #EBECEE; }
.scene-categories .st-list-item, .scene-list .st-list-item { width: 100%; border: 0; text-align: left; background-color: transparent; }
.scene-categories .is-selected, .scene-list .is-selected { background-color: var(--st-primary-weak); }
.scene-categories .st-list-item:hover, .scene-list .st-list-item:hover { background-color: var(--st-bg-hover); }
.scene-results { flex: 1; min-width: 0; padding-left: 8px; display: flex; flex-direction: column; }
.scene-heading { font-size: 12px; color: var(--st-text-3); line-height: 24px; padding-left: 8px; }
.scene-list { overflow-y: auto; flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-content: start; gap: 0 8px; }
.scene-list .st-list-item { min-width: 0; }
.scene-list .scene-meta { flex: none; color: var(--st-text-4); font-weight: 400; }
.scene-empty { grid-column: 1 / -1; }
@media (max-width: 540px) { .scene-list { grid-template-columns: minmax(0, 1fr); } }
.scene-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scene-meta { font-size: 12px; color: var(--st-text-3); margin-left: auto; }
.scene-custom { margin-top: 8px; width: 100%; flex-shrink: 0; border: 0; background: transparent; }
.scene-empty { padding: 12px 8px; color: var(--st-text-3); line-height: 22px; }
.asp-detail { max-height: calc(100dvh - 24px); overflow-x: hidden; overflow-y: auto; scrollbar-width: none; padding: 16px; box-sizing: border-box; background: linear-gradient(145deg, #F6F0FC, #F7F8FA 150px); overscroll-behavior: contain; }
.asp-detail::-webkit-scrollbar { display: none; }
.scene-list [aria-disabled="true"] { color: var(--st-text-3); }
</style>
