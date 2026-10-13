<template>
  <!-- 表格设置面板（设计文档 §2.4）：字段显隐/拖拽排序/修改/删除/新增 + 列编组管理 -->
  <el-drawer v-model="visibleModel" title="表格设置" size="380px" >
    <div class="settings">
      <div v-for="f in orderedFields" :key="f.field_name" class="field-row"
           draggable="true" @dragstart="dragFrom = f.field_name"
           @dragover.prevent @drop="onDrop(f.field_name)">
        <span class="drag">⋮⋮</span>
        <span class="f-icon">{{ regOf(f).icon }}</span>
        <span class="f-name">{{ f.label }}</span>
        <el-switch :model-value="!isHidden(f)" size="small" @change="(v) => $emit('toggle-visible', f, v)" />
        <el-dropdown trigger="click" @command="(cmd) => $emit('field-action', cmd, f)">
          <span class="f-more">⋯</span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="edit">修改字段</el-dropdown-item>
              <el-dropdown-item command="duplicate">创建副本</el-dropdown-item>
              <el-dropdown-item command="newGroup">新建编组</el-dropdown-item>
              <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <el-button class="add-field" type="primary" plain @click="$emit('add-field')">＋ 新增字段</el-button>

      <div v-if="columnGroups.length" class="groups-sec">
        <div class="sec-title">列编组</div>
        <div v-for="g in columnGroups" :key="g.id" class="group-row">
          <span class="g-name">{{ g.name }}</span>
          <span class="g-count">{{ g.field_names.length }} 列</span>
          <el-button link type="primary" size="small" @click="$emit('edit-group', g)">修改</el-button>
          <el-button link type="danger" size="small" @click="$emit('delete-group', g)">解散</el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref } from 'vue'
import { regOf } from '../../../smart/registry/fieldRegistry.js'

const props = defineProps({
  visible: Boolean,
  fields: { type: Array, default: () => [] },
  view: { type: Object, default: () => ({ config: {} }) },
  columnGroups: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'update:visible', 'toggle-visible', 'reorder', 'field-action', 'add-field', 'edit-group', 'delete-group'])
const visibleModel = computed({ get: () => props.visible, set: (v) => emit('update:visible', v) })

const dragFrom = ref(null)

const orderedFields = computed(() => {
  const order = props.view?.config?.fieldOrder
  const fs = [...props.fields]
  if (order?.length) {
    const idx = new Map(order.map((n, i) => [n, i]))
    fs.sort((a, b) => (idx.get(a.field_name) ?? 999) - (idx.get(b.field_name) ?? 999))
  }
  return fs
})

const isHidden = (f) => (props.view?.config?.fieldVisibility || {})[f.field_name] === false

function onDrop(target) {
  if (!dragFrom.value || dragFrom.value === target) return
  const order = orderedFields.value.map(f => f.field_name)
  const from = order.indexOf(dragFrom.value)
  const to = order.indexOf(target)
  order.splice(to, 0, order.splice(from, 1)[0])
  emit('reorder', order)
  dragFrom.value = null
}
</script>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 4px; }
.field-row { display: flex; align-items: center; gap: 8px; padding: 6px 4px; border-radius: 6px; }
.field-row:hover { background: var(--el-fill-color-light); }
.drag { color: var(--el-text-color-placeholder); cursor: grab; }
.f-icon { color: var(--el-color-primary); width: 18px; text-align: center; }
.f-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.f-more { cursor: pointer; padding: 0 4px; }
.add-field { margin-top: 10px; }
.groups-sec { margin-top: 16px; border-top: 1px solid var(--el-border-color-lighter); padding-top: 10px; }
.sec-title { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.group-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.g-name { flex: 1; font-weight: 600; }
.g-count { color: var(--el-text-color-placeholder); font-size: 12px; }
</style>
