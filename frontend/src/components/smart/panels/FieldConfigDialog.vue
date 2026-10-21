<template>
  <!-- 字段配置面板（对齐参照 docs/智慧表格/添加列/列-*.png）：
       字段名称 → 字段类型（带图标）→ [类型说明] → 分隔线 → 类型专属设置（灰色小标题分区）→
       底部：左侧 AI 入口（使用 AI 生成/计算/判断/匹配标签/生成公式），右侧 确定 / 取消。
       无标题栏；所有入口均非模态，at 存在时锚定在打开位置（anchoredDialogAttrs），点击外部收起 -->
  <el-dialog :model-value="visible" :width="isNumberFamily ? '322px' : '470px'" :show-close="false" class="st-fcd" :class="{ 'st-fcd-number': isNumberFamily }" append-to-body
             v-bind="anchoredDialogAttrs(at, isNumberFamily ? 322 : 470, 560)" :close-on-press-escape="!fxEditor && !aiFormula" @opened="placeEditor" @update:model-value="$emit('close')" destroy-on-close>
    <div ref="editorBody" class="fcd">
      <input ref="nameRef" v-model="form.label" class="fcd-input fcd-name" placeholder="字段名称" maxlength="100"
             @keydown.enter="save" @keydown.esc="$emit('close')" />
      <el-select v-model="form.field_type" class="fcd-select fcd-type" popper-class="fcd-pop" :disabled="!!field && isSystemLike"
                 @change="onTypeChange">
        <template #prefix><StIcon :name="form.field_type" :size="17" class="fcd-pre" /></template>
        <el-option-group v-for="g in TYPE_GROUPS" :key="g.key">
          <el-option v-for="ft in g.types" :key="ft" :value="ft" :label="FIELD_REGISTRY[ft].label">
            <span class="fcd-opt"><StIcon :name="ft" :size="16" />{{ FIELD_REGISTRY[ft].label }}</span>
          </el-option>
        </el-option-group>
      </el-select>
      <div v-if="typeHint" class="fcd-hint">{{ typeHint }}</div>

      <template v-if="hasBody">
        <div class="fcd-sep" />

        <!-- ========== 单选 / 多选 ========== -->
        <template v-if="isSelect">
          <div class="fcd-head">
            <span class="fcd-label">选项</span>
            <span class="fcd-right">
              <el-checkbox :model-value="isRef" @change="toggleRef">引用选项</el-checkbox>
              <el-tooltip :hide-after="0" content="选项集来自其他表的单选/多选字段，源表选项变更后自动同步" placement="top">
                <StIcon name="info" :size="15" class="fcd-tip" /></el-tooltip>
            </span>
          </div>
          <template v-if="!isRef">
            <div class="fcd-optbox">
              <div v-for="(o, i) in form.config.options" :key="o.id" class="fcd-opt-row" :class="dropCls(i)"
                   @dragover.prevent="overIdx = i" @drop.prevent="dropOpt(i)">
                <span class="fcd-del st-icon-action" data-smart-tip="删除选项" @click="form.config.options.splice(i, 1)"><StIcon name="minus-circle" :size="20" /></span>
                <el-popover :hide-after="0" trigger="click" placement="bottom-start" :width="208" popper-class="fcd-color-pop" :show-arrow="false">
                  <template #reference>
                    <span class="fcd-color" :style="{ background: optionColor(o.color).value }" data-smart-tip="选择颜色" />
                  </template>
                  <div class="fcd-palette">
                    <span v-for="c in OPTION_COLORS" :key="c.key" class="fcd-pal" :class="{ on: o.color === c.key }"
                          :style="{ background: c.value }" :data-smart-tip="c.label" @click="o.color = c.key" />
                  </div>
                </el-popover>
                <input v-model="o.label" class="fcd-opt-in" />
                <span class="fcd-drag st-icon-action" draggable="true" data-smart-tip="拖拽调整顺序" @dragstart="dragIdx = i" @dragend="dragIdx = overIdx = -1">
                  <StIcon name="drag" :size="16" /></span>
              </div>
              <div class="fcd-add" @click="addOption"><StIcon name="plus-circle" :size="20" />添加选项</div>
            </div>
            <el-checkbox v-model="form.config.allowAddOptionWhenEditing" class="fcd-ck">允许填写时新增选项</el-checkbox>
          </template>
          <template v-else>
            <div class="fcd-row2">
              <el-select v-model="form.config.reference.tableId" class="fcd-select" placeholder="选择表" filterable popper-class="fcd-pop"
                         @change="form.config.reference.fieldId = null">
                <template #prefix><StIcon name="table" :size="16" class="fcd-pre" /></template>
                <el-option v-for="t in tables" :key="t.id" :value="t.id" :label="t.label" />
              </el-select>
              <el-select v-model="form.config.reference.fieldId" class="fcd-select" placeholder="选择字段" popper-class="fcd-pop">
                <template v-if="refFieldObj" #prefix><StIcon :name="fieldIconName(refFieldObj)" :size="16" class="fcd-pre" /></template>
                <el-option v-for="f in refSelectFields" :key="f.field_name" :value="f.field_name" :label="f.label">
                  <span class="fcd-opt"><StIcon :name="fieldIconName(f)" :size="15" />{{ f.label }}</span>
                </el-option>
              </el-select>
            </div>
            <div class="fcd-inline">
              <el-checkbox :model-value="linkageEnabled" @change="(v) => (form.config.optionLinkage.enabled = v)">启用选项联动</el-checkbox>
              <el-tooltip :hide-after="0" content="按本表当前行的字段值，过滤引用表中可选的选项" placement="top"><StIcon name="info" :size="15" class="fcd-tip" /></el-tooltip>
            </div>
            <div v-if="linkageEnabled" class="fcd-graybox">
              <div class="fcd-gb-head">
                <span>联动条件</span>
                <MatchSwitch v-model="form.config.optionLinkage.match" />
              </div>
              <div v-for="(c, i) in form.config.optionLinkage.conditions" :key="i" class="fcd-cond">
                <FieldSel v-model="c.localFieldId" :fields="fields" placeholder="本表的字段" class="fcd-c1" />
                <el-select v-model="c.operator" class="fcd-select fcd-c2" popper-class="fcd-pop"><el-option value="eq" label="等于" /></el-select>
                <FieldSel v-model="c.remoteFieldId" :fields="refFields" placeholder="引用表的字段" class="fcd-c3" />
                <span class="fcd-del st-icon-action" @click="form.config.optionLinkage.conditions.splice(i, 1)"><StIcon name="minus-circle" :size="20" /></span>
              </div>
              <div class="fcd-add gray" @click="form.config.optionLinkage.conditions.push({ localFieldId: null, operator: 'eq', remoteFieldId: null })">
                <StIcon name="plus" :size="16" />添加条件</div>
            </div>
          </template>
        </template>

        <!-- ========== 数字 / 百分数 / 货币 / 进度 ========== -->
        <template v-if="isNumberFamily">
          <div class="fcd-label">快捷转换</div>
          <div class="fcd-quick">
            <div v-for="q in QUICK" :key="q.ft" class="fcd-qt" :class="{ on: form.field_type === q.ft }" @click="switchNumber(q.ft)">
              <span class="fcd-qt-ico">
                <template v-if="q.text">{{ q.text }}</template>
                <StIcon v-else :name="q.ft" :size="22" />
              </span>
              <span>{{ q.label }}</span>
            </div>
          </div>
          <template v-if="form.field_type === 'currency'">
            <div class="fcd-label">货币符号</div>
            <el-select v-model="form.config.currencyCode" class="fcd-select" popper-class="fcd-pop" @change="(c) => (form.config.currencySymbol = CURRENCIES[c].s)">
              <el-option v-for="(c, code) in CURRENCIES" :key="code" :value="code" :label="`${code} - ${c.s}`">
                <span class="fcd-opt-lr"><span>{{ code }} - {{ c.s }}</span><span class="fcd-sub">{{ c.name }}</span></span>
              </el-option>
              <template #label="{ value }"><span class="fcd-opt-lr"><span>{{ value }} - {{ CURRENCIES[value]?.s }}</span><span class="fcd-sub">{{ CURRENCIES[value]?.name }}</span></span></template>
            </el-select>
          </template>
          <template v-if="form.field_type === 'progress'">
            <div class="fcd-label">进度条颜色</div>
            <div class="fcd-pcolors">
              <el-popover v-for="c in PROGRESS_COLORS" :key="c.key" trigger="hover" placement="right" :width="164" :show-arrow="false" :show-after="180">
                <template #reference>
                  <button type="button" class="fcd-pc" :class="{ on: form.config.color === c.key }" :aria-label="c.label" :aria-pressed="form.config.color === c.key"
                          :style="{ background: c.css }" @click="form.config.color = c.key" />
                </template>
                <div class="fcd-progress-preview">
                  <div v-for="p in [0.1, 0.3, 0.45, 0.6, 0.75, 0.9]" :key="p" class="fcd-preview-track">
                    <span :style="{ width: `${p * 100}%`, background: progressColor(c.key, p) }" />
                  </div>
                  <div class="fcd-preview-name">{{ c.label }}</div>
                </div>
              </el-popover>
            </div>
            <div class="fcd-row2">
              <div class="fcd-col">
                <div class="fcd-label">数字格式</div>
                <el-select v-model="form.config.numberFormat" class="fcd-select" popper-class="fcd-pop">
                  <el-option value="value" label="数值" /><el-option value="percent" label="百分比" />
                </el-select>
              </div>
              <div class="fcd-col">
                <div class="fcd-label">小数位数</div>
                <el-select v-model="form.config.precision" class="fcd-select" popper-class="fcd-pop">
                  <el-option v-for="p in PRECISIONS" :key="String(p.v)" :value="p.v" :label="p.l" />
                </el-select>
              </div>
            </div>
            <div class="fcd-label">进度条范围</div>
            <div class="fcd-range">
              <span class="fcd-range-value">
                <input v-model.number="form.config.range.min" inputmode="decimal" class="fcd-range-in" aria-label="进度最小值"
                       :style="{ width: `${Math.max(1, String(form.config.range.min).length)}ch` }" />
                <span v-if="form.config.numberFormat === 'percent'">%</span>
              </span>
              <span class="fcd-range-dash">—</span>
              <span class="fcd-range-value right">
                <input v-model.number="form.config.range.max" inputmode="decimal" class="fcd-range-in right" aria-label="进度最大值"
                       :style="{ width: `${Math.max(1, String(form.config.range.max).length)}ch` }" />
                <span v-if="form.config.numberFormat === 'percent'">%</span>
              </span>
            </div>
            <el-checkbox v-model="form.config.showNumber" class="fcd-ck">展示数字</el-checkbox>
          </template>
          <template v-else>
            <div class="fcd-label">小数位数</div>
            <el-select v-model="form.config.precision" class="fcd-select" popper-class="fcd-pop">
              <el-option v-for="p in PRECISIONS" :key="String(p.v)" :value="p.v" :label="p.l">
                <span class="fcd-opt-lr"><span>{{ p.l }}</span><span class="fcd-sub">{{ precisionSample(p.v) }}</span></span>
              </el-option>
              <template #label="{ label, value }"><span class="fcd-opt-lr"><span>{{ label }}</span><span class="fcd-sub">{{ precisionSample(value) }}</span></span></template>
            </el-select>
            <el-checkbox v-model="form.config.thousandSeparator" class="fcd-ck">使用千位符</el-checkbox>
          </template>
        </template>

        <!-- ========== 日期 / 创建时间 / 最后编辑时间 ========== -->
        <template v-if="isDateFamily">
          <div class="fcd-label">格式设置</div>
          <el-select v-model="form.config.format" class="fcd-select" popper-class="fcd-pop fcd-date-pop">
            <el-option v-for="d in DATE_FORMATS" :key="d.v" :value="d.v" :label="d.l">
              <span class="fcd-date-check"><StIcon v-if="form.config.format === d.v" name="check" :size="16" /></span>{{ d.l }}
            </el-option>
          </el-select>
          <el-checkbox v-if="form.field_type === 'date'" v-model="form.config.autoFillCreatedTime" class="fcd-ck">默认填充创建时间</el-checkbox>
        </template>

        <!-- ========== 人员 ========== -->
        <template v-if="form.field_type === 'member'">
          <div class="fcd-switch"><span>允许添加多个人员</span><el-switch v-model="form.config.multiple" /></div>
          <div class="fcd-switch"><span>添加人员时通知他</span><el-switch v-model="form.config.notifyOnAdd" /></div>
        </template>

        <!-- ========== 图片 ========== -->
        <el-checkbox v-if="form.field_type === 'image'" v-model="form.config.cameraOnly" class="fcd-ck">仅限手机拍照上传</el-checkbox>

        <!-- ========== 复选框 ========== -->
        <el-checkbox v-if="form.field_type === 'checkbox'" v-model="form.config.defaultChecked" class="fcd-ck">默认勾选</el-checkbox>

        <!-- ========== 链接 ========== -->
        <template v-if="form.field_type === 'url'">
          <div class="fcd-label">格式设置</div>
          <div class="fcd-lrow">
            <span>展示样式</span>
            <el-select v-model="form.config.displayStyle" class="fcd-select fcd-w200" popper-class="fcd-pop">
              <template #prefix><StIcon :name="form.config.displayStyle === 'text' ? 'link' : 'view-grid'" :size="15" class="fcd-pre" /></template>
              <el-option value="text" label="文字"><span class="fcd-opt"><StIcon name="link" :size="15" />文字</span></el-option>
              <el-option value="iconText" label="图标文字"><span class="fcd-opt"><StIcon name="view-grid" :size="15" />图标文字</span></el-option>
            </el-select>
          </div>
        </template>

        <!-- ========== 关联 ========== -->
        <template v-if="form.field_type === 'relation'">
          <div class="fcd-label">关联的智能表</div>
          <el-select v-model="form.config.targetTableId" class="fcd-select" placeholder="选择要关联的智能表" filterable popper-class="fcd-pop">
            <template #prefix><StIcon name="table" :size="16" class="fcd-pre" /></template>
            <el-option v-for="t in tables" :key="t.id" :value="t.id" :label="t.label" />
          </el-select>
          <div class="fcd-cks">
            <el-checkbox v-model="form.config.bidirectional" :disabled="!form.config.targetTableId">在「{{ targetTableName || '关联表' }}」表显示</el-checkbox>
            <el-checkbox v-model="form.config.multiple">允许多选</el-checkbox>
            <el-checkbox :model-value="!!form.config.viewId" :disabled="!form.config.targetTableId" @change="(v) => (form.config.viewId = v ? (targetViews[0]?.id || null) : null)">指定视图</el-checkbox>
            <el-select v-if="form.config.viewId" v-model="form.config.viewId" class="fcd-select" popper-class="fcd-pop">
              <el-option v-for="v in targetViews" :key="v.id" :value="v.id" :label="v.name" />
            </el-select>
          </div>
        </template>

        <!-- ========== 自动编号 ========== -->
        <template v-if="form.field_type === 'autoNumber'">
          <div class="fcd-label">编号类型</div>
          <el-select v-model="form.config.numberType" class="fcd-select" popper-class="fcd-pop">
            <el-option value="autoIncrement" label="自增数字" /><el-option value="custom" label="自定义编号" />
          </el-select>
          <div v-if="form.config.numberType === 'autoIncrement'" class="fcd-hint">从 1 开始连续递增的数字编号，如：1、2、3</div>
          <template v-if="form.config.numberType === 'custom'">
            <div class="fcd-hint">自定义格式和规则的编号</div>
            <div class="fcd-segbox">
              <div class="fcd-seg-preview"><span class="fcd-sub">编号预览</span>{{ segPreview }}</div>
              <div v-for="(s, i) in form.config.segments" :key="i" class="fcd-seg" :class="dropCls(i)"
                   @dragover.prevent="overIdx = i" @drop.prevent="dropSeg(i)">
                <span class="fcd-del st-icon-action" :class="{ hidden: s.type === 'autoIncrement' }" @click="s.type !== 'autoIncrement' && form.config.segments.splice(i, 1)">
                  <StIcon name="minus-circle" :size="20" /></span>
                <span class="fcd-seg-l">{{ SEG_LABELS[s.type] }}</span>
                <div class="fcd-seg-ctl">
                  <div v-if="s.type === 'autoIncrement'" class="fcd-digits">
                    <input v-model.number="s.digits" type="number" min="1" max="8" class="fcd-digits-in" /><span class="fcd-sub">位</span>
                    <span class="fcd-steps"><span @click="s.digits = Math.min(8, (s.digits || 3) + 1)">▲</span><span @click="s.digits = Math.max(1, (s.digits || 3) - 1)">▼</span></span>
                  </div>
                  <input v-else-if="s.type === 'fixedText'" v-model="s.text" class="fcd-input fcd-seg-in" placeholder="请输入" />
                  <el-select v-else v-model="s.format" class="fcd-select" popper-class="fcd-pop">
                    <el-option v-for="(l, k) in DATE_SEG_FORMATS" :key="k" :value="k" :label="l" />
                  </el-select>
                </div>
                <span class="fcd-drag st-icon-action" draggable="true" @dragstart="dragIdx = i" @dragend="dragIdx = overIdx = -1"><StIcon name="drag" :size="16" /></span>
              </div>
              <el-dropdown :hide-after="0" trigger="click" @command="addSeg">
                <div class="fcd-add dark"><StIcon name="plus-circle" :size="20" />添加编号字段</div>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="fixedText">固定字符</el-dropdown-item>
                    <el-dropdown-item command="createDate">创建日期</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
          <div v-if="field" class="fcd-hint">修改编号格式后，已有记录保留原序号，仅更新编号格式。</div>
        </template>

        <!-- ========== 公式 ========== -->
        <template v-if="form.field_type === 'formula'">
          <div class="fcd-label">公式内容</div>
          <div class="fx-entry" :class="{ filled: form.config.formula }" @click="fxEditor = true">
            <template v-if="!form.config.formula"><StIcon name="pencil" :size="17" /><span>编辑公式</span></template>
            <span v-else class="fx-preview">
              <template v-for="(p, i) in fxTokens" :key="i">
                <span v-if="p.t === 'field'" class="fx-chip"><StIcon :name="fieldIconName(p.field)" :size="12" />{{ p.field.label }}</span>
                <span v-else-if="p.t === 'table' || p.t === 'tcol'" class="fx-chip fx-chip-t"><StIcon name="view-grid" :size="12" />{{ p.table.label }}{{ p.t === 'tcol' ? `.${p.field.label}` : '' }}</span>
                <span v-else>{{ p.v }}</span>
              </template>
            </span>
            <span class="fx-caret" />
          </div>
          <div v-if="form.config.formula" class="fcd-hint">结果类型：{{ { number: '数字', date: '日期' }[form.config.returnType] || '文本' }}（按第 1 行试算结果自动识别）</div>
        </template>

        <!-- ========== 查找引用 ========== -->
        <template v-if="form.field_type === 'lookup'">
          <div class="fcd-label">要引用的字段</div>
          <div class="fcd-row2">
            <el-select v-model="form.config.sourceTableId" class="fcd-select" placeholder="选择表" filterable popper-class="fcd-pop"
                       @change="form.config.sourceFieldId = null" @visible-change="open => { if (open) refreshLookupOptions() }">
              <template #prefix><StIcon name="table" :size="16" class="fcd-pre" /></template>
              <el-option v-for="t in lookupTables" :key="t.id" :value="t.id" :label="t.label" />
            </el-select>
            <FieldSel v-model="form.config.sourceFieldId" :fields="srcFields" placeholder="选择字段" />
          </div>
          <div class="fcd-graybox">
            <div class="fcd-gb-head">
              <el-dropdown :hide-after="0" trigger="click" @command="(m) => { lookupMode = m; if (m === 'all') form.config.conditions = [] }">
                <span class="fcd-link-dd gray">{{ lookupMode === 'all' ? '引用全部记录' : '按条件查找' }}<StIcon name="chevron-down" :size="13" /></span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="cond">按条件查找</el-dropdown-item>
                    <el-dropdown-item command="all">引用全部记录</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <MatchSwitch v-if="lookupMode === 'cond'" v-model="lookupMatch" />
            </div>
            <template v-if="lookupMode === 'cond'">
              <div v-for="(c, i) in form.config.conditions" :key="i" class="fcd-cond">
                <FieldSel v-model="c.sourceFieldId" :fields="srcFields" placeholder="引用表的字段" class="fcd-c1" />
                <el-select v-model="c.op" class="fcd-select fcd-c2" popper-class="fcd-pop" :disabled="!c.sourceFieldId">
                  <el-option value="eq" label="等于" /><el-option value="neq" label="不等于" /><el-option value="contains" label="包含" />
                </el-select>
                <input v-if="c.useValue" v-model="c.rightValue" class="fcd-input fcd-c3 fcd-small" placeholder="输入值" />
                <FieldSel v-else v-model="c.rightFieldId" :fields="fields" placeholder="本表的字段" class="fcd-c3" />
                <el-tooltip :hide-after="0" :content="c.useValue ? '改为引用本表字段' : '改为输入固定值'" placement="top">
                  <span class="fcd-swap" :class="{ off: !c.sourceFieldId }" @click="toggleCondValue(c)">A<sub>⇆</sub></span>
                </el-tooltip>
                <span class="fcd-del st-icon-action" @click="form.config.conditions.splice(i, 1)"><StIcon name="minus-circle" :size="20" /></span>
              </div>
              <div class="fcd-add gray" @click="form.config.conditions.push({ sourceFieldId: null, op: 'eq', rightFieldId: null })">
                <StIcon name="plus" :size="16" />添加条件</div>
            </template>
          </div>
          <div class="fcd-label">统计方式</div>
          <el-select v-model="form.config.aggregation" class="fcd-select" popper-class="fcd-pop">
            <el-option v-for="(l, k) in LOOKUP_AGGS" :key="k" :value="k" :label="l" />
          </el-select>
        </template>
      </template>

      <!-- 底部：AI 入口 + 确定/取消 -->
      <div class="fcd-foot" :class="{ sep: !hasBody }">
        <span v-if="aiAction" class="fcd-ai" @click="onAi"><span class="fcd-ai-logo"><StIcon name="sparkle" :size="11" /></span>{{ aiAction }}</span>
        <span class="fcd-flex" />
        <button class="fcd-btn primary" :disabled="!form.label.trim()" @click="save">确定</button>
        <button class="fcd-btn" @click="$emit('close')">取消</button>
      </div>
    </div>

    <FormulaEditor v-if="form.field_type === 'formula'" :visible="fxEditor" :title="form.label || '公式'" :formula="form.config.formula || ''" :fields="fields"
                   :field-name="field?.field_name || null" :table-id="tableId" :sample-record-id="sampleRecordId"
                   @close="fxEditor = false"
                   @save="(r) => { form.config.formula = r.formula; form.config.returnType = r.returnType; fxEditor = false }" />
    <AiFormulaDialog v-if="form.field_type === 'formula'" :visible="aiFormula" :table-id="tableId" :fields="fields" @close="aiFormula = false"
                     @apply="(r) => { form.config.formula = r.formula; form.config.returnType = r.returnType; aiFormula = false }" />
  </el-dialog>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, defineComponent, h, nextTick, reactive, ref, watch } from 'vue'
import { ElDropdown, ElDropdownItem, ElDropdownMenu, ElMessage, ElOption, ElSelect } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import AiFormulaDialog from '../ai/AiFormulaDialog.vue'
import FormulaEditor from '../formula/FormulaEditor.vue'
import { referencedTableIds, tokenize } from '../../../smart/utils/formula.js'
import { FIELD_REGISTRY, OPTION_COLORS, PROGRESS_COLORS, optionColor, progressColor } from '../../../smart/registry/fieldRegistry.js'
import { anchoredDialogAttrs, useButtonAnchoredDialog, useNonModalOutsideClose } from '../../../smart/utils/anchorDialog.js'
import { smartListViews } from '../../../api/index.js'

const props = defineProps({
  visible: Boolean,
  field: Object,          // 编辑态传入现有字段；新增为 null
  preset: { type: Object, default: null },   // 新增预设 {field_type, label}（AddFieldPop 类型网格跳入）
  fields: { type: Array, default: () => [] },   // 本表字段（lookup 条件右值用）
  tables: { type: Array, default: () => [] },   // 可选的关联/引用目标表
  lookupTables: { type: Array, default: () => [] },   // 当前文档内的智能表
  sourceFieldsOf: { type: Function, default: () => () => [] },  // (tableId) => Promise<fields[]>
  tableId: { type: Number, default: null },     // AI 写公式需要表上下文
  sampleRecordId: { type: Number, default: null },   // 公式试算用的当前视图首行
  at: { type: Object, default: null },   // {x,y} 打开位置 → 非模态、在该位置弹出
})
const emit = defineEmits(['close', 'save', 'ai-tags', 'ai-field', 'refresh-lookup-tables'])
const editorBody = ref(null)
const placeEditor = useButtonAnchoredDialog(() => editorBody.value, () => props.at, () => props.visible)
const aiFormula = ref(false)
const fxEditor = ref(false)
// The formula editor is teleported outside this dialog. Its interactions and
// dismissal belong to the child, not to the field configuration underneath it.
useNonModalOutsideClose(() => props.visible && !fxEditor.value && !aiFormula.value, () => emit('close'))
const nameRef = ref(null)

// ---------- 常量（对齐参照） ----------
// 类型下拉：分组顺序同「添加列」类型网格（组间分隔线）
const TYPE_GROUPS = [
  { key: 'basic', types: ['text', 'singleSelect', 'multiSelect', 'number', 'percent', 'currency', 'progress', 'date'] },
  { key: 'collab', types: ['member', 'image', 'file'] },
  { key: 'ident', types: ['relation', 'url', 'checkbox', 'autoNumber'] },
  { key: 'calc', types: ['formula', 'lookup'] },
  { key: 'sys', types: ['createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime'] },
]
const HINTS = {
  member: '你可以在人员列类型@人', relation: '你可以通过关联列获取其他智能表的数据',
  createdBy: '自动展示每行记录的创建人，不可修改', lastModifiedBy: '自动展示每行记录的最后编辑人，不可修改',
  createdTime: '自动展示每行记录的创建时间，不可修改', lastModifiedTime: '自动展示每行记录最后一次编辑的时间，不可修改',
}
const QUICK = [{ ft: 'number', label: '数字', text: '123' }, { ft: 'percent', label: '百分数', text: '%' },
               { ft: 'currency', label: '货币' }, { ft: 'progress', label: '进度' }]
const CURRENCIES = { CNY: { s: '￥', name: '人民币' }, USD: { s: '$', name: '美元' }, EUR: { s: '€', name: '欧元' },
                     JPY: { s: '¥', name: '日元' }, HKD: { s: 'HK$', name: '港币' }, GBP: { s: '£', name: '英镑' } }
const PRECISIONS = [{ v: 'default', l: '默认' }, { v: 0, l: '整数' }, { v: 1, l: '1 位小数' }, { v: 2, l: '2 位小数' },
                    { v: 3, l: '3 位小数' }, { v: 4, l: '4 位小数' }]
import { DATE_FORMATS } from '../../../smart/utils/format.js'
const SEG_LABELS = { autoIncrement: '自增数字', fixedText: '固定字符', createDate: '创建日期' }
const LOOKUP_AGGS = { raw: '原样引用', rawDistinct: '去重引用', sum: '求和', count: '计数', countDistinct: '去重计数', avg: '平均值', max: '最大值', min: '最小值' }
const AI_ACTIONS = { text: '使用 AI 生成', image: '使用 AI 生成', number: '使用 AI 计算', percent: '使用 AI 计算', currency: '使用 AI 计算',
                     progress: '使用 AI 计算', date: '使用 AI 计算', checkbox: '使用 AI 判断', singleSelect: '使用 AI 匹配标签',
                     multiSelect: '使用 AI 匹配标签', formula: '使用 AI 生成公式' }

const today = new Date()
const pad = (x) => String(x).padStart(2, '0')
const DATE_SEG_FORMATS = {
  yyyyMMdd: `${today.getFullYear()}${pad(today.getMonth() + 1)}${pad(today.getDate())}`,
  'yyyy-MM-dd': `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`,
  yyyyMM: `${today.getFullYear()}${pad(today.getMonth() + 1)}`, yyyy: String(today.getFullYear()),
}

// ---------- 小组件：带图标的字段下拉 / 满足全部·任一条件 ----------
const FieldSel = defineComponent({
  props: { modelValue: [String, Number], fields: { type: Array, default: () => [] }, placeholder: String },
  emits: ['update:modelValue'],
  setup(p, { emit: e }) {
    return () => {
      const cur = p.fields.find(f => f.field_name === p.modelValue)
      return h(ElSelect, { modelValue: p.modelValue, placeholder: p.placeholder, filterable: true, class: 'fcd-select', popperClass: 'fcd-pop',
                           'onUpdate:modelValue': (v) => e('update:modelValue', v) }, {
        prefix: cur ? () => h(StIcon, { name: fieldIconName(cur), size: 16, class: 'fcd-pre' }) : undefined,
        default: () => p.fields.map(f => h(ElOption, { key: f.field_name, value: f.field_name, label: f.label }, () =>
          h('span', { class: 'fcd-opt' }, [h(StIcon, { name: fieldIconName(f), size: 15 }), f.label]))),
      })
    }
  },
})
const MatchSwitch = defineComponent({
  props: { modelValue: String },
  emits: ['update:modelValue'],
  setup(p, { emit: e }) {
    return () => h('span', { class: 'fcd-match' }, ['满足以下', h(ElDropdown, { trigger: 'click', onCommand: (v) => e('update:modelValue', v) }, {
      default: () => h('span', { class: 'fcd-link-dd' }, [p.modelValue === 'any' ? '任一条件' : '全部条件', h(StIcon, { name: 'chevron-down', size: 13 })]),
      dropdown: () => h(ElDropdownMenu, null, () => [h(ElDropdownItem, { command: 'all' }, () => '全部条件'), h(ElDropdownItem, { command: 'any' }, () => '任一条件')]),
    })])
  },
})

// ---------- 表单 ----------
const form = reactive({ label: '', field_type: 'text', config: {} })
let lastSelectCfg = null
watch(() => props.visible, async (v) => {
  if (!v) return
  lastSelectCfg = null
  if (props.field) {
    form.label = props.field.label
    form.field_type = props.field.field_type || 'text'
    form.config = JSON.parse(JSON.stringify(props.field.options || {}))
  } else {
    form.label = props.preset?.label || ''
    form.field_type = props.preset?.field_type || 'text'
    form.config = FIELD_REGISTRY[form.field_type].defaultConfig()
    if (!form.label && props.preset?.field_type) form.label = FIELD_REGISTRY[form.field_type].label
  }
  normalizeConfig()
  await nextTick()
  setTimeout(() => { nameRef.value?.focus(); nameRef.value?.select() }, 50)   // 名称默认全选（参照）
})

const isSystemLike = computed(() => ['createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime'].includes(props.field?.field_type))
const isSelect = computed(() => ['singleSelect', 'multiSelect'].includes(form.field_type))
const isNumberFamily = computed(() => ['number', 'percent', 'currency', 'progress'].includes(form.field_type))
const isDateFamily = computed(() => ['date', 'createdTime', 'lastModifiedTime'].includes(form.field_type))
const typeHint = computed(() => HINTS[form.field_type] || '')
const hasBody = computed(() => !['text', 'file', 'createdBy', 'lastModifiedBy'].includes(form.field_type))
// AI 入口：公式/单选多选沿用原能力；其余类型 → 改用 AI 字段生成该列（AI 场景市场）
const aiAction = computed(() => {
  const a = AI_ACTIONS[form.field_type]
  if (!a) return ''
  if (isSelect.value && !props.field) return '使用 AI 生成'
  if (form.field_type === 'formula' && !props.tableId) return ''
  return a
})

function onTypeChange(ft) {
  if (Array.isArray(form.config?.options)) lastSelectCfg = { options: form.config.options, allow: form.config.allowAddOptionWhenEditing }
  form.config = FIELD_REGISTRY[ft].defaultConfig()
  if (['singleSelect', 'multiSelect'].includes(ft) && lastSelectCfg) {
    form.config.options = lastSelectCfg.options
    if (lastSelectCfg.allow !== undefined) form.config.allowAddOptionWhenEditing = lastSelectCfg.allow
  }
  normalizeConfig()
  if (!form.label) form.label = FIELD_REGISTRY[ft].label
}
// 快捷转换：数字族互转，切换后用目标类型的默认设置（如货币默认 2 位小数 + 千位符，同参照）
function switchNumber(ft) {
  if (form.field_type === ft) return
  const oldLabel = FIELD_REGISTRY[form.field_type].label
  form.field_type = ft
  form.config = FIELD_REGISTRY[ft].defaultConfig()
  normalizeConfig()
  if (!form.label || form.label === oldLabel) form.label = FIELD_REGISTRY[ft].label
}
function normalizeConfig() {
  const c = form.config
  if (isSelect.value) {
    if (!c.options) c.options = []
    if (!c.optionSource) c.optionSource = 'manual'
    if (!c.reference) c.reference = { tableId: null, fieldId: null }
    if (!c.optionLinkage) c.optionLinkage = { enabled: false, match: 'all', conditions: [] }
  }
  if (isNumberFamily.value && c.precision === undefined) c.precision = 'default'
  if (form.field_type === 'currency' && !c.currencyCode) c.currencyCode = 'CNY'
  if (form.field_type === 'progress') {
    if (!c.range) c.range = { min: 0, max: 100 }
    if (!c.color) c.color = 'green'
    if (!c.numberFormat) c.numberFormat = 'value'
    if (c.showNumber === undefined) c.showNumber = true
  }
  if (isDateFamily.value && !c.format) c.format = 'yyyy-MM-dd'
  if (form.field_type === 'url' && !c.displayStyle) c.displayStyle = 'iconText'
  if (form.field_type === 'autoNumber') {
    if (!c.numberType) c.numberType = 'autoIncrement'
    if (!c.segments?.length) c.segments = [{ type: 'autoIncrement', digits: 3 }]
  }
  if (form.field_type === 'lookup') {
    if (!c.conditions) c.conditions = []
    c.conditions.forEach(x => { x.useValue = !x.rightFieldId && x.rightValue != null && x.rightValue !== '' })
    lookupMode.value = c.conditions.length || !props.field ? 'cond' : 'all'
  }
}

// ---------- 单选/多选 ----------
const isRef = computed(() => form.config?.optionSource === 'reference')
const linkageEnabled = computed(() => !!form.config?.optionLinkage?.enabled)
function toggleRef(v) { form.config.optionSource = v ? 'reference' : 'manual' }
const refFields = ref([])
const refSelectFields = computed(() => refFields.value.filter(f => ['singleSelect', 'multiSelect'].includes(f.field_type)))
const refFieldObj = computed(() => refFields.value.find(f => f.field_name === form.config?.reference?.fieldId))
watch(() => form.config?.reference?.tableId, async (tid) => { refFields.value = tid ? await props.sourceFieldsOf(tid) : [] })
let optSeq = 1
function addOption() {
  const opts = form.config.options
  opts.push({ id: `opt_${Date.now()}_${optSeq++}`, label: `选项${opts.length + 1}`, color: OPTION_COLORS[opts.length % OPTION_COLORS.length].key, order: opts.length })
}
// 拖拽排序（选项 / 编号段共用）
const dragIdx = ref(-1)
const overIdx = ref(-1)
const dropCls = (i) => (dragIdx.value < 0 || overIdx.value !== i || dragIdx.value === i ? '' : dragIdx.value > i ? 'drop-before' : 'drop-after')
function moveIn(arr, i) {
  const from = dragIdx.value
  dragIdx.value = overIdx.value = -1
  if (from < 0 || from === i) return
  arr.splice(i, 0, arr.splice(from, 1)[0])
}
function dropOpt(i) { moveIn(form.config.options, i); form.config.options.forEach((o, k) => { o.order = k }) }
function dropSeg(i) { moveIn(form.config.segments, i) }

// ---------- 数字族 ----------
function precisionSample(p) {
  const n = p === 'default' || p == null ? '1' : (1).toFixed(p)
  if (form.field_type === 'currency') return `${CURRENCIES[form.config.currencyCode]?.s || '￥'}${p === 'default' || p == null ? '1' : n}`
  if (form.field_type === 'percent') return `${n}%`
  return n
}

// ---------- 关联 ----------
const targetTableName = computed(() => (props.tables || []).find(t => t.id === form.config?.targetTableId)?.label || '')
const targetViews = ref([])
watch(() => form.field_type === 'relation' && form.config?.targetTableId, async (tid) => {
  targetViews.value = []
  if (!tid) return
  try { targetViews.value = ((await smartListViews(tid)).views || []).filter(v => v.type === 'grid') } catch { /* 无权访问 */ }
})

// ---------- 自动编号 ----------
const segPreview = computed(() => (form.config.segments || []).map(s => {
  if (s.type === 'autoIncrement') return '0'.repeat(Math.max(0, (s.digits || 3) - 1)) + '1'
  if (s.type === 'fixedText') return s.text || ''
  return DATE_SEG_FORMATS[s.format || 'yyyyMMdd'] || ''
}).join(''))
function addSeg(type) {
  form.config.segments.push(type === 'createDate' ? { type, format: 'yyyyMMdd' } : { type, text: '' })
}

// ---------- 公式 ----------
const refTableFields = ref({})
watch(() => form.config.formula, async (src) => {
  for (const tid of referencedTableIds(src || '')) {
    if (tid === props.tableId || refTableFields.value[tid]) continue
    try { refTableFields.value = { ...refTableFields.value, [tid]: await props.sourceFieldsOf(tid) } } catch { /* 无权访问 */ }
  }
}, { immediate: true })
const fxTokens = computed(() => tokenize(form.config.formula || '', props.fields,
  new Map((props.tables || []).map(t => [t.id, { id: t.id, label: t.label,
    fields: t.id === props.tableId ? props.fields : (refTableFields.value[t.id] || []) }]))))

// ---------- 查找引用 ----------
const srcFields = ref([])
let sourceFieldsRequest = 0
async function refreshSourceFields() {
  const request = ++sourceFieldsRequest
  const tid = form.config?.sourceTableId
  srcFields.value = []
  try {
    const fields = tid ? await props.sourceFieldsOf(tid) : []
    if (request === sourceFieldsRequest) srcFields.value = fields
  } catch (error) {
    if (request === sourceFieldsRequest) ElMessage.error(error.message || '引用字段加载失败')
  }
}
function refreshLookupOptions() {
  emit('refresh-lookup-tables')
  refreshSourceFields()
}
watch(() => form.config?.sourceTableId, refreshSourceFields)
watch(() => [props.visible, form.field_type], ([visible, type]) => {
  if (visible && type === 'lookup') refreshLookupOptions()
}, { flush: 'post' })
const lookupMode = ref('cond')
const lookupMatch = computed({ get: () => (form.config.conditionLogic === 'or' ? 'any' : 'all'), set: (v) => { form.config.conditionLogic = v === 'any' ? 'or' : 'and' } })
function toggleCondValue(c) {
  if (!c.sourceFieldId) return
  c.useValue = !c.useValue
  if (c.useValue) c.rightFieldId = null
  else c.rightValue = ''
}

// ---------- AI ----------
function onAi() {
  if (form.field_type === 'formula') { aiFormula.value = true; return }
  if (isSelect.value && props.field) { emit('ai-tags', props.field); return }
  emit('ai-field', { label: form.label.trim(), field: props.field || null, fieldType: form.field_type })
}

// ---------- 保存 ----------
function save() {
  if (!form.label.trim()) return
  const config = JSON.parse(JSON.stringify(form.config))
  if (isSelect.value) {
    if (config.optionSource === 'reference') {
      if (!config.reference?.tableId || !config.reference?.fieldId) { ElMessage.warning('引用选项需要选择引用的表和字段'); return }
      delete config.allowAddOptionWhenEditing
      if (!config.optionLinkage?.enabled) delete config.optionLinkage
      else config.optionLinkage = { enabled: true, match: config.optionLinkage.match === 'any' ? 'any' : 'all',
                                    conditions: (config.optionLinkage.conditions || []).filter(c => c.localFieldId && c.remoteFieldId) }
    } else {
      config.optionSource = 'manual'
      delete config.reference
      delete config.optionLinkage
      config.options = (config.options || []).filter(o => String(o.label || '').trim()).map((o, i) => ({ ...o, label: o.label.trim(), order: i }))
    }
  }
  if (form.field_type === 'currency') config.currencySymbol = CURRENCIES[config.currencyCode]?.s || '￥'
  if (isDateFamily.value) config.includeTime = /HH/.test(config.format || '')
  if (form.field_type === 'progress' && !(Number(config.range?.max) > Number(config.range?.min))) { ElMessage.warning('进度条最大值必须大于最小值'); return }
  if (form.field_type === 'lookup') {
    if (!config.sourceTableId || !config.sourceFieldId) { ElMessage.warning('请选择要引用的表和字段'); return }
    config.conditions = (config.conditions || []).filter(c => c.sourceFieldId && (c.rightFieldId || (c.useValue && c.rightValue !== '')))
      .map(({ useValue, ...c }) => (useValue ? { ...c, rightFieldId: null } : { ...c, rightValue: undefined }))
  }
  if (form.field_type === 'relation' && !config.targetTableId) { ElMessage.warning('请选择关联的智能表'); return }
  emit('save', { label: form.label.trim(), field_type: form.field_type, config })
}
</script>

<style scoped>
.fcd { display: flex; flex-direction: column; --el-color-primary: var(--st-primary); }
.fcd-input { box-sizing: border-box; height: 36px; border: 1px solid #DEE0E3; border-radius: 6px; padding: 0 12px; font-size: 14px;
             color: var(--st-text-1); outline: none; background: #fff; }
.fcd-input:hover { border-color: #C9CDD4; }
.fcd-input:focus { border-color: var(--st-primary); }
.fcd-name { width: 100%; margin-bottom: 12px; }
.fcd-select { width: 100%; }
.fcd-select :deep(.el-select__wrapper) { min-height: 36px; border-radius: 6px; font-size: 14px; box-shadow: 0 0 0 1px #DEE0E3 inset; padding: 0 12px; }
.fcd-select :deep(.el-select__wrapper:hover) { box-shadow: 0 0 0 1px #C9CDD4 inset; }
.fcd-select :deep(.el-select__wrapper.is-focused) { box-shadow: 0 0 0 1px var(--st-primary) inset; }
.fcd-pre { color: var(--st-text-1); margin-right: 4px; }
.fcd-opt { display: inline-flex; align-items: center; gap: 10px; }
.fcd-opt .st-icon { color: var(--st-text-1); }
.fcd-opt-lr { display: flex; justify-content: space-between; width: 100%; gap: 16px; }
.fcd-select :deep(.el-select__selected-item) { width: 100%; }   /* 让选中值的右侧说明（人民币 / ¥1.00）靠右 */
.fcd-sub { color: var(--st-text-3); font-size: 14px; margin-right: 6px; }
.fcd-hint { font-size: 14px; color: var(--st-text-3); margin-top: 10px; }
.fcd-sep { height: 1px; background: #EBECEE; margin: 16px -24px 16px; }
/* 分区小标题：上方 16px 与上一分区隔开；紧跟分隔线的第一个分区不加 */
.fcd-label { font-size: 15px; color: var(--st-text-3); margin: 16px 0 8px; }
.fcd-sep + .fcd-label, .fcd-sep + .fcd-head { margin-top: 0; }
.fcd-row2 + .fcd-label { margin-top: 16px; }
.fcd-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.fcd-head .fcd-label { margin: 0; }
.fcd-right, .fcd-inline { display: inline-flex; align-items: center; gap: 6px; }
.fcd-inline { margin: 12px 0 8px; }
.fcd-tip { color: var(--st-text-3); cursor: help; }
.fcd :deep(.el-checkbox__label) { font-size: 16px; color: var(--st-text-1); padding-left: 10px; }
.fcd :deep(.el-checkbox__inner) { width: 18px; height: 18px; border-radius: 4px; }
.fcd :deep(.el-checkbox__inner::after) { width: 4px; height: 8px; border-width: 0 2px 2px 0; }
.fcd-ck { margin-top: 12px; height: auto; }
/* 选项列表框 */
.fcd-optbox { border: 1px solid #DEE0E3; border-radius: 8px; padding: 8px 12px 6px; }
.fcd-opt-row { display: flex; align-items: center; gap: 14px; height: 44px; margin: 0 -8px; padding: 0 8px; border-radius: 6px;
               border-top: 2px solid transparent; border-bottom: 2px solid transparent; }
.fcd-opt-row:hover { background: #F2F3F5; }
.fcd-opt-row.drop-before { border-top-color: var(--st-primary); }
.fcd-opt-row.drop-after { border-bottom-color: var(--st-primary); }
.fcd-del { display: inline-flex; color: #C9CDD4; cursor: pointer; flex: none; }
.fcd-del:hover { color: var(--el-color-danger); }
.fcd-del.hidden { visibility: hidden; }
.fcd-color { width: 22px; height: 22px; border-radius: 4px; cursor: pointer; flex: none; }
.fcd-opt-in { flex: 1; min-width: 0; height: 36px; border: 1px solid transparent; border-radius: 6px; padding: 0 10px; margin-left: -10px;
              font-size: 14px; color: var(--st-text-1); background: transparent; outline: none; }
.fcd-opt-in:focus { border-color: var(--st-primary); background: #fff; }
.fcd-drag { display: inline-flex; color: var(--st-text-3); cursor: grab; flex: none; }
.fcd-add { display: inline-flex; align-items: center; gap: 12px; height: 44px; color: var(--st-primary); font-size: 16px; cursor: pointer; }
.fcd-add.gray { color: var(--st-text-2); gap: 6px; height: 36px; }
.fcd-add.gray:hover { color: var(--st-text-1); }
.fcd-add.dark { color: var(--st-text-1); }
.fcd-palette { display: grid; grid-template-columns: repeat(6, 24px); gap: 8px; }
.fcd-pal { width: 24px; height: 24px; border-radius: 4px; cursor: pointer; box-sizing: border-box; }
.fcd-pal.on { box-shadow: 0 0 0 2px #fff inset, 0 0 0 2px var(--st-primary); }
/* 两列 / 灰底条件框 */
.fcd-row2 { display: flex; gap: 8px; }
.fcd-row2 > * { flex: 1; min-width: 0; }
.fcd-col { display: flex; flex-direction: column; }
.fcd-graybox { background: #F5F6F7; border-radius: 8px; padding: 14px 18px 8px; margin-top: 12px; }
.fcd-gb-head { display: flex; align-items: center; justify-content: space-between; font-size: 15px; color: var(--st-text-2); margin-bottom: 12px; }
.fcd-cond { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.fcd-cond :deep(.el-select__wrapper) { background: #fff; }
.fcd-c1, .fcd-c3 { flex: 1; min-width: 0; }
.fcd-c2 { width: 92px; flex: none; }
.fcd-small { height: 36px; font-size: 14px; }
.fcd :deep(.fcd-match) { display: inline-flex; align-items: center; gap: 2px; color: var(--st-text-2); }
.fcd :deep(.fcd-link-dd) { display: inline-flex; align-items: center; gap: 2px; color: var(--st-primary); cursor: pointer; font-size: 15px; }
.fcd :deep(.fcd-link-dd.gray) { color: var(--st-text-2); }
.fcd-swap { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 36px; border: 1px solid #DEE0E3; border-radius: 6px;
            background: #fff; font-size: 14px; color: var(--st-text-1); cursor: pointer; flex: none; }
.fcd-swap sub { font-size: 11px; }
.fcd-swap.off { opacity: .4; cursor: not-allowed; }
/* 数字族：快捷转换 */
.fcd-quick { display: grid; grid-template-columns: repeat(4, 1fr); background: #F2F3F5; border-radius: 8px; padding: 0; overflow: hidden; }
.fcd-qt { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; height: 64px; box-sizing: border-box; cursor: pointer;
          font-size: 15px; color: var(--st-text-1); border: 1px solid transparent; border-radius: 8px; }
.fcd-qt:hover { background: #E8E9EB; }
.fcd-qt.on { background: #fff; border-color: #DEE0E3; }
.fcd-qt-ico { height: 28px; display: inline-flex; align-items: center; font-size: 22px; font-weight: 300; }
.fcd-pcolors { display: grid; grid-template-columns: repeat(9, 20px); justify-content: space-between; row-gap: 12px; }
.fcd-pc { width: 20px; height: 20px; padding: 0; border: none; border-radius: 2px; cursor: pointer; box-sizing: border-box; }
.fcd-pc.on { outline: 1px solid var(--st-primary); outline-offset: 2px; }
.fcd-progress-preview { display: flex; flex-direction: column; gap: 4px; }
.fcd-preview-track { height: 10px; background: #f1f2f3; border-radius: 2px; overflow: hidden; }
.fcd-preview-track span { display: block; height: 100%; border-radius: 2px; }
.fcd-preview-name { text-align: center; margin-top: 8px; font-size: 13px; color: var(--st-text-1); }
.fcd-range { display: flex; align-items: center; height: 36px; border: 1px solid #DEE0E3; border-radius: 6px; padding: 0 12px; }
.fcd-range-in { flex: 1; min-width: 0; border: none; outline: none; font-size: 14px; color: var(--st-text-1); background: transparent; }
.fcd-range-in.right { text-align: right; }
.fcd-range-value { display: flex; align-items: center; flex: 1; min-width: 0; }
.fcd-range-value.right { justify-content: flex-end; }
.fcd-range-value .fcd-range-in { flex: none; padding: 0; max-width: calc(100% - 16px); }
.fcd-range-dash { color: #DEE0E3; padding: 0 12px; }
/* 人员：开关行 */
.fcd-switch { display: flex; align-items: center; justify-content: space-between; font-size: 16px; color: var(--st-text-1); height: 40px; }
.fcd-switch + .fcd-switch { margin-top: 16px; }
.fcd-lrow { display: flex; align-items: center; justify-content: space-between; font-size: 16px; color: var(--st-text-1); }
.fcd-w200 { width: 224px; }
.fcd-cks { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; margin-top: 18px; }
.fcd-cks :deep(.el-checkbox) { height: 32px; }
/* 自动编号 */
.fcd-segbox { border: 1px solid #DEE0E3; border-radius: 8px; overflow: hidden; margin-top: 14px; padding-bottom: 6px; }
.fcd-seg-preview { background: #F2F3F5; height: 54px; display: flex; align-items: center; gap: 12px; padding: 0 18px; font-size: 16px; color: var(--st-text-1); margin-bottom: 8px; }
.fcd-seg { display: flex; align-items: center; gap: 14px; padding: 4px 18px; border-top: 2px solid transparent; border-bottom: 2px solid transparent; }
.fcd-seg.drop-before { border-top-color: var(--st-primary); }
.fcd-seg.drop-after { border-bottom-color: var(--st-primary); }
.fcd-seg-l { width: 96px; flex: none; font-size: 15px; color: var(--st-text-1); }
.fcd-seg-ctl { flex: 1; min-width: 0; }
.fcd-seg-in { width: 100%; height: 36px; font-size: 14px; }
.fcd-seg-ctl :deep(.el-select__wrapper) { min-height: 36px; }
.fcd-digits { display: flex; align-items: center; height: 36px; border: 1px solid #DEE0E3; border-radius: 6px; overflow: hidden; padding-left: 12px; }
.fcd-digits-in { flex: 1; min-width: 0; border: none; outline: none; font-size: 14px; background: transparent; -moz-appearance: textfield; }
.fcd-digits-in::-webkit-inner-spin-button { display: none; }
.fcd-steps { display: flex; flex-direction: column; width: 46px; height: 100%; background: #F2F3F5; font-size: 9px; color: var(--st-text-2); }
.fcd-steps span { flex: 1; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.fcd-steps span:hover { background: #E3E5E8; }
.fcd-segbox :deep(.el-dropdown) { padding: 0 18px; }
/* 公式入口 */
.fx-entry { display: flex; align-items: center; gap: 12px; min-height: 54px; padding: 8px 18px; background: #F5F6F7; border-radius: 6px; cursor: pointer;
            font-size: 16px; color: var(--st-text-1); }
.fx-entry:hover { background: #EDEEF0; }
.fx-preview { flex: 1; min-width: 0; font-family: Menlo, Consolas, monospace; font-size: 13px; line-height: 26px; word-break: break-all;
              display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.fx-chip { display: inline-flex; align-items: center; gap: 3px; border: 1px solid #3D7BF2; background: #EAF1FE; border-radius: 11px;
           padding: 0 7px; line-height: 20px; font-family: var(--el-font-family); margin: 0 1px; }
.fx-chip-t { border-color: #2BB3A3; background: #E3F7F3; }
.fx-caret { margin-left: auto; width: 0; height: 0; border-top: 4px solid transparent; border-bottom: 4px solid transparent; border-left: 5px solid #C9CDD4; }
/* 底部 */
.fcd-foot { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.fcd-foot.sep { border-top: 1px solid #EBECEE; margin: 16px -24px 0; padding: 16px 24px 0; }
.fcd-flex { flex: 1; }
.fcd-ai { display: inline-flex; align-items: center; gap: 6px; font-size: 14px; color: var(--st-text-3); cursor: pointer; }
.fcd-ai:hover { color: var(--st-text-1); }
.fcd-ai-logo { width: 18px; height: 18px; border-radius: 5px; background: linear-gradient(135deg, #8B6CF6, #E96BD8); color: #fff; display: inline-flex; align-items: center; justify-content: center; }
.fcd-btn { height: 32px; padding: 0 16px; border-radius: 6px; border: none; background: #F2F3F5; font-size: 14px; color: var(--st-text-1); cursor: pointer; }
.fcd-btn:hover { background: #E6E8EA; }
.fcd-btn.primary { background: var(--st-primary); color: #fff; }
.fcd-btn.primary:hover { background: #255BD0; }
.fcd-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>

<style>
/* 面板外壳（el-dialog 去标题栏）：白底圆角 + 阴影，内容区 24px 留白 */
.el-dialog.st-fcd { padding: 0; border-radius: 8px; box-shadow: 0 8px 32px rgba(0, 0, 0, .14); }
.el-dialog.st-fcd .el-dialog__header { display: none; }
.el-dialog.st-fcd .el-dialog__body { padding: 24px; }
.el-dialog.st-fcd-number .el-dialog__body { padding: 16px; }
.el-dialog.st-fcd-number .fcd-qt { height: 56px; }
.el-dialog.st-fcd-number .fcd-sep { margin-left: -16px; margin-right: -16px; }
.el-dialog.st-fcd-number .fcd-foot.sep { margin-left: -16px; margin-right: -16px; padding-left: 16px; padding-right: 16px; }
/* 下拉：选项 16px、带图标；类型下拉分组之间用分隔线 */
.fcd-pop .el-select-dropdown__item { font-size: 15px; height: 40px; line-height: 40px; }
.fcd-date-pop .el-select-dropdown__wrap { max-height: min(380px, calc(100vh - 32px)); }
.fcd-date-pop .el-select-dropdown__item { display: flex; align-items: center; font-weight: normal; color: var(--st-text-1); }
.fcd-date-check { display: inline-flex; width: 26px; flex-shrink: 0; color: var(--el-color-primary); }
.fcd-pop .el-select-group__wrap:not(:last-of-type)::after { left: 12px; right: 12px; background: #EBECEE; }
.fcd-pop .el-select-group__title { display: none; }
.fcd-color-pop.el-popover { padding: 12px; }
</style>
