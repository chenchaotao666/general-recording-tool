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
       内容多时自动增高（上限 220px 后滚动）；Enter 换行、Ctrl+Enter/失焦提交、Esc 取消。
       preview（单击选中态）：同一浮层只读展示全文——用 div 而非 readonly textarea
       （Chrome 里 readonly textarea 的内容仍可被拖选），失焦/点外部/Esc 关闭，双击浮层进编辑 -->
  <template v-else-if="editorKind === 'inline'">
    <span ref="anchorRef" class="cell-anchor" />
    <teleport to="body">
      <div v-if="overlayRect" class="cell-overlay" :class="{ preview }" :style="overlayStyle"
           @mousedown.stop @dblclick.stop="preview && $emit('enter-edit')">
        <div v-if="preview" ref="taRef" class="cell-textarea preview-text" :style="taStyle">{{ draft }}</div>
        <textarea v-else ref="taRef" v-model="draft" class="cell-textarea" :style="taStyle" rows="1"
                  @input="autoGrow" @keydown.esc="discard"
                  @keydown.ctrl.enter="commitInline" @blur="commitInline" />
      </div>
    </teleport>
  </template>

  <!-- 单选/多选：自定义下拉面板（设计稿：单元格输入-单选.png；搜索/创建选项/联动过滤） -->
  <SelectCellPanel
    v-else-if="editorKind === 'select'" :field="field" :record="record" :frozen="frozen"
    @commit="(v) => $emit('commit', v)" @cancel="$emit('cancel')"
    @add-option="(label) => $emit('add-option', label)" />

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
import { computed, getCurrentInstance, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { regOf } from '../../../smart/registry/fieldRegistry.js'
import { uploadImageFile } from '../../../api/index.js'
import SelectCellPanel from './SelectCellPanel.vue'

const props = defineProps({
  field: { type: Object, required: true },
  record: { type: Object, required: true },
  frozen: { type: Boolean, default: false },   // 列是否被冻结（判断显示副本在哪个 wrapper）
  preview: { type: Boolean, default: false },  // 单击选中的只读预览（仅文本浮层用）
})
const emit = defineEmits(['commit', 'cancel', 'open-config', 'add-option', 'enter-edit'])

const memberList = inject('smartMembers', { value: [] })          // [{id, name}]
const relationRows = inject('smartRelationRows', { value: new Map() })  // targetTableId → [{id,label}]

const cfg = computed(() => props.field.options || {})
const ft = computed(() => props.field.field_type || 'text')
const editorKind = computed(() => regOf(props.field).editor)
const isMulti = computed(() => ft.value === 'multiSelect')
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
const selfInst = getCurrentInstance()   // 必须在 setup 顶层捕获，回调里调用会返回 null

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
// 文字排版与查看态逐像素对齐。实测查看态文字 top 偏移 = max(6, (H-26)/2)
// （52/76/100 按公式，36px 默认行高因 vxe 取整多 1px——硬公式会让文字上移 1px 被感知为抖动）；
// 浮层 2px 边框吞掉的 2px 从 padding-top 里扣回，padBottom 补齐使单行 scrollHeight 恰等于内容盒高。
const taStyle = computed(() => {
  const r = overlayRect.value
  const viewTop = Math.max(6, ((r?.height || 36) - 26) / 2)
  const padTop = Math.max(0, viewTop - 2)
  const padBottom = ((r?.height || 36) - 26) - padTop
  return { padding: `${padTop}px 6px ${padBottom}px` }
})
function autoGrow() {
  const ta = taRef.value
  if (!ta) return
  ta.style.height = 'auto'
  // border-box：scrollHeight 即整高（含 padding）；内容盒至少与单元格等高（减去浮层边框 4px）
  const min = (overlayRect.value?.height || 36) - 4
  const need = ta.scrollHeight
  // 单行吸附到内容盒等高（容忍 scrollHeight 的 1px 取整误差）；多行按内容撑高（上限 216px）
  const h = need <= min + 1 ? min : Math.min(need, 216)
  ta.style.height = `${h}px`
  ta.style.overflowY = need > h ? 'auto' : 'hidden'
}
function focusTextarea() {
  const ta = taRef.value
  if (!ta || props.preview) return
  ta.focus({ preventScroll: true })
  const end = draft.value?.length || 0
  ta.setSelectionRange?.(end, end)
}
onMounted(() => nextTick(() => {
  // vxe 冻结列会把同一单元格渲染三份（main / fixed-left / fixed-right wrapper），
  // 冻结列的显示副本在 fixed wrapper、非冻结列在 main wrapper；非显示副本的编辑器
  // 必须完全惰性（不聚焦不开浮层），否则多实例互抢焦点，失焦误提交并把编辑态关掉。
  // （td 上的 fixed--hidden 类是 vxe 后置补的，挂载时不存在，只能按 wrapper 判断；
  //  多根组件的 $el 可能是文本锚点节点，没有 closest，须先取到元素节点）
  const root = selfInst?.proxy?.$el
  const rootEl = root?.nodeType === 1 ? root : root?.parentElement
  const hostTd = rootEl?.closest?.('td')
  const inFixed = !!hostTd?.closest?.('.vxe-table--fixed-left-wrapper, .vxe-table--fixed-right-wrapper')
  if (inFixed !== props.frozen) return
  const el = inputRef.value?.focus?.() || selectRef.value?.focus?.() || dateRef.value?.focus?.()
  // 文本浮层：锚定单元格位置；编辑态聚焦，预览态（div）不可聚焦、由 Esc/点外部关闭
  if (anchorRef.value) {
    const td = anchorRef.value.closest('td') || anchorRef.value.parentElement
    overlayRect.value = td?.getBoundingClientRect() || null
    // overlayRect 驱动 v-if 渲染内容——等下一拍渲染完成再聚焦（否则 taRef 还是 null）
    nextTick(() => {
      autoGrow()
      if (props.preview) {
        // 预览态：点击浮层和宿主单元格之外 = 关闭（div 无焦点，没有 blur 可用）
        document.addEventListener('mousedown', onPreviewOutside, true)
        return
      }
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

// 预览态点外部关闭（捕获阶段；浮层自身 mousedown.stop 不会触发）
function onPreviewOutside(e) {
  const overlay = taRef.value?.closest('.cell-overlay')
  const td = anchorRef.value?.closest('td')
  if (overlay?.contains(e.target) || td?.contains(e.target)) return
  emit('cancel')
}

// 预览 → 编辑切换：内容从 div 换成 textarea，补焦一次；预览的外部点击监听摘掉
// （否则编辑态点外部会被误取消，编辑态的关闭走 textarea blur 提交）
watch(() => props.preview, async (p) => {
  if (p || !anchorRef.value) return
  document.removeEventListener('mousedown', onPreviewOutside, true)
  await nextTick()
  autoGrow()
  focusTextarea()
})

function commitInline() {
  if (discarded) return
  // vxe 重渲染会直接重建单元格 DOM（不走 Vue 卸载），textarea 被移除文档树触发 blur，
  // 这种"卸载性 blur"不是用户操作，不提交
  if (taRef.value && !taRef.value.isConnected) return
  if (inputRef.value?.$el && !inputRef.value.$el.isConnected) return
  let v = draft.value
  if (['number', 'percent', 'currency', 'progress'].includes(ft.value)) {
    if (v === '' || v == null) v = null
    else if (Number.isNaN(Number(v))) { ElMessage.warning('请输入数字'); return }
    else v = Number(v)
  }
  emit('commit', v === '' ? null : v)
}
function commit() { emit('commit', draft.value === '' ? null : draft.value) }
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
// 组件被卸载（如 vxe 重渲染重建单元格 DOM）时 textarea 的 blur 会误触发提交，一律禁止
onBeforeUnmount(() => {
  discarded = true
  document.removeEventListener('mousedown', onPreviewOutside, true)
})
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
/* 单击预览态：div 展示全文（Chrome 里 readonly textarea 仍可拖选，div 才可靠禁选） */
.cell-overlay.preview .preview-text {
  user-select: none; cursor: default; white-space: pre-wrap; word-break: break-all;
}
.slider { padding: 0 8px; }
.url-editor { background: #fff; border: 1px solid var(--el-border-color); border-radius: 6px; padding: 8px; box-shadow: var(--el-box-shadow-light); min-width: 220px; }
.url-field { margin-bottom: 6px; }
.url-ops { display: flex; justify-content: flex-end; gap: 6px; }
.blocked { display: flex; align-items: center; gap: 6px; background: #fff; padding: 4px 8px; border-radius: 6px; box-shadow: var(--el-box-shadow-light); font-size: 12px; }
.blocked-text { color: var(--el-text-color-secondary); }
.hint { color: #909399; font-size: 12px; margin-top: 4px; }
</style>
