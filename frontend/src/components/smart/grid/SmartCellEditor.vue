<template>
  <!-- 编辑态挂载器：按字段类型分发编辑器（设计文档 §4：六类提交策略）。
       统一契约：props {field, record}，emit commit(value) / cancel() -->
  <!-- 内联输入（数字/百分数/货币/电话/邮箱）：失焦/回车提交，Esc 取消 -->
  <el-input
    v-if="editorKind === 'inline' && ft !== 'text'" ref="inputRef" v-model="draft" size="small" class="cell-editor"
    @blur="commitInline" @keyup.enter="commitInline" @keyup.esc="$emit('cancel')">
    <template v-if="field.field_type === 'percent'" #suffix>%</template>
  </el-input>

  <!-- 文本：双击进入的浮层编辑（企微式）。边界=单元格（边框与选中态同款 2px 主色），
       内容多时自动增高（上限 220px 后滚动）；Enter 换行、Ctrl+Enter/失焦提交、Esc 取消 -->
  <template v-else-if="editorKind === 'inline'">
    <span ref="anchorRef" class="cell-anchor" />
    <teleport to="body">
      <div v-if="overlayRect" class="cell-overlay" :style="overlayStyle" @mousedown.stop>
        <textarea ref="taRef" v-model="draft" class="cell-textarea" :style="taStyle" rows="1"
                  @input="autoGrow" @keydown.esc="discard"
                  @keydown.ctrl.enter="commitInline" @blur="commitInline" />
      </div>
    </teleport>
  </template>

  <!-- 单选/多选：下拉浮层（单选点选即关，多选失焦关）。
       面板挂 body（默认 teleported）：teleported=false 会被单元格 overflow 裁掉，等于没有选项 -->
  <el-select
    v-else-if="editorKind === 'select'" ref="selectRef" v-model="draft" size="small" class="cell-editor"
    :multiple="isMulti" automatic-dropdown clearable
    :filterable="true" :allow-create="allowCreate" default-first-option
    @change="onSelectChange" @visible-change="(vis) => !vis && onSelectBlur()">
    <el-option v-for="o in (field.options?.options || [])" :key="o.id" :value="o.id">
      <span class="opt-tag" :style="{ background: optionColor(o.color).value, color: optionColor(o.color).text }">{{ o.label }}</span>
    </el-option>
  </el-select>

  <!-- 日期（面板挂 body：teleported=false 会被单元格 overflow 裁掉，等于打不开） -->
  <el-date-picker
    v-else-if="editorKind === 'date'" ref="dateRef" v-model="draft" size="small" class="cell-editor"
    :type="cfg.includeTime ? 'datetime' : 'date'" value-format="YYYY-MM-DD HH:mm:ss"
    @change="commit" @visible-change="(vis) => !vis && $emit('cancel')" />

  <!-- 人员：成员多选（V1 单层浮层，数据源=租户成员；面板挂 body 防单元格裁剪） -->
  <el-select
    v-else-if="editorKind === 'member'" ref="selectRef" v-model="draft" size="small" class="cell-editor"
    :multiple="cfg.multiple !== false" filterable automatic-dropdown
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

  <!-- 关联：目标表记录选择（面板挂 body 防单元格裁剪） -->
  <el-select
    v-else-if="editorKind === 'relation'" ref="selectRef" v-model="draft" size="small" class="cell-editor"
    :multiple="cfg.multiple !== false" filterable automatic-dropdown
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

// 文本浮层编辑：定位锚=单元格 rect；高度随内容增长（上限 220px 滚动）
const anchorRef = ref(null)
const taRef = ref(null)
const overlayRect = ref(null)
const overlayStyle = computed(() => {
  const r = overlayRect.value
  if (!r) return {}
  // 宽度严格=单元格宽（只纵向随内容增高）
  return {
    left: `${r.left}px`, top: `${r.top}px`,
    width: `${r.width}px`, minHeight: `${r.height}px`,
  }
})
// 文字排版与查看态逐像素对齐（查看态：.vxe-cell padding 8px、行高 22px、smart-cell 13px），
// 否则编辑瞬间文字跳动且右边界收窄裁字。浮层 2px 边框吞掉的 2px 从 padding 里扣回。
const taStyle = computed(() => {
  const r = overlayRect.value
  const padV = r ? Math.max(0, (r.height - 4 - 22) / 2) : 5
  return { padding: `${padV}px 6px` }
})
function autoGrow() {
  const ta = taRef.value
  if (!ta) return
  ta.style.height = 'auto'
  // border-box：scrollHeight 即整高（含 padding）；内容盒至少与单元格等高（减去浮层边框 4px）
  const min = (overlayRect.value?.height || 36) - 4
  const h = Math.min(Math.max(ta.scrollHeight, min), 216)
  ta.style.height = `${h}px`
  ta.style.overflowY = ta.scrollHeight > 216 ? 'auto' : 'hidden'
}
function focusTextarea() {
  const ta = taRef.value
  if (!ta) return
  ta.focus({ preventScroll: true })
  const end = draft.value?.length || 0
  ta.setSelectionRange(end, end)
}
onMounted(() => nextTick(() => {
  const el = inputRef.value?.focus?.() || selectRef.value?.focus?.() || dateRef.value?.focus?.()
  // 文本浮层：锚定单元格位置并聚焦
  if (anchorRef.value) {
    const td = anchorRef.value.closest('td') || anchorRef.value.parentElement
    overlayRect.value = td?.getBoundingClientRect() || null
    // overlayRect 驱动 v-if 渲染 textarea——等下一拍渲染完成再聚焦（否则 taRef 还是 null）
    nextTick(() => {
      autoGrow()
      focusTextarea()
      // 兜底：个别时序下焦点会被表格内部处理夺回，下一帧校验补焦
      requestAnimationFrame(() => {
        const ta = taRef.value
        if (ta && document.activeElement !== ta && document.body.contains(ta)) focusTextarea()
      })
    })
  }
  return el
}))

function commitInline() {
  if (discarded) return
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
function discard() {
  discarded = true
  emit('cancel')
}
function commitUrl() {
  if (!urlLink.value) { ElMessage.warning('链接不能为空'); return }
  const url = /^https?:\/\//i.test(urlLink.value) ? urlLink.value : `https://${urlLink.value}`
  emit('commit', { url, text: urlText.value || urlLink.value })
}

// Esc/取消时浮层卸载会触发 blur → 防误提交：取消置标志，提交跳过
let discarded = false
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
.cell-editor { width: 100%; height: 100%; }
/* 编辑态边框统一由 SmartGrid 画在 .vxe-cell 上，wrapper 自身不再描边（避免 EP content-box 高 2px 被裁） */
.cell-editor :deep(.el-input__wrapper) { height: 100%; box-shadow: none; }
.cell-anchor { display: block; width: 100%; height: 100%; }
/* 文本浮层编辑（teleport 到 body）：边框与选中态同款 2px 主色，边界起于单元格 */
.cell-overlay {
  position: fixed; z-index: 3000; background: #fff; box-sizing: border-box;
  border: 2px solid var(--el-color-primary); border-radius: 2px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .12);
}
.cell-textarea {
  display: block; width: 100%; border: none; outline: none; resize: none;
  box-sizing: border-box; padding: 5px 6px; overflow-y: hidden;
  font-family: inherit; font-size: 13px; line-height: 22px; max-height: 216px;
}
.slider { padding: 0 8px; }
.url-editor { background: #fff; border: 1px solid var(--el-border-color); border-radius: 6px; padding: 8px; box-shadow: var(--el-box-shadow-light); min-width: 220px; }
.url-field { margin-bottom: 6px; }
.url-ops { display: flex; justify-content: flex-end; gap: 6px; }
.blocked { display: flex; align-items: center; gap: 6px; background: #fff; padding: 4px 8px; border-radius: 6px; box-shadow: var(--el-box-shadow-light); font-size: 12px; }
.blocked-text { color: var(--el-text-color-secondary); }
.hint { color: #909399; font-size: 12px; margin-top: 4px; }
.opt-tag { padding: 1px 8px; border-radius: 10px; font-size: 12px; }
</style>
