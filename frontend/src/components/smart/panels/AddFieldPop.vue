<template>
  <!-- 添加列：锚定浮层（对齐参照 添加列-所有字段类型.png）：
       字段名输入 → AI 字段通栏入口 → 「选择字段类型」两列图标网格。
       ↑↓←→ 移动，⏎ 选定，Tab 选定并继续添加下一列（emit pick-again），Esc 关闭 -->
  <div class="afp-mask" @click="$emit('close')" @contextmenu.prevent="$emit('close')">
    <div ref="popRef" class="afp" :style="{ left: `${pos.x}px`, top: `${pos.y}px` }" @click.stop @mousedown.stop>
      <input ref="nameRef" v-model="name" class="st-control st-control--native afp-name" placeholder="字段名称"
             @keydown="onKey" @keydown.esc.stop="$emit('close')" />
      <div class="afp-ai" @click="ai">
        <StIcon name="sparkle" :size="15" class="afp-ai-icon" />AI 字段
        <StIcon name="chevron-right" :size="13" class="afp-ai-caret" />
      </div>
      <div v-for="group in typeGroups" :key="group.key" class="afp-grid" :aria-label="group.label">
        <div class="afp-group-title">{{ group.label }}</div>
        <div v-for="t in group.types" :key="t.key" class="afp-type" :class="{ on: t.index === idx }"
             @mouseenter="idx = t.index" @click="pick(t, false)">
          <StIcon :name="t.key" :size="15" />{{ t.label }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import StIcon from '../icons/StIcon.vue'
import { FIELD_REGISTRY } from '../../../smart/registry/fieldRegistry.js'
import { useFloatingPanel } from '../../../smart/utils/floatingPanel.js'

const props = defineProps({
  x: { type: Number, default: 200 },
  y: { type: Number, default: 100 },
})
const emit = defineEmits(['pick', 'pick-again', 'close', 'ai'])

// 按用途分类，只展示已支持的字段类型。
const GROUPS = [
  { key: 'basic', label: '基础数据', types: ['text', 'number', 'percent', 'currency', 'date'] },
  { key: 'status', label: '选项与状态', types: ['singleSelect', 'multiSelect', 'checkbox', 'progress'] },
  { key: 'resources', label: '人员与资源', types: ['member', 'image', 'file', 'url'] },
  { key: 'calculation', label: '关联与计算', types: ['relation', 'lookup', 'formula'] },
  { key: 'system', label: '自动记录', types: ['autoNumber', 'createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime'] },
]
const typeGroups = computed(() => {
  let index = 0
  return GROUPS.map(group => ({ ...group, types: group.types.filter(k => FIELD_REGISTRY[k]).map(k => ({ key: k, label: FIELD_REGISTRY[k].label, index: index++ })) }))
})
const typeList = computed(() => typeGroups.value.flatMap(group => group.types))
const typeRows = computed(() => typeGroups.value.flatMap(group => {
  const rows = []
  for (let i = 0; i < group.types.length; i += 2) rows.push(group.types.slice(i, i + 2))
  return rows
}))

const name = ref('')
const idx = ref(0)
const nameRef = ref(null)
const popRef = ref(null)
useFloatingPanel(() => popRef.value, () => popRef.value?.closest('.afp-mask'))

// 位置钳制在视口内
// 按浮层实际尺寸限制在视口内（固定估值会让右侧/底部最后一行被裁掉）
const size = ref({ w: 320, h: 480 })
const pos = computed(() => ({
  x: Math.max(8, Math.min(props.x, window.innerWidth - size.value.w - 8)),
  y: Math.max(8, Math.min(props.y, window.innerHeight - size.value.h - 8)),
}))

onMounted(async () => {
  await nextTick()
  if (popRef.value) size.value = { w: popRef.value.offsetWidth, h: popRef.value.offsetHeight }
  nameRef.value?.focus()
})

function onKey(e) {
  const n = typeList.value.length
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    const rows = typeRows.value
    const rowIndex = rows.findIndex(row => row.some(t => t.index === idx.value))
    const column = rows[rowIndex].findIndex(t => t.index === idx.value)
    const target = rows[rowIndex + (e.key === 'ArrowDown' ? 1 : -1)]
    if (target) idx.value = target[Math.min(column, target.length - 1)].index
  }
  else if (e.key === 'ArrowRight') { e.preventDefault(); idx.value = Math.min(n - 1, idx.value + 1) }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); idx.value = Math.max(0, idx.value - 1) }
  else if (e.key === 'Enter') { e.preventDefault(); pick(typeList.value[idx.value], false) }
  else if (e.key === 'Tab') { e.preventDefault(); pick(typeList.value[idx.value], true) }
  if (e.key.startsWith('Arrow')) nextTick(() => popRef.value?.querySelector('.afp-type.on')?.scrollIntoView({ block: 'nearest' }))
}
function pick(t, again) {
  if (!t) return
  emit(again ? 'pick-again' : 'pick', { field_type: t.key, label: name.value.trim() })
}
// AI 字段：打开场景市场（V3），带上已输入的字段名
function ai() { emit('ai', { label: name.value.trim(), x: pos.value.x, y: pos.value.y }) }
</script>

<style scoped>
.afp-mask { position: fixed; inset: 0; z-index: 3000; }
.afp {
  position: fixed; width: 320px; max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); box-sizing: border-box; overflow: auto; scrollbar-width: none; background: #fff; border-radius: 8px;
  box-shadow: var(--st-shadow-pop); padding: 12px; display: flex; flex-direction: column;
}
.afp-name {
  outline: none; font-size: var(--st-font-size); padding: 0 10px; width: 100%; height: 32px; line-height: normal;
  border: 1px solid var(--st-border); border-radius: 4px; box-sizing: border-box;
}
.afp-name::placeholder { color: var(--st-text-4); }
.afp-ai {
  display: flex; align-items: center; gap: 8px; padding: 6px 2px; margin-top: 4px;
  font-size: var(--st-font-size); cursor: pointer; border-radius: 6px; color: var(--st-text-2);
}
.afp-ai:hover { background: var(--st-bg-hover); }
.afp-ai-icon { color: var(--st-ai); }
.afp-ai-caret { margin-left: auto; color: var(--st-text-3); }
.afp > :not(.afp-grid) { flex-shrink: 0; }
.afp::-webkit-scrollbar { display: none; }
.afp-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0; flex-shrink: 0; }
.afp-grid + .afp-grid { margin-top: 6px; }
.afp-group-title { grid-column: 1 / -1; display: flex; align-items: center; gap: 8px; padding: 2px; font-size: 12px; line-height: 18px; color: var(--st-text-3); }
.afp-group-title::after { content: ''; flex: 1; height: 1px; background: var(--st-border); }
.afp-type {
  display: flex; align-items: center; gap: 8px; height: 28px; box-sizing: border-box; padding: 0 8px; font-size: var(--st-font-size); line-height: 20px;
  cursor: pointer; border-radius: 6px; color: var(--st-text-2);
}
.afp-type .st-icon { color: var(--st-text-2); }
.afp-type.on { background: var(--st-bg-hover); }
</style>
