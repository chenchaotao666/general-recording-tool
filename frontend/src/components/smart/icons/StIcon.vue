<template>
  <!-- 智慧表格统一图标：name 支持字段类型（date/member/…）与功能图标（filter/pin/…），
       1.5px 线性、stroke=currentColor（颜色由外层 CSS 控制）。差距文档 §1：消灭 emoji/Unicode/EP 三套并存 -->
  <svg viewBox="0 0 16 16" :width="size" :height="size" fill="none" stroke="currentColor"
       :stroke-width="strokeWidth" stroke-linecap="round" stroke-linejoin="round"
       class="st-icon" aria-hidden="true" v-html="inner" />
</template>

<script setup>
import { computed } from 'vue'
import { FIELD_TYPE_ICONS } from '../../../smart/registry/fieldIcons.js'
import { UI_ICONS } from '../../../smart/registry/uiIcons.js'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 14 },
  strokeWidth: { type: [Number, String], default: 1.5 },
})

const inner = computed(() => UI_ICONS[props.name] || FIELD_TYPE_ICONS[props.name] || FIELD_TYPE_ICONS.text)
</script>

<style scoped>
.st-icon { display: inline-block; vertical-align: middle; flex: none; }
</style>
