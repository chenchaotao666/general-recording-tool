<template>
  <!-- 表单视图（§12，对齐参照 右上角工具栏-生成表单-编辑(2).png / 新建-收集表单 编辑界面）：
       顶部工具条：↶ ↷ ｜ ⏱ 设置自动化提醒 ｜ 居中「编辑表单 | 填写表单」｜ 右侧分享
       编辑态：左侧「可添加字段」面板 + 中央画布（封面/标题/描述/题目卡片/添加新字段） -->
  <div class="fv">
    <div class="fv-bar">
      <div class="fv-bar-l">
        <button class="fv-ico st-icon-action" data-smart-tip="撤销" :disabled="!hist.past.length" @click="undo"><StIcon name="undo" :size="16" /></button>
        <button class="fv-ico st-icon-action" data-smart-tip="重做" :disabled="!hist.future.length" @click="redo"><StIcon name="redo" :size="16" /></button>
        <span class="fv-sep" />
        <button class="fv-tool" @click="emit('open-automation')"><StIcon name="automation" :size="15" />设置自动化提醒</button>
      </div>
      <div class="fv-tabs">
        <span class="fv-tab" :class="{ on: tab === 'edit' }" @click="tab = 'edit'">编辑表单</span>
        <span class="fv-tab" :class="{ on: tab === 'fill' }" @click="tab = 'fill'">填写表单</span>
      </div>
      <div class="fv-bar-r">
        <FormShare :view-id="view.id" :title="form.title" :can-manage="canManage" />
      </div>
    </div>

    <!-- ========== 编辑态 ========== -->
    <div v-if="tab === 'edit'" class="fv-main">
      <div class="fv-left">
        <div class="fv-left-head"><span>可添加字段</span><div class="fv-left-actions">
          <button class="fv-link-g" :disabled="!form.items.length" @click="removeAll">全部移出</button>
          <button class="fv-link-g" :disabled="!availableFields.length" @click="addAll">全部添加</button>
        </div></div>
        <div class="fv-field-list">
        <div v-if="!availableFields.length" class="fv-avail-empty">所有字段都已添加至表单</div>
        <div v-for="f in availableFields" :key="f.field_name" class="fv-avail" :class="{ dragging: dragItem?.fieldId === f.field_name }"
             :data-field-id="f.field_name" draggable="true" role="button" tabindex="0" data-smart-tip="点击添加，或拖动到右侧指定位置"
             @dragstart="startFieldDrag($event, f.field_name)" @dragend="endFieldDrag"
             @keydown.enter.prevent="addItem(f.field_name)" @click="addItem(f.field_name)">
          <StIcon :name="fieldIconName(f)" :size="14" />{{ f.label }}<StIcon name="plus" :size="13" class="fv-avail-plus" />
        </div>
        </div>
        <div class="fv-add-new" @click="(e) => emit('add-field', e)">
          <StIcon name="plus-circle" :size="16" />添加新字段到表单<StIcon name="chevron-right" :size="13" class="fv-add-caret" />
        </div>
      </div>
      <div ref="canvasRef" class="fv-canvas" @click="active = null" @dragover="dragCanvas"
           @dragleave="leaveCanvas" @drop.prevent="dropField" @dragend="endFieldDrag">
        <div class="fv-paper-wrap" :class="{ 'has-cover': form.cover }">
          <div class="fv-cover-bar" @click.stop>
            <img v-if="form.cover" :src="coverSrc" class="fv-cover-img" alt="表单封面" />
            <el-popover v-if="form.cover" v-model:visible="coverMenu" trigger="click" placement="bottom-end"
                        :width="150" popper-class="st-pop fv-cover-pop">
              <template #reference>
                <button class="fv-cover-more st-icon-action" aria-label="封面设置" data-smart-tip="封面设置"><StIcon name="more-h" :size="18" /></button>
              </template>
              <div class="fv-cover-menu">
                <button @click="coverMenu = false; coverPicker = true">更换封面</button>
                <button @click="coverMenu = false; setForm({ cover: null })">移除封面</button>
              </div>
            </el-popover>
            <button v-else class="fv-cover-btn" @click="coverPicker = true"><StIcon name="image" :size="15" />添加封面</button>
          </div>
          <div class="fv-paper">
            <input :value="form.title" class="fv-title" placeholder="表单标题" @change="(e) => setForm({ title: e.target.value })" />
            <input :value="form.description" class="fv-desc" placeholder="添加描述" @change="(e) => setForm({ description: e.target.value })" />
            <div class="fv-line" />

            <template v-for="(it, i) in itemsWithField" :key="it.fieldId">
            <div v-if="dragItem && dropIndex === i" class="fv-drop-placeholder" :style="{ height: `${dragHeight}px` }"
                 @dragover.prevent.stop="dragPlaceholder($event, i)" @drop.prevent.stop="dropField" />
            <div class="fv-q" :data-field-id="it.fieldId" :class="{ active: active === it.fieldId, dragging: dragItem?.existing && dragItem.fieldId === it.fieldId }"
                 @click.stop="active = it.fieldId" @dragover="dragQuestion">
              <span class="fv-drag st-icon-action" draggable="true" data-smart-tip="拖动排序" @dragstart.stop="startFieldDrag($event, it.fieldId, true)" @dragend.stop="endFieldDrag">
                <StIcon name="drag" :size="14" /></span>
              <template v-if="active === it.fieldId">
                <input :value="it.title || it.field.label" class="fv-q-title-in" @click.stop
                       @change="(e) => patchItem(i, { title: e.target.value === it.field.label ? null : e.target.value })" />
                <input :value="it.description || ''" class="fv-q-desc-in" placeholder="添加问题描述" @click.stop
                       @change="(e) => patchItem(i, { description: e.target.value || null })" />
                <!-- 选项编辑（与表格列共享数据源） -->
                <div v-if="isSelect(it.field) && !isRefOptions(it.field)" class="fv-opts" @click.stop>
                  <div v-for="(o, oi) in it.field.options?.options || []" :key="o.id" class="fv-opt" :class="{ over: optOver === oi }"
                       @dragover="dragOption($event, oi)" @dragleave="optOver = null" @drop="onOptionDrop($event, it.field, oi)">
                    <span class="fv-opt-drag st-icon-action" draggable="true" @dragstart.stop="optFrom = oi" @dragend.stop="optFrom = null; optOver = null"><StIcon name="drag" :size="12" /></span>
                    <span class="fv-opt-color" :style="{ background: optionColor(o.color).value }" data-smart-tip="切换颜色" @click="cycleColor(it.field, oi)" />
                    <input :value="o.label" class="fv-opt-in" @change="(e) => renameOption(it.field, oi, e.target.value)" />
                    <span class="fv-opt-rm st-icon-action" data-smart-tip="删除选项" @click="removeOption(it.field, oi)"><StIcon name="minus-circle" :size="16" /></span>
                  </div>
                  <a class="fv-opt-add" @click="addOption(it.field)"><StIcon name="plus" :size="14" />添加选项</a>
                  <div class="fv-opt-tip">此处修改将影响表格列</div>
                </div>
                <FormControl v-else :item="it" preview />
                <!-- 底部属性条 -->
                <div class="fv-attrs" @click.stop>
                  <span class="fv-attr-l">字段</span>
                  <el-select :model-value="it.fieldId" size="small" class="fv-attr-field" :teleported="false"
                             @update:model-value="(fn) => rebind(i, fn)">
                    <template #prefix><StIcon :name="fieldIconName(it.field)" :size="13" /></template>
                    <el-option :value="it.fieldId" :label="it.field.label" />
                    <el-option v-for="f in availableFields" :key="f.field_name" :value="f.field_name" :label="f.label" />
                  </el-select>
                  <template v-if="it.field.field_type === 'singleSelect'">
                    <span class="fv-attr-sep" />
                    <el-select :model-value="it.widget || 'inline'" size="small" class="fv-attr-widget" :teleported="false"
                               @update:model-value="(w) => patchItem(i, { widget: w })">
                      <el-option value="inline" label="平铺" /><el-option value="dropdown" label="下拉" />
                    </el-select>
                  </template>
                  <span class="fv-attr-sp" />
                  <el-checkbox :model-value="!!it.required" :disabled="it.field.readonly" @update:model-value="(v) => patchItem(i, { required: v })">必填</el-checkbox>
                  <span class="fv-attr-sep" />
                  <el-tooltip v-if="i === 0" content="表单的首个问题不支持设置显示条件" placement="top">
                    <span class="fv-attr-btn disabled" aria-disabled="true"><StIcon name="group" :size="14" />显示条件</span>
                  </el-tooltip>
                  <el-popover v-else trigger="click" placement="bottom-start" :width="612" :popper-style="{ maxWidth: 'calc(100vw - 32px)' }" popper-class="st-pop fv-condition-pop">
                    <template #reference>
                      <span class="fv-attr-btn" :class="{ on: it.visibility?.conditions?.length }"><StIcon name="group" :size="14" />显示条件{{ it.visibility?.conditions?.length ? ` ${it.visibility.conditions.length}` : '' }}</span>
                    </template>
                    <div class="fv-vis">
                      <div v-if="!it.visibility?.conditions?.length" class="fv-vis-t">仅在满足以下条件时显示</div>
                      <div v-else class="fv-vis-t">仅在满足以下
                        <el-select :model-value="it.visibility?.match || 'all'" size="small" class="fv-vis-match" :teleported="false"
                                   @update:model-value="(m) => patchVis(i, { match: m })">
                          <el-option value="all" label="所有" /><el-option value="any" label="任一" />
                        </el-select>条件时显示</div>
                      <PermCondRow v-for="(c, ci) in it.visibility?.conditions || []" :key="ci" :cond="c" :fields="otherQuestionFields(it)"
                                   @update="(nc) => setVisCond(i, ci, nc)" @remove="removeVisCond(i, ci)" />
                      <button class="fv-vis-add" :disabled="(it.visibility?.conditions?.length || 0) >= 10"
                              @click.stop="addVisCond(i)"><StIcon name="plus" :size="15" />添加显示条件</button>
                    </div>
                  </el-popover>
                  <span class="fv-attr-sep" />
                  <el-tooltip content="移出" placement="top">
                    <span class="fv-attr-btn st-icon-action" aria-label="移出表单" @click="removeItem(i)"><StIcon name="minus-circle" :size="16" /></span>
                  </el-tooltip>
                  <span class="fv-attr-sep" />
                  <el-tooltip content="编辑字段" placement="top">
                    <button class="fv-attr-btn fv-attr-icon st-icon-action" aria-label="编辑字段" :disabled="!canManage"
                            @click="editField(it.field, $event)"><StIcon name="pencil" :size="16" /></button>
                  </el-tooltip>
                  <span class="fv-attr-sep" />
                  <el-tooltip content="删除字段" placement="top">
                    <button class="fv-attr-btn fv-attr-icon danger st-icon-action" aria-label="删除字段" :disabled="!canManage"
                            @click="emit('delete-field', it.field)"><StIcon name="trash" :size="16" /></button>
                  </el-tooltip>
                </div>
              </template>
              <template v-else>
                <div class="fv-q-title"><span v-if="it.required" class="fv-req">*</span>{{ it.title || it.field.label }}
                  <span v-if="it.visibility?.conditions?.length" class="fv-q-vis">有显示条件</span></div>
                <div v-if="it.description" class="fv-q-desc">{{ it.description }}</div>
                <FormControl :item="it" preview />
              </template>
            </div>
            </template>
            <div v-if="itemsWithField.length && dragItem && dropIndex === itemsWithField.length" class="fv-drop-placeholder" :style="{ height: `${dragHeight}px` }"
                 @dragover.prevent.stop="dragPlaceholder($event, itemsWithField.length)" @drop.prevent.stop="dropField" />
            <div v-if="!itemsWithField.length" class="fv-empty" :class="{ 'drop-active': dragItem && dropIndex === 0 }">
              <span>拖动字段到此或<button @click.stop="(e) => emit('add-field', e)">新建字段</button></span>
            </div>
            <div class="fv-add-wrap"><span class="fv-add-btn" @click.stop="(e) => emit('add-field', e)"><StIcon name="plus-circle" :size="15" />添加新字段</span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ========== 填写态 ========== -->
    <div v-else class="fv-fill">
      <FormFill ref="fillRef" :def="fillDef" :cover-src="coverSrc" :uploader="upload"
                :members="members" :submitting="submitting" @submit="submit" />
    </div>
    <FormCoverPicker v-model="coverPicker" :cover="form.cover" @select="cover => setForm({ cover })" />
  </div>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import PermCondRow from '../perms/PermCondRow.vue'
import FormControl from './FormControl.vue'
import FormFill from './FormFill.vue'
import FormShare from './FormShare.vue'
import FormCoverPicker from './FormCoverPicker.vue'
import { presetCoverUrl } from './covers.js'
import { normalizeVisibility } from './formLogic.js'
import { OPTION_COLORS, optionColor } from '../../../smart/registry/fieldRegistry.js'
import { imageUrl, smartSubmitForm,
         smartUploadFile, uploadImageFile } from '../../../api/index.js'

const props = defineProps({
  view: { type: Object, required: true },
  fields: { type: Array, default: () => [] },
  tableId: Number,
  tableName: { type: String, default: '' },
  members: { type: Array, default: () => [] },
  canManage: { type: Boolean, default: true },
})
const emit = defineEmits(['save', 'add-field', 'update-options', 'edit-field', 'delete-field', 'open-automation', 'submitted'])

const SYSTEM = ['createdBy', 'lastModifiedBy', 'createdTime', 'lastModifiedTime']
const READONLY = ['formula', 'lookup', 'autoNumber', 'ai']
const tab = ref('edit')
const active = ref(null)
const form = reactive({ title: '', description: '', cover: null, items: [], submit: {} })
const hist = reactive({ past: [], future: [] })
let saveTimer = null

function loadFromView() {
  const f = props.view?.config?.form || {}
  Object.assign(form, { title: f.title || props.view?.name || '表单', description: f.description || '', cover: f.cover || null,
                        items: JSON.parse(JSON.stringify(f.items || [])), submit: f.submit || {} })
  form.items = normalizeVisibility(form.items.filter(it => props.fields.some(f => f.field_name === it.fieldId)))
}
watch(() => props.view?.id, () => { loadFromView(); hist.past = []; hist.future = [] }, { immediate: true })
// 外部（如「添加新字段到表单」）更新了视图 config 时同步（本地无待保存改动才同步）
watch(() => props.view?.config?.form, () => { if (!saveTimer) loadFromView() })

const fieldMap = computed(() => new Map(props.fields.map(f => [f.field_name, f])))
const itemsWithField = computed(() => form.items.filter(it => fieldMap.value.has(it.fieldId)).map(it => {
  const f = fieldMap.value.get(it.fieldId)
  return { ...it, field: { ...f, readonly: READONLY.includes(f.field_type) } }
}))
const availableFields = computed(() => {
  const used = new Set(form.items.map(it => it.fieldId))
  return props.fields.filter(f => !used.has(f.field_name) && !SYSTEM.includes(f.field_type))
})
const fillDef = computed(() => ({ title: form.title, description: form.description, items: itemsWithField.value }))

function snapshot() { return JSON.stringify({ title: form.title, description: form.description, cover: form.cover, items: form.items }) }
function commit(mutator) {
  hist.past.push(snapshot())
  if (hist.past.length > 50) hist.past.shift()
  hist.future = []
  mutator()
  form.items = normalizeVisibility(form.items)
  scheduleSave()
}
function scheduleSave() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    emit('save', { title: form.title, description: form.description, cover: form.cover, items: form.items, submit: form.submit })
  }, 400)
}
function restore(snap) { Object.assign(form, JSON.parse(snap)); form.items = normalizeVisibility(form.items); scheduleSave() }
function undo() { if (!hist.past.length) return; hist.future.push(snapshot()); restore(hist.past.pop()) }
function redo() { if (!hist.future.length) return; hist.past.push(snapshot()); restore(hist.future.pop()) }

function setForm(obj) { commit(() => Object.assign(form, obj)) }
function editField(field, event) {
  const rect = event.currentTarget.getBoundingClientRect()
  emit('edit-field', field, { x: rect.left, y: rect.bottom, top: rect.top, bottom: rect.bottom, placement: 'button' })
}
function addItem(fn) {
  if (!availableFields.value.some(f => f.field_name === fn)) return
  commit(() => form.items.push({ fieldId: fn, required: false }))
  revealQuestion(fn)
}
function addAll() {
  const fields = availableFields.value
  if (!fields.length) return
  commit(() => form.items.push(...fields.map(f => ({ fieldId: f.field_name, required: false }))))
  revealQuestion(fields[0].field_name)
}
function removeItem(i) { commit(() => form.items.splice(i, 1)); active.value = null }
function removeAll() { if (form.items.length) commit(() => { form.items = [] }); active.value = null }
function patchItem(i, obj) { commit(() => { form.items[i] = { ...form.items[i], ...obj } }) }
function rebind(i, fn) { if (fn !== form.items[i].fieldId) { patchItem(i, { fieldId: fn, title: null, visibility: null }); active.value = fn } }
function patchVis(i, obj) { if (i > 0) patchItem(i, { visibility: { match: 'all', conditions: [], ...(form.items[i].visibility || {}), ...obj } }) }
function addVisCond(i) {
  const previous = form.items[i - 1]
  const conditions = form.items[i]?.visibility?.conditions || []
  if (!previous || conditions.length >= 10) return
  // 后台会清理没有 fieldId 的条件；直接添加有效默认条件，避免保存回显时消失。
  patchVis(i, { conditions: [...conditions, { fieldId: previous.fieldId, operator: 'isNotEmpty' }] })
}
function setVisCond(i, ci, c) { const l = [...(form.items[i].visibility?.conditions || [])]; l[ci] = c; patchVis(i, { conditions: l }) }
function removeVisCond(i, ci) { patchVis(i, { conditions: form.items[i].visibility.conditions.filter((_, j) => j !== ci) }) }
function otherQuestionFields(it) { return itemsWithField.value.slice(0, itemsWithField.value.findIndex(x => x.fieldId === it.fieldId)).map(x => x.field) }

// 题目拖拽排序
const canvasRef = ref(null)
const dragItem = ref(null)
const dropIndex = ref(null)
const dragHeight = ref(100)
let scrollFrame = 0
let dragPoint = null
async function revealQuestion(fn) {
  active.value = fn
  await nextTick()
  const card = [...(canvasRef.value?.querySelectorAll('.fv-q') || [])].find(el => el.dataset.fieldId === fn)
  card?.scrollIntoView({ block: 'nearest', behavior: 'auto' })
}
function startFieldDrag(event, fieldId, existing = false) {
  dragItem.value = { fieldId, existing }
  dropIndex.value = null
  const card = event.target.closest('.fv-q')
  dragHeight.value = existing ? Math.min(300, card?.offsetHeight || 174) : 100
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = existing ? 'move' : 'copy'
    event.dataTransfer.setData('text/plain', fieldId)
    if (card) event.dataTransfer.setDragImage(card, 24, 24)
  }
}
function endFieldDrag() {
  dragItem.value = null
  dropIndex.value = null
  dragPoint = null
  cancelAnimationFrame(scrollFrame)
  scrollFrame = 0
}
function trackDrag(event) {
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = dragItem.value.existing ? 'move' : 'copy'
  dragPoint = { x: event.clientX, y: event.clientY }
  if (!scrollFrame) scrollFrame = requestAnimationFrame(scrollDrag)
}
function scrollDrag() {
  scrollFrame = 0
  const canvas = canvasRef.value
  if (!dragItem.value || !dragPoint || !canvas) return
  const rect = canvas.getBoundingClientRect()
  const y = dragPoint.y
  const speed = y < rect.top + 56 ? -12 : y > rect.bottom - 56 ? 12 : 0
  if (speed) {
    canvas.scrollTop += speed
    const target = document.elementFromPoint(dragPoint.x, y)
    const card = target?.closest('.fv-q')
    if (card && canvas.contains(card)) setDropAtCard(card, y)
  }
  scrollFrame = requestAnimationFrame(scrollDrag)
}
function setDropAtCard(card, y) {
  const index = itemsWithField.value.findIndex(it => it.fieldId === card.dataset.fieldId)
  const rect = card.getBoundingClientRect()
  dropIndex.value = index + (y >= rect.top + rect.height / 2 ? 1 : 0)
}
function dragQuestion(event) {
  if (!dragItem.value) return
  event.stopPropagation()
  trackDrag(event)
  setDropAtCard(event.currentTarget, event.clientY)
}
function dragPlaceholder(event, index) {
  if (!dragItem.value) return
  trackDrag(event)
  dropIndex.value = index
}
function dragCanvas(event) {
  if (!dragItem.value) return
  trackDrag(event)
  const cards = [...canvasRef.value.querySelectorAll('.fv-q')]
  dropIndex.value = cards.findIndex(card => event.clientY < card.getBoundingClientRect().top)
  if (dropIndex.value < 0) dropIndex.value = cards.length
}
function leaveCanvas(event) {
  if (event.relatedTarget && canvasRef.value?.contains(event.relatedTarget)) return
  const rect = canvasRef.value?.getBoundingClientRect()
  // 新占位框替换鼠标下的节点时，浏览器也会触发 relatedTarget=null 的 dragleave。
  if (rect && event.clientX >= rect.left && event.clientX <= rect.right &&
      event.clientY >= rect.top && event.clientY <= rect.bottom) return
  dropIndex.value = null
  dragPoint = null
  cancelAnimationFrame(scrollFrame)
  scrollFrame = 0
}
function dropField() {
  const item = dragItem.value
  const target = dropIndex.value
  endFieldDrag()
  if (!item || target == null) return
  if (item.existing) {
    const from = form.items.findIndex(it => it.fieldId === item.fieldId)
    if (from < 0) return
    const to = target > from ? target - 1 : target
    if (to !== from) commit(() => {
      const [question] = form.items.splice(from, 1)
      form.items.splice(to, 0, question)
    })
  } else {
    if (!availableFields.value.some(f => f.field_name === item.fieldId)) return
    commit(() => form.items.splice(target, 0, { fieldId: item.fieldId, required: false }))
  }
  revealQuestion(item.fieldId)
}
onBeforeUnmount(endFieldDrag)

// ---------- 选项编辑（改字段级选项，与表格共享） ----------
const isSelect = (f) => ['singleSelect', 'multiSelect'].includes(f.field_type)
const isRefOptions = (f) => f.options?.optionSource === 'reference'
const optFrom = ref(null)
const optOver = ref(null)
function emitOptions(f, opts) { emit('update-options', f, opts.map((o, i) => ({ ...o, order: i }))) }
function addOption(f) {
  const opts = [...(f.options?.options || [])]
  opts.push({ id: `opt_${Date.now()}`, label: `选项${opts.length + 1}`, color: OPTION_COLORS[opts.length % OPTION_COLORS.length].key })
  emitOptions(f, opts)
}
function renameOption(f, oi, label) {
  if (!label.trim()) return
  const opts = [...f.options.options]; opts[oi] = { ...opts[oi], label: label.trim() }
  emitOptions(f, opts)
}
function cycleColor(f, oi) {
  const opts = [...f.options.options]
  const idx = OPTION_COLORS.findIndex(c => c.key === opts[oi].color)
  opts[oi] = { ...opts[oi], color: OPTION_COLORS[(idx + 1) % OPTION_COLORS.length].key }
  emitOptions(f, opts)
}
async function removeOption(f, oi) {
  await ElMessageBox.confirm(`删除选项「${f.options.options[oi].label}」？表格中已选该选项的单元格将变为空。`, '删除选项', { type: 'warning' })
  emitOptions(f, f.options.options.filter((_, j) => j !== oi))
}
function dropOption(f, to) {
  const from = optFrom.value
  optOver.value = null
  optFrom.value = null
  if (from == null || from === to) return
  const opts = [...f.options.options]
  const [m] = opts.splice(from, 1)
  opts.splice(to, 0, m)
  emitOptions(f, opts)
}
function dragOption(event, index) {
  if (optFrom.value == null || dragItem.value) return
  event.preventDefault()
  event.stopPropagation()
  optOver.value = index
}
function onOptionDrop(event, field, index) {
  if (optFrom.value == null || dragItem.value) return
  event.preventDefault()
  event.stopPropagation()
  dropOption(field, index)
}

// ---------- 封面 ----------
const coverPicker = ref(false)
const coverMenu = ref(false)
const coverSrc = computed(() => presetCoverUrl(form.cover) || (form.cover ? imageUrl(form.cover) : ''))

// ---------- 填写 ----------
const submitting = ref(false)
const fillRef = ref(null)
async function upload(file, kind) {
  if (kind === 'image') {
    const r = await uploadImageFile(file)
    return { id: r.files?.[0]?.id, name: file.name }
  }
  return smartUploadFile(props.tableId, file)
}
async function submit(data, reset) {
  submitting.value = true
  try {
    await smartSubmitForm(props.view.id, data)
    ElMessage.success((form.submit?.successText) || '提交成功')
    reset()
    emit('submitted')
  } catch (e) {
    ElMessage.error(e.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

defineExpose({ addItem })
</script>

<style scoped>
.fv { display: flex; flex-direction: column; flex: 1; min-height: 0; background: var(--st-bg-canvas); }
.fv-bar { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; height: 46px; padding: 0 12px; background: #F7F8F8; border-bottom: 1px solid var(--st-border); }
.fv-bar-l { display: flex; align-items: center; gap: 4px; }
.fv-bar-r { display: flex; justify-content: flex-end; }
.fv-ico { width: 28px; height: 28px; border: none; background: transparent; border-radius: 6px; cursor: pointer; color: var(--st-text-2); display: inline-flex; align-items: center; justify-content: center; }
.fv-ico:hover:not(:disabled) { background: var(--st-bg-hover); }
.fv-ico:disabled { color: var(--st-disabled); cursor: not-allowed; }
.fv-sep { width: 1px; height: 16px; background: var(--st-border); margin: 0 6px; }
.fv-tool { display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 8px; border: none; background: transparent; border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--st-text-1); }
.fv-tool:hover:not(:disabled) { background: var(--st-bg-hover); }
.fv-tool:disabled { color: var(--st-disabled); cursor: not-allowed; }
.fv-tabs { display: flex; gap: 28px; height: 100%; }
.fv-tab { display: flex; align-items: center; font-size: 14px; color: var(--st-text-1); cursor: pointer; border-bottom: 3px solid transparent; padding-top: 3px; }
.fv-tab.on { border-bottom-color: var(--st-primary); color: var(--st-text-1); font-weight: 500; }
.fv-main { flex: 1; display: flex; min-height: 0; }
.fv-left { width: 260px; box-sizing: border-box; flex: none; display: flex; flex-direction: column; min-height: 0; background: #F9FAFA; border-right: 1px solid var(--st-border); padding: 16px 10px 12px; }
.fv-left-head { display: flex; align-items: center; justify-content: space-between; gap: 6px; flex: none; font-size: 13px; color: var(--st-text-1); margin: 0 6px 12px; }
.fv-left-actions { display: flex; gap: 8px; }
.fv-link-g { padding: 0; border: 0; background: transparent; color: var(--st-text-2); cursor: pointer; font-size: 12px; white-space: nowrap; }
.fv-link-g:hover:not(:disabled) { color: var(--st-primary); }
.fv-link-g:disabled { color: var(--st-disabled); cursor: default; }
.fv-field-list { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: thin; padding-right: 6px; }
.fv-avail-empty { border: 1px dashed #D8DADD; border-radius: 6px; padding: 26px 0; text-align: center; font-size: 12px; color: var(--st-text-2); margin-bottom: 10px; }
.fv-avail { display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid transparent; border-radius: 4px; padding: 8px 10px; margin-bottom: 6px; font-size: 13px; cursor: grab; user-select: none; }
.fv-avail:active { cursor: grabbing; }
.fv-avail.dragging,.fv-q.dragging { opacity: .4; }
.fv-avail:hover { border-color: var(--st-primary); }
.fv-avail .st-icon { color: var(--st-text-2); }
.fv-avail-plus { margin-left: auto; color: var(--st-text-3) !important; }
.fv-add-new { display: flex; flex: none; align-items: center; gap: 8px; background: #fff; border-radius: 6px; padding: 10px 12px; font-size: 13px; color: var(--st-primary); cursor: pointer; margin-top: 12px; }
.fv-add-new .st-icon { color: var(--st-primary); }
.fv-add-caret { margin-left: auto; }
.fv-canvas { flex: 1; overflow: auto; padding: 36px 24px 60px; background: #EFF0F1; }
.fv-paper-wrap { max-width: 780px; margin: 0 auto; background: #F6F7F7; border-radius: 16px; padding: 0 24px 24px; }
.fv-cover-bar { display: flex; align-items: center; justify-content: center; height: 48px; position: relative; }
.has-cover .fv-cover-bar { height: 170px; margin: 0 -24px; }
.fv-cover-img { width: 100%; height: 170px; object-fit: cover; border-radius: 16px 16px 0 0; display: block; }
.fv-cover-btn { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 12px; border: 0; border-radius: 4px; background: #E9EBEC; font-size: 13px; color: var(--st-text-1); cursor: pointer; }
.fv-cover-btn:hover { background: #E0E3E5; }
.fv-cover-more { position: absolute; right: 16px; top: 16px; display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 0; border-radius: 4px; background: #ffffff55; color: #30343B; cursor: pointer; }
.fv-cover-menu { display: flex; flex-direction: column; gap: 2px; }
.fv-cover-menu button { height: 32px; text-align: left; padding: 0 10px; border: 0; border-radius: 4px; background: transparent; color: #30343B; cursor: pointer; }
.fv-cover-menu button:hover { background: #E6E8E8; }
.has-cover .fv-paper { position: relative; margin-top: -44px; }
.fv-hidden { display: none; }
.fv-paper { background: #fff; border-radius: 10px; padding: 32px 46px 40px; }
.fv-title { width: 100%; border: none; outline: none; font-size: 20px; font-weight: 700; color: var(--st-text-1); padding: 4px 0; }
.fv-desc { width: 100%; border: none; outline: none; font-size: 14px; color: var(--st-text-2); padding: 8px 0; }
.fv-desc::placeholder, .fv-q-desc-in::placeholder { color: var(--st-text-4); }
.fv-line { height: 1px; background: var(--st-border); margin: 16px 0 18px; }
.fv-q { position: relative; padding: 16px 34px 18px; margin: 4px -18px; border: 1px solid var(--st-border); border-radius: 4px; cursor: pointer; }
.fv-q:hover { border-color: var(--st-border); }
.fv-q.active { border-color: var(--st-primary); box-shadow: 0 0 0 1px var(--st-primary); cursor: default; padding-bottom: 0; }
.fv-drop-placeholder { box-sizing: border-box; margin: 4px -18px; border: 1px solid var(--st-primary); border-radius: 4px; background: #DCEBFC; }
.fv-q :deep(.fc.preview .fc-ph) { box-sizing: border-box; min-height: 32px; padding: 6px 8px; line-height: 18px; border-color: #DADDE0; background: #F7F7F7; font-size: 13px; color: var(--st-text-3); }
.fv-drag { position: absolute; left: 10px; top: 18px; color: var(--st-text-3); cursor: grab; display: inline-flex; }
.fv-q:hover .fv-drag, .fv-q.active .fv-drag { display: inline-flex; }
.fv-q-title { font-size: 15px; font-weight: 600; color: var(--st-text-1); margin-bottom: 12px; display: flex; align-items: center; gap: 4px; }
.fv-req { color: var(--el-color-danger); }
.fv-q-vis { font-size: 11px; font-weight: 400; color: var(--st-primary); background: var(--st-primary-weak); border-radius: 3px; padding: 0 5px; margin-left: 6px; }
.fv-q-desc { font-size: 13px; color: var(--st-text-3); margin: -6px 0 10px; }
.fv-q-title-in { width: 100%; border: none; outline: none; font-size: 15px; font-weight: 600; padding: 0 0 8px; }
.fv-q-desc-in { width: 100%; border: none; outline: none; font-size: 14px; color: var(--st-text-2); padding: 4px 0 12px; }
.fv-opts { max-height: 260px; overflow: auto; padding-bottom: 6px; scrollbar-width: thin; }
.fv-opt { display: flex; align-items: center; gap: 10px; padding: 4px 6px; border-radius: 4px; }
.fv-opt.over { border-top: 2px solid var(--st-primary); }
.fv-opt-drag { color: var(--st-text-4); cursor: grab; display: inline-flex; }
.fv-opt-color { width: 20px; height: 20px; border-radius: 4px; cursor: pointer; flex: none; }
.fv-opt-in { flex: 1; border: none; outline: none; font-size: 15px; padding: 4px 0; color: var(--st-text-1); }
.fv-opt-rm { color: var(--st-text-4); cursor: pointer; display: inline-flex; }
.fv-opt-rm:hover { color: var(--el-color-danger); }
.fv-opt-add { display: inline-flex; align-items: center; gap: 6px; color: var(--st-primary); cursor: pointer; font-size: 15px; padding: 8px 6px; }
.fv-opt-tip { font-size: 12px; color: var(--st-text-4); padding: 0 6px; }
.fv-attrs { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 46px; box-sizing: border-box; margin: 16px -34px 0; padding: 8px 24px; background: #ECEDEE; border-top: 1px solid var(--st-border); border-radius: 0 0 3px 3px; font-size: 13px; }
.fv-attr-l { color: var(--st-text-2); }
.fv-attr-field { width: 100px; }
.fv-attr-widget { width: 66px; }
.fv-attr-sp { flex: 1; }
.fv-attr-sep { width: 1px; height: 14px; background: #D5D7DA; }
.fv-attr-btn { display: inline-flex; align-items: center; gap: 4px; color: var(--st-text-2); cursor: pointer; }
.fv-attr-btn:hover, .fv-attr-btn.on { color: var(--st-primary); }
.fv-attr-btn.disabled, .fv-attr-btn.disabled:hover { color: #B7BCC3; cursor: not-allowed; }
.fv-attr-btn.on { background: #DDE0E4; border-radius: 3px; }
.fv-attr-icon { border: 0; background: transparent; padding: 3px; border-radius: 3px; }
.fv-attr-icon:hover:not(:disabled) { background: #DDE0E4; }
.fv-attr-icon.danger:hover:not(:disabled) { color: var(--el-color-danger); }
.fv-attr-icon:disabled { color: var(--st-disabled); cursor: not-allowed; }
.fv-vis { display: flex; flex-direction: column; gap: 18px; padding: 8px 12px 12px; }
.fv-vis-t { display: flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 600; color: var(--st-text-1); }
.fv-vis-match { width: 80px; }
.fv-vis-add { display: inline-flex; align-self: flex-start; align-items: center; gap: 6px; padding: 7px 12px; border: 0; border-radius: 4px; background: #F2F3F5; color: var(--st-text-1); cursor: pointer; font-size: 13px; }
.fv-vis-add:hover { background: #E8EAED; }
.fv-vis-add:disabled { color: var(--st-disabled); cursor: not-allowed; }
.fv-empty { display: flex; align-items: center; justify-content: center; min-height: 90px; box-sizing: border-box; border: 2px dashed #E2E5E8; margin: 4px -18px; color: var(--st-text-2); font-size: 13px; }
.fv-empty button { border: 0; padding: 0; background: transparent; color: var(--st-primary); cursor: pointer; font: inherit; }
.fv-empty.drop-active { border: 1px solid var(--st-primary); border-radius: 4px; background: #DCEBFC; }
.fv-empty.drop-active > span { visibility: hidden; }
.fv-add-wrap { display: flex; justify-content: center; margin-top: 28px; }
.fv-add-btn { display: inline-flex; align-items: center; gap: 6px; background: #F2F3F5; border-radius: 6px; padding: 9px 22px; color: var(--st-primary); font-size: 14px; cursor: pointer; }
.fv-add-btn:hover { background: #E8EAED; }
.fv-fill { flex: 1; overflow: auto; padding: 36px 24px 60px; background: #EFF0F1; }
</style>
