<template>
  <span class="image-cell-anchor" :class="{ 'can-preview': selected || opened }" @mousedown.stop @click.stop @dblclick.stop>
    <div v-if="!detail || !current.length" ref="anchor" class="image-cell-trigger" @click="toggle">
      <span class="image-cell-thumbs"><img v-for="(item, index) in current.slice(0, 3)" :key="idOf(item)" :src="src(item)" alt="预览图片" role="button" tabindex="0" @click.stop="preview(index)" @keydown.enter.stop="preview(index)" /><span v-if="current.length > 3">+{{ current.length - 3 }}</span></span>
      <CellDropdown v-if="!readonly" class="image-cell-arrow" overlay :visible="selected || opened" :open="opened" label="展开或收起图片面板" @click="toggle" />
    </div>
    <component :is="detail && current.length ? 'div' : ElPopover" v-if="opened || (detail && current.length)"
               :class="{ 'image-detail-gallery': detail && current.length }"
               v-bind="detail && current.length ? {} : { visible: opened, virtualTriggering: true, virtualRef: anchor, placement: 'bottom-start', width: current.length ? 400 : 480, showArrow: false, popperClass: 'image-cell-pop', persistent: false }">
      <div ref="panel" class="image-upload-panel" tabindex="-1" @mousedown.stop @click.stop @keydown.esc.stop.prevent="close">
        <div class="image-drop-wrap" :class="{ 'has-images': current.length, dragging: dragDepth > 0 }"
            @dragenter.prevent="dragDepth++" @dragover.prevent="onDragOver" @dragleave.prevent="dragDepth = Math.max(0, dragDepth - 1)" @drop.prevent="drop">
          <div v-if="current.length" class="image-gallery">
            <div v-for="(item, index) in current" :key="idOf(item)" class="image-card">
              <div class="image-card-preview">
                <el-image :src="src(item)" fit="contain" :preview-src-list="current.map(src)" :initial-index="index" preview-teleported />
                <div v-if="!readonly" class="image-card-actions">
                  <el-dropdown trigger="click" :disabled="uploading || saving" popper-class="image-item-menu" @command="command => itemCommand(command, item, index)">
                    <button class="image-action" aria-label="图片操作" :disabled="uploading || saving"><el-icon><MoreFilled /></el-icon></button>
                    <template #dropdown><el-dropdown-menu>
                      <el-dropdown-item command="rename" :disabled="!managed(item)">重命名</el-dropdown-item>
                      <el-dropdown-item command="download">下载</el-dropdown-item>
                      <el-dropdown-item command="delete">删除</el-dropdown-item>
                    </el-dropdown-menu></template>
                  </el-dropdown>
                  <button class="image-action" aria-label="删除图片" :disabled="uploading || saving" @click="remove(index)"><el-icon><Close /></el-icon></button>
                </div>
              </div>
              <div v-if="renaming === idOf(item)" class="image-rename-wrap">
                <input v-model="renameDraft" class="image-rename" aria-label="图片名称（不含后缀）" :disabled="saving" :maxlength="255 - renameSuffix.length"
                  @keydown.enter.stop.prevent="saveName(item)" @keydown.esc.stop.prevent="renaming = null" @blur="saveName(item)" />
                <span class="image-rename-suffix">{{ renameSuffix }}</span>
              </div>
              <div v-else class="image-card-name" :data-smart-tip="nameOf(item)">{{ nameOf(item) }}</div>
            </div>
          </div>
          <button v-else class="image-drop-zone" :class="{ dragging: dragDepth > 0, busy: uploading }" :disabled="uploading" @click="choose">
            <template v-if="uploading"><el-icon class="is-loading"><Loading /></el-icon><span>正在上传 {{ completed }} / {{ total }} 张图片</span></template>
            <span v-else>{{ dragDepth ? '松开即可添加图片' : '将图片拖拽至此即可添加' }}</span>
          </button>
          <div v-if="current.length && (uploading || dragDepth)" class="image-gallery-status">{{ uploading ? `正在上传 ${completed} / ${total} 张图片` : '松开即可添加图片' }}</div>
          <div v-if="error" class="image-upload-error" role="alert">{{ error }}</div>
        </div>
        <button v-if="!readonly" class="image-local-upload" :disabled="uploading" @click="choose"><el-icon><Picture /></el-icon>添加本地图片</button>
        <input ref="fileInput" class="image-file-input" type="file" accept="image/*" multiple aria-label="选择本地图片" @change="onFiles" />
      </div>
    </component>
    <el-image-viewer v-if="previewIndex !== null" :url-list="current.map(src)" :initial-index="previewIndex" teleported @close="previewIndex = null" />
  </span>
</template>
<script setup>
import { useGridScrollCollapse } from '../../../smart/utils/useGridScrollCollapse.js'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Loading, Picture, MoreFilled, Close } from '@element-plus/icons-vue'
import { ElMessage, ElPopover } from 'element-plus'
import { imageUrl, uploadImageFile, imageMeta, renameImage } from '../../../api/index.js'
import CellDropdown from './CellDropdown.vue'
const props = defineProps({ value: [Array, String], closed: Boolean, readonly: Boolean, selected: Boolean, detail: Boolean, upload: { type: Function, default: uploadImageFile } })
const emit = defineEmits(['commit', 'cancel', 'open', 'select', 'collapse'])
const previewIndex = ref(null)
function preview(index) { const active = props.selected || opened.value; emit('select'); if (active) previewIndex.value = index }
const opened = ref(false), dragDepth = ref(0), uploading = ref(false), completed = ref(0), total = ref(0), error = ref('')
const anchor = ref(null), panel = ref(null), fileInput = ref(null)
const current = ref([]), metadata = ref({}), renaming = ref(null), renameDraft = ref(''), saving = ref(false)
const renameSuffix = ref('')
const idOf = item => typeof item === 'object' ? item.id || item.url : item
const managed = item => /^[a-f0-9]{32}$/.test(String(idOf(item)))
function src(item) { const id = idOf(item); return /^https?:|^data:|^blob:|^\//.test(String(id)) ? id : imageUrl(id) }
function nameOf(item) { return metadata.value[idOf(item)]?.filename || item?.filename || item?.name || (managed(item) ? '图片' : String(idOf(item)).split('/').pop()?.split('?')[0] || '图片') }
watch(() => props.value, value => { current.value = Array.isArray(value) ? [...value] : value ? [value] : [] }, { immediate: true })
watch([opened, current, () => props.detail], async () => {
  if (!opened.value && !props.detail) return
  await Promise.all(current.value.filter(item => managed(item) && !metadata.value[idOf(item)]).map(async item => {
    try { metadata.value[idOf(item)] = await imageMeta(idOf(item)) } catch { /* 图片不可访问时仍可从单元格移除 */ }
  }))
}, { immediate: true })
function publish(items) { current.value = items; emit('commit', [...items]) }
function remove(index) { if (!uploading.value && !saving.value) publish(current.value.filter((_, i) => i !== index)) }
async function itemCommand(command, item, index) {
  if (command === 'delete') return remove(index)
  if (command === 'download') {
    try {
      const response = await fetch(src(item))
      if (!response.ok) throw new Error('下载失败')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a'); link.href = url; link.download = nameOf(item); link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { ElMessage.error(e.message || '下载失败') }
    return
  }
  if (!metadata.value[idOf(item)]) {
    try { metadata.value[idOf(item)] = await imageMeta(idOf(item)) }
    catch { ElMessage.error('无法读取图片名称，请重试'); return }
  }
  const filename = nameOf(item), dot = filename.lastIndexOf('.')
  renameSuffix.value = dot > 0 ? filename.slice(dot) : ''
  renaming.value = idOf(item); renameDraft.value = dot > 0 ? filename.slice(0, dot) : filename
  await nextTick(); const input = panel.value?.querySelector('.image-rename'); input?.focus(); input?.select()
}
async function saveName(item) {
  if (saving.value || renaming.value !== idOf(item)) return
  const name = renameDraft.value.trim()
  if (!name) { error.value = '图片名称不能为空'; return }
  saving.value = true
  try { metadata.value[idOf(item)] = await renameImage(idOf(item), name + renameSuffix.value); renaming.value = null; error.value = '' }
  catch (e) { error.value = e.message || '重命名失败' }
  finally { saving.value = false }
}
async function focus() { if (props.readonly) return; opened.value = true; emit('open'); await nextTick(); panel.value?.focus({ preventScroll: true }) }
function toggle() { const active = props.selected || opened.value; emit('select'); if (props.readonly || !active) return; if (opened.value) close(true); else focus() }
function close(keepSelected = true) { if (uploading.value || saving.value) return; opened.value = false; emit(keepSelected ? 'collapse' : 'cancel') }
function choose() { if (!uploading.value) fileInput.value?.click() }
function onDragOver(event) { if (event.dataTransfer) event.dataTransfer.dropEffect = uploading.value ? 'none' : 'copy' }
function drop(event) { dragDepth.value = 0; uploadFiles(event.dataTransfer?.files || []) }
function onFiles(event) { const files = [...event.target.files]; event.target.value = ''; uploadFiles(files) }
async function uploadFiles(files) {
  if (props.readonly || uploading.value) return
  error.value = ''
  const images = [...files].filter(f => f.type.startsWith('image/'))
  const rejected = files.length - images.length
  if (!images.length) { error.value = '请选择图片文件'; return }
  uploading.value = true; completed.value = 0; total.value = images.length
  const result = [...current.value], failures = []
  // 顺序追加，整批完成后提交一次，避免每张图片从相同旧值起步而覆盖前一张。
  for (const file of images) {
    try {
      const response = await props.upload(file)
      const id = response?.files?.[0]?.id ?? response?.id
      if (id == null) throw new Error('服务未返回图片编号')
      metadata.value[id] = { ...response?.files?.[0], filename: response?.files?.[0]?.filename || file.name }
      result.push(String(id))
    } catch (e) { failures.push(`${file.name}：${e.message || '上传失败'}`) }
    finally { completed.value++ }
  }
  uploading.value = false
  error.value = [rejected ? `已跳过 ${rejected} 个非图片文件` : '', ...failures].filter(Boolean).join('；')
  if (result.length > current.value.length) {
    if (error.value) ElMessage.warning(error.value)
    publish(result)
  }
}
function outside(event) {
  if (event.target.closest?.('.image-item-menu, .el-image-viewer__wrapper')) return
  if (opened.value && !anchor.value?.contains(event.target) && !panel.value?.contains(event.target)) {
    const item = current.value.find(item => idOf(item) === renaming.value)
    if (item) saveName(item).then(() => { if (!renaming.value) close(false) })
    else close(false)
  }
}
watch(opened, (visible, _, onCleanup) => {
  if (!visible) return
  document.addEventListener('mousedown', outside, true)
  onCleanup(() => document.removeEventListener('mousedown', outside, true))
}, { flush: 'sync' })
onBeforeUnmount(() => document.removeEventListener('mousedown', outside, true))
defineExpose({ focus })
useGridScrollCollapse(() => opened.value, () => {
  opened.value = false
  emit('collapse')
})
</script>
<style>
.el-popper.image-cell-pop { padding: 0; max-width: calc(100vw - 24px); border: 1px solid #dcdfe4; border-radius: 6px; box-shadow: 0 4px 14px #0002; }
</style>
<style scoped>
.image-cell-anchor { display: block; width: 100%; height: 100%; }
.image-cell-trigger { position: relative; display: flex; width: 100%; height: 100%; min-height: 28px; align-items: center; padding: 0; box-sizing: border-box; background: transparent; border: 0; cursor: default; }
.image-cell-anchor.can-preview .image-cell-trigger { cursor: pointer; }
.image-cell-thumbs { display: flex; align-items: center; flex: 1; min-width: 0; height: calc(var(--image-cell-height, 34px) - 6px); overflow: hidden; gap: 4px; color: #8b919b; }
.image-cell-thumbs img { width: auto; height: 100%; box-sizing: border-box; flex: none; border: 1px solid #dcdfe4; border-radius: 4px; cursor: default; }
.image-cell-anchor.can-preview .image-cell-thumbs img { cursor: zoom-in; }
.image-upload-panel { color: #858d9b; font-size: var(--st-font-size); outline: none; }
.image-upload-panel button:focus-visible { outline: 2px solid #3985f7; outline-offset: -2px; }
.image-drop-wrap { padding: 16px; }
.image-drop-wrap.has-images { padding: 12px; }
.image-drop-wrap.dragging { background: #eef4ff; }
.image-gallery { display: flex; flex-wrap: wrap; gap: 14px; max-height: 280px; overflow-y: auto; }
.image-card { width: 82px; min-width: 0; }
.image-card-preview { position: relative; width: 80px; height: 80px; border: 1px solid #edeef0; border-radius: 4px; }
.image-card-preview > .el-image { width: 100%; height: 100%; cursor: zoom-in; }
.image-card-actions { position: absolute; top: 3px; right: 3px; display: flex; gap: 3px; opacity: 0; }
.image-card:hover .image-card-actions, .image-card:focus-within .image-card-actions { opacity: 1; }
.image-action { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; padding: 0; border: 0; border-radius: 3px; background: #d3d5d9; color: white; cursor: pointer; }
.image-action:hover { background: #aeb3bc; }
.image-card-name { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: var(--st-font-size); height: 24px; line-height: 24px; }
.image-rename-wrap { display: flex; align-items: center; height: 26px; box-sizing: border-box; border: 1px solid #3985f7; border-radius: 4px; padding: 0 4px; }
.image-rename { width: 0; flex: 1; min-width: 0; border: 0; font-size: var(--st-font-size); padding: 0; outline: none; }
.image-rename-suffix { flex: none; font-size: var(--st-font-size); color: var(--st-text-2); }
.image-gallery-status { font-size: var(--st-font-size); padding-top: 10px; text-align: center; color: #3985f7; }
.image-drop-zone { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; height: 140px; border: 1px dashed #d7d9de; border-radius: 6px; background: #f3f4f5; color: inherit; font: inherit; cursor: pointer; transition: background .15s, border-color .15s; }
.image-drop-zone:hover, .image-drop-zone.dragging { background: #eef4ff; border-color: #3985f7; color: #3985f7; }
.image-drop-zone.busy { cursor: wait; }
.image-local-upload { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; height: 44px; padding: 0 16px; border: 0; border-top: 1px solid #edeef0; border-radius: 0 0 6px 6px; background: white; color: inherit; font: inherit; cursor: pointer; }
.image-local-upload:hover { background: #f3f4f5; }
.image-local-upload:disabled { cursor: wait; opacity: .6; }
.image-local-upload .el-icon { font-size: var(--st-font-size); }
.image-detail-gallery { background: var(--st-bg-hover, #f3f4f5); border-radius: 4px; }
.image-detail-gallery .image-drop-wrap.has-images { padding: 8px; }
.image-detail-gallery .image-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(0, min(112px, 100%))); gap: 8px; max-height: none; overflow: visible; }
.image-detail-gallery .image-card { width: 100%; }
.image-detail-gallery .image-card-preview { width: 100%; height: auto; aspect-ratio: 1; box-sizing: border-box; background: #fff; overflow: hidden; }
.image-detail-gallery .image-card-name { font-size: 12px; color: var(--st-text-3); }
.image-detail-gallery .image-local-upload { height: 32px; background: transparent; font-size: 12px; }
.image-file-input { display: none; }
.image-upload-error { margin-top: 8px; font-size: var(--st-font-size); color: #d95959; overflow-wrap: anywhere; max-height: 64px; overflow: auto; }
</style>
