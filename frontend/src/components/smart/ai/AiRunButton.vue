<template>
  <!-- AI 生成按钮（参照 选中AI列是AI按钮.png / PixPin_2026-10-17_14-36-19.png）：
       选中 AI 列或 AI 单元格时，浮在其右侧的「✦ | ▾」分体按钮。
       ✦ = 重新生成（列：整列；单元格：该行），▾ = 生成全部 / 仅生成空白行 / 重新生成失败行 -->
  <teleport to="body">
    <div class="arb" :style="{ left: `${x}px`, top: `${y}px` }" @mousedown.stop>
      <el-tooltip :hide-after="0" :content="mode === 'cell' ? '重新生成此行' : '重新生成'" placement="top" :show-after="200">
        <span class="arb-main st-icon-action" @click="emit('run', mode === 'cell' ? 'row' : 'all')"><span class="arb-logo"><StIcon name="sparkle" :size="11" /></span></span>
      </el-tooltip>
      <span class="arb-dd st-icon-action" :class="{ open: menu }" @click="menu = !menu"><span class="arb-tri" /></span>
      <div v-if="menu" class="arb-menu">
        <div class="arb-mi" @click="pick('all')">生成全部</div>
        <div class="arb-mi" @click="pick('empty')">仅生成空白行</div>
        <div class="arb-mi" @click="pick('failed')">重新生成失败行</div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref } from 'vue'
import StIcon from '../icons/StIcon.vue'

defineProps({
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  mode: { type: String, default: 'col' },   // col | cell
})
const emit = defineEmits(['run'])
const menu = ref(false)
function pick(scope) { menu.value = false; emit('run', scope) }
</script>

<style scoped>
.arb { position: fixed; z-index: 2100; display: inline-flex; align-items: stretch; height: 32px; background: #fff; border: 1px solid #E3E5E8;
       border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, .08); }
.arb-main, .arb-dd { display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
.arb-main { width: 34px; border-radius: 7px 0 0 7px; }
.arb-dd { width: 20px; border-left: 1px solid #E3E5E8; border-radius: 0 7px 7px 0; }
.arb-main:hover, .arb-dd:hover, .arb-dd.open { background: #F2F3F5; }
.arb-logo { width: 20px; height: 20px; border-radius: 5px; background: linear-gradient(135deg, #8B6CF6, #E96BD8); color: #fff;
            display: inline-flex; align-items: center; justify-content: center; }
.arb-tri { width: 0; height: 0; border-left: 3.5px solid transparent; border-right: 3.5px solid transparent; border-top: 5px solid #1F2329; }
.arb-menu { position: absolute; left: 0; top: calc(100% + 6px); background: #fff; border-radius: 8px; box-shadow: 0 6px 24px rgba(0, 0, 0, .14);
            padding: 6px; width: 150px; }
.arb-mi { height: 36px; display: flex; align-items: center; padding: 0 12px; border-radius: 6px; font-size: 14px; color: #1F2329; cursor: pointer; white-space: nowrap; }
.arb-mi:hover { background: #F2F3F5; }
</style>
