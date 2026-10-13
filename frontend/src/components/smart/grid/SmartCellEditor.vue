<template>
  <!-- 编辑态挂载器：按字段类型分发编辑器（设计文档 §4：六类提交策略）。
       统一契约：props {field, record}，emit commit(value) / cancel() -->
  <!-- 内联输入（文本/数字/百分数/货币/电话/邮箱）：失焦/回车提交，Esc 取消 -->
  <el-input
    v-if="editorKind === 'inline'" ref="inputRef" v-model="draft" size="small" class="cell-editor"
    @blur="commitInline" @keyup.enter="commitInline" @keyup.esc="$emit('cancel')">
    <template v-if="field.field_type === 'percent'" #suffix>%</template>
  </el-input>

  <!-- 单选/多选：下拉浮层（单选点选即关，多选失焦关） -->
  <el-select
    v-else-if="editorKind === 'select'" ref="selectRef" v-model="draft" size="small" class="cell-editor"
    :multiple="isMulti" :teleported="false" :teleported-fix="false" automatic-dropdown clearable
    :filterable="true" :allow-create="allowCreate" default-first-option
    @change="onSelectChange" @visible-change="(vis) => !vis && onSelectBlur()">
    <el-option v-for="o in (field.options?.options || [])" :key="o.id" :value="o.id">
      <span class="opt-tag" :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">{{ o.label }}</span>
    </el-option>
  </el-select>

  <!-- 日期 -->
  <el-date-picker
    v-else-if="editorKind === 'date'" ref="dateRef" v-model="draft" size="small" class="cell-editor"
    :type="cfg.includeTime ? 'datetime' : 'date'" value-format="YYYY-MM-DD HH:mm:ss"
    :teleported="false" @change="commit" @visible-change="(vis) => !vis && $emit('cancel')" />

  <!-- 人员：成员多选（V1 单层浮层，数据源=租户成员） -->
  <el-select
    v-else-if="editorKind === 'member'" ref="selectRef" v-model="draft" size="small" class="cell-editor"
    :multiple="cfg.multiple !== false" filterable :teleported="false" automatic-dropdown
    @visible-change="(vis) => !vis && commit()">
    <el-option v-for="m in memberList" :key="m.id" :value="m.id" :label="m.name" />
  </el-select>

  <!-- 链接：显式确认表单 -->
  <div v-else-if="editorKind === 'url'" class="url-editor" @click.stop>
    <el-input v-model="urlText" size="small" placeholder="显示文本" class="url-field" />
    <el-input v-model="urlLink" size="small" placeholder="链接 https://…" class="url-field" />
    <div class="url-ops">
      <el-button size="small" @click="$emit('cancel')">取消</el-button>
      <el-button size="small" type="primary" @click="commitUrl">确认</el-button>
    </div>
  </div>

  <!-- 进度：滑块 -->
  <el-slider
    v-else-if="editorKind === 'progress'" v-model="draft" size="small" class="cell-editor slider"
    :min="cfg.range?.min ?? 0" :max="cfg.range?.max ?? 100" @change="commit" />

  <!-- 图片/文件：上传面板 -->
  <div v-else-if="editorKind === 'upload'" class="upload-editor" @click.stop>
    <el-upload :show-file-list="false" :http-request="onUpload" multiple
               :accept="field.field_type === 'image' ? 'image/*' : undefined">
      <el-button size="small" type="primary" plain>＋ 添加{{ field.field_type === 'image' ? '图片' : '文件' }}</el-button>
    </el-upload>
    <div v-if="uploading" class="hint">上传中…</div>
  </div>

  <!-- 关联：目标表记录选择 -->
  <el-select
    v-else-if="editorKind === 'relation'" ref="selectRef" v-model="draft" size="small" class="cell-editor"
    :multiple="cfg.multiple !== false" filterable :teleported="false" automatic-dropdown
    @visible-change="(vis) => !vis && commit()">
    <el-option v-for="r in relationOptions" :key="r.id" :value="r.id" :label="r.label" />
  </el-select>

  <!-- 只读字段：提示气泡（BlockedEditor，设计文档 §4.3） -->
  <div v-else class="blocked" @click.stop>
    <span class="blocked-text">{{ blockedText }}</span>
    <el-button link type="primary" size="small" @click="$emit('open-config', field)">修改设置</el-button>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { regOf, optionColor } from '../../../smart/registry/fieldRegistry.js'
import { uploadImageFile } from '../../../api/index.js'

const props = defineProps({
  field: { type: Object, required: true },
  record: { type: Object, required: true },
})
const emit = defineEmits(['commit', 'cancel', 'open-config', 'add-option'])

const memberList = inject('smartMembers', { value: [] })          // [{id, name}]
const relationRows = inject('smartRelationRows', { value: new Map() })  // targetTableId → [{id,label}]

const cfg = computed(() => props.field.options || {})
const ft = computed(() => props.field.field_type || 'text')
const editorKind = computed(() => regOf(props.field).editor)
const isMulti = computed(() => ft.value === 'multiSelect')
const allowCreate = computed(() => cfg.value.allowAddOptionWhenEditing !== false)
const blockedText = computed(() => ({
  formula: '公式计算结果不可直接编辑', lookup: '查找引用内容不可直接编辑',
  createdBy: '创建人字段不可直接编辑', lastModifiedBy: '最后编辑人字段不可直接编辑',
  createdTime: '创建时间字段不可直接编辑', lastModifiedTime: '最后编辑时间字段不可直接编辑',
  autoNumber: '自动编号不可直接编辑',
}[ft.value] || '该字段不可直接编辑'))

const cur = props.record[props.field.field_name]
const draft = ref(
  ft.value === 'progress' ? Number(cur ?? cfg.value.range?.min ?? 0)
    : Array.isArray(cur) ? [...cur] : (cur ?? (isMulti.value ? [] : '')))

// 链接双字段
const urlText = ref(cur?.text || '')
const urlLink = ref(cur?.url || '')

const inputRef = ref(null)
const selectRef = ref(null)
const dateRef = ref(null)
onMounted(() => nextTick(() => inputRef.value?.focus?.() || selectRef.value?.focus?.() || dateRef.value?.focus?.()))

function commitInline() {
  let v = draft.value
  if (['number', 'percent', 'currency', 'progress'].includes(ft.value)) {
    if (v === '' || v == null) v = null
    else if (Number.isNaN(Number(v))) { ElMessage.warning('请输入数字'); return }
    else v = Number(v)
  }
  emit('commit', v === '' ? null : v)
}
function commit() { emit('commit', draft.value === '' ? null : draft.value) }
function onSelectChange(v) {
  if (!isMulti.value) emit('commit', v ?? null)   // 单选点选即提交并关闭
}
function onSelectBlur() { if (isMulti.value) commit() }
function commitUrl() {
  if (!urlLink.value) { ElMessage.warning('链接不能为空'); return }
  const url = /^https?:\/\//i.test(urlLink.value) ? urlLink.value : `https://${urlLink.value}`
  emit('commit', { url, text: urlText.value || urlLink.value })
}

const uploading = ref(false)
async function onUpload({ file }) {
  uploading.value = true
  try {
    const res = await uploadImageFile(file)
    const fid = res?.id ?? res?.file_id ?? res
    const list = Array.isArray(draft.value) ? [...draft.value] : []
    list.push(ft.value === 'image' ? String(fid) : { id: fid, name: file.name })
    draft.value = list
    commit()
  } catch (e) {
    ElMessage.error(e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

const relationOptions = computed(() => relationRows.value.get(cfg.value.targetTableId) || [])
</script>

<style scoped>
.cell-editor { width: 100%; }
.cell-editor :deep(.el-input__wrapper) { box-shadow: 0 0 0 2px var(--el-color-primary) inset; }
.slider { padding: 0 8px; }
.url-editor { background: #fff; border: 1px solid var(--el-border-color); border-radius: 6px; padding: 8px; box-shadow: var(--el-box-shadow-light); min-width: 220px; }
.url-field { margin-bottom: 6px; }
.url-ops { display: flex; justify-content: flex-end; gap: 6px; }
.blocked { display: flex; align-items: center; gap: 6px; background: #fff; padding: 4px 8px; border-radius: 6px; box-shadow: var(--el-box-shadow-light); font-size: 12px; }
.blocked-text { color: var(--el-text-color-secondary); }
.hint { color: #909399; font-size: 12px; margin-top: 4px; }
.opt-tag { padding: 1px 8px; border-radius: 10px; font-size: 12px; }
</style>
