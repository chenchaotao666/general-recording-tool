<template>
  <div>
    <div class="page-header"><h2>导入 Excel 建表</h2></div>
    <el-steps :active="step" align-center finish-status="success" style="margin-bottom: 24px">
      <el-step title="上传 Excel" />
      <el-step title="AI 结构分析" />
      <el-step title="确认结构" />
      <el-step title="导入结果" />
    </el-steps>

    <!-- 第 1 步：上传 -->
    <el-card v-if="step === 0">
      <el-upload
        drag :limit="1" accept=".xlsx,.csv" :file-list="fileList"
        :http-request="doUpload" :on-remove="onRemove"
      >
        <el-icon size="40" color="#909399"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到这里，或 <em>点击上传</em>（支持 .xlsx / .csv，≤50MB）</div>
      </el-upload>

      <template v-if="fileInfo">
        <el-form inline style="margin-top: 20px">
          <el-form-item label="工作表">
            <el-select v-model="sheetName" style="width: 240px">
              <el-option
                v-for="s in fileInfo.sheets" :key="s.name"
                :label="`${s.name}（${s.total_rows} 行数据）`" :value="s.name"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="表头所在行">
            <el-input-number v-model="headerRow" :min="1" :max="50" />
          </el-form-item>
        </el-form>

        <el-table v-if="currentSheet && currentSheet.headers.length" :data="previewRows" size="small" border max-height="260">
          <el-table-column
            v-for="(h, i) in currentSheet.headers" :key="i"
            :prop="String(i)" :label="h" show-overflow-tooltip
          />
        </el-table>

        <el-button type="primary" :loading="analyzing" style="margin-top: 16px" @click="doAnalyze">
          开始 AI 分析
        </el-button>
      </template>
    </el-card>

    <!-- 第 2 步：AI 分析中 -->
    <el-card v-if="step === 1">
      <div v-loading="true" element-loading-text="AI 正在分析表结构，请稍候..." style="height: 220px" />
    </el-card>

    <!-- 第 3 步：确认结构 -->
    <template v-if="step === 2">
      <el-alert
        v-if="analysis?.notes" :title="'AI 分析说明：' + analysis.notes"
        type="info" :closable="false" style="margin-bottom: 12px"
      />
      <el-form inline>
        <el-form-item label="表名称">
          <el-input v-model="confirm.label" style="width: 240px" placeholder="如：客户跟进记录" />
        </el-form-item>
        <el-form-item label="表名">
          <el-input v-model="confirm.name" style="width: 240px" placeholder="留空自动生成 dyn_xxx" />
        </el-form-item>
        <el-form-item label="存储方式">
          <el-radio-group v-model="confirm.storage_mode">
            <el-radio value="json">JSON 存储（推荐）</el-radio>
            <el-radio value="physical" :disabled="!canUsePhysical">
              独立物理表{{ canUsePhysical ? '（VIP）' : '（VIP 功能）' }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <el-table :data="confirm.fields" border size="small">
        <el-table-column label="源表头" width="130">
          <template #default="{ row }">{{ row.source_header }}</template>
        </el-table-column>
        <el-table-column label="字段名" width="170">
          <template #default="{ row }"><el-input v-model="row.field_name" size="small" /></template>
        </el-table-column>
        <el-table-column label="显示名" width="150">
          <template #default="{ row }"><el-input v-model="row.label" size="small" /></template>
        </el-table-column>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">
            <el-select v-model="row.data_type" size="small" @change="onTypeChange(row)">
              <el-option v-for="t in DATA_TYPES" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="长度" width="90">
          <template #default="{ row }">
            <el-input-number v-if="row.data_type === 'varchar'" v-model="row.length" size="small" :min="1" :max="4000" :controls="false" />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="必填" width="60" align="center">
          <template #default="{ row }"><el-switch v-model="row.nullable" :active-value="false" :inactive-value="true" size="small" /></template>
        </el-table-column>
        <el-table-column label="控件" width="140">
          <template #default="{ row }">
            <el-select v-model="row.widget" size="small">
              <el-option v-for="w in WIDGETS" :key="w.value" :label="w.label" :value="w.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.confidence != null" :type="confidenceType(row.confidence)" size="small">
              {{ Math.round(row.confidence * 100) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ $index }">
            <el-button text size="small" :disabled="$index === 0" @click="moveField($index, -1)">上移</el-button>
            <el-button text size="small" :disabled="$index === confirm.fields.length - 1" @click="moveField($index, 1)">下移</el-button>
            <el-button text size="small" type="danger" @click="confirm.fields.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px">
        <el-button @click="addField">添加字段</el-button>
        <el-button @click="step = 0">上一步</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">确认建表并导入</el-button>
      </div>
    </template>

    <!-- 第 4 步：导入结果 -->
    <el-card v-if="step === 3 && report">
      <el-result
        :icon="report.failed === 0 ? 'success' : 'warning'"
        title="建表完成"
        :sub-title="`共 ${report.total} 行数据：成功 ${report.success} 行，失败 ${report.failed} 行`"
      >
        <template #extra>
          <el-button type="primary" @click="$router.push(`/t/${createdTableId}`)">查看数据表</el-button>
          <el-button @click="reset">再导入一个</el-button>
        </template>
      </el-result>
      <template v-if="report.failures?.length">
        <h4>失败明细（最多显示 200 条）</h4>
        <el-table :data="report.failures" size="small" border max-height="320">
          <el-table-column prop="row_no" label="Excel 行号" width="100" />
          <el-table-column prop="error" label="错误原因" width="320" show-overflow-tooltip />
          <el-table-column label="原始数据">
            <template #default="{ row }">
              <span style="font-size: 12px; color: #909399">{{ JSON.stringify(row.values) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { analyzeExcel, createTable, uploadExcel } from '../api'

const DATA_TYPES = [
  { value: 'varchar', label: '文本' }, { value: 'text', label: '长文本' },
  { value: 'int', label: '整数' }, { value: 'decimal', label: '小数' },
  { value: 'date', label: '日期' }, { value: 'datetime', label: '日期时间' },
  { value: 'bool', label: '是/否' },
]
const WIDGETS = [
  { value: 'input', label: '输入框' }, { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' }, { value: 'date-picker', label: '日期选择' },
  { value: 'datetime-picker', label: '日期时间' }, { value: 'select', label: '下拉选择' },
  { value: 'switch', label: '开关' },
]
const DEFAULT_WIDGET = {
  varchar: 'input', text: 'textarea', int: 'number', decimal: 'number',
  date: 'date-picker', datetime: 'datetime-picker', bool: 'switch',
}

const step = ref(0)
const fileList = ref([])
const fileInfo = ref(null)
const sheetName = ref('')
const headerRow = ref(1)
const analyzing = ref(false)
const analysis = ref(null)
const confirm = reactive({ label: '', name: '', fields: [], storage_mode: 'json' })
const creating = ref(false)
const report = ref(null)
const createdTableId = ref(null)

const myPerms = JSON.parse(localStorage.getItem('grt_user') || '{}').perms || []
const canUsePhysical = myPerms.includes('create_physical_table')

const currentSheet = computed(() => fileInfo.value?.sheets.find((s) => s.name === sheetName.value))
const previewRows = computed(() =>
  (currentSheet.value?.sample || []).map((row) => Object.fromEntries(row.map((v, i) => [String(i), v])))
)

async function doUpload({ file }) {
  try {
    const res = await uploadExcel(file)
    fileInfo.value = res
    const first = res.sheets.find((s) => s.total_rows > 0) || res.sheets[0]
    sheetName.value = first?.name || ''
    headerRow.value = first?.header_row || 1
    ElMessage.success('上传成功')
  } catch (e) {
    fileList.value = []
    ElMessage.error(e.message)
  }
}

function onRemove() {
  fileInfo.value = null
  fileList.value = []
}

function confidenceType(c) {
  return c >= 0.9 ? 'success' : c >= 0.7 ? 'warning' : 'danger'
}

async function doAnalyze() {
  analyzing.value = true
  step.value = 1
  try {
    const res = await analyzeExcel({
      file_id: fileInfo.value.file_id,
      sheet_name: sheetName.value,
      header_row: headerRow.value,
    })
    analysis.value = res
    confirm.label = res.table_name_suggestion || fileInfo.value.file_name.replace(/\.[^.]+$/, '')
    confirm.name = ''
    confirm.fields = res.columns.map((c) => ({ ...c }))
    step.value = 2
  } catch (e) {
    ElMessage.error(e.message)
    step.value = 0
  } finally {
    analyzing.value = false
  }
}

function onTypeChange(row) {
  row.widget = DEFAULT_WIDGET[row.data_type] || 'input'
}

function moveField(index, dir) {
  const arr = confirm.fields
  const j = index + dir
  if (j < 0 || j >= arr.length) return
  ;[arr[index], arr[j]] = [arr[j], arr[index]]
}

let newFieldSeq = 1
function addField() {
  confirm.fields.push({
    source_header: null, field_name: `extra_${newFieldSeq++}`, label: '新字段',
    data_type: 'varchar', length: 255, nullable: true, widget: 'input', options: {},
  })
}

async function doCreate() {
  if (!confirm.label.trim()) return ElMessage.warning('请填写表名称')
  if (!confirm.fields.length) return ElMessage.warning('至少需要一个字段')
  creating.value = true
  try {
    const res = await createTable({
      label: confirm.label.trim(),
      name: confirm.name.trim() || null,
      fields: confirm.fields.map(({ confidence, ...f }) => f),
      storage_mode: confirm.storage_mode,
      source: { file_id: fileInfo.value.file_id, sheet_name: sheetName.value, header_row: headerRow.value },
    })
    report.value = res.import_report
    createdTableId.value = res.table.id
    step.value = 3
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    creating.value = false
  }
}

function reset() {
  step.value = 0
  fileList.value = []
  fileInfo.value = null
  analysis.value = null
  report.value = null
  createdTableId.value = null
  confirm.label = ''
  confirm.name = ''
  confirm.fields = []
  confirm.storage_mode = 'json'
}
</script>
