<template>
  <span class="file-cell-anchor" @mousedown.stop @click.stop @dblclick.stop>
    <div ref="anchor" class="file-cell-trigger" :class="{ selected }" @click="toggle('pick')">
      <CompactCellTags class="file-compact-tags" :tags="fileTags" :expanded="selected" @tag-click="(_, event) => { event.stopPropagation(); clickFile() }">
        <template #tag="{ tag }"><FileTypeIcon :file="tag.file" /><span class="file-chip-name">{{ tag.label }}</span></template>
      </CompactCellTags>
      <CellDropdown v-if="!readonly" class="file-cell-arrow" overlay :bordered="selected" :visible="selected || opened" :open="opened" label="展开或收起文件面板" @click="toggle('pick')" />
    </div>
    <el-popover v-if="opened" :visible="opened" virtual-triggering :virtual-ref="anchor" placement="bottom-end" :width="mode === 'pick' ? 280 : 400" :show-arrow="false" popper-class="file-cell-pop" :persistent="false">
      <div ref="panel" class="file-panel" tabindex="-1" @mousedown.stop @click.stop @keydown.esc.stop.prevent="close(true)" @dragover.prevent @drop.prevent="drop">
        <template v-if="mode === 'pick'">
          <input ref="search" v-model="query" class="file-search" placeholder="搜索文件或粘贴链接" aria-label="搜索文件或粘贴链接" @keydown.enter.prevent="addLink" />
          <div class="file-section-title">最近上传</div>
          <div class="file-recent">
            <button v-if="link" class="file-recent-row" @click="addLink"><FileTypeIcon :file="link" /><span>添加链接：{{ link.name }}</span></button>
            <button v-for="file in filteredRecent" :key="keyOf(file)" class="file-recent-row" :disabled="busy" @click="toggleFile(file)"><FileTypeIcon :file="file" /><span>{{ file.name }}</span><el-icon v-if="files.some(f => keyOf(f) === keyOf(file))" class="file-check"><Check /></el-icon></button>
            <div v-if="loading" class="file-empty">加载中…</div>
            <div v-else-if="!filteredRecent.length" class="file-empty">{{ query ? '无匹配文件' : '暂无最近上传的文件' }}</div>
          </div>
          <button class="file-upload-button" :disabled="busy" @click="choose"><el-icon><Upload /></el-icon>{{ busy ? `正在上传 ${completed}/${total}` : '上传本地文件' }}</button>
        </template>
        <template v-else>
          <div class="file-panel-toolbar"><button class="file-toolbar-icon" :class="{ active: layout === 'list' }" aria-label="列表视图" @click="layout = 'list'"><el-icon><List /></el-icon></button><button class="file-toolbar-icon" :class="{ active: layout === 'grid' }" aria-label="网格视图" @click="layout = 'grid'"><el-icon><Grid /></el-icon></button></div>
          <div class="file-items" :class="layout">
            <div v-for="(file, index) in files" :key="keyOf(file)" class="file-item">
              <button class="file-preview" @click="viewFile(file)"><img v-if="fileKind(file).image && fileUrl(file)" :src="fileUrl(file)" alt="" /><FileTypeIcon v-else :file="file" /></button>
              <button class="file-info" @click="viewFile(file)"><span class="file-item-name" :data-smart-tip="[file.name || '文件', fileSize(file.size)].filter(Boolean).join('  ')">{{ file.name || '文件' }}</span><span v-if="layout === 'list'" class="file-item-size">{{ fileSize(file.size) || '链接' }}</span></button>
              <el-dropdown v-if="layout === 'grid'" trigger="click" popper-class="file-item-menu" @command="cmd => cmd === 'download' ? downloadFile(file) : remove(index)">
                <button class="file-menu-button" aria-label="文件操作"><el-icon><MoreFilled /></el-icon></button>
                <template #dropdown><el-dropdown-menu><el-dropdown-item command="download">下载</el-dropdown-item><el-dropdown-item v-if="!readonly" command="delete" :disabled="busy">删除</el-dropdown-item></el-dropdown-menu></template>
              </el-dropdown>
              <button v-else-if="!readonly" class="file-toolbar-icon file-delete" aria-label="删除文件" :disabled="busy" @click="remove(index)"><el-icon><Delete /></el-icon></button>
            </div>
            <div v-if="!files.length" class="file-empty">暂无文件</div>
          </div>
          <button v-if="!readonly" class="file-add-button" :disabled="busy" @click="showPicker"><el-icon><Plus /></el-icon>{{ busy ? `正在上传 ${completed}/${total}` : '添加文件' }}</button>
        </template>
        <div v-if="error" class="file-error" role="alert">{{ error }}</div>
        <input ref="fileInput" type="file" multiple class="file-input" @change="onFiles" />
      </div>
    </el-popover>
    <el-image-viewer v-if="previewUrl" :url-list="[previewUrl]" teleported @close="previewUrl = ''" />
  </span>
</template>
<script setup>
import { useGridScrollCollapse } from '../../../smart/utils/useGridScrollCollapse.js'
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Check, Upload, List, Grid, Plus, MoreFilled, Delete } from '@element-plus/icons-vue'
import { smartUploadFile, smartRecentFiles } from '../../../api/index.js'
import { fileKind, fileSize, fileUrl } from './fileDisplay.js'
import FileTypeIcon from './FileTypeIcon.vue'
import CellDropdown from './CellDropdown.vue'
import CompactCellTags from './CompactCellTags.vue'
const props = defineProps({ value: Array, selected: Boolean, readonly: Boolean, upload: { type: Function, default: smartUploadFile }, loadRecent: { type: Function, default: smartRecentFiles } })
const emit = defineEmits(['select', 'open', 'collapse', 'cancel', 'commit'])
const tableId = inject('smartTableId', { value: null })
const files = ref([]), recent = ref([]), opened = ref(false), mode = ref('pick'), layout = ref('grid'), query = ref(''), error = ref(''), loading = ref(false), busy = ref(false), total = ref(0), completed = ref(0), previewUrl = ref('')
const anchor = ref(null), panel = ref(null), search = ref(null), fileInput = ref(null)
const keyOf = file => file.id || file.url || file.name
watch(() => props.value, value => { files.value = [...(value || [])] }, { immediate: true })
const fileTags = computed(() => files.value.map(file => ({ key: keyOf(file), file, label: file.name || '文件', style: { background: '#f2f3f5' } })))
const filteredRecent = computed(() => [...new Map([...files.value, ...recent.value].map(f => [keyOf(f), f])).values()].filter(f => (f.name || '').toLowerCase().includes(query.value.trim().toLowerCase())))
const link = computed(() => {
  try { const url = new URL(query.value.trim()); if (!['http:', 'https:'].includes(url.protocol)) return null; return { url: url.href, name: decodeURIComponent(url.pathname.split('/').pop() || url.hostname) } } catch { return null }
})
function publish(next) { files.value = next; emit('commit', [...next]) }
function toggleFile(file) { if (props.readonly || busy.value) return; const exists = files.value.some(f => keyOf(f) === keyOf(file)); publish(exists ? files.value.filter(f => keyOf(f) !== keyOf(file)) : [...files.value, file]) }
function remove(index) { if (!busy.value && !props.readonly) publish(files.value.filter((_, i) => i !== index)) }
function addLink() { if (!link.value || props.readonly) return; if (!files.value.some(f => f.url === link.value.url)) publish([...files.value, link.value]); mode.value = 'files'; query.value = '' }
async function load() { if (!tableId.value) return; loading.value = true; try { recent.value = await props.loadRecent(tableId.value) } catch { error.value = '最近文件加载失败，可继续上传本地文件' } finally { loading.value = false } }
async function focus(nextMode = 'pick') { mode.value = props.readonly ? 'files' : nextMode; opened.value = true; emit('open'); await nextTick(); panel.value?.focus({ preventScroll: true }); if (mode.value === 'pick') load() }
function toggle(nextMode) { const active = props.selected || opened.value; emit('select'); if (!active) return; if (opened.value) close(true); else focus(nextMode) }
function clickFile() { const active = props.selected || opened.value; emit('select'); if (active) focus('files') }
function close(keep) { if (busy.value) return; opened.value = false; emit(keep ? 'collapse' : 'cancel') }
function showPicker() { mode.value = 'pick'; query.value = ''; load(); nextTick(() => search.value?.focus()) }
function choose() { fileInput.value?.click() }
function viewFile(file) { const url = fileUrl(file, true); if (!url) { error.value = '文件地址不可用'; return } if (fileKind(file).image) previewUrl.value = url; else window.open(url, '_blank', 'noopener,noreferrer') }
async function downloadFile(file) {
  const url = fileUrl(file)
  if (!url) { error.value = '文件地址不可用'; return }
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error('下载失败，请重试')
    const blobUrl = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = blobUrl; link.download = file.name || '文件'; link.click()
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
  } catch (e) { error.value = e.message || '下载失败，请重试' }
}
function onFiles(event) { const chosen = [...event.target.files]; event.target.value = ''; uploadFiles(chosen) }
function drop(event) { uploadFiles([...event.dataTransfer.files]) }
async function uploadFiles(chosen) {
  if (busy.value || props.readonly || !chosen.length) return
  if (!tableId.value) { error.value = '无法获取当前表格，请重新打开后重试'; return }
  busy.value = true; total.value = chosen.length; completed.value = 0; error.value = ''
  const next = [...files.value], failures = []
  for (const file of chosen) {
    try { if (file.size > 20 * 1024 * 1024) throw new Error('超过20MB上限'); const result = await props.upload(tableId.value, file); if (!result?.id) throw new Error('未返回文件编号'); next.push({ id: result.id, name: result.name || file.name, size: result.size ?? file.size }) }
    catch (e) { failures.push(`${file.name}：${e.message || '上传失败'}`) }
    finally { completed.value++ }
  }
  busy.value = false; error.value = failures.join('；')
  if (next.length > files.value.length) { publish(next); mode.value = 'files' }
}
function outside(event) { if (event.target.closest?.('.file-item-menu, .el-image-viewer__wrapper')) return; if (opened.value && !anchor.value?.contains(event.target) && !panel.value?.contains(event.target)) close(false) }
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
.el-popper.file-cell-pop { padding: 0; border: 1px solid #e0e2e6; border-radius: 8px; box-shadow: 0 4px 16px #0002; max-width: calc(100vw - 24px); }
</style>
<style scoped>
button { font: inherit; color: inherit; cursor: pointer; }
.file-cell-anchor { display: block; width: 100%; }
.file-cell-trigger { position: relative; cursor: default; min-height: 28px; }
.file-cell-trigger.selected { cursor: pointer; box-sizing: border-box; min-height: var(--file-row-height, 36px); border: 2px solid var(--st-primary, #3370ff); background: white; padding: 4px 26px 4px 6px; border-radius: 0; z-index: 2; box-shadow: 0 4px 16px #0000001f; }
.file-compact-tags .file-chip-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-panel { font-size: 13px; color: #30343b; outline: none; }
.file-search { width: 100%; box-sizing: border-box; height: 44px; padding: 0 16px; border: 0; border-bottom: 1px solid #eceef0; border-radius: 8px 8px 0 0; outline: none; font: inherit; }
.file-search::placeholder { color: #a0a5ae; }
.file-section-title { padding: 14px 16px 6px; color: #9399a3; font-size: 12px; }
.file-recent { max-height: 250px; overflow: auto; padding: 0 6px 8px; }
.file-recent-row { display: flex; align-items: center; gap: 8px; width: 100%; padding: 9px 10px; background: transparent; border: 0; border-radius: 4px; text-align: left; }
.file-recent-row > span:nth-child(2) { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-recent-row:hover { background: #f2f3f5; }
.file-check { color: #3985f7; }
.file-upload-button, .file-add-button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 12px 16px; background: transparent; border: 0; border-top: 1px solid #eceef0; border-radius: 0 0 8px 8px; text-align: left; }
.file-add-button { justify-content: center; color: #969da8; }
.file-upload-button:hover, .file-add-button:hover { background: #f2f3f5; }
.file-panel-toolbar { display: flex; justify-content: flex-end; padding: 6px 12px; border-bottom: 1px solid #eceef0; gap: 4px; }
.file-toolbar-icon { width: 28px; height: 26px; border: 0; border-radius: 4px; background: transparent; display: inline-flex; align-items: center; justify-content: center; color: #828a97; }
.file-toolbar-icon:hover, .file-toolbar-icon.active { background: #e9ebee; }
.file-items { padding: 12px; max-height: 290px; overflow: auto; }
.file-items.grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.file-item { position: relative; min-width: 0; }
.file-preview { display: flex; justify-content: center; align-items: center; border: 1px solid #e9ebee; border-radius: 4px; height: 72px; width: 100%; background: white; padding: 0; overflow: hidden; }
.file-preview img { width: 100%; height: 100%; object-fit: contain; }
.file-preview .file-type-icon { width: 32px; height: 32px; font-size: 20px; }
.file-info { border: 0; background: transparent; padding: 6px 0 0; width: 100%; text-align: left; min-width: 0; }
.file-item-name { display: block; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-item > .el-dropdown { position: absolute; top: 3px; right: 3px; }
.file-menu-button { display: inline-flex; justify-content: center; align-items: center; width: 20px; height: 20px; border: 0; border-radius: 3px; background: #a4a9b1; color: white; opacity: 0; }
.file-item:hover .file-menu-button, .file-item:focus-within .file-menu-button { opacity: 1; }
.file-items.list { display: flex; flex-direction: column; gap: 8px; }
.file-items.list .file-item { display: flex; align-items: center; gap: 10px; border: 1px solid #d7dbe1; border-radius: 4px; background: #f4f5f6; padding: 10px; }
.file-items.list .file-preview { width: 30px; height: 30px; flex: none; border: 0; background: transparent; }
.file-items.list .file-info { flex: 1; padding: 0; }
.file-item-size { display: block; color: #9aa1ac; margin-top: 4px; font-size: 12px; }
.file-delete { flex: none; }
.file-empty { padding: 16px 10px; color: #969da8; font-size: 12px; }
.file-error { padding: 8px 12px; color: #da6262; font-size: 12px; overflow-wrap: anywhere; max-height: 70px; overflow: auto; }
.file-input { display: none; }
</style>
