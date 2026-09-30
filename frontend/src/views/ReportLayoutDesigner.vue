<template>
  <div v-loading="loading" class="rp-designer">
    <!-- 顶栏（与工作流编辑器一致：白底通栏、名称内联编辑、操作按钮右排）
         分组：返回+名称 ｜ 页签 ｜（弹性空白）｜ 全局时间 ｜ 操作按钮 -->
    <div class="topbar">
      <!-- 组1：返回 + 名称 -->
      <div class="tb-group">
        <el-button link @click="goBack">
          <el-icon><ArrowLeft /></el-icon>返回
        </el-button>
        <el-input v-model="tplName" placeholder="报表名称" class="name-input" @input="dirty = true" />
        <el-tag v-if="dirty" size="small" type="warning" effect="plain">未保存</el-tag>
      </div>

      <div class="tb-divider" />

      <!-- 组2：页签（可横向滚动） -->
      <div class="page-bar">
        <div
          v-for="(p, pi) in pages" :key="p.id" class="page-tab" :class="{ active: p.id === activePageId }"
          @click="activePageId = p.id" @dblclick="renamePage(p)"
        >
          <span>{{ p.title }}</span>
          <template v-if="p.id === activePageId">
            <el-icon v-if="pi > 0" title="前移" @click.stop="movePage(pi, -1)"><ArrowLeftBold /></el-icon>
            <el-icon v-if="pi < pages.length - 1" title="后移" @click.stop="movePage(pi, 1)"><ArrowRightBold /></el-icon>
            <el-icon title="重命名" @click.stop="renamePage(p)"><EditPen /></el-icon>
            <el-icon v-if="pages.length > 1" title="删除页签" @click.stop="deletePage(p)"><Close /></el-icon>
          </template>
        </div>
        <el-button v-if="pages.length < PAGES_MAX" link type="primary" :icon="Plus" @click="addPage">页签</el-button>
      </div>

      <div class="spacer" />

      <!-- 组3：全局口径（与查看页一致直接可切；设置抽屉里仍是完整的口径/推送配置） -->
      <template v-if="tpl">
        <div class="tb-group">
          <span class="tb-label">全局时间</span>
          <el-select :model-value="tpl.range?.mode || 'this_week'" size="small" class="range-select" title="全局口径"
            @update:model-value="onGlobalRangeMode">
            <el-option v-for="[v, l] in RANGE_MODES" :key="v" :label="l" :value="v" />
          </el-select>
          <el-date-picker
            v-if="tpl.range?.mode === 'custom'" v-model="globalRangeCustom" type="daterange" size="small"
            value-format="YYYY-MM-DD" start-placeholder="开始" end-placeholder="结束" class="range-dates"
          />
        </div>
        <div class="tb-divider" />
      </template>

      <!-- 组4：操作按钮 -->
      <div class="tb-group">
        <el-button :icon="RefreshLeft" :disabled="!canUndo" title="撤销（Ctrl+Z）" @click="undo">撤销</el-button>
        <el-button :icon="RefreshRight" :disabled="!canRedo" title="重做（Ctrl+Y）" @click="redo">重做</el-button>
        <el-button class="ai-btn" title="用一句话描述需求，AI 生成区块草稿" @click="openAi">
          <el-icon><MagicStick /></el-icon>AI 生成
        </el-button>
        <el-button :icon="Grid" @click="autoArrange">自动排版</el-button>
        <el-button :icon="VideoPlay" :loading="previewLoading" title="沙盒试运行：用当前未保存的配置生成预览，不落库" @click="previewRun">试运行</el-button>
        <el-button :icon="View" title="打开报表查看页（已保存的内容）" @click="onGoView">查看</el-button>
        <el-button :icon="Setting" @click="openSettings">设置</el-button>
        <el-button type="primary" :icon="Check" :loading="saving" @click="save">保存</el-button>
      </div>
    </div>

    <div class="body">
      <!-- 左：区块类型（点击添加）+ 数据源树（拖字段成图）+ 未放置区块 -->
      <div class="sidebar">
        <div class="side-section">
          <div class="side-title">区块（点击或拖入画布）</div>
          <div class="block-palette">
            <div
              v-for="t in ['stat', 'chart', 'pivot', 'table', 'text', 'filter']" :key="t"
              class="palette-item" :title="`点击添加「${BLOCK_TYPE_LABELS[t]}」，或拖到画布任意位置`"
              draggable="true" @click="addBlock(t)" @dragstart="onBlockDragStart($event, t)"
            >
              <el-icon class="pi-icon"><component :is="BLOCK_TYPE_ICONS[t]" /></el-icon>
              <span>{{ BLOCK_TYPE_LABELS[t] }}</span>
            </div>
          </div>
        </div>
        <div class="side-section">
          <div class="side-title">
            数据源（点击或拖入画布）
            <el-button link type="primary" size="small" style="float: right" @click="addDatasetVisible = true">+ 添加</el-button>
          </div>
          <div v-for="d in datasets" :key="d.id" class="ds-group">
            <div class="ds-head">
              <span class="ds-name">{{ d.name }}</span>
              <div class="ds-ops">
                <el-icon title="编辑数据集（关联/计算字段）" @click="openDatasetEditor(d)"><Setting /></el-icon>
                <el-icon title="删除数据源" @click="removeDataset(d)"><Delete /></el-icon>
              </div>
            </div>
            <div
              v-for="f in fieldsOf(d.id)" :key="f.field_name" class="field-chip" draggable="true"
              :title="`${f.label}（${f.data_type}）— 点击或拖入画布成图`"
              @click="onFieldClick(d, f)" @dragstart="onFieldDragStart($event, d, f)"
            >
              <span class="fc-type" :class="ftypeClass(f)">{{ ftypeShort(f) }}</span>
              <span class="fc-label">{{ f.label }}</span>
            </div>
          </div>
          <el-empty v-if="!datasets.length" description="先添加一个数据源" :image-size="40" />
        </div>
      </div>

      <!-- 栅格画布（点空白处收起配置面板） -->
      <div ref="canvasEl" class="canvas-wrap" @dragover.prevent @drop="onFieldDrop" @click="onCanvasBackdropClick">
        <GridLayout
          :layout="glItems" :col-num="GRID_COLS" :row-height="ROW_HEIGHT"
          :margin="[GRID_MARGIN, GRID_MARGIN]" :vertical-compact="false" @layout-updated="onLayoutUpdated"
        >
          <GridItem
            v-for="item in glItems" :key="item.i" v-bind="item"
            drag-allow-from=".gi-head" drag-ignore-from="button, a"
          >
            <div class="gi-card" :class="{ selected: item.i === selectedBlockId, invalid: invalidIds.includes(item.i) }" @click.stop="selectedBlockId = item.i">
              <div class="gi-head">
                <span class="gi-type">{{ BLOCK_TYPE_LABELS[blockOf(item.i)?.type] || '区块' }}</span>
                <span class="gi-title">{{ blockOf(item.i)?.title || '未命名' }}</span>
                <span v-if="dsOf(blockOf(item.i))" class="gi-ds">{{ dsOf(blockOf(item.i)).name }}</span>
                <el-button text size="small" :icon="CopyDocument" title="复制区块" @click.stop="duplicateBlock(item.i)" />
                <el-button text size="small" :icon="Close" title="删除区块" @click.stop="removeBlock(item.i)" />
              </div>
              <!-- 真实数据渲染（draft 沙盒取数）；无数据时显示占位提示（半成品块列出缺失项） -->
              <div v-if="blockResults[item.i]" class="gi-real">
                <ReportBlock :block="blockResults[item.i]" fill @page="onTablePage" @table-sort="onTableSort" />
              </div>
              <div v-else class="gi-body">
                <template v-if="missingOf(item.i).length">还差：{{ missingOf(item.i).join('、') }}</template>
                <template v-else>{{ dataLoading ? '绘制中…' : '等待数据…' }}</template>
              </div>
            </div>
          </GridItem>
        </GridLayout>
        <div v-if="!glItems.length" class="empty-hint">从左侧拖字段到画布自动成图，或点「自动排版」一键布局</div>
      </div>

      <!-- 右：选中区块的内联配置（浮动覆盖画布，不推挤布局；可拖宽） -->
      <div v-if="selectedBlock" class="config-panel" :style="{ width: panelWidth + 'px' }">
        <div class="panel-resizer" title="拖动调整宽度" @mousedown="startResize" />
        <div class="config-head">
          <span class="config-title">{{ BLOCK_TYPE_LABELS[selectedBlock.type] }}配置</span>
          <div>
            <el-button link class="ai-link" size="small" @click="openBlockAi">✨ AI 帮我设置</el-button>
            <el-button link type="danger" size="small" @click="removeBlock(selectedBlock.id)">删除区块</el-button>
            <el-button link type="info" size="small" @click="selectedBlockId = null">收起</el-button>
          </div>
        </div>
        <el-input v-model="selectedBlock.title" placeholder="区块显示名" size="small" class="mb" @input="dirty = true" />

        <el-form v-if="selectedBlock.type !== 'text'" label-position="top" size="small" @change="dirty = true">
          <el-form-item label="数据源">
            <el-select
              :model-value="selectedBlock.dataset_id" class="w-full"
              @change="(v) => onBlockDatasetChange(selectedBlock, v)"
            >
              <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
          </el-form-item>
          <!-- 筛选块是交互控件、自身不查数据：块级日期字段/时间范围对它无意义，不显示 -->
          <el-form-item v-if="selectedBlock.type !== 'filter'" label="日期字段（全局口径作用字段）">
            <el-select v-model="selectedBlock.date_field" class="w-full" placeholder="日期字段">
              <el-option label="不随时间筛选" :value="null" />
              <el-option label="创建时间" value="created_at" />
              <el-option label="更新时间" value="updated_at" />
              <el-option v-for="f in dateFieldsOf(selectedBlock.dataset_id)" :key="f.field_name" :label="f.label" :value="f.field_name" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="selectedBlock.type !== 'filter'" label="时间范围">
            <el-select v-model="rangeModeOf" class="w-full">
              <el-option label="跟随全局口径" value="" />
              <el-option v-for="[v, l] in RANGE_MODES" :key="v" :label="l" :value="v" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="selectedBlock.range_mode === 'custom'">
            <el-date-picker
              v-model="rangeCustomOf" type="daterange" value-format="YYYY-MM-DD"
              class="w-full" start-placeholder="开始" end-placeholder="结束"
            />
          </el-form-item>
        </el-form>

        <!-- 筛选组件的作用域 -->
        <el-form v-if="selectedBlock.type === 'filter'" label-position="top" size="small" @change="dirty = true">
          <el-form-item label="作用范围">
            <el-select v-model="filterTargetMode" class="w-full">
              <el-option label="同数据源的全部区块" value="same_dataset" />
              <el-option label="指定区块" value="blocks" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="filterTargetMode === 'blocks'">
            <el-select v-model="filterTargetIds" multiple class="w-full" placeholder="选择目标区块">
              <el-option
                v-for="b2 in sameDatasetBlocks" :key="b2.id"
                :label="`${BLOCK_TYPE_LABELS[b2.type]} · ${b2.title || b2.id}`" :value="b2.id"
              />
            </el-select>
          </el-form-item>
        </el-form>

        <el-divider content-position="left">图表配置</el-divider>
        <BlockConfigForm :block="selectedBlock" :fields="fieldsOf(selectedBlock.dataset_id)" :stat-blocks="statBlocks" />
        <div class="panel-tip">改配置会立即自动重绘；顶栏「保存」（Ctrl+S）才会写入报表，误操作可 Ctrl+Z 撤销</div>
      </div>
    </div>

    <!-- 添加数据源 -->
    <el-dialog v-model="addDatasetVisible" title="添加数据源" width="440px" destroy-on-close>
      <el-select v-model="newDatasetTableIds" multiple collapse-tags :max-collapse-tags="2"
        placeholder="选择数据表（可多选，已添加的不可重复）" style="width: 100%" filterable>
        <el-option
          v-for="t in tables" :key="t.id" :value="t.id"
          :label="`${t.label}（${t.storage_mode === 'physical' ? '物理' : 'JSON'}）${datasets.some((d) => d.base_table_id === t.id) ? ' · 已添加' : ''}`"
          :disabled="datasets.some((d) => d.base_table_id === t.id)"
        />
      </el-select>
      <template #footer>
        <el-button @click="addDatasetVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!newDatasetTableIds.length" @click="addDataset">添加</el-button>
      </template>
    </el-dialog>

    <!-- 数据集编辑：多表关联 + 计算字段 -->
    <el-drawer v-model="dsEditorVisible" size="640px" class="ds-drawer">
      <template #header>
        <div class="dsd-head">
          <span class="dsd-title">数据集设置</span>
          <el-input v-if="editingDs" v-model="editingDs.name" maxlength="32" class="dsd-name" placeholder="数据集名称" />
        </div>
      </template>
      <template v-if="editingDs">
        <!-- 关联表 -->
        <div class="src-sec">
          <div class="src-sec-head">
            <div class="src-sec-title">🔗 关联表</div>
            <el-button text type="primary" size="small" :disabled="editingDs.joins.length >= 3"
              @click="editingDs.joins.push({ table_id: null, prefix: '', on: [{ left: null, right: null }] })">+ 添加关联</el-button>
          </div>
          <div class="src-sec-desc">以本表为主表左连接其他表（最多 3 张，仅物理存储表），关联后可以使用对方的字段</div>

          <div v-for="(j, ji) in editingDs.joins" :key="ji" class="join-card">
            <div class="join-head">
              <span class="join-no">关联表 {{ ji + 1 }}</span>
              <el-button text type="danger" size="small" @click="editingDs.joins.splice(ji, 1)">删除</el-button>
            </div>
            <div class="join-body">
              <div class="join-field">
                <span class="jf-label">关联哪张表</span>
                <el-select v-model="j.table_id" size="small" placeholder="选择表" filterable class="jf-grow"
                  @change="onJoinTableChange(j)">
                  <el-option v-for="t in joinableTables" :key="t.id" :label="t.label" :value="t.id" />
                </el-select>
              </div>
              <div class="join-field">
                <span class="jf-label">字段前缀
                  <el-tooltip content="关联表的字段名会加上此前缀，避免与主表字段重名，如填「客户.」" placement="top">
                    <el-icon class="hint-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </span>
                <el-input v-model="j.prefix" size="small" placeholder="如：客户." style="width: 140px" />
              </div>
              <div class="join-conds">
                <span class="jf-label">关联条件</span>
                <div class="join-cond-list">
                  <div v-for="(o, oi) in j.on" :key="oi" class="join-cond">
                    <el-select v-model="o.left" size="small" placeholder="本表字段" filterable class="jf-grow">
                      <el-option v-for="f in baseFieldsOf(editingDs.base_table_id)" :key="f.field_name" :label="`本表·${f.label}`" :value="f.field_name" />
                      <el-option label="本表·ID" value="id" />
                    </el-select>
                    <span class="join-eq">=</span>
                    <el-select v-model="o.right" size="small" placeholder="关联表字段" filterable class="jf-grow">
                      <el-option label="关联表·ID" value="id" />
                      <el-option v-for="f in joinFieldsOf(j.table_id)" :key="f.field_name" :label="`关联表·${f.label}`" :value="f.field_name" />
                    </el-select>
                    <el-button text type="danger" size="small" :disabled="j.on.length <= 1" @click="j.on.splice(oi, 1)">删</el-button>
                  </div>
                </div>
                <el-button text size="small" type="primary" @click="j.on.push({ left: null, right: null })">+ 关联条件</el-button>
              </div>
            </div>
          </div>
          <div v-if="!editingDs.joins.length" class="src-empty">单表使用可不添加关联</div>
        </div>

        <!-- 计算字段 -->
        <div class="src-sec">
          <div class="src-sec-head">
            <div class="src-sec-title">🧮 计算字段</div>
            <el-button text type="primary" size="small"
              @click="editingDs.computed_fields.push({ name: '', expr: '', type: '' })">+ 添加字段</el-button>
          </div>
          <div class="src-sec-desc">用表达式从现有字段算出新字段，随每行数据实时计算</div>

          <div v-for="(c, ci) in editingDs.computed_fields" :key="ci" class="cf-card">
            <div class="cf-row2">
              <el-input v-model="c.name" size="small" placeholder="字段名，如：不良率" style="width: 150px" />
              <el-select v-model="c.type" size="small" placeholder="类型（自动）" clearable style="width: 120px">
                <el-option label="整数" value="int" />
                <el-option label="小数" value="decimal" />
                <el-option label="布尔" value="bool" />
                <el-option label="文本" value="varchar" />
              </el-select>
              <el-button text type="danger" size="small" @click="editingDs.computed_fields.splice(ci, 1)">删</el-button>
            </div>
            <!-- 表达式 + 插入字段：不用背字段名，点了插到光标处；输入时实时校验语法/字段/类型 -->
            <div class="cf-expr-row">
              <el-input
                v-model="c.expr" size="small" placeholder="表达式，如：actual / plan * 100" class="cf-expr"
                :ref="(el) => (cfExprRefs[ci] = el)" @focus="cfExprFocused[ci] = true" @input="checkExprNow(ci)"
              />
              <VariablePicker
                compact title="插入字段或函数" :groups="dsExprGroups" empty-text="主表字段加载后可用"
                @insert="(n) => insertCfField(ci, n)"
              />
            </div>
            <div v-if="cfCheck[ci]" class="cf-check" :class="cfCheck[ci].state">
              <template v-if="cfCheck[ci].state === 'checking'">校验中…</template>
              <template v-else-if="cfCheck[ci].state === 'ok'">✓ 表达式有效，结果类型：{{ CF_TYPE_LABELS[cfCheck[ci].type] || cfCheck[ci].type }}</template>
              <template v-else>✗ {{ cfCheck[ci].error }}</template>
            </div>
          </div>
          <div v-if="!editingDs.computed_fields.length" class="src-empty">没有计算字段时可留空</div>

          <el-collapse class="cf-help">
            <el-collapse-item title="可用的运算符和函数（点击展开）" name="1">
              <div class="cf-help-body">
                支持 <code>+ - * /</code>、比较、<code>and/or</code>、<code>iff(条件,a,b)</code>、<code>coalesce</code>、<code>concat</code>、<code>abs</code>、<code>round</code>、<code>floor</code>、<code>ceil</code>、<code>min</code>、<code>max</code>、<code>year</code>、<code>month</code>、<code>day</code>、<code>datediff</code><br>
                <code>+</code> 只做数值加法，<b>字符串拼接必须用 concat</b>，如：<code>concat(operator, '-', production_date)</code><br>
                引用关联字段用「前缀.字段名」，如：<code>iff(客户.level == 'A', 1, 0)</code>；<br>
                字段名含 - 空格等特殊字符时（如「生产记录表-物理.」前缀），用括号引用：<code>[生产记录表-物理.operator]</code>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- 结果字段预览 -->
        <div class="src-sec">
          <div class="src-sec-head">
            <div class="src-sec-title">👁 结果字段预览</div>
          </div>
          <div class="src-sec-desc">按当前配置，数据集最终提供的字段</div>
          <div class="dsd-preview">
            <el-tag v-for="f in dsPreviewFields" :key="f.key" size="small" :type="f.kind" effect="plain">{{ f.label }}</el-tag>
            <span v-if="!dsPreviewFields.length" class="src-empty">主表字段加载后显示</span>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="dsEditorVisible = false">关闭</el-button>
        <el-button type="primary" @click="applyDatasetEditor">应用</el-button>
      </template>
    </el-drawer>

    <!-- 模板设置：描述 + 定时推送（名称/全局口径在顶栏编辑，AI 生成在顶栏） -->
    <el-drawer v-model="settingsVisible" title="报表设置" size="520px" class="rp-settings">
      <el-form label-position="top" size="small">
        <div class="set-sec">
          <div class="set-sec-title">基本信息</div>
          <el-form-item label="描述">
            <el-input v-model="settingsForm.description" placeholder="选填" />
          </el-form-item>
        </div>

        <div class="set-sec">
          <div class="set-sec-title">
            定时推送
            <el-switch v-model="settingsForm.enabled" size="small" style="margin-left: 10px"
              :disabled="!settingsForm.schedule.type" active-text="启用" />
          </div>
          <div class="set-sec-desc">配好周期和渠道后开启；启用后按周期自动生成并推送报表</div>

          <!-- 执行周期：与工作流触发器的「触发频率」同款交互（间隔 / Cron 可视化构建器） -->
          <el-form-item label="执行周期">
            <el-radio-group v-model="settingsForm.schedule.type" size="small">
              <el-radio-button value="">不定时</el-radio-button>
              <el-radio-button value="interval">间隔</el-radio-button>
              <el-radio-button value="cron">Cron</el-radio-button>
            </el-radio-group>
            <div v-if="settingsForm.schedule.type === 'interval'" class="mt row">
              <span>每</span>
              <el-input-number v-model="settingsForm.schedule.minutes" :min="1" size="small" controls-position="right" style="width: 100px" />
              <span>分钟</span>
            </div>
            <template v-else-if="settingsForm.schedule.type === 'cron'">
              <div class="mt row">
                <el-select v-model="cronMode" size="small" style="width: 170px">
                  <el-option label="每小时" value="hour" />
                  <el-option label="每天" value="day" />
                  <el-option label="每周" value="week" />
                  <el-option label="每月" value="month" />
                  <el-option label="自定义（cron 表达式）" value="custom" />
                </el-select>
                <template v-if="cronMode === 'hour'">
                  <span>第</span>
                  <el-input-number v-model="cronMinute" :min="0" :max="59" size="small" controls-position="right" style="width: 80px" />
                  <span>分</span>
                </template>
                <template v-else-if="cronMode !== 'custom'">
                  <el-select v-if="cronMode === 'week'" v-model="cronWeek" size="small" style="width: 90px">
                    <el-option v-for="(w, i) in ['周一', '周二', '周三', '周四', '周五', '周六', '周日']" :key="i" :label="w" :value="i" />
                  </el-select>
                  <template v-if="cronMode === 'month'">
                    <el-input-number v-model="cronDom" :min="1" :max="31" size="small" controls-position="right" style="width: 80px" />
                    <span>日</span>
                  </template>
                  <el-time-picker v-model="cronTime" size="small" format="HH:mm" value-format="HH:mm"
                    placeholder="时间" style="width: 110px" />
                </template>
              </div>
              <el-input v-if="cronMode === 'custom'" v-model="settingsForm.schedule.expr" size="small" class="mt"
                placeholder="cron 表达式：分 时 日 月 周（周一 = 0，周日 = 6）" />
              <div class="mt hint">实际生效：{{ settingsForm.schedule.expr }}</div>
            </template>
          </el-form-item>

          <template v-if="settingsForm.schedule.type">
            <div class="set-sub">推送渠道</div>
            <el-form-item label="收件邮箱">
              <!-- 与工作流「接收邮箱」同款：标签式录入，回车添加、逐个校验格式 -->
              <el-select :model-value="recipientsList" multiple filterable allow-create default-first-option
                placeholder="输入邮箱后回车，可添加多个" style="width: 100%" @update:model-value="setRecipients">
                <el-option v-for="r in recipientsList" :key="r" :label="r" :value="r" />
              </el-select>
            </el-form-item>
            <!-- 群机器人：通道选择与工作流「发送通知」节点的通道同款（完整名称下拉） -->
            <el-form-item label="群机器人">
              <div style="width: 100%">
                <div v-for="(wh, i) in settingsForm.push.webhooks" :key="i" class="wh-row">
                  <el-select v-model="wh.type" size="small" style="width: 140px">
                    <el-option label="企业微信机器人" value="wecom" />
                    <el-option label="钉钉机器人" value="dingtalk" />
                    <el-option label="自定义 Webhook" value="custom" />
                  </el-select>
                  <el-input v-model="wh.url" size="small" placeholder="Webhook 地址" style="flex: 1" />
                  <el-button text type="danger" size="small" @click="settingsForm.push.webhooks.splice(i, 1)">删</el-button>
                </div>
                <el-button text type="primary" size="small" @click="settingsForm.push.webhooks.push({ type: 'wecom', url: '' })">+ 添加机器人</el-button>
              </div>
            </el-form-item>
            <el-form-item label="推送内容">
              <el-checkbox-group v-model="settingsForm.push.formats" size="small">
                <el-checkbox value="html_inline">邮件正文</el-checkbox>
                <el-checkbox value="xlsx">Excel 附件</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="邮件主题">
              <el-input v-model="settingsForm.push.subject" placeholder="默认：【报表名】时间范围" />
            </el-form-item>

            <div class="set-sub">阈值告警</div>
            <!-- 阈值告警：多条件（全部/任一满足才发送，与区块筛选同款规则行） -->
            <el-checkbox
              :model-value="!!settingsForm.push.guard?.rules?.length"
              size="small"
              @change="onGuardToggle"
            >仅当条件满足时才发送</el-checkbox>
            <div v-if="settingsForm.push.guard?.rules?.length" class="guard-box">
              <div class="guard-logic">
                满足
                <el-radio-group v-model="settingsForm.push.guard.logic" size="small">
                  <el-radio-button value="AND">全部条件</el-radio-button>
                  <el-radio-button value="OR">任一条件</el-radio-button>
                </el-radio-group>
                时才发送
              </div>
              <div v-for="(r, ri) in settingsForm.push.guard.rules" :key="ri" class="guard-row">
                <el-select v-model="r.block_id" size="small" style="flex: 1" placeholder="选择统计卡">
                  <el-option v-for="s in statBlocks" :key="s.id" :label="s.title || s.id" :value="s.id" />
                </el-select>
                <el-select v-model="r.op" size="small" style="width: 64px">
                  <el-option v-for="[v, l] in GUARD_OPS" :key="v" :label="l" :value="v" />
                </el-select>
                <el-input-number v-model="r.value" size="small" controls-position="right" style="width: 100px" />
                <el-button text type="danger" size="small" @click="settingsForm.push.guard.rules.splice(ri, 1)">删</el-button>
              </div>
              <el-button text type="primary" size="small" @click="addGuardRule">+ 添加条件</el-button>
              <div class="hint">条件不满足时本次不发送，推送日志标记「条件未满足」</div>
            </div>
            <div v-if="settingsForm.push.guard?.rules?.length && !statBlocks.length" class="hint">还没有统计卡区块，先加一个</div>
          </template>
        </div>
      </el-form>
      <template #footer>
        <el-button :loading="pushPreviewLoading" @click="onPreviewPush">预览推送内容</el-button>
        <el-button type="primary" @click="applySettings">应用</el-button>
      </template>
    </el-drawer>

    <!-- 推送内容预览：邮件 HTML / 群机器人 Markdown（不实际发送） -->
    <el-dialog v-model="pushPreviewVisible" title="推送内容预览（按已保存的配置生成，不发送）" width="760px" top="6vh">
      <div v-loading="pushPreviewLoading" style="min-height: 200px">
        <template v-if="pushPreview">
          <div class="pp-subject">主题：{{ pushPreview.subject }}</div>
          <el-tabs>
            <el-tab-pane label="邮件正文">
              <iframe :srcdoc="pushPreview.html" class="pp-frame" sandbox="" />
            </el-tab-pane>
            <el-tab-pane label="群机器人（Markdown）">
              <pre class="pp-md">{{ pushPreview.markdown }}</pre>
            </el-tab-pane>
          </el-tabs>
        </template>
      </div>
    </el-dialog>

    <!-- AI 辅助 -->
    <el-dialog v-model="aiVisible" title="AI 辅助生成报表" width="640px" destroy-on-close>
      <el-select v-model="aiTableId" placeholder="基于哪张表生成" style="width: 100%; margin-bottom: 10px" filterable>
        <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
      </el-select>
      <!-- 已有区块时默认追加意图：AI 只生成本次要求的区块，不重新设计整表 -->
      <el-radio-group v-if="blocks.length" v-model="aiAppend" size="small" style="margin-bottom: 10px">
        <el-radio-button :value="true">在现有报表上追加</el-radio-button>
        <el-radio-button :value="false">重新设计整张报表</el-radio-button>
      </el-radio-group>
      <el-input
        v-model="aiDescription" type="textarea" :rows="4"
        :placeholder="aiAppend
          ? '描述要追加的内容，如：再增加一个按产品分组的金额合计图表'
          : '用自然语言描述你想要的报表，如：做一个上周的客户跟进周报，包含新增客户数、客户分级占比、每日新增趋势、客户明细和一段小结'"
      />
      <div style="margin: 10px 0">
        <el-button class="ai-btn" :loading="aiGenerating" :disabled="!aiTableId || !aiDescription.trim()" @click="aiGenerate">
          {{ aiResult ? '重新生成' : '生成' }}
        </el-button>
        <span v-if="aiGenerating" style="margin-left: 10px; font-size: 12px; color: #909399">AI 设计中，可能需要十几秒…</span>
      </div>
      <template v-if="aiResult">
        <el-alert type="success" :closable="false" style="margin-bottom: 10px"
          :title="`已生成「${aiResult.name}」：${aiResult.blocks.length} 个区块`" />
        <el-alert v-if="aiResult.notes" type="warning" :closable="false" :title="aiResult.notes" style="margin-bottom: 10px" />
        <!-- 应用方式：有存量区块时可选追加（追加不重排现有布局） -->
        <el-radio-group v-model="aiMode" size="small" style="margin-bottom: 4px">
          <el-radio-button value="replace">替换全部区块</el-radio-button>
          <el-radio-button value="append_page" :disabled="!blocks.length">追加为新页签</el-radio-button>
          <el-radio-button value="append_current" :disabled="!blocks.length">追加到当前页</el-radio-button>
        </el-radio-group>
      </template>
      <template #footer>
        <el-button @click="aiVisible = false">取消</el-button>
        <el-button v-if="aiResult" class="ai-btn" @click="aiApply">
          {{ aiMode === 'replace' ? '应用（替换全部区块）' : '应用（追加）' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- AI 帮我设置这个区块（与工作流节点的「AI 帮我配置」同款） -->
    <el-dialog v-model="aiBlockVisible" :title="`AI 设置 · ${BLOCK_TYPE_LABELS[selectedBlock?.type] || ''}`" width="480px">
      <el-input v-model="aiBlockDesc" type="textarea" :rows="4"
        placeholder="用一句话描述你想要的效果，例如：按产品分组看金额合计，只要本月已完成的" />
      <template #footer>
        <el-button @click="aiBlockVisible = false">取消</el-button>
        <el-button class="ai-btn" :loading="aiBlockLoading" @click="applyBlockAi">生成并填入</el-button>
      </template>
    </el-dialog>

    <!-- 试运行预览（draft 不落库） -->
    <el-dialog v-model="previewVisible" title="试运行预览（未保存的配置，不影响线上报表）" width="88%" top="4vh">
      <div v-loading="previewLoading" style="min-height: 200px">
        <ReportDashboard v-if="previewResult" :blocks="previewResult.blocks" :layout="previewResult.layout" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, ArrowLeftBold, ArrowRightBold, Calendar, Check, CircleCheck, Close, Coin, CopyDocument, Delete, Document,
  EditPen, Filter, Grid, Histogram, MagicStick, Odometer, Plus, QuestionFilled, RefreshLeft, RefreshRight, Setting, Tickets, VideoPlay, View,
} from '@element-plus/icons-vue'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { aiAssistBlock, aiAssistReport, checkExpr, getReport, getTable, listTables, previewPushReport, runReport, updateReport } from '../api'
import ReportDashboard from '../components/ReportDashboard.vue'
import VariablePicker from '../components/workflow/VariablePicker.vue'
import ReportBlock from '../components/ReportBlock.vue'
import BlockConfigForm from '../components/BlockConfigForm.vue'
import {
  BLOCK_SIZE, BLOCK_TYPE_LABELS, GRID_COLS, GRID_MARGIN, PAGES_MAX, ROW_HEIGHT,
  autoLayout, defaultItem, nextPageId, normalizeLayout, smartBlockForField,
} from '../utils/reportLayout'

// 区块类型图标（侧栏区块面板用）
const BLOCK_TYPE_ICONS = { stat: Odometer, chart: Histogram, pivot: Grid, table: Tickets, text: Document, filter: Filter }

const RANGE_MODES = [
  ['today', '今天'], ['yesterday', '昨天'], ['past_7d', '近7天'], ['past_30d', '近30天'],
  ['this_week', '本周'], ['last_week', '上周'], ['this_month', '本月'], ['last_month', '上月'],
  ['this_quarter', '本季度'], ['this_year', '今年'], ['custom', '自定义'],
]

const route = useRoute()
const router = useRouter()
const tplId = route.params.id

const loading = ref(false)
const saving = ref(false)
const tpl = ref(null)
const pages = ref([])
const activePageId = ref('')
const dirty = ref(false)

const blocks = computed(() => tpl.value?.blocks || [])
const statBlocks = computed(() => blocks.value.filter((b) => b.type === 'stat'))
const activePage = computed(() => pages.value.find((p) => p.id === activePageId.value))

// 顶栏名称内联编辑（与工作流编辑器一致）
const tplName = computed({
  get: () => tpl.value?.name || '',
  set: (v) => { if (tpl.value) tpl.value.name = v },
})

// 右侧配置面板：可拖宽（与工作流编辑器一致）
const panelWidth = ref(400)

function startResize(e) {
  e.preventDefault()
  const startX = e.clientX
  const startW = panelWidth.value
  const onMove = (ev) => {
    panelWidth.value = Math.min(640, Math.max(320, startW + (startX - ev.clientX)))
  }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

function blockOf(id) {
  return blocks.value.find((b) => b.id === id)
}

// ---------- 数据集 ----------
const datasets = ref([])
const fieldMap = ref({})       // dataset_id -> 数据集字段（含关联/计算）
const baseFieldMap = ref({})   // table_id -> 基表字段
const tables = ref([])
const joinMeta = ref({})       // table_id -> fields（关联表）

let dsSeq = 0
function nextDatasetId() {
  const existing = new Set(datasets.value.map((d) => d.id))
  do { dsSeq += 1 } while (existing.has(`d${dsSeq}`))
  return `d${dsSeq}`
}

function dsOf(block) {
  if (!block || block.type === 'text') return null
  return datasets.value.find((d) => d.id === block.dataset_id) || null
}

function fieldsOf(did) {
  return fieldMap.value[did] || []
}

function baseFieldsOf(tid) {
  return baseFieldMap.value[tid] || []
}

function dateFieldsOf(did) {
  return fieldsOf(did).filter((f) => ['date', 'datetime'].includes(f.data_type))
}

function joinFieldsOf(tid) {
  return joinMeta.value[tid] || []
}

async function loadBaseFields(tid) {
  if (!baseFieldMap.value[tid]) {
    const t = await getTable(tid)
    baseFieldMap.value[tid] = t.fields
  }
  return baseFieldMap.value[tid]
}

async function refreshFields(did) {
  const d = datasets.value.find((x) => x.id === did)
  if (!d) return
  const base = await loadBaseFields(d.base_table_id)
  let out = [...base]
  for (const j of d.joins || []) {
    if (!j.table_id || !j.prefix) continue
    if (!joinMeta.value[j.table_id]) {
      joinMeta.value[j.table_id] = (await getTable(j.table_id)).fields
    }
    out = out.concat(joinMeta.value[j.table_id].map((f) => ({
      ...f, field_name: j.prefix + f.field_name, label: j.prefix + f.label,
    })))
  }
  for (const c of d.computed_fields || []) {
    if (c.name?.trim()) out.push({ field_name: c.name.trim(), label: c.name.trim(), data_type: c.type || 'decimal' })
  }
  fieldMap.value = { ...fieldMap.value, [did]: out }
}

async function refreshAllFields() {
  for (const d of datasets.value) await refreshFields(d.id)
}

// 添加数据源
const addDatasetVisible = ref(false)
const newDatasetTableIds = ref([])

async function addDataset() {
  // 多选添加；同一张表只允许一个数据源（下拉里已添加的被禁用，这里再兜底）
  const added = []
  for (const tid of newDatasetTableIds.value) {
    if (datasets.value.some((d) => d.base_table_id === tid)) continue
    const t = tables.value.find((x) => x.id === tid)
    const d = { id: nextDatasetId(), name: t?.label || '', base_table_id: tid, joins: [], computed_fields: [] }
    datasets.value.push(d)
    added.push(d)
  }
  addDatasetVisible.value = false
  newDatasetTableIds.value = []
  for (const d of added) await refreshFields(d.id)
  if (added.length) {
    dirty.value = true
    ElMessage.success(`已添加 ${added.length} 个数据源，拖字段到画布即可成图`)
  }
}

// 删除数据源：引用它的区块一并移除（画布/布局同步清理）
async function removeDataset(d) {
  const used = tpl.value.blocks.filter((b) => b.dataset_id === d.id)
  try {
    await ElMessageBox.confirm(
      used.length
        ? `删除数据源「${d.name}」将同时移除 ${used.length} 个使用它的区块，确定？`
        : `确定删除数据源「${d.name}」？`,
      '删除数据源', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  datasets.value = datasets.value.filter((x) => x.id !== d.id)
  if (used.length) {
    const ids = new Set(used.map((b) => b.id))
    tpl.value.blocks = tpl.value.blocks.filter((b) => !ids.has(b.id))
    for (const p of pages.value) p.items = p.items.filter((it) => !ids.has(it.block_id))
    if (ids.has(selectedBlockId.value)) selectedBlockId.value = null
    layoutVersion.value++
    refreshData(true)
  }
  dirty.value = true
  ElMessage.success('已删除数据源')
}

// 数据集编辑抽屉
const dsEditorVisible = ref(false)
const editingDs = ref(null)

const joinableTables = computed(() =>
  tables.value.filter((t) => t.storage_mode === 'physical' && t.id !== editingDs.value?.base_table_id)
)

async function openDatasetEditor(d) {
  editingDs.value = d
  await loadBaseFields(d.base_table_id)
  for (const j of d.joins || []) {
    if (j.table_id && !joinMeta.value[j.table_id]) {
      joinMeta.value[j.table_id] = (await getTable(j.table_id)).fields
    }
  }
  dsEditorVisible.value = true
}

async function onJoinTableChange(j) {
  j.on = [{ left: null, right: null }]
  if (j.table_id && !joinMeta.value[j.table_id]) {
    joinMeta.value[j.table_id] = (await getTable(j.table_id)).fields
  }
  if (!j.prefix && j.table_id) {
    const t = tables.value.find((x) => x.id === j.table_id)
    j.prefix = t ? `${t.label}.` : ''
  }
}

// 结果字段预览：主表字段 + 关联字段（带前缀）+ 计算字段（kind 用于 tag 颜色区分来源）
const dsPreviewFields = computed(() => {
  const d = editingDs.value
  if (!d) return []
  const out = baseFieldsOf(d.base_table_id).map((f) => ({ key: f.field_name, label: f.label, kind: 'primary' }))
  for (const j of d.joins || []) {
    if (!j.table_id) continue
    const prefix = j.prefix || ''
    for (const f of joinFieldsOf(j.table_id)) {
      out.push({ key: `${prefix}${f.field_name}`, label: `${prefix}${f.label}`, kind: 'success' })
    }
  }
  for (const c of d.computed_fields || []) {
    if (c.name?.trim()) out.push({ key: c.name.trim(), label: c.name.trim(), kind: 'warning' })
  }
  return out
})

// 计算字段表达式的「插入字段」面板：主表字段 + 各关联表的字段（带前缀），点击插到光标处
// 字段名含 - 空格 等标识符非法字符时（如「生产记录表-物理.」前缀），插入括号引用形式 [任意字段名]
const IDENT_SEG = /^[A-Za-z_一-龥][\w一-龥]*$/
const exprText = (name) => (name.split('.').every((s) => IDENT_SEG.test(s)) ? name : `[${name}]`)

// 常用函数骨架（点了插入占位模板，再逐个替换占位符；比背函数签名快）
const FUNC_SNIPPETS = [
  { label: '拼接 concat（文本+文本）', expr: "concat(字段1, '-', 字段2)" },
  { label: '条件分支 iff', expr: 'iff(条件, 值1, 值2)' },
  { label: '空值兜底 coalesce', expr: 'coalesce(字段, 0)' },
  { label: '保留小数 round', expr: 'round(字段, 2)' },
  { label: '相差天数 datediff', expr: 'datediff(日期字段1, 日期字段2)' },
  { label: '取年份 year', expr: 'year(日期字段)' },
  { label: '取月份 month', expr: 'month(日期字段)' },
  { label: '绝对值 abs', expr: 'abs(字段)' },
  { label: '多值最小 min', expr: 'min(字段1, 字段2)' },
  { label: '多值最大 max', expr: 'max(字段1, 字段2)' },
]

const dsExprGroups = computed(() => {
  const d = editingDs.value
  if (!d) return []
  const groups = [{
    title: '常用函数',
    items: FUNC_SNIPPETS,
  }, {
    title: `主表字段（${d.name}）`,
    items: baseFieldsOf(d.base_table_id).map((f) => ({ label: f.label, expr: exprText(f.field_name) })),
  }]
  for (const j of d.joins || []) {
    if (!j.table_id) continue
    const t = tables.value.find((x) => x.id === j.table_id)
    const prefix = j.prefix || ''
    groups.push({
      title: `关联字段（${t?.label || ''}）`,
      items: joinFieldsOf(j.table_id).map((f) => ({ label: `${prefix}${f.label}`, expr: exprText(`${prefix}${f.field_name}`) })),
    })
  }
  return groups
})

// 实时校验用的字段集（与后端 out_names 同源：主表 + 关联带前缀 + 已定义的计算字段）
const cfCheckFields = computed(() => {
  const d = editingDs.value
  if (!d) return []
  const out = baseFieldsOf(d.base_table_id).map((f) => ({ field_name: f.field_name, data_type: f.data_type }))
  for (const j of d.joins || []) {
    if (!j.table_id) continue
    const prefix = j.prefix || ''
    for (const f of joinFieldsOf(j.table_id)) {
      out.push({ field_name: `${prefix}${f.field_name}`, data_type: f.data_type })
    }
  }
  for (const c of d.computed_fields || []) {
    if (c.name?.trim()) out.push({ field_name: c.name.trim(), data_type: c.type || 'decimal' })
  }
  return out
})

const cfExprRefs = reactive({})
const cfExprFocused = reactive({})
const cfCheck = reactive({})   // ci -> { state: 'checking'|'ok'|'err', type?, error? }
const CF_TYPE_LABELS = { int: '整数', decimal: '小数', bool: '布尔', varchar: '文本', date: '日期', datetime: '日期时间' }
const cfCheckTimers = {}

function checkExprNow(ci) {
  const c = editingDs.value?.computed_fields?.[ci]
  const expr = (c?.expr || '').trim()
  clearTimeout(cfCheckTimers[ci])
  if (!expr) { cfCheck[ci] = null; return }
  cfCheck[ci] = { state: 'checking' }
  cfCheckTimers[ci] = setTimeout(async () => {
    try {
      const r = await checkExpr({ expr, fields: cfCheckFields.value })
      cfCheck[ci] = r.ok ? { state: 'ok', type: r.type } : { state: 'err', error: r.error }
    } catch { cfCheck[ci] = null }
  }, 450)
}

function insertCfField(ci, name) {
  const c = editingDs.value.computed_fields[ci]
  const el = cfExprRefs[ci]?.input || cfExprRefs[ci]?.$el?.querySelector('input')
  const v = c.expr || ''
  if (el && cfExprFocused[ci]) {
    const start = el.selectionStart ?? v.length
    c.expr = v.slice(0, start) + name + v.slice(el.selectionEnd ?? start)
    nextTick(() => {
      el.focus()
      el.selectionStart = el.selectionEnd = start + name.length
    })
  } else {
    c.expr = v ? `${v} ${name}` : name
  }
  checkExprNow(ci)   // 插入后即时校验
}

async function applyDatasetEditor() {
  dsEditorVisible.value = false
  if (editingDs.value) await refreshFields(editingDs.value.id)
  dirty.value = true
  ElMessage.success('数据集已应用，保存后生效')
  refreshData(true)   // 数据集变更后重绘
}

// ---------- 选中区块的内联编辑 ----------
const selectedBlockId = ref(null)
const selectedBlock = computed(() => blockOf(selectedBlockId.value))
// 保存校验未通过的区块（画布上红框标记；再次编辑即清除）
const invalidIds = ref([])

const rangeModeOf = computed({
  get: () => selectedBlock.value?.range_mode || '',
  set: (v) => {
    const b = selectedBlock.value
    if (!b) return
    if (v) {
      b.range_mode = v
    } else {
      delete b.range_mode
      delete b.range_start
      delete b.range_end
    }
  },
})

const rangeCustomOf = computed({
  get: () => (selectedBlock.value?.range_start && selectedBlock.value?.range_end
    ? [selectedBlock.value.range_start, selectedBlock.value.range_end] : null),
  set: (v) => {
    const b = selectedBlock.value
    if (!b) return
    b.range_start = v?.[0] || null
    b.range_end = v?.[1] || null
  },
})

// 筛选组件作用域
const filterTargetMode = computed({
  get: () => selectedBlock.value?.target?.mode || 'same_dataset',
  set: (v) => {
    const b = selectedBlock.value
    if (!b) return
    b.target = v === 'blocks' ? { mode: 'blocks', block_ids: b.target?.block_ids || [] } : { mode: 'same_dataset' }
  },
})
const filterTargetIds = computed({
  get: () => selectedBlock.value?.target?.block_ids || [],
  set: (v) => { if (selectedBlock.value) selectedBlock.value.target = { mode: 'blocks', block_ids: v } },
})
const sameDatasetBlocks = computed(() =>
  blocks.value.filter((b) => b.dataset_id === selectedBlock.value?.dataset_id && b.id !== selectedBlock.value?.id && !['text', 'filter'].includes(b.type))
)

let blockSeq = 0
function nextBlockId() {
  const existing = new Set(blocks.value.map((b) => b.id))
  do { blockSeq += 1 } while (existing.has(`b${blockSeq}`))
  return `b${blockSeq}`
}

// 区块换源：同名字段保留，冲突配置清空
function onBlockDatasetChange(block, did) {
  block.dataset_id = did
  const valid = new Set(fieldsOf(did).map((f) => f.field_name))
  const keep = (fn) => (fn && (valid.has(fn) || ['created_at', 'updated_at', 'id'].includes(fn)) ? fn : null)
  const dropped = []
  for (const key of ['field']) {
    if (block[key] && !keep(block[key])) { block[key] = null; dropped.push(key) }
  }
  if (block.group && block.group.field && !keep(block.group.field)) { block.group.field = null; dropped.push('group') }
  if (block.group2?.field && !keep(block.group2.field)) { block.group2.field = null; dropped.push('group2') }
  if (block.row?.field && !keep(block.row.field)) block.row.field = null
  if (block.col?.field && !keep(block.col.field)) block.col.field = null
  if (Array.isArray(block.columns)) block.columns = block.columns.filter(keep)
  if (block.filters?.rules) block.filters.rules = block.filters.rules.filter((r) => keep(r.field))
  if (block.type === 'filter' && !keep(block.field)) block.field = null
  if (block.date_field && !['created_at', 'updated_at'].includes(block.date_field) && !valid.has(block.date_field)) {
    block.date_field = 'created_at'
  }
  dirty.value = true
  if (dropped.length) ElMessage.warning(`换源后部分配置因字段不存在已清空：${dropped.join('、')}`)
}

// 复制区块：克隆配置为新块（标题加「副本」），放到当前页底部并选中
function duplicateBlock(blockId) {
  const src = blockOf(blockId)
  if (!src || !activePage.value) return
  const b = JSON.parse(JSON.stringify(src))
  b.id = nextBlockId()
  b.title = `${src.title || BLOCK_TYPE_LABELS[src.type]} 副本`
  tpl.value.blocks.push(b)
  activePage.value.items.push(defaultItem(b, activePage.value.items))
  selectedBlockId.value = b.id
  commit()
  layoutVersion.value++
  ElMessage.success(`已复制为「${b.title}」`)
  if (b.type !== 'text') refreshData(true)
}

// 真删除区块（画布 ✕ 与面板按钮共用）：从模板与所有页签移除
async function removeBlock(blockId) {
  const b = blockOf(blockId)
  if (!b) return
  try {
    await ElMessageBox.confirm(`确定删除区块「${b.title || b.id}」？`, '删除区块', { type: 'warning' })
  } catch { return }
  tpl.value.blocks = blocks.value.filter((x) => x.id !== b.id)
  for (const p of pages.value) p.items = p.items.filter((it) => it.block_id !== b.id)
  if (selectedBlockId.value === b.id) selectedBlockId.value = null
  dirty.value = true
  commit()
  layoutVersion.value++
}

// ---------- 拖字段成图 ----------
let dragPayload = null
const canvasEl = ref(null)

function onFieldDragStart(e, d, f) {
  dragPayload = { did: d.id, field: f }
  e.dataTransfer.effectAllowed = 'copy'
}

// 侧栏区块类型拖入画布
function onBlockDragStart(e, type) {
  dragPayload = { blockType: type }
  e.dataTransfer.effectAllowed = 'copy'
}

// 鼠标落点 → 栅格坐标（块中心对准光标，越界收敛；取不到容器时返回 null 回退底部追加）
function dropPosition(e, w, h) {
  const gl = canvasEl.value?.querySelector('.vgl-layout')
  if (!gl) return null
  const rect = gl.getBoundingClientRect()
  const colW = (rect.width - (GRID_COLS - 1) * GRID_MARGIN) / GRID_COLS
  const px = e.clientX - rect.left
  const py = e.clientY - rect.top
  if (px < 0 || py < 0) return null
  const gx = Math.min(Math.max(Math.round(px / (colW + GRID_MARGIN) - w / 2), 0), GRID_COLS - w)
  let gy = Math.max(Math.round(py / (ROW_HEIGHT + GRID_MARGIN)) - 1, 0)
  // 避免与现有块重叠：有重叠时下移到其底边（保持鼠标所在列）
  const items = activePage.value?.items || []
  const overlapped = (y) => items.some((it) => gx < it.x + it.w && gx + w > it.x && y < it.y + it.h && y + h > it.y)
  let guard = 0
  while (overlapped(gy) && guard++ < 200) gy += 1
  return { x: gx, y: gy, w, h }
}

function ftypeShort(f) {
  // 字段类型单字标记：图=文本（拖入画布生成图表）、数=数值（生成统计卡）、期=日期（生成趋势图）、否=布尔
  return { int: '数', decimal: '数', date: '期', datetime: '期', bool: '否' }[f.data_type] || '图'
}

function ftypeClass(f) {
  if (['int', 'decimal'].includes(f.data_type)) return 'num'
  if (['date', 'datetime'].includes(f.data_type)) return 'date'
  if (f.data_type === 'bool') return 'bool'
  return 'text'
}

function onFieldDrop(e) {
  e.preventDefault()
  if (!dragPayload || !activePage.value) return
  // 拖的是区块类型（侧栏区块面板）：按默认配置建块，落在鼠标位置
  if (dragPayload.blockType) {
    const b = buildBlock(dragPayload.blockType)
    dragPayload = null
    if (!b) return
    const { def } = BLOCK_SIZE[b.type] || BLOCK_SIZE.text
    mountBlock(b, dropPosition(e, ...def) || null)
    ElMessage.success(`已添加「${b.title}」，在右侧完善配置`)
    return
  }
  // 拖字段成图：先按字段类型推断块类型取默认尺寸，再按鼠标落点换算栅格坐标
  const probe = smartBlockForField(dragPayload.field)
  const { def } = BLOCK_SIZE[probe.type] || BLOCK_SIZE.text
  addFieldBlock(dragPayload.did, dragPayload.field, dropPosition(e, ...def))
  dragPayload = null
}

// 侧栏字段点击添加：与拖入画布同一套建块逻辑，缺省落到当前页底部
function onFieldClick(d, f) {
  if (!activePage.value) return
  addFieldBlock(d.id, f, null)
}

// 侧栏字段成块共用逻辑：拖入画布（带落点 pos）与点击添加（落当前页底部）
function addFieldBlock(did, f, pos) {
  const b = {
    id: nextBlockId(), ...smartBlockForField(f),
    dataset_id: did,
    date_field: ['date', 'datetime'].includes(f.data_type) ? f.field_name : 'created_at',
  }
  tpl.value.blocks.push(b)
  activePage.value.items.push(pos ? { block_id: b.id, ...pos } : defaultItem(b, activePage.value.items))
  selectedBlockId.value = b.id
  commit()
  layoutVersion.value++
  ElMessage.success(`已生成「${b.title}」`)
  refreshData(true)   // 新块立即绘制
}

// 点画布空白处收起配置面板（点块时 gi-card 已 stop）
function onCanvasBackdropClick(e) {
  if (!e.target.closest('.gi-card')) selectedBlockId.value = null
}

function onKeydown(e) {
  const tag = e.target?.tagName
  const typing = tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable
  if ((e.ctrlKey || e.metaKey) && !typing) {
    const k = e.key.toLowerCase()
    if (k === 'z' && !e.shiftKey) { e.preventDefault(); undo(); return }
    if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); redo(); return }
    if (k === 's') { e.preventDefault(); save(); return }
  }
  if (e.key === 'Escape' && selectedBlockId.value) selectedBlockId.value = null
}

// ---------- 画布实时绘制（draft 沙盒取数，不落库） ----------
const blockResults = ref({})   // block_id -> run 结果块
const dataLoading = ref(false)

// 明细表服务端分页（与查看页一致：每页 50 条；配置变更回第 1 页）
const TABLE_PAGE_SIZE = 50
const tablePages = ref({})
// 点列头排序的临时覆盖（预览用，不写入配置；配置里的排序在右侧面板改）
const sortOverrides = ref({})

function tablePagesParam() {
  const out = {}
  for (const b of blocks.value) {
    if (b.type === 'table') out[b.id] = { page: tablePages.value[b.id] || 1, page_size: TABLE_PAGE_SIZE }
  }
  return Object.keys(out).length ? out : null
}

function onTablePage({ block_id, page }) {
  tablePages.value = { ...tablePages.value, [block_id]: page }
  refreshData(true)
}

function onTableSort({ block_id, sort_by, sort_order }) {
  const s = { ...sortOverrides.value }
  if (sort_by) s[block_id] = { sort_by, sort_order }
  else delete s[block_id]
  sortOverrides.value = s
  const p = { ...tablePages.value }
  delete p[block_id]
  tablePages.value = p
  refreshData(true)
}

// 半成品块缺什么（画布占位提示 + 草稿过滤共用的单一事实源）：
// 未配置完成的块不进草稿——后端校验严格，半成品块会让整个草稿运行 400，画布上其他块也绘不出来
function blockMissing(b) {
  const miss = []
  const needsNum = (agg) => agg && !['count', 'ratio'].includes(agg)
  if (b.type === 'filter') {
    if (!b.field) miss.push('选择筛选字段')
  } else if (b.type === 'pivot') {
    if (!b.row?.field) miss.push('选择行维度')
    if (!b.col?.field) miss.push('选择列维度')
  } else if (b.type === 'chart') {
    if (b.chart_type !== 'gauge' && !b.group?.field) miss.push('选择分组字段')
    if ((b.metrics || []).some((m) => needsNum(m.agg || 'count') && !m.field)) miss.push('补全指标的数值字段')
    if (b.chart_type === 'mixed' && (b.metrics || []).filter((m) => m.agg).length < 2) miss.push('组合图至少 2 个指标')
    if (b.on_click === 'jump' && !b.jump_report_id) miss.push('选择跳转的目标报表')
  }
  // 单指标/统计卡/透视表：求和等数值聚合必须选字段（多指标模式下走 metrics，上面已查）
  if (['stat', 'chart', 'pivot'].includes(b.type) && needsNum(b.agg) && !b.field && !(b.metrics || []).length) {
    miss.push('选择数值字段')
  }
  return miss
}

function missingOf(blockId) {
  const b = blockOf(blockId)
  return b ? blockMissing(b) : []
}

function buildDraft() {
  const draftBlocks = blocks.value.filter((b) => blockMissing(b).length === 0)
  const readyIds = new Set(draftBlocks.map((b) => b.id))
  const layout = layoutData()
  for (const p of layout.pages) p.items = p.items.filter((it) => readyIds.has(it.block_id))
  return {
    datasets: cleanedDatasets(),
    blocks: cleanedBlocks(draftBlocks),
    layout,
    range: { mode: tpl.value.range?.mode || 'this_week', start: tpl.value.range?.start, end: tpl.value.range?.end },
  }
}

async function refreshData(silent = false) {
  if (!blocks.value.length) {
    blockResults.value = {}
    return
  }
  dataLoading.value = true
  try {
    const res = await runReport(tplId, null, null, null, buildDraft(), tablePagesParam(),
      Object.keys(sortOverrides.value).length ? sortOverrides.value : undefined)
    blockResults.value = Object.fromEntries((res.blocks || []).map((b) => [b.id, b]))
  } catch (e) {
    if (!silent) ElMessage.error(`绘制失败：${e.message}`)
  } finally {
    dataLoading.value = false
  }
}

// 配置变更自动重绘（防抖 800ms）：右侧面板改配置即自动刷新画布；
// 非静默——绘制失败要弹错误（原「应用并绘制」按钮的报错职责移到这里）
let redrawTimer = null
watch(blocks, () => {
  if (!tpl.value) return
  invalidIds.value = []   // 任何配置变更都清除校验红框（重新保存时再判定）
  tablePages.value = {}   // 明细表回第 1 页
  sortOverrides.value = {}   // 排序临时覆盖一并清掉（配置里的排序在右侧面板改）
  clearTimeout(redrawTimer)
  redrawTimer = setTimeout(() => refreshData(), 800)
}, { deep: true })

// GridLayout 内部态与 pages 解耦（关键：库在拖动时不发 update:layout，只在 dragend/resizeend 发 layout-updated）：
// ① 结构变化（换页/撤销/放置/排版/删除）→ layoutVersion++ → syncGlItems 重建布局数组；
// ② 拖动/缩放结束 → onLayoutUpdated 把坐标写回 pages。
const glItems = ref([])
const layoutVersion = ref(0)

function syncGlItems() {
  glItems.value = (activePage.value?.items || []).map((it) => {
    const { min } = BLOCK_SIZE[blockOf(it.block_id)?.type] || BLOCK_SIZE.text
    return { i: it.block_id, x: it.x, y: it.y, w: it.w, h: it.h, minW: min[0], minH: min[1] }
  })
}

watch([activePageId, layoutVersion], syncGlItems, { immediate: true })

function onLayoutUpdated(arr) {
  if (!activePage.value) return
  const byI = new Map(arr.map((it) => [it.i, it]))
  // grid-layout-plus 在挂载/布局同步后也会回调一次；坐标没实际变化时不算修改（否则刚进页面就提示未保存）
  let changed = false
  activePage.value.items = activePage.value.items.map((it) => {
    const g = byI.get(it.block_id)
    if (!g) return it
    if (g.x !== it.x || g.y !== it.y || g.w !== it.w || g.h !== it.h) changed = true
    return { block_id: it.block_id, x: g.x, y: g.y, w: g.w, h: g.h }
  })
  if (changed) commit()
}

// ---------- 结构变更标脏 + 撤销/重做 ----------
// 快照栈约定：所有结构性变更都是「先改状态、后调 commit()」，所以 commit 时把
// 「上一次提交后的快照」压入撤销栈——那正是本次变更前的状态。
const undoStack = ref([])
const redoStack = ref([])
const HISTORY_MAX = 50
let lastSnap = null

const canUndo = computed(() => undoStack.value.length > 0)
const canRedo = computed(() => redoStack.value.length > 0)

function snapshot() {
  return JSON.stringify({
    name: tpl.value?.name,
    blocks: tpl.value?.blocks || [],
    datasets: datasets.value,
    pages: pages.value,
  })
}

function commit() {
  if (!tpl.value) { dirty.value = true; return }
  if (lastSnap !== null) {
    undoStack.value.push(lastSnap)
    if (undoStack.value.length > HISTORY_MAX) undoStack.value.shift()
    redoStack.value = []
  }
  lastSnap = snapshot()
  dirty.value = true
}

function applySnap(s) {
  const d = JSON.parse(s)
  tpl.value.name = d.name
  tpl.value.blocks = d.blocks
  datasets.value = d.datasets
  pages.value = d.pages
  // 恢复后当前页签/选中块可能已不存在，收敛到合法状态
  if (!pages.value.some((p) => p.id === activePageId.value)) activePageId.value = pages.value[0]?.id || ''
  if (selectedBlockId.value && !d.blocks.some((b) => b.id === selectedBlockId.value)) selectedBlockId.value = null
  lastSnap = snapshot()
  dirty.value = true
  layoutVersion.value++
  refreshData(true)
}

function undo() {
  if (!undoStack.value.length) return
  redoStack.value.push(snapshot())
  applySnap(undoStack.value.pop())
}

function redo() {
  if (!redoStack.value.length) return
  undoStack.value.push(snapshot())
  applySnap(redoStack.value.pop())
}

// ---------- 区块放置 ----------

// 手动加块的默认配置（点击/拖拽共用）
const BLOCK_DEFS = {
  stat: { title: '统计卡', agg: 'count', field: null },
  chart: {
    title: '图表', chart_type: 'bar', group: { kind: 'month', field: 'created_at' },
    agg: 'count', field: null, top_n: 30, metrics: [], group2: { field: null }, stack: false, on_click: 'drill',
  },
  pivot: {
    title: '透视表', row: { kind: 'field', field: null }, col: { kind: 'month', field: 'created_at' },
    agg: 'count', field: null, totals: true,
  },
  table: { title: '明细表', columns: [], limit: 100 },   // limit 已废弃：明细表不再限条数（前端分页），保留字段兼容旧数据
  text: { title: '文本', content: '' },
  filter: { title: '筛选', field: null, target: { mode: 'same_dataset' } },
}

function buildBlock(type) {
  if (type !== 'text' && !datasets.value.length) {
    ElMessage.warning('先在左侧添加数据源')
    return null
  }
  const ds = datasets.value[0]
  const base = { id: nextBlockId(), dataset_id: ds?.id, date_field: 'created_at', filters: { logic: 'AND', rules: [] } }
  const b = { ...base, type, ...BLOCK_DEFS[type] }
  if (type === 'text') { delete b.dataset_id; delete b.date_field }   // 文本块不依赖数据源
  if (type === 'filter') delete b.date_field                          // 筛选块自身不查数据，日期字段无意义
  return b
}

// 落块：加到当前页签（pos 缺省追加到底部）并选中，右侧配置面板随即展开
function mountBlock(b, pos) {
  tpl.value.blocks.push(b)
  // pos 来自 dropPosition 只有坐标，必须补 block_id（GridLayout 以它为 key，缺了不渲染）
  const item = pos ? { block_id: b.id, ...pos } : defaultItem(b, activePage.value.items)
  activePage.value.items.push(item)
  selectedBlockId.value = b.id
  commit()
  layoutVersion.value++
  if (b.type !== 'text') refreshData(true)
}

// 侧栏点击加块
function addBlock(type) {
  if (!activePage.value) return
  const b = buildBlock(type)
  if (!b) return
  mountBlock(b, null)
  ElMessage.success(`已添加「${b.title}」，在右侧完善配置`)
}

function place(block) {
  if (!activePage.value) return
  activePage.value.items.push(defaultItem(block, activePage.value.items))
  commit()
  layoutVersion.value++
}

function autoArrange() {
  const p = activePage.value
  if (!p) return
  const pageBlocks = p.items.map((it) => blockOf(it.block_id)).filter(Boolean)
  p.items = autoLayout(pageBlocks).pages[0].items
  commit()
  layoutVersion.value++
  ElMessage.success('已按规则自动排版')
}

// ---------- 页签管理 ----------
function addPage() {
  const id = nextPageId(pages.value)
  pages.value.push({ id, title: `页签${pages.value.length + 1}`, items: [] })
  activePageId.value = id
  commit()
}

async function renamePage(p) {
  try {
    const { value } = await ElMessageBox.prompt('页签名称（≤20 字）', '重命名', {
      inputValue: p.title, inputValidator: (v) => (v?.trim().length ? (v.trim().length <= 20 || '不能超过 20 字') : '不能为空'),
    })
    p.title = value.trim()
    commit()
  } catch { /* 取消 */ }
}

async function deletePage(p) {
  try {
    await ElMessageBox.confirm(
      p.items.length ? `删除页签「${p.title}」？页内 ${p.items.length} 个区块将一并删除。` : `删除页签「${p.title}」？`,
      '删除页签', { type: 'warning' },
    )
  } catch { return }
  // 页内区块一并删除（已无"未放置"暂存区）
  const ids = new Set(p.items.map((it) => it.block_id))
  if (ids.size) {
    tpl.value.blocks = blocks.value.filter((b) => !ids.has(b.id))
    for (const other of pages.value) other.items = other.items.filter((it) => !ids.has(it.block_id))
    if (selectedBlockId.value && ids.has(selectedBlockId.value)) selectedBlockId.value = null
  }
  pages.value = pages.value.filter((x) => x.id !== p.id)
  if (activePageId.value === p.id) activePageId.value = pages.value[0]?.id || ''
  commit()
}

function movePage(pi, dir) {
  const arr = pages.value
  ;[arr[pi], arr[pi + dir]] = [arr[pi + dir], arr[pi]]
  commit()
}

// ---------- 顶栏全局口径（与查看页一致；改后标脏并用草稿重绘画布） ----------
const globalRangeCustom = computed({
  get: () => (tpl.value?.range?.start && tpl.value?.range?.end ? [tpl.value.range.start, tpl.value.range.end] : null),
  set: (v) => {
    if (!tpl.value) return
    tpl.value.range = { ...tpl.value.range, start: v?.[0] || null, end: v?.[1] || null }
    if (v?.[0] && v?.[1]) onGlobalRangeApplied()
  },
})

function onGlobalRangeMode(v) {
  if (!tpl.value) return
  tpl.value.range = { mode: v, start: null, end: null }
  if (v !== 'custom') onGlobalRangeApplied()   // custom 等日期选完再重绘
}

function onGlobalRangeApplied() {
  dirty.value = true
  refreshData(true)
}

// ---------- 模板设置 ----------
// 全局口径在顶栏「全局时间」直接编辑，设置抽屉只管描述 + 定时推送
const settingsVisible = ref(false)
const settingsForm = reactive({
  name: '', description: '', enabled: false,
  schedule: { type: '', minutes: 60, expr: '0 9 * * 1' },
  push: { recipients: '', formats: ['html_inline', 'xlsx'], subject: '', webhooks: [] },
})

// ---------- 阈值告警（推送守卫：多条件，全部/任一满足才发送） ----------
const GUARD_OPS = [['gt', '>'], ['gte', '≥'], ['lt', '<'], ['lte', '≤'], ['eq', '='], ['ne', '≠']]

function onGuardToggle(v) {
  settingsForm.push.guard = v
    ? { logic: 'AND', rules: [{ block_id: statBlocks.value[0]?.id || null, op: 'gt', value: 0 }] }
    : undefined
}

function addGuardRule() {
  settingsForm.push.guard.rules.push({ block_id: statBlocks.value[0]?.id || null, op: 'gt', value: 0 })
}

// 收件邮箱：标签数组 ⇄ 逗号分隔字符串（后端 push.recipients 的存储格式），逐个校验格式
const recipientsList = computed(() =>
  String(settingsForm.push.recipients || '').split(/[,，\n]/).map((s) => s.trim()).filter(Boolean))

function setRecipients(list) {
  const re = /^\S+@\S+\.\S+$/
  const bad = list.filter((s) => !re.test(s))
  if (bad.length) ElMessage.warning(`已忽略格式不正确的邮箱：${bad.join('、')}`)
  settingsForm.push.recipients = list.filter((s) => re.test(s)).join(',')
}

// ---------- 执行周期：Cron 可视化构建器（与工作流触发频率同款；APScheduler 周一=0） ----------
const cronMode = ref('day')
const cronMinute = ref(0)          // 每小时模式：第几分
const cronTime = ref('09:00')      // 天/周/月模式：HH:mm
const cronWeek = ref(0)            // 周一 = 0
const cronDom = ref(1)             // 每月几号

function parseCron(expr) {
  const p = (expr || '').trim().split(/\s+/)
  if (p.length !== 5) return 'custom'
  const [m, h, dom, , dow] = p
  const num = (s) => /^\d+$/.test(s)
  if (num(m) && h === '*' && dom === '*' && dow === '*') { cronMinute.value = Number(m); return 'hour' }
  if (num(m) && num(h) && dom === '*' && dow === '*') {
    cronTime.value = `${h.padStart(2, '0')}:${m.padStart(2, '0')}`; return 'day'
  }
  if (num(m) && num(h) && dom === '*' && num(dow)) {
    cronTime.value = `${h.padStart(2, '0')}:${m.padStart(2, '0')}`; cronWeek.value = Number(dow) % 7; return 'week'
  }
  if (num(m) && num(h) && num(dom) && dow === '*') {
    cronTime.value = `${h.padStart(2, '0')}:${m.padStart(2, '0')}`; cronDom.value = Number(dom); return 'month'
  }
  return 'custom'
}

function buildCron() {
  const [h, m] = (cronTime.value || '09:00').split(':').map(Number)
  switch (cronMode.value) {
    case 'hour': return `${cronMinute.value} * * * *`
    case 'day': return `${m} ${h} * * *`
    case 'week': return `${m} ${h} * * ${cronWeek.value}`
    case 'month': return `${m} ${h} ${cronDom.value} * *`
    default: return settingsForm.schedule.expr
  }
}

watch([cronMode, cronMinute, cronTime, cronWeek, cronDom], () => {
  if (cronMode.value !== 'custom') settingsForm.schedule.expr = buildCron()
})

function openSettings() {
  const t = tpl.value
  Object.assign(settingsForm, {
    description: t.description || '', enabled: t.enabled,
    schedule: { type: '', minutes: 60, expr: '0 9 * * 1', ...(t.schedule || {}) },
    push: { recipients: '', formats: ['html_inline', 'xlsx'], subject: '', webhooks: [], ...(t.push || {}) },
  })
  // Cron 构建器按已存表达式反向解析回填
  cronMode.value = parseCron(settingsForm.schedule.expr)
  settingsVisible.value = true
}

function applySettings() {
  tpl.value.description = settingsForm.description
  tpl.value.enabled = settingsForm.schedule.type ? settingsForm.enabled : false
  tpl.value.schedule = settingsForm.schedule.type
    ? (settingsForm.schedule.type === 'interval'
      ? { type: 'interval', minutes: settingsForm.schedule.minutes }
      : { type: 'cron', expr: settingsForm.schedule.expr })
    : {}
  tpl.value.push = settingsForm.schedule.type
    ? { ...settingsForm.push, webhooks: (settingsForm.push.webhooks || []).filter((w) => (w.url || '').trim()) }
    : {}
  settingsVisible.value = false
  dirty.value = true
  ElMessage.success('设置已应用，保存后生效')
}

// ---------- 推送预览（按已保存的配置渲染，不发送） ----------
const pushPreviewVisible = ref(false)
const pushPreviewLoading = ref(false)
const pushPreview = ref(null)

async function onPreviewPush() {
  if (dirty.value) ElMessage.warning('预览基于已保存的配置；当前修改未保存，内容可能不一致')
  pushPreviewVisible.value = true
  pushPreviewLoading.value = true
  pushPreview.value = null
  try {
    pushPreview.value = await previewPushReport(tplId)
  } catch (e) {
    pushPreviewVisible.value = false
    ElMessage.error(e.message)
  } finally {
    pushPreviewLoading.value = false
  }
}

// ---------- AI 辅助 ----------
const aiVisible = ref(false)
const aiTableId = ref(null)
const aiDescription = ref('')
const aiGenerating = ref(false)
const aiResult = ref(null)
const aiMode = ref('replace')   // replace 替换全部 / append_page 追加为新页签 / append_current 追加到当前页
const aiAppend = ref(true)      // 生成意图：true=只生成本次要求的区块（追加）；false=重新设计整表

function openAi() {
  aiResult.value = null
  aiMode.value = 'replace'
  aiAppend.value = !!blocks.value.length   // 有存量默认追加意图
  aiTableId.value = datasets.value[0]?.base_table_id || null
  aiVisible.value = true
}

async function aiGenerate() {
  aiGenerating.value = true
  try {
    aiResult.value = await aiAssistReport(aiTableId.value, aiDescription.value.trim(), aiAppend.value)
    // 追加意图生成的就是增量区块，应用方式默认「追加为新页签」
    aiMode.value = aiAppend.value && blocks.value.length ? 'append_page' : 'replace'
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiGenerating.value = false
  }
}

async function aiApply() {
  if (aiMode.value === 'replace' && blocks.value.length) {
    try {
      await ElMessageBox.confirm('应用将替换当前全部区块并重排布局，确定继续？', 'AI 辅助', { type: 'warning' })
    } catch { return }
  }
  // 找到或创建该表对应的数据集
  let dset = datasets.value.find((d) => d.base_table_id === aiTableId.value)
  if (!dset) {
    const t = tables.value.find((x) => x.id === aiTableId.value)
    dset = { id: nextDatasetId(), name: t?.label || '', base_table_id: aiTableId.value, joins: [], computed_fields: [] }
    datasets.value.push(dset)
    await refreshFields(dset.id)
  }
  const df = aiResult.value.range?.date_field || 'created_at'
  const mapped = aiResult.value.blocks.map((b) => ({
    ...b,
    filters: b.filters || { logic: 'AND', rules: [] },
    group: b.group ? { ...b.group } : undefined,
    dataset_id: dset.id,
    date_field: df,
    ...(b.type === 'pivot' ? {
      row: { kind: 'field', field: null, ...(b.row || {}) },
      col: { kind: 'field', field: null, ...(b.col || {}) },
      totals: b.totals !== false,
    } : {}),
  }))

  // AI 配的报表设置（执行周期/推送渠道/阈值告警）：应用进模板；推送默认停用，用户到设置里确认后启用
  const aiSchedule = aiResult.value.schedule
  if (aiSchedule?.type) {
    tpl.value.schedule = aiSchedule.type === 'interval'
      ? { type: 'interval', minutes: aiSchedule.minutes }
      : { type: 'cron', expr: aiSchedule.expr }
    tpl.value.enabled = false
  }
  if (aiResult.value.push) {
    tpl.value.push = { recipients: '', formats: ['html_inline'], subject: '', webhooks: [], ...aiResult.value.push }
    tpl.value.enabled = false
  }
  if (aiMode.value === 'replace') {
    tpl.value.blocks = mapped
    pages.value = autoLayout(tpl.value.blocks).pages
    activePageId.value = pages.value[0]?.id || ''
    tpl.value.range = { mode: aiResult.value.range?.mode || 'this_week', start: null, end: null }
    if (!tpl.value.name.trim()) tpl.value.name = aiResult.value.name
  } else {
    // 追加模式：AI 生成的块 id（b1/b2…）可能与现有冲突，统一重新分配；不动现有布局
    if (!mapped.length) {
      // 纯口径调整（blocks 为空）：只改全局口径，不加块
      const r = aiResult.value.range
      if (r?.mode) {
        tpl.value.range = { mode: r.mode, start: r.start || null, end: r.end || null }
        aiVisible.value = false
        settingsVisible.value = false
        dirty.value = true
        commit()
        ElMessage.success('已调整全局口径')
        refreshData(true)
        return
      }
      ElMessage.warning('AI 没有生成任何内容，换个说法试试')
      return
    }
    for (const b of mapped) b.id = nextBlockId()
    tpl.value.blocks.push(...mapped)
    if (aiMode.value === 'append_page') {
      const page = { id: nextPageId(pages.value), title: `${aiResult.value.name || 'AI 生成'}`.slice(0, 20), items: [] }
      page.items = autoLayout(mapped).pages[0].items
      pages.value.push(page)
      activePageId.value = page.id
    } else {
      // append_current：追加到当前页底部
      for (const b of mapped) activePage.value.items.push(defaultItem(b, activePage.value.items))
    }
  }
  aiVisible.value = false
  settingsVisible.value = false
  dirty.value = true
  commit()
  layoutVersion.value++
  ElMessage.success(aiMode.value === 'replace' ? '已应用，可继续调整后保存' : '已追加，可继续调整后保存')
  refreshData(true)   // AI 生成后立即绘制
}

// ---- AI 帮我设置这个区块（与工作流节点「AI 帮我配置」同款：一句话 → 配置 patch，合并后自动重绘） ----
const aiBlockVisible = ref(false)
const aiBlockDesc = ref('')
const aiBlockLoading = ref(false)

function openBlockAi() {
  aiBlockDesc.value = ''
  aiBlockVisible.value = true
}

async function applyBlockAi() {
  const b = selectedBlock.value
  if (!b) return
  if (!aiBlockDesc.value.trim()) { ElMessage.warning('请描述你想要的效果'); return }
  aiBlockLoading.value = true
  try {
    // 数据集字段（含关联/计算字段）作为 AI 的可用字段清单
    const fields = (fieldsOf(b.dataset_id) || []).map((f) => ({
      field_name: f.field_name, label: f.label, data_type: f.data_type, options: f.options || {},
    }))
    // 当前配置一并给 AI（编辑语义：如「增加一个指标」= 在现有 metrics 上加，而不是重生成一份）
    const current = cleanedBlocks([b]).map(({ id, dataset_id, date_field, type, ...rest }) => rest)[0]
    // 文本块：附上统计卡变量映射（{b3}=成交总额），AI 才能写出能真实取值的占位符
    if (b.type === 'text') {
      current.stats = statBlocks.value.map((s) => ({ ref: `{${s.id}}`, label: s.title || s.id }))
    }
    const r = await aiAssistBlock(b.type, aiBlockDesc.value.trim(), fields, current)
    // 合并 patch（不动 id/dataset_id/type/date_field）；blocks 的 watch 会自动重绘
    Object.assign(b, r.config || {})
    aiBlockVisible.value = false
    aiBlockDesc.value = ''
    commit()   // 进撤销栈，误填可 Ctrl+Z
    ElMessage.success(r.notes ? `已填入 AI 配置（${r.notes}），请检查后保存` : '已填入 AI 生成的配置，请检查后保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiBlockLoading.value = false
  }
}

// ---------- 加载 / 保存 ----------
async function load() {
  loading.value = true
  try {
    tpl.value = await getReport(tplId)
    upgradeLegacy()
    const layoutData = tpl.value.layout
      ? normalizeLayout(tpl.value.layout, tpl.value.blocks || [])
      : autoLayout(tpl.value.blocks || [])
    pages.value = layoutData.pages
    activePageId.value = pages.value[0]?.id || ''
    dirty.value = !tpl.value.datasets?.length  // 旧模板升级后未落库，提示保存
    await refreshAllFields()
    refreshData(true)   // 打开即绘制真实数据
    // 撤销/重做基线：加载完成的状态作为第一个快照，历史清空
    lastSnap = snapshot()
    undoStack.value = []
    redoStack.value = []
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// 旧格式（table_id + source + filter_fields）→ v3 结构（内存合成，保存即升级）
function upgradeLegacy() {
  const t = tpl.value
  if (t.datasets?.length) {
    datasets.value = t.datasets.map((d) => ({
      ...d, joins: d.joins || [], computed_fields: d.computed_fields || [],
    }))
    return
  }
  const d = {
    id: 'd1', name: t.table_label || '主数据集', base_table_id: t.table_id,
    joins: (t.source?.joins || []).map((j) => ({ ...j, on: (j.on || []).map((o) => ({ ...o })) })),
    computed_fields: (t.source?.computed_fields || []).map((c) => ({ type: '', ...c })),
  }
  datasets.value = [d]
  const df = t.range?.date_field || 'created_at'
  const newBlocks = []
  for (const b of t.blocks || []) {
    if (b.type === 'text') {
      newBlocks.push(b)
      continue
    }
    const nb = { ...b, dataset_id: b.dataset_id || 'd1' }
    if (!('date_field' in nb)) nb.date_field = df
    newBlocks.push(nb)
  }
  // 旧查看端筛选字段 → 筛选组件块（放到首页顶部）
  const fbs = (t.filter_fields || []).map((fn) => ({
    id: nextBlockId(), type: 'filter', title: fn, field: fn, dataset_id: 'd1',
    date_field: null, target: { mode: 'same_dataset' }, filters: { logic: 'AND', rules: [] },
  }))
  t.blocks = [...fbs, ...newBlocks]
  if (fbs.length && t.layout?.pages?.length) {
    // 有布局：插入到首页顶部（现有内容下移 2 行 × 每行 4 个）
    const page = t.layout.pages[0]
    const rows = Math.ceil(fbs.length / 4) * 2
    page.items = page.items.map((it) => ({ ...it, y: it.y + rows }))
    fbs.forEach((fb, i) => page.items.unshift({ block_id: fb.id, x: (i % 4) * 6, y: Math.floor(i / 4) * 2, w: 6, h: 2 }))
  }
}

function cleanedDatasets() {
  return datasets.value.map((d) => ({
    id: d.id,
    name: (d.name || '').trim() || d.id,
    base_table_id: d.base_table_id,
    joins: (d.joins || [])
      .filter((j) => j.table_id && j.prefix?.trim() && j.on.some((o) => o.left && o.right))
      .map((j) => ({ table_id: j.table_id, prefix: j.prefix.trim(), on: j.on.filter((o) => o.left && o.right) })),
    computed_fields: (d.computed_fields || [])
      .filter((c) => c.name?.trim() && c.expr?.trim())
      .map((c) => ({ name: c.name.trim(), expr: c.expr.trim(), ...(c.type ? { type: c.type } : {}) })),
  }))
}

function layoutData() {
  return {
    version: 1,
    grid: { cols: GRID_COLS, row_height: ROW_HEIGHT },
    pages: pages.value.map((p) => ({
      id: p.id,
      title: p.title,
      items: p.items.map((it) => ({ block_id: it.block_id, x: it.x, y: it.y, w: it.w, h: it.h })),
    })),
  }
}

function cleanedBlocks(list) {
  return list.map((b) => {
    const { series_mode, ...rest } = b
    // filters 可能缺失（AI 生成/旧数据/API 直接建的块），缺省给空条件组——否则这里抛 TypeError，
    // 被 refreshData 吞掉后画布全是「等待数据…」占位
    const f = b.filters || {}
    return { ...rest, filters: { logic: f.logic || 'AND', rules: (f.rules || []).filter((r) => r.field && r.op) } }
  })
}

function buildPayload() {
  const t = tpl.value
  const dsets = cleanedDatasets()
  return {
    name: (t.name || '').trim() || '未命名报表',
    description: t.description || null,
    table_id: dsets[0]?.base_table_id || t.table_id,
    enabled: t.enabled,
    range: { mode: t.range?.mode || 'this_week', start: t.range?.start || null, end: t.range?.end || null },
    blocks: cleanedBlocks(t.blocks || []),
    layout: layoutData(),
    source: null,
    datasets: dsets,
    filter_fields: [],
    schedule: t.schedule || {},
    push: t.push || {},
  }
}

async function save() {
  invalidIds.value = []
  // 本地预检：半成品块直接标红并定位，不发请求（与草稿过滤同一套 blockMissing 规则）
  const bad = blocks.value.filter((b) => blockMissing(b).length)
  if (bad.length) {
    invalidIds.value = bad.map((b) => b.id)
    locateBlock(bad[0].id)
    ElMessage.error(`有 ${bad.length} 个区块未配置完成（已红框标出）：「${bad[0].title || bad[0].id}」${blockMissing(bad[0]).join('、')}`)
    return
  }
  saving.value = true
  try {
    tpl.value = await updateReport(tplId, buildPayload())
    dirty.value = false
    ElMessage.success('已保存')
  } catch (e) {
    // 后端校验错误统一带「区块 <id>（标题）：原因」，解析出来在画布标红定位
    const m = /区块\s+([A-Za-z0-9_]+)/.exec(e.message || '')
    if (m && blockOf(m[1])) {
      invalidIds.value = [m[1]]
      locateBlock(m[1])
    }
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

// 跳到指定区块：切到所在页签 + 选中（配置面板展开）
function locateBlock(blockId) {
  const pg = pages.value.find((p) => p.items.some((it) => it.block_id === blockId))
  if (pg) activePageId.value = pg.id
  selectedBlockId.value = blockId
}

// ---------- 试运行（draft 沙盒，不落库） ----------
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewResult = ref(null)

async function previewRun() {
  previewVisible.value = true
  previewLoading.value = true
  previewResult.value = null
  try {
    previewResult.value = await runReport(tplId, null, null, null, buildDraft())
  } catch (e) {
    previewVisible.value = false
    ElMessage.error(e.message)
  } finally {
    previewLoading.value = false
  }
}

function goBack() {
  // 设计器是列表页「设计」入口进入的，返回即回列表
  if (dirty.value) {
    ElMessageBox.confirm('有未保存的修改，确定离开？', '提示', { type: 'warning' })
      .then(() => router.push('/reports'))
      .catch(() => {})
  } else {
    router.push('/reports')
  }
}

function onGoView() {
  // 查看页展示的是已保存内容：有未保存修改时先提示，避免"设计器里看到的和查看页不一样"
  if (dirty.value) {
    ElMessageBox.confirm('有未保存的修改，查看页只能看到已保存的内容，确定离开？', '提示', { type: 'warning' })
      .then(() => router.push(`/reports/${tplId}/view`))
      .catch(() => {})
  } else {
    router.push(`/reports/${tplId}/view`)
  }
}

function onBeforeUnload(e) {
  if (dirty.value) e.preventDefault()
}

onMounted(async () => {
  await load()
  if (!tables.value.length) {
    try { tables.value = await listTables() } catch { /* 添加数据源时会重试 */ }
  }
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  clearTimeout(redrawTimer)
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
/* 结构与工作流编辑器一致：白顶栏 + 左白栏 + 灰画布 + 右白配置面板（可拖宽）。
   高度用 100%（填满 el-main 内容区），不能用 100vh：外层还有顶栏 + el-main padding。 */
.rp-designer { height: 100%; display: flex; flex-direction: column; background: #f5f7fa; }
.topbar {
  display: flex; align-items: center; gap: 14px; padding: 8px 16px;
  background: #fff; border-bottom: 1px solid #e4e7ed;
}
/* 顶栏分组：组内紧凑，组间竖杆分隔 */
.tb-group { display: flex; align-items: center; gap: 8px; }
.tb-divider { width: 1px; height: 20px; background: #dcdfe6; flex-shrink: 0; }
.tb-label { font-size: 12px; color: #909399; flex-shrink: 0; }
.name-input { width: 220px; }
.spacer { flex: 1; }
.range-select { width: 118px; flex-shrink: 0; }
.range-dates { width: 230px; flex-shrink: 0; }
/* .ai-btn 紫色样式已上移 App.vue 全局 */

/* 页签：顶栏居中、可横向滚动 */
.page-bar {
  display: flex; align-items: center; gap: 6px; max-width: 44vw; overflow-x: auto;
  scrollbar-width: none;
}
.page-bar::-webkit-scrollbar { display: none; }
.page-tab {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; cursor: pointer;
  background: #f5f7fa; border: 1px solid #dcdfe6; border-radius: 6px; font-size: 13px; color: #606266;
  user-select: none; white-space: nowrap;
}
.page-tab.active { border-color: #409eff; color: #409eff; background: #ecf5ff; }
.page-tab .el-icon { font-size: 12px; color: #909399; }
.page-tab .el-icon:hover { color: #409eff; }

.body { flex: 1; display: flex; min-height: 0; position: relative; }

/* 左侧栏（与工作流节点面板一致：白底、右边线） */
.sidebar { width: 210px; background: #fff; border-right: 1px solid #e4e7ed; overflow-y: auto; padding: 10px; }
.side-section { margin-bottom: 18px; }
.side-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.ds-group { margin-bottom: 12px; }
.ds-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 2px; margin-bottom: 4px; }
.ds-name { font-size: 12px; font-weight: 600; color: #909399; }
.ds-ops { display: inline-flex; gap: 8px; }
.ds-ops .el-icon { color: #909399; cursor: pointer; }
.ds-ops .el-icon:hover { color: #409eff; }
.field-chip {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px; margin-bottom: 4px; cursor: grab;
  border: 1px solid #e4e7ed; border-radius: 6px; font-size: 12px; background: #fff;
}
.field-chip:hover { border-color: #409eff; background: #ecf5ff; }
/* 区块类型面板：两列网格，点击添加 */
.block-palette { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.block-palette .palette-item {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 10px 0 8px; font-size: 12px; color: #303133; cursor: pointer;
  border: 1px solid #e4e7ed; border-radius: 6px; background: #fff;
}
.block-palette .palette-item:hover { border-color: #409eff; background: #ecf5ff; color: #409eff; }
.block-palette .pi-icon { font-size: 18px; color: #909399; }
.block-palette .palette-item:hover .pi-icon { color: #409eff; }
.fc-type { flex-shrink: 0; width: 18px; height: 18px; border-radius: 4px; font-size: 11px; text-align: center; line-height: 18px; color: #fff; }
.fc-type.num { background: #e6a23c; }
.fc-type.date { background: #67c23a; }
.fc-type.bool { background: #909399; }
.fc-type.text { background: #409eff; }
.fc-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 画布（灰底点阵，无卡片包裹） */
.canvas-wrap {
  flex: 1; min-width: 0; position: relative; overflow-y: auto; padding: 12px;
  background-image: radial-gradient(circle, #d4d7de 1px, transparent 1px); background-size: 16px 16px;
}
.gi-card {
  height: 100%; background: #fff; border: 1px solid #e4e7ed; border-radius: 8px;
  display: flex; flex-direction: column; overflow: hidden; cursor: pointer;
}
.gi-card.selected { border-color: #409eff; box-shadow: 0 0 0 2px rgba(64, 158, 255, .25); }
/* 保存校验未通过的区块红框标记（编辑后自动清除） */
.gi-card.invalid { border-color: #f56c6c; box-shadow: 0 0 0 2px rgba(245, 108, 108, .25); }
/* 画布卡片头（gi-head）已显示标题，隐藏筛选块控件上方的重复标题（查看页没有卡片头，仍需显示） */
.gi-real :deep(.filter-label) { display: none; }
.gi-head {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  border-bottom: 1px solid #f0f2f5; font-size: 13px;
}
.gi-type { flex-shrink: 0; font-size: 12px; color: #fff; background: #409eff; border-radius: 4px; padding: 1px 6px; }
.gi-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #303133; }
.gi-ds { flex-shrink: 0; font-size: 11px; color: #909399; background: #f0f2f5; border-radius: 4px; padding: 1px 6px; }
.gi-body { flex: 1; display: flex; align-items: center; justify-content: center; color: #c0c4cc; font-size: 12px; }
/* 画布内真实渲染：压平内层卡片，避免双层阴影 */
.gi-real { flex: 1; min-height: 0; overflow: hidden; }
.gi-real :deep(.block-card), .gi-real :deep(.stat-card) { box-shadow: none; border-radius: 0; height: 100%; box-sizing: border-box; }
.gi-real :deep(.rblock), .gi-real :deep(.rblock.fill) { height: 100%; }
.panel-tip { margin-top: 8px; font-size: 12px; color: #c0c4cc; line-height: 1.5; }

.empty-hint {
  position: absolute; top: 40%; left: 50%; transform: translateX(-50%);
  color: #c0c4cc; font-size: 14px; pointer-events: none;
}

/* 右侧配置面板：浮动覆盖画布右缘（画布尺寸恒定，块不被推挤缩放），可拖宽 */
.config-panel {
  position: absolute; right: 0; top: 0; bottom: 0; z-index: 20;
  background: #fff; border-left: 1px solid #e4e7ed; box-shadow: -6px 0 20px rgba(0, 0, 0, .1);
  overflow-y: auto; padding: 12px; animation: panel-in .16s ease-out;
}
@keyframes panel-in {
  from { transform: translateX(24px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
.panel-resizer { position: absolute; left: 0; top: 0; bottom: 0; width: 5px; cursor: col-resize; z-index: 5; }
.panel-resizer:hover { background: rgba(64, 158, 255, .35); }
.config-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.config-title { font-size: 13px; font-weight: 600; }
/* 配置面板的 AI 入口：蓝色文字链 */
.ai-link { color: #409eff; }
.ai-link:hover, .ai-link:focus { color: #337ecc; }
.mb { margin-bottom: 10px; }
.w-full { width: 100%; }

/* ---------- 数据集设置抽屉 ---------- */
/* 抽屉标题与正文的间距收紧（el-drawer 标题默认 32px 太大；EP 不透传自定义 class 到抽屉根，按页面作用域统一收紧） */
.rp-designer :deep(.el-drawer__header) { margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #f2f6fc; }
.dsd-head { display: flex; align-items: center; gap: 14px; }

/* ---------- 报表设置抽屉：分区卡片化 ---------- */
.rp-settings :deep(.el-form-item) { margin-bottom: 10px; }
.rp-settings :deep(.el-form-item__label) { padding-bottom: 2px !important; font-size: 12px; color: #606266; }
.rp-settings .hint { font-size: 12px; color: #909399; line-height: 1.6; margin-top: 6px; }
.rp-settings .mt { margin-top: 8px; }
.rp-settings .row { display: flex; align-items: center; gap: 8px; }
/* 表单项内容是 flex-wrap 布局：构建器行占满整行换到 radio 组下方（否则会贴在同一行右侧） */
.rp-settings .mt.row { flex-basis: 100%; }
.rp-settings .row > span { color: #606266; font-size: 12px; }
.set-sec {
  border: 1px solid #ebeef5; border-radius: 10px; padding: 12px 14px; margin-bottom: 14px;
  background: #fff;
}
.set-sec-title { font-size: 13px; font-weight: 600; color: #303133; display: flex; align-items: center; margin-bottom: 4px; }
.set-sec-desc { font-size: 12px; color: #909399; margin-bottom: 10px; line-height: 1.6; }
.set-sub {
  font-size: 12px; font-weight: 600; color: #909399; margin: 12px 0 8px;
  padding-top: 10px; border-top: 1px dashed #ebeef5;
}
.wh-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.guard-box { margin-top: 8px; border: 1px solid #ebeef5; border-radius: 8px; padding: 10px 12px; background: #fafbfc; }
.guard-logic { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #606266; margin-bottom: 8px; }
.guard-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.dsd-title { font-size: 16px; font-weight: 600; color: #303133; }
.dsd-name { width: 220px; }
.src-sec { margin-bottom: 22px; }
.src-sec-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.src-sec-title { font-size: 14px; font-weight: 600; color: #303133; }
.src-sec-desc { font-size: 12px; color: #909399; margin-bottom: 10px; line-height: 1.6; }
.src-empty { padding: 14px; text-align: center; font-size: 12px; color: #c0c4cc; background: #fafafa; border-radius: 8px; }

/* 关联表卡片 */
.join-card { border: 1px solid #e4e7ed; border-radius: 8px; margin-bottom: 10px; overflow: hidden; }
.join-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 12px; background: #f5f7fa; border-bottom: 1px solid #ebeef5;
}
.join-no { font-size: 12px; font-weight: 600; color: #606266; }
.join-body { padding: 10px 12px; }
.join-field { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.jf-label { flex-shrink: 0; width: 64px; font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 2px; }
.jf-grow { flex: 1; min-width: 0; }
.hint-icon { color: #c0c4cc; cursor: help; font-size: 13px; }
.join-conds { display: flex; gap: 8px; align-items: flex-start; }
.join-cond-list { flex: 1; min-width: 0; }
.join-cond { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.join-eq { color: #909399; flex-shrink: 0; }

/* 计算字段卡片 */
.cf-card { border: 1px solid #e4e7ed; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }
.cf-row2 { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cf-expr { font-family: monospace; }
.cf-expr-row { display: flex; align-items: center; gap: 4px; }
.cf-expr-row .el-input { flex: 1; }
.cf-check { margin-top: 4px; font-size: 12px; line-height: 1.6; }
.cf-check.ok { color: #67c23a; }
.cf-check.err { color: #f56c6c; }
.cf-check.checking { color: #c0c4cc; }
.cf-help { margin-top: 8px; border: none; }
.cf-help :deep(.el-collapse-item__header) { font-size: 12px; color: #909399; height: 32px; border: none; }
.cf-help :deep(.el-collapse-item__wrap) { border: none; }
.cf-help-body { font-size: 12px; color: #606266; line-height: 1.9; }
.cf-help-body code { background: #f5f7fa; border: 1px solid #e4e7ed; border-radius: 4px; padding: 0 4px; }

/* 结果字段预览 */
.dsd-preview {
  display: flex; flex-wrap: wrap; gap: 6px; padding: 12px;
  background: #fafafa; border: 1px dashed #e4e7ed; border-radius: 8px; max-height: 160px; overflow-y: auto;
}

/* 推送预览 */
.pp-subject { font-size: 13px; color: #606266; margin-bottom: 8px; }
.pp-frame { width: 100%; height: 56vh; border: 1px solid #e4e7ed; border-radius: 6px; background: #fff; }
.pp-md {
  margin: 0; padding: 12px; max-height: 56vh; overflow: auto; white-space: pre-wrap;
  background: #f5f7fa; border-radius: 6px; font-size: 12px; color: #606266;
}

:deep(.vgl-item--placeholder) { background: #409eff !important; opacity: .2; }
</style>
