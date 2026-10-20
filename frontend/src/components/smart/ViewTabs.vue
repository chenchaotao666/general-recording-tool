<template>
  <!-- 视图页签（对齐参照 上方Tab页签.png）：激活=浅灰圆角块 + 类型图标 + ⋮；非激活灰字无底；末尾竖分隔 + ＋ -->
  <div class="view-tabs">
    <div v-for="v in views" :key="v.id" class="view-tab" :class="{ active: v.id === currentId }"
         @click="$emit('switch', v)">
      <StIcon :name="TYPE_ICON[v.type] || 'view-grid'" :size="13" class="vt-icon" />{{ v.name }}
      <el-dropdown :hide-after="0" v-if="v.id === currentId" trigger="click" @command="(cmd) => $emit('action', cmd, v)">
        <span class="vt-more st-icon-action" @click.stop><StIcon name="more-v" :size="13" /></span>
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
    <!-- ＋：新建表格视图 / 看板 / 表单（§12.1：表单与表格视图并列于页签，可建多个） -->
    <el-dropdown :hide-after="0" trigger="click" @command="(t) => $emit('action', 'add', t)">
      <span class="vt-add st-icon-action" data-smart-tip="新建视图"><StIcon name="plus" :size="13" /></span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="grid"><StIcon name="view-grid" :size="14" class="vt-dd-i" />表格视图</el-dropdown-item>
          <el-dropdown-item command="kanban"><StIcon name="kanban" :size="14" class="vt-dd-i" />看板视图</el-dropdown-item>
          <el-dropdown-item command="form"><StIcon name="form" :size="14" class="vt-dd-i" />表单</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <div v-if="$slots.actions" class="vt-actions"><slot name="actions" /></div>
  </div>
</template>

<script setup>
import StIcon from './icons/StIcon.vue'

defineProps({ views: { type: Array, default: () => [] }, currentId: Number })
const TYPE_ICON = { grid: 'view-grid', form: 'form', kanban: 'kanban' }
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
.vt-dd-i { margin-right: 6px; color: var(--st-text-2); }
.vt-actions { display: flex; align-items: center; flex-shrink: 0; margin-left: auto; margin-bottom: 6px; padding-left: 12px; }
</style>
