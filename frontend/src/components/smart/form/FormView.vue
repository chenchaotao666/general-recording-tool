<template>
  <!-- 表单视图（§12，对齐参照 右上角工具栏-生成表单-编辑(2).png / 新建-收集表单 编辑界面）：
       顶部工具条：↶ ↷ ｜ ⏱ 设置自动化提醒 ｜ 居中「编辑表单 | 填写表单」｜ 右侧分享
       编辑态：左侧「可添加字段」面板 + 中央画布（封面/标题/描述/题目卡片/添加新字段） -->
  <div class="fv">
    <div class="fv-bar">
      <div class="fv-bar-l">
        <button class="fv-ico" title="撤销" :disabled="!hist.past.length" @click="undo"><StIcon name="undo" :size="16" /></button>
        <button class="fv-ico" title="重做" :disabled="!hist.future.length" @click="redo"><StIcon name="redo" :size="16" /></button>
        <span class="fv-sep" />
        <button class="fv-tool" @click="emit('open-automation')"><StIcon name="automation" :size="15" />设置自动化提醒</button>
      </div>
      <div class="fv-tabs">
        <span class="fv-tab" :class="{ on: tab === 'edit' }" @click="tab = 'edit'">编辑表单</span>
        <span class="fv-tab" :class="{ on: tab === 'fill' }" @click="tab = 'fill'">填写表单</span>
      </div>
      <div class="fv-bar-r">
        <el-popover v-model:visible="share.visible" trigger="click" placement="bottom-end" :width="380" popper-class="st-pop">
          <template #reference>
            <button class="fv-tool" :disabled="!canManage" @click="loadLink"><StIcon name="share" :size="15" />分享</button>
          </template>
          <div class="fv-share">
            <div class="fv-share-t">公开填写</div>
            <div class="fv-share-d">任何拿到链接的人都可以填写表单，提交的数据进入「{{ tableName }}」。</div>
            <template v-if="share.link">
              <div class="fv-share-url"><el-input :model-value="linkUrl" readonly size="small" />
                <el-button size="small" type="primary" @click="copyLink">复制</el-button></div>
              <div class="fv-share-row">
                <el-input v-model="share.password" size="small" placeholder="访问密码（可选，至少 4 位）" show-password />
                <el-button size="small" @click="saveLink">{{ share.link.has_password ? '更新密码' : '设置密码' }}</el-button>
              </div>
              <a class="fv-share-off" @click="closeLink">关闭公开链接</a>
            </template>
            <el-button v-else type="primary" size="small" :loading="share.loading" @click="saveLink">开启公开填写链接</el-button>
          </div>
        </el-popover>
      </div>
    </div>

    <!-- ========== 编辑态 ========== -->
    <div v-if="tab === 'edit'" class="fv-main">
      <div class="fv-left">
        <div class="fv-left-head"><span>可添加字段</span><a class="fv-link-g" :class="{ off: !form.items.length }" @click="removeAll">全部移出</a></div>
        <div v-if="!availableFields.length" class="fv-avail-empty">所有字段都已添加至表单</div>
        <div v-for="f in availableFields" :key="f.field_name" class="fv-avail" title="点击添加到表单" @click="addItem(f.field_name)">
          <StIcon :name="fieldIconName(f)" :size="14" />{{ f.label }}<StIcon name="plus" :size="13" class="fv-avail-plus" />
        </div>
        <div class="fv-add-new" @click="(e) => emit('add-field', e)">
          <StIcon name="plus-circle" :size="16" />添加新字段到表单<StIcon name="chevron-right" :size="13" class="fv-add-caret" />
        </div>
      </div>
      <div class="fv-canvas" @click="active = null">
        <div class="fv-paper-wrap">
          <div class="fv-cover-bar">
            <img v-if="form.cover" :src="imageUrl(form.cover)" class="fv-cover-img" alt="" />
            <span class="fv-cover-btn" @click.stop="pickCover"><StIcon name="image" :size="15" />{{ form.cover ? '更换封面' : '添加封面' }}</span>
            <span v-if="form.cover" class="fv-cover-btn" @click.stop="setForm({ cover: null })">移除封面</span>
            <input ref="coverRef" type="file" accept="image/*" class="fv-hidden" @change="onCover" />
          </div>
          <div class="fv-paper">
            <input :value="form.title" class="fv-title" placeholder="表单标题" @change="(e) => setForm({ title: e.target.value })" />
            <input :value="form.description" class="fv-desc" placeholder="添加描述" @change="(e) => setForm({ description: e.target.value })" />
            <div class="fv-line" />

            <div v-for="(it, i) in itemsWithField" :key="it.fieldId" class="fv-q" :class="{ active: active === it.fieldId, over: dragOver === i }"
                 @click.stop="active = it.fieldId" @dragover.prevent="dragOver = i" @dragleave="dragOver = null" @drop="onDrop(i)">
              <span class="fv-drag" draggable="true" title="拖动排序" @dragstart="dragFrom = i" @dragend="dragOver = null">
                <StIcon name="drag" :size="14" /></span>
              <template v-if="active === it.fieldId">
                <input :value="it.title || it.field.label" class="fv-q-title-in" @click.stop
                       @change="(e) => patchItem(i, { title: e.target.value === it.field.label ? null : e.target.value })" />
                <input :value="it.description || ''" class="fv-q-desc-in" placeholder="添加问题描述" @click.stop
                       @change="(e) => patchItem(i, { description: e.target.value || null })" />
                <!-- 选项编辑（与表格列共享数据源） -->
                <div v-if="isSelect(it.field) && !isRefOptions(it.field)" class="fv-opts" @click.stop>
                  <div v-for="(o, oi) in it.field.options?.options || []" :key="o.id" class="fv-opt" :class="{ over: optOver === oi }"
                       @dragover.prevent="optOver = oi" @dragleave="optOver = null" @drop.stop="dropOption(it.field, oi)">
                    <span class="fv-opt-drag" draggable="true" @dragstart="optFrom = oi"><StIcon name="drag" :size="12" /></span>
                    <span class="fv-opt-color" :style="{ background: optionColor(o.color).value }" title="切换颜色" @click="cycleColor(it.field, oi)" />
                    <input :value="o.label" class="fv-opt-in" @change="(e) => renameOption(it.field, oi, e.target.value)" />
                    <span class="fv-opt-rm" title="删除选项" @click="removeOption(it.field, oi)"><StIcon name="minus-circle" :size="16" /></span>
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
                  <el-popover trigger="click" placement="top" :width="520" popper-class="st-pop">
                    <template #reference>
                      <span class="fv-attr-btn" :class="{ on: it.visibility?.conditions?.length }"><StIcon name="group" :size="14" />显示条件{{ it.visibility?.conditions?.length ? ` ${it.visibility.conditions.length}` : '' }}</span>
                    </template>
                    <div class="fv-vis">
                      <div class="fv-vis-t">满足以下
                        <el-select :model-value="it.visibility?.match || 'all'" size="small" class="fv-vis-match" :teleported="false"
                                   @update:model-value="(m) => patchVis(i, { match: m })">
                          <el-option value="all" label="所有" /><el-option value="any" label="任一" />
                        </el-select>条件时显示此题</div>
                      <PermCondRow v-for="(c, ci) in it.visibility?.conditions || []" :key="ci" :cond="c" :fields="otherQuestionFields(it)"
                                   @update="(nc) => setVisCond(i, ci, nc)" @remove="removeVisCond(i, ci)" />
                      <a class="fv-vis-add" @click="addVisCond(i)"><StIcon name="plus" :size="13" />添加条件</a>
                    </div>
                  </el-popover>
                  <span class="fv-attr-sep" />
                  <span class="fv-attr-btn" title="移出表单" @click="removeItem(i)"><StIcon name="minus-circle" :size="16" /></span>
                  <span class="fv-attr-sep" />
                  <el-dropdown trigger="click" @command="(c) => c === 'edit' && emit('edit-field', it.field)">
                    <span class="fv-attr-btn"><StIcon name="more-h" :size="16" /></span>
                    <template #dropdown>
                      <el-dropdown-menu><el-dropdown-item command="edit">在表格中修改字段</el-dropdown-item></el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </template>
              <template v-else>
                <div class="fv-q-title"><span v-if="it.required" class="fv-req">*</span>{{ it.title || it.field.label }}
                  <span v-if="it.visibility?.conditions?.length" class="fv-q-vis">有显示条件</span></div>
                <div v-if="it.description" class="fv-q-desc">{{ it.description }}</div>
                <FormControl :item="it" preview />
              </template>
            </div>
            <div v-if="!itemsWithField.length" class="fv-empty">从左侧添加字段，或点击下方添加新字段</div>
            <div class="fv-add-wrap"><span class="fv-add-btn" @click.stop="(e) => emit('add-field', e)"><StIcon name="plus-circle" :size="15" />添加新字段</span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ========== 填写态 ========== -->
    <div v-else class="fv-fill">
      <FormFill ref="fillRef" :def="fillDef" :cover-src="form.cover ? imageUrl(form.cover) : ''" :uploader="upload"
                :members="members" :submitting="submitting" @submit="submit" />
    </div>
  </div>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import PermCondRow from '../perms/PermCondRow.vue'
import FormControl from './FormControl.vue'
import FormFill from './FormFill.vue'
import { OPTION_COLORS, optionColor } from '../../../smart/registry/fieldRegistry.js'
import { imageUrl, smartCreateFormLink, smartDeleteFormLink, smartGetFormLink, smartSubmitForm,
         smartUploadFile, uploadImageFile } from '../../../api/index.js'

const props = defineProps({
  view: { type: Object, required: true },
  fields: { type: Array, default: () => [] },
  tableId: Number,
  tableName: { type: String, default: '' },
  members: { type: Array, default: () => [] },
  canManage: { type: Boolean, default: true },
})
const emit = defineEmits(['save', 'add-field', 'update-options', 'edit-field', 'open-automation', 'submitted'])

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
  scheduleSave()
}
function scheduleSave() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    emit('save', { title: form.title, description: form.description, cover: form.cover, items: form.items, submit: form.submit })
  }, 400)
}
function restore(snap) { Object.assign(form, JSON.parse(snap)); scheduleSave() }
function undo() { if (!hist.past.length) return; hist.future.push(snapshot()); restore(hist.past.pop()) }
function redo() { if (!hist.future.length) return; hist.past.push(snapshot()); restore(hist.future.pop()) }

function setForm(obj) { commit(() => Object.assign(form, obj)) }
function addItem(fn) { commit(() => form.items.push({ fieldId: fn, required: false })); active.value = fn }
function removeItem(i) { commit(() => form.items.splice(i, 1)); active.value = null }
function removeAll() { if (form.items.length) commit(() => { form.items = [] }) }
function patchItem(i, obj) { commit(() => { form.items[i] = { ...form.items[i], ...obj } }) }
function rebind(i, fn) { if (fn !== form.items[i].fieldId) { patchItem(i, { fieldId: fn, title: null, visibility: null }); active.value = fn } }
function patchVis(i, obj) { patchItem(i, { visibility: { match: 'all', conditions: [], ...(form.items[i].visibility || {}), ...obj } }) }
function addVisCond(i) { patchVis(i, { conditions: [...(form.items[i].visibility?.conditions || []), { fieldId: null, operator: 'eq' }] }) }
function setVisCond(i, ci, c) { const l = [...(form.items[i].visibility?.conditions || [])]; l[ci] = c; patchVis(i, { conditions: l }) }
function removeVisCond(i, ci) { patchVis(i, { conditions: form.items[i].visibility.conditions.filter((_, j) => j !== ci) }) }
function otherQuestionFields(it) { return itemsWithField.value.filter(x => x.fieldId !== it.fieldId).map(x => x.field) }

// 题目拖拽排序
const dragFrom = ref(null)
const dragOver = ref(null)
function onDrop(i) {
  const from = dragFrom.value
  dragOver.value = null
  dragFrom.value = null
  if (from == null || from === i) return
  commit(() => { const [m] = form.items.splice(from, 1); form.items.splice(i, 0, m) })
}

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

// ---------- 封面 ----------
const coverRef = ref(null)
function pickCover() { coverRef.value?.click() }
async function onCover(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  try {
    const r = await uploadImageFile(file)
    setForm({ cover: String(r.files?.[0]?.id) })
  } catch (err) {
    ElMessage.error(err.message || '上传失败')
  }
}

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

// ---------- 分享 ----------
const share = reactive({ visible: false, link: null, password: '', loading: false })
const linkUrl = computed(() => (share.link ? `${location.origin}/sf/${share.link.token}` : ''))
async function loadLink() { share.link = (await smartGetFormLink(props.view.id).catch(() => ({ link: null }))).link }
async function saveLink() {
  share.loading = true
  try {
    share.link = (await smartCreateFormLink(props.view.id, share.password ? { password: share.password } : {})).link
    share.password = ''
    ElMessage.success('公开链接已生效')
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    share.loading = false
  }
}
async function closeLink() {
  await smartDeleteFormLink(props.view.id)
  share.link = null
  ElMessage.success('已关闭公开链接')
}
async function copyLink() {
  try { await navigator.clipboard.writeText(linkUrl.value); ElMessage.success('链接已复制') } catch { ElMessage.info(linkUrl.value) }
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
.fv-left { width: 270px; flex: none; background: #F9FAFA; border-right: 1px solid var(--st-border); padding: 16px 14px; overflow: auto; }
.fv-left-head { display: flex; justify-content: space-between; font-size: 13px; color: var(--st-text-1); margin-bottom: 12px; }
.fv-link-g { color: var(--st-text-2); cursor: pointer; font-size: 12px; }
.fv-link-g.off { color: var(--st-disabled); cursor: default; }
.fv-avail-empty { border: 1px dashed #D8DADD; border-radius: 6px; padding: 26px 0; text-align: center; font-size: 12px; color: var(--st-text-2); margin-bottom: 10px; }
.fv-avail { display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid var(--st-border); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; font-size: 13px; cursor: pointer; }
.fv-avail:hover { border-color: var(--st-primary); }
.fv-avail .st-icon { color: var(--st-text-2); }
.fv-avail-plus { margin-left: auto; color: var(--st-text-3) !important; }
.fv-add-new { display: flex; align-items: center; gap: 8px; background: #fff; border-radius: 6px; padding: 10px 12px; font-size: 13px; color: var(--st-primary); cursor: pointer; margin-top: 8px; }
.fv-add-new .st-icon { color: var(--st-primary); }
.fv-add-caret { margin-left: auto; }
.fv-canvas { flex: 1; overflow: auto; padding: 36px 24px 60px; background: #EFF0F1; }
.fv-paper-wrap { max-width: 780px; margin: 0 auto; background: #F6F7F7; border-radius: 16px; padding: 0 18px 18px; }
.fv-cover-bar { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 0; position: relative; }
.fv-cover-img { width: 100%; max-height: 200px; object-fit: cover; border-radius: 10px; }
.fv-cover-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--st-text-1); cursor: pointer; }
.fv-cover-btn:hover { color: var(--st-primary); }
.fv-hidden { display: none; }
.fv-paper { background: #fff; border-radius: 10px; padding: 32px 46px 40px; }
.fv-title { width: 100%; border: none; outline: none; font-size: 20px; font-weight: 700; color: var(--st-text-1); padding: 4px 0; }
.fv-desc { width: 100%; border: none; outline: none; font-size: 14px; color: var(--st-text-2); padding: 8px 0; }
.fv-desc::placeholder, .fv-q-desc-in::placeholder { color: var(--st-text-4); }
.fv-line { height: 1px; background: var(--st-border); margin: 16px 0 18px; }
.fv-q { position: relative; padding: 16px 40px 18px 46px; margin: 0 -46px; border: 1px solid transparent; border-radius: 4px; cursor: pointer; }
.fv-q:hover { border-color: var(--st-border); }
.fv-q.active { border-color: var(--st-primary); cursor: default; padding-bottom: 0; }
.fv-q.over { border-top: 2px solid var(--st-primary); }
.fv-drag { position: absolute; left: 18px; top: 18px; color: var(--st-text-3); cursor: grab; display: none; }
.fv-q:hover .fv-drag, .fv-q.active .fv-drag { display: inline-flex; }
.fv-q-title { font-size: 15px; font-weight: 600; color: var(--st-text-1); margin-bottom: 12px; display: flex; align-items: center; gap: 4px; }
.fv-req { color: var(--el-color-danger); }
.fv-q-vis { font-size: 11px; font-weight: 400; color: var(--st-primary); background: var(--st-primary-weak); border-radius: 3px; padding: 0 5px; margin-left: 6px; }
.fv-q-desc { font-size: 13px; color: var(--st-text-3); margin: -6px 0 10px; }
.fv-q-title-in { width: 100%; border: none; outline: none; font-size: 15px; font-weight: 600; padding: 0 0 8px; }
.fv-q-desc-in { width: 100%; border: none; outline: none; font-size: 14px; color: var(--st-text-2); padding: 4px 0 12px; }
.fv-opts { max-height: 340px; overflow: auto; padding-bottom: 6px; }
.fv-opt { display: flex; align-items: center; gap: 10px; padding: 4px 6px; border-radius: 4px; }
.fv-opt.over { border-top: 2px solid var(--st-primary); }
.fv-opt-drag { color: var(--st-text-4); cursor: grab; display: inline-flex; }
.fv-opt-color { width: 20px; height: 20px; border-radius: 4px; cursor: pointer; flex: none; }
.fv-opt-in { flex: 1; border: none; outline: none; font-size: 15px; padding: 4px 0; color: var(--st-text-1); }
.fv-opt-rm { color: var(--st-text-4); cursor: pointer; display: inline-flex; }
.fv-opt-rm:hover { color: var(--el-color-danger); }
.fv-opt-add { display: inline-flex; align-items: center; gap: 6px; color: var(--st-primary); cursor: pointer; font-size: 15px; padding: 8px 6px; }
.fv-opt-tip { font-size: 12px; color: var(--st-text-4); padding: 0 6px; }
.fv-attrs { display: flex; align-items: center; gap: 10px; margin: 16px -40px 0 -46px; padding: 10px 24px 10px 36px; background: #F2F3F4; border-top: 1px solid var(--st-border); border-radius: 0 0 4px 4px; font-size: 13px; }
.fv-attr-l { color: var(--st-text-2); }
.fv-attr-field { width: 150px; }
.fv-attr-widget { width: 86px; }
.fv-attr-sp { flex: 1; }
.fv-attr-sep { width: 1px; height: 14px; background: #D5D7DA; }
.fv-attr-btn { display: inline-flex; align-items: center; gap: 4px; color: var(--st-text-2); cursor: pointer; }
.fv-attr-btn:hover, .fv-attr-btn.on { color: var(--st-primary); }
.fv-vis { display: flex; flex-direction: column; gap: 10px; }
.fv-vis-t { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.fv-vis-match { width: 80px; }
.fv-vis-add { display: inline-flex; align-items: center; gap: 4px; color: var(--st-primary); cursor: pointer; font-size: 13px; }
.fv-empty { text-align: center; color: var(--st-text-4); font-size: 13px; padding: 30px 0; }
.fv-add-wrap { display: flex; justify-content: center; margin-top: 28px; }
.fv-add-btn { display: inline-flex; align-items: center; gap: 6px; background: #F2F3F5; border-radius: 6px; padding: 9px 22px; color: var(--st-primary); font-size: 14px; cursor: pointer; }
.fv-add-btn:hover { background: #E8EAED; }
.fv-fill { flex: 1; overflow: auto; padding: 36px 24px 60px; background: #EFF0F1; }
.fv-share { display: flex; flex-direction: column; gap: 10px; }
.fv-share-t { font-weight: 600; font-size: 14px; }
.fv-share-d { font-size: 12px; color: var(--st-text-2); }
.fv-share-url, .fv-share-row { display: flex; gap: 6px; }
.fv-share-off { font-size: 12px; color: var(--el-color-danger); cursor: pointer; align-self: flex-start; }
</style>
