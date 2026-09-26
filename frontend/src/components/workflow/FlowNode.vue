<template>
  <div class="flow-node" :class="[`cat-${data.category}`, { selected, disabled: data.disabled }]">
    <!-- 悬停工具栏：试运行到此 / 停用 / 复制 / 删除（触发器节点没有） -->
    <div v-if="data.nodeType !== 'trigger'" class="node-tools" @click.stop>
      <div class="tools-box">
        <el-icon title="试运行到此节点" @click="data.onAction?.('run-to', id)"><VideoPlay /></el-icon>
        <el-icon :title="data.disabled ? '启用节点' : '停用节点'" :class="{ off: data.disabled }"
          @click="data.onAction?.('toggle-disabled', id)"><SwitchButton /></el-icon>
        <el-icon title="复制节点" @click="data.onAction?.('duplicate', id)"><CopyDocument /></el-icon>
        <el-icon title="删除节点" class="danger" @click="data.onAction?.('delete', id)"><Delete /></el-icon>
      </div>
    </div>
    <Handle v-if="data.nodeType !== 'trigger'" type="target" :position="Position.Left" />
    <div class="node-head">
      <span class="dot" />
      <span class="type-name">{{ data.typeName }}</span>
      <span v-if="data.disabled" class="off-tag">已停用</span>
    </div>
    <div class="node-label">{{ data.name || data.typeName }}</div>
    <template v-if="data.nodeType === 'condition'">
      <Handle id="true" type="source" :position="Position.Right" class="h-true" />
      <Handle id="false" type="source" :position="Position.Right" class="h-false" />
      <span class="branch-tag t">是</span>
      <span class="branch-tag f">否</span>
    </template>
    <!-- 逐条处理：「每条」出口接循环体（循环体末尾连回本节点），「完成」出口接后续 -->
    <template v-else-if="data.nodeType === 'foreach'">
      <Handle id="loop" type="source" :position="Position.Right" class="h-true" />
      <Handle id="done" type="source" :position="Position.Right" class="h-false" />
      <span class="branch-tag t">每条</span>
      <span class="branch-tag f">完成</span>
    </template>
    <!-- 多路分支：每个分支一个出口 + 默认出口，分支名直接作为 handle id / 边的 branch -->
    <template v-else-if="data.nodeType === 'switch'">
      <Handle v-for="(b, i) in switchBranches" :key="b.id" :id="b.id" type="source" :position="Position.Right"
        :style="{ top: `${40 + i * (50 / Math.max(switchBranches.length - 1, 1))}%` }" />
      <span v-for="(b, i) in switchBranches" :key="`t-${b.id}`" class="branch-tag sw"
        :style="{ top: `calc(${40 + i * (50 / Math.max(switchBranches.length - 1, 1))}% - 5px)` }">{{ b.name }}</span>
    </template>
    <Handle v-else type="source" :position="Position.Right" />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { CopyDocument, Delete, SwitchButton, VideoPlay } from '@element-plus/icons-vue'

const props = defineProps({
  id: { type: String, required: true },
  data: { type: Object, required: true },   // {nodeType, typeName, category, name, disabled?, onAction?}
  selected: { type: Boolean, default: false },
})

// 多路分支的出口：每个分支名 + 兜底 default
const switchBranches = computed(() => {
  const cases = props.data.config?.cases || []
  return [
    ...cases.filter((c) => c.label?.trim()).map((c) => ({ id: c.label.trim(), name: c.label.trim() })),
    { id: 'default', name: '默认' },
  ]
})
</script>

<style scoped>
.flow-node {
  width: 160px; padding: 8px 10px; border-radius: 8px; background: #fff;
  border: 1.5px solid #dcdfe6; font-size: 12px; position: relative;
  box-shadow: 0 1px 4px rgba(0, 0, 0, .06);
}
.flow-node.selected { border-color: #409eff; box-shadow: 0 0 0 2px rgba(64, 158, 255, .2); }
.flow-node.disabled { opacity: .45; border-style: dashed; }
/* 工具栏容器用 padding-bottom 桥接到节点上边缘，鼠标从节点移上去时不留死角 */
.node-tools {
  display: none; position: absolute; top: -34px; left: 50%; transform: translateX(-50%);
  padding-bottom: 8px; z-index: 10; white-space: nowrap;
}
.flow-node:hover .node-tools { display: block; }
.tools-box {
  display: flex; align-items: center; gap: 6px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; padding: 3px 5px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, .1);
}
.node-tools .el-icon { cursor: pointer; color: #606266; font-size: 14px; padding: 2px; }
.node-tools .el-icon:hover { color: #409eff; }
.node-tools .el-icon.off { color: #e6a23c; }
.node-tools .el-icon.danger:hover { color: #f56c6c; }
.node-head { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #909399; }
.cat-data .dot { background: #409eff; }
.cat-ai .dot { background: #9b59b6; }
.cat-logic .dot { background: #e6a23c; }
.cat-action .dot { background: #67c23a; }
.cat-human .dot { background: #f56c6c; }
.cat-trigger .dot { background: #ff7849; }
.type-name { color: #909399; font-size: 11px; }
.off-tag { font-size: 10px; color: #e6a23c; border: 1px solid #e6a23c; border-radius: 3px; padding: 0 3px; margin-left: auto; }
.node-label { font-weight: 600; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.h-true { top: 55% !important; }
.h-false { top: 80% !important; }
.branch-tag { position: absolute; right: -18px; font-size: 10px; line-height: 1; }
.branch-tag.t { top: calc(55% - 5px); color: #67c23a; }
.branch-tag.f { top: calc(80% - 5px); color: #f56c6c; }
.branch-tag.sw { right: auto; left: calc(100% + 8px); color: #e6a23c; white-space: nowrap; max-width: 60px; overflow: hidden; text-overflow: ellipsis; }
</style>
