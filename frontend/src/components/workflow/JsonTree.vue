<template>
  <!-- 可折叠树形 JSON 查看器：替代裸 <pre>，长 records 列表可逐层收起 -->
  <div class="json-tree" :style="{ paddingLeft: depth ? '14px' : '0' }">
    <template v-if="isObject">
      <div class="jt-row" @click="open = !open">
        <span class="jt-toggle">{{ open ? '▾' : '▸' }}</span>
        <span class="jt-key" v-if="keyLabel">{{ keyLabel }}</span>
        <span class="jt-summary">{{ summary }}</span>
      </div>
      <template v-if="open">
        <JsonTree v-for="entry in entries" :key="entry.k" :data="entry.v" :key-label="entry.k" :depth="depth + 1" />
      </template>
    </template>
    <div v-else class="jt-row leaf">
      <span class="jt-key" v-if="keyLabel">{{ keyLabel }}:</span>
      <span class="jt-val" :class="valClass">{{ display }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  data: {},
  keyLabel: { type: String, default: '' },
  depth: { type: Number, default: 0 },
})

// 顶层默认展开，嵌套层默认收起（长列表不刷屏）；前两层展开更友好
const open = ref(props.depth < 2)

const isObject = computed(() => props.data !== null && typeof props.data === 'object')
const isArray = computed(() => Array.isArray(props.data))

const entries = computed(() => {
  if (isArray.value) return props.data.map((v, i) => ({ k: `[${i}]`, v }))
  return Object.entries(props.data || {}).map(([k, v]) => ({ k, v }))
})

const summary = computed(() =>
  isArray.value ? `数组（${props.data.length} 项）` : `对象（${entries.value.length} 键）`
)

const valClass = computed(() => {
  const v = props.data
  if (v === null || v === undefined) return 'null'
  return { string: 'str', number: 'num', boolean: 'bool' }[typeof v] || 'str'
})

const display = computed(() => {
  const v = props.data
  if (v === null || v === undefined) return 'null'
  if (typeof v === 'string') return v.length > 200 ? `${v.slice(0, 200)}…` : v
  return String(v)
})
</script>

<style scoped>
.json-tree { font-size: 12px; font-family: Consolas, Monaco, monospace; line-height: 1.7; }
.jt-row { cursor: pointer; border-radius: 3px; padding: 0 4px; }
.jt-row:hover { background: #ecf5ff; }
.jt-row.leaf { cursor: default; }
.jt-toggle { color: #909399; margin-right: 2px; user-select: none; }
.jt-key { color: #303133; font-weight: 600; margin-right: 4px; }
.jt-summary { color: #909399; }
.jt-val { word-break: break-all; white-space: pre-wrap; }
.jt-val.str { color: #67c23a; }
.jt-val.num { color: #e6a23c; }
.jt-val.bool { color: #9b59b6; }
.jt-val.null { color: #c0c4cc; }
</style>
