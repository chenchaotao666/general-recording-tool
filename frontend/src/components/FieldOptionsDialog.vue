<template>
  <el-dialog
    :model-value="modelValue" :title="`字段配置：${field.label || field.field_name || '（未命名）'}`"
    width="640px" append-to-body destroy-on-close @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form label-width="110px">
      <el-form-item v-if="field.data_type !== 'subform'" label="控件类型">
        <el-select v-model="local.widget" style="width: 240px">
          <el-option v-for="w in widgetChoices" :key="w.value" :label="w.label" :value="w.value" />
        </el-select>
      </el-form-item>

      <!-- 自动编号配置 -->
      <template v-if="field.data_type === 'serial'">
        <el-form-item label="编号规则">
          <div style="width: 100%">
            <el-input v-model="serialCfg.pattern" placeholder="如：PO{YYYY}{MM}{DD}-{0000}" clearable />
            <div class="hint">
              占位符：{YYYY} {YY} {MM} {DD} 日期；{0000} 或 {SEQ} 为流水号（0 的个数=位数）。留空默认 {YYYY}{MM}{DD}{0000}
            </div>
          </div>
        </el-form-item>
        <el-form-item label="流水重置">
          <el-select v-model="serialCfg.reset" style="width: 240px">
            <el-option label="连续（永不重置）" value="never" />
            <el-option label="每日从 1 开始" value="daily" />
            <el-option label="每月从 1 开始" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item label="允许手改">
          <el-checkbox v-model="serialCfg.allow_manual" />
          <span class="hint" style="margin-left: 8px">勾选后开单时可手工填写编号；不勾选则始终由系统生成</span>
        </el-form-item>
      </template>

      <!-- 公式：任意非子表/图片字段可配 -->
      <el-form-item v-if="!['subform', 'image'].includes(field.data_type)" label="计算公式">
        <div style="width: 100%">
          <el-input
            v-model="local.options.formula" placeholder="如：qty * price；留空则手工录入"
            clearable
          />
          <div class="hint">
            可用字段：{{ siblingFields.map((s) => s.field_name).filter(Boolean).join('、') || '（先命名字段）' }}；
            支持 + - * /、括号、iff/coalesce/round/abs/min/max，字段名特殊时用 [字段名] 引用
          </div>
        </div>
      </el-form-item>

      <!-- 关联字段配置：选项加载完成前不渲染，避免 el-select 显示原始 id/字段名 -->
      <template v-if="local.widget === 'relation-picker'">
        <div v-if="!relReady" style="padding: 8px 0; color: #909399; font-size: 13px">
          正在加载关联配置…
        </div>
        <template v-else>
        <el-form-item label="目标表">
          <el-select
            v-model="rel.table_id" style="width: 240px" placeholder="选择关联的数据表"
            @change="onTargetTable"
          >
            <el-option v-for="t in tables" :key="t.id" :label="t.label" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="值字段">
          <el-select v-model="rel.value_field" style="width: 240px" placeholder="存入本字段的值（如编号）">
            <el-option v-for="f in targetFields" :key="f.field_name" :label="`${f.label}（${f.field_name}）`" :value="f.field_name" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示字段">
          <el-select v-model="rel.label_field" style="width: 240px" placeholder="下拉中显示（如名称）">
            <el-option v-for="f in targetFields" :key="f.field_name" :label="`${f.label}（${f.field_name}）`" :value="f.field_name" />
          </el-select>
        </el-form-item>
        <el-form-item label="带出映射">
          <div style="width: 100%">
            <div v-for="(m, i) in rel.carry_fields" :key="i" class="carry-row">
              <el-select v-model="m.from" placeholder="源字段（目标表）" style="width: 220px">
                <el-option v-for="f in targetFields" :key="f.field_name" :label="f.label" :value="f.field_name" />
              </el-select>
              <span>→</span>
              <el-select v-model="m.to" placeholder="回填到（本表）" style="width: 220px">
                <el-option v-for="s in siblingFields" :key="s.field_name" :label="s.label || s.field_name" :value="s.field_name" />
              </el-select>
              <el-button text type="danger" size="small" @click="rel.carry_fields.splice(i, 1)">删</el-button>
            </div>
            <el-button text type="primary" size="small" @click="rel.carry_fields.push({ from: '', to: '' })">
              + 添加带出（如：选供应商带出地址/电话）
            </el-button>
          </div>
        </el-form-item>
        </template>
      </template>

      <!-- 子表列定义 -->
      <template v-if="field.data_type === 'subform'">
        <el-divider content-position="left">明细列（{{ local.options.columns.length }}）</el-divider>
        <div class="col-head col-row">
          <span class="c-label">显示名</span><span class="c-name">列名（英文）</span>
          <span class="c-type">类型</span><span class="c-null">可空</span><span class="c-op" />
        </div>
        <div v-for="(c, i) in local.options.columns" :key="i" class="col-row">
          <el-input v-model="c.label" placeholder="如：金额" class="c-label" />
          <el-input v-model="c.field_name" placeholder="如：amount" class="c-name" />
          <el-select v-model="c.data_type" class="c-type">
            <el-option v-for="t in COLUMN_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <el-checkbox v-model="c.nullable" class="c-null" />
          <span class="c-op">
            <el-button text type="primary" size="small" @click="openColumn(c)">配置</el-button>
            <el-button text type="danger" size="small" @click="local.options.columns.splice(i, 1)">删</el-button>
          </span>
        </div>
        <el-button text type="primary" size="small" @click="addColumn">+ 添加明细列</el-button>
        <div class="hint">列的「配置」里可设：关联选择（选产品带出规格/单价）、行内公式（金额=数量×单价）、合计回填（sum_to）</div>
      </template>

      <el-form-item v-if="depth === 0" label="列表中显示" style="margin-top: 12px">
        <el-checkbox v-model="showInList" :disabled="field.data_type === 'subform'" />
        <span v-if="field.data_type === 'subform'" class="hint" style="margin-left: 8px">明细字段不进列表</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="onSave">确定</el-button>
    </template>

    <!-- 子表列的嵌套配置（深度 1，不再允许子表） -->
    <FieldOptionsDialog
      v-if="columnDialogVisible" v-model="columnDialogVisible"
      :field="editingColumn" :sibling-fields="local.options.columns" :depth="1"
      @save="onColumnSave"
    />
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { getTable, listTables } from '../api'

// 字段业务配置：控件类型 / 关联（carry_fields 带出）/ 公式 / 子表列定义 / 列表显隐
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  field: { type: Object, required: true },        // 正在配置的字段行（struct row 或子表列）
  siblingFields: { type: Array, default: () => [] }, // 同层字段（带出目标/公式引用提示）
  depth: { type: Number, default: 0 },            // 0=表字段，1=子表列（禁止再嵌套子表）
})
const emit = defineEmits(['update:modelValue', 'save'])

const COLUMN_TYPES = ['varchar', 'text', 'int', 'decimal', 'date', 'datetime', 'bool', 'image']

const local = reactive({ widget: 'input', options: { columns: [] } })
const rel = reactive({ table_id: null, value_field: '', label_field: '', carry_fields: [] })
const serialCfg = reactive({ pattern: '', reset: 'never', allow_manual: false })
const showInList = ref(true)
const relReady = ref(false)   // 关联选项（表列表 + 目标表字段）是否已加载完
// 注意：immediate watcher 在 setup 同步执行，这两个 ref 必须先于 watcher 声明（否则 TDZ 报错）
const tables = ref([])
const targetFields = ref([])

const widgetChoices = computed(() => {
  const t = props.field.data_type
  const base = {
    varchar: ['input', 'textarea', 'select', 'relation-picker'],
    text: ['textarea', 'input'],
    int: ['number', 'select', 'relation-picker', 'input'],
    decimal: ['number', 'input'],
    date: ['date-picker'], datetime: ['datetime-picker'],
    bool: ['switch'], image: ['image-uploader'], serial: ['serial'],
  }[t] || ['input']
  const LABELS = {
    input: '单行输入', textarea: '多行文本', number: '数字', select: '下拉选择',
    'date-picker': '日期', 'datetime-picker': '日期时间', switch: '开关',
    'image-uploader': '图片上传', 'relation-picker': '关联选择（带出其他字段）',
    serial: '自动编号（保存时生成）',
  }
  return base.map((w) => ({ value: w, label: LABELS[w] || w }))
})

watch(() => props.modelValue, async (v) => {
  if (!v) return
  relReady.value = false
  local.widget = props.field.widget || 'input'
  local.options = JSON.parse(JSON.stringify(props.field.options || {}))
  if (props.field.data_type === 'subform' && !Array.isArray(local.options.columns)) local.options.columns = []
  const r = local.options.relation || {}
  Object.assign(rel, { table_id: null, value_field: '', label_field: '', carry_fields: [] },
    JSON.parse(JSON.stringify(r)))
  if (rel.table_id !== null && rel.table_id !== '') rel.table_id = Number(rel.table_id)   // 与选项的数值 id 严格匹配
  Object.assign(serialCfg, { pattern: '', reset: 'never', allow_manual: false },
    JSON.parse(JSON.stringify(local.options.serial || {})))
  showInList.value = local.options.show_in_list !== false
  // 关联配置还原：按顺序等待目标表/字段列表加载完再渲染下拉，避免显示原始 id
  if (local.widget === 'relation-picker') {
    await loadTables()
    if (rel.table_id) {
      await loadTargetFields(rel.table_id)
      ensureTableOption(rel.table_id)
    }
  }
  relReady.value = true
}, { immediate: true })   // 对话框以 v-if 创建，创建时 modelValue 已为 true，必须立即初始化

watch(() => local.widget, async (w, prev) => {
  if (w !== 'relation-picker' || w === prev) return
  relReady.value = false
  await loadTables()
  if (rel.table_id) {
    await loadTargetFields(rel.table_id)
    ensureTableOption(rel.table_id)
  }
  relReady.value = true
})

// ---------- 关联配置 ----------

async function loadTables() {
  if (tables.value.length) return
  try {
    // all=1：admin 配置他人单据的关联时可看到全部表（非 admin 由后端忽略该参数）
    tables.value = await listTables({ all: 1 })
  } catch (e) {
    console.warn('加载数据表列表失败', e)
    tables.value = []
  }
}

async function loadTargetFields(tid) {
  try {
    targetFields.value = (await getTable(tid)).fields || []
  } catch (e) {
    console.warn('加载目标表字段失败', e)
    targetFields.value = []
  }
}

// 目标表不在可选列表里（如无查看权限/已被删）时，补一个临时选项让已配置值能显示名称
function ensureTableOption(tid) {
  if (tables.value.some((t) => t.id === tid)) return
  getTable(tid)
    .then((t) => { if (!tables.value.some((x) => x.id === tid)) tables.value.push({ id: tid, label: t.label }) })
    .catch(() => tables.value.push({ id: tid, label: `表 #${tid}（无权限或已删除）` }))
}

function onTargetTable(tid) {
  rel.value_field = ''
  rel.label_field = ''
  rel.carry_fields = []
  loadTargetFields(tid)
}

// ---------- 子表列 ----------
const columnDialogVisible = ref(false)
const editingColumn = ref(null)

function addColumn() {
  local.options.columns.push({ field_name: '', label: '', data_type: 'varchar', nullable: true, widget: 'input', options: {} })
}

function openColumn(c) {
  editingColumn.value = c
  columnDialogVisible.value = true
}

function onColumnSave({ widget, options }) {
  editingColumn.value.widget = widget
  editingColumn.value.options = options
  columnDialogVisible.value = false
}

function onSave() {
  const options = JSON.parse(JSON.stringify(local.options))
  if (local.widget === 'relation-picker') {
    options.relation = {
      table_id: rel.table_id, value_field: rel.value_field, label_field: rel.label_field,
      carry_fields: rel.carry_fields.filter((m) => m.from && m.to),
    }
  } else {
    delete options.relation
  }
  if (props.field.data_type === 'serial') {
    options.serial = {
      ...(serialCfg.pattern?.trim() ? { pattern: serialCfg.pattern.trim() } : {}),
      reset: serialCfg.reset || 'never',
      allow_manual: !!serialCfg.allow_manual,
    }
  } else {
    delete options.serial
  }
  options.show_in_list = props.field.data_type === 'subform' ? false : showInList.value
  if (!options.formula) delete options.formula
  if (props.field.data_type === 'subform' && !options.columns.length) delete options.columns
  emit('save', { widget: props.field.data_type === 'subform' ? 'subform' : local.widget, options })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.hint { font-size: 12px; color: #909399; margin-top: 4px; line-height: 1.5; }
.carry-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.col-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.col-head { font-size: 12px; color: #909399; }
.c-label { width: 120px; }
.c-name { width: 130px; }
.c-type { width: 100px; }
.c-null { width: 40px; }
.c-op { display: flex; }
</style>
