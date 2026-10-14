<template>
  <div class="st-page">
    <!-- 视图页签 -->
    <ViewTabs :views="views" :current-id="view?.id" @switch="switchView" @action="onViewAction" />

    <!-- 工具栏（设计文档 §2.1 L3：徽章=生效规则数） -->
    <div class="toolbar">
      <el-button type="primary" size="small" :disabled="!perms.can_create" @click="addRow">⊕ 添加一行</el-button>
      <el-divider direction="vertical" />
      <el-button size="small" text @click="settingsVisible = true">▦ 表格设置</el-button>

      <FilterPanel :visible="activePanel === 'filter'" @update:visible="(v) => (activePanel = v ? 'filter' : (activePanel === 'filter' ? null : activePanel))" :fields="resolvedFields"
                   :conditions="panelConditions" :scope="filterScope"
                   @change="onFiltersChange" @scope-change="onScopeChange">
        <el-button size="small" text :type="filterCount ? 'primary' : ''"
                   >⧩ 筛选{{ filterCount ? ` ${filterCount}` : '' }}</el-button>
      </FilterPanel>

      <GroupPanel :visible="activePanel === 'group'" @update:visible="(v) => (activePanel = v ? 'group' : (activePanel === 'group' ? null : activePanel))" :fields="fields" :groups="cfg.groups || []"
                  @change="(v) => patchConfig({ groups: v })">
        <el-button size="small" text :type="(cfg.groups || []).length ? 'primary' : ''"
                   >≡ 分组{{ (cfg.groups || []).length ? ` ${cfg.groups.length}` : '' }}</el-button>
      </GroupPanel>

      <SortPanel :visible="activePanel === 'sort'" @update:visible="(v) => (activePanel = v ? 'sort' : (activePanel === 'sort' ? null : activePanel))" :fields="fields" :sorts="cfg.sorts || []"
                 :auto-sort="cfg.autoSort !== false"
                 @change="(v) => patchConfig({ sorts: v })" @auto-sort="(v) => patchConfig({ autoSort: v })">
        <el-button size="small" text :type="(cfg.sorts || []).length ? 'primary' : ''"
                   >⇅ 排序{{ (cfg.sorts || []).length ? ` ${cfg.sorts.length}` : '' }}</el-button>
      </SortPanel>

      <el-dropdown trigger="click" @command="(v) => patchConfig({ rowHeight: v })">
        <el-button size="small" text @click.stop>⇕ 行高</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="(l, k) in ROW_HEIGHTS" :key="k" :command="k">
              <span :style="{ color: cfg.rowHeight === k || (!cfg.rowHeight && k === 'default') ? 'var(--el-color-primary)' : '' }">
                {{ cfg.rowHeight === k || (!cfg.rowHeight && k === 'default') ? '✓ ' : '' }}{{ l }}
              </span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <FillPanel :visible="activePanel === 'fill'" @update:visible="(v) => (activePanel = v ? 'fill' : (activePanel === 'fill' ? null : activePanel))" :fields="resolvedFields" :rules="cfg.fillRules || []"
                 @change="(v) => patchConfig({ fillRules: v })">
        <el-button size="small" text :type="fillCount ? 'primary' : ''"
                   >🖌 填色{{ fillCount ? ` ${fillCount}` : '' }}</el-button>
      </FillPanel>

      <div class="tb-right">
        <!-- 条件胶囊（pin 的筛选条件） -->
        <el-popover v-for="c in pinnedConditions" :key="c.id" trigger="click" placement="bottom-start" :width="320">
          <template #reference>
            <span class="chip">✓ {{ labelOf(c.fieldId) }} ▾</span>
          </template>
          <div class="chip-edit">
            <el-select :model-value="c.operator" size="small" style="width: 100px"
                       @change="(v) => updateChip(c, { operator: v })">
              <el-option v-for="op in opsOf(c)" :key="op" :value="op" :label="OP_LABELS[op]" />
            </el-select>
            <el-button link type="danger" size="small" @click="removeChip(c)">删除</el-button>
          </div>
        </el-popover>
        <el-button size="small" text circle title="撤销" :disabled="!undoStack.canUndo" @click="doUndo">↶</el-button>
        <el-button size="small" text circle title="重做" :disabled="!undoStack.canRedo" @click="doRedo">↷</el-button>
        <el-button size="small" text circle title="查找替换" @click="findVisible = true">🔍</el-button>
      </div>
    </div>

    <!-- 批量操作条 -->
    <div v-if="selection.length" class="batch-bar">
      已选 {{ selection.length }} 条
      <el-button size="small" type="danger" plain @click="batchDelete">批量删除</el-button>
      <el-button size="small" text @click="selection = []">取消</el-button>
    </div>

    <!-- 网格 -->
    <SmartGrid
      ref="gridRef"
      v-loading="loading"
      :fields="resolvedFields" :rows="rows" :grouped="grouped" :total="total" :aggregations="aggregations"
      :view="view" :column-groups="columnGroups" :collapsed-groups="collapsedGroups"
      :height="gridHeight" :readonly="!perms.can_edit"
      @cell-commit="onCellCommit" @add-row="addRow" @cell-menu="onCellMenu" @field-menu="onFieldMenu"
      @toggle-group="toggleGroup" @selection-change="(s) => (selection = s)" @open-config="openFieldConfig"
      @add-field="openFieldConfig(null)" @add-option="onAddOption"
    />

    <!-- 分页（未分组时） -->
    <div v-if="!grouped && total > pageSize" class="pager">
      <el-pagination layout="prev, pager, next, total" :total="total" :page-size="pageSize"
                     :current-page="page" @current-change="(p) => { page = p; loadGrid() }" />
    </div>

    <!-- 面板与弹窗 -->
    <TableSettingsPanel :visible="settingsVisible" @update:visible="(v) => (settingsVisible = v)" :fields="fields" :view="view" :column-groups="columnGroups"
                        @close="settingsVisible = false" @toggle-visible="onToggleVisible" @reorder="onReorder"
                        @field-action="onFieldAction" @add-field="openFieldConfig(null)"
                        @edit-group="editGroup" @delete-group="deleteGroup" />
    <FieldConfigDialog :visible="fieldDialog.visible" :field="fieldDialog.field" :fields="fields"
                       :tables="allTables" :source-fields-of="loadFieldsOf"
                       @close="fieldDialog.visible = false" @save="onFieldSave" />
    <RecordDetailDrawer :visible="detail.visible" @update:visible="(v) => (detail.visible = v)" :record="detail.record" :fields="resolvedFields"
                        :has-prev="detailIdx > 0" :has-next="detailIdx < dataRows.length - 1"
                        @close="detail.visible = false" @nav="navDetail" @cell-commit="onCellCommit" />
    <FindReplaceDialog :visible="findVisible" :table-id="tableId"
                       @close="findVisible = false" @replaced="loadGrid" />

    <!-- 字段列头菜单 -->
    <teleport to="body">
      <div v-if="fieldMenu.visible" class="fm-mask" @click="fieldMenu.visible = false"
           @contextmenu.prevent="fieldMenu.visible = false">
        <div class="fm" :style="{ left: `${fieldMenu.x}px`, top: `${fieldMenu.y}px` }" @click.stop>
          <div class="mi" @click="fieldAct('edit')">✏ 修改字段</div>
          <div class="mi" @click="fieldAct('filterBy')">⧩ 筛选</div>
          <div class="mi" @click="fieldAct('sortAsc')">↑ {{ dirLabels[0] }}</div>
          <div class="mi" @click="fieldAct('sortDesc')">↓ {{ dirLabels[1] }}</div>
          <div class="mi" @click="fieldAct('freeze')">❄ 冻结至此列</div>
          <div class="mi" @click="fieldAct('hide')">🚫 隐藏</div>
          <div class="mi" @click="fieldAct('duplicate')">⧉ 创建副本</div>
          <div class="mi danger" @click="fieldAct('delete')">🗑 删除</div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, provide, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import SmartGrid from '../../components/smart/grid/SmartGrid.vue'
import ViewTabs from '../../components/smart/ViewTabs.vue'
import FilterPanel from '../../components/smart/panels/FilterPanel.vue'
import SortPanel from '../../components/smart/panels/SortPanel.vue'
import GroupPanel from '../../components/smart/panels/GroupPanel.vue'
import FillPanel from '../../components/smart/panels/FillPanel.vue'
import TableSettingsPanel from '../../components/smart/panels/TableSettingsPanel.vue'
import FieldConfigDialog from '../../components/smart/panels/FieldConfigDialog.vue'
import RecordDetailDrawer from '../../components/smart/panels/RecordDetailDrawer.vue'
import FindReplaceDialog from '../../components/smart/panels/FindReplaceDialog.vue'
import { FIELD_REGISTRY, filterOpsOf, OP_LABELS, OPTION_COLORS, sortDirectionLabels } from '../../smart/registry/fieldRegistry.js'
import { isRuleComplete, createUndoStack } from '../../smart/utils/format.js'
import { resolveRefOptions } from '../../smart/utils/refOptions.js'
import {
  alterTable, getTable, listMembers, listTables,
  smartGrid, smartListViews, smartCreateView, smartUpdateView, smartDeleteView,
  smartDuplicateView, smartSetDefaultView, smartPutViewPref, smartDeleteViewPref,
  smartCreateRecord, smartUpdateRecord, smartDeleteRecord, smartBatchDelete,
  smartDuplicateRecord, smartDuplicateField, smartFieldDeps,
  smartListColumnGroups, smartCreateColumnGroup, smartDeleteColumnGroup,
} from '../../api/index.js'

const route = useRoute()
const tableId = Number(route.params.tableId)

const ROW_HEIGHTS = { default: '默认', medium: '中等', tall: '高', extraTall: '超高' }

// ---------- 状态 ----------
const loading = ref(false)
const fields = ref([])
const rows = ref([])
const total = ref(0)
const aggregations = ref({})
const grouped = ref(false)
const views = ref([])
const view = ref(null)
const perms = ref({ can_create: true, can_edit: true, can_delete: true })
const columnGroups = ref([])
const collapsedGroups = ref(new Set())
const selection = ref([])
const page = ref(1)
const pageSize = 200
const activePanel = ref(null)
const settingsVisible = ref(false)
const findVisible = ref(false)
const filterScope = ref('shared')
const undoStack = createUndoStack()

const members = ref([])
const memberDir = computed(() => new Map(members.value.map(m => [Number(m.id), m])))
provide('smartMembers', members)
provide('smartMemberDir', memberDir)

const relationRows = ref(new Map())
provide('smartRelationRows', relationRows)
const relationDir = computed(() => {
  const m = new Map()
  for (const [tid, rowsL] of relationRows.value) m.set(tid, new Map(rowsL.map(r => [r.id, r.label])))
  return m
})
provide('smartRelationDir', relationDir)

// ---------- 引用选项 / 选项联动（设计文档 §3.3） ----------
// refFieldsCache: 引用表 id → 其字段元数据（解析选项集用）
// refRowsCache:   引用表 id → 其记录行（联动条件比较用）
const refFieldsCache = ref(new Map())
const refRowsCache = ref(new Map())

const isRefSelect = (f) => ['singleSelect', 'multiSelect'].includes(f.field_type)
  && f.options?.optionSource === 'reference' && f.options?.reference?.tableId

async function loadRefSources() {
  for (const f of fields.value.filter(isRefSelect)) {
    const tid = f.options.reference.tableId
    try {
      if (!refFieldsCache.value.has(tid)) {
        const meta = await getTable(tid)
        refFieldsCache.value = new Map(refFieldsCache.value).set(tid, meta.fields)
      }
      if (f.options.optionLinkage?.enabled && !refRowsCache.value.has(tid)) {
        const g = await smartGrid(tid, { page_size: 200 })
        refRowsCache.value = new Map(refRowsCache.value).set(tid, g.items.filter(r => !r.__rowType))
      }
    } catch { /* 引用表无权访问/已删除：兜底本地 options */ }
  }
}

// 渲染用字段：reference 模式的选项集实时取自引用字段（源表变更自动同步）
const resolvedFields = computed(() => fields.value.map(f => {
  if (!isRefSelect(f)) return f
  const ref = f.options.reference
  const refField = (refFieldsCache.value.get(ref.tableId) || []).find(x => x.field_name === ref.fieldId)
  return { ...f, options: { ...f.options, options: resolveRefOptions(f, refField) } }
}))

// 联动上下文：单元格编辑器按当前行过滤可选项
const refContext = computed(() => {
  const m = new Map()
  for (const f of fields.value.filter(x => isRefSelect(x) && x.options.optionLinkage?.enabled)) {
    const ref = f.options.reference
    m.set(f.field_name, {
      linkage: f.options.optionLinkage,
      remoteRows: refRowsCache.value.get(ref.tableId) || [],
      refFieldId: ref.fieldId,
    })
  }
  return m
})
provide('smartRefContext', refContext)

const cfg = computed(() => view.value?.config || {})
const dataRows = computed(() => rows.value.filter(r => r.__rowType !== 'group' && r.__rowType !== 'add'))
const gridHeight = computed(() => window.innerHeight - 220)
const gridRef = ref(null)

const filterCount = computed(() => (cfg.value.filters?.conditions || []).filter(c => c.fieldId).length)
const fillCount = computed(() => (cfg.value.fillRules || []).filter(isRuleComplete).length)
const pinnedConditions = computed(() => (cfg.value.filters?.conditions || []).filter(c => c.pinned && c.fieldId))
const panelConditions = computed(() => cfg.value.filters?.conditions || [])

// ---------- 加载 ----------
async function loadAll() {
  loading.value = true
  try {
    const [meta, vs, gs] = await Promise.all([
      getTable(tableId), smartListViews(tableId), smartListColumnGroups(tableId),
    ])
    fields.value = meta.fields
    perms.value = meta.my_perms || perms.value
    views.value = vs.views
    columnGroups.value = gs.groups
    members.value = (await listMembers().catch(() => [])) || []
    const qv = Number(route.query.view)
    await loadGrid(qv || undefined)
    loadRelationRows()
    loadRefSources()
  } finally {
    loading.value = false
  }
}

async function loadGrid(viewId) {
  loading.value = true
  try {
    const g = await smartGrid(tableId, { view_id: viewId, page: page.value, page_size: pageSize })
    rows.value = g.items
    total.value = g.total
    aggregations.value = g.aggregations || {}
    grouped.value = !!g.grouped
    view.value = g.view
    if (g.view) filterScope.value = g.view.config?.filtersScope === 'personal' ? 'personal' : 'shared'
  } finally {
    loading.value = false
  }
}

// 关联字段：加载目标表记录做标签目录
async function loadRelationRows() {
  for (const f of fields.value.filter(x => x.field_type === 'relation' && x.options?.targetTableId)) {
    const tid = f.options.targetTableId
    if (relationRows.value.has(tid)) continue
    try {
      const g = await smartGrid(tid, { page_size: 200 })
      const labelField = g.fields.find(x => x.field_type === 'text') || g.fields[0]
      const next = new Map(relationRows.value)
      next.set(tid, g.items.filter(r => !r.__rowType).map(r => ({ id: r.id, label: r[labelField?.field_name] ?? `#${r.id}` })))
      relationRows.value = next
    } catch { /* 目标表无权访问时忽略 */ }
  }
}

// ---------- 视图操作 ----------
function switchView(v) { page.value = 1; loadGrid(v.id) }

async function onViewAction(cmd, v) {
  if (cmd === 'add') {
    const r = await smartCreateView(tableId, { name: `表格视图 ${views.value.length + 1}`, config: {} })
    views.value.push(r.view)
    switchView(r.view)
  } else if (cmd === 'rename') {
    const { value } = await ElMessageBox.prompt('视图名称', '重命名', { inputValue: v.name })
    if (value) { await smartUpdateView(v.id, { name: value }); views.value = (await smartListViews(tableId)).views }
  } else if (cmd === 'duplicate') {
    const r = await smartDuplicateView(v.id)
    views.value.push(r.view)
  } else if (cmd === 'default') {
    await smartSetDefaultView(v.id)
    views.value = (await smartListViews(tableId)).views
  } else if (cmd === 'delete') {
    await ElMessageBox.confirm(`删除视图「${v.name}」？`, '删除', { type: 'warning' })
    await smartDeleteView(v.id)
    views.value = (await smartListViews(tableId)).views
    await loadGrid()
  }
}

// ---------- 视图配置修改（防抖保存） ----------
let saveTimer = null
function patchConfig(patch, { reload = true } = {}) {
  if (!view.value) return
  view.value = { ...view.value, config: { ...view.value.config, ...patch } }
  clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    // 保存前剔除未选字段的不完整规则（分组/排序/筛选/填色），避免后端 400
    const c = { ...view.value.config }
    if (c.groups) c.groups = c.groups.filter(g => g.fieldId)
    if (c.sorts) c.sorts = c.sorts.filter(s => s.fieldId)
    if (c.filters?.conditions) c.filters = { ...c.filters, conditions: c.filters.conditions.filter(x => x.fieldId) }
    if (c.fillRules) c.fillRules = c.fillRules.filter(r => r.fieldId)
    try {
      await smartUpdateView(view.value.id, { config: c })
    } catch (e) {
      ElMessage.error(e.message || '视图保存失败')
    }
    if (reload) loadGrid(view.value.id)
  }, 400)
  if (reload && ('filters' in patch || 'sorts' in patch || 'groups' in patch)) {
    // 筛选/排序/分组需要服务端重算——防抖后立即重查由上面定时器处理
  }
}

function togglePanel(name) { activePanel.value = activePanel.value === name ? null : name }

// 受控 popover 的外点关闭（点击面板与工具栏以外区域时收起）
function onDocClick(e) {
  if (!activePanel.value) return
  if (e.target.closest('.el-popover') || e.target.closest('.toolbar')) return
  activePanel.value = null
}

// ---------- 筛选（含个人覆盖） ----------
function onFiltersChange(conditions) {
  const filters = { conjunction: 'and', conditions }
  if (filterScope.value === 'personal') {
    view.value = { ...view.value, config: { ...view.value.config, filters, filtersScope: 'personal' } }
    smartPutViewPref(view.value.id, { filters }).then(() => loadGrid(view.value.id))
  } else {
    patchConfig({ filters })
  }
}
async function onScopeChange(scope) {
  filterScope.value = scope
  if (scope === 'shared' && view.value) {
    await smartDeleteViewPref(view.value.id).catch(() => {})
    loadGrid(view.value.id)
  }
}
function labelOf(fn) { return fields.value.find(f => f.field_name === fn)?.label || fn }
function opsOf(c) { const f = fields.value.find(x => x.field_name === c.fieldId); return f ? filterOpsOf(f) : [] }
function updateChip(c, patch) {
  onFiltersChange(panelConditions.value.map(x => (x.id === c.id ? { ...x, ...patch } : x)))
}
function removeChip(c) { onFiltersChange(panelConditions.value.filter(x => x.id !== c.id)) }

// ---------- 记录操作 ----------
async function onCellCommit({ row, field, value }) {
  const old = row[field.field_name]
  row[field.field_name] = value   // 乐观更新
  try {
    const r = await smartUpdateRecord(tableId, row.id, { data: { [field.field_name]: value } })
    Object.assign(row, r.record)
    undoStack.push({
      label: `编辑 ${field.label}`,
      undo: async () => { await smartUpdateRecord(tableId, row.id, { data: { [field.field_name]: old } }); loadGrid(view.value?.id) },
      redo: async () => { await smartUpdateRecord(tableId, row.id, { data: { [field.field_name]: value } }); loadGrid(view.value?.id) },
    })
    if (field.field_type !== 'checkbox' && cfg.value.autoSort !== false && (cfg.value.sorts || []).length) loadGrid(view.value?.id)
  } catch (e) {
    row[field.field_name] = old
    ElMessage.error(e.message || '保存失败')
  }
}

// 单元格内新建选项：落库为真选项（修旧版 allow-create 只存原始标签的问题），再提交新 optionId
async function onAddOption({ row, field, label }) {
  const f = fields.value.find(x => x.field_name === field.field_name)
  if (!f) return
  const opts = [...(f.options?.options || [])]
  const nid = `opt_${Date.now()}`
  opts.push({ id: nid, label, color: OPTION_COLORS[opts.length % OPTION_COLORS.length].key, order: opts.length })
  try {
    await alterTable(tableId, [{ op: 'update_field', field_name: f.field_name, options: { ...f.options, options: opts } }])
    f.options = { ...f.options, options: opts }
    const value = f.field_type === 'multiSelect'
      ? [...(Array.isArray(row[f.field_name]) ? row[f.field_name] : []), nid]
      : nid
    await onCellCommit({ row, field: f, value })
    ElMessage.success(`已创建选项「${label}」`)
  } catch (e) {
    ElMessage.error(e.message || '创建选项失败')
  }
}

async function addRow() {
  const r = await smartCreateRecord(tableId, { data: {} })
  undoStack.push({
    label: '添加行',
    undo: async () => { await smartDeleteRecord(tableId, r.record.id); loadGrid(view.value?.id) },
    redo: async () => { await smartCreateRecord(tableId, { data: {} }); loadGrid(view.value?.id) },
  })
  ElMessage.success('已添加一行')
  loadGrid(view.value?.id)
}

async function batchDelete() {
  await ElMessageBox.confirm(`删除选中的 ${selection.value.length} 条记录？`, '批量删除', { type: 'warning' })
  const snapshot = selection.value.map(r => ({ ...r }))
  const ids = snapshot.map(r => r.id)
  await smartBatchDelete(tableId, ids)
  undoStack.push({
    label: `删除 ${ids.length} 行`,
    undo: async () => {
      for (const s of snapshot) {
        const data = { ...s }
        delete data.id; delete data.created_at; delete data.updated_at
        delete data.owner_id; delete data.tenant_id; delete data.parent_id; delete data.updated_by
        delete data.__key; delete data.__no; delete data.__indent; delete data.__rowType
        await smartCreateRecord(tableId, { data })
      }
      loadGrid(view.value?.id)
    },
    redo: async () => { await smartBatchDelete(tableId, ids); loadGrid(view.value?.id) },
  })
  selection.value = []
  ElMessage.success('已删除')
  loadGrid(view.value?.id)
}

async function doUndo() { await undoStack.undo() }
async function doRedo() { await undoStack.redo() }

function onKeydown(e) {
  if (e.key === 'Escape') { activePanel.value = null; return }
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); doUndo() }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); doRedo() }
}

// ---------- 右键菜单（vxe menu-config 原生渲染，点击项直接分发） ----------
const ctx = reactive({ row: null, field: null })
function onCellMenu({ row, field, cmd }) {
  Object.assign(ctx, { row, field })
  onCtxAction(cmd)
}
const detail = reactive({ visible: false, record: null })
const detailIdx = computed(() => dataRows.value.findIndex(r => r.id === detail.record?.id))

async function onCtxAction(cmd) {
  const { row, field } = ctx
  if (cmd === 'expand') {
    detail.record = row; detail.visible = true
  } else if (cmd === 'only' || cmd === 'exclude') {
    const op = cmd === 'only' ? 'eq' : 'neq'
    const c = { id: `c_${Date.now()}`, fieldId: field.field_name, operator: op, value: row[field.field_name] }
    onFiltersChange([...panelConditions.value, c])
  } else if (cmd === 'duplicate') {
    await smartDuplicateRecord(tableId, row.id)
    loadGrid(view.value?.id)
  } else if (cmd === 'add-child') {
    await smartCreateRecord(tableId, { data: {}, parent_id: row.id })
    loadGrid(view.value?.id)
  } else if (cmd === 'delete') {
    await ElMessageBox.confirm('删除这条记录？', '删除', { type: 'warning' })
    await smartDeleteRecord(tableId, row.id)
    loadGrid(view.value?.id)
  }
}
function navDetail(step) {
  const i = detailIdx.value + step
  if (i >= 0 && i < dataRows.value.length) detail.record = dataRows.value[i]
}

// ---------- 字段操作 ----------
const fieldDialog = reactive({ visible: false, field: null })
const allTables = ref([])

function openFieldConfig(f) { fieldDialog.field = f; fieldDialog.visible = true }

const DATA_TYPE_MAP = {
  text: 'varchar', singleSelect: 'varchar', multiSelect: 'json', number: 'decimal', percent: 'decimal',
  currency: 'decimal', date: 'datetime', checkbox: 'bool', url: 'json', phone: 'varchar', email: 'varchar',
  member: 'json', progress: 'decimal', image: 'image', file: 'json', autoNumber: 'serial', relation: 'json',
  lookup: 'json', formula: 'varchar', createdBy: 'varchar', lastModifiedBy: 'varchar',
  createdTime: 'datetime', lastModifiedTime: 'datetime',
}
const WIDGET_MAP = {
  text: 'input', singleSelect: 'select', multiSelect: 'select', number: 'number', percent: 'number',
  currency: 'number', date: 'datetime-picker', checkbox: 'switch', url: 'input', phone: 'input',
  email: 'input', member: 'input', progress: 'number', image: 'image-uploader', file: 'input',
  autoNumber: 'serial', relation: 'input', lookup: 'input', formula: 'input', createdBy: 'input',
  lastModifiedBy: 'input', createdTime: 'datetime-picker', lastModifiedTime: 'datetime-picker',
}

function buildFieldPayload(field_type, label, config) {
  const options = { ...config }
  if (field_type === 'autoNumber') {
    // segments → serial pattern（与后端 autonumber_segments_to_pattern 同规则）
    const pattern = (config.segments || []).map(s => {
      if (s.type === 'autoIncrement') return `{${'0'.repeat(s.digits || 3)}}`
      if (s.type === 'fixedText') return s.text || ''
      return { yyyyMMdd: '{YYYY}{MM}{DD}', 'yyyy-MM-dd': '{YYYY}-{MM}-{DD}', yyyyMM: '{YYYY}{MM}', yyyy: '{YYYY}' }[s.format] || '{YYYY}{MM}{DD}'
    }).join('') || '{000}'
    options.serial = { pattern, reset: 'never', allow_manual: false }
  }
  if (field_type === 'formula') options.formula = config.formula || ''
  return {
    field_name: nextFieldName(), label: label || FIELD_REGISTRY[field_type].label,
    data_type: DATA_TYPE_MAP[field_type], widget: WIDGET_MAP[field_type],
    options, field_type, nullable: true,
  }
}

function nextFieldName() {
  const names = new Set(fields.value.map(f => f.field_name))
  let n = 1
  while (names.has(`f_${n}`)) n++
  return `f_${n}`
}

async function onFieldSave({ label, field_type, config }) {
  if (fieldDialog.field) {
    const f = fieldDialog.field
    const op = { op: 'update_field', field_name: f.field_name, label, options: config, field_type }
    if (f.field_type !== field_type) op.data_type = DATA_TYPE_MAP[field_type]
    await alterTable(tableId, [op])
  } else {
    await alterTable(tableId, [{ op: 'add_field', field: buildFieldPayload(field_type, label, config) }])
  }
  fieldDialog.visible = false
  await reloadMeta()
  loadGrid(view.value?.id)
}

async function reloadMeta() {
  const meta = await getTable(tableId)
  fields.value = meta.fields
  loadRefSources()   // 字段增删改后引用选项/联动源可能变化
}

// 列头菜单
const fieldMenu = reactive({ visible: false, x: 0, y: 0, field: null })
const dirLabels = computed(() => sortDirectionLabels(fieldMenu.field))
function onFieldMenu(field, event) {
  Object.assign(fieldMenu, { visible: true, x: event.clientX, y: event.clientY, field })
}

async function fieldAct(cmd) {
  const f = fieldMenu.field
  fieldMenu.visible = false
  if (cmd === 'edit') openFieldConfig(f)
  else if (cmd === 'filterBy') { activePanel.value = 'filter' }
  else if (cmd === 'sortAsc' || cmd === 'sortDesc') {
    const sorts = (cfg.value.sorts || []).filter(s => s.fieldId !== f.field_name)
    sorts.push({ fieldId: f.field_name, direction: cmd === 'sortDesc' ? 'desc' : 'asc' })
    patchConfig({ sorts })
  } else if (cmd === 'freeze') patchConfig({ frozenFieldId: f.field_name }, { reload: false })
  else if (cmd === 'hide') patchConfig({ fieldVisibility: { ...(cfg.value.fieldVisibility || {}), [f.field_name]: false } }, { reload: false })
  else if (cmd === 'duplicate') { await smartDuplicateField(tableId, f.field_name); reloadMeta(); loadGrid(view.value?.id) }
  else if (cmd === 'delete') await deleteField(f)
}

async function deleteField(f) {
  const { deps } = await smartFieldDeps(tableId, f.field_name)
  const depText = deps.length
    ? `\n该字段被以下视图引用：${deps.map(d => `「${d.viewName}」(${d.usages.join('/')})`).join('、')}，删除后这些配置将失效。`
    : ''
  await ElMessageBox.confirm(`删除字段「${f.label}」？存量数据将一并清除。${depText}`, '删除字段', { type: 'warning' })
  await alterTable(tableId, [{ op: 'delete_field', field_name: f.field_name }])
  reloadMeta()
  loadGrid(view.value?.id)
}

// ---------- 表格设置面板回调 ----------
function onToggleVisible(f, visible) {
  patchConfig({ fieldVisibility: { ...(cfg.value.fieldVisibility || {}), [f.field_name]: !visible ? false : true } }, { reload: false })
}
function onReorder(order) { patchConfig({ fieldOrder: order }, { reload: false }) }
async function onFieldAction(cmd, f) {
  if (cmd === 'edit') openFieldConfig(f)
  else if (cmd === 'delete') deleteField(f)
  else if (cmd === 'duplicate') { await smartDuplicateField(tableId, f.field_name); reloadMeta(); loadGrid(view.value?.id) }
  else if (cmd === 'newGroup') {
    const { value } = await ElMessageBox.prompt('编组名称', '新建编组', { inputValue: '编组' })
    if (value) {
      await smartCreateColumnGroup(tableId, { name: value, field_names: [f.field_name] })
      columnGroups.value = (await smartListColumnGroups(tableId)).groups
    }
  }
}
async function editGroup(g) {
  const { value } = await ElMessageBox.prompt('编组名称', '修改编组', { inputValue: g.name })
  if (value) {
    const { smartUpdateColumnGroup } = await import('../../api/index.js')
    await smartUpdateColumnGroup(g.id, { name: value })
    columnGroups.value = (await smartListColumnGroups(tableId)).groups
  }
}
async function deleteGroup(g) {
  await ElMessageBox.confirm(`解散编组「${g.name}」？字段保留。`, '解散编组', { type: 'warning' })
  await smartDeleteColumnGroup(g.id)
  columnGroups.value = (await smartListColumnGroups(tableId)).groups
}

async function loadFieldsOf(tid) {
  const meta = await getTable(tid)
  return meta.fields
}

function toggleGroup(key) {
  const next = new Set(collapsedGroups.value)
  if (next.has(key)) next.delete(key); else next.add(key)
  collapsedGroups.value = next
}

onMounted(() => {
  loadAll()
  listTables().then(r => { allTables.value = Array.isArray(r) ? r : (r.tables || []) }).catch(() => {})
  window.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onDocClick)
  document.addEventListener('contextmenu', onDocClick)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('contextmenu', onDocClick)
})
</script>

<style scoped>
.st-page { display: flex; flex-direction: column; height: 100%; background: #fff; }
.toolbar { display: flex; align-items: center; gap: 4px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
.tb-right { margin-left: auto; display: flex; align-items: center; gap: 6px; }
.chip { background: var(--el-fill-color-light); border-radius: 12px; padding: 3px 10px; font-size: 12px; cursor: pointer; }
.chip:hover { background: var(--el-fill-color); }
.chip-edit { display: flex; gap: 8px; align-items: center; }
.batch-bar { display: flex; align-items: center; gap: 12px; padding: 6px 12px; background: var(--el-color-primary-light-9); font-size: 13px; }
.pager { padding: 8px; display: flex; justify-content: center; }
.fm-mask { position: fixed; inset: 0; z-index: 3000; }
.fm { position: fixed; background: #fff; border-radius: 8px; box-shadow: var(--el-box-shadow); padding: 4px; min-width: 170px; }
.mi { padding: 6px 12px; font-size: 13px; border-radius: 4px; cursor: pointer; white-space: nowrap; }
.mi:hover { background: var(--el-fill-color-light); }
.mi.danger { color: var(--el-color-danger); }
</style>
