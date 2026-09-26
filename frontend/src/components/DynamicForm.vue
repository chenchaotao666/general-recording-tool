<template>
  <div>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
      <el-form-item v-for="f in fields" :key="f.field_name" :label="f.label" :prop="f.field_name">
        <el-input
          v-if="f.widget === 'textarea'"
          v-model="form[f.field_name]" type="textarea" :rows="5" :placeholder="'请输入' + f.label"
        />
        <el-input-number
          v-else-if="f.widget === 'number'"
          v-model="form[f.field_name]" style="width: 100%" controls-position="right"
        />
        <el-date-picker
          v-else-if="f.widget === 'date-picker'"
          v-model="form[f.field_name]" type="date" value-format="YYYY-MM-DD"
          :placeholder="'请选择' + f.label" style="width: 100%"
        />
        <el-date-picker
          v-else-if="f.widget === 'datetime-picker'"
          v-model="form[f.field_name]" type="datetime" value-format="YYYY-MM-DD HH:mm:ss"
          :placeholder="'请选择' + f.label" style="width: 100%"
        />
        <el-select
          v-else-if="f.widget === 'select'"
          v-model="form[f.field_name]" clearable :placeholder="'请选择' + f.label" style="width: 100%"
        >
          <el-option v-for="opt in fieldOptions(f)" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-switch v-else-if="f.widget === 'switch'" v-model="form[f.field_name]" />
        <!-- 图片字段：压缩上传，最多 5 张，可预览/删除 -->
        <el-upload
          v-else-if="f.widget === 'image-uploader'"
          :file-list="imageLists[f.field_name] || []" list-type="picture-card" accept="image/*"
          :limit="5" multiple :http-request="(req) => uploadImage(f.field_name, req)"
          :on-remove="(file) => removeImage(f.field_name, file)"
          :on-preview="(file) => previewImage(f.field_name, file)"
        >
          <el-icon><Plus /></el-icon>
        </el-upload>
        <el-input v-else v-model="form[f.field_name]" clearable :placeholder="'请输入' + f.label" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="onSubmit">保存</el-button>
        <el-button @click="$emit('cancel')">取消</el-button>
        <el-button
          v-if="tableId" type="success" plain :icon="Camera"
          style="margin-left: auto" @click="openVision"
        >智能识别</el-button>
      </el-form-item>
    </el-form>

    <!-- 图片预览 -->
    <el-image-viewer
      v-if="previewList.length" :url-list="previewList" :initial-index="previewIndex"
      teleported hide-on-click-modal @close="previewList = []"
    />

    <!-- 智能识别对话框 -->
    <el-dialog v-model="visionVisible" title="图片智能识别" width="760px" destroy-on-close append-to-body>
      <!-- 上传阶段 -->
      <template v-if="visionStage === 'upload'">
        <el-upload
          v-model:file-list="imgList" :auto-upload="false" :limit="5" multiple
          accept="image/*" list-type="picture-card"
        >
          <el-icon><Plus /></el-icon>
        </el-upload>
        <div style="margin-top: 8px; color: #909399; font-size: 12px">
          上传单据、名片、截图等图片（最多 5 张），AI 会自动识别内容并建议填入下方表单。识别结果需要你确认后才会填入。
        </div>
        <div style="margin-top: 16px; text-align: right">
          <el-button @click="visionVisible = false">取消</el-button>
          <el-button type="primary" :loading="recognizing" :disabled="!imgList.length" @click="doRecognize">
            开始识别
          </el-button>
        </div>
      </template>

      <!-- 结果确认阶段 -->
      <template v-else>
        <el-alert
          v-if="visionResult?.notes" :title="visionResult.notes" type="info"
          :closable="false" style="margin-bottom: 12px"
        />
        <el-empty v-if="!visionRows.length" description="未能从图片中识别出可填入的字段" />
        <el-table v-else :data="visionRows" size="small" border max-height="420">
          <el-table-column width="50" align="center">
            <template #default="{ row }"><el-checkbox v-model="row.adopt" /></template>
          </el-table-column>
          <el-table-column label="字段" prop="label" width="130" />
          <el-table-column label="当前值" min-width="120">
            <template #default="{ row }">
              <span style="color: #909399">{{ displayVal(row.current) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="识别值" min-width="120">
            <template #default="{ row }">
              <span :style="row.conflict ? 'color: #e6a23c; font-weight: 600' : ''">{{ displayVal(row.recognized) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tooltip :content="row.conflictReason || ''" :disabled="!row.conflict">
                <el-tag size="small" :type="row.conflict ? 'warning' : 'success'">
                  {{ row.conflict ? '冲突' : '新值' }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
        <div style="margin-top: 16px; text-align: right">
          <el-button @click="visionStage = 'upload'">重新识别</el-button>
          <el-button type="primary" :disabled="!visionRows.some((r) => r.adopt)" @click="applyVision">
            应用选中到表单
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Camera, Plus } from '@element-plus/icons-vue'
import { adoptVision, imageUrl, recognizeForm, uploadImage as apiUploadImage } from '../api'

const props = defineProps({
  fields: { type: Array, required: true },
  initial: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  tableId: { type: Number, default: null },   // 有 tableId 才显示智能识别
  recordId: { type: Number, default: null },  // 编辑场景的记录 id（留痕用）
})
const emit = defineEmits(['submit', 'cancel'])

const formRef = ref()
const form = reactive({})

watch(
  () => props.initial,
  (v) => {
    for (const key of Object.keys(form)) delete form[key]
    for (const f of props.fields) {
      const val = v?.[f.field_name]
      if (val !== undefined && val !== null) {
        form[f.field_name] = val
      } else if (f.widget === 'switch') {
        form[f.field_name] = false
      } else if (f.widget === 'image-uploader') {
        form[f.field_name] = []
      } else {
        form[f.field_name] = null
      }
      // 图片字段：由 file_id 列表构建 el-upload 的 file-list
      if (f.widget === 'image-uploader') {
        const ids = Array.isArray(form[f.field_name]) ? form[f.field_name] : []
        form[f.field_name] = ids
        imageLists[f.field_name] = ids.map((id) => ({ uid: id, name: id.slice(0, 8), url: imageUrl(id), status: 'success' }))
      }
    }
  },
  { immediate: true, deep: true }
)

// ---------- 图片上传 ----------
const imageLists = reactive({})   // field_name → el-upload file-list
const previewList = ref([])
const previewIndex = ref(0)

// 上传前压缩（最长边 1600 JPEG），与助手粘贴图片同一策略
function compressImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, 1600 / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale)
      canvas.height = Math.round(img.height * scale)
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      canvas.toBlob(
        (blob) => resolve(new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' })),
        'image/jpeg', 0.85,
      )
    }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('图片读取失败')) }
    img.src = url
  })
}

async function uploadImage(fieldName, req) {
  try {
    const compressed = await compressImage(req.file)
    const res = await apiUploadImage(compressed)
    const fid = res.files[0].id
    if (!Array.isArray(form[fieldName])) form[fieldName] = []
    form[fieldName].push(fid)
    imageLists[fieldName] = [
      ...(imageLists[fieldName] || []),
      { uid: fid, name: fid.slice(0, 8), url: imageUrl(fid), status: 'success' },
    ]
    req.onSuccess && req.onSuccess({})
  } catch (e) {
    ElMessage.error(e.message)
    req.onError && req.onError(e)
  }
}

function removeImage(fieldName, file) {
  const ids = Array.isArray(form[fieldName]) ? form[fieldName] : []
  form[fieldName] = ids.filter((id) => id !== file.uid)
  imageLists[fieldName] = (imageLists[fieldName] || []).filter((x) => x.uid !== file.uid)
}

function previewImage(fieldName, file) {
  const ids = Array.isArray(form[fieldName]) ? form[fieldName] : []
  previewList.value = ids.map(imageUrl)
  previewIndex.value = Math.max(0, ids.indexOf(file.uid))
}

const rules = computed(() => {
  const r = {}
  for (const f of props.fields) {
    if (!f.nullable) {
      r[f.field_name] = [{ required: true, message: `请填写${f.label}`, trigger: ['blur', 'change'] }]
    }
  }
  return r
})

function fieldOptions(f) {
  return (f.options?.options || []).map((o) =>
    typeof o === 'object' && o !== null ? o : { label: String(o), value: o }
  )
}

async function onSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  emit('submit', { ...form })
}

// ---------- 智能识别 ----------
const visionVisible = ref(false)
const visionStage = ref('upload')   // upload | result
const imgList = ref([])
const recognizing = ref(false)
const visionResult = ref(null)
const visionRows = ref([])

function openVision() {
  visionStage.value = 'upload'
  imgList.value = []
  visionResult.value = null
  visionRows.value = []
  visionVisible.value = true
}

function displayVal(v) {
  if (v === null || v === undefined || v === '') return '（空）'
  if (v === true) return '是'
  if (v === false) return '否'
  return String(v)
}

async function doRecognize() {
  recognizing.value = true
  try {
    const fd = new FormData()
    fd.append('table_id', String(props.tableId))
    fd.append('current', JSON.stringify({ ...form }))
    if (props.recordId) fd.append('record_id', String(props.recordId))
    for (const item of imgList.value) {
      fd.append('images', item.raw)
    }
    const res = await recognizeForm(fd)
    visionResult.value = res
    const conflictMap = Object.fromEntries((res.conflicts || []).map((c) => [c.field_name, c.reason]))
    visionRows.value = Object.entries(res.fields || {}).map(([fieldName, recognized]) => {
      const f = props.fields.find((x) => x.field_name === fieldName)
      const conflict = fieldName in conflictMap
      return {
        field_name: fieldName,
        label: f?.label || fieldName,
        current: form[fieldName],
        recognized,
        conflict,
        conflictReason: conflictMap[fieldName],
        adopt: !conflict,   // 冲突字段默认不勾选，让用户主动确认
      }
    })
    visionStage.value = 'result'
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    recognizing.value = false
  }
}

async function applyVision() {
  const adopted = visionRows.value.filter((r) => r.adopt)
  for (const row of adopted) {
    form[row.field_name] = row.recognized
  }
  if (visionResult.value?.log_id) {
    adoptVision(visionResult.value.log_id, adopted.map((r) => r.field_name)).catch(() => {})
  }
  visionVisible.value = false
  ElMessage.success(`已填入 ${adopted.length} 个字段，请检查后保存`)
}
</script>
