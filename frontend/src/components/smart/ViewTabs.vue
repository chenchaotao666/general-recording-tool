<template>
  <!-- 视图页签（对齐参照 上方Tab页签.png）：激活=浅灰圆角块 + 类型图标 + ⋮；非激活灰字无底；末尾竖分隔 + ＋ -->
  <div class="view-tabs">
    <div v-for="v in views" :key="v.id" class="view-tab" :class="{ active: v.id === currentId }"
         @click="$emit('switch', v)">
      <StIcon name="view-grid" :size="13" class="vt-icon" />{{ v.name }}
      <el-dropdown v-if="v.id === currentId" trigger="click" @command="(cmd) => $emit('action', cmd, v)">
        <span class="vt-more" @click.stop><StIcon name="more-v" :size="13" /></span>
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
    <span class="vt-sep" />
    <span class="vt-add" title="新建视图" @click="$emit('action', 'add')"><StIcon name="plus" :size="13" /></span>
  </div>
</template>

<script setup>
import StIcon from './icons/StIcon.vue'

defineProps({ views: { type: Array, default: () => [] }, currentId: Number })
defineEmits(['switch', 'action'])
</script>

<style scoped>
.view-tabs { display: flex; align-items: center; gap: 2px; border-bottom: 1px solid var(--st-border); padding: 6px 8px 0; background: #fff; }
.view-tab {
  display: inline-flex; align-items: center; gap: 5px; padding: 5px 10px; margin-bottom: 6px;
  font-size: 13px; cursor: pointer; color: var(--st-text-2); border-radius: 6px;
}
.view-tab:hover { background: var(--st-bg-hover); }
.view-tab.active { background: var(--st-bg-active); color: var(--st-text-1); font-weight: 500; }
.vt-icon { color: var(--st-text-3); }
.view-tab.active .vt-icon { color: var(--st-text-2); }
.vt-more { display: inline-flex; padding: 0 2px; color: var(--st-text-3); border-radius: 4px; }
.vt-more:hover { color: var(--st-text-1); }
.vt-sep { width: 1px; height: 16px; background: var(--st-border); margin: 0 6px 6px; }
.vt-add { display: inline-flex; padding: 4px; margin-bottom: 6px; cursor: pointer; color: var(--st-text-2); border-radius: 4px; }
.vt-add:hover { background: var(--st-bg-hover); }
</style>
