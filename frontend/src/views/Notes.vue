<template>
  <div class="notes-page">
    <!-- 左侧：搜索 + 页面树（可折叠，业内笔记本风格）；宽度可拖拽调节，可整体收起 -->
    <div v-show="!sideCollapsed" class="notes-side" :style="{ width: sideWidth + 'px' }">
      <div class="side-top">
        <div class="side-top-row">
          <el-icon class="side-fold" title="收起目录" @click="collapseSide"><Fold /></el-icon>
          <el-input
            v-model="keyword" placeholder="搜索笔记" clearable :prefix-icon="Search"
            @input="onSearchInput" @clear="searchResults = null"
          />
        </div>
        <div class="side-top-row">
          <el-button type="primary" :icon="Plus" class="side-new" @click="createPage()">新建</el-button>
          <el-button :icon="FolderAdd" title="新建文件夹" @click="createFolder()" />
        </div>
      </div>
      <div v-loading="treeLoading" class="tree">
        <template v-if="displayTree.length">
          <div
            v-for="n in displayTree" :key="n.id"
            class="tree-item" :class="[{ active: current?.id === n.id }, dnd.indicatorClass(n)]"
            :style="{ paddingLeft: 6 + n.level * 16 + 'px' }"
            :draggable="searchResults === null"
            @click="onItemClick(n)"
            @dragstart="dnd.start(n, $event)"
            @dragover="dnd.over(n, $event)"
            @drop="dnd.drop(n, $event)"
            @dragend="dnd.end"
          >
            <DndHandle v-if="searchResults === null" />
            <span
              class="tree-chevron" :class="{ has: n.hasChildren, open: n.hasChildren && !collapsed.has(n.id) }"
              @click.stop="toggleCollapse(n)"
            >
              <el-icon v-if="n.hasChildren"><ArrowRight /></el-icon>
            </span>
            <el-icon class="tree-doc"><Folder v-if="n.kind === 'folder'" /><Document v-else /></el-icon>
            <span class="tree-title">{{ n.title || (n.kind === 'folder' ? '未命名文件夹' : '无标题页面') }}</span>
            <span class="tree-ops" @click.stop>
              <el-icon v-if="n.kind === 'folder' && n.level < 2" title="新增子页" @click="createPage(n)"><Plus /></el-icon>
              <el-dropdown trigger="click" placement="bottom-end" @command="(cmd) => onMenu(cmd, n)">
                <el-icon title="更多" class="tree-more"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="rename">重命名</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </span>
          </div>
        </template>
        <div v-else-if="!treeLoading" class="side-empty">
          {{ keyword ? '没有匹配的笔记' : '还没有笔记，点上方「新建」开始' }}
        </div>
      </div>
    </div>
    <!-- 分隔条：拖拽调节目录栏宽度 -->
    <div v-show="!sideCollapsed" class="side-resizer" title="拖动调整目录宽度" @mousedown.prevent="startSideResize" />
    <!-- 收起后的窄条：点击展开 -->
    <div v-show="sideCollapsed" class="side-expand" title="展开目录" @click="expandSide">
      <el-icon><Expand /></el-icon>
    </div>

    <!-- 右侧：富文本编辑器（wangEditor） -->
    <div ref="mainRef" class="notes-main">
      <template v-if="current">
        <div class="main-top">
          <input v-model="current.title" class="title-input" placeholder="无标题页面" maxlength="200" @input="onTitleInput" />
          <div class="main-ops">
            <span class="save-state" :class="{ err: saveState === '保存失败' }">{{ saveState }}</span>
          </div>
        </div>
        <!-- :key = 笔记 id：切页时整体重建，content 只在挂载时读入 -->
        <WangRichEditor :key="current.id" ref="editorRef" :content="current.content" @change="onEditorChange" @ai="openAi" />
        <!-- AI 写作面板：可拖动（拖标题栏移动）；点击外部 / Esc 关闭 -->
        <div
          v-if="ai.visible" class="ai-panel"
          :style="ai.x !== null ? { left: ai.x + 'px', top: ai.y + 'px', right: 'auto',
                                    maxHeight: ai.maxH ? ai.maxH + 'px' : undefined } : {}"
          @keydown.stop
        >
          <div class="ai-panel-head" @mousedown="startAiDrag">
            ✨ AI 写作<span class="ai-drag-hint">按住拖动</span>
          </div>
          <div v-if="ai.selected" class="ai-selected" :title="ai.selected">
            📌 基于选中内容（{{ ai.selected.length }} 字）：{{ ai.selected.slice(0, 60) }}{{ ai.selected.length > 60 ? '…' : '' }}
          </div>
          <input
            ref="aiInputRef" v-model="ai.instruction" class="ai-input"
            :placeholder="ai.selected ? '对选中内容做什么？如：润色 / 扩写 / 总结 / 翻译（直接回车=润色）' : '描述要生成的内容，如：写一份本周工作总结；也可粘贴截图按图生成'"
            @keydown.enter.prevent="aiGenerate"
          />
          <AiImagePicker v-if="!ai.preview" v-model="ai.images" />
          <!-- 选中内容时的快捷指令：点一下直接生成，不用打字 -->
          <div v-if="ai.selected && !ai.preview" class="ai-quick">
            <button
              v-for="q in AI_QUICK_ACTIONS" :key="q" class="ai-chip" type="button"
              :disabled="ai.loading" @click="aiQuick(q)"
            >{{ q }}</button>
          </div>
          <div v-if="ai.preview" class="ai-preview" v-html="ai.preview" />
          <div class="ai-panel-ops">
            <span class="ai-hint">{{ ai.preview ? '确认后插入到光标处 · Esc 丢弃' : 'Enter 生成 · Esc 取消' }}</span>
            <div>
              <template v-if="ai.preview">
                <el-button size="small" text @click="closeAi(true)">丢弃</el-button>
                <el-button size="small" :loading="ai.loading" @click="aiGenerate">重新生成</el-button>
                <el-button size="small" type="primary" @click="aiInsert(false)">插入</el-button>
                <el-button v-if="ai.selected" size="small" type="danger" plain @click="aiInsert(true)">替换选中</el-button>
              </template>
              <el-button v-else size="small" type="primary" :loading="ai.loading" @click="aiGenerate">生成</el-button>
            </div>
          </div>
          <div v-if="ai.error" class="ai-error">{{ ai.error }}</div>
        </div>
      </template>
      <el-empty v-else description="选择左侧页面，或新建一个开始记录" />
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Document, Expand, Fold, Folder, FolderAdd, MoreFilled, Plus, Search } from '@element-plus/icons-vue'
import { createNote, deleteNote, getNote, noteAiAssist, noteTree, searchNotes, updateNote } from '../api'
import WangRichEditor from '../components/notes/WangRichEditor.vue'
import AiImagePicker from '../components/AiImagePicker.vue'
import DndHandle from '../components/DndHandle.vue'
import { useTreeDnd } from '../composables/useTreeDnd.js'

const route = useRoute()
const router = useRouter()

const notes = ref([])          // 扁平列表（后端已排好序）
const treeLoading = ref(false)
const current = ref(null)      // 当前打开的页面（含 content HTML）
const keyword = ref('')
const searchResults = ref(null) // 非 null 时展示搜索结果（平铺）
const saveState = ref('')
const editorRef = ref(null)
const collapsed = ref(new Set())  // 目录树中收起的页面 id

// 目录栏：宽度可拖拽调节（200~480px，记住选择）；可整体收起为窄条
// 存储键带版本（_v3）：默认值调整时换版本，忽略旧键里的历史值
const sideWidth = ref(Number(localStorage.getItem('grt_notes_side_w_v3')) || 280)
const sideCollapsed = ref(localStorage.getItem('grt_notes_side_collapsed') === '1')
function collapseSide() { sideCollapsed.value = true; localStorage.setItem('grt_notes_side_collapsed', '1') }
function expandSide() { sideCollapsed.value = false; localStorage.setItem('grt_notes_side_collapsed', '0') }
function startSideResize(e) {
  const startX = e.clientX
  const startW = sideWidth.value
  const onMove = (ev) => { sideWidth.value = Math.min(480, Math.max(200, startW + ev.clientX - startX)) }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    // 只有真的拖过才记住宽度，避免误点分隔条把当前默认值存成"用户选择"
    if (sideWidth.value !== startW) localStorage.setItem('grt_notes_side_w_v3', String(sideWidth.value))
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

// AI 写作面板（可拖动；点击外部 / Esc 关闭）
const ai = ref({ visible: false, loading: false, instruction: '', error: '', preview: null, x: null, y: null, images: [] })
const aiInputRef = ref(null)
const mainRef = ref(null)

let latestHtml = ''    // 编辑器最近一次 change 的 HTML（flushSave 以它为准）
let saveTimer = null
let saving = false
let dirty = false

function toggleCollapse(n) {
  if (!n.hasChildren) return
  const s = new Set(collapsed.value)
  if (s.has(n.id)) s.delete(n.id)
  else s.add(n.id)
  collapsed.value = s
}

// 文件夹（kind=folder）仅作目录分组：点击折叠/展开，不打开内容
function onItemClick(n) {
  if (n.kind === 'folder') {
    toggleCollapse(n)
    return
  }
  open(n)
}

// ---------- 文件夹（新建 / 重命名 / 移入，对齐智能表目录的 ⋯ 菜单） ----------

function isCancel(e) {
  return e === 'cancel' || e === 'close'
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', { inputValue: '未命名文件夹' })
    if (value == null) return
    await createNote({ kind: 'folder', title: value.trim() || '未命名文件夹' })
    await loadTree()
  } catch (e) {
    if (!isCancel(e)) ElMessage.error(e.message || e)
  }
}

async function onMenu(cmd, n) {
  if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('名称', '重命名', { inputValue: n.title })
      if (!value?.trim()) return
      await updateNote(n.id, { title: value.trim() })
      if (current.value?.id === n.id) current.value.title = value.trim()
      await loadTree()
    } catch (e) {
      if (!isCancel(e)) ElMessage.error(e.message || e)
    }
  } else if (cmd === 'delete') {
    del(n)
  }
}

// 扁平列表 → 带层级的树（平铺展示，用 level 缩进；收起的父页不显示其子树）
const displayTree = computed(() => {
  if (searchResults.value !== null) return searchResults.value.map((n) => ({ ...n, level: 0, hasChildren: false }))
  const byId = new Map(notes.value.map((n) => [n.id, { ...n, children: [] }]))
  const roots = []
  for (const n of byId.values()) {
    if (n.parent_id && byId.has(n.parent_id)) byId.get(n.parent_id).children.push(n)
    else roots.push(n)
  }
  const out = []
  const walk = (list, level) => list.forEach((n) => {
    out.push({ ...n, level, hasChildren: n.children.length > 0 })
    if (!collapsed.value.has(n.id)) walk(n.children, level + 1)
  })
  walk(roots, 0)
  return out
})

async function loadTree() {
  treeLoading.value = true
  try {
    notes.value = (await noteTree()).notes
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    treeLoading.value = false
  }
}

function debounce(fn, ms) {
  let t = null
  return (...args) => {
    clearTimeout(t)
    t = setTimeout(() => fn(...args), ms)
  }
}

const onSearchInput = debounce(async () => {
  const kw = keyword.value.trim()
  if (!kw) {
    searchResults.value = null
    return
  }
  try {
    searchResults.value = (await searchNotes(kw)).notes.filter((x) => x.kind !== 'folder')
  } catch (e) {
    ElMessage.error(e.message)
  }
}, 300)

// ---------- 编辑器 ----------

function onEditorChange(html) {
  latestHtml = html
  dirty = true
  scheduleSave()
}

const scheduleSave = () => {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(flushSave, 1000)
}

async function flushSave() {
  if (!current.value || saving || !dirty) return
  saving = true
  saveState.value = '保存中…'
  try {
    const res = await updateNote(current.value.id, { content: latestHtml })
    current.value.updated_at = res.updated_at
    dirty = false
    saveState.value = `已保存 ${new Date().toTimeString().slice(0, 5)}`
  } catch (e) {
    saveState.value = '保存失败'
    ElMessage.error(e.message)
  } finally {
    saving = false
  }
}

async function open(n) {
  if (n.kind === 'folder') return   // 文件夹无内容，点击走 onItemClick 的折叠/展开
  if (current.value?.id === n.id) return
  clearTimeout(saveTimer)
  if (dirty && editorRef.value) {
    latestHtml = editorRef.value.getHtml()
    await flushSave()
  }
  closeAi()
  saveState.value = ''
  try {
    // 先加载再切换：旧内容保持显示直到新笔记就绪，避免清空 → 空态 → 新内容的闪烁
    const full = await getNote(n.id)
    current.value = full
    latestHtml = full.content || ''
    dirty = false
    // 选中态同步到 URL query，F5 刷新后恢复
    router.replace({ query: { ...route.query, noteId: full.id } })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

const onTitleInput = debounce(async () => {
  if (!current.value) return
  try {
    await updateNote(current.value.id, { title: current.value.title })
    const item = notes.value.find((x) => x.id === current.value.id)
    if (item) item.title = current.value.title
    saveState.value = `已保存 ${new Date().toTimeString().slice(0, 5)}`
  } catch (e) {
    ElMessage.error(e.message)
  }
}, 600)

// ---------- AI 写作 ----------

function openAi() {
  // 面板聚焦前抓取选区：有选中内容时它是本次 AI 操作的主要对象
  const sel = (editorRef.value?.getSelectionText() || '').trim()
  ai.value = { visible: true, loading: false, instruction: '', error: '', preview: null,
               x: null, y: null, maxH: null, selected: sel, images: [] }
  placeAiPanel()
  nextTick(() => aiInputRef.value?.focus())
  // 点击面板外 / 任意位置 Esc 关闭（capture 阶段，面板内 Esc 也能生效）
  document.addEventListener('mousedown', onAiDocDown, true)
  document.addEventListener('keydown', onAiEsc, true)
}

// 面板定位：有选中内容 → 跟在选区旁边（下方放不下翻到上方）；
// 无选中（点工具栏按钮唤起）→ 贴「✨ AI 写作」按钮下方，与入口视觉呼应；
// 都拿不到 → 编辑区中上方居中兜底。全程限制在编辑区内。
function placeAiPanel() {
  const main = mainRef.value?.getBoundingClientRect()
  if (!main) return
  const PANEL_W = 460
  const s = window.getSelection()
  let rect = s?.rangeCount ? s.getRangeAt(0).getBoundingClientRect() : null
  // 光标态（折叠选区）个别浏览器返回全 0 矩形，视为无选区
  if (rect && !rect.width && !rect.height && !rect.top && !rect.left) rect = null
  if (!rect || (s.isCollapsed && !ai.value.selected)) {
    // 无选中内容：贴工具栏 AI 按钮（按钮在编辑器组件内，从主区里查）
    const btn = mainRef.value?.querySelector('.ai-write-btn')
    const br = btn?.getBoundingClientRect()
    if (br) {
      ai.value.x = Math.max(8, Math.min(br.left - main.left, main.width - PANEL_W - 8))
      ai.value.y = br.bottom - main.top + 6
    } else {
      ai.value.x = Math.max(8, (main.width - PANEL_W) / 2)
      ai.value.y = 72
    }
    return
  }
  ai.value.x = Math.max(8, Math.min(rect.left - main.left, main.width - PANEL_W - 8))
  ai.value.y = Math.max(8, rect.bottom - main.top + 8)
  nextTick(() => {
    const panel = document.querySelector('.ai-panel')
    if (!panel) return
    const ph = panel.offsetHeight
    if (ai.value.y + ph > main.height - 8) {
      ai.value.y = Math.max(8, rect.top - main.top - ph - 8)   // 下方放不下 → 翻到上方
    }
  })
}

function closeAi(refocus = false) {
  ai.value.visible = false
  ai.value.preview = null
  document.removeEventListener('mousedown', onAiDocDown, true)
  document.removeEventListener('keydown', onAiEsc, true)
  if (refocus) editorRef.value?.focus()
}

function onAiDocDown(e) {
  const panel = document.querySelector('.ai-panel')
  if (panel && !panel.contains(e.target)) closeAi()   // 失焦即隐藏，不抢焦点（点击正常生效）
}

function onAiEsc(e) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    closeAi(true)
  }
}

// 拖动标题栏移动面板（限制在编辑区内）
function startAiDrag(e) {
  const panel = e.currentTarget.closest('.ai-panel')
  const rect = panel.getBoundingClientRect()
  const main = mainRef.value.getBoundingClientRect()
  const offX = e.clientX - rect.left
  const offY = e.clientY - rect.top
  const move = (ev) => {
    ai.value.x = Math.max(0, Math.min(ev.clientX - main.left - offX, main.width - rect.width))
    ai.value.y = Math.max(0, Math.min(ev.clientY - main.top - offY, main.height - 80))
  }
  const up = () => {
    document.removeEventListener('mousemove', move)
    document.removeEventListener('mouseup', up)
  }
  document.addEventListener('mousemove', move)
  document.addEventListener('mouseup', up)
}

// 选中内容时的快捷指令（面板输入框上方的 chips）
const AI_QUICK_ACTIONS = ['润色', '扩写', '总结要点', '翻译成英文', '修正错别字']

function aiQuick(q) {
  ai.value.instruction = q
  aiGenerate()
}

async function aiGenerate() {
  // 选中内容时 Enter 空提交 = 默认「润色」；只传图不写字 = 按图片内容整理成文（后端默认指令）
  const instruction = ai.value.instruction.trim()
    || (ai.value.selected ? '润色' : '')
  if ((!instruction && !(ai.value.images || []).length) || ai.value.loading) return
  ai.value.loading = true
  ai.value.error = ''
  try {
    const text = editorRef.value?.getText() || ''
    const context = text.split('\n').map((s) => s.trim()).filter(Boolean).slice(-20)
    const res = await noteAiAssist({ instruction, note_title: current.value?.title || '', context,
                                     selection: ai.value.selected || '', images: ai.value.images || [] })
    ai.value.preview = res.html  // 只预览，不写入；用户点「插入」才进文档
    clampAiPanel()               // 预览撑高面板后重新校准位置/高度，防止底部被编辑区裁掉
  } catch (e) {
    ai.value.error = e.message
  } finally {
    ai.value.loading = false
  }
}

// 生成结果撑高面板后：底部超出编辑区先整体上移；已到顶仍超高则限高，预览区内部滚动
function clampAiPanel() {
  nextTick(() => {
    const panel = document.querySelector('.ai-panel')
    const main = mainRef.value?.getBoundingClientRect()
    if (!panel || !main || ai.value.y === null) return
    const r = panel.getBoundingClientRect()
    if (r.bottom > main.bottom - 8) {
      ai.value.y = Math.max(8, ai.value.y - (r.bottom - main.bottom + 8))
    }
    const r2 = panel.getBoundingClientRect()
    if (r2.bottom > main.bottom - 8) {
      ai.value.maxH = Math.max(220, main.bottom - 8 - r2.top)
    }
  })
}

// 确认插入：HTML 片段写入光标处（编辑器的 change 事件会自动触发保存）
function aiInsert(replaceSelection = false) {
  if (!ai.value.preview) return
  editorRef.value?.insertHtml(ai.value.preview, { replaceSelection })
  closeAi(true)
}

// ---------- 页面操作 ----------

async function createPage(parent = null) {
  try {
    const res = await createNote(parent ? { parent_id: parent.id } : {})
    await loadTree()
    ElMessage.success(parent ? `已在「${parent.title || '无标题页面'}」下新建子页` : '已新建页面')
    open(res)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 页面排序（纯顺序操作：上移 / 置顶，无"置顶状态"概念） ----------

// 目录拖拽排序（通用逻辑与样式：composables/useTreeDnd.js + styles/tree-dnd.css + components/DndHandle.vue）
const dnd = useTreeDnd({
  items: notes,
  visible: displayTree,
  persist: updateNote,
  reload: loadTree,
  onMoved: (zone, target) => {
    // 移入收起的文件夹时自动展开，让用户看到落点
    if (zone === 'into' && collapsed.value.has(target.id)) {
      const s = new Set(collapsed.value)
      s.delete(target.id)
      collapsed.value = s
    }
  },
})

async function del(n) {
  try {
    await deleteNote(n.id)
    ElMessage.success('已删除')
    if (current.value?.id === n.id) {
      clearTimeout(saveTimer)
      dirty = false
      current.value = null
      const q = { ...route.query }
      delete q.noteId
      router.replace({ query: q })
    }
    await loadTree()
    if (searchResults.value !== null) onSearchInput()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  await loadTree()
  // F5 刷新后恢复上次选中的笔记（URL ?noteId=）
  const qid = Number(route.query.noteId)
  if (qid) {
    const n = notes.value.find((x) => x.id === qid)
    if (n) open(n)
  }
})
onBeforeUnmount(async () => {
  clearTimeout(saveTimer)
  document.removeEventListener('mousedown', onAiDocDown, true)
  document.removeEventListener('keydown', onAiEsc, true)
  if (dirty && editorRef.value) {
    latestHtml = editorRef.value.getHtml()
    await flushSave()
  }
})
</script>

<style scoped>
.notes-page { display: flex; height: calc(100vh - var(--chrome-h, 48px)); }

/* 左侧页面树：业内笔记本风格（Notion/语雀）——折叠箭头 + 图标芯片 + 悬浮操作 */
.notes-side {
  width: 280px; flex-shrink: 0; background: #fff;
  box-shadow: 0 2px 12px rgba(31, 45, 61, .08); display: flex; flex-direction: column; overflow: hidden;
}
.side-top { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border-bottom: 1px solid #f0f2f5; }
.side-top-row { display: flex; align-items: center; gap: 8px; }
.side-new { flex: 1; padding: 8px 4px; }
/* flex 布局下用 gap 控制间距，去掉 EP 相邻按钮的默认左外边距 */
.side-top-row .el-button + .el-button { margin-left: 0; }
.side-fold { font-size: 16px; color: #909399; cursor: pointer; padding: 4px; border-radius: 6px; flex-shrink: 0; }
.side-fold:hover { background: #f5f7fa; color: #303133; }
/* 分隔条：悬浮显示把手，按住横向拖动调宽 */
.side-resizer { width: 10px; flex-shrink: 0; cursor: col-resize; display: flex; align-items: center; justify-content: center; }
.side-resizer::after { content: ''; width: 3px; height: 36px; border-radius: 2px; background: transparent; transition: background-color .15s ease; }
.side-resizer:hover::after { background: #c0c4cc; }
/* 目录栏收起后的窄条：图标位置与收起前的收起图标对齐（距顶 18px、距左 16px） */
.side-expand {
  width: 36px; flex-shrink: 0; margin-right: 10px; padding: 14px 0 0 12px;
  background: #fff; box-shadow: 0 2px 12px rgba(31, 45, 61, .08);
  display: flex; justify-content: flex-start; cursor: pointer; color: #909399;
}
.side-expand .el-icon { padding: 4px; font-size: 16px; border-radius: 6px; }
.side-expand:hover { color: var(--grt-primary, #409eff); }
.tree { flex: 1; overflow-y: auto; padding: 8px; }
.tree-item {
  display: flex; align-items: center; gap: 2px; height: 34px; padding: 0 8px;
  border-radius: 6px; cursor: pointer; font-size: 14px; color: #303133;
  transition: background-color .12s ease;
}
.tree-item:hover { background: #f5f7fa; }
.tree-item.active { background: #e8f1fd; color: var(--grt-primary, #409eff); font-weight: 500; }
.tree-chevron {
  width: 20px; height: 20px; flex-shrink: 0; display: inline-flex;
  align-items: center; justify-content: center; border-radius: 4px; color: #909399;
}
.tree-chevron.has:hover { background: #e4e7ed; color: #303133; }
.tree-chevron .el-icon { font-size: 12px; transition: transform .15s ease; }
.tree-chevron.open .el-icon { transform: rotate(90deg); }
/* 条目图标：纯图标，不加底块 */
.tree-doc { color: #a8abb2; font-size: 15px; flex-shrink: 0; margin: 0 4px 0 2px; }
.tree-item.active .tree-doc { color: var(--grt-primary, #409eff); }
.tree-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-ops { display: none; gap: 2px; flex-shrink: 0; color: #909399; align-items: center; }
.tree-item:hover .tree-ops { display: inline-flex; }
.tree-ops .el-icon { padding: 3px; border-radius: 4px; font-size: 14px; }
.tree-ops .el-icon:hover { background: #e4e7ed; color: #303133; }
.side-empty { padding: 40px 12px; text-align: center; color: #c0c4cc; font-size: 13px; }

/* 右侧编辑区 */
.notes-main {
  flex: 1; background: #fff; border-radius: 10px; box-shadow: 0 2px 12px rgba(31, 45, 61, .08);
  display: flex; flex-direction: column; overflow: hidden; position: relative;
}
.main-top {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 24px 8px;
}
.title-input {
  flex: 1; border: none; outline: none; font-size: 24px; font-weight: 700; color: #303133;
  background: transparent; min-width: 0;
}
.title-input::placeholder { color: #c0c4cc; }
.main-ops { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.save-state { font-size: 12px; color: #909399; margin-right: 4px; }
.save-state.err { color: #f56c6c; }

.ai-selected {
  font-size: 12px; color: #7c5cff; background: #f4f0ff; border-radius: 6px;
  padding: 4px 10px; margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* AI 写作面板：位置由 placeAiPanel 计算（选区/光标附近，兜底中上方居中），可拖动换位 */
.ai-panel {
  position: absolute; top: 72px; right: 24px; z-index: 100; width: 640px;
  padding: 12px 14px; background: #fff; border: 1px solid #e4e7ed; border-radius: 12px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, .12);
  display: flex; flex-direction: column; overflow: hidden;
}
/* 限高时（生成内容很长）：只有预览区收缩滚动，标题/输入/按钮保持原位 */
.ai-panel-head, .ai-selected, .ai-input, .ai-quick, .ai-panel-ops { flex-shrink: 0; }
.ai-panel-head {
  font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px;
  cursor: move; user-select: none; display: flex; align-items: center; justify-content: space-between;
}
.ai-drag-hint { font-size: 11px; font-weight: 400; color: #c0c4cc; }
.ai-input {
  width: 100%; border: none; outline: none; font-size: 14px; color: #303133;
  padding: 6px 0; background: transparent; box-sizing: border-box;
}
.ai-input::placeholder { color: #c0c4cc; }
/* 选中内容的快捷指令 chips */
.ai-quick { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.ai-chip {
  height: 24px; padding: 0 10px; border: 1px solid #dcdfe6; border-radius: 12px;
  background: #fff; color: #606266; font-size: 12px; cursor: pointer;
}
.ai-chip:hover:not(:disabled) { border-color: var(--grt-ai, #7c5cff); color: var(--grt-ai, #7c5cff); }
.ai-chip:disabled { color: #c0c4cc; cursor: not-allowed; }
.ai-panel-ops { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.ai-hint { font-size: 12px; color: #c0c4cc; }
.ai-error { font-size: 12px; color: #f56c6c; margin-top: 6px; }
.ai-preview {
  max-height: 40vh; overflow-y: auto; margin-top: 8px; padding: 8px 2px 2px;
  border-top: 1px dashed #e4e7ed; font-size: 14px; line-height: 1.8; color: #303133;
  min-height: 0;   /* 面板限高时允许收缩，配合内部滚动 */
}
.ai-preview :deep(h1) { font-size: 20px; margin: 8px 0 4px; }
.ai-preview :deep(h2) { font-size: 17px; margin: 6px 0 4px; }
.ai-preview :deep(h3) { font-size: 15px; margin: 4px 0 2px; }
.ai-preview :deep(p) { margin: 4px 0; }
.ai-preview :deep(ul), .ai-preview :deep(ol) { padding-left: 20px; margin: 4px 0; }
.ai-preview :deep(blockquote) { border-left: 3px solid #dcdfe6; padding-left: 10px; margin: 6px 0; color: #606266; }
.ai-preview :deep(pre) { background: #f5f7fa; border-radius: 6px; padding: 8px 10px; font-size: 13px; overflow-x: auto; }
.ai-preview :deep(hr) { border: none; border-top: 1px solid #e4e7ed; margin: 10px 0; }
</style>
