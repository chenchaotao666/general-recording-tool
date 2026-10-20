<template>
  <Teleport to="body">
    <div ref="menuEl" class="cell-context-menu" role="menu" aria-label="单元格操作" :style="position" @contextmenu.prevent @pointerdown.stop @keydown.esc.stop="emit('close')">
      <template v-for="(group, index) in groups" :key="index">
        <div v-if="index" class="cell-menu-divider" role="separator" />
        <div v-for="item in group" :key="item.code" class="cell-menu-entry" @mouseenter="active = item.children ? item.code : null">
          <div v-if="item.insert" class="cell-menu-insert" :class="{ 'is-disabled': item.disabled }">
            <button class="cell-menu-item" role="menuitem" :disabled="item.disabled" @click="choose(item.code)">
              <StIcon :name="item.icon" :size="18" :stroke-width="1.3" /><span>{{ item.label }}</span>
            </button>
            <input v-model.number="counts[item.code]" :aria-label="`${item.label}行数`" type="number" min="1" max="100" step="1"
                   :disabled="item.disabled" @keydown.enter.stop.prevent="choose(item.code)" @click.stop />
            <span class="cell-menu-unit">行</span>
          </div>
          <button v-else class="cell-menu-item" role="menuitem" :disabled="item.disabled" :data-smart-tip="item.hint" :aria-haspopup="item.children ? 'menu' : undefined" :aria-expanded="item.children ? active === item.code : undefined"
                  @click="item.children ? active = active === item.code ? null : item.code : choose(item.code)" @keydown.right.prevent="active = item.code">
            <StIcon :name="item.icon" :size="18" :stroke-width="1.3" />
            <span class="cell-menu-label">{{ item.label }}</span>
            <StIcon v-if="item.children" name="chevron-right" :size="14" class="cell-menu-chevron" />
          </button>
          <div v-if="item.children && active === item.code && !item.disabled" class="cell-menu-sub" :class="{ 'opens-left': opensLeft }" role="menu" :style="{ top: `${submenuTop}px` }">
            <button v-for="child in item.children" :key="child.code" class="cell-menu-item" role="menuitem" @click="choose(child.code)"><StIcon :name="child.icon" :size="18" />{{ child.label }}</button>
          </div>
        </div>
      </template>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
const props = defineProps({ x: Number, y: Number, hasField: Boolean, canCreate: Boolean, canDelete: Boolean, readonly: Boolean })
const emit = defineEmits(['action', 'close'])
const menuEl = ref(null)
const active = ref(null)
const counts = ref({ 'insert-up': 1, 'insert-down': 1 })
const position = ref({ left: '0px', top: '0px', visibility: 'hidden' })
const opensLeft = ref(false)
const submenuTop = ref(0)
const groups = computed(() => [
  [{ code: 'expand', label: '展开记录', icon: 'expand' }],
  [{ code: 'only', label: '只看此内容', icon: 'filter', disabled: !props.hasField }, { code: 'exclude', label: '不看此内容', icon: 'filter', disabled: !props.hasField }],
  [{ code: 'viz', label: '数据可视化', icon: 'magic', disabled: !props.hasField || props.readonly, children: [
    { code: 'viz-bar', label: '柱状图', icon: 'chart-bar' }, { code: 'viz-pie', label: '饼图', icon: 'pie' }, { code: 'viz-more', label: '更多图表', icon: 'chart-more' },
  ] }, { code: 'reminders', label: '设置提醒', icon: 'play-circle', disabled: !props.hasField || props.readonly, children: [
    { code: 'reminder', label: '内容变更提醒', icon: 'bell' }, { code: 'automation', label: '更多自动化设置', icon: 'automation' },
  ] }],
  [{ code: 'add-child', label: '添加子记录', icon: 'child-record', disabled: !props.canCreate }],
  [{ code: 'duplicate', label: '创建副本', icon: 'copy', disabled: !props.canCreate },
    { code: 'insert-up', label: '向上插入', icon: 'arrow-up', insert: true, disabled: !props.canCreate },
    { code: 'insert-down', label: '向下插入', icon: 'arrow-down', insert: true, disabled: !props.canCreate }],
  [{ code: 'delete', label: '删除', icon: 'trash', disabled: !props.canDelete }],
])
function choose(code) {
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
  const rect = menuEl.value?.getBoundingClientRect()
  if (!rect) return
  const left = Math.max(8, Math.min(props.x, window.innerWidth - rect.width - 8))
  position.value = { left: `${left}px`, top: `${Math.max(8, Math.min(props.y, window.innerHeight - rect.height - 8))}px` }
  opensLeft.value = left + rect.width + 192 > window.innerWidth - 8
}
watch(() => [props.x, props.y], () => { active.value = null; place() })
watch(active, async () => {
  submenuTop.value = 0
  await nextTick()
  const sub = menuEl.value?.querySelector('.cell-menu-sub')
  if (sub) submenuTop.value = Math.min(0, window.innerHeight - 8 - sub.getBoundingClientRect().bottom)
})
function outside(event) { if (!menuEl.value?.contains(event.target)) emit('close') }
function escape(event) { if (event.key === 'Escape') emit('close') }
function closeOnWheel(event) { if (event.target instanceof Element && event.target.closest('.smart-grid')) emit('close') }
onMounted(() => { place(); document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape); window.addEventListener('resize', outside); document.addEventListener('wheel', closeOnWheel, true) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); window.removeEventListener('resize', outside); document.removeEventListener('wheel', closeOnWheel, true) })
</script>

<style scoped>
.cell-context-menu,.cell-menu-sub { position: fixed; z-index: 3500; box-sizing: border-box; width: 240px; padding: 6px 0; border: 1px solid #dedfe2; border-radius: 10px; background: #fff; box-shadow: 0 4px 20px #0002; color: #252a34; font-size: 14px; }
.cell-context-menu { width: 200px; max-height: calc(100vh - 16px); }
.cell-menu-entry { position: relative; }
.cell-menu-item { display: flex; align-items: center; gap: 8px; width: 100%; height: 32px; padding: 0 14px; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; white-space: nowrap; }
.cell-menu-item:hover:not(:disabled),.cell-menu-item:focus-visible { background: #f2f3f5; outline: none; }
.cell-menu-item:disabled { color: #a6aab2; cursor: not-allowed; }
.cell-menu-item svg { flex-shrink: 0; }
.cell-menu-label { flex: 1; }
.cell-menu-divider { height: 1px; background: #ececef; margin: 4px 0; }
.cell-menu-chevron,.cell-menu-unit { color: #9298a2; }
.cell-menu-insert { display: flex; align-items: center; gap: 8px; height: 32px; margin: 0 4px; padding-right: 10px; border-radius: 3px; }
.cell-menu-insert:hover:not(.is-disabled),.cell-menu-insert:focus-within:not(.is-disabled) { background: #f2f3f5; }
.cell-menu-insert .cell-menu-item { flex: 1; width: auto; min-width: 0; padding: 0 0 0 10px; }
.cell-menu-insert .cell-menu-item:hover:not(:disabled) { background: transparent; }
.cell-menu-insert input { flex: 0 0 36px; width: 36px; height: 20px; box-sizing: border-box; padding: 0 3px; text-align: center; border: 1px solid #d1d3d8; border-radius: 2px; background: #fff; color: inherit; font: inherit; appearance: textfield; }
.cell-menu-insert input:focus { outline: 1px solid #397bff; }
.cell-menu-insert input::-webkit-inner-spin-button { appearance: none; }
.cell-menu-sub { position: absolute; left: calc(100% - 2px); width: 192px; }
.cell-menu-sub.opens-left { left: auto; right: calc(100% - 2px); }
</style>
