<template>
  <!-- 视图页签（设计文档 §2.3）：同一数据多视图，配置独立 -->
  <div class="view-tabs">
    <div v-for="v in views" :key="v.id" class="view-tab" :class="{ active: v.id === currentId }"
         @click="$emit('switch', v)">
      <span class="vt-icon">⊞</span>{{ v.name }}
      <el-dropdown v-if="v.id === currentId" trigger="click" @command="(cmd) => $emit('action', cmd, v)">
        <span class="vt-more" @click.stop>⋮</span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="rename">重命名</el-dropdown-item>
            <el-dropdown-item command="duplicate">复制视图</el-dropdown-item>
            <el-dropdown-item command="default">设为默认</el-dropdown-item>
            <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <span class="vt-add" title="新建视图" @click="$emit('action', 'add')">＋</span>
  </div>
</template>

<script setup>
defineProps({ views: { type: Array, default: () => [] }, currentId: Number })
defineEmits(['switch', 'action'])
</script>

<style scoped>
.view-tabs { display: flex; align-items: center; gap: 2px; border-bottom: 1px solid var(--el-border-color-lighter); padding: 0 8px; background: #fff; }
.view-tab { display: inline-flex; align-items: center; gap: 4px; padding: 8px 12px; font-size: 13px; cursor: pointer; color: var(--el-text-color-regular); border-bottom: 2px solid transparent; }
.view-tab.active { color: var(--el-color-primary); border-bottom-color: var(--el-color-primary); font-weight: 600; }
.vt-icon { font-size: 12px; }
.vt-more { padding: 0 4px; color: var(--el-text-color-placeholder); }
.vt-more:hover { color: var(--el-color-primary); }
.vt-add { padding: 4px 8px; cursor: pointer; color: var(--el-color-primary); font-weight: 600; }
</style>
