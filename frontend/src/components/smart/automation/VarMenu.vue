<template>
  <!-- 变量菜单（§11.2 变量系统）：仪表盘ⓘ / 分析报告ⓘ / 自然时间 / 第 N 步的 —— 二级飞出，
       对齐参照 右上角工具栏-新建自动化提醒.png（悬停ⓘ提示「插入的仪表盘将以图片形式展示」） -->
  <div ref="menuRoot" class="vm" :class="{ 'vm-inline': inline }" :style="inline ? undefined : posStyle" @mousedown.prevent @click.stop>
    <div v-if="!valueMode" class="vm-item has-sub" @mouseenter="openSubmenu('dash')" @mouseleave="closeSubmenu">
      仪表盘
      <el-tooltip :hide-after="0" content="插入的仪表盘将以链接形式展示" placement="top"><StIcon name="info" :size="13" class="vm-i" /></el-tooltip>
      <StIcon name="chevron-right" :size="12" class="vm-caret" />
      <div v-if="hover === 'dash'" class="vm-sub">
        <div v-for="d in dashboards" :key="d.id" class="vm-item"
             @click="pick({ kind: 'dashboard', entryId: d.id, name: d.name }, `仪表盘 ${d.name}`)">
          <StIcon name="dashboard" :size="14" />{{ d.name }}
        </div>
        <div v-if="!dashboards.length" class="vm-empty">暂无仪表盘</div>
      </div>
    </div>
    <div v-if="!valueMode" class="vm-item has-sub" @mouseenter="openSubmenu('report')" @mouseleave="closeSubmenu">
      分析报告
      <el-tooltip :hide-after="0" content="插入的分析报告将以链接形式展示" placement="top"><StIcon name="info" :size="13" class="vm-i" /></el-tooltip>
      <StIcon name="chevron-right" :size="12" class="vm-caret" />
      <div v-if="hover === 'report'" class="vm-sub">
        <div v-for="r in reports" :key="r.id" class="vm-item" @click="pick({ kind: 'report', entryId: r.id, name: r.name }, `分析报告 ${r.name}`)">
          <StIcon name="file" :size="14" />{{ r.name }}
        </div>
        <div v-if="!reports.length" class="vm-empty">暂无分析报告</div>
      </div>
    </div>
    <div v-if="!hideTime" class="vm-item has-sub" @mouseenter="openSubmenu('time')" @mouseleave="closeSubmenu">
      自然时间 <StIcon name="chevron-right" :size="12" class="vm-caret" />
      <div v-if="hover === 'time'" class="vm-sub">
        <div class="vm-item" @click="pick({ kind: 'time', key: 'today' }, '今天')">今天</div>
        <div class="vm-item" @click="pick({ kind: 'time', key: 'now' }, '现在')">现在</div>
      </div>
    </div>
    <div v-for="s in steps" :key="s.step" class="vm-item has-sub" @mouseenter="openSubmenu(`s${s.step}`)" @mouseleave="closeSubmenu">
      第{{ s.step }}步{{ s.name }}的 <StIcon name="chevron-right" :size="12" class="vm-caret" />
      <div v-if="hover === `s${s.step}`" class="vm-sub vm-sub-fields">
        <FieldPickList :fields="variableFields(s)" :column-groups="s.columnGroups ?? []" :max-height="260"
                       @pick="f => pick(f.variable, `第${s.step}步${s.name}的 ${f.label}`)" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import StIcon from '../icons/StIcon.vue'
import FieldPickList from '../panels/FieldPickList.vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },        // [{step, name, vars: [{key, label, icon, var}]}]
  dashboards: { type: Array, default: () => [] },   // [{id, name}]
  reports: { type: Array, default: () => [] },
  x: { type: Number, default: 0 },
  y: { type: Number, default: 0 },
  valueMode: { type: Boolean, default: false },     // 赋值场景：只给时间与步骤变量
  inline: Boolean,
  hideTime: Boolean,
})
const emit = defineEmits(['pick'])
const hover = ref(null)
let closeTimer
function openSubmenu(key) {
  clearTimeout(closeTimer)
  hover.value = key
}
function closeSubmenu() {
  clearTimeout(closeTimer)
  // 留出跨越父菜单与子菜单间隙的时间；进入子菜单时父节点会再次收到 mouseenter。
  closeTimer = setTimeout(() => { hover.value = null }, 80)
}
function variableFields(step) {
  return (step.vars || []).map(v => ({ field_name: v.key, label: v.label, field_type: v.icon || 'text', variable: v.var }))
}
const menuRoot = ref(null)
let layoutFrame = 0
function placeSubmenu() {
  const panel = menuRoot.value?.querySelector('.vm-sub')
  if (!panel) return
  const margin = 12
  panel.style.maxHeight = `${Math.max(0, Math.min(320, window.innerHeight - margin * 2))}px`
  const anchor = panel.parentElement.getBoundingClientRect()
  const bounds = panel.getBoundingClientRect()
  const top = Math.max(margin, Math.min(anchor.top - 6, window.innerHeight - margin - bounds.height))
  const leftSide = anchor.left - bounds.width - 4
  const rightSide = anchor.right + 4
  let left = props.inline ? leftSide : rightSide
  if (left < margin) left = rightSide
  if (left + bounds.width > window.innerWidth - margin) left = leftSide
  left = Math.max(margin, Math.min(left, window.innerWidth - margin - bounds.width))
  panel.style.top = `${top - anchor.top}px`
  panel.style.left = `${left - anchor.left}px`
  panel.style.right = 'auto'
}
function scheduleSubmenu(event) {
  // 子菜单自己的滚动不改变锚点，也不重置滚动位置。
  if (event?.target?.closest?.('.vm-sub')) return
  cancelAnimationFrame(layoutFrame)
  layoutFrame = requestAnimationFrame(placeSubmenu)
}
watch(hover, async () => {
  await nextTick()
  placeSubmenu()
  scheduleSubmenu()
})
onMounted(() => {
  window.addEventListener('resize', scheduleSubmenu)
  document.addEventListener('scroll', scheduleSubmenu, true)
})
onBeforeUnmount(() => {
  clearTimeout(closeTimer)
  cancelAnimationFrame(layoutFrame)
  window.removeEventListener('resize', scheduleSubmenu)
  document.removeEventListener('scroll', scheduleSubmenu, true)
})
const posStyle = computed(() => ({
  left: `${Math.min(props.x, window.innerWidth - 480)}px`,
  top: `${Math.min(props.y, window.innerHeight - 220)}px`,
}))
function pick(v, label) { emit('pick', v, label) }
</script>

<style scoped>
.vm { position: fixed; z-index: 4000; background: #fff; border-radius: 10px; box-shadow: var(--st-shadow-pop); padding: 6px; min-width: 220px; }
.vm-item { position: relative; display: flex; align-items: center; gap: 8px; padding: 0 14px; border-radius: 6px; cursor: pointer; font-size: var(--st-font-size); color: var(--st-text-2); white-space: nowrap;  height: var(--st-list-item-height); box-sizing: border-box; }
.vm-item:hover { background: var(--st-bg-hover); }
.vm-item .st-icon { color: var(--st-text-2); }
.vm-i { color: var(--st-text-3) !important; }
.vm-caret { margin-left: auto; color: var(--st-text-3) !important; }
.vm-sub { position: absolute; left: calc(100% + 4px); top: -6px; background: #fff; border-radius: 10px; box-shadow: var(--st-shadow-pop); padding: 6px; min-width: min(220px, calc(100vw - 24px)); max-width: calc(100vw - 24px); max-height: min(320px, calc(100vh - 24px)); box-sizing: border-box; overflow: auto; }
.vm-sub-fields { width: 324px; padding: 10px 8px; }
.vm-sub-fields :deep(.fpl) { width: 100%; }
.vm-sub-fields :deep(.fpl-list) { max-height: min(260px, calc(100vh - 80px)) !important; }
.vm-empty { padding: 9px 14px; font-size: var(--st-font-size); color: var(--st-text-4); }
.vm.vm-inline { position: relative; z-index: auto; box-shadow: none; border-radius: 0; min-width: 0; border-top: 1px solid var(--st-border); }
.vm-inline .vm-sub { left: auto; right: calc(100% + 4px); z-index: 1; }
</style>
