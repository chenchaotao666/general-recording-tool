<template>
  <Teleport to="body">
    <SmartMenu ref="menuEl" class="cell-context-menu" role="menu" aria-label="单元格操作" :style="{ ...position, zIndex }" @contextmenu.prevent @pointerdown.stop @scroll.capture="placeActiveSubmenu" @keydown.esc.stop="emit('close')">
      <template v-for="(group, index) in groups" :key="index">
        <div v-if="index" class="cell-menu-divider fm-divider" role="separator" />
        <div v-for="item in group" :key="item.code" class="cell-menu-entry" @mouseenter="active = item.children ? item.code : null">
          <div v-if="item.insert" class="cell-menu-insert" :class="{ 'is-disabled': item.disabled }">
            <button class="cell-menu-item mi" role="menuitem" :disabled="item.disabled" @click="choose(item.code)">
              <StIcon :name="item.icon" :size="15" /><span>{{ item.label }}</span>
            </button>
            <input v-model.number="counts[item.code]" :aria-label="`${item.label}行数`" type="number" min="1" max="100" step="1"
                   :disabled="item.disabled" @keydown.enter.stop.prevent="choose(item.code)" @click.stop />
            <span class="cell-menu-unit">行</span>
          </div>
          <button v-else class="cell-menu-item mi" role="menuitem" :disabled="item.disabled" :data-smart-tip="item.hint" :aria-haspopup="item.children ? 'menu' : undefined" :aria-expanded="item.children ? active === item.code : undefined"
                  @click="item.children ? active = active === item.code ? null : item.code : choose(item.code)" @keydown.right.prevent="active = item.code">
            <StIcon :name="item.icon" :size="15" />
            <span class="cell-menu-label">{{ item.label }}</span>
            <StIcon v-if="item.children" name="chevron-right" :size="14" class="cell-menu-chevron" />
          </button>
          <div v-if="item.children && active === item.code && !item.disabled" class="cell-menu-sub fm-sub" role="menu">
            <button v-for="child in item.children" :key="child.code" class="cell-menu-item mi" role="menuitem" @click="choose(child.code)"><StIcon :name="child.icon" :size="15" />{{ child.label }}</button>
          </div>
        </div>
      </template>
    </SmartMenu>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, useZIndex } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import SmartMenu from '../common/SmartMenu.vue'
import { placeSubmenu } from '../../../smart/utils/menuBounds'
const props = defineProps({ x: Number, y: Number, hasField: Boolean, canCreate: Boolean, canDelete: Boolean, readonly: Boolean, rowOnly: Boolean, rangeRowCount: { type: Number, default: 0 } })
const emit = defineEmits(['action', 'close', 'layer'])
const menuEl = ref(null)
const { nextZIndex } = useZIndex(4000)
const zIndex = ref(4000)
const active = ref(null)
const counts = ref({ 'insert-up': 1, 'insert-down': 1 })
const position = ref({ left: '0px', top: '0px', visibility: 'hidden' })
const groups = computed(() => props.rangeRowCount > 0 && !props.rowOnly
  ? [[{ code: 'delete-rows', label: `删除 ${props.rangeRowCount} 行`, icon: 'trash', disabled: !props.canDelete }]] : [
  [{ code: 'expand', label: '展开记录', icon: 'expand' }],
  [{ code: 'only', label: '只看此内容', icon: 'filter', disabled: !props.hasField }, { code: 'exclude', label: '不看此内容', icon: 'filter', disabled: !props.hasField }],
  [{ code: 'viz', label: '数据可视化', icon: 'magic', disabled: !props.hasField || props.readonly, children: [
    { code: 'viz-bar', label: '柱状图', icon: 'chart-bar' }, { code: 'viz-pie', label: '饼图', icon: 'pie' }, { code: 'viz-more', label: '更多图表', icon: 'chart-more' },
  ] }, { code: 'reminders', label: '设置提醒', icon: 'play-circle', disabled: !props.hasField || props.readonly, children: [
    { code: 'reminder', label: '内容变更提醒', icon: 'bell' }, { code: 'automation', label: '更多自动化设置', icon: 'automation' },
  ] }],
  [{ code: 'duplicate', label: '创建副本', icon: 'copy', disabled: !props.canCreate },
    { code: 'insert-up', label: '向上插入', icon: 'arrow-up', insert: true, disabled: !props.canCreate },
    { code: 'insert-down', label: '向下插入', icon: 'arrow-down', insert: true, disabled: !props.canCreate }],
  [{ code: 'delete', label: '删除', icon: 'trash', disabled: !props.canDelete }],
].filter((_, index) => !props.rowOnly || ![1, 2].includes(index)))
function choose(code) {
  if (code === 'delete-rows' && !props.canDelete) return
  const count = counts.value[code]
  if (code.startsWith('insert-')) {
    if (!props.canCreate) return
    if (!Number.isInteger(count) || count < 1 || count > 100) {
      ElMessage.warning('请输入 1–100 的整数行数')
      return
    }
  }
  emit('action', code, count)
  emit('close')
}
async function place() {
  await nextTick()
  const rect = menuEl.value?.$el?.getBoundingClientRect()
  if (!rect) return
  const left = Math.max(8, Math.min(props.x, window.innerWidth - rect.width - 8))
  position.value = { left: `${left}px`, top: `${Math.max(8, Math.min(props.y, window.innerHeight - rect.height - 8))}px` }
  await nextTick()
  placeActiveSubmenu()
}
function placeActiveSubmenu() {
  const sub = menuEl.value?.$el?.querySelector('.cell-menu-sub')
  if (sub) placeSubmenu(sub, sub.parentElement)
}
watch(() => [props.x, props.y], () => { active.value = null; place() })
watch(active, async () => { await nextTick(); placeActiveSubmenu() })
function outside(event) { if (!menuEl.value?.$el?.contains(event.target)) emit('close') }
function escape(event) { if (event.key === 'Escape') emit('close') }
function closeOnWheel(event) { if (event.target instanceof Element && event.target.closest('.smart-grid')) emit('close') }
onMounted(() => { zIndex.value = nextZIndex(); emit('layer', zIndex.value); place(); document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape); window.addEventListener('resize', place); document.addEventListener('wheel', closeOnWheel, true) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); window.removeEventListener('resize', place); document.removeEventListener('wheel', closeOnWheel, true) })
</script>

<style scoped>
.cell-context-menu { z-index: 3500; width: 220px; }
.cell-menu-entry { position: relative; }
.cell-menu-item { width: 100%; }
.cell-menu-label { flex: 1; }
.cell-menu-chevron,.cell-menu-unit { color: var(--st-text-3); }
.cell-menu-insert { display: flex; align-items: center; gap: 8px; height: var(--st-list-item-height); padding-right: 12px; border-radius: 4px; }
.cell-menu-insert:hover:not(.is-disabled),.cell-menu-insert:focus-within:not(.is-disabled) { background: var(--st-bg-hover); }
.cell-menu-insert .cell-menu-item { flex: 1; width: auto; min-width: 0; padding-right: 0; }
.cell-menu-insert .cell-menu-item:hover:not(:disabled) { background: transparent; }
.cell-menu-insert input { flex: 0 0 36px; width: 36px; height: 20px; box-sizing: border-box; padding: 0 3px; text-align: center; border: 1px solid var(--st-border); border-radius: 4px; background: #fff; color: inherit; font: inherit; appearance: textfield; }
.cell-menu-insert input:disabled { color: var(--st-disabled); cursor: not-allowed; }
.cell-menu-insert input:focus { outline: 1px solid var(--st-primary); }
.cell-menu-insert input::-webkit-inner-spin-button { appearance: none; }
.cell-menu-sub { position: fixed; width: 192px; }
</style>
