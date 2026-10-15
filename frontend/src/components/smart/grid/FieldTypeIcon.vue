<template>
  <!-- 字段类型图标（设计稿 PixPin_2026-10-15_22-57-20）：文本/数字/公式等为圆角徽章字形，
       其余为 element-plus 线性图标，单色 -->
  <span class="ft-icon">
    <span v-if="conf.badge" class="ft-badge" :class="{ italic: conf.italic }">{{ conf.badge }}</span>
    <svg v-else-if="conf.svg === 'checkbox'" viewBox="0 0 16 16" width="15" height="15" fill="none"
         stroke="currentColor" stroke-width="1.4">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2.5" />
      <path d="M4.5 8.2l2.4 2.4 4.6-5" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
    <svg v-else-if="conf.svg === 'progress'" viewBox="0 0 16 16" width="15" height="15" fill="none"
         stroke="currentColor" stroke-width="1.4">
      <rect x="1" y="4.5" width="14" height="7" rx="3.5" />
      <rect x="3" y="6.5" width="6" height="3" rx="1.5" fill="currentColor" stroke="none" />
    </svg>
    <el-icon v-else :size="15"><component :is="conf.icon" /></el-icon>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import {
  Calendar, CircleCheck, Clock, Connection, Finished, Folder, Link,
  Message, Phone, Picture, Tickets, User,
} from '@element-plus/icons-vue'

const MAP = {
  text: { badge: 'A' },
  number: { badge: '123' },
  percent: { badge: '%' },
  currency: { badge: '¥' },
  formula: { badge: 'fx', italic: true },
  autoNumber: { badge: '1↓' },
  singleSelect: { icon: CircleCheck },
  multiSelect: { icon: Finished },
  date: { icon: Calendar },
  createdTime: { icon: Calendar },
  lastModifiedTime: { icon: Clock },
  member: { icon: User },
  createdBy: { icon: User },
  lastModifiedBy: { icon: User },
  image: { icon: Picture },
  file: { icon: Folder },
  url: { icon: Link },
  relation: { icon: Connection },
  phone: { icon: Phone },
  email: { icon: Message },
  lookup: { icon: Tickets },
  checkbox: { svg: 'checkbox' },
  progress: { svg: 'progress' },
}

const props = defineProps({ field: { type: Object, required: true } })
const conf = computed(() => MAP[props.field?.field_type] || MAP.text)
</script>

<style scoped>
.ft-icon { display: inline-flex; align-items: center; justify-content: center; width: 18px; color: var(--el-text-color-regular); }
.ft-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 16px; height: 16px; padding: 0 2px; box-sizing: border-box;
  border: 1px solid currentColor; border-radius: 3px;
  font-size: 10px; line-height: 1; transform: scale(.92);
}
.ft-badge.italic { font-style: italic; font-weight: 600; }
</style>
