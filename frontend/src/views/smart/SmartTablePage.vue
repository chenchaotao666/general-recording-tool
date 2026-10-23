<template>
  <div class="st-page">
    <div v-if="initialLoading || initialError" class="st-initial" role="status">
      <span>{{ initialError || '正在加载工作表…' }}</span>
      <el-button v-if="initialError" size="small" @click="loadInitialTable">重试</el-button>
    </div>
    <template v-else>
    <div class="st-table-pane">
    <!-- 视图页签 -->
    <ViewTabs :views="views" :current-id="view?.id" @switch="switchView" @action="onViewAction">
      <template #actions>
        <button type="button" class="tb-btn tab-automation" :class="{ on: automation.visible }" @click="openAutomation()">
          <StIcon name="automation" :size="18" />自动化
        </button>
      </template>
    </ViewTabs>

    <div class="st-panel">
    <!-- 表单视图（V3 §12）：自带工具条与编辑/填写页签 -->
    <FormView v-if="viewType === 'form' && view" ref="formRef" :view="view" :fields="resolvedFields" :table-id="tableId"
              :table-name="entry?.name || ''" :members="members" :can-manage="contentPerm.viewManage"
              @save="onFormSave" @add-field="onFormAddField" @update-options="onFormOptions"
              @edit-field="(f, at) => openFieldConfig(f, null, at)" @delete-field="onFormDeleteField" @open-automation="openAutomation(formAutomationDraft())" />

    <template v-else>
    <!-- 工具栏（对齐参照 上方Tab页签.png：添加一行=蓝字圆⊕；条件按钮生效时浅蓝胶囊+计数） -->
    <div class="toolbar">
      <button class="tb-btn tb-add" :disabled="!perms.can_create" @click="addRow()">
        <StIcon name="plus-circle" :size="15" />添加一行
      </button>
      <span class="tb-sep" />
      <!-- 工具栏按钮（对齐参照 docs/智慧表格/表格上方按钮）：筛选/分组/排序/填色生效或面板展开=浅灰底（个人筛选追加「· 仅你可见」）；
           排序与行高之间竖分隔 -->
      <TableSettingsPanel :visible="activePanel === 'settings'" @update:visible="(v) => setPanel('settings', v)" :fields="fields" :view="view"
                          :column-groups="columnGroups" @toggle-visible="onToggleVisible" @reorder="onReorder"
                          @field-action="onFieldAction" @add-field="(e) => { activePanel = null; onAddFieldAt(e) }" @set-field-group="setFieldGroup">
        <button class="tb-btn" :class="{ open: activePanel === 'settings' }"><StIcon name="table" :size="15" />表格设置</button>
      </TableSettingsPanel>

      <FilterPanel :visible="activePanel === 'filter'" @update:visible="(v) => setPanel('filter', v)" :fields="resolvedFields"
                   :column-groups="columnGroups" :conditions="panelConditions" :conjunction="cfg.filters?.conjunction || 'and'"
                   :scope="filterScope" @change="onFiltersChange" @scope-change="onScopeChange">
        <!-- 生效/展开态与排序、分组一致：浅灰底深色字 -->
        <button class="tb-btn" :class="{ on: filterCount || activePanel === 'filter' }">
          <StIcon name="filter" :size="15" />筛选{{ filterCount ? ` ${filterCount}` : '' }}<span v-if="filterCount && filterScope === 'personal'" class="tb-scope">· 仅你可见</span>
        </button>
      </FilterPanel>

      <GroupPanel :visible="activePanel === 'group'" @update:visible="(v) => setPanel('group', v)" :fields="fields" :groups="cfg.groups || []"
                  @change="(v) => patchConfig({ groups: v })">
        <button class="tb-btn" :class="{ on: (cfg.groups || []).length || activePanel === 'group' }">
          <StIcon name="group" :size="15" />分组{{ (cfg.groups || []).length ? ` ${cfg.groups.length}` : '' }}
        </button>
      </GroupPanel>

      <SortPanel :visible="activePanel === 'sort'" @update:visible="(v) => setPanel('sort', v)" :fields="fields" :sorts="cfg.sorts || []"
                 :auto-sort="cfg.autoSort !== false"
                 @change="(v) => patchConfig({ sorts: v })" @auto-sort="(v) => patchConfig({ autoSort: v })">
        <button class="tb-btn" :class="{ on: (cfg.sorts || []).length || activePanel === 'sort' }">
          <StIcon name="sort" :size="15" />排序{{ (cfg.sorts || []).length ? ` ${cfg.sorts.length}` : '' }}
        </button>
      </SortPanel>
      <span class="tb-sep" />

      <!-- 行高（对齐参照 行高.png）：✓ + 档位图标 + 文案；底部自定义行高（行数） -->
      <!-- 弹出方式与排序/分组等工具栏面板一致：trigger=click + 受控 visible（点按钮开合、点外部关闭，带指向箭头） -->
      <el-popover :hide-after="0" trigger="click" :visible="activePanel === 'rowHeight'" @update:visible="(v) => setPanel('rowHeight', v)"
                  placement="bottom-start" :width="250" popper-class="st-tbpanel st-rh-pop">
        <template #reference>
          <button class="tb-btn" :class="{ on: activePanel === 'rowHeight' }">
            <StIcon name="row-height" :size="15" />行高
          </button>
        </template>
        <div class="rh-menu">
          <div v-for="(l, k) in ROW_HEIGHTS" :key="k" class="rh-item" @click="patchConfig({ rowHeight: k }); activePanel = null">
            <span class="rh-check">{{ currentRowHeight === k ? '✓' : '' }}</span>
            <StIcon :name="`rh-${k}`" :size="17" class="rh-ico" />{{ l }}
          </div>
          <div class="rh-custom">自定义行高
            <el-input-number :model-value="typeof cfg.rowHeight === 'number' ? cfg.rowHeight : null" :min="1" :max="20" :controls="false"
                             size="small" class="st-control st-control--small rh-num" placeholder="" @change="(v) => v && patchConfig({ rowHeight: Math.round(v) })" />行
          </div>
        </div>
      </el-popover>

      <FillPanel :visible="activePanel === 'fill'" @update:visible="(v) => setPanel('fill', v)" :fields="resolvedFields" :rules="cfg.fillRules || []"
                 @change="(v) => patchConfig({ fillRules: v })">
        <button class="tb-btn" :class="{ on: fillCount || activePanel === 'fill' }">
          <StIcon name="fill" :size="15" />填色{{ fillCount ? ` ${fillCount}` : '' }}
        </button>
      </FillPanel>

      <button class="tb-btn" :disabled="!view || !fields.length" title="自动调整所有列宽" @click="autoFitAllFields">
        <StIcon name="autofit" :size="15" />自动列宽
      </button>

      <!-- 批量操作（勾选行后出现）：已选 N 条 · 批量删除 · 取消 -->
      <template v-if="selection.length">
        <span class="tb-sep" />
        <span class="tb-selected">已选 {{ selection.length }} 条</span>
        <button class="tb-btn tb-danger" :disabled="!perms.can_delete" @click="batchDelete">批量删除</button>
        <button class="tb-btn" @click="selection = []; gridRef?.clearSelection()">取消</button>
      </template>

      <div class="tb-right">
        <!-- 条件胶囊（pin 的筛选条件）：点击弹单字段筛选浮层（运算符+勾选清单，与列头「筛选」同款） -->
        <el-popover :hide-after="0" v-for="c in pinnedConditions" :key="c.id" :visible="activePanel === `pinned:${c.id}`" placement="bottom-start" :width="480" popper-class="st-pop st-ffp-pop">
          <template #reference>
            <span class="chip" @click="togglePanel(`pinned:${c.id}`)"><StIcon name="filter" :size="12" />{{ labelOf(c.fieldId) }}<StIcon name="chevron-down" :size="12" /></span>
          </template>
          <FieldFilterPop v-if="activePanel === `pinned:${c.id}` && fieldOfName(c.fieldId)" :field="fieldOfName(c.fieldId)" :condition="c" pinned
                          :scope-text="filterScope === 'personal' ? '调整仅你可见' : '对所有人生效'"
                          @change="(cond) => applyFieldCondition(c.fieldId, cond)"
                          @pin="(v) => setFieldPinned(c.fieldId, v)" @open-panel="setPanel('filter', true)" />
        </el-popover>
        <!-- 右上工具栏：内容权限 / 生成表单 -->
        <el-tooltip :hide-after="0" content="内容权限" placement="bottom" :show-after="200">
          <button class="tb-ico st-icon-action" :class="{ on: permPanel.visible }" @click="openPermPanel()"><StIcon name="lock" :size="16" /></button>
        </el-tooltip>
        <el-tooltip :hide-after="0" content="生成表单" placement="bottom" :show-after="200">
          <button class="tb-ico st-icon-action" :disabled="!contentPerm.viewManage" @click="generateForm"><StIcon name="form-add" :size="16" /></button>
        </el-tooltip>
        <span class="tb-sep" />
        <button class="tb-ico st-icon-action" aria-label="撤销" :disabled="!undoStack.canUndo" @click="doUndo"><StIcon name="undo" :size="16" /></button>
        <button class="tb-ico st-icon-action" aria-label="重做" :disabled="!undoStack.canRedo" @click="doRedo"><StIcon name="redo" :size="16" /></button>
        <button class="tb-ico st-icon-action" data-smart-tip="查找替换" @click="openFind($event)"><StIcon name="search" :size="16" /></button>
      </div>
    </div>


    <!-- 主体：表格区 + 右侧记录详情面板（占位停靠，表格让出宽度） -->
    <div class="st-body">
    <div ref="gridAreaRef" class="st-main">
    <!-- 看板（V3 数据可视化入口）/ 网格 -->
    <KanbanView v-if="viewType === 'kanban'" v-loading="loading" :fields="resolvedFields" :rows="dataRows"
                :config="cfg.kanban || {}" :can-edit-cell="canEditCell" :can-add="perms.can_create"
                :can-manage="contentPerm.viewManage" @move="onKanbanMove" @add="onKanbanAdd"
                @open="openDetail"
                @config="(p) => patchConfig({ kanban: { ...(cfg.kanban || {}), ...p } }, { reload: false })" />
    <SmartGrid
      v-else
      ref="gridRef"
      v-loading="loading"
      :fields="resolvedFields" :rows="rows" :grouped="grouped" :total="total" :aggregations="aggregations"
      :view="view" :column-groups="columnGroups" :collapsed-groups="collapsedGroups"
      :height="gridHeight" :readonly="!perms.can_edit" :can-edit-cell="canEditCell"
      :paste-cells="onPasteCells"
      :menu-field="fieldMenu.visible ? fieldMenu.field?.field_name : null"
      :active-row-id="detail.visible ? detailRecord?.id : null"
      :search-matches="findHighlight.matches" :search-current-index="findHighlight.currentIndex"
      @expand-row="(r) => openDetail(r)"
      @row-activate="syncDetailRow"
      :can-create="perms.can_create" :can-delete="perms.can_delete"
      @cell-commit="onCellCommit" @add-row="addRow" @cell-menu="onCellMenu" @field-menu="onFieldMenu" @ai-run="runAiField" @field-edit="(f, at) => openFieldConfig(f, null, at)"
      @group-edit="(g, at) => openGroupDialog(null, g, at)"
      @field-filter="(f, rect) => openFieldFilterAt(f, rect)"
      @toggle-group="toggleGroup" @selection-change="(s) => (selection = s)" @open-config="openFieldConfig"
      @add-field="onAddFieldAt" @add-option="onAddOption" @footer-menu="onFooterMenu"
      @group-menu="onGroupMenu" @add-row-in-group="addRowInGroup"
    />

    <!-- 分页（未分组时） -->
    <div v-if="showPager" class="pager">
      <el-pagination small layout="prev, pager, next, total" :total="total" :page-size="pageSize"
                     :current-page="page" @current-change="(p) => { page = p; loadGrid() }" />
    </div>
    </div>

    </div>
    </template>

    </div>
    </div>
    <AutomationDrawer :visible="automation.visible" :table-id="tableId" :table-name="entry?.name || ''" :fields="fields"
                      :tables="smartTables" :members="members" :dashboards="dashboards" :load-fields="loadFieldsOf"
                      :initial-draft="automation.draft" @close="automation.visible = false" @run-complete="refreshAfterAutomation" />
    <RecordDetailPanel v-if="detail.visible && detailRecord" :record="detailRecord" :fields="resolvedFields"
                       :view="view" :column-groups="columnGroups"
                       :has-prev="detailIdx > 0" :has-next="detailIdx < dataRows.length - 1"
                       :readonly="!perms.can_edit" :can-edit-cell="canEditCell"
                       :can-create="perms.can_create" :can-delete="perms.can_delete"
                       :title-field="cfg.recordTitleField" :can-set-title="contentPerm.viewManage"
                       @field-click="f => gridRef?.revealField(f.field_name, detailRecord.id)"
                       @set-title-field="(fn) => patchConfig({ recordTitleField: fn }, { reload: false })"
                       @close="detail.visible = false" @nav="navDetail" @cell-commit="onCellCommit"
                       @add-option="onAddOption" @open-config="openFieldConfig" @record-action="onDetailAction" />
    <!-- 面板与弹窗 -->
    <FieldConfigDialog :visible="fieldDialog.visible" :field="fieldDialog.field" :preset="fieldDialog.preset" :fields="fields" :at="fieldDialog.at"
                       :table-id="tableId" :sample-record-id="dataRows[0]?.id || null"
                       :tables="allTables" :lookup-tables="lookupTables" :source-fields-of="loadFieldsOf" @refresh-lookup-tables="loadDocEntries"
                       @close="fieldDialog.visible = false" @save="onFieldSave"
                       @ai-tags="(f) => { fieldDialog.visible = false; Object.assign(aiTags, { visible: true, field: f }) }" />
    <FindReplaceDialog ref="findDialogRef" :visible="findVisible" :table-id="tableId" :view-id="view?.id" :at="findAt"
                       :order-matches="matches => gridRef?.orderSearchMatches?.(matches) ?? matches"
                       @close="closeFind" @highlight="findHighlight = $event"
                       @locate="locateFindMatch" @replaced="onFindReplaced" />

    <!-- 新建/修改编组弹窗（设计文档 §6.1：编组名称 + 包含字段，默认含当前列） -->
    <!-- 非模态（同字段编辑框）：双击编组表头时在鼠标位置弹出，点外部收起 -->
    <el-dialog :model-value="groupDialog.visible" :title="groupDialog.id ? '修改编组' : '新建编组'"
               width="320px" class="st-fcd st-fcd-compact" :show-close="false" append-to-body destroy-on-close
               v-bind="anchoredDialogAttrs(groupDialog.at, 320, 250)"
               @opened="placeGroupDialog(); focusGroupName()" @close="groupDialog.visible = false; groupFieldsOpen = false">
      <div class="gd-form" v-panel-drag="{ panel: '.el-dialog' }">
        <div class="fcd-move" data-panel-drag-handle />
        <input ref="groupNameRef" v-model="groupDialog.name" class="st-control st-control--native gd-name" placeholder="编组名称" aria-label="编组名称" maxlength="100"
               @keydown.enter="saveGroupDialog" @keydown.esc="groupDialog.visible = false" />
        <el-popover v-model:visible="groupFieldsOpen" trigger="click" placement="bottom-start" :width="324"
                    :hide-after="0" :show-arrow="false" popper-class="st-tbpanel st-pick-pop">
          <template #reference>
            <div class="st-control st-control--native st-control--wrap gd-fields" :class="{ open: groupFieldsOpen }" role="button" tabindex="0" aria-label="选择包含字段"
                 :aria-expanded="groupFieldsOpen" @keydown.enter.prevent="groupFieldsOpen = !groupFieldsOpen">
              <StIcon name="colgroup" :size="17" />
              <SmartTagList :items="groupDialog.members.map(name => ({ value: name, label: fields.find(f => f.field_name === name)?.label || name }))"
                            placeholder="包含字段" @remove="name => toggleGroupField({ field_name: name })" />
              <StIcon :name="groupFieldsOpen ? 'chevron-up' : 'chevron-down'" :size="14" />
            </div>
          </template>
          <FieldPickList :fields="fields" :column-groups="columnGroups" :selected="groupDialog.members" @pick="toggleGroupField" />
        </el-popover>
        <div class="gd-foot">
          <button type="button" class="st-button st-button--primary gd-btn primary" @click="saveGroupDialog">确定</button>
          <button type="button" class="st-button gd-btn" @click="groupDialog.visible = false">取消</button>
        </div>
      </div>
    </el-dialog>

    <!-- 字段列头菜单 -->
    <teleport to="body">
      <div v-if="fieldMenu.visible" class="fm-mask field-menu-layer">
        <SmartMenu v-menu-bounds="fieldMenu" class="fm" @click.stop>
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
          <!-- 根据此列…（V3，对齐参照 表头-数据可视化.png）：内容权限 / 数据可视化 / AI 匹配标签 / 内容变更时提醒 -->
          <div class="fm-divider" />
          <div class="fm-group-t">根据此列...</div>
          <div class="mi" @click="fieldAct('perm')"><StIcon name="lock" :size="15" />内容权限<span class="st-free-tag fm-free">限时免费</span>
            <span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span></div>
          <div class="mi has-sub">
            <StIcon name="magic" :size="15" />数据可视化 <span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span>
            <div class="fm-sub fm-viz">
              <div class="fm-sub-t">视图</div>
              <div class="mi mi-2" :class="{ disabled: !menuIsSingleSelect }" @click="menuIsSingleSelect && fieldAct('kanban')">
                <StIcon name="kanban" :size="16" /><div><div>新建看板</div><div class="mi-s">{{ menuIsSingleSelect ? '按选项分类查看' : '仅单选字段可建看板' }}</div></div>
              </div>
              <div class="fm-divider" />
              <div class="fm-sub-t">图表</div>
              <div v-for="ch in VIZ_CHARTS" :key="ch.type" class="mi mi-2 has-sub">
                <StIcon :name="ch.icon" :size="16" /><div><div>{{ ch.label }}</div><div class="mi-s">{{ ch.desc }}</div></div>
                <span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span>
                <div class="fm-sub">
                  <div class="fm-sub-t">添加到仪表盘</div>
                  <div v-for="d in dashboards" :key="d.id" class="mi" @click="addVizChart(ch.type, d)"><StIcon name="dashboard" :size="14" />{{ d.name }}</div>
                  <div class="mi" @click="addVizChart(ch.type, null)"><StIcon name="plus" :size="14" />新建仪表盘</div>
                </div>
              </div>
              <div class="mi has-sub">
                添加更多图表… <span class="sub-caret"><StIcon name="chevron-right" :size="12" /></span>
                <div class="fm-sub">
                  <div class="fm-sub-t">在仪表盘中配置</div>
                  <div v-for="d in dashboards" :key="d.id" class="mi" @click="addMoreCharts(d)"><StIcon name="dashboard" :size="14" />{{ d.name }}</div>
                  <div class="mi" @click="addMoreCharts(null)"><StIcon name="plus" :size="14" />新建仪表盘</div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="menuIsSelect" class="mi" @click="fieldAct('aiTags')"><StIcon name="sparkle" :size="15" class="fm-ai" />AI 匹配标签</div>
          <div class="mi" @click="fieldAct('reminder')"><StIcon name="play-circle" :size="15" />内容变更时提醒</div>
          <!-- 底部图标快捷栏：副本/列宽/冻结/隐藏/删除 -->
          <div class="fm-bar">
            <el-tooltip :hide-after="0" content="创建副本" placement="top" :show-after="150">
              <span class="fb-item st-icon-action" @click="fieldAct('duplicate')"><StIcon name="copy" :size="16" /></span>
            </el-tooltip>
            <el-tooltip :hide-after="0" content="自动调整列宽" placement="top" :show-after="150">
              <span class="fb-item st-icon-action" @click="fieldAct('autoFit')"><StIcon name="autofit" :size="16" /></span>
            </el-tooltip>
            <el-tooltip :hide-after="0" :content="menuFieldFrozen ? '取消冻结' : menuFreezeBlocked ? '无法冻结，窗口宽度不足' : '冻结至此列'" placement="top" :show-after="150">
              <span class="fb-item st-icon-action" :class="{ 'freeze-disabled': menuFreezeBlocked }" :aria-disabled="menuFreezeBlocked" @click="fieldAct('freeze')"><StIcon :name="menuFieldFrozen ? 'unfreeze' : 'freeze'" :size="16" /></span>
            </el-tooltip>
            <span class="fb-item st-icon-action" aria-label="隐藏" @click="fieldAct('hide')"><StIcon name="eye-off" :size="16" /></span>
            <span class="fb-item st-icon-action" aria-label="删除" @click="fieldAct('delete')"><StIcon name="trash" :size="16" /></span>
          </div>
        </SmartMenu>
      </div>
    </teleport>

    <!-- 编组组头菜单（设计稿 PixPin_2026-10-16_00-40-59） -->
    <teleport to="body">
      <div v-if="groupMenu.visible" class="fm-mask group-menu-layer">
        <div v-menu-bounds="groupMenu" class="fm" @click.stop>
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
          <div class="mi" :class="{ disabled: !freezeFits(groupMenu.group?.field_names?.at(-1)) }" :title="freezeFits(groupMenu.group?.field_names?.at(-1)) ? '' : '无法冻结，窗口宽度不足'" @click="groupAct('freeze')"><StIcon name="freeze" :size="15" />冻结至此编组</div>
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
        <div v-menu-bounds="statMenu" class="fm stat-fm" @click.stop>
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
                   @close="addFieldPop.visible = false" @ai="onAiFromAddField" />
      <AiFieldPanel v-if="aiPanel.visible" :at="aiPanel.at" :field="aiPanel.field || undefined" :x="aiPanel.x" :y="aiPanel.y" :table-id="tableId" :fields="resolvedFields"
                    :rows="dataRows" :total-rows="total"
                    :preset-label="aiPanel.label" @close="aiPanel.visible = false" @save="onAiSave"
                    @run="({ scope }) => runAiField(aiPanel.field, scope)"
                    @write-formula="() => { aiPanel.visible = false; aiFormulaDlg.visible = true }" />
    </teleport>

    <!-- ========== V3：协作与智能 ========== -->
    <PermissionPanel :visible="permPanel.visible" :doc-id="doc?.id" :members="members" :focus-entry-id="permPanel.focus"
                     @close="permPanel.visible = false" @changed="loadGrid(view?.id)" />
    <QuickReminderDialog :visible="reminder.visible" :table-id="tableId" :field="reminder.field" :fields="fields"
                         :members="members" :me="me?.id" @close="reminder.visible = false"
                         @more="(d) => openAutomation(d)" />
    <AiFormulaDialog :visible="aiFormulaDlg.visible" :table-id="tableId" :fields="fields" with-name
                     @close="aiFormulaDlg.visible = false" @apply="onAiFormulaApply" />
    <AiMatchTagsDialog :visible="aiTags.visible" :table-id="tableId" :field="aiTags.field" :fields="fields"
                       @close="aiTags.visible = false" @done="reloadMeta(); loadGrid(view?.id)" />

    <!-- 列头「筛选」：贴列头的单字段筛选浮层 -->
    <teleport to="body">
      <div v-if="fieldFilter.visible" class="fm-mask" @click="fieldFilter.visible = false"
           @contextmenu.prevent="fieldFilter.visible = false">
        <div v-menu-bounds="fieldFilter" class="fm ffp-wrap" @click.stop>
          <FieldFilterPop v-if="fieldFilter.field" :field="fieldFilter.field"
                          :condition="panelConditions.find(c => c.fieldId === fieldFilter.field?.field_name) || null"
                          :pinned="!!panelConditions.find(c => c.fieldId === fieldFilter.field?.field_name)?.pinned"
                          :scope-text="filterScope === 'personal' ? '调整仅你可见' : '对所有人生效'"
                          @change="(cond) => applyFieldCondition(fieldFilter.field.field_name, cond)"
                          @pin="(v) => setFieldPinned(fieldFilter.field.field_name, v)"
                          @open-panel="fieldFilter.visible = false; setPanel('filter', true)" />
        </div>
      </div>
    </teleport>
    </template>
  </div>
</template>

<script setup>
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, provide, reactive, ref, watch } from 'vue'
import vMenuBounds from '../../smart/utils/menuBounds'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import SmartGrid from '../../components/smart/grid/SmartGrid.vue'
import StIcon from '../../components/smart/icons/StIcon.vue'
import SmartMenu from '../../components/smart/common/SmartMenu.vue'
import ViewTabs from '../../components/smart/ViewTabs.vue'
import FilterPanel from '../../components/smart/panels/FilterPanel.vue'
import SortPanel from '../../components/smart/panels/SortPanel.vue'
import GroupPanel from '../../components/smart/panels/GroupPanel.vue'
import FillPanel from '../../components/smart/panels/FillPanel.vue'
import TableSettingsPanel from '../../components/smart/panels/TableSettingsPanel.vue'
import FieldConfigDialog from '../../components/smart/panels/FieldConfigDialog.vue'
import FieldFilterPop from '../../components/smart/panels/FieldFilterPop.vue'
import AddFieldPop from '../../components/smart/panels/AddFieldPop.vue'
import RecordDetailPanel from '../../components/smart/panels/RecordDetailPanel.vue'
import FindReplaceDialog from '../../components/smart/panels/FindReplaceDialog.vue'
import PermissionPanel from '../../components/smart/perms/PermissionPanel.vue'
import AutomationDrawer from '../../components/smart/automation/AutomationDrawer.vue'
import FieldPickList from '../../components/smart/panels/FieldPickList.vue'
import SmartTagList from '../../components/smart/common/SmartTagList.vue'
import QuickReminderDialog from '../../components/smart/automation/QuickReminderDialog.vue'
import FormView from '../../components/smart/form/FormView.vue'
import KanbanView from '../../components/smart/kanban/KanbanView.vue'
import AiFieldPanel from '../../components/smart/ai/AiFieldPanel.vue'
import AiFormulaDialog from '../../components/smart/ai/AiFormulaDialog.vue'
import AiMatchTagsDialog from '../../components/smart/ai/AiMatchTagsDialog.vue'
import { FIELD_REGISTRY, filterOpsOf, OP_LABELS, OPTION_COLORS, sortDirectionLabels,
         footerStatsOf, STAT_LABELS, formatStatValue } from '../../smart/registry/fieldRegistry.js'
import { anchoredDialogAttrs, useButtonAnchoredDialog, useNonModalOutsideClose } from '../../smart/utils/anchorDialog.js'
import { vPanelDrag } from '../../smart/utils/panelDrag.js'
import { isRuleComplete, isCondValueEmpty, createUndoStack, formatDate } from '../../smart/utils/format.js'
import { resolveRefOptions } from '../../smart/utils/refOptions.js'
import { resolveEnumTags } from '../../smart/utils/enumTags.js'
import { rowHeightPixels, wrappedTextWidth, wrappedTagWidth } from '../../smart/utils/autoColumnWidth.js'
import { buildColumnLayout } from '../../smart/utils/columnLayout.js'
import { waitForGridIdle } from '../../smart/utils/waitForGridIdle.js'
import { mergeUpdatedRows, reconcileRows } from '../../smart/utils/reconcileRows.js'
import { previewCells, rollbackCells } from '../../smart/utils/optimisticCells.js'
import { canInsertLocally, insertViewRows } from '../../smart/utils/insertViewRows.js'
import { presetFromFilters } from '../../smart/utils/newRowPreset.js'
import {
  alterTable, getTable, listMembers, listTables, getUserDirectory,
  smartGrid, smartRelationRecords, smartRecordsRevision, smartListViews, smartCreateView, smartUpdateView, smartDeleteView,
  smartDuplicateView, smartSetDefaultView, smartPutViewPref, smartDeleteViewPref,
  smartCreateRecord, smartInsertRecords, smartUpdateRecord, smartDeleteRecord, smartBatchDelete, smartBatchUpdate,
  smartDuplicateRecord, smartDuplicateField, smartFieldDeps, smartFieldStats,
  smartListColumnGroups, smartCreateColumnGroup, smartUpdateColumnGroup, smartDeleteColumnGroup,
  smartGetDoc, smartGetTree, smartDocMembers, smartCreateEntry, smartCreateWidget, smartAiRun, handleBillingError,
} from '../../api/index.js'

const route = useRoute()
const router = useRouter()
const tableId = ref(Number(route.params.tableId))
const entryQuery = { ...route.query }
let pageActive = true
let pageLoaded = false
provide('smartTableId', tableId)
const me = JSON.parse(localStorage.getItem('grt_user') || 'null')

const ROW_HEIGHTS = { default: '默认', medium: '中等', tall: '高', extraTall: '超高' }

// ---------- 状态 ----------
const loading = ref(false)
const initialLoading = ref(true)
const initialError = ref('')
const fields = ref([])
const rows = ref([])
const total = ref(0)
const aggregations = ref({})
const grouped = ref(false)
const views = ref([])
const view = ref(null)
const perms = ref({ can_create: true, can_edit: true, can_delete: true })
// V3 内容权限（grid 接口下发）：行级只读标记 row.__readonly + 字段三态 fieldRights + 视图管理开关
const contentPerm = ref({ managed: true, level: 'FULL', viewManage: true, schemaEdit: true, fieldRights: {} })
const doc = ref(null)
const entry = ref(null)        // 本表对应的文档条目（内容权限按条目配置）
const docEntries = ref([])
const dashboards = computed(() => docEntries.value.filter(e => e.type === 'dashboard'))
const smartTables = computed(() => docEntries.value.filter(e => e.ref_table_id && ['sheet', 'form'].includes(e.type))
  .map(e => ({ id: e.ref_table_id, label: e.name })))
const lookupTables = computed(() => docEntries.value.filter(e => e.type === 'sheet' && e.ref_table_id)
  .map(e => ({ id: e.ref_table_id, label: e.name })))
const columnGroups = ref([])
provide('smartColumnGroups', columnGroups)   // 统一字段选择面板（FieldPickList）按编组展示字段
const collapsedGroups = ref(new Set())
const selection = ref([])
const page = ref(1)
const pageSize = 200
const activePanel = ref(null)
const findVisible = ref(false)
const findDialogRef = ref(null)
const findAt = ref(null)
const findHighlight = ref({ matches: [], currentIndex: -1 })
let findLocateSeq = 0
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

let referenceLoadVersion = 0
async function prepareRefSources(fieldList) {
  const fieldCache = new Map(refFieldsCache.value)
  const rowCache = new Map(refRowsCache.value)
  const lookupSources = new Set(fieldList.filter(f => f.field_type === 'lookup').map(f => f.options?.sourceTableId).filter(Boolean))
  await Promise.all([...lookupSources].map(async tid => {
    try {
      const meta = await getTable(tid)
      fieldCache.set(tid, meta.fields)
    } catch { /* 无权访问或源表已删除时保留文本兜底 */ }
  }))
  for (const f of fieldList.filter(isRefSelect)) {
    const tid = f.options.reference.tableId
    try {
      if (!fieldCache.has(tid)) {
        const meta = await getTable(tid)
        fieldCache.set(tid, meta.fields)
      }
      if (f.options.optionLinkage?.enabled && !rowCache.has(tid)) {
        const g = await smartGrid(tid, { page_size: 200 })
        rowCache.set(tid, g.items.filter(r => !r.__rowType))
      }
    } catch { /* 引用表无权访问/已删除：兜底本地 options */ }
  }
  return { fieldCache, rowCache }
}
async function loadRefSources() {
  const version = ++referenceLoadVersion
  const tid = tableId.value
  const sources = await prepareRefSources(fields.value)
  if (version !== referenceLoadVersion || tid !== tableId.value) return
  refFieldsCache.value = sources.fieldCache
  refRowsCache.value = sources.rowCache
}

// 渲染用字段：reference 模式的选项集实时取自引用字段（源表变更自动同步）
const resolvedFields = computed(() => fields.value.map(f => {
  if (f.field_type === 'lookup') {
    const source = (refFieldsCache.value.get(f.options?.sourceTableId) || []).find(x => x.field_name === f.options?.sourceFieldId)
    return { ...f, lookupDisplayField: source }
  }
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
const viewType = computed(() => view.value?.type || 'grid')
const dataRows = computed(() => rows.value.filter(r => r.__rowType !== 'group'))
// 表格最大高度：撑到页面底部（留 8px）；需要分页时给紧凑分页条留 36px。
// 数据不满一屏时表格按内容收缩（SmartGrid 用 max-height），统计行/分页条跟着上移
const showPager = computed(() => viewType.value === 'grid' && !grouped.value && total.value > pageSize)
const gridAreaRef = ref(null)
const gridAreaHeight = ref(0)
const gridAreaWidth = ref(0)
let gridAreaObserver = null
watch(gridAreaRef, element => {
  gridAreaObserver?.disconnect()
  if (!element) return
  gridAreaHeight.value = element.clientHeight
  gridAreaWidth.value = element.clientWidth
  gridAreaObserver = new ResizeObserver(() => { gridAreaHeight.value = element.clientHeight; gridAreaWidth.value = element.clientWidth })
  gridAreaObserver.observe(element)
}, { flush: 'post' })
const gridHeight = computed(() => Math.max(100, (gridAreaHeight.value || window.innerHeight - 176) - (showPager.value ? 32 : 0)))
const gridRef = ref(null)

// 计数只算生效的条件（固定到工具栏但还没填值的不算）
const filterCount = computed(() => (cfg.value.filters?.conditions || []).filter(c => c.fieldId && (['isEmpty', 'isNotEmpty'].includes(c.operator) || !isCondValueEmpty(c.value))).length)
const fillCount = computed(() => (cfg.value.fillRules || []).filter(isRuleComplete).length)
const pinnedConditions = computed(() => (cfg.value.filters?.conditions || []).filter(c => c.pinned && c.fieldId))
const panelConditions = computed(() => cfg.value.filters?.conditions || [])

// ---------- 加载 ----------
let loadRequestId = 0
let recordsRevision = null
let revisionTimer = null
let revisionPolling = false
let pendingCellWrites = 0
function scheduleRevisionPoll() {
  clearTimeout(revisionTimer)
  if (pageActive) revisionTimer = setTimeout(pollRevision, 2000)
}
async function pollRevision() {
  if (revisionPolling) return
  revisionPolling = true
  const tid = tableId.value
  try {
    if (!pageActive || document.hidden || loading.value || pendingCellWrites || gridRef.value?.isEditing?.() || gridRef.value?.isScrolling?.()) return
    const result = await smartRecordsRevision(tid)
    if (pageActive && tid === tableId.value && !pendingCellWrites && !gridRef.value?.isEditing?.()
        && result.revision !== recordsRevision) {
      await loadGrid(view.value?.id, { silent: true })
    }
  } catch { /* 暂时断网时保留当前数据，下次检查重试。 */ }
  finally { revisionPolling = false; scheduleRevisionPoll() }
}
async function loadAll({ silent = false } = {}) {
  const requestId = ++loadRequestId
  const requestedTableId = tableId.value
  loading.value = !silent
  try {
    const qv = view.value?.id || Number(entryQuery.view) || undefined
    const [meta, vs, gs, d, grid] = await Promise.all([
      getTable(requestedTableId), smartListViews(requestedTableId), smartListColumnGroups(requestedTableId), smartGetDoc(),
      smartGrid(requestedTableId, { view_id: qv, page: page.value, page_size: pageSize }),
    ])
    if (requestId !== loadRequestId) return
    fields.value = meta.fields
    perms.value = meta.my_perms || perms.value
    views.value = vs.views
    columnGroups.value = gs.groups
    doc.value = d
    loadDocEntries()
    await applyGridResult(grid)
    if (requestId !== loadRequestId) return
    // 成员目录不是网格显示的前置条件，后台补齐，避免表结构与行数据分两次渲染。
    ;(async () => {
      const directory = (await smartDocMembers(d.id).catch(() => null))?.members
        || ((await listMembers().catch(() => [])) || []).map(m => ({ id: m.user_id, name: m.username }))
      const contacts = await getUserDirectory().catch(() => null)
      const people = [...directory, ...(contacts?.enterprise?.members || []),
        ...(contacts?.friends || []).map(p => ({ id: p.user_id, name: p.username })),
        ...(contacts?.groups || []).flatMap(g => (g.members || []).map(p => ({ id: p.id, name: p.username })))]
      if (requestId === loadRequestId) members.value = [...new Map(people.map(p => [p.id, p])).values()]
    })()
    loadRelationRows()
    loadRefSources()
  } finally {
    if (requestId === loadRequestId && !silent) loading.value = false
  }
}

// focusId：返回该记录（筛选+排序后）所在的页，用于新增一行后翻到它
async function refreshAfterAutomation() {
  try {
    await loadGrid(view.value?.id, { silent: true })
  } catch (e) {
    ElMessage.error(e.message || '自动化已执行，表格刷新失败，请重试')
  }
}

async function loadGrid(viewId, { silent = false, focusId = null } = {}) {
  const requestId = ++loadRequestId
  const requestedTableId = tableId.value
  if (!silent) loading.value = true
  try {
    const g = await smartGrid(requestedTableId, { view_id: viewId, page: page.value, page_size: pageSize,
                                         ...(focusId != null ? { focus_id: focusId } : {}) })
    if (requestedTableId !== tableId.value || requestId !== loadRequestId) return
    if (silent && !await waitForGridIdle(
      () => gridRef.value?.isScrolling?.(),
      () => pageActive && requestedTableId === tableId.value && requestId === loadRequestId,
    )) return
    if (silent && (pendingCellWrites || gridRef.value?.isEditing?.())) return
    await applyGridResult(g)
  } finally {
    if (!silent && requestedTableId === tableId.value) loading.value = false
  }
}

async function applyGridResult(g) {
  recordsRevision = g.revision ?? null
  if (g.page) page.value = g.page
  rows.value = reconcileRows(rows.value, g.items)
  loadRelationRows()
  total.value = g.total
  aggregations.value = g.aggregations || {}
  grouped.value = !!g.grouped
  view.value = g.view
  if (g.my_perms) perms.value = g.my_perms
  if (g.content_perm) contentPerm.value = g.content_perm
  if (g.view) filterScope.value = g.view.config?.filtersScope === 'personal' ? 'personal' : 'shared'
  if (hasUnknownAiOptions()) await reloadMeta()   // AI 生成时自动新建了选项：刷新字段元数据，否则单元格显示裸 optionId
  scheduleAiPoll()
  scheduleRevisionPoll()
}

function openFind(event) {
  const rect = event?.currentTarget?.getBoundingClientRect?.()
  if (rect) findAt.value = { x: rect.right - 404, y: rect.bottom + 4 }
  findVisible.value = true
}

function closeFind() {
  findLocateSeq += 1
  findVisible.value = false
  findHighlight.value = { matches: [], currentIndex: -1 }
}

async function locateFindMatch(match) {
  if (!match || !findVisible.value) return
  const seq = ++findLocateSeq
  let shown = await gridRef.value?.focusRecord?.(match.recordId, match.field, { select: false })
  if (seq !== findLocateSeq || !findVisible.value) return
  if (shown) return
  await loadGrid(view.value?.id, { focusId: match.recordId })
  if (seq !== findLocateSeq || !findVisible.value) return
  shown = await gridRef.value?.focusRecord?.(match.recordId, match.field, { select: false })
  if (shown === false) ElMessage.info('该结果不在当前视图显示范围内，暂未定位')
}

async function applyFindChanges(changes, valueKey) {
  const byRecord = new Map()
  for (const change of changes) {
    const rid = Number(change.recordId)
    if (!Number.isFinite(rid) || !change.field) continue
    if (!byRecord.has(rid)) byRecord.set(rid, {})
    byRecord.get(rid)[change.field] = change[valueKey]
  }
  for (const [rid, data] of byRecord) {
    await smartUpdateRecord(tableId.value, rid, { data })
  }
  await loadGrid(view.value?.id)
}

async function onFindReplaced(payload) {
  const changes = Array.isArray(payload?.changes) ? payload.changes : []
  if (!changes.length) return
  const label = payload?.label || '查找替换'
  undoStack.push({
    label,
    undo: async () => {
      await applyFindChanges(changes, 'before')
      await findDialogRef.value?.refresh?.()
    },
    redo: async () => {
      await applyFindChanges(changes, 'after')
      await findDialogRef.value?.refresh?.()
    },
  })
  // 保持当前视图；直接把 loadGrid 绑给 replaced 会丢 viewId 并跳回默认视图。
  await loadGrid(view.value?.id)
}

async function loadDocEntries() {
  if (!doc.value) return
  const t = await smartGetTree(doc.value.id).catch(() => ({ entries: [] }))
  docEntries.value = t.entries
  entry.value = t.entries.find(e => e.ref_table_id === tableId.value) || null
}

// 单元格可编辑：行级编辑范围外（__readonly）或字段无编辑权时只读
function canEditCell(row, field) {
  if (!row || row.__readonly) return false
  return contentPerm.value.fieldRights?.[field?.field_name]?.edit !== false
}

// 同一批未知 id 只刷新一次元数据（选项已在库里丢失的历史数据刷新也找不回，避免每次轮询都重拉）
let lastUnknownSig = ''
function hasUnknownAiOptions() {
  const sel = fields.value.filter(f => f.field_type === 'ai' && ['singleSelect', 'multiSelect'].includes(f.options?.outputType))
  if (!sel.length) return false
  const unknown = new Set()
  for (const f of sel) {
    const ids = new Set((f.options?.options || []).map(o => o.id))
    for (const r of rows.value) {
      const v = r[f.field_name]
      for (const id of (Array.isArray(v) ? v : (v == null || v === '' ? [] : [v]))) if (!ids.has(id)) unknown.add(`${f.field_name}:${id}`)
    }
  }
  const sig = [...unknown].sort().join('|')
  if (!sig || sig === lastUnknownSig) return false
  lastUnknownSig = sig
  return true
}

// AI 字段生成中：静默轮询网格直到无 pending/running 单元格
let aiPollTimer = null
function scheduleAiPoll() {
  clearTimeout(aiPollTimer)
  const busy = rows.value.some(r => r.__ai && Object.values(r.__ai).some(x => x.status === 'pending' || x.status === 'running'))
  if (pageActive && busy) aiPollTimer = setTimeout(() => loadGrid(view.value?.id, { silent: true }), 2500)
}

// 关联字段：加载目标表记录做标签目录
async function loadRelationRows() {
  for (const f of fields.value.filter(x => x.field_type === 'relation' && x.options?.targetTableId)) {
    const tid = f.options.targetTableId
    const cached = new Map((relationRows.value.get(tid) || []).map(r => [r.id, r]))
    const ids = [...new Set(rows.value.flatMap(r => {
      const value = r[f.field_name]
      return (Array.isArray(value) ? value : value ? [value] : []).map(Number)
    }))].filter(id => !cached.has(id))
    if (!ids.length) continue
    try {
      for (let offset = 0; offset < ids.length; offset += 200) {
        const g = await smartRelationRecords(tid, { ids: ids.slice(offset, offset + 200).join(',') })
        const labelField = g.fields.find(x => x.field_type === 'text') || g.fields[0]
        const next = new Map(relationRows.value)
        const merged = new Map((relationRows.value.get(tid) || []).map(r => [r.id, r]))
        g.items.forEach(r => merged.set(r.id, { id: r.id, label: r.__relation_label ?? r[labelField?.field_name] ?? `#${r.id}` }))
        next.set(tid, [...merged.values()])
        relationRows.value = next
      }
    } catch { /* 目标表无权访问时忽略 */ }
  }
}

// ---------- 视图操作 ----------
function switchView(v) { page.value = 1; loadGrid(v.id) }

async function onViewAction(cmd, v) {
  if (cmd === 'add') {
    const type = v || 'grid'
    const base = { grid: '表格视图', kanban: '看板', form: '表单' }[type]
    const sameType = views.value.filter(x => (x.type || 'grid') === type).length
    try {
      const r = await smartCreateView(tableId.value, { type, name: sameType ? `${base} ${sameType + 1}` : base, config: {} })
      views.value.push(r.view)
      switchView(r.view)
    } catch (e) {
      ElMessage.error(e.message || '新建视图失败')
    }
  } else if (cmd === 'rename') {
    const { value } = await ElMessageBox.prompt('视图名称', '重命名', { inputValue: v.name })
    if (value) { await smartUpdateView(v.id, { name: value }); views.value = (await smartListViews(tableId.value)).views }
  } else if (cmd === 'duplicate') {
    const r = await smartDuplicateView(v.id)
    views.value.push(r.view)
  } else if (cmd === 'default') {
    await smartSetDefaultView(v.id)
    views.value = (await smartListViews(tableId.value)).views
  } else if (cmd === 'delete') {
    await ElMessageBox.confirm(`删除视图「${v.name}」？`, '删除', { type: 'warning' })
    await smartDeleteView(v.id)
    views.value = (await smartListViews(tableId.value)).views
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
// 受控面板开关：打开某面板即关闭其他面板；关闭只在当前面板是它时生效
function setPanel(name, v) { activePanel.value = v ? name : (activePanel.value === name ? null : activePanel.value) }
const currentRowHeight = computed(() => (typeof cfg.value.rowHeight === 'number' ? null : (cfg.value.rowHeight || 'default')))

// 受控 popover 的外点关闭（点击面板与工具栏以外区域时收起）
function onDocClick(e) {
  if (!activePanel.value) return
  // 点击目标在本次事件处理中已被移出 DOM（如点面板里的"删除行"先删了自身所在行），
  // detached 节点 closest 必为 null，不能算作外点
  if (!document.contains(e.target)) return
  // 面板内的下拉（字段/运算符/更多菜单）teleport 到 body，同样视为面板内部
  if (e.target.closest('.el-popover') || e.target.closest('.el-popper') || e.target.closest('.toolbar')) return
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
  const existing = panelConditions.value.find(c => c.fieldId === fieldName)
  let conds
  if (cond) {
    const next = { ...cond, id: existing?.id || `c_${Date.now()}`, pinned: existing?.pinned || false }
    // 原位替换（保持条件顺序），没有则追加
    conds = existing ? panelConditions.value.map(c => (c.fieldId === fieldName ? next : c)) : [...panelConditions.value, next]
  } else {
    conds = panelConditions.value.filter(c => c.fieldId !== fieldName)
  }
  onFiltersChange(conds, cfg.value.filters?.conjunction || 'and')
}
// 📌 固定到工具栏 / 取消固定：没有条件时新建一个未填值的固定条件（不生效，供快速筛选）；
// 取消固定时若条件还没填值则一并移除
function setFieldPinned(fieldName, pinned) {
  const existing = panelConditions.value.find(c => c.fieldId === fieldName)
  const f = fields.value.find(x => x.field_name === fieldName)
  const empty = (v) => v == null || v === '' || (Array.isArray(v) && !v.length)
  let conds
  if (existing) {
    const incomplete = !['isEmpty', 'isNotEmpty'].includes(existing.operator) && empty(existing.value)
    conds = !pinned && incomplete
      ? panelConditions.value.filter(c => c.fieldId !== fieldName)
      : panelConditions.value.map(c => (c.fieldId === fieldName ? { ...c, pinned } : c))
  } else {
    if (!pinned || !f) return
    conds = [...panelConditions.value, { id: `c_${Date.now()}`, fieldId: fieldName, operator: filterOpsOf(f)[0] || 'contains', value: undefined, pinned: true }]
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

async function onPasteCells(changes) {
  const tid = tableId.value
  const cells = changes.map(({ row, field, labels, value }) => ({ id: row.id, field: field.field_name,
    ...(labels ? { labels } : { value }) }))
  const old = changes.map(({ row, field }) => ({ id: row.id, field: field.field_name, value: row[field.field_name] ?? null }))
  const preview = previewCells(rows.value, changes)
  rows.value = preview.rows
  ++loadRequestId
  pendingCellWrites++
  let result
  try {
    result = await smartBatchUpdate(tid, cells, true)
    if (tid !== tableId.value) return
    for (const [name, options] of Object.entries(result.fieldOptions || {})) {
      const field = fields.value.find(f => f.field_name === name)
      if (field) field.options = options
    }
    const records = new Map(result.records.map(row => [row.id, row]))
    const appliedKeys = new Set(result.applied.map(cell => `${cell.id}:${cell.field}`))
    rows.value = mergeUpdatedRows(rollbackCells(rows.value, preview.snapshots, appliedKeys), result.records)
    const appliedOld = old.filter(cell => appliedKeys.has(`${cell.id}:${cell.field}`))
    const saved = result.applied.map(cell => ({ id: cell.id, field: cell.field, value: records.get(cell.id)?.[cell.field] ?? null }))
    if (saved.length) undoStack.push({ label: '粘贴单元格',
      undo: async () => { await smartBatchUpdate(tid, appliedOld); await loadGrid(view.value?.id, { silent: true }) },
      redo: async () => { await smartBatchUpdate(tid, saved); await loadGrid(view.value?.id, { silent: true }) },
    })
  } catch (error) {
    if (tid === tableId.value) rows.value = rollbackCells(rows.value, preview.snapshots)
    throw error
  } finally {
    pendingCellWrites--
    scheduleRevisionPoll()
  }
  if (result.applied.length && changes.some(({ field }) => fieldAffectsView(field))) {
    loadGrid(view.value?.id, { silent: true }).catch(() => ElMessage.error('已保存，视图更新失败，请刷新重试'))
  }
  return result
}

async function onCellCommit({ row, field, value }) {
  const old = row[field.field_name]
  if (sameCellValue(old, value)) return   // 未修改：不写库、不刷新
  const tid = tableId.value, viewId = view.value?.id
  ++loadRequestId
  pendingCellWrites++
  // 网格展示行与页面源数据独立：两者同时更新，后续填充不能拿旧源数据覆盖已输入值。
  const preview = previewCells(rows.value, [{ row, field, value }])
  rows.value = preview.rows
  row[field.field_name] = value   // 乐观更新
  try {
    const r = await smartUpdateRecord(tid, row.id, { data: { [field.field_name]: value } })
    if (tid !== tableId.value) return
    rows.value = mergeUpdatedRows(rows.value, [r.record])
    Object.assign(row, r.record)
    undoStack.push({
      label: `编辑 ${field.label}`,
      undo: async () => { await smartUpdateRecord(tid, row.id, { data: { [field.field_name]: old } }); await loadGrid(viewId, { silent: true }) },
      redo: async () => { await smartUpdateRecord(tid, row.id, { data: { [field.field_name]: value } }); await loadGrid(viewId, { silent: true }) },
    })
    // 只在改动影响排序/筛选/分组/聚合结果时重查；否则乐观更新即可（公式/查找由 PATCH 响应带回）
    // 后台同步视图结果，复用未变化的行；单元格保存不显示整表加载遮罩。
    if (field.field_type !== 'checkbox' && fieldAffectsView(field)) {
      loadGrid(view.value?.id, { silent: true }).catch(() => {
        ElMessage.error('已保存，视图更新失败，请刷新重试')
      })
    }
  } catch (e) {
    if (tid === tableId.value) {
      rows.value = rollbackCells(rows.value, preview.snapshots)
      if (sameCellValue(row[field.field_name], value)) row[field.field_name] = old
    }
    ElMessage.error(e.message || '保存失败')
  } finally {
    pendingCellWrites--
    scheduleRevisionPoll()
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
    await alterTable(tableId.value, [{ op: 'update_field', field_name: f.field_name, options: { ...f.options, options: opts } }])
    f.options = { ...f.options, options: opts }
    const value = (f.field_type === 'ai' ? f.options?.outputType : f.field_type) === 'multiSelect'
      ? [...(Array.isArray(row[f.field_name]) ? row[f.field_name] : []), nid]
      : nid
    await onCellCommit({ row, field: f, value })
    ElMessage.success(`已创建选项「${label}」`)
  } catch (e) {
    ElMessage.error(e.message || '创建选项失败')
  }
}

// 添加一行：按当前筛选条件预设初始值（让新记录能命中筛选而显示出来），groupPreset（组内「+」的分组值）优先；
// 新记录按视图排序落位，翻到所在页并编辑它的第一个可见单元格
async function addRow(groupPreset = {}) {
  if (insertingRows.value || !perms.value.can_create) return
  const tid = tableId.value, viewId = view.value?.id
  const preset = {
    ...presetFromFilters({
      conditions: panelConditions.value, conjunction: cfg.value.filters?.conjunction || 'and',
      fields: resolvedFields.value, viewerId: me?.id ?? null, members: members.value, relationRows: relationRows.value,
    }),
    ...groupPreset,
  }
  insertingRows.value = true
  ++loadRequestId
  pendingCellWrites++
  let r
  try {
    r = await smartCreateRecord(tid, { data: preset })
  } finally {
    pendingCellWrites--
    insertingRows.value = false
    scheduleRevisionPoll()
  }
  if (tid !== tableId.value || viewId !== view.value?.id) return
  let newId = r.record.id
  undoStack.push({
    label: '添加行',
    undo: async () => { await smartDeleteRecord(tid, newId); await loadGrid(viewId, { silent: true }) },
    redo: async () => { const result = await smartCreateRecord(tid, { data: preset }); newId = result.record.id; await loadGrid(viewId, { silent: true }) },
  })
  const shown = await applyInsertedRows([r.record], null, 'up', tid, viewId, newId)
  if (shown === false) ElMessage.info('已添加一行，但它不符合当前筛选条件，暂未显示')
  else ElMessage.success('已添加一行')
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
  return deleteSelectedRows(selection.value)
}
async function deleteSelectedRows(selectedRows) {
  if (!perms.value.can_delete || !selectedRows?.length) return
  const snapshot = [...new Map(selectedRows.map(r => [r.id, { ...r }])).values()]
  await ElMessageBox.confirm(`删除选中的 ${snapshot.length} 条记录？`, '批量删除', { type: 'warning' })
  const ids = snapshot.map(r => r.id)
  await smartBatchDelete(tableId.value, ids)
  undoStack.push({
    label: `删除 ${ids.length} 行`,
    undo: async () => {
      for (const s of snapshot) {
        const data = { ...s }
        delete data.id; delete data.created_at; delete data.updated_at
        delete data.owner_id; delete data.tenant_id; delete data.parent_id; delete data.updated_by
        delete data.__key; delete data.__no; delete data.__indent; delete data.__rowType
        await smartCreateRecord(tableId.value, { data })
      }
      loadGrid(view.value?.id)
    },
    redo: async () => { await smartBatchDelete(tableId.value, ids); loadGrid(view.value?.id) },
  })
  selection.value = []
  gridRef.value?.clearSelection()
  ElMessage.success('已删除')
  loadGrid(view.value?.id)
}

async function doUndo() { await undoStack.undo() }
async function doRedo() { await undoStack.redo() }

function onKeydown(e) {
  if (e.key === 'Escape') { activePanel.value = null; if (findVisible.value) closeFind(); return }
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); doUndo() }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); doRedo() }
}

// ---------- 单元格右键菜单操作 ----------
const ctx = reactive({ row: null, field: null })
function onCellMenu({ row, field, rows: rangeRows, cmd, count }) {
  Object.assign(ctx, { row, field })
  const action = cmd === 'delete-rows' ? deleteSelectedRows(rangeRows) : onCtxAction(cmd, count)
  action.catch(e => {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '操作失败')
  })
}
const detail = reactive({ visible: false, record: null })
// 详情记录按 id 跟随最新数据（表格重查后行对象会被替换）
const detailRecord = computed(() => dataRows.value.find(r => r.id === detail.record?.id) || detail.record)
const detailIdx = computed(() => dataRows.value.findIndex(r => r.id === detail.record?.id))
function openDetail(r) {
  automation.visible = false
  detail.record = dataRows.value.find(x => x.id === r.id) || r
  detail.visible = true
}
function syncDetailRow(row) {
  if (!detail.visible || detail.record?.id === row.id) return
  detail.record = dataRows.value.find(record => record.id === row.id) || row
}
// 详情面板 ⋯：生成记录副本 / 删除记录（删除后切到下一条，没有则收起）
async function onDetailAction(cmd, rec) {
  if (cmd === 'duplicate') {
    await duplicateRow(rec)
  } else if (cmd === 'delete') {
    await ElMessageBox.confirm('删除这条记录？', '删除', { type: 'warning' })
    const i = detailIdx.value
    const next = dataRows.value[i + 1] || dataRows.value[i - 1] || null
    await smartDeleteRecord(tableId.value, rec.id)
    if (next) detail.record = next
    else detail.visible = false
    loadGrid(view.value?.id)
  }
}

const insertingRows = ref(false)
async function applyInsertedRows(records, anchorId, direction, tid, viewId, focusId = null) {
  if (tid !== tableId.value || viewId !== view.value?.id) return
  if (focusId != null) gridRef.value?.clearEditing()
  const local = (anchorId != null || page.value === 1) && canInsertLocally(cfg.value, grouped.value, contentPerm.value.managed, viewType.value)
    ? insertViewRows(rows.value, records || [], anchorId, direction, pageSize) : null
  if (local) {
    rows.value = local
    total.value += records.length
  }
  // Sorting/filtering/grouping and summaries are authoritative on the server.
  // Silent loading reconciles changed rows and retains the existing grid instance.
  if (!local || (focusId != null && !local.some(row => row.id === focusId)) || Object.keys(cfg.value.aggregations || {}).length) {
    await loadGrid(viewId, { silent: true, focusId })
  }
  if (focusId != null && tid === tableId.value && viewId === view.value?.id) {
    return gridRef.value?.focusRecord?.(focusId, null, { edit: true })
  }
}
async function duplicateRow(row) {
  if (insertingRows.value || !perms.value.can_create) return
  const tid = tableId.value, viewId = view.value?.id
  insertingRows.value = true
  ++loadRequestId
  pendingCellWrites++
  let result
  try {
    result = await smartDuplicateRecord(tid, row.id)
  } finally {
    pendingCellWrites--
    insertingRows.value = false
    scheduleRevisionPoll()
  }
  await applyInsertedRows([result.record], row.id, 'down', tid, viewId)
}
async function onCtxAction(cmd, count = 1) {
  const { row, field } = ctx
  if (cmd === 'expand') {
    openDetail(row)
  } else if (cmd === 'insert-up' || cmd === 'insert-down') {
    if (insertingRows.value || !perms.value.can_create) return
    const tid = tableId.value, viewId = view.value?.id
    insertingRows.value = true
    ++loadRequestId
    pendingCellWrites++
    let result
    try {
      result = await smartInsertRecords(tid, row.id, {
        direction: cmd === 'insert-up' ? 'up' : 'down', count, view_id: viewId,
        data: presetFromFilters({
          conditions: panelConditions.value, conjunction: cfg.value.filters?.conjunction || 'and',
          fields: resolvedFields.value, viewerId: me?.id ?? null, members: members.value, relationRows: relationRows.value,
        }),
      })
    } finally {
      pendingCellWrites--
      insertingRows.value = false
      scheduleRevisionPoll()
    }
    const shown = await applyInsertedRows(result.records, row.id, cmd === 'insert-up' ? 'up' : 'down', tid, viewId, result.ids[0])
    if (tid === tableId.value && viewId === view.value?.id) {
      if (shown === false) ElMessage.info(`已插入 ${result.ids.length} 行，但在当前筛选或折叠分组中不可见`)
      else ElMessage.success(`已插入 ${result.ids.length} 行`)
    }
  } else if (cmd.startsWith('viz-')) {
    fieldMenu.field = field
    if (cmd === 'viz-more') await addMoreCharts()
    else await addVizChart(cmd === 'viz-pie' ? 'pie' : 'bar')
  } else if (cmd === 'reminder') {
    Object.assign(reminder, { visible: true, field })
  } else if (cmd === 'automation') {
    openAutomation()
  } else if (cmd === 'only' || cmd === 'exclude') {
    if (!field) return
    const op = cmd === 'only' ? 'eq' : 'neq'
    const c = { id: `c_${Date.now()}`, fieldId: field.field_name, operator: op, value: row[field.field_name] }
    onFiltersChange([...panelConditions.value, c])
  } else if (cmd === 'duplicate') {
    await duplicateRow(row)
  } else if (cmd === 'delete') {
    await ElMessageBox.confirm('删除这条记录？', '删除', { type: 'warning' })
    await smartDeleteRecord(tableId.value, row.id)
    loadGrid(view.value?.id)
  }
}
function navDetail(step) {
  const i = detailIdx.value + step
  if (i >= 0 && i < dataRows.value.length) detail.record = dataRows.value[i]
}

// ---------- 字段操作 ----------
const fieldDialog = reactive({ visible: false, field: null, insertCtx: null, preset: null, addAgain: false, at: null })   // at：双击表头的鼠标位置，编辑框在此弹出
const allTables = ref([])

function openFieldConfig(f, insertCtx = null, at = null) {
  if (f?.field_type === 'ai') {   // AI 字段：场景市场面板编辑
    Object.assign(aiPanel, { visible: true, field: f, label: f.label, at, x: window.innerWidth - 40, y: 90 })
    return
  }
  fieldDialog.field = f
  fieldDialog.insertCtx = insertCtx
  fieldDialog.scrollToEnd = false
  fieldDialog.preset = null
  fieldDialog.addAgain = false
  fieldDialog.at = at
  fieldDialog.visible = true
}

// 添加列类型网格浮层（AddFieldPop）：表格末尾「+」/表格设置「新增字段」/列头「插入字段」之外的统一入口
const addFieldPop = reactive({ visible: false, x: 0, y: 0 })
const lastAddFieldPos = { x: 200, y: 100 }
function openAddFieldPop(x, y, scrollToEnd = false) {
  Object.assign(addFieldPop, { visible: true, x, y, scrollToEnd })
  lastAddFieldPos.x = x; lastAddFieldPos.y = y
}
function onAddFieldAt(e) {
  // 事件可能来自网格表头（MouseEvent）或设置面板（同样透传 MouseEvent）
  const x = e?.clientX ?? window.innerWidth - 520
  const y = e?.clientY ?? 120
  openAddFieldPop(x, y, !!e?.target?.closest?.('.th-add-col'))
}
function onTypePick({ field_type, label }, again = false) {
  addFieldPop.visible = false
  fieldDialog.field = null
  fieldDialog.insertCtx = null
  fieldDialog.scrollToEnd = !!addFieldPop.scrollToEnd
  fieldDialog.preset = { field_type, label }
  fieldDialog.addAgain = again
  fieldDialog.visible = true
}

const DATA_TYPE_MAP = {
  text: 'varchar', singleSelect: 'varchar', multiSelect: 'json', number: 'decimal', percent: 'decimal',
  currency: 'decimal', date: 'datetime', checkbox: 'bool', url: 'json', phone: 'varchar', email: 'varchar',
  member: 'json', progress: 'decimal', image: 'image', file: 'json', autoNumber: 'serial', relation: 'json',
  lookup: 'json', formula: 'varchar', createdBy: 'varchar', lastModifiedBy: 'varchar',
  createdTime: 'datetime', lastModifiedTime: 'datetime', ai: 'json',
}
const WIDGET_MAP = {
  text: 'input', singleSelect: 'select', multiSelect: 'select', number: 'number', percent: 'number',
  currency: 'number', date: 'datetime-picker', checkbox: 'switch', url: 'input', phone: 'input',
  email: 'input', member: 'input', progress: 'number', image: 'image-uploader', file: 'input',
  autoNumber: 'serial', relation: 'input', lookup: 'input', formula: 'input', createdBy: 'input',
  lastModifiedBy: 'input', createdTime: 'datetime-picker', lastModifiedTime: 'datetime-picker', ai: 'input',
}

function buildFieldPayload(field_type, label, config) {
  const options = { ...config }
  if (field_type === 'autoNumber') {
    // segments → serial pattern（与后端 autonumber_segments_to_pattern 同规则）
    const pattern = config.numberType !== 'custom' ? '{0}' : (config.segments || []).map(s => {
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
    const options = field_type === 'autoNumber' ? buildFieldPayload(field_type, label, config).options : config
    const op = { op: 'update_field', field_name: f.field_name, label, options, field_type }
    if (f.field_type !== field_type) op.data_type = DATA_TYPE_MAP[field_type]
    if (field_type === 'lookup' || f.field_type === 'lookup') {
      ++loadRequestId
      ++referenceLoadVersion
      pendingCellWrites++
      try {
        await alterTable(tableId.value, [op])
        fieldDialog.visible = false
        await reloadLookupGrid()
      } catch (error) {
        ElMessage.error(error.message || '引用设置保存失败')
      } finally {
        pendingCellWrites--
        scheduleRevisionPoll()
      }
      return
    }
    await alterTable(tableId.value, [op])
    fieldDialog.visible = false
    await reloadMeta()
    loadGrid(view.value?.id)
  } else {
    const payload = buildFieldPayload(field_type, label, config)
    await alterTable(tableId.value, [{ op: 'add_field', field: payload }])
    fieldDialog.visible = false
    if (fieldDialog.scrollToEnd && !fieldDialog.insertCtx) gridRef.value?.requestScrollToEnd?.()
    await reloadMeta()
    // 插入上下文定位（编组菜单/列头菜单「插入字段」；AddFieldPop 无上下文保持末尾）
    if (fieldDialog.insertCtx) await placeNewField(payload.field_name, fieldDialog.insertCtx)
    // 表单「添加新字段到表单」：同步建表列 + 加入表单题目（双向绑定，§12.1）
    if (pendingFormAdd) { pendingFormAdd = false; formRef.value?.addItem(payload.field_name) }
    // 普通新增列没有已有数据，只更新列结构，保留当前行与滚动位置。
    // 服务端计算/系统字段仍需读取实际值，但不触发整表 loading。
    if (['formula', 'lookup', 'autoNumber', 'createdTime', 'lastModifiedTime', 'createdBy', 'lastModifiedBy', 'ai'].includes(field_type)
      || config.formula || config.serial) {
      await loadGrid(view.value?.id, { silent: true })
    }
    // AddFieldPop 的「Tab 再添加一列」：保存完成后重新打开类型网格
    if (fieldDialog.addAgain) { fieldDialog.addAgain = false; openAddFieldPop(lastAddFieldPos.x, lastAddFieldPos.y, fieldDialog.scrollToEnd) }
  }
}

async function reloadMeta() {
  const meta = await getTable(tableId.value)
  fields.value = meta.fields
  loadRefSources()   // 字段增删改后引用选项/联动源可能变化
}

async function reloadLookupGrid() {
  const tid = tableId.value
  const requestId = ++loadRequestId
  const referenceVersion = ++referenceLoadVersion
  pendingCellWrites++
  try {
    // Keep the old cells visible until metadata, source formats and values are ready.
    const [meta, grid] = await Promise.all([
      getTable(tid), smartGrid(tid, { view_id: view.value?.id, page: page.value, page_size: pageSize }),
    ])
    const sources = await prepareRefSources(meta.fields)
    if (tid !== tableId.value || requestId !== loadRequestId || referenceVersion !== referenceLoadVersion) return
    // Vue batches these assignments into one render; no old/new format mismatch.
    refFieldsCache.value = sources.fieldCache
    refRowsCache.value = sources.rowCache
    fields.value = meta.fields
    await applyGridResult(grid)
  } catch (error) {
    ElMessage.error(error.message || '引用结果刷新失败，请重试')
  } finally {
    pendingCellWrites--
    scheduleRevisionPoll()
  }
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
  groupMenu.visible = false
  const offset = event.type === 'contextmenu' ? 6 : 0
  Object.assign(fieldMenu, { visible: true, x: event.clientX + offset, y: event.clientY + offset, field })
}
watch(() => fieldMenu.visible, (visible, _, onCleanup) => {
  if (!visible) return
  const closeOutside = event => {
    if (!event.target?.closest?.('.field-menu-layer .fm')) fieldMenu.visible = false
  }
  // Observe outside presses without intercepting the cell's native interaction.
  document.addEventListener('pointerdown', closeOutside, true)
  onCleanup(() => document.removeEventListener('pointerdown', closeOutside, true))
}, { flush: 'sync' })

// 列头「筛选」：贴列头的单字段筛选浮层（与 pin 胶囊共用 FieldFilterPop）
const fieldFilter = reactive({ visible: false, x: 0, y: 0, field: null })
function openFieldFilter(field, x, y) {
  fieldMenu.visible = false
  Object.assign(fieldFilter, { visible: true, field,
    x: Math.max(8, Math.min(x, window.innerWidth - 492)), y: Math.max(8, Math.min(y, window.innerHeight - 560)) })
}
// 列头漏斗点击：面板贴在该列右侧、与表头顶部对齐（参照 表头-过滤按钮点击-多选.png）
function openFieldFilterAt(field, rect) {
  const x = rect.right + 492 <= window.innerWidth ? rect.right + 2 : rect.left - 482
  openFieldFilter(field, x, rect.top)
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
  } else if (cmd === 'freeze') { if (menuFreezeBlocked.value) return; fieldMenu.visible = false; patchConfig({ frozenFieldId: menuFieldFrozen.value ? null : f.field_name }, { reload: false }) }
  else if (cmd === 'hide') { fieldMenu.visible = false; patchConfig({ fieldVisibility: { ...(cfg.value.fieldVisibility || {}), [f.field_name]: false } }, { reload: false }) }
  else if (cmd === 'autoFit') { fieldMenu.visible = false; autoFitFields([f.field_name]) }
  else if (cmd === 'duplicate') { fieldMenu.visible = false; await smartDuplicateField(tableId.value, f.field_name); reloadMeta(); loadGrid(view.value?.id) }
  else if (cmd === 'delete') { fieldMenu.visible = false; await deleteField(f) }
  else if (cmd === 'perm') { fieldMenu.visible = false; openPermPanel(entry.value?.id) }
  else if (cmd === 'kanban') { fieldMenu.visible = false; await createKanban(f) }
  else if (cmd === 'aiTags') { fieldMenu.visible = false; Object.assign(aiTags, { visible: true, field: f }) }
  else if (cmd === 'reminder') { fieldMenu.visible = false; Object.assign(reminder, { visible: true, field: f }) }
}

// ================= V3：协作与智能 =================
const menuFieldFrozen = computed(() => Boolean(cfg.value.frozenFieldId)
  && cfg.value.frozenFieldId === fieldMenu.field?.field_name)
function freezeFits(fieldName) {
  if (!fieldName || !gridAreaWidth.value) return false
  const order = new Map((cfg.value.fieldOrder || []).map((name, i) => [name, i]))
  const visible = fields.value.filter(f => cfg.value.fieldVisibility?.[f.field_name] !== false)
    .sort((a, b) => (order.get(a.field_name) ?? 999) - (order.get(b.field_name) ?? 999))
  const layout = buildColumnLayout(visible, columnGroups.value, fieldName)
  const frozenWidth = layout.filter(n => n.fixed === 'left')
    .flatMap(n => n.isGroup ? n.fields : [n.field])
    .reduce((sum, f) => sum + Number(cfg.value.colWidths?.[f.field_name] || 160), 75)
  // 留出至少 120px 用于滚动列与滚动条，避免冻结区域遮住右侧内容。
  return frozenWidth <= gridAreaWidth.value - 120
}
const menuFreezeBlocked = computed(() => !menuFieldFrozen.value && !freezeFits(fieldMenu.field?.field_name))
const menuIsSelect = computed(() => ['singleSelect', 'multiSelect'].includes(fieldMenu.field?.field_type))
const menuIsSingleSelect = computed(() => fieldMenu.field?.field_type === 'singleSelect')
const VIZ_CHARTS = [
  { type: 'bar', icon: 'chart-bar', label: '添加柱状图', desc: '按选项统计行数' },
  { type: 'pie', icon: 'pie', label: '添加饼图', desc: '按选项统计占比' },
]

// ---------- 内容权限 ----------
const permPanel = reactive({ visible: false, focus: null })
function openPermPanel(focusEntryId = null) {
  automation.visible = false
  Object.assign(permPanel, { visible: !permPanel.visible || !!focusEntryId, focus: focusEntryId })
}

// ---------- 自动化 ----------
const automation = reactive({ visible: false, draft: null })
const reminder = reactive({ visible: false, field: null })
function openAutomation(draft = null) {
  detail.visible = false
  permPanel.visible = false
  Object.assign(automation, { visible: true, draft })
}
// 表单「设置自动化提醒」：预置「添加新记录时 → 发送消息」
function formAutomationDraft() {
  const primary = fields.value[0]
  return {
    name: '表单提交提醒', enabled: true,
    trigger: { type: 'recordCreated', rowConditions: [], filter: { match: 'all', conditions: [] } },
    actions: [{ id: `a${Date.now().toString(36)}`, type: 'sendMessage', channel: 'docMessage', to: me?.id ? [me.id] : [],
                toFields: [], webhookUrl: '', title: '收到新的表单提交',
                content: [{ t: 'text', v: '表单收到新提交：' },
                          ...(primary ? [{ t: 'var', var: { kind: 'step', step: 1, key: 'field', field: primary.field_name },
                                           label: `第1步添加新记录的 ${primary.label}` }] : [])],
                buttons: [{ label: '查看记录' }] }],
  }
}

// ---------- 表单 ----------
const formRef = ref(null)
let pendingFormAdd = false
async function generateForm() {
  const n = views.value.filter(v => v.type === 'form').length
  try {
    const r = await smartCreateView(tableId.value, { type: 'form', name: n ? `表单 ${n + 1}` : '表单' })
    views.value.push(r.view)
    switchView(r.view)
    ElMessage.success('已按表格字段生成表单')
  } catch (e) {
    ElMessage.error(e.message || '生成表单失败')
  }
}
async function onFormSave(form) {
  if (!view.value) return
  const config = { ...(view.value.config || {}), form }
  delete config.filtersScope
  try {
    const r = await smartUpdateView(view.value.id, { config })
    view.value = { ...view.value, config: { ...view.value.config, form: r.view.config.form } }
  } catch (e) {
    ElMessage.error(e.message || '表单保存失败')
  }
}
function onFormAddField(e) { pendingFormAdd = true; onAddFieldAt(e) }
async function onFormDeleteField(field) {
  try { await deleteField(field) }
  catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '删除字段失败')
  }
}
async function onFormOptions(field, options) {
  const f = fields.value.find(x => x.field_name === field.field_name)
  if (!f) return
  try {
    await alterTable(tableId.value, [{ op: 'update_field', field_name: f.field_name, options: { ...f.options, options } }])
    await reloadMeta()
  } catch (e) {
    ElMessage.error(e.message || '选项保存失败')
  }
}

// ---------- 看板 ----------
async function createKanban(f) {
  try {
    const r = await smartCreateView(tableId.value, { type: 'kanban', name: `${f.label}看板`, config: { kanban: { groupField: f.field_name } } })
    views.value.push(r.view)
    switchView(r.view)
  } catch (e) {
    ElMessage.error(e.message || '新建看板失败')
  }
}
function onKanbanMove(row, field, value) { onCellCommit({ row, field, value }).then(() => loadGrid(view.value?.id)) }
function onKanbanAdd(optionId) {
  const fn = cfg.value.kanban?.groupField
  addRow(fn && optionId ? { [fn]: optionId } : {})
}

// ---------- 数据可视化：生成图表到仪表盘 ----------
async function ensureDashboard(d, name) {
  if (d) return d
  const r = await smartCreateEntry(doc.value.id, { type: 'dashboard', name })
  await loadDocEntries()
  return r.entry
}
async function addVizChart(chartType, d) {
  const f = fieldMenu.field
  fieldMenu.visible = false
  if (!f) return
  try {
    const dash = await ensureDashboard(d, `${entry.value?.name || '表格'}仪表盘`)
    await smartCreateWidget(dash.id, {
      title: `${f.label}${chartType === 'pie' ? '占比' : '统计'}`, chart_type: chartType,
      config: { sourceTableId: tableId.value, dimension: f.field_name, metric: { agg: 'count', field: null },
                splitMulti: true, sort: { by: 'value', direction: 'desc' } },
    })
    await ElMessageBox.confirm(`已将「${f.label}」${chartType === 'pie' ? '饼图' : '柱状图'}添加到「${dash.name}」，是否前往查看？`, '已添加图表',
      { confirmButtonText: '前往查看', cancelButtonText: '留在此页', type: 'success' })
    router.push(`/smart/dashboard/${dash.id}`)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '添加图表失败')
  }
}
async function addMoreCharts(d) {
  const f = fieldMenu.field
  fieldMenu.visible = false
  if (!f) return
  try {
    const dash = await ensureDashboard(d, `${entry.value?.name || '表格'}仪表盘`)
    router.push({ path: `/smart/dashboard/${dash.id}`, query: { addChart: 1, table: tableId.value, dim: f.field_name, title: `${f.label}统计` } })
  } catch (e) {
    ElMessage.error(e.message || '打开仪表盘失败')
  }
}

// ---------- AI 字段 ----------
const aiPanel = reactive({ visible: false, x: 0, y: 0, at: null, field: null, label: '' })
const aiFormulaDlg = reactive({ visible: false })
const aiTags = reactive({ visible: false, field: null })
function onAiFromAddField({ label, x, y }) {
  addFieldPop.visible = false
  Object.assign(aiPanel, { visible: true, field: null, label, at: null, x: x + 480, y })
}
// run：first5 = 生成前 5 行 / all = 生成全部 / none = 仅保存配置；编辑态 null = 仅保存
async function onAiSave({ label, config, run }) {
  const editing = aiPanel.field
  aiPanel.visible = false
  try {
    let fn
    if (editing) {
      await alterTable(tableId.value, [{ op: 'update_field', field_name: editing.field_name, label, options: config, field_type: 'ai' }])
      fn = editing.field_name
    } else {
      const payload = buildFieldPayload('ai', label, config)
      await alterTable(tableId.value, [{ op: 'add_field', field: payload }])
      fn = payload.field_name
    }
    await reloadMeta()
    if (run === 'first5' || run === 'all') {
      // 前 5 行 = 当前视图（排序/筛选/分组后）看到的前 5 条数据行，而不是按记录 id 的前 5 条
      const first5 = dataRows.value.filter(r => !r.__rowType && r.id != null).slice(0, 5).map(r => r.id)
      const r = await smartAiRun(tableId.value, fn, run === 'first5' ? { record_ids: first5 } : { scope: 'all' })
      ElMessage.success(r.queued ? `AI 正在生成 ${r.queued} 行…` : '已保存 AI 字段')
    } else {
      ElMessage.success(editing ? '已保存 AI 字段设置' : '已保存 AI 字段配置，可在列头 ✦ 按钮中随时生成')
    }
    loadGrid(view.value?.id)
  } catch (e) {
    if (!handleBillingError(e)) ElMessage.error(e.message || '保存 AI 字段失败')
  }
}
// AI 列重新生成：all 全部 / empty 仅空白行 / failed 失败行 / rows 指定行（选中单元格的「重新生成此行」）
async function runAiField(f, scope = 'all', recordIds = null) {
  if (!f) return
  try {
    const r = await smartAiRun(tableId.value, f.field_name, scope === 'rows' ? { record_ids: recordIds } : { scope })
    ElMessage.success(r.queued ? `AI 正在生成 ${r.queued} 行…` : (scope === 'failed' ? '没有生成失败的行' : '没有需要生成的行'))
    loadGrid(view.value?.id, { silent: true })
  } catch (e) {
    if (!handleBillingError(e)) ElMessage.error(e.message || '生成失败')
  }
}
async function onAiFormulaApply({ formula, returnType, label }) {
  aiFormulaDlg.visible = false
  try {
    const payload = buildFieldPayload('formula', label || '公式', { formula, returnType })
    await alterTable(tableId.value, [{ op: 'add_field', field: payload }])
    await reloadMeta()
    loadGrid(view.value?.id)
    ElMessage.success('已添加公式列')
  } catch (e) {
    ElMessage.error(e.message || '添加公式列失败')
  }
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
  smartFieldStats(tableId.value, { field_name: field.field_name, view_id: view.value?.id })
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
const groupDialog = reactive({ visible: false, id: null, name: '', members: [], at: null })
const groupNameRef = ref(null)
const placeGroupDialog = useButtonAnchoredDialog(() => groupNameRef.value?.parentElement, () => groupDialog.at, () => groupDialog.visible)
const groupFieldsOpen = ref(false)
function toggleGroupField(field) {
  const name = field.field_name
  groupDialog.members = groupDialog.members.includes(name)
    ? groupDialog.members.filter(n => n !== name) : [...groupDialog.members, name]
}
function focusGroupName() {
  groupNameRef.value?.focus()
  groupNameRef.value?.select()
}
function openGroupDialog(field, group = null, at = null) {
  groupFieldsOpen.value = false
  fieldMenu.visible = false
  Object.assign(groupDialog, group
    ? { visible: true, id: group.id, name: group.name, members: [...(group.field_names || [])], at }
    : { visible: true, id: null, name: '', members: field ? [field.field_name] : [], at })
}
useNonModalOutsideClose(() => groupDialog.visible, () => { groupDialog.visible = false })
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
  else await smartCreateColumnGroup(tableId.value, { name: groupDialog.name || '编组', field_names: members })
  groupDialog.visible = false
  columnGroups.value = (await smartListColumnGroups(tableId.value)).groups
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
  columnGroups.value = (await smartListColumnGroups(tableId.value)).groups
}

// 列头菜单「移入编组 ▸」：切换语义（已在该组则移出）
async function moveToGroup(g) {
  const f = fieldMenu.field
  if (!f) return
  fieldMenu.visible = false
  await setFieldGroup(f.field_name, (g.field_names || []).includes(f.field_name) ? null : g)
}

async function deleteField(f) {
  const { deps } = await smartFieldDeps(tableId.value, f.field_name)
  const depText = deps.length
    ? `\n该字段被以下视图引用：${deps.map(d => `「${d.viewName}」(${d.usages.join('/')})`).join('、')}，删除后这些配置将失效。`
    : ''
  await ElMessageBox.confirm(`删除字段「${f.label}」？存量数据将一并清除。${depText}`, '删除字段', { type: 'warning' })
  await alterTable(tableId.value, [{ op: 'delete_field', field_name: f.field_name }])
  await reloadMeta()
  // Keep the mounted grid while synchronizing any affected filters/groups/data.
  // The column-signature watcher restores its viewport after column registration.
  await loadGrid(view.value?.id, { silent: true })
}

// ---------- 表格设置面板回调 ----------
function onToggleVisible(f, visible) {
  patchConfig({ fieldVisibility: { ...(cfg.value.fieldVisibility || {}), [f.field_name]: !visible ? false : true } }, { reload: false })
}
function onReorder(order) { patchConfig({ fieldOrder: order }, { reload: false }) }
async function onFieldAction(cmd, f) {
  if (cmd === 'edit') openFieldConfig(f)
  else if (cmd === 'delete') deleteField(f)
  else if (cmd === 'duplicate') { await smartDuplicateField(tableId.value, f.field_name); reloadMeta(); loadGrid(view.value?.id) }
  else if (cmd === 'newGroup') openGroupDialog(f)
}

// ---------- 编组组头菜单（设计稿 PixPin_2026-10-16_00-40-59） ----------
const groupMenu = reactive({ visible: false, x: 0, y: 0, group: null })
function onGroupMenu(group, e) {
  fieldMenu.visible = false
  const offset = e.type === 'contextmenu' ? 6 : 0
  Object.assign(groupMenu, { visible: true, x: e.clientX + offset, y: e.clientY + offset, group })
}
watch(() => groupMenu.visible, (visible, _, onCleanup) => {
  if (!visible) return
  const closeOutside = event => {
    if (!event.target?.closest?.('.group-menu-layer .fm')) groupMenu.visible = false
  }
  document.addEventListener('pointerdown', closeOutside, true)
  onCleanup(() => document.removeEventListener('pointerdown', closeOutside, true))
}, { flush: 'sync' })

async function groupAct(cmd) {
  const g = groupMenu.group
  groupMenu.visible = false
  if (!g) return
  const members = g.field_names || []
  if (cmd === 'edit') openGroupDialog(null, g)
  else if (cmd === 'insertRight' || cmd === 'insertLeft' || cmd === 'insertInside') {
    openFieldConfig(null, { mode: { insertRight: 'right', insertLeft: 'left', insertInside: 'inside' }[cmd], group: g })
  } else if (cmd === 'duplicate') await duplicateGroup(g)
  else if (cmd === 'freeze') {
    if (!freezeFits(members[members.length - 1])) { ElMessage.warning('无法冻结，窗口宽度不足'); return }
    patchConfig({ frozenFieldId: members[members.length - 1] }, { reload: false })
  }
  else if (cmd === 'autoFit') autoFitGroup(g)
  else if (cmd === 'hide') {
    const vis = { ...(cfg.value.fieldVisibility || {}) }
    members.forEach(n => { vis[n] = false })
    patchConfig({ fieldVisibility: vis }, { reload: false })
  } else if (cmd === 'dissolve') {
    await ElMessageBox.confirm(`解散编组「${g.name}」？字段保留。`, '解散编组', { type: 'warning' })
    await smartDeleteColumnGroup(g.id)
    columnGroups.value = (await smartListColumnGroups(tableId.value)).groups
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
    columnGroups.value = (await smartListColumnGroups(tableId.value)).groups
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
    const r = await smartDuplicateField(tableId.value, fn)
    newNames.push(r.field_name)
  }
  await reloadMeta()
  await smartCreateColumnGroup(tableId.value, { name: `${g.name} 副本`, field_names: newNames })
  columnGroups.value = (await smartListColumnGroups(tableId.value)).groups
  const base = cfg.value.fieldOrder?.length ? [...cfg.value.fieldOrder] : fields.value.map(f => f.field_name)
  const order = base.filter(n => !newNames.includes(n))
  const last = (g.field_names || [])[(g.field_names || []).length - 1]
  let idx = last ? order.indexOf(last) : -1
  order.splice((idx < 0 ? order.length : idx) + 1, 0, ...newNames)
  patchConfig({ fieldOrder: order }, { reload: false })
  loadGrid(view.value?.id)
}

// 自动调整列宽：结合当前行高估算文本换行和标签排布；各入口共用。
function autoFitFields(names) {
  const ctx = document.createElement('canvas').getContext('2d')
  const measured = new Map()
  const fontSize = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--st-font-size')) || 14
  const measure = (text, size = fontSize) => {
    const key = `${size}:${text}`
    if (!measured.has(key)) {
      ctx.font = `${size}px "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif`
      measured.set(key, ctx.measureText(String(text)).width)
    }
    return measured.get(key)
  }
  const height = rowHeightPixels(cfg.value.rowHeight)
  const widths = { ...(cfg.value.colWidths || {}) }
  const sampleRows = dataRows.value.slice(0, 200)
  const fieldsByName = new Map(resolvedFields.value.map(field => [field.field_name, field]))
  for (const fn of names) {
    const f = fieldsByName.get(fn)
    if (!f) continue
    const type = f.field_type === 'ai' ? f.options?.outputType : f.field_type
    if (type === 'checkbox') { widths[fn] = 80; continue }
    const isDate = ['date', 'createdTime', 'lastModifiedTime'].includes(type)
    let w = measure(f.label) + 56   // 图标/排序标/▾/内边距
    // Also size empty date columns for their selected format; use double-digit month/day.
    if (isDate) w = Math.max(w, 120, measure(formatDate('2026-12-28T23:59:00', f.options || {})) + 24)
    for (const r of sampleRows) {
      const v = r[fn]
      if (v == null || v === '') continue
      const values = Array.isArray(v) ? v : [v]
      let contentWidth
      if (['singleSelect', 'multiSelect'].includes(type)) {
        const tags = resolveEnumTags(f.options?.options, v)
        contentWidth = wrappedTagWidth(tags.map(tag => measure(tag.label) + (tags.length === 1 ? 16 : 12)), height)
      } else if (type === 'member') {
        contentWidth = wrappedTagWidth(values.map(id => measure(memberDir.value.get(Number(id))?.name || `#${id}`) + 36), height)
      } else if (type === 'relation') {
        const labels = relationDir.value.get(f.options?.targetTableId)
        contentWidth = wrappedTagWidth(values.map(id => measure(labels?.get(id) ?? labels?.get(Number(id)) ?? `#${id}`) + 30), height)
      } else if (type === 'file') {
        contentWidth = wrappedTagWidth(values.map(file => measure(file.name || '文件') + 34), height)
      } else if (type === 'text' || type === 'url') {
        contentWidth = wrappedTextWidth(type === 'url' ? (v.text || v.url || '') : v, height, measure)
      } else {
        const text = isDate ? formatDate(v, f.options || {}) : (Array.isArray(v) ? v.join('、') : String(v))
        contentWidth = measure(text)
      }
      w = Math.max(w, contentWidth + 24)
    }
    const minWidth = type === 'progress' ? 180 : type === 'member' ? 120 : 80
    widths[fn] = Math.round(Math.min(Math.max(w, minWidth), 300))
  }
  patchConfig({ colWidths: widths }, { reload: false })
  gridRef.value?.applyColumnWidths?.(Object.fromEntries(names.map(name => [name, widths[name]])))
    ?.catch(error => ElMessage.error(error.message || '列宽调整失败'))
}
function autoFitAllFields() {
  activePanel.value = null
  autoFitFields(fields.value.map(field => field.field_name))
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


async function loadInitialTable() {
  initialLoading.value = true
  initialError.value = ''
  try {
    await loadAll()
    pageLoaded = true
  } catch (e) {
    initialError.value = e.message || '工作表加载失败'
    return
  } finally {
    initialLoading.value = false
  }
  // 通知链接 ?record=<id>：直接展开该记录详情（自动化消息「查看记录」）
  const rid = Number(entryQuery.record)
  if (rid) {
    const r = dataRows.value.find(x => x.id === rid)
    if (r) openDetail(r)
  }
  listTables().then(r => { allTables.value = Array.isArray(r) ? r : (r.tables || []) }).catch(() => {})
}
onMounted(loadInitialTable)
onActivated(() => {
  pageActive = true
  if (pageLoaded) loadAll({ silent: true }).catch(e => ElMessage.error(e.message))
  scheduleAiPoll()
  window.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onDocClick)
  document.addEventListener('contextmenu', onDocClick)
})
onDeactivated(() => {
  pageActive = false
  ++loadRequestId
  clearTimeout(revisionTimer)
  clearTimeout(aiPollTimer)
  window.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('contextmenu', onDocClick)
  activePanel.value = null
  closeFind()
  for (const panel of [fieldDialog, addFieldPop, fieldMenu, fieldFilter, permPanel,
    automation, reminder, aiPanel, aiFormulaDlg, aiTags, statMenu, groupDialog, groupMenu]) {
    panel.visible = false
  }
})
onUnmounted(() => {
  pageActive = false
  ++loadRequestId
  clearTimeout(revisionTimer)
  gridAreaObserver?.disconnect()
  clearTimeout(aiPollTimer)
  window.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('contextmenu', onDocClick)
})
</script>

<style scoped>
.st-page { display: flex; gap: 12px; height: 100%; min-width: 0; box-sizing: border-box; padding: 6px 12px 12px 12px; background: #fff; }
.st-initial { flex: 1; display: flex; align-items: center; justify-content: center; gap: 12px; color: var(--st-text-2); font-size: var(--st-font-size); }
.st-table-pane { display: flex; flex-direction: column; flex: 1; min-width: 0; min-height: 0; }
.st-page :deep(.view-tabs) { height: 40px; box-sizing: border-box; flex-shrink: 0; border-bottom: 0; padding-left: 0; }
.st-page :deep(.rd-panel) { padding: 0; }
.st-page :deep(.rd-top) { height: 40px; box-sizing: border-box; flex-shrink: 0; margin: 0; }
.st-panel { display: flex; flex-direction: column; flex: 1; min-height: 0; min-width: 0; border: 1px solid var(--st-border); border-radius: 8px; overflow: hidden; background: #fff; box-shadow: 0 2px 4px rgba(31, 45, 61, .04), 0 4px 10px rgba(31, 45, 61, .10); }
/* 表格区 + 右侧详情面板并排：面板占位，表格区收窄 */
.st-body { display: flex; flex: 1; min-height: 0; }
.st-main { display: flex; flex-direction: column; flex: 1; min-width: 0; min-height: 0; }
.toolbar { display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-bottom: 1px solid var(--st-border); }
/* 幽灵按钮（对齐参照）：图标+文字 13px，hover 浅灰；生效条件=浅蓝胶囊+计数 */
.tb-btn {
  display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 8px;
  border: none; background: transparent; border-radius: 6px; cursor: pointer;
  font-size: var(--st-font-size); color: var(--st-text-2); white-space: nowrap;
}
.tb-btn .st-icon { color: var(--st-text-2); }
.tb-btn:hover { background: var(--st-bg-hover); }
.tb-btn:disabled { color: var(--st-disabled); cursor: not-allowed; background: transparent; }
.tb-btn:disabled .st-icon { color: var(--st-disabled); }
/* 生效态：筛选/分组/排序/填色 = 浅灰底深色字 */
.tb-btn.on, .tb-btn.open { background: #E8E9EB; color: var(--st-text-2); }
.tb-btn.on .st-icon, .tb-btn.open .st-icon { color: var(--st-text-2); }
.tb-scope { color: var(--st-text-2); margin-left: 4px; }   /* 灰底按钮上的次要说明：中灰（原浅蓝随按钮改灰底一起换掉） */
/* 行高菜单 */
.rh-menu { display: flex; flex-direction: column; margin: -14px -16px -12px; }
.rh-item { display: flex; align-items: center; gap: 10px;  padding: 0 16px 0 12px; margin: 0 6px; border-radius: 6px; cursor: pointer; font-size: var(--st-font-size); color: var(--st-text-2);  height: var(--st-list-item-height); box-sizing: border-box; }
.rh-item:hover { background: var(--st-bg-hover); }
.rh-check { width: 16px; color: var(--st-primary); font-size: var(--st-font-size); }
.rh-ico { color: var(--st-text-2); }
.rh-custom { display: flex; align-items: center; gap: 10px; border-top: 1px solid var(--st-border); margin-top: 4px; padding: 12px 18px; font-size: var(--st-font-size); color: var(--st-text-2); }
.rh-num { width: 56px; }
.rh-num :deep(.el-input__inner) { text-align: center; }
.tb-btn.tb-add { color: var(--st-primary); font-weight: 500; }
.tb-btn.tb-add .st-icon { color: var(--st-primary); }
.tb-sep { width: 1px; height: 16px; background: var(--st-border); margin: 0 6px; flex: none; }
.tb-right { margin-left: auto; display: flex; align-items: center; gap: 4px; }
.tb-ico {
  display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px;
  border: none; background: transparent; border-radius: 6px; cursor: pointer; color: var(--st-text-2);
}
.tb-ico:hover { background: var(--st-bg-hover); color: var(--st-text-2); }
.tb-ico:disabled { color: var(--st-disabled); cursor: not-allowed; background: transparent; }
/* pin 的条件胶囊：浅灰底圆角块（类型图标+字段名+⌄） */
.chip {
  display: inline-flex; align-items: center; gap: 4px; background: var(--st-bg-hover);
  border-radius: 6px; padding: 4px 8px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer;
}
.chip .st-icon { color: var(--st-text-3); }
.chip:hover { background: var(--st-bg-active); }
.chip-edit { display: flex; gap: 8px; align-items: center; }
.tb-selected { font-size: var(--st-font-size); color: var(--st-text-2); white-space: nowrap; padding: 0 4px; }
.tb-btn.tb-danger { color: var(--el-color-danger); }
.tb-btn.tb-danger:hover { background: var(--el-color-danger-light-9); }
/* 分页条：紧凑（36px），紧跟表格 */
.pager { height: 32px; flex: 0 0 32px; padding: 0; display: flex; align-items: center; justify-content: center; }
.fm-mask { position: fixed; inset: 0; z-index: 3000; }
.field-menu-layer, .group-menu-layer { pointer-events: none; }
.field-menu-layer > .fm, .group-menu-layer > .fm { pointer-events: auto; }
.fm:not(.smart-menu) { position: fixed; background: #fff; border-radius: 8px; box-shadow: var(--st-shadow-pop); padding: 4px; min-width: min(170px, calc(100vw - 16px)); max-width: calc(100vw - 16px); max-height: calc(100dvh - 16px); box-sizing: border-box; overflow: auto; }
.fm:not(.smart-menu) .mi {
  display: flex; align-items: center; gap: 8px; padding: 0 12px; font-size: var(--st-font-size);
  border-radius: 4px; cursor: pointer; white-space: nowrap; color: var(--st-text-2);
 height: var(--st-list-item-height); box-sizing: border-box; }
.mi .st-icon { color: var(--st-text-2); }
.mi:hover { background: var(--st-bg-hover); }
.mi.danger { color: var(--el-color-danger); }
.mi.danger .st-icon { color: var(--el-color-danger); }
/* 列头菜单的移入编组子菜单：hover 右侧飞出 */
.mi.has-sub { position: relative; display: flex; align-items: center; }
.sub-caret { margin-left: auto; color: var(--st-text-3); display: inline-flex; }
.fm-sub { display: none; }
.fm:not(.smart-menu) .fm-sub {
  position: absolute; left: calc(100% - 2px); top: -4px; z-index: 1;
  background: #fff; border-radius: 8px; box-shadow: var(--st-shadow-pop); padding: 4px; min-width: 140px;
}
.mi.has-sub:hover > .fm-sub { display: block; }
.mi.disabled { color: var(--st-disabled); cursor: not-allowed; }
.fb-item.freeze-disabled { color: var(--st-disabled); cursor: not-allowed; }
.mi.disabled .st-icon { color: var(--st-disabled); }
/* V3「根据此列…」分节 + 数据可视化飞出（双行项：标题 + 灰色说明） */
.fm-group-t { font-size: var(--st-font-size); color: var(--st-text-3); padding: 6px 12px 2px; }
.fm-free { margin-left: 6px; }
.fm-ai { color: var(--st-ai) !important; }
.fm .fm-viz { min-width: 260px; }
.fm-sub-t { font-size: var(--st-font-size); color: var(--st-text-3); padding: 6px 12px 2px; }
.mi-2 { align-items: flex-start; }
.mi-2 > .st-icon { margin-top: 2px; }
.mi-s { font-size: var(--st-font-size); color: var(--st-text-3); margin-top: 2px; }
.tb-ico.on { background: var(--st-primary-weak); color: var(--st-primary); }
.sub-check { display: inline-block; width: 16px; color: var(--st-primary); }
.gd-form { display: flex; flex-direction: column; --el-color-primary: var(--st-primary); }
.gd-name { width: 100%; box-sizing: border-box; height: 36px; margin-bottom: 12px; border: 1px solid #DEE0E3; border-radius: 6px; padding: 0 12px; font-size: var(--st-font-size); color: var(--st-text-2); background: #fff; outline: none; }
.gd-name:hover { border-color: #C9CDD4; }
.gd-name:focus { border-color: var(--st-primary); }
.gd-fields { display: flex; align-items: center; gap: 8px; min-height: 36px; border-radius: 6px; box-shadow: 0 0 0 1px #DEE0E3 inset; padding: 5px 12px; box-sizing: border-box; cursor: pointer; }
.gd-fields:hover { box-shadow: 0 0 0 1px #C9CDD4 inset; }
.gd-fields.open, .gd-fields:focus-visible { outline: none; box-shadow: 0 0 0 1px var(--st-primary) inset; }
.gd-fields > .st-icon { flex: none; }
.gd-foot { display: flex; align-items: center; justify-content: flex-end; gap: 12px; border-top: 1px solid #EBECEE; margin: 16px -16px 0; padding: 16px 16px 0; }
.gd-btn { height: 32px; padding: 0 16px; border-radius: 6px; border: none; background: #F2F3F5; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.gd-btn:hover { background: #E6E8EA; }
.gd-btn.primary { background: var(--st-primary); color: #fff; }
.gd-btn.primary:hover { background: #255BD0; }
/* 统计行菜单：勾选位 + 方式名 + 右对齐值（对齐设计稿 PixPin_2026-10-15_16-56-53） */
.stat-fm { min-width: 180px; }
.stat-mi { display: flex; align-items: center; gap: 6px; }
.sm-check { width: 14px; color: var(--st-primary); }
.sm-label { flex: 1; }
.sm-val { color: var(--st-text-2); font-variant-numeric: tabular-nums; }
.fm:not(.smart-menu) .fm-divider { height: 1px; background: var(--st-border); margin: 4px 6px; }
/* 排序项行尾：当前方向内联灰字（参照 表头-工具栏.png「选项正序 ›」） */
.mi-tail { margin-left: auto; display: inline-flex; align-items: center; gap: 2px; color: var(--st-text-3); font-size: var(--st-font-size); }
.mi.has-sub .mi-tail .sub-caret { margin-left: 0; }
/* 列头菜单底部图标快捷栏：5 图标等距，hover 浅灰块，tooltip 由 el-tooltip 提供 */
.fm-bar { display: flex; align-items: center; justify-content: space-around; border-top: 1px solid var(--st-border); margin-top: 4px; padding: 6px 4px 2px; }
.fb-item { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 28px; border-radius: 6px; cursor: pointer; color: var(--st-text-2); }
.fb-item:hover { background: var(--st-bg-hover); color: var(--st-text-2); }
/* 列头单字段筛选浮层容器 */
.ffp-wrap { width: 480px; box-sizing: border-box; padding: 18px 20px 16px; border-radius: 12px; box-shadow: 0 8px 28px rgba(0, 0, 0, .14); }
</style>
