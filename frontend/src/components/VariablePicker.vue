<template>
  <el-popover v-model:visible="visible" placement="bottom-end" :width="320" trigger="click">
    <template #reference>
      <el-button link type="primary" size="small" class="picker-btn" :title="title">
        <el-icon><MagicStick /></el-icon><span v-if="!compact">插入变量</span>
      </el-button>
    </template>
    <el-input v-model="kw" size="small" placeholder="搜索变量名" clearable class="mb" />
    <div class="vars">
      <div v-for="g in filtered" :key="g.title" class="group">
        <div class="g-title">{{ g.title }}</div>
        <!-- 时间变量分组 + controlPick 模式（筛选值等场景）：点了就关掉面板，
             由外层把控件换成日期/日期时间选择器，不在面板里弹选择内容 -->
        <template v-if="g.datePicker && controlPick">
          <div class="v-item" @click="pickControl('date')">
            <span class="v-label">日期选择…</span><code class="v-expr">YYYY-MM-DD</code>
          </div>
          <div class="v-item" @click="pickControl('datetime')">
            <span class="v-label">日期时间选择…</span><code class="v-expr">YYYY-MM-DD HH:mm:ss</code>
          </div>
        </template>
        <div v-for="it in g.items" :key="it.expr" class="v-item" @click="pick(it)">
          <span class="v-label">{{ it.label }}</span>
          <code class="v-expr">{{ it.expr }}</code>
        </div>
      </div>
      <div v-if="!filtered.length" class="empty">{{ emptyText }}</div>
    </div>
  </el-popover>
</template>

<script setup>
import { computed, ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'

const props = defineProps({
  // [{ title: '查昨日收支 (q_1)', items: [{ label: '记录数', expr: '{nodes.q_1.count}' }] }]
  groups: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },   // 紧凑模式：只显示图标（用在条件行的值旁边）
  title: { type: String, default: '插入变量' },
  emptyText: { type: String, default: '无可用变量（先用连线接入上游节点）' },
  // 开启后，时间变量分组的「日期选择/日期时间选择」通过 pick-control 事件交给外层把控件换成对应选择器
  controlPick: { type: Boolean, default: false },
})
const emit = defineEmits(['insert', 'pick-control'])

const visible = ref(false)
const kw = ref('')

const filtered = computed(() => {
  const k = kw.value.trim().toLowerCase()
  if (!k) return props.groups
  return props.groups
    .map((g) => ({
      ...g,
      items: g.items.filter((it) =>
        it.label.toLowerCase().includes(k) || it.expr.toLowerCase().includes(k)
        || g.title.toLowerCase().includes(k)),
    }))
    .filter((g) => g.items.length || (g.datePicker && props.controlPick))
})

function pick(it) {
  emit('insert', it.expr)
  visible.value = false
}

function pickControl(mode) {
  emit('pick-control', mode)
  visible.value = false
}
</script>

<style scoped>
.picker-btn { padding: 0; font-size: 12px; }
.mb { margin-bottom: 6px; }
.vars { max-height: 320px; overflow-y: auto; }
.g-title { font-size: 12px; color: #909399; margin: 8px 0 2px; }
.v-item {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 5px 8px; border-radius: 4px; cursor: pointer; font-size: 12px;
}
.v-item:hover { background: #ecf5ff; }
.v-label { color: #303133; }
.v-expr { color: #c0c4cc; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { color: #c0c4cc; font-size: 12px; text-align: center; padding: 16px 0; }
</style>
