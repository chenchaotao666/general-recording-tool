<template>
  <el-dialog
    :model-value="modelValue" :title="mode === 'edit' ? '卡片设置' : '添加卡片'"
    width="min(680px, 94vw)" append-to-body destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <!-- 编辑模式：顶部显示当前卡片类型 -->
    <div v-if="mode === 'edit' && currentType" class="type-current">
      <span class="type-icon" :style="{ background: currentType.accent.bg, color: currentType.accent.fg }">
        <el-icon :size="18"><component :is="currentType.icon" /></el-icon>
      </span>
      <span class="type-current-name">{{ currentType.name }}</span>
    </div>

    <!-- 第一步：选类型 -->
    <template v-if="mode !== 'edit'">
      <div class="step-label">选择卡片类型</div>
      <div class="type-grid">
        <div
          v-for="t in types" :key="t.type" class="type-item" :class="{ active: type === t.type }"
          @click="pick(t)"
        >
          <span class="type-icon" :style="{ background: t.accent.bg, color: t.accent.fg }">
            <el-icon :size="18"><component :is="t.icon" /></el-icon>
          </span>
          <span class="type-text">
            <span class="type-name">{{ t.name }}</span>
            <span class="type-desc">{{ t.desc }}</span>
          </span>
          <el-icon v-if="type === t.type" class="type-check"><CircleCheckFilled /></el-icon>
        </div>
      </div>
    </template>

    <!-- 第二步：配置（按类型） -->
    <template v-if="type">
      <div class="step-label">卡片设置</div>
      <el-form label-width="86px" size="small" class="cfg-form">
      <el-form-item v-if="type === 'table'" label="数据表" required>
        <el-select v-model="cfg.table_id" filterable placeholder="选择数据表" style="width: 100%">
          <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="type === 'table'" label="显示">
        <el-checkbox v-model="cfg.show_count">显示记录数</el-checkbox>
      </el-form-item>
      <el-form-item v-if="type === 'menu'" label="功能" required>
        <el-select v-model="cfg.path" placeholder="选择功能入口" style="width: 100%">
          <el-option v-for="e in menuEntries" :key="e.path" :label="e.title" :value="e.path">
            <span>{{ e.title }}</span>
            <span class="menu-desc">{{ e.desc }}</span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item v-if="type === 'report'" label="报表" required>
        <el-select v-model="cfg.report_id" filterable placeholder="选择报表" style="width: 100%"
                   @change="onReportChange">
          <el-option v-for="r in reports" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="type === 'report' && cfg.report_id" label="区块">
        <el-select v-model="cfg.block_id" clearable placeholder="自动（第一个统计卡/图表）" style="width: 100%">
          <el-option v-for="b in reportBlocks" :key="b.id" :label="`${b.title || '未命名'}（${b.type}）`" :value="b.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="['notifications', 'todos', 'table-list'].includes(type)" label="条数">
        <el-input-number v-model="cfg.limit" :min="1" :max="20" />
      </el-form-item>
      <!-- 数据类卡片（菜单卡是纯入口，无数据可刷） -->
      <el-form-item v-if="['table', 'table-list', 'notifications', 'todos', 'report'].includes(type)" label="自动刷新">
        <el-select v-model="cfg.refresh" style="width: 160px">
          <el-option label="关闭" :value="0" />
          <el-option label="每 30 秒" :value="30" />
          <el-option label="每 1 分钟" :value="60" />
          <el-option label="每 5 分钟" :value="300" />
          <el-option label="每 10 分钟" :value="600" />
        </el-select>
      </el-form-item>
    </el-form>
    </template>
    <el-empty v-else description="先选择卡片类型" :image-size="60" />

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!valid" @click="confirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { getReport, listReports } from '../api'
import { listCardTypes, menuEntriesFor } from './cardTypes'
import { loadTablesShared } from './tableCache'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  mode: { type: String, default: 'add' },           // add / edit
  initial: { type: Object, default: null },         // edit 模式：{type, config}
})
const emit = defineEmits(['update:modelValue', 'confirm'])

const types = listCardTypes()
const user = JSON.parse(localStorage.getItem('grt_user') || 'null')
const menuEntries = menuEntriesFor(user)

const type = ref('')
const cfg = reactive({})
const tables = ref([])
const reports = ref([])
const reportBlocks = ref([])

const currentType = computed(() => types.find((t) => t.type === type.value) || null)

watch(() => props.modelValue, async (v) => {
  if (!v) return
  if (props.mode === 'edit' && props.initial) {
    type.value = props.initial.type
    Object.keys(cfg).forEach((k) => delete cfg[k])
    Object.assign(cfg, props.initial.config || {})
    cfg.refresh ??= 0   // 老卡片无此配置时给默认
    if (cfg.report_id) onReportChange(cfg.report_id)
  } else {
    type.value = ''
    Object.keys(cfg).forEach((k) => delete cfg[k])
    reportBlocks.value = []
  }
  tables.value = await loadTablesShared()
  try { reports.value = await listReports() } catch { reports.value = [] }
})

async function onReportChange(id) {
  cfg.block_id = null
  reportBlocks.value = []
  try {
    const t = await getReport(id)
    reportBlocks.value = (t.blocks || []).filter((b) => b.type !== 'filter')
  } catch { /* 列表里保留选择即可 */ }
}

function pick(t) {
  type.value = t.type
  Object.keys(cfg).forEach((k) => delete cfg[k])
  Object.assign(cfg, t.defaultConfig || {})
  cfg.refresh = 0   // 数据类卡片默认不自动刷新
  if (t.type === 'menu') cfg.path = ''
  if (t.type === 'table') { cfg.table_id = null; cfg.show_count = true }
  if (t.type === 'report') { cfg.report_id = null; cfg.block_id = null }
}

const valid = computed(() => {
  if (!type.value) return false
  if (type.value === 'table') return !!cfg.table_id
  if (type.value === 'menu') return !!cfg.path
  if (type.value === 'report') return !!cfg.report_id
  return true
})

function confirm() {
  emit('confirm', { type: type.value, config: { ...cfg } })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.step-label { font-size: 13px; font-weight: 600; color: #606266; margin: 2px 0 10px; }
.cfg-form { margin-top: 2px; }

/* 类型卡片：图标柔色底 + 名称/描述，选中带对勾 */
.type-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.type-item {
  position: relative; display: flex; align-items: center; gap: 10px;
  border: 1px solid #e4e7ed; border-radius: 10px; padding: 10px 12px; cursor: pointer;
  transition: border-color .15s, box-shadow .15s, background .15s;
}
.type-item:hover { border-color: #a0cfff; box-shadow: 0 2px 8px rgba(64, 158, 255, .12); }
.type-item.active { border-color: #409eff; background: #f5faff; }
.type-icon {
  width: 36px; height: 36px; border-radius: 9px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.type-text { display: flex; flex-direction: column; min-width: 0; }
.type-name { font-size: 13px; font-weight: 600; color: #303133; }
.type-desc {
  font-size: 12px; color: #909399; margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.type-check { position: absolute; top: 6px; right: 8px; color: #409eff; font-size: 16px; }

/* 编辑模式顶部：当前类型 */
.type-current { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.type-current-name { font-size: 14px; font-weight: 600; color: #303133; }

.menu-desc { float: right; color: #909399; font-size: 12px; }
</style>
