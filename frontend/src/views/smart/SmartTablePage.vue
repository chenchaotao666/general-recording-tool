<template>
  <div class="st-page">
    <!-- 视图页签 -->
    <ViewTabs :views="views" :current-id="view?.id" @switch="switchView" @action="onViewAction" />

    <!-- 工具栏（对齐参照 上方Tab页签.png：添加一行=蓝字圆⊕；条件按钮生效时浅蓝胶囊+计数） -->
    <div class="toolbar">
      <button class="tb-btn tb-add" :disabled="!perms.can_create" @click="addRow">
        <StIcon name="plus-circle" :size="15" />添加一行
      </button>
      <span class="tb-sep" />
      <button class="tb-btn" @click="settingsVisible = true"><StIcon name="table" :size="15" />表格设置</button>

      <FilterPanel :visible="activePanel === 'filter'" @update:visible="(v) => (activePanel = v ? 'filter' : (activePanel === 'filter' ? null : activePanel))" :fields="resolvedFields"
                   :conditions="panelConditions" :conjunction="cfg.filters?.conjunction || 'and'" :scope="filterScope"
                   @change="onFiltersChange" @scope-change="onScopeChange">
        <button class="tb-btn" :class="{ on: filterCount }">
          <StIcon name="filter" :size="15" />筛选{{ filterCount ? ` ${filterCount}` : '' }}
        </button>
      </FilterPanel>

      <GroupPanel :visible="activePanel === 'group'" @update:visible="(v) => (activePanel = v ? 'group' : (activePanel === 'group' ? null : activePanel))" :fields="fields" :groups="cfg.groups || []"
                  @change="(v) => patchConfig({ groups: v })">
        <button class="tb-btn" :class="{ on: (cfg.groups || []).length }">
          <StIcon name="group" :size="15" />分组{{ (cfg.groups || []).length ? ` ${cfg.groups.length}` : '' }}
        </button>
      </GroupPanel>

      <SortPanel :visible="activePanel === 'sort'" @update:visible="(v) => (activePanel = v ? 'sort' : (activePanel === 'sort' ? null : activePanel))" :fields="fields" :sorts="cfg.sorts || []"
                 :auto-sort="cfg.autoSort !== false"
                 @change="(v) => patchConfig({ sorts: v })" @auto-sort="(v) => patchConfig({ autoSort: v })">
        <button class="tb-btn" :class="{ on: (cfg.sorts || []).length }">
          <StIcon name="sort" :size="15" />排序{{ (cfg.sorts || []).length ? ` ${cfg.sorts.length}` : '' }}
        </button>
      </SortPanel>

      <el-dropdown trigger="click" @command="(v) => patchConfig({ rowHeight: v })">
        <button class="tb-btn" @click.stop><StIcon name="row-height" :size="15" />行高</button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="(l, k) in ROW_HEIGHTS" :key="k" :command="k">
              <span :style="{ color: cfg.rowHeight === k || (!cfg.rowHeight && k === 'default') ? 'var(--st-primary)' : '' }">
                {{ cfg.rowHeight === k || (!cfg.rowHeight && k === 'default') ? '✓ ' : '' }}{{ l }}
              </span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <FillPanel :visible="activePanel === 'fill'" @update:visible="(v) => (activePanel = v ? 'fill' : (activePanel === 'fill' ? null : activePanel))" :fields="resolvedFields" :rules="cfg.fillRules || []"
                 @change="(v) => patchConfig({ fillRules: v })">
        <button class="tb-btn" :class="{ on: fillCount }">
          <StIcon name="fill" :size="15" />填色{{ fillCount ? ` ${fillCount}` : '' }}
        </button>
      </FillPanel>

      <div class="tb-right">
        <!-- 条件胶囊（pin 的筛选条件）：点击弹单字段筛选浮层（运算符+勾选清单，与列头「筛选」同款） -->
        <el-popover v-for="c in pinnedConditions" :key="c.id" trigger="click" placement="bottom-start" :width="300" popper-class="st-pop">
          <template #reference>
            <span class="chip"><StIcon name="filter" :size="12" />{{ labelOf(c.fieldId) }}<StIcon name="chevron-down" :size="12" /></span>
          </template>
          <FieldFilterPop v-if="fieldOfName(c.fieldId)" :field="fieldOfName(c.fieldId)" :condition="c"
                          :scope-text="filterScope === 'personal' ? '调整仅你可见' : '对所有人生效'"
                          @change="(cond) => applyFieldCondition(c.fieldId, cond)" />
        </el-popover>
        <button class="tb-ico" title="撤销" :disabled="!undoStack.canUndo" @click="doUndo"><StIcon name="undo" :size="16" /></button>
        <button class="tb-ico" title="重做" :disabled="!undoStack.canRedo" @click="doRedo"><StIcon name="redo" :size="16" /></button>
        <button class="tb-ico" title="查找替换" @click="findVisible = true"><StIcon name="search" :size="16" /></button>
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
      @add-field="onAddFieldAt" @add-option="onAddOption" @footer-menu="onFooterMenu"
      @group-menu="onGroupMenu" @add-row-in-group="addRowInGroup"
    />

    <!-- 分页（未分组时） -->
    <div v-if="!grouped && total > pageSize" class="pager">
      <el-pagination layout="prev, pager, next, total" :total="total" :page-size="pageSize"
                     :current-page="page" @current-change="(p) => { page = p; loadGrid() }" />
    </div>

    <!-- 面板与弹窗 -->
    <TableSettingsPanel :visible="settingsVisible" @update:visible="(v) => (settingsVisible = v)" :fields="fields" :view="view" :column-groups="columnGroups"
                        @close="settingsVisible = false" @toggle-visible="onToggleVisible" @reorder="onReorder"
                        @field-action="onFieldAction" @add-field="onAddFieldAt" @set-field-group="setFieldGroup" />
    <FieldConfigDialog :visible="fieldDialog.visible" :field="fieldDialog.field" :preset="fieldDialog.preset" :fields="fields"
                       :tables="allTables" :source-fields-of="loadFieldsOf"
                       @close="fieldDialog.visible = false" @save="onFieldSave" />
    <RecordDetailDrawer :visible="detail.visible" @update:visible="(v) => (detail.visible = v)" :record="detail.record" :fields="resolvedFields"
                        :column-groups="columnGroups"
                        :has-prev="detailIdx > 0" :has-next="detailIdx < dataRows.length - 1"
                        @close="detail.visible = false" @nav="navDetail" @cell-commit="onCellCommit" />
    <FindReplaceDialog :visible="findVisible" :table-id="tableId"
                       @close="findVisible = false" @replaced="loadGrid" />

    <!-- 新建/修改编组弹窗（设计文档 §6.1：编组名称 + 包含字段，默认含当前列） -->
    <el-dialog :model-value="groupDialog.visible" :title="groupDialog.id ? '修改编组' : '新建编组'"
               width="420px" @close="groupDialog.visible = false">
      <div class="gd-form">
        <el-input v-model="groupDialog.name" placeholder="编组名称" maxlength="100" />
        <el-select v-model="groupDialog.members" multiple placeholder="包含字段" style="width: 100%">
          <el-option v-for="f in fields" :key="f.field_name" :value="f.field_name" :label="f.label" />
        </el-select>
      </div>
      <template #footer>
        <el-button size="small" @click="groupDialog.visible = false">取消</el-button>
        <el-button size="small" type="primary" @click="saveGroupDialog">确定</el-button>
      </template>
    </el-dialog>

    <!-- 字段列头菜单 -->
    <teleport to="body">
      <div v-if="fieldMenu.visible" class="fm-mask" @click="fieldMenu.visible = false"
           @contextmenu.prevent="fieldMenu.visible = false">
        <div class="fm" :style="{ left: `${fieldMenu.x}px`, top: `${fieldMenu.y}px` }" @click.stop>
          <div class="mi" @click="fieldAct('edit')"><StIcon name="pencil" :size="15" />修改字段</div>
          <div class="mi has-sub">
            <StIcon name="move-into" :size="15" />插入字段 <span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span>
            <div class="fm-sub">
              <div class="mi" @click="fieldAct('insertLeft')">← 向左插入</div>
              <div class="mi" @click="fieldAct('insertRight')">→ 向右插入</div>
            </div>
          </div>
          <div class="fm-divider" />
          <div class="mi" @click="fieldAct('filterBy')"><StIcon name="filter" :size="15" />筛选</div>
          <div class="mi" @click="fieldAct('toggleGroupBy')"><StIcon name="group" :size="15" />{{ isMenuFieldGrouped ? '取消分组' : '分组' }}</div>
          <div class="mi has-sub">
            <StIcon name="sort" :size="15" />排序
            <span class="mi-tail">{{ menuSortInline }}<span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span></span>
            <div class="fm-sub">
              <div class="mi" @click="fieldAct('sortAsc')"><span class="sub-check">{{ menuSortDir === 'asc' ? '✓' : '' }}</span>{{ dirLabels[0] }}</div>
              <div class="mi" @click="fieldAct('sortDesc')"><span class="sub-check">{{ menuSortDir === 'desc' ? '✓' : '' }}</span>{{ dirLabels[1] }}</div>
            </div>
          </div>
          <!-- 整列填色 ▸（设计稿 PixPin_2026-10-16_00-14-52）：创建整列规则并打开填色面板选色 -->
          <div class="mi has-sub">
            <StIcon name="fill" :size="15" />整列填色 <span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span>
            <div class="fm-sub">
              <div class="mi" @click="columnFill('all')">为所有内容填色</div>
              <div class="mi" @click="columnFill('header')">为字段名称填色</div>
            </div>
          </div>
          <div class="fm-divider" />
          <div class="mi" @click="openGroupDialog(fieldMenu.field)"><StIcon name="colgroup" :size="15" />新建编组</div>
          <!-- 移入编组 ▸（设计文档 §6.1：存在编组时出现；已在组内的项点击为移出） -->
          <div v-if="columnGroups.length" class="mi has-sub">
            <StIcon name="move-into" :size="15" />移入编组 <span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span>
            <div class="fm-sub">
              <div v-for="g in columnGroups" :key="g.id" class="mi" @click="moveToGroup(g)">
                <span class="sub-check">{{ g.field_names?.includes(fieldMenu.field?.field_name) ? '✓' : '' }}</span>{{ g.name }}
              </div>
            </div>
          </div>
          <!-- 底部图标快捷栏（对齐参照 表头-工具栏.png：副本/列宽/冻结/隐藏/删除，黑底 tooltip） -->
          <div class="fm-bar">
            <el-tooltip content="创建副本" placement="top" :show-after="150">
              <span class="fb-item" @click="fieldAct('duplicate')"><StIcon name="copy" :size="16" /></span>
            </el-tooltip>
            <el-tooltip content="自动调整列宽" placement="top" :show-after="150">
              <span class="fb-item" @click="fieldAct('autoFit')"><StIcon name="autofit" :size="16" /></span>
            </el-tooltip>
            <el-tooltip content="冻结至此列" placement="top" :show-after="150">
              <span class="fb-item" @click="fieldAct('freeze')"><StIcon name="freeze" :size="16" /></span>
            </el-tooltip>
            <el-tooltip content="隐藏" placement="top" :show-after="150">
              <span class="fb-item" @click="fieldAct('hide')"><StIcon name="eye-off" :size="16" /></span>
            </el-tooltip>
            <el-tooltip content="删除" placement="top" :show-after="150">
              <span class="fb-item" @click="fieldAct('delete')"><StIcon name="trash" :size="16" /></span>
            </el-tooltip>
          </div>
        </div>
      </div>
    </teleport>

    <!-- 编组组头菜单（设计稿 PixPin_2026-10-16_00-40-59） -->
    <teleport to="body">
      <div v-if="groupMenu.visible" class="fm-mask" @click="groupMenu.visible = false"
           @contextmenu.prevent="groupMenu.visible = false">
        <div class="fm" :style="{ left: `${groupMenu.x}px`, top: `${groupMenu.y}px` }" @click.stop>
          <div class="mi" @click="groupAct('edit')"><StIcon name="pencil" :size="15" />修改编组</div>
          <div class="mi has-sub">
            <StIcon name="move-into" :size="15" />插入字段 <span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span>
            <div class="fm-sub">
              <div class="mi" @click="groupAct('insertRight')">→ 向右插入</div>
              <div class="mi" @click="groupAct('insertLeft')">← 向左插入</div>
              <div class="mi" @click="groupAct('insertInside')">在编组内插入</div>
            </div>
          </div>
          <div class="mi" @click="groupAct('duplicate')"><StIcon name="copy" :size="15" />创建副本</div>
          <div class="mi" @click="groupAct('freeze')"><StIcon name="freeze" :size="15" />冻结至此编组</div>
          <div class="mi" @click="groupAct('autoFit')"><StIcon name="autofit" :size="15" />自动调整列宽</div>
          <div class="mi" @click="groupAct('hide')"><StIcon name="eye-off" :size="15" />隐藏</div>
          <div class="mi danger" @click="groupAct('dissolve')">解散编组</div>
        </div>
      </div>
    </teleport>

    <!-- 统计行设置菜单（点击 footer 单元格弹出，向上展开） -->
    <teleport to="body">
      <div v-if="statMenu.visible" class="fm-mask" @click="statMenu.visible = false"
           @contextmenu.prevent="statMenu.visible = false">
        <div class="fm stat-fm" :style="{ left: `${statMenu.x}px`, top: `${statMenu.y}px` }" @click.stop>
          <div v-for="o in statOptions" :key="o.key" class="mi stat-mi" @click="statAct(o.key)">
            <span class="sm-check">{{ statCurrent === o.key ? '✓' : '' }}</span>
            <span class="sm-label">{{ o.label }}</span>
            <span class="sm-val">{{ o.value }}</span>
          </div>
          <div v-if="statCurrent" class="mi stat-mi" @click="statAct(null)">
            <span class="sm-check" /><span class="sm-label">不展示</span>
          </div>
          <div class="fm-divider" />
          <div class="mi" @click="copyStats"><StIcon name="copy" :size="15" />复制数据统计</div>
        </div>
      </div>
    </teleport>
    <!-- 添加列类型网格浮层（表格末尾「+」/设置面板「新增字段」统一入口） -->
    <teleport to="body">
      <AddFieldPop v-if="addFieldPop.visible" :x="addFieldPop.x" :y="addFieldPop.y"
                   @pick="(p) => onTypePick(p, false)" @pick-again="(p) => onTypePick(p, true)"
                   @close="addFieldPop.visible = false" />
    </teleport>

    <!-- 列头「筛选」：贴列头的单字段筛选浮层 -->
    <teleport to="body">
      <div v-if="fieldFilter.visible" class="fm-mask" @click="fieldFilter.visible = false"
           @contextmenu.prevent="fieldFilter.visible = false">
        <div class="fm ffp-wrap" :style="{ left: `${fieldFilter.x}px`, top: `${fieldFilter.y}px` }" @click.stop>
          <FieldFilterPop v-if="fieldFilter.field" :field="fieldFilter.field"
                          :condition="panelConditions.find(c => c.fieldId === fieldFilter.field?.field_name) || null"
                          :scope-text="filterScope === 'personal' ? '调整仅你可见' : '对所有人生效'"
                          @change="(cond) => applyFieldCondition(fieldFilter.field.field_name, cond)" />
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
import StIcon from '../../components/smart/icons/StIcon.vue'
import ViewTabs from '../../components/smart/ViewTabs.vue'
import FilterPanel from '../../components/smart/panels/FilterPanel.vue'
import SortPanel from '../../components/smart/panels/SortPanel.vue'
import GroupPanel from '../../components/smart/panels/GroupPanel.vue'
import FillPanel from '../../components/smart/panels/FillPanel.vue'
import TableSettingsPanel from '../../components/smart/panels/TableSettingsPanel.vue'
import FieldConfigDialog from '../../components/smart/panels/FieldConfigDialog.vue'
import FieldFilterPop from '../../components/smart/panels/FieldFilterPop.vue'
import AddFieldPop from '../../components/smart/panels/AddFieldPop.vue'
import RecordDetailDrawer from '../../components/smart/panels/RecordDetailDrawer.vue'
import FindReplaceDialog from '../../components/smart/panels/FindReplaceDialog.vue'
import { FIELD_REGISTRY, filterOpsOf, OP_LABELS, OPTION_COLORS, sortDirectionLabels,
         footerStatsOf, STAT_LABELS, formatStatValue } from '../../smart/registry/fieldRegistry.js'
import { isRuleComplete, createUndoStack } from '../../smart/utils/format.js'
import { resolveRefOptions } from '../../smart/utils/refOptions.js'
import {
  alterTable, getTable, listMembers, listTables,
  smartGrid, smartListViews, smartCreateView, smartUpdateView, smartDeleteView,
  smartDuplicateView, smartSetDefaultView, smartPutViewPref, smartDeleteViewPref,
  smartCreateRecord, smartUpdateRecord, smartDeleteRecord, smartBatchDelete,
  smartDuplicateRecord, smartDuplicateField, smartFieldDeps, smartFieldStats,
  smartListColumnGroups, smartCreateColumnGroup, smartUpdateColumnGroup, smartDeleteColumnGroup,
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
const dataRows = computed(() => rows.value.filter(r => r.__rowType !== 'group'))
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
  // 点击目标在本次事件处理中已被移出 DOM（如点面板里的"删除行"先删了自身所在行），
  // detached 节点 closest 必为 null，不能算作外点
  if (!document.contains(e.target)) return
  if (e.target.closest('.el-popover') || e.target.closest('.toolbar')) return
  activePanel.value = null
}

// ---------- 筛选（含个人覆盖） ----------
function onFiltersChange(conditions, conjunction = 'and') {
  const filters = { conjunction, conditions }
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
function fieldOfName(fn) { return resolvedFields.value.find(f => f.field_name === fn) }
// 单字段筛选浮层（pin 胶囊 / 列头「筛选」共用）：upsert 或移除该字段的条件，其余条件不动
function applyFieldCondition(fieldName, cond) {
  const conds = panelConditions.value.filter(c => c.fieldId !== fieldName)
  if (cond) {
    const existing = panelConditions.value.find(c => c.fieldId === fieldName)
    conds.push({ ...cond, id: existing?.id || `c_${Date.now()}`, pinned: existing?.pinned || false })
  }
  onFiltersChange(conds, cfg.value.filters?.conjunction || 'and')
}
function updateChip(c, patch) {
  onFiltersChange(panelConditions.value.map(x => (x.id === c.id ? { ...x, ...patch } : x)), cfg.value.filters?.conjunction || 'and')
}
function removeChip(c) { onFiltersChange(panelConditions.value.filter(x => x.id !== c.id), cfg.value.filters?.conjunction || 'and') }

// ---------- 记录操作 ----------
// 值比较：null/''/undefined/空数组等价（都视为"空"）；数组按集合比较（多选顺序无语义）；
// 数字与数字字符串等价（存量可能是文本，编辑器提交的是 number）
function sameCellValue(a, b) {
  const isEmpty = (v) => v == null || v === '' || (Array.isArray(v) && !v.length)
  if (isEmpty(a) && isEmpty(b)) return true
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
    const sa = a.map(String).sort(), sb = b.map(String).sort()
    return sa.every((x, i) => x === sb[i])
  }
  if (a && b && typeof a === 'object' && typeof b === 'object') return JSON.stringify(a) === JSON.stringify(b)
  return String(a ?? '') === String(b ?? '')
}

// 该字段的改动是否影响当前视图的服务端结果（排序/筛选/分组/聚合），决定提交后要不要整表重查。
// 填色规则在前端渲染层即时计算（evalFillRules 随乐观更新生效），不需要重查。
function fieldAffectsView(field) {
  const c = cfg.value
  const name = field.field_name
  return (c.autoSort !== false && (c.sorts || []).some(s => s.fieldId === name))
    || (c.filters?.conditions || []).some(x => x.fieldId === name)
    || (c.groups || []).some(g => g.fieldId === name)
    || aggregations.value[name] != null   // 汇总行/分组求和展示了该字段，编辑后数值会过期
}

async function onCellCommit({ row, field, value }) {
  const old = row[field.field_name]
  if (sameCellValue(old, value)) return   // 未修改：不写库、不刷新
  row[field.field_name] = value   // 乐观更新
  try {
    const r = await smartUpdateRecord(tableId, row.id, { data: { [field.field_name]: value } })
    Object.assign(row, r.record)
    undoStack.push({
      label: `编辑 ${field.label}`,
      undo: async () => { await smartUpdateRecord(tableId, row.id, { data: { [field.field_name]: old } }); loadGrid(view.value?.id) },
      redo: async () => { await smartUpdateRecord(tableId, row.id, { data: { [field.field_name]: value } }); loadGrid(view.value?.id) },
    })
    // 只在改动影响排序/筛选/分组/聚合结果时重查；否则乐观更新即可（公式/查找由 PATCH 响应带回）
    if (field.field_type !== 'checkbox' && fieldAffectsView(field)) loadGrid(view.value?.id)
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

async function addRow(preset = {}) {
  const r = await smartCreateRecord(tableId, { data: preset })
  undoStack.push({
    label: '添加行',
    undo: async () => { await smartDeleteRecord(tableId, r.record.id); loadGrid(view.value?.id) },
    redo: async () => { await smartCreateRecord(tableId, { data: preset }); loadGrid(view.value?.id) },
  })
  ElMessage.success('已添加一行')
  loadGrid(view.value?.id)
}

// 组内「+」行：带上该组全部分组条件的预设值（多级分组逐层下发）
function addRowInGroup(groupConds) {
  const preset = {}
  for (const gc of groupConds || []) {
    if (gc.fieldId && gc.value != null && gc.value !== '') preset[gc.fieldId] = gc.value
  }
  addRow(preset)
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
const fieldDialog = reactive({ visible: false, field: null, insertCtx: null, preset: null, addAgain: false })
const allTables = ref([])

function openFieldConfig(f, insertCtx = null) {
  fieldDialog.field = f
  fieldDialog.insertCtx = insertCtx
  fieldDialog.preset = null
  fieldDialog.addAgain = false
  fieldDialog.visible = true
}

// 添加列类型网格浮层（AddFieldPop）：表格末尾「+」/表格设置「新增字段」/列头「插入字段」之外的统一入口
const addFieldPop = reactive({ visible: false, x: 0, y: 0 })
const lastAddFieldPos = { x: 200, y: 100 }
function openAddFieldPop(x, y) {
  Object.assign(addFieldPop, { visible: true, x, y })
  lastAddFieldPos.x = x; lastAddFieldPos.y = y
}
function onAddFieldAt(e) {
  // 事件可能来自网格表头（MouseEvent）或设置面板（同样透传 MouseEvent）
  const x = e?.clientX ?? window.innerWidth - 520
  const y = e?.clientY ?? 120
  openAddFieldPop(x, y)
}
function onTypePick({ field_type, label }, again = false) {
  addFieldPop.visible = false
  fieldDialog.field = null
  fieldDialog.insertCtx = null
  fieldDialog.preset = { field_type, label }
  fieldDialog.addAgain = again
  fieldDialog.visible = true
}

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
    fieldDialog.visible = false
    await reloadMeta()
    loadGrid(view.value?.id)
  } else {
    const payload = buildFieldPayload(field_type, label, config)
    await alterTable(tableId, [{ op: 'add_field', field: payload }])
    fieldDialog.visible = false
    await reloadMeta()
    // 插入上下文定位（编组菜单/列头菜单「插入字段」；AddFieldPop 无上下文保持末尾）
    if (fieldDialog.insertCtx) await placeNewField(payload.field_name, fieldDialog.insertCtx)
    loadGrid(view.value?.id)
    // AddFieldPop 的「Tab 再添加一列」：保存完成后重新打开类型网格
    if (fieldDialog.addAgain) { fieldDialog.addAgain = false; openAddFieldPop(lastAddFieldPos.x, lastAddFieldPos.y) }
  }
}

async function reloadMeta() {
  const meta = await getTable(tableId)
  fields.value = meta.fields
  loadRefSources()   // 字段增删改后引用选项/联动源可能变化
}

// 列头菜单
const fieldMenu = reactive({ visible: false, x: 0, y: 0, field: null })
const dirLabels = computed(() => sortDirectionLabels(fieldMenu.field))
// 动态项：该列是否已是分组字段（分组/取消分组切换）；排序项内联显示当前方向
const isMenuFieldGrouped = computed(() =>
  !!fieldMenu.field && (cfg.value.groups || []).some(g => g.fieldId === fieldMenu.field.field_name))
const menuSortDir = computed(() =>
  (cfg.value.sorts || []).find(s => s.fieldId === fieldMenu.field?.field_name)?.direction || null)
const menuSortInline = computed(() => menuSortDir.value ? dirLabels.value[menuSortDir.value === 'desc' ? 1 : 0] : '')
function onFieldMenu(field, event) {
  Object.assign(fieldMenu, { visible: true, x: event.clientX, y: event.clientY, field })
}

// 列头「筛选」：贴列头的单字段筛选浮层（与 pin 胶囊共用 FieldFilterPop）
const fieldFilter = reactive({ visible: false, x: 0, y: 0, field: null })
function openFieldFilter(field, x, y) {
  fieldMenu.visible = false
  Object.assign(fieldFilter, { visible: true, field,
    x: Math.min(x, window.innerWidth - 320), y: Math.min(y, window.innerHeight - 360) })
}

// 整列填色：为「所有内容 / 字段名称」创建整列规则（无运算符），并打开填色面板选色
function columnFill(target) {
  const f = fieldMenu.field
  if (!f) return
  fieldMenu.visible = false
  const rules = [...(cfg.value.fillRules || [])]
  if (!rules.some(r => r.fieldId === f.field_name && r.fillTarget === target)) {
    rules.push({
      id: `f_${Date.now()}`, fieldId: f.field_name, fillTarget: target,
      color: target === 'header' ? '#e8f0fe' : '#feefe3', wholeRow: false, order: rules.length,
    })
    patchConfig({ fillRules: rules })
  }
  activePanel.value = 'fill'
}

async function fieldAct(cmd) {
  const f = fieldMenu.field
  if (!f) return
  if (cmd === 'edit') { fieldMenu.visible = false; openFieldConfig(f) }
  else if (cmd === 'filterBy') openFieldFilter(f, fieldMenu.x, fieldMenu.y)
  else if (cmd === 'insertLeft' || cmd === 'insertRight') {
    fieldMenu.visible = false
    openFieldConfig(null, { mode: cmd === 'insertLeft' ? 'left' : 'right', field: f })
  }
  else if (cmd === 'toggleGroupBy') {
    fieldMenu.visible = false
    const groups = (cfg.value.groups || []).filter(g => g.fieldId)
    if (isMenuFieldGrouped.value) patchConfig({ groups: groups.filter(g => g.fieldId !== f.field_name) })
    else patchConfig({ groups: [...groups, { fieldId: f.field_name, direction: 'asc' }] })
  }
  else if (cmd === 'sortAsc' || cmd === 'sortDesc') {
    fieldMenu.visible = false
    const sorts = (cfg.value.sorts || []).filter(s => s.fieldId !== f.field_name)
    sorts.push({ fieldId: f.field_name, direction: cmd === 'sortDesc' ? 'desc' : 'asc' })
    patchConfig({ sorts })
  } else if (cmd === 'freeze') { fieldMenu.visible = false; patchConfig({ frozenFieldId: f.field_name }, { reload: false }) }
  else if (cmd === 'hide') { fieldMenu.visible = false; patchConfig({ fieldVisibility: { ...(cfg.value.fieldVisibility || {}), [f.field_name]: false } }, { reload: false }) }
  else if (cmd === 'autoFit') { fieldMenu.visible = false; autoFitFields([f.field_name]) }
  else if (cmd === 'duplicate') { fieldMenu.visible = false; await smartDuplicateField(tableId, f.field_name); reloadMeta(); loadGrid(view.value?.id) }
  else if (cmd === 'delete') { fieldMenu.visible = false; await deleteField(f) }
}

// ---------- 统计行：按列设置统计方式 ----------
const statMenu = reactive({ visible: false, x: 0, y: 0, field: null, stats: {} })
const statCurrent = computed(() => (statMenu.field && cfg.value.aggregations?.[statMenu.field.field_name]) || null)
const statOptions = computed(() => footerStatsOf(statMenu.field).map(k => ({
  key: k, label: STAT_LABELS[k],
  value: statMenu.stats[k] != null ? formatStatValue(k, statMenu.stats[k], statMenu.field) : '',
})))

function onFooterMenu(field, e) {
  // 菜单从点击处向上展开（footer 在视口底部）；高度按选项数估算
  const estH = footerStatsOf(field).length * 30 + 80
  Object.assign(statMenu, {
    visible: true, field, stats: {},
    x: Math.min(e.clientX, window.innerWidth - 200),
    y: Math.max(8, e.clientY - estH),
  })
  // 各统计方式的值异步拉取（服务端按筛选后全集计算），到位后填入菜单
  smartFieldStats(tableId, { field_name: field.field_name, view_id: view.value?.id })
    .then(r => { if (statMenu.visible && statMenu.field === field) statMenu.stats = r.stats || {} })
    .catch(() => {})
}

function statAct(key) {
  const fn = statMenu.field?.field_name
  if (!fn) return
  const aggs = { ...(cfg.value.aggregations || {}) }
  if (key) aggs[fn] = key
  else delete aggs[fn]
  statMenu.visible = false
  patchConfig({ aggregations: aggs })
}

async function copyStats() {
  const lines = statOptions.value.filter(o => o.value !== '').map(o => `${o.label}: ${o.value}`)
  if (!lines.length) { statMenu.visible = false; return }
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
  } catch {
    const ta = document.createElement('textarea')
    ta.value = lines.join('\n')
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  ElMessage.success('已复制数据统计')
  statMenu.visible = false
}

// ---------- 列编组（设计文档 §6.3：新建/修改弹窗 + 移入移出；字段最多属于一个编组） ----------
const groupDialog = reactive({ visible: false, id: null, name: '', members: [] })
function openGroupDialog(field, group = null) {
  fieldMenu.visible = false
  Object.assign(groupDialog, group
    ? { visible: true, id: group.id, name: group.name, members: [...(group.field_names || [])] }
    : { visible: true, id: null, name: '', members: field ? [field.field_name] : [] })
}
async function saveGroupDialog() {
  const members = groupDialog.members
  if (!members.length) { ElMessage.warning('请选择包含字段'); return }
  // 字段最多属于一个编组：先把这些字段从其他编组移除
  for (const g of columnGroups.value) {
    if (g.id === groupDialog.id) continue
    const rest = (g.field_names || []).filter(n => !members.includes(n))
    if (rest.length !== (g.field_names || []).length) {
      await smartUpdateColumnGroup(g.id, { field_names: rest })
    }
  }
  if (groupDialog.id) await smartUpdateColumnGroup(groupDialog.id, { name: groupDialog.name, field_names: members })
  else await smartCreateColumnGroup(tableId, { name: groupDialog.name || '编组', field_names: members })
  groupDialog.visible = false
  columnGroups.value = (await smartListColumnGroups(tableId)).groups
}

// 字段编组归属变更：targetGroup 为 null = 移出所有编组；否则移入目标组（字段最多属于一个编组）。
// 组的最后成员被移出时直接解散该组（"拖出去那就没编组了"）
async function setFieldGroup(fieldName, targetGroup) {
  for (const g of columnGroups.value) {
    if ((g.field_names || []).includes(fieldName) && g.id !== targetGroup?.id) {
      const rest = g.field_names.filter(n => n !== fieldName)
      if (rest.length) await smartUpdateColumnGroup(g.id, { field_names: rest })
      else await smartDeleteColumnGroup(g.id)
    }
  }
  if (targetGroup && !(targetGroup.field_names || []).includes(fieldName)) {
    await smartUpdateColumnGroup(targetGroup.id, { field_names: [...(targetGroup.field_names || []), fieldName] })
  }
  columnGroups.value = (await smartListColumnGroups(tableId)).groups
}

// 列头菜单「移入编组 ▸」：切换语义（已在该组则移出）
async function moveToGroup(g) {
  const f = fieldMenu.field
  if (!f) return
  fieldMenu.visible = false
  await setFieldGroup(f.field_name, (g.field_names || []).includes(f.field_name) ? null : g)
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
  else if (cmd === 'newGroup') openGroupDialog(f)
}

// ---------- 编组组头菜单（设计稿 PixPin_2026-10-16_00-40-59） ----------
const groupMenu = reactive({ visible: false, x: 0, y: 0, group: null })
function onGroupMenu(group, e) {
  Object.assign(groupMenu, { visible: true, x: e.clientX, y: e.clientY, group })
}

async function groupAct(cmd) {
  const g = groupMenu.group
  groupMenu.visible = false
  if (!g) return
  const members = g.field_names || []
  if (cmd === 'edit') openGroupDialog(null, g)
  else if (cmd === 'insertRight' || cmd === 'insertLeft' || cmd === 'insertInside') {
    openFieldConfig(null, { mode: { insertRight: 'right', insertLeft: 'left', insertInside: 'inside' }[cmd], group: g })
  } else if (cmd === 'duplicate') await duplicateGroup(g)
  else if (cmd === 'freeze') patchConfig({ frozenFieldId: members[members.length - 1] }, { reload: false })
  else if (cmd === 'autoFit') autoFitGroup(g)
  else if (cmd === 'hide') {
    const vis = { ...(cfg.value.fieldVisibility || {}) }
    members.forEach(n => { vis[n] = false })
    patchConfig({ fieldVisibility: vis }, { reload: false })
  } else if (cmd === 'dissolve') {
    await ElMessageBox.confirm(`解散编组「${g.name}」？字段保留。`, '解散编组', { type: 'warning' })
    await smartDeleteColumnGroup(g.id)
    columnGroups.value = (await smartListColumnGroups(tableId)).groups
  }
}

// 插入字段创建后的定位：ctx.group → left=首成员前 / right=末成员后 / inside=加入编组并排末位；
// ctx.field（列头菜单「插入字段」）→ 该字段前/后
async function placeNewField(newName, ctx) {
  const base = cfg.value.fieldOrder?.length ? [...cfg.value.fieldOrder] : fields.value.map(f => f.field_name)
  const order = base.filter(n => n !== newName)
  if (!ctx.group) {
    let idx = ctx.field ? order.indexOf(ctx.field.field_name) : -1
    if (idx < 0) idx = order.length
    else if (ctx.mode !== 'left') idx += 1
    order.splice(idx, 0, newName)
    patchConfig({ fieldOrder: order }, { reload: false })
    return
  }
  const g = ctx.group
  const members = g.field_names || []
  let anchor
  if (ctx.mode === 'inside') {
    await smartUpdateColumnGroup(g.id, { field_names: [...members, newName] })
    columnGroups.value = (await smartListColumnGroups(tableId)).groups
    anchor = members[members.length - 1]
  } else {
    anchor = ctx.mode === 'left' ? members[0] : members[members.length - 1]
  }
  let idx = anchor ? order.indexOf(anchor) : -1
  if (idx < 0) idx = order.length
  else if (ctx.mode !== 'left') idx += 1
  order.splice(idx, 0, newName)
  patchConfig({ fieldOrder: order }, { reload: false })
}

// 创建副本：逐成员复制字段（名称加「副本」），新编组「名称 副本」排在原组之后
async function duplicateGroup(g) {
  const newNames = []
  for (const fn of g.field_names || []) {
    const r = await smartDuplicateField(tableId, fn)
    newNames.push(r.field_name)
  }
  await reloadMeta()
  await smartCreateColumnGroup(tableId, { name: `${g.name} 副本`, field_names: newNames })
  columnGroups.value = (await smartListColumnGroups(tableId)).groups
  const base = cfg.value.fieldOrder?.length ? [...cfg.value.fieldOrder] : fields.value.map(f => f.field_name)
  const order = base.filter(n => !newNames.includes(n))
  const last = (g.field_names || [])[(g.field_names || []).length - 1]
  let idx = last ? order.indexOf(last) : -1
  order.splice((idx < 0 ? order.length : idx) + 1, 0, ...newNames)
  patchConfig({ fieldOrder: order }, { reload: false })
  loadGrid(view.value?.id)
}

// 自动调整列宽：按表头与内容文本宽度估算（canvas 测量，80–400px）；编组菜单与列头菜单共用
function autoFitFields(names) {
  const ctx = document.createElement('canvas').getContext('2d')
  ctx.font = '13px "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif'
  const widths = { ...(cfg.value.colWidths || {}) }
  for (const fn of names) {
    const f = fields.value.find(x => x.field_name === fn)
    if (!f) continue
    let w = ctx.measureText(f.label).width + 56   // 图标/排序标/▾/内边距
    for (const r of dataRows.value.slice(0, 200)) {
      const v = r[fn]
      const text = v == null ? '' : (Array.isArray(v) ? v.join('、') : String(v))
      w = Math.max(w, ctx.measureText(text).width + 24)
    }
    widths[fn] = Math.round(Math.min(Math.max(w, 80), 400))
  }
  patchConfig({ colWidths: widths }, { reload: false })
}
function autoFitGroup(g) { autoFitFields(g.field_names || []) }

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
.toolbar { display: flex; align-items: center; gap: 2px; padding: 6px 12px; border-bottom: 1px solid var(--st-border); }
/* 幽灵按钮（对齐参照）：图标+文字 13px，hover 浅灰；生效条件=浅蓝胶囊+计数 */
.tb-btn {
  display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 8px;
  border: none; background: transparent; border-radius: 6px; cursor: pointer;
  font-size: 13px; color: var(--st-text-1); white-space: nowrap;
}
.tb-btn .st-icon { color: var(--st-text-2); }
.tb-btn:hover { background: var(--st-bg-hover); }
.tb-btn:disabled { color: var(--st-disabled); cursor: not-allowed; background: transparent; }
.tb-btn:disabled .st-icon { color: var(--st-disabled); }
.tb-btn.on { background: var(--st-primary-weak); color: var(--st-primary); }
.tb-btn.on .st-icon { color: var(--st-primary); }
.tb-btn.tb-add { color: var(--st-primary); font-weight: 500; }
.tb-btn.tb-add .st-icon { color: var(--st-primary); }
.tb-sep { width: 1px; height: 16px; background: var(--st-border); margin: 0 6px; flex: none; }
.tb-right { margin-left: auto; display: flex; align-items: center; gap: 4px; }
.tb-ico {
  display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px;
  border: none; background: transparent; border-radius: 6px; cursor: pointer; color: var(--st-text-2);
}
.tb-ico:hover { background: var(--st-bg-hover); color: var(--st-text-1); }
.tb-ico:disabled { color: var(--st-disabled); cursor: not-allowed; background: transparent; }
/* pin 的条件胶囊：浅灰底圆角块（类型图标+字段名+⌄） */
.chip {
  display: inline-flex; align-items: center; gap: 4px; background: var(--st-bg-hover);
  border-radius: 6px; padding: 4px 8px; font-size: 12px; color: var(--st-text-1); cursor: pointer;
}
.chip .st-icon { color: var(--st-text-3); }
.chip:hover { background: var(--st-bg-active); }
.chip-edit { display: flex; gap: 8px; align-items: center; }
.batch-bar { display: flex; align-items: center; gap: 12px; padding: 6px 12px; background: var(--st-primary-weak); font-size: 13px; }
.pager { padding: 8px; display: flex; justify-content: center; }
.fm-mask { position: fixed; inset: 0; z-index: 3000; }
.fm { position: fixed; background: #fff; border-radius: 8px; box-shadow: var(--st-shadow-pop); padding: 4px; min-width: 170px; }
.mi {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px; font-size: 13px;
  border-radius: 4px; cursor: pointer; white-space: nowrap; color: var(--st-text-1);
}
.mi .st-icon { color: var(--st-text-2); }
.mi:hover { background: var(--st-bg-hover); }
.mi.danger { color: var(--el-color-danger); }
.mi.danger .st-icon { color: var(--el-color-danger); }
/* 列头菜单的移入编组子菜单：hover 右侧飞出 */
.mi.has-sub { position: relative; display: flex; align-items: center; }
.sub-caret { margin-left: auto; color: var(--st-text-3); display: inline-flex; }
.fm-sub {
  display: none; position: absolute; left: calc(100% - 2px); top: -4px; z-index: 1;
  background: #fff; border-radius: 8px; box-shadow: var(--st-shadow-pop); padding: 4px; min-width: 140px;
}
.mi.has-sub:hover .fm-sub { display: block; }
.sub-check { display: inline-block; width: 16px; color: var(--st-primary); }
.gd-form { display: flex; flex-direction: column; gap: 12px; }
/* 统计行菜单：勾选位 + 方式名 + 右对齐值（对齐设计稿 PixPin_2026-10-15_16-56-53） */
.stat-fm { min-width: 180px; }
.stat-mi { display: flex; align-items: center; gap: 6px; }
.sm-check { width: 14px; color: var(--st-primary); }
.sm-label { flex: 1; }
.sm-val { color: var(--st-text-2); font-variant-numeric: tabular-nums; }
.fm-divider { height: 1px; background: var(--st-border); margin: 4px 6px; }
/* 排序项行尾：当前方向内联灰字（参照 表头-工具栏.png「选项正序 ›」） */
.mi-tail { margin-left: auto; display: inline-flex; align-items: center; gap: 2px; color: var(--st-text-3); font-size: 12px; }
.mi.has-sub .mi-tail .sub-caret { margin-left: 0; }
/* 列头菜单底部图标快捷栏：5 图标等距，hover 浅灰块，tooltip 由 el-tooltip 提供 */
.fm-bar { display: flex; align-items: center; justify-content: space-around; border-top: 1px solid var(--st-border); margin-top: 4px; padding: 6px 4px 2px; }
.fb-item { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 28px; border-radius: 6px; cursor: pointer; color: var(--st-text-2); }
.fb-item:hover { background: var(--st-bg-hover); color: var(--st-text-1); }
/* 列头单字段筛选浮层容器 */
.ffp-wrap { padding: 12px; min-width: 280px; }
</style>
