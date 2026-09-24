<template>
  <div class="flow-node" :class="[`cat-${data.category}`, { selected }]">
    <Handle type="target" :position="Position.Left" />
    <div class="node-head">
      <span class="dot" />
      <span class="type-name">{{ data.typeName }}</span>
    </div>
    <div class="node-label">{{ data.name || data.typeName }}</div>
    <template v-if="data.nodeType === 'condition'">
      <Handle id="true" type="source" :position="Position.Right" class="h-true" />
      <Handle id="false" type="source" :position="Position.Right" class="h-false" />
      <span class="branch-tag t">是</span>
      <span class="branch-tag f">否</span>
    </template>
    <Handle v-else type="source" :position="Position.Right" />
  </div>
</template>

<script setup>
import { Handle, Position } from '@vue-flow/core'

defineProps({
  data: { type: Object, required: true },   // {nodeType, typeName, category, name}
  selected: { type: Boolean, default: false },
})
</script>

<style scoped>
.flow-node {
  width: 160px; padding: 8px 10px; border-radius: 8px; background: #fff;
  border: 1.5px solid #dcdfe6; font-size: 12px; position: relative;
  box-shadow: 0 1px 4px rgba(0, 0, 0, .06);
}
.flow-node.selected { border-color: #409eff; box-shadow: 0 0 0 2px rgba(64, 158, 255, .2); }
.node-head { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #909399; }
.cat-data .dot { background: #409eff; }
.cat-ai .dot { background: #9b59b6; }
.cat-logic .dot { background: #e6a23c; }
.cat-action .dot { background: #67c23a; }
.cat-human .dot { background: #f56c6c; }
.type-name { color: #909399; font-size: 11px; }
.node-label { font-weight: 600; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.h-true { top: 55% !important; }
.h-false { top: 80% !important; }
.branch-tag { position: absolute; right: -18px; font-size: 10px; line-height: 1; }
.branch-tag.t { top: calc(55% - 5px); color: #67c23a; }
.branch-tag.f { top: calc(80% - 5px); color: #f56c6c; }
</style>
