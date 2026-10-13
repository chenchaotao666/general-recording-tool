<template>
  <!-- 智能表首页（设计文档 §2.2/§2.5）：左侧条目树 + 新建菜单 -->
  <div class="smart-home">
    <div class="nav">
      <div class="nav-head">
        <span class="doc-name">{{ doc?.name || '智能表' }}</span>
      </div>
      <el-input v-model="kw" size="small" placeholder="搜索" clearable class="nav-search" prefix-icon="Search" />
      <el-tree
        :data="tree" node-key="id" :props="{ label: 'name', children: 'children' }"
        default-expand-all highlight-current :expand-on-click-node="false"
        @node-click="onNodeClick">
        <template #default="{ data }">
          <span class="tree-node">
            <span class="t-icon">{{ data.type === 'folder' ? '📂' : data.type === 'dashboard' ? '⌚' : '⊞' }}</span>
            <span class="t-name">{{ data.name }}</span>
            <el-dropdown trigger="click" @command="(cmd) => onNodeAction(cmd, data)">
              <span class="t-more" @click.stop>⋯</span>
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

      <div class="nav-new">
        <div class="new-title">新建</div>
        <div class="new-item" @click="createEntry('sheet')">⊞ 工作表</div>
        <div class="new-item" @click="createEntry('dashboard')">⌚ 仪表盘</div>
        <div class="new-item" @click="createEntry('folder')">📂 文件夹</div>
        <div class="new-item" @click="importVisible = true">⤓ 导入表格</div>
      </div>
    </div>

    <div class="main">
      <el-empty v-if="!entries.length" description="还没有内容，从左侧「新建」开始吧" />
      <template v-else>
        <div class="welcome">
          <h3>智能表</h3>
          <p class="hint">从左侧选择工作表开始编辑，或新建工作表 / 导入 Excel。</p>
          <div class="quick">
            <el-card v-for="e in recentSheets" :key="e.id" shadow="hover" class="quick-card"
                     @click="openEntry(e)">
              <span class="q-icon">⊞</span>
              <span class="q-name">{{ e.name }}</span>
            </el-card>
          </div>
        </div>
      </template>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  smartGetDoc, smartGetTree, smartCreateEntry, smartUpdateEntry, smartDeleteEntry,
  smartImportExcel, uploadExcel, excelPreview,
} from '../../api/index.js'

const router = useRouter()
const doc = ref(null)
const entries = ref([])
const kw = ref('')

const folders = computed(() => entries.value.filter(e => e.type === 'folder'))
const tree = computed(() => {
  const k = kw.value.trim()
  const list = k ? entries.value.filter(e => e.name.includes(k)) : entries.value
  const byParent = new Map()
  for (const e of list) {
    const p = e.parent_id ?? 0
    if (!byParent.has(p)) byParent.set(p, [])
    byParent.get(p).push(e)
  }
  const build = (pid) => (byParent.get(pid) || []).map(e => ({ ...e, children: build(e.id) }))
  return build(0)
})
const recentSheets = computed(() => entries.value.filter(e => e.type === 'sheet').slice(-6).reverse())

async function load() {
  doc.value = await smartGetDoc()
  entries.value = (await smartGetTree(doc.value.id)).entries
}

function onNodeClick(data) {
  if (data.type !== 'folder') openEntry(data)
}
function openEntry(e) {
  if (e.type === 'sheet') router.push(`/smart/table/${e.ref_table_id}`)
  else if (e.type === 'dashboard') router.push(`/smart/dashboard/${e.id}`)
}

async function createEntry(type) {
  const defaults = { sheet: '工作表', dashboard: '仪表盘', folder: '文件夹' }
  const { value } = await ElMessageBox.prompt('名称', `新建${defaults[type]}`, { inputValue: defaults[type] })
  if (value == null) return
  const r = await smartCreateEntry(doc.value.id, { type, name: value || defaults[type] })
  await load()
  if (type === 'sheet') router.push(`/smart/table/${r.table_id}`)
  else if (type === 'dashboard') router.push(`/smart/dashboard/${r.entry.id}`)
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
      load()
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

onMounted(load)
</script>

<style scoped>
.smart-home { display: flex; height: 100%; background: #fff; }
.nav { width: 240px; border-right: 1px solid var(--el-border-color-lighter); display: flex; flex-direction: column; padding: 12px; gap: 8px; overflow: auto; }
.nav-head { font-weight: 700; font-size: 15px; }
.nav-search { margin-bottom: 4px; }
.tree-node { display: flex; align-items: center; gap: 6px; width: 100%; }
.t-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.t-more { visibility: hidden; padding: 0 4px; }
.tree-node:hover .t-more { visibility: visible; }
.nav-new { border-top: 1px solid var(--el-border-color-lighter); padding-top: 8px; margin-top: auto; }
.new-title { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.new-item { padding: 6px 8px; border-radius: 6px; font-size: 13px; cursor: pointer; }
.new-item:hover { background: var(--el-fill-color-light); }
.main { flex: 1; padding: 40px; }
.welcome h3 { margin: 0 0 8px; }
.hint { color: #909399; font-size: 12px; }
.quick { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
.quick-card { width: 160px; cursor: pointer; }
.q-icon { color: var(--el-color-primary); margin-right: 6px; }
.imp { display: flex; flex-direction: column; gap: 10px; }
.up { padding: 30px; color: var(--el-text-color-secondary); font-size: 13px; }
</style>
