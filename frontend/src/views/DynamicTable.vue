<template>
  <div v-loading="metaLoading">
    <div class="page-header">
      <h2>
        {{ meta?.label || '数据表' }}
        <el-tag v-if="meta && !meta.is_owner" size="small" style="margin-left: 8px">来自 {{ meta.owner_label }} 的分享</el-tag>
      </h2>
      <div>
        <el-popover placement="bottom-end" width="320" trigger="click">
          <template #reference>
            <el-button :icon="Grid">显示列</el-button>
          </template>
          <div class="col-picker">
            <div class="col-picker-head">
              <span>选择要显示的列（{{ listFields.length }}/{{ columnCandidates.length }}）</span>
              <el-button text type="primary" size="small" @click="resetColumns">恢复默认</el-button>
            </div>
            <div class="col-picker-actions">
              <el-button size="small" @click="showAllColumns">全选</el-button>
              <el-button size="small" @click="hideAllColumns">全不选</el-button>
            </div>
            <div v-for="(f, i) in orderedCandidates" :key="f.field_name" class="col-picker-row">
              <el-checkbox
                :model-value="!effHidden.has(f.field_name)"
                :label="f.label" size="small"
                @change="(v) => toggleColumn(f.field_name, v)"
              />
              <span class="col-mover">
                <el-button
                  text size="small" :type="fixedCols.has(f.field_name) ? 'primary' : 'info'"
                  title="固定到左侧：横向滚动时该列保持可见（再点取消）" @click="toggleFixedCol(f.field_name)"
                >
                  <el-icon><Position /></el-icon>
                </el-button>
                <el-button text size="small" :disabled="i === 0" title="移到最上" @click="moveColumnTo(f.field_name, 0)">
                  <el-icon><Top /></el-icon>
                </el-button>
                <el-button text size="small" :disabled="i === 0" title="上移" @click="moveColumn(f.field_name, -1)">
                  <el-icon><ArrowUp /></el-icon>
                </el-button>
                <el-button text size="small" :disabled="i === orderedCandidates.length - 1" title="下移" @click="moveColumn(f.field_name, 1)">
                  <el-icon><ArrowDown /></el-icon>
                </el-button>
                <el-button text size="small" :disabled="i === orderedCandidates.length - 1" title="移到最下" @click="moveColumnTo(f.field_name, orderedCandidates.length - 1)">
                  <el-icon><Bottom /></el-icon>
                </el-button>
              </span>
            </div>
          </div>
        </el-popover>
        <el-button v-if="canAlter" :icon="SetUp" @click="openStruct">表结构</el-button>
        <el-button :icon="Download" @click="exportXlsx">导出 Excel</el-button>
        <el-button v-if="canCreate" type="primary" :icon="Plus" @click="openCreate">新增记录</el-button>
      </div>
    </div>

    <!-- 动态筛选区：各字段条件平铺，组合为 AND -->
    <el-card v-if="filterable.length || fields.length" class="filter-card" style="margin-bottom: 14px">
      <div style="display: flex; justify-content: flex-end; margin-bottom: 6px">
        <!-- 筛选条件显隐（用户级偏好，按表记忆；顺序由「显示列」统一控制） -->
        <el-popover v-if="filterableAll.length" placement="bottom-end" width="280" trigger="click">
          <template #reference>
            <el-button text :icon="Setting" size="small">筛选设置</el-button>
          </template>
          <div class="col-picker">
            <div class="col-picker-head">
              <span>选择要显示的筛选条件（{{ filterable.length }}/{{ filterableAll.length }}）</span>
              <el-button text type="primary" size="small" @click="resetFiltersLayout">恢复默认</el-button>
            </div>
            <div v-for="f in filterableAll" :key="f.field_name" class="col-picker-row">
              <el-checkbox
                :model-value="!effHiddenFilters.has(f.field_name)"
                :label="f.label" size="small"
                @change="(v) => toggleFilter(f.field_name, v)"
              />
            </div>
          </div>
        </el-popover>
      </div>
      <el-form inline class="filter-form" label-width="88px">
        <el-form-item v-for="f in filterable" :key="f.field_name" :label="f.label">
          <el-select
            v-if="f.widget === 'select'" v-model="filterModel[f.field_name]" clearable
            style="width: 100%" placeholder="全部"
          >
            <el-option
              v-for="opt in fieldOptions(f)" :key="String(opt.value)" :label="opt.label" :value="opt.value"
            />
          </el-select>
          <RelationPicker
            v-else-if="f.widget === 'relation-picker' && f.options?.relation?.table_id"
            v-model="filterModel[f.field_name]" :relation="f.options.relation"
            :allow-create="['varchar', 'text'].includes(f.data_type)"
            placeholder="全部" style="width: 100%"
          />
          <el-select v-else-if="f.widget === 'switch'" v-model="filterModel[f.field_name]" clearable style="width: 100%" placeholder="全部">
            <el-option label="是" :value="true" /><el-option label="否" :value="false" />
          </el-select>
          <div v-else-if="f.widget === 'number'" class="num-filter">
            <el-select v-model="filterOps[f.field_name]" style="width: 64px; flex-shrink: 0">
              <el-option v-for="o in NUM_OPS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <template v-if="filterOps[f.field_name] === 'between'">
              <el-input-number
                v-model="filterModel[f.field_name]" controls-position="right"
                :precision="f.data_type === 'decimal' ? 4 : 0"
                placeholder="最小" class="ctl-grow"
              />
              <span class="num-sep">~</span>
              <el-input-number
                v-model="filterMax[f.field_name]" controls-position="right"
                :precision="f.data_type === 'decimal' ? 4 : 0"
                placeholder="最大" class="ctl-grow"
              />
            </template>
            <el-input-number
              v-else v-model="filterModel[f.field_name]" controls-position="right"
              :precision="f.data_type === 'decimal' ? 4 : 0"
              placeholder="值" class="ctl-grow"
            />
          </div>
          <div v-else-if="f.widget === 'date-picker' || f.widget === 'datetime-picker'" class="num-filter">
            <!-- 日期筛选类型：默认「范围」，其余为相对/空值等日期操作符；切换类型时清空旧值 -->
            <el-select
              :model-value="filterDateOps[f.field_name] || 'range'" style="width: 112px; flex-shrink: 0"
              @update:model-value="(v) => { filterDateOps[f.field_name] = v; filterModel[f.field_name] = null }"
            >
              <el-option v-for="o in DATE_OPS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <el-date-picker
              v-if="!filterDateOps[f.field_name] || filterDateOps[f.field_name] === 'range'"
              v-model="filterModel[f.field_name]" type="daterange" value-format="YYYY-MM-DD"
              start-placeholder="开始" end-placeholder="结束" class="ctl-grow"
            />
            <el-date-picker
              v-else-if="['eq', 'gte', 'lte'].includes(filterDateOps[f.field_name])"
              v-model="filterModel[f.field_name]" type="date" value-format="YYYY-MM-DD"
              placeholder="选择日期" class="ctl-grow"
            />
            <template v-else-if="DATE_DAY_OPS.includes(filterDateOps[f.field_name])">
              <el-input-number
                v-model="filterModel[f.field_name]" :min="0" controls-position="right"
                placeholder="N" class="ctl-grow"
              />
              <span class="num-sep">天</span>
            </template>
            <!-- today / null / not_null：无需输入值 -->
          </div>
          <el-input v-else v-model="filterModel[f.field_name]" clearable placeholder="包含..." style="width: 100%" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 动态列表：合计行固定显示数字列总和（口径 = 全部筛选结果） -->
    <el-table
      :data="rows" v-loading="loading" border stripe show-summary :summary-method="summaryMethod"
      @sort-change="onSortChange"
    >
      <el-table-column type="index" width="55" label="#" :fixed="fixedCols.size ? 'left' : false" />
      <el-table-column
        v-for="f in listFields" :key="f.field_name"
        :prop="f.field_name" :label="f.label" sortable="custom"
        show-overflow-tooltip min-width="110"
        :fixed="fixedCols.has(f.field_name) ? 'left' : false"
      >
        <template #default="{ row }">
          <template v-if="f.data_type === 'image'">
            <el-image
              v-for="id in asImageList(row[f.field_name]).slice(0, 3)" :key="id"
              :src="imageUrl(id)" :preview-src-list="asImageList(row[f.field_name]).map(imageUrl)"
              :initial-index="asImageList(row[f.field_name]).indexOf(id)"
              fit="cover" preview-teleported hide-on-click-modal class="cell-thumb"
            />
            <span v-if="asImageList(row[f.field_name]).length > 3" class="thumb-more">
              +{{ asImageList(row[f.field_name]).length - 3 }}
            </span>
          </template>
          <span v-else-if="f.data_type === 'subform'">
            {{ Array.isArray(row[f.field_name]) ? `共 ${row[f.field_name].length} 行明细` : '' }}
          </span>
          <span v-else>{{ fmt(f, row[f.field_name]) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="canEdit || canDelete" label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canEdit" text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm v-if="canDelete" title="确定删除该记录？" @confirm="del(row)">
            <template #reference>
              <el-button text type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>暂无数据</template>
    </el-table>

    <el-pagination
      v-model:current-page="page" v-model:page-size="pageSize"
      :total="total" layout="total, sizes, prev, pager, next"
      style="margin-top: 14px" @current-change="load" @size-change="load"
    />

    <el-dialog
      v-model="dialogVisible" :title="editing ? '编辑记录' : '新增记录'"
      :width="hasSubform || fields.length > 10 ? '860px' : '640px'" destroy-on-close
    >
      <DynamicForm
        :fields="formFields" :initial="editing || {}" :loading="saving"
        :table-id="tableId" :record-id="editing?.id || null"
        @submit="onSave" @cancel="dialogVisible = false"
      />
    </el-dialog>

    <!-- 表结构编辑：加/删/改/重命名字段（仅主人/admin 可见） -->
    <el-drawer v-model="structVisible" title="表结构设置" size="min(1080px, 94vw)">
      <el-form label-width="70px" style="max-width: 400px">
        <el-form-item label="表名称">
          <el-input v-model="structLabel" maxlength="64" />
        </el-form-item>
      </el-form>
      <el-divider content-position="left">字段（{{ structRows.length }}）</el-divider>
      <div class="struct-head struct-row">
        <span class="sr-label">显示名</span>
        <span class="sr-name">字段名（英文）</span>
        <span class="sr-type">类型</span>
        <span class="sr-null">可空</span>
        <span class="sr-show">显示</span>
        <span class="sr-cfg">配置</span>
        <span class="sr-del">删除</span>
      </div>
      <div v-for="(r, i) in structRows" :key="r._key" class="struct-row-wrap">
        <div class="struct-row">
          <el-input v-model="r.label" placeholder="如：金额" class="sr-label" />
          <el-input v-model="r.field_name" placeholder="如：amount" class="sr-name" />
          <el-select v-model="r.data_type" class="sr-type" :disabled="!!r.id && meta?.storage_mode !== 'json'">
            <el-option v-for="t in DATA_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <el-checkbox v-model="r.nullable" class="sr-null" />
          <!-- 显隐总开关：控制 新增/编辑/过滤/列表；子表字段不适用（始终只在表单中） -->
          <el-checkbox
            v-if="r.data_type !== 'subform'"
            :model-value="r.options?.show_in_list !== false" class="sr-show"
            @change="(v) => setRowVisible(r, v)"
          />
          <span v-else class="sr-show" style="color: #c0c4cc">-</span>
          <el-button
            text type="primary" size="small" class="sr-cfg"
            :type="hasBizConfig(r) ? 'warning' : 'primary'" @click="openFieldConfig(r)"
          >配置</el-button>
          <el-button text type="danger" size="small" class="sr-del" @click="structRows.splice(i, 1)">删</el-button>
        </div>
        <!-- 字段配置摘要：控件/选项/关联/公式/编号/子表/列表显隐，一眼看清每个字段配了什么 -->
        <div v-if="configSummary(r).length" class="struct-cfg-tags">
          <el-tag v-for="(t, j) in configSummary(r)" :key="j" size="small" type="info" effect="plain">{{ t }}</el-tag>
        </div>
      </div>
      <el-button text type="primary" size="small" @click="addStructRow">+ 添加字段</el-button>
      <div class="struct-hint">
        「显示」是总开关：关闭后该字段在新增、编辑、过滤、列表中全部隐藏；「显示列」面板只控制表格列。「配置」可设置：下拉选项、关联选择（选供应商带出地址/电话）、计算公式、subform 明细表。
      </div>
      <div v-if="meta?.storage_mode !== 'json'" class="struct-hint">
        physical 模式表暂不支持修改已有字段类型（可加/删/改名字段）
      </div>
      <div class="struct-hint">
        修改类型会尝试转换存量数据（转不了的值将被清空）；删除字段会连带删除存量数据中的该字段。
      </div>
      <div class="struct-footer">
        <el-button @click="structVisible = false">取消</el-button>
        <el-button type="primary" :loading="structSaving" @click="saveStruct">保存修改</el-button>
      </div>
    </el-drawer>

    <!-- 字段业务配置（关联带出/公式/子表列） -->
    <FieldOptionsDialog
      v-if="cfgVisible" v-model="cfgVisible" :field="cfgField"
      :sibling-fields="structRows" @save="onFieldConfigSave"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Download, SetUp, Grid, ArrowUp, ArrowDown, Top, Bottom, Setting, Position } from '@element-plus/icons-vue'
import DynamicForm from '../components/DynamicForm.vue'
import FieldOptionsDialog from '../components/FieldOptionsDialog.vue'
import RelationPicker from '../components/RelationPicker.vue'
import { alterTable, createRecord, deleteRecord, getTable, imageUrl, listRecords, listTables, recordExportUrl, updateRecord, updateTable } from '../api'

const DATA_TYPES = ['varchar', 'text', 'int', 'decimal', 'date', 'datetime', 'bool', 'image', 'subform', 'serial']
const WIDGET_OF = {
  varchar: 'input', text: 'textarea', int: 'number', decimal: 'number',
  date: 'date-picker', datetime: 'datetime-picker', bool: 'switch', image: 'image-uploader',
  subform: 'subform', serial: 'serial',
}

// 图片列兜底：值可能是 list / JSON 字符串 / null
function asImageList(v) {
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v.startsWith('[')) {
    try { return JSON.parse(v) } catch { return [] }
  }
  return []
}

const route = useRoute()
const tableId = Number(route.params.id)

const meta = ref(null)
const metaLoading = ref(true)
const rows = ref([])
const summary = ref({})   // 数字列合计（服务端随列表返回，口径为全部筛选结果）
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const sortBy = ref(null)
const sortOrder = ref(null)
const filterModel = reactive({})
// 数字字段的比较操作符与区间上限（与 filterModel 平行的辅助模型）
const NUM_OPS = [
  { value: 'eq', label: '=' }, { value: 'ne', label: '≠' },
  { value: 'gt', label: '>' }, { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' }, { value: 'lte', label: '≤' },
  { value: 'between', label: '介于' },
]
const filterOps = reactive({})
const filterMax = reactive({})
// 日期字段的筛选类型（与 filterModel 平行的辅助模型）：默认 range（范围），
// 其余为后端支持的日期操作符（等于/不早于/不晚于/当天/N 天相对条件/空值判断）
const DATE_OPS = [
  { value: 'range', label: '范围' },
  { value: 'eq', label: '等于' }, { value: 'gte', label: '不早于' }, { value: 'lte', label: '不晚于' },
  { value: 'today', label: '当天' },
  { value: 'past_days', label: '过去 N 天' }, { value: 'older_than_days', label: '早于 N 天前' },
  { value: 'within_days', label: '未来 N 天内' },
  { value: 'null', label: '为空' }, { value: 'not_null', label: '不为空' },
]
const DATE_DAY_OPS = ['past_days', 'older_than_days', 'within_days']   // 值为天数 N
const DATE_NO_VALUE_OPS = ['today', 'null', 'not_null']                // 无需输入值
const filterDateOps = reactive({})
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)

const fields = computed(() => meta.value?.fields || [])
// 「显示」总开关（show_in_list）：优先级最高，关闭后字段在 新增/编辑/过滤/列表 全部不出现；
// 子表字段天然不进列表，总开关不适用于它（始终在表单中显示）
const isFieldVisible = (f) => f.data_type === 'subform' || f.options?.show_in_list !== false
const visibleFields = computed(() => fields.value.filter(isFieldVisible))
const canCreate = computed(() => meta.value?.my_perms?.can_create)
const canEdit = computed(() => meta.value?.my_perms?.can_edit)
const canAlter = computed(() => meta.value?.is_owner || meta.value?.my_perms?.is_admin)
const canDelete = computed(() => meta.value?.my_perms?.can_delete)
// ---------- 显示列选择（用户级，localStorage 按表记忆；只控制表格列显示，候选集已被「显示」总开关过滤） ----------
const COLS_KEY = `grt_cols_${tableId}`
// 存"隐藏集合"而非"显示集合"：以后新增字段默认可见
const hiddenCols = ref(loadHiddenCols())

function loadHiddenCols() {
  try {
    const raw = localStorage.getItem(COLS_KEY)
    if (raw === null) return null   // 未自定义过 → 全部显示
    return new Set(JSON.parse(raw))
  } catch { return null }
}

function saveHiddenCols() {
  try { localStorage.setItem(COLS_KEY, JSON.stringify([...hiddenCols.value])) } catch { /* 隐私模式等场景忽略 */ }
}

const defaultHidden = computed(() => new Set())   // 显隐由「显示」总开关接管，这里不再有默认隐藏
const effHidden = computed(() => hiddenCols.value ?? defaultHidden.value)
// 可选列全集：已按「显示」总开关过滤；不含 subform
const columnCandidates = computed(() => visibleFields.value.filter((f) => f.data_type !== 'subform'))

// 列顺序（用户级，localStorage 按表记忆；null = 字段默认顺序）
const ORDER_KEY = `grt_colorder_${tableId}`
const colOrder = ref(loadColOrder())

function loadColOrder() {
  try {
    const raw = localStorage.getItem(ORDER_KEY)
    return raw === null ? null : JSON.parse(raw)
  } catch { return null }
}

function saveColOrder() {
  try { localStorage.setItem(ORDER_KEY, JSON.stringify(colOrder.value)) } catch { /* ignore */ }
}

// 固定列（左固定，用户级，localStorage 按表记忆；横向滚动时保持可见）
const FIXED_KEY = `grt_colfixed_${tableId}`
const fixedCols = ref(loadFixedCols())

function loadFixedCols() {
  try {
    const raw = localStorage.getItem(FIXED_KEY)
    return new Set(raw === null ? [] : JSON.parse(raw))
  } catch { return new Set() }
}

function saveFixedCols() {
  try { localStorage.setItem(FIXED_KEY, JSON.stringify([...fixedCols.value])) } catch { /* ignore */ }
}

function toggleFixedCol(name) {
  const next = new Set(fixedCols.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  fixedCols.value = next
  saveFixedCols()
}

// 有效列顺序：用户自定义顺序优先，之后新增的字段按默认顺序排在末尾
const orderedCandidates = computed(() => {
  const natural = columnCandidates.value
  if (!colOrder.value) return natural
  const byName = new Map(natural.map((f) => [f.field_name, f]))
  const out = []
  for (const name of colOrder.value) {
    const f = byName.get(name)
    if (f) { out.push(f); byName.delete(name) }
  }
  return out.concat([...byName.values()])
})

const listFields = computed(() => orderedCandidates.value.filter((f) => !effHidden.value.has(f.field_name)))

// 编辑表单的字段顺序：只含「显示」开启的字段；优先采用「显示列」里用户调好的列顺序；未涉及字段（subform/新字段）按默认顺序排尾
const formFields = computed(() => {
  if (!colOrder.value) return visibleFields.value
  const byName = new Map(visibleFields.value.map((f) => [f.field_name, f]))
  const out = []
  for (const name of colOrder.value) {
    const f = byName.get(name)
    if (f) { out.push(f); byName.delete(name) }
  }
  return out.concat([...byName.values()])
})

function moveColumn(name, dir) {
  const arr = orderedCandidates.value.map((f) => f.field_name)
  const i = arr.indexOf(name)
  const j = i + dir
  if (i < 0 || j < 0 || j >= arr.length) return
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
  colOrder.value = arr
  saveColOrder()
}

function moveColumnTo(name, index) {
  const arr = orderedCandidates.value.map((f) => f.field_name)
  const i = arr.indexOf(name)
  if (i < 0 || i === index) return
  arr.splice(i, 1)
  arr.splice(index, 0, name)
  colOrder.value = arr
  saveColOrder()
}

function toggleColumn(name, show) {
  const next = new Set(effHidden.value)
  if (show) next.delete(name)
  else next.add(name)
  hiddenCols.value = next
  saveHiddenCols()
}

function resetColumns() {
  hiddenCols.value = null
  colOrder.value = null
  fixedCols.value = new Set()
  try {
    localStorage.removeItem(COLS_KEY)
    localStorage.removeItem(ORDER_KEY)
    localStorage.removeItem(FIXED_KEY)
  } catch { /* ignore */ }
}

function showAllColumns() {
  hiddenCols.value = new Set()
  saveHiddenCols()
}

function hideAllColumns() {
  hiddenCols.value = new Set(columnCandidates.value.map((f) => f.field_name))
  saveHiddenCols()
}
const hasSubform = computed(() => fields.value.some((f) => f.data_type === 'subform'))
// ---------- 快捷筛选条件：顺序跟随「显示列」的列字段顺序；显隐为用户级偏好（localStorage 按表记忆） ----------
const FILTER_WIDGETS = ['input', 'select', 'switch', 'number', 'date-picker', 'datetime-picker', 'relation-picker', 'serial']
// 全部可筛选字段：基于 formFields（已实现 colOrder 排序），widget 白名单过滤（subform 天然排除）
const filterableAll = computed(() => formFields.value.filter((f) => FILTER_WIDGETS.includes(f.widget)))

// 存"隐藏集合"而非"显示集合"：以后新增字段默认显示
const FILTER_KEY = `grt_filterhidden_${tableId}`
const hiddenFilters = ref(loadHiddenFilters())

function loadHiddenFilters() {
  try {
    const raw = localStorage.getItem(FILTER_KEY)
    return raw === null ? null : new Set(JSON.parse(raw))
  } catch { return null }
}

function saveHiddenFilters() {
  try { localStorage.setItem(FILTER_KEY, JSON.stringify([...hiddenFilters.value])) } catch { /* 隐私模式等场景忽略 */ }
}

const effHiddenFilters = computed(() => hiddenFilters.value ?? new Set())
// 实际渲染的筛选条件：扣掉用户隐藏的
const filterable = computed(() => filterableAll.value.filter((f) => !effHiddenFilters.value.has(f.field_name)))

function toggleFilter(name, show) {
  const next = new Set(effHiddenFilters.value)
  if (show) next.delete(name)
  else {
    next.add(name)
    // 清理残留筛选值，避免重新显示时带出旧值（buildFilters 只迭代可见筛选条件，隐藏后本就不生效）
    filterModel[name] = null
    filterOps[name] = 'eq'
    filterMax[name] = null
    filterDateOps[name] = 'range'
  }
  hiddenFilters.value = next
  saveHiddenFilters()
}

function resetFiltersLayout() {
  hiddenFilters.value = null
  try { localStorage.removeItem(FILTER_KEY) } catch { /* ignore */ }
}

function fmt(f, val) {
  if (val === null || val === undefined) return ''
  if (f.data_type === 'bool') return val ? '是' : '否'
  if (f.data_type === 'date') return String(val).slice(0, 10)
  if (f.data_type === 'datetime') return String(val).replace('T', ' ').slice(0, 19)
  return val
}

// 合计行：首列写「合计」，数字列取服务端合计值，其余留空
function summaryMethod({ columns }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const f = fields.value.find((x) => x.field_name === col.property)
    if (!f || !['int', 'decimal'].includes(f.data_type)) return ''
    const v = summary.value[f.field_name]
    if (v === null || v === undefined) return ''
    return f.data_type === 'int' ? Math.round(v) : Math.round(v * 10000) / 10000
  })
}

function fieldOptions(f) {
  return (f.options?.options || []).map((o) =>
    typeof o === 'object' && o !== null ? o : { label: String(o), value: o }
  )
}

function buildFilters() {
  // 各字段条件平铺为数组，后端按 AND 组合
  const filters = []
  for (const f of filterable.value) {
    const v = filterModel[f.field_name]
    if (f.widget === 'number') {
      const op = filterOps[f.field_name] || 'eq'
      if (op === 'between') {
        if (v !== null && v !== undefined && v !== '') filters.push({ field: f.field_name, op: 'gte', value: v })
        const v2 = filterMax[f.field_name]
        if (v2 !== null && v2 !== undefined && v2 !== '') filters.push({ field: f.field_name, op: 'lte', value: v2 })
      } else if (v !== null && v !== undefined && v !== '') {
        filters.push({ field: f.field_name, op, value: v })
      }
      continue
    }
    if (f.widget === 'date-picker' || f.widget === 'datetime-picker') {
      // 日期：按筛选类型生成条件；datetime 字段的「当天末尾」统一按 23:59:59 收尾（与范围逻辑一致）
      const dop = filterDateOps[f.field_name] || 'range'
      const isDt = f.widget === 'datetime-picker'
      if (dop === 'range') {
        if (Array.isArray(v) && v.length === 2) {
          filters.push({ field: f.field_name, op: 'gte', value: v[0] })
          filters.push({ field: f.field_name, op: 'lte', value: isDt ? `${v[1]} 23:59:59` : v[1] })
        }
      } else if (DATE_NO_VALUE_OPS.includes(dop)) {
        filters.push({ field: f.field_name, op: dop })   // 当天/为空/不为空：无条件生效，无需值
      } else if (DATE_DAY_OPS.includes(dop)) {
        if (v !== null && v !== undefined && v !== '') filters.push({ field: f.field_name, op: dop, value: v })
      } else if (v !== null && v !== undefined && v !== '') {
        if (isDt && dop === 'lte') {
          filters.push({ field: f.field_name, op: 'lte', value: `${v} 23:59:59` })
        } else if (isDt && dop === 'eq') {
          // datetime 字段的「等于」按当天理解：用户只选到日，精确到秒匹配几乎永不命中
          filters.push({ field: f.field_name, op: 'gte', value: v })
          filters.push({ field: f.field_name, op: 'lte', value: `${v} 23:59:59` })
        } else {
          filters.push({ field: f.field_name, op: dop, value: v })
        }
      }
      continue
    }
    if (v === null || v === undefined || v === '') continue
    if (['input', 'serial'].includes(f.widget)) {
      // 单行文本/自动编号（单号）：模糊匹配
      filters.push({ field: f.field_name, op: 'contains', value: v })
    } else {
      filters.push({ field: f.field_name, op: 'eq', value: v })
    }
  }
  return filters
}

// 导出按当前筛选/排序条件（与列表同口径），上限 5000 条
function exportXlsx() {
  const f = buildFilters()
  const has = Array.isArray(f) ? f.length > 0 : (f.rules || []).length > 0
  window.open(recordExportUrl(tableId, {
    sort_by: sortBy.value || undefined,
    sort_order: sortOrder.value || undefined,
    filters: has ? JSON.stringify(f) : undefined,
  }), '_blank')
}

function queryParams() {
  return {
    page: page.value,
    page_size: pageSize.value,
    sort_by: sortBy.value || undefined,
    sort_order: sortOrder.value || undefined,
    filters: JSON.stringify(buildFilters()),
  }
}

async function load() {
  loading.value = true
  try {
    const res = await listRecords(tableId, queryParams())
    rows.value = res.items
    total.value = res.total
    summary.value = res.summary || {}
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// 静默刷新：轮询用，不闪 loading、失败不打扰
async function silentLoad() {
  try {
    const res = await listRecords(tableId, queryParams())
    rows.value = res.items
    total.value = res.total
    summary.value = res.summary || {}
  } catch { /* 静默刷新失败不打断用户 */ }
}

// 后台写入（工作流定时/webhook、其他同事编辑）感知：页面可见时每 15s 静默刷新
let pollTimer = null
function startPoll() {
  stopPoll()
  pollTimer = setInterval(() => {
    if (document.hidden || loading.value || dialogVisible.value) return
    silentLoad()
  }, 15000)
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// 同页写入（AI 助手填表等）即时刷新：监听应用内广播
function onRecordsChanged(e) {
  if (Number(e.detail?.table_id) === tableId) load()
}

function search() {
  page.value = 1
  load()
}

function resetFilters() {
  for (const k of Object.keys(filterModel)) filterModel[k] = null
  for (const k of Object.keys(filterMax)) filterMax[k] = null
  for (const k of Object.keys(filterOps)) filterOps[k] = 'eq'
  for (const k of Object.keys(filterDateOps)) filterDateOps[k] = 'range'
  search()
}

function onSortChange({ prop, order }) {
  sortBy.value = order ? prop : null
  sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  load()
}

function openCreate() {
  editing.value = null
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  dialogVisible.value = true
}

async function onSave(values) {
  saving.value = true
  try {
    if (editing.value) {
      await updateRecord(tableId, editing.value.id, values)
    } else {
      await createRecord(tableId, values)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function del(row) {
  try {
    await deleteRecord(tableId, row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 表结构编辑 ----------
const structVisible = ref(false)
const structSaving = ref(false)
const structLabel = ref('')
const structRows = ref([])
const origFields = ref([])
let structKeySeq = 0

function openStruct() {
  structLabel.value = meta.value?.label || ''
  origFields.value = JSON.parse(JSON.stringify(meta.value?.fields || []))
  // 字段行顺序优先采用「显示列」里调好的顺序（与编辑表单一致）
  const orderIndex = new Map((colOrder.value || []).map((name, i) => [name, i]))
  const sorted = colOrder.value
    ? origFields.value.slice().sort((a, b) =>
        (orderIndex.get(a.field_name) ?? 1e9) - (orderIndex.get(b.field_name) ?? 1e9))
    : origFields.value
  // 每行深拷贝：options 必须与 origFields 快照脱钩，否则原地修改（如「显示」开关）在 diff 时永远相等、保存丢失
  structRows.value = sorted.map((f) => ({ ...JSON.parse(JSON.stringify(f)), _key: ++structKeySeq }))
  structVisible.value = true
  // 拉表清单用于把关联配置的 table_id 显示成表名（失败不影响抽屉打开）
  listTables({ all: 1 })
    .then((ts) => { structTableNames.value = Object.fromEntries(ts.map((t) => [t.id, t.label])) })
    .catch(() => {})
}

function addStructRow() {
  structRows.value.push({
    id: null, _key: ++structKeySeq, label: '', field_name: '',
    data_type: 'varchar', nullable: true, widget: 'input', options: {},
  })
}

// 「显示」总开关：写入 options.show_in_list，保存时随 update_field 一起提交
function setRowVisible(r, v) {
  if (!r.options || typeof r.options !== 'object') r.options = {}
  r.options.show_in_list = !!v
}

// ---------- 字段业务配置（关联/公式/子表列） ----------
const cfgVisible = ref(false)
const cfgField = ref(null)
const structTableNames = ref({})   // 关联目标表 id → 表名（配置摘要展示用）

const WIDGET_LABELS = {
  input: '单行输入', textarea: '多行文本', number: '数字', select: '下拉选择',
  'date-picker': '日期', 'datetime-picker': '日期时间', switch: '开关',
  'image-uploader': '图片上传', 'relation-picker': '关联选择', subform: '子表', serial: '自动编号',
}

// 字段配置摘要：把 options 里的业务配置转成一行可读标签
function configSummary(r) {
  const tags = []
  const opts = r.options || {}
  const w = r.data_type === 'subform' ? 'subform' : r.widget
  if (w && w !== 'input') tags.push(`控件：${WIDGET_LABELS[w] || w}`)
  if (w === 'select' && Array.isArray(opts.options) && opts.options.length) {
    const names = opts.options.map((o) => (typeof o === 'object' && o !== null ? o.label ?? o.value : o))
    tags.push(`选项：${names.slice(0, 6).join('、')}${names.length > 6 ? ` 等 ${names.length} 项` : ''}`)
  }
  if (opts.relation?.table_id) {
    const tname = structTableNames.value[opts.relation.table_id] || `表 #${opts.relation.table_id}`
    const carry = (opts.relation.carry_fields || []).filter((m) => m.from && m.to).length
    tags.push(`关联：${tname}（存 ${opts.relation.value_field || '?'}）${carry ? `，带出 ${carry} 项` : ''}`)
  }
  if (opts.formula) tags.push(`公式：${opts.formula}${opts.sum_to ? `（合计回填 ${opts.sum_to}）` : ''}`)
  if (opts.serial) tags.push(`编号：${opts.serial.pattern || '默认规则'}`)
  if (r.data_type === 'subform') tags.push(`子表：${(opts.columns || []).length} 列`)
  return tags
}

function hasBizConfig(r) {
  const opts = r.options || {}
  return !!(opts.formula || opts.relation || opts.serial || r.data_type === 'subform'
    || (Array.isArray(opts.options) && opts.options.length)
    || (r.widget && !['input', 'textarea', 'number', 'date-picker', 'datetime-picker'].includes(r.widget)))
}

function openFieldConfig(r) {
  cfgField.value = r
  cfgVisible.value = true
}

function onFieldConfigSave({ widget, options }) {
  cfgField.value.widget = widget
  cfgField.value.options = options
  cfgVisible.value = false
}

function buildStructOps() {
  const ops = []
  const origById = new Map(origFields.value.map((f) => [f.id, f]))
  const seenIds = new Set()
  // widget/options 差异补进 update_field
  const fillBiz = (upd, r, orig) => {
    if (r.widget && r.widget !== orig.widget) upd.widget = r.widget
    if (JSON.stringify(r.options || {}) !== JSON.stringify(orig.options || {})) upd.options = r.options || {}
  }
  for (const r of structRows.value) {
    if (r.id) {
      seenIds.add(r.id)
      const orig = origById.get(r.id)
      if (!orig) continue
      if (r.field_name !== orig.field_name) {
        ops.push({
          op: 'rename_field', field_name: orig.field_name, new_field_name: r.field_name,
          ...(r.label !== orig.label ? { label: r.label } : {}),
        })
        const upd = { op: 'update_field', field_name: r.field_name }
        if (r.data_type !== orig.data_type) upd.data_type = r.data_type
        if (r.nullable !== orig.nullable) upd.nullable = r.nullable
        fillBiz(upd, r, orig)
        if (Object.keys(upd).length > 2) ops.push(upd)
      } else {
        const upd = { op: 'update_field', field_name: r.field_name }
        if (r.label !== orig.label) upd.label = r.label
        if (r.data_type !== orig.data_type) upd.data_type = r.data_type
        if (r.nullable !== orig.nullable) upd.nullable = r.nullable
        fillBiz(upd, r, orig)
        if (Object.keys(upd).length > 2) ops.push(upd)
      }
    } else if (r.field_name.trim()) {
      ops.push({
        op: 'add_field',
        field: {
          field_name: r.field_name.trim(), label: r.label.trim() || r.field_name.trim(),
          data_type: r.data_type, nullable: r.nullable,
          widget: r.widget || WIDGET_OF[r.data_type] || 'input',
          options: r.options || {},
        },
      })
    }
  }
  for (const f of origFields.value) {
    if (!seenIds.has(f.id)) ops.push({ op: 'delete_field', field_name: f.field_name })
  }
  return ops
}

async function saveStruct() {
  const ops = buildStructOps()
  const labelChanged = structLabel.value.trim() && structLabel.value.trim() !== meta.value?.label
  if (!ops.length && !labelChanged) { structVisible.value = false; return }
  const destructive = ops.filter((o) => o.op === 'delete_field' || (o.op === 'update_field' && o.data_type))
  if (destructive.length) {
    await ElMessageBox.confirm(
      '本次修改包含删除字段或修改字段类型，存量数据可能受影响（删除的字段数据将被清除、无法转换的值将被置空）。确定继续？',
      '修改确认', { type: 'warning', confirmButtonText: '继续保存', cancelButtonText: '再想想' },
    )
  }
  structSaving.value = true
  try {
    if (labelChanged) await updateTable(tableId, { label: structLabel.value.trim() })
    let result = null
    if (ops.length) result = await alterTable(tableId, ops)
    ElMessage.success(result?.changes?.length ? `已更新：${result.changes.join('；')}` : '已保存')
    if (result?.warnings?.length) ElMessage.warning(result.warnings.join('；'))
    structVisible.value = false
    meta.value = await getTable(tableId)
    load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || e)
  } finally {
    structSaving.value = false
  }
}

// 数字筛选操作符默认值（元数据加载/变更后调用）
function initFilterOps() {
  for (const f of fields.value) {
    if (f.widget === 'number' && !filterOps[f.field_name]) filterOps[f.field_name] = 'eq'
  }
}

async function reloadMeta() {
  try {
    meta.value = await getTable(tableId)
    initFilterOps()
  } catch { /* 静默 */ }
}

// AI 助手改了表结构时，元数据即时重载（字段列随之更新）
function onTableMetaChanged(e) {
  if (Number(e.detail?.table_id) === tableId) reloadMeta()
}

onMounted(async () => {
  try {
    meta.value = await getTable(tableId)
    initFilterOps()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    metaLoading.value = false
  }
  load()
  window.addEventListener('grt:records-changed', onRecordsChanged)
  window.addEventListener('grt:table-meta-changed', onTableMetaChanged)
  startPoll()
})

onUnmounted(() => {
  window.removeEventListener('grt:records-changed', onRecordsChanged)
  window.removeEventListener('grt:table-meta-changed', onTableMetaChanged)
  stopPoll()
})
</script>

<style scoped>
.struct-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; width: 100%; }
.struct-row-wrap { margin-bottom: 8px; }
.struct-row-wrap .struct-row { margin-bottom: 4px; }
.struct-cfg-tags { display: flex; flex-wrap: wrap; gap: 6px; padding-left: 2px; }
.struct-head { font-size: 12px; color: #909399; }
/* 显示名/字段名弹性占满剩余宽度，其余列固定 */
.sr-label { flex: 1 1 0; min-width: 140px; }
.sr-name { flex: 1 1 0; min-width: 160px; }
.sr-type { width: 120px; flex: none; }
.sr-null { width: 40px; flex: none; white-space: nowrap; display: flex; justify-content: center; margin-right: 0; }
.sr-show { width: 40px; flex: none; white-space: nowrap; display: flex; justify-content: center; margin-right: 0; }
.sr-cfg { width: 42px; flex: none; display: flex; justify-content: center; padding-left: 0; padding-right: 0; }
.sr-del { width: 36px; flex: none; display: flex; justify-content: center; padding-left: 0; padding-right: 0; margin-left: 0; }
.struct-hint { font-size: 12px; color: #909399; margin-top: 10px; }
.struct-footer { margin-top: 18px; display: flex; justify-content: flex-end; gap: 8px; }
.cell-thumb { width: 40px; height: 40px; border-radius: 4px; margin-right: 4px; vertical-align: middle; }
.thumb-more { font-size: 12px; color: #909399; }
.num-filter { display: flex; align-items: center; gap: 4px; width: 100%; }
.num-sep { color: #909399; flex-shrink: 0; }
/* 筛选卡片：收紧默认 body padding（el-card 默认 20px），减少筛选区上下的空隙 */
.filter-card :deep(.el-card__body) { padding: 10px 16px 2px; }
/* 筛选区：等宽网格列对齐——每项一格、列宽一致（格宽按最宽组合控件「日期范围」≈430px 定） */
.filter-form { display: grid; grid-template-columns: repeat(auto-fill, minmax(430px, 1fr)); column-gap: 18px; }
.filter-form :deep(.el-form-item) { margin-right: 0; }
.filter-form :deep(.el-form-item__label) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.filter-form :deep(.el-form-item__content) { min-width: 0; }
/* 组合控件（操作符 + 值）里的值控件吃掉剩余宽度，保证各项右缘对齐 */
.filter-form .ctl-grow { flex: 1; min-width: 0; }
.filter-form .ctl-grow :deep(.el-input__wrapper) { width: 100%; }
.col-picker { display: flex; flex-direction: column; max-height: 360px; overflow-y: auto; }
.col-picker-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; color: #606266; }
.col-picker-actions { display: flex; gap: 8px; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #ebeef5; }
.col-picker-actions .el-button + .el-button { margin-left: 0; }
.col-picker-row { display: flex; align-items: center; justify-content: space-between; }
.col-picker-row .el-checkbox { flex: 1; }
.col-mover { display: flex; }
.col-mover .el-button + .el-button { margin-left: 2px; }
</style>
