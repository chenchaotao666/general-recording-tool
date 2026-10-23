<template>
  <!-- AI 生成按钮（参照 选中AI列是AI按钮.png / PixPin_2026-10-17_14-36-19.png）：
       选中 AI 列或 AI 单元格时，浮在其右侧的「✦ | ▾」分体按钮。
       ✦ = 重新生成（列：整列；单元格：该行），▾ = 生成全部 / 仅生成空白行 / 重新生成失败行 -->
  <teleport to="body">
    <div ref="panelRef" class="arb" @mousedown.stop>
      <el-tooltip :hide-after="0" :content="mode === 'cell' ? '重新生成此行' : '重新生成'" placement="top" :show-after="200">
        <span class="arb-main st-icon-action" @click="emit('run', mode === 'cell' ? 'row' : 'all')"><span class="arb-logo"><StIcon name="sparkle" :size="11" /></span></span>
      </el-tooltip>
      <span class="arb-dd st-icon-action" :class="{ open: menu }" @click="menu = !menu"><span class="arb-tri" /></span>
      <div v-if="menu" ref="menuRef" class="arb-menu">
        <div class="arb-mi" @click="pick('all')">生成全部</div>
        <div class="arb-mi" @click="pick('empty')">仅生成空白行</div>
        <div class="arb-mi" @click="pick('failed')">重新生成失败行</div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useFloatingPanel } from '../../../smart/utils/floatingPanel.js'
import StIcon from '../icons/StIcon.vue'

const props = defineProps({
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  mode: { type: String, default: 'col' },   // col | cell
})
const emit = defineEmits(['run'])
const menu = ref(false)
const panelRef = ref(null)
const menuRef = ref(null)
useFloatingPanel(() => panelRef.value)
const refreshMenu = useFloatingPanel(() => menuRef.value)
const clamp = (value, size, extent) => Math.max(12, Math.min(value, extent - size - 12))
function place() {
  const panel = panelRef.value
  if (!panel) return
  const width = window.innerWidth, height = window.innerHeight
  const rect = panel.getBoundingClientRect()
  const left = clamp(props.x + rect.width > width - 12 ? props.x - rect.width : props.x, rect.width, width)
  const top = clamp(props.y + rect.height > height - 12 ? props.y - rect.height : props.y, rect.height, height)
  Object.assign(panel.style, { left: `${left}px`, top: `${top}px` })
  const dropdown = menuRef.value
  if (!dropdown) return
  // 使用 fixed 坐标，菜单宽于按钮时向左对齐，底部空间不足时翻到上方。
  dropdown.style.maxWidth = `${Math.max(0, width - 24)}px`
  dropdown.style.maxHeight = `${Math.max(0, height - 24)}px`
  const box = dropdown.getBoundingClientRect()
  const x = left + box.width > width - 12 ? left + rect.width - box.width : left
  const below = top + rect.height + 6
  const y = below + box.height > height - 12 ? top - box.height - 6 : below
  Object.assign(dropdown.style, { left: `${clamp(x, box.width, width)}px`, top: `${clamp(y, box.height, height)}px` })
}
watch(() => [props.x, props.y], () => nextTick(place), { flush: 'post' })
watch(menu, async (open) => { await nextTick(); if (open) await refreshMenu(); place() })
onMounted(() => {
  nextTick(place)
  window.addEventListener('resize', place)
  window.visualViewport?.addEventListener('resize', place)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', place)
  window.visualViewport?.removeEventListener('resize', place)
})
function pick(scope) { menu.value = false; emit('run', scope) }
</script>

<style scoped>
.arb { position: fixed; display: inline-flex; align-items: stretch; height: 32px; background: #fff; border: 1px solid #E3E5E8;
       border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, .08); }
.arb-main, .arb-dd { display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
.arb-main { width: 34px; border-radius: 7px 0 0 7px; }
.arb-dd { width: 20px; border-left: 1px solid #E3E5E8; border-radius: 0 7px 7px 0; }
.arb-main:hover, .arb-dd:hover, .arb-dd.open { background: #F2F3F5; }
.arb-logo { width: 20px; height: 20px; border-radius: 5px; background: linear-gradient(135deg, #8B6CF6, #E96BD8); color: #fff;
            display: inline-flex; align-items: center; justify-content: center; }
.arb-tri { width: 0; height: 0; border-left: 3.5px solid transparent; border-right: 3.5px solid transparent; border-top: 5px solid #1F2329; }
.arb-menu { position: fixed; background: #fff; border-radius: 8px; box-shadow: 0 6px 24px rgba(0, 0, 0, .14);
            padding: 6px; width: 162px; box-sizing: border-box; max-width: calc(100vw - 24px); max-height: calc(100vh - 24px); overflow: auto; }
.arb-mi {  display: flex; align-items: center; padding: 0 12px; border-radius: 6px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; white-space: nowrap;  height: var(--st-list-item-height); box-sizing: border-box; }
.arb-mi:hover { background: #F2F3F5; }
</style>
