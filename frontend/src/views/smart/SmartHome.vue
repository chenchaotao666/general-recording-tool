<template>
  <!-- 智能表首页（设计文档 §2.2/§2.5）：左侧条目树 + 新建菜单 -->
  <div class="smart-home">
    <div v-show="!sideCollapsed" class="nav" :style="{ width: sideWidth + 'px' }">
      <div class="side-top">
        <div class="side-top-row">
          <button class="side-fold st-icon-action" type="button" data-smart-tip="收起目录" @click="toggleSide"><el-icon><Fold /></el-icon></button>
          <el-input v-model="kw" placeholder="搜索智能表" clearable :prefix-icon="Search" />
        </div>
        <div class="side-top-row">
          <el-dropdown class="side-new" trigger="click" @command="cmd => cmd === 'import' ? importVisible = true : createEntry(cmd)">
            <el-button type="primary" :icon="Plus">新建</el-button>
            <template #dropdown><el-dropdown-menu>
              <el-dropdown-item command="sheet">工作表</el-dropdown-item>
              <el-dropdown-item command="dashboard">仪表盘</el-dropdown-item>
              <el-dropdown-item command="form">收集表单</el-dropdown-item>
              <el-dropdown-item command="import" divided>导入表格</el-dropdown-item>
            </el-dropdown-menu></template>
          </el-dropdown>
          <el-button :icon="FolderAdd" data-smart-tip="新建文件夹" @click="createEntry('folder')" />
          <el-tooltip content="内容权限" placement="bottom">
            <button class="side-fold st-icon-action" type="button" aria-label="内容权限" @click="permVisible = !permVisible"><StIcon name="lock" :size="15" /></button>
          </el-tooltip>
        </div>
      </div>
      <el-tree
        ref="treeRef" v-loading="treeLoading" class="entry-tree" :current-node-key="activeEntry?.id"
        :data="tree" node-key="id" :props="{ label: 'name', children: 'children' }"
        default-expand-all highlight-current :expand-on-click-node="false"
        :empty-text="kw ? '没有匹配的内容' : '还没有内容，点击上方新建'"
        @node-click="onNodeClick">
        <template #default="{ data }">
          <span class="tree-node">
            <StIcon :name="{ folder: 'folder', dashboard: 'dashboard', form: 'form' }[data.type] || 'view-grid'"
                    :size="14" class="t-icon" />
            <span class="t-name">{{ data.name }}</span>
            <el-dropdown trigger="click" @command="(cmd) => onNodeAction(cmd, data)">
              <span class="t-more st-icon-action" @click.stop><StIcon name="more-h" :size="14" /></span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rename">重命名</el-dropdown-item>
                  <el-dropdown-item command="move">移入文件夹</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </span>
        </template>
      </el-tree>

    </div>

    <div v-show="!sideCollapsed" class="side-resizer" data-smart-tip="拖动调整目录宽度" @pointerdown.prevent="startSideResize" />
    <button v-if="sideCollapsed" class="side-expand st-icon-action" type="button" aria-label="展开目录" @click="toggleSide">
      <el-icon><Expand /></el-icon>
    </button>
    <div class="smart-content">
      <router-view v-slot="{ Component }">
        <component :is="Component" v-if="Component" :key="$route.path" />
        <el-empty v-else :description="treeLoading ? '正在加载…' : '从左侧选择或新建工作表'" />
      </router-view>
    </div>

    <!-- 导入 Excel（复用现有上传/探测） -->
    <el-dialog v-model="importVisible" title="导入本地 Excel 文件" width="560px" destroy-on-close>
      <div class="imp">
        <el-upload drag :show-file-list="false" :http-request="onUpload" accept=".xlsx,.csv">
          <div class="up">将文件拖拽至此，或点击选择（.xlsx / .csv）</div>
        </el-upload>
        <template v-if="fileId">
          <el-select v-model="sheetName" placeholder="选择工作表" @change="loadPreview">
            <el-option v-for="s in sheets" :key="s.name" :value="s.name" :label="s.name" />
          </el-select>
          <el-input-number v-model="headerRow" :min="1" :max="10" size="small" @change="loadPreview" />
          <span class="hint">表头行</span>
          <el-input v-model="importName" placeholder="工作表名称" />
          <el-table v-if="preview.length" :data="preview" size="small" max-height="200" border>
            <el-table-column v-for="(h, i) in previewHeaders" :key="i" :prop="`c${i}`" :label="h" show-overflow-tooltip />
          </el-table>
        </template>
      </div>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!fileId || !sheetName || importing" :loading="importing" @click="doImport">
          导入
        </el-button>
      </template>
    </el-dialog>

    <PermissionPanel :visible="permVisible" :doc-id="doc?.id" :members="members" @close="permVisible = false" />

    <!-- 移入文件夹 -->
    <el-dialog v-model="move.visible" title="移入文件夹" width="360px">
      <el-select v-model="move.target" clearable placeholder="选择目标文件夹（留空=根级）" style="width: 100%">
        <el-option v-for="f in folders" :key="f.id" :value="f.id" :label="f.name" />
      </el-select>
      <template #footer>
        <el-button @click="move.visible = false">取消</el-button>
        <el-button type="primary" @click="doMove">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  smartGetDoc, smartGetTree, smartCreateEntry, smartUpdateEntry, smartDeleteEntry,
  smartImportExcel, uploadExcel, excelPreview, smartDocMembers,
} from '../../api/index.js'
import { Expand, Fold, FolderAdd, Plus, Search } from '@element-plus/icons-vue'
import StIcon from '../../components/smart/icons/StIcon.vue'
import PermissionPanel from '../../components/smart/perms/PermissionPanel.vue'

const router = useRouter()
const route = useRoute()
const treeRef = ref(null)
const treeLoading = ref(false)
const sideWidth = ref(Math.min(480, Math.max(200, Number(localStorage.getItem('grt_smart_side_w')) || 280)))
const sideCollapsed = ref(localStorage.getItem('grt_smart_side_collapsed') === '1')
const doc = ref(null)
const entries = ref([])
const kw = ref('')
const permVisible = ref(false)
const members = ref([])

const folders = computed(() => entries.value.filter(e => e.type === 'folder'))
const tree = computed(() => {
  const k = kw.value.trim()
  const byId = new Map(entries.value.map(e => [e.id, e]))
  const included = new Set()
  for (const entry of entries.value) {
    if (!k || entry.name.toLowerCase().includes(k.toLowerCase())) {
      let current = entry
      while (current && !included.has(current.id)) {
        included.add(current.id)
        current = byId.get(current.parent_id)
      }
    }
  }
  const list = entries.value.filter(e => included.has(e.id))
  const byParent = new Map()
  for (const e of list) {
    const p = e.parent_id ?? 0
    if (!byParent.has(p)) byParent.set(p, [])
    byParent.get(p).push(e)
  }
  const build = (pid) => (byParent.get(pid) || []).map(e => ({ ...e, children: build(e.id) }))
  return build(0)
})
const activeEntry = computed(() => entries.value.find(e =>
  route.params.tableId ? ['sheet', 'form'].includes(e.type) && e.ref_table_id === Number(route.params.tableId)
    : route.params.entryId && e.id === Number(route.params.entryId)))
function entryPath(e) {
  return e.type === 'dashboard' ? `/smart/dashboard/${e.id}` : `/smart/table/${e.ref_table_id}`
}
function openDefault() {
  if (route.path !== '/smart') return
  const available = entries.value.filter(e => e.type !== 'folder')
  const last = localStorage.getItem(`grt_smart_last_${doc.value?.id}`)
  const target = available.find(e => entryPath(e) === last) || available.find(e => e.type === 'sheet') || available[0]
  if (target) router.replace(entryPath(target))
}
watch(() => route.path, openDefault)
watch(activeEntry, async entry => {
  if (entry && doc.value) localStorage.setItem(`grt_smart_last_${doc.value.id}`, entryPath(entry))
  await nextTick()
  treeRef.value?.setCurrentKey(entry?.id ?? null)
})
function toggleSide() {
  sideCollapsed.value = !sideCollapsed.value
  localStorage.setItem('grt_smart_side_collapsed', sideCollapsed.value ? '1' : '0')
}
let stopResize = null
function startSideResize(event) {
  stopResize?.()
  const startX = event.clientX, startWidth = sideWidth.value
  const move = e => { sideWidth.value = Math.max(200, Math.min(480, startWidth + e.clientX - startX)) }
  stopResize = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stopResize)
    window.removeEventListener('pointercancel', stopResize)
    localStorage.setItem('grt_smart_side_w', String(sideWidth.value))
    stopResize = null
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stopResize)
  window.addEventListener('pointercancel', stopResize)
}
onBeforeUnmount(() => stopResize?.())

async function load() {
  doc.value = await smartGetDoc()
  entries.value = (await smartGetTree(doc.value.id)).entries
  if (!members.value.length) members.value = (await smartDocMembers(doc.value.id).catch(() => ({ members: [] }))).members
}

function onNodeClick(data, node) {
  if (data.type !== 'folder') openEntry(data)
  else {
    if (node.expanded) node.collapse(); else node.expand()
    nextTick(() => treeRef.value?.setCurrentKey(activeEntry.value?.id ?? null))
  }
}
function openEntry(e) {
  if (e.type === 'sheet' || e.type === 'form') router.push(`/smart/table/${e.ref_table_id}`)
  else if (e.type === 'dashboard') router.push(`/smart/dashboard/${e.id}`)
}

async function createEntry(type) {
  try {
    const defaults = { sheet: '工作表', dashboard: '仪表盘', folder: '文件夹', form: '收集表单' }
    const { value } = await ElMessageBox.prompt('名称', `新建${defaults[type]}`, { inputValue: defaults[type] })
    if (value == null) return
    const r = await smartCreateEntry(doc.value.id, { type, name: value || defaults[type] })
    await load()
    if (type === 'sheet' || type === 'form') router.push(`/smart/table/${r.table_id}`)
    else if (type === 'dashboard') router.push(`/smart/dashboard/${r.entry.id}`)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}

async function onNodeAction(cmd, data) {
  if (cmd === 'rename') {
    const { value } = await ElMessageBox.prompt('名称', '重命名', { inputValue: data.name })
    if (value) { await smartUpdateEntry(data.id, { name: value }); load() }
  } else if (cmd === 'move') {
    Object.assign(move, { visible: true, entry: data, target: null })
  } else if (cmd === 'delete') {
    await ElMessageBox.confirm(`删除「${data.name}」？${data.type === 'sheet' ? '表内数据将一并删除。' : ''}`, '删除', { type: 'warning' })
    try {
      await smartDeleteEntry(data.id)
      ElMessage.success('已删除')
      await load()
      if (!activeEntry.value) await router.replace('/smart')
    } catch (e) {
      ElMessage.error(e.message)
    }
  }
}

const move = reactive({ visible: false, entry: null, target: null })
async function doMove() {
  try {
    await smartUpdateEntry(move.entry.id, { parent_id: move.target })
    move.visible = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 导入 ----------
const importVisible = ref(false)
const fileId = ref(null)
const sheets = ref([])
const sheetName = ref('')
const headerRow = ref(1)
const importName = ref('')
const preview = ref([])
const previewHeaders = ref([])
const importing = ref(false)

async function onUpload({ file }) {
  const res = await uploadExcel(file)
  fileId.value = res.file_id
  sheets.value = res.sheets || []
  sheetName.value = sheets.value[0]?.name || ''
  importName.value = file.name.replace(/\.(xlsx|csv)$/i, '')
  loadPreview()
}
async function loadPreview() {
  if (!fileId.value || !sheetName.value) return
  const res = await excelPreview(fileId.value, sheetName.value, headerRow.value)
  previewHeaders.value = res.headers || []
  preview.value = (res.rows || []).map(r => Object.fromEntries(r.map((v, i) => [`c${i}`, v])))
}
async function doImport() {
  importing.value = true
  try {
    const r = await smartImportExcel(doc.value.id, {
      file_id: fileId.value, sheet_name: sheetName.value, header_row: headerRow.value, name: importName.value,
    })
    const rep = r.import_report || {}
    ElMessage.success(`导入完成：成功 ${rep.success ?? 0} 行${rep.failed ? `，失败 ${rep.failed} 行` : ''}`)
    importVisible.value = false
    await load()
    router.push(`/smart/table/${r.table_id}`)
  } catch (e) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importing.value = false
  }
}

onMounted(async () => {
  treeLoading.value = true
  try { await load(); openDefault() }
  catch (e) { ElMessage.error(e.message) }
  finally { treeLoading.value = false }
})
</script>

<style scoped>
.smart-home { display: flex; height: calc(100vh - var(--chrome-h, 48px)); min-width: 0; overflow: hidden; background: #f5f7fa; }
.nav { flex-shrink: 0; display: flex; flex-direction: column; overflow: hidden; background: #fff; box-shadow: 0 2px 12px rgba(31,45,61,.08); }
.side-top { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border-bottom: 1px solid #f0f2f5; }
.side-top-row { display: flex; align-items: center; gap: 8px; }
.side-new { flex: 1; min-width: 0; }
.side-new .el-button { width: 100%; }
.side-top-row .el-button + .el-button { margin-left: 0; }
.side-fold { border: 0; background: transparent; display: inline-flex; padding: 4px; color: #909399; cursor: pointer; border-radius: 6px; font-size: 16px; }
.side-fold:hover { background: #f5f7fa; color: #303133; }
.entry-tree { flex: 1; min-height: 0; overflow: auto; padding: 8px; }
.tree-node { display: flex; align-items: center; gap: 6px; width: 100%; min-width: 0; font-size: 14px; }
.t-icon { color: #a8abb2; flex: none; }
.t-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t-more { visibility: hidden; padding: 3px; display: inline-flex; color: #909399; }
.tree-node:hover .t-more, .tree-node:focus-within .t-more { visibility: visible; }
.nav :deep(.el-tree-node__content) { height: 34px; border-radius: 6px; }
.nav :deep(.el-tree-node__content:hover) { background: #f5f7fa; }
.nav :deep(.el-tree-node.is-current > .el-tree-node__content) { background: #e8f1fd; color: var(--grt-primary, #409eff); font-weight: 500; }
.nav :deep(.el-tree-node.is-current > .el-tree-node__content .t-icon) { color: var(--grt-primary, #409eff); }
.side-resizer { width: 10px; flex-shrink: 0; cursor: col-resize; touch-action: none; display: flex; align-items: center; justify-content: center; }
.side-resizer::after { content: ''; width: 3px; height: 36px; border-radius: 2px; background: transparent; }
.side-resizer:hover::after { background: #c0c4cc; }
.side-expand { width: 46px; flex-shrink: 0; padding: 18px 0 0; border: 0; background: #fff; display: flex; justify-content: center; align-items: flex-start; color: #909399; cursor: pointer; }
.smart-content { flex: 1; min-width: 0; min-height: 0; overflow: auto; background: #fff; }
.hint { color: #909399; font-size: 12px; }
.imp { display: flex; flex-direction: column; gap: 10px; }
.up { padding: 30px; color: var(--el-text-color-secondary); font-size: 13px; }
</style>
