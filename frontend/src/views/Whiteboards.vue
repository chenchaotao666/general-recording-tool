<template>
  <div class="wb-page">
    <!-- 左侧：搜索 + 画板树（可折叠，与记事本一致的界面模式）；宽度可拖拽调节，可整体收起 -->
    <div v-show="!sideCollapsed" class="wb-side" :style="{ width: sideWidth + 'px' }">
      <div class="side-top">
        <div class="side-top-row">
          <el-icon class="side-fold" title="收起目录" @click="collapseSide"><Fold /></el-icon>
          <el-input
            v-model="keyword" placeholder="搜索画板" clearable :prefix-icon="Search"
            @input="onSearchInput" @clear="searchResults = null"
          />
        </div>
        <div class="side-top-row">
          <!-- 两个引擎入口并列；建好后引擎固定（excalidraw/drawio 数据格式不同不能互转），文件夹仅作目录分组 -->
          <el-button type="primary" :icon="Plus" class="side-new" @click="createPage(null, 'excalidraw')">手绘风</el-button>
          <el-button class="side-new" @click="createPage(null, 'drawio')">图形全</el-button>
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
            <el-icon class="tree-doc">
              <Folder v-if="n.kind === 'folder'" />
              <Connection v-else-if="n.engine === 'drawio'" />
              <Brush v-else />
            </el-icon>
            <span class="tree-title">{{ n.title || (n.kind === 'folder' ? '未命名文件夹' : '无标题画板') }}</span>
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
          {{ keyword ? '没有匹配的画板' : '还没有画板，点上方「新建」开始' }}
        </div>
      </div>
    </div>
    <!-- 分隔条：拖拽调节目录栏宽度 -->
    <div v-show="!sideCollapsed" class="side-resizer" @mousedown.prevent="startSideResize" />
    <!-- 收起后的窄条：点击展开 -->
    <div v-show="sideCollapsed" class="side-expand" title="展开目录" @click="expandSide">
      <el-icon><Expand /></el-icon>
    </div>

    <!-- 右侧：画布编辑器（Excalidraw / drawio，按画板 engine 分发） -->
    <div class="wb-main">
      <template v-if="current">
        <div class="main-top" :class="{ 'main-top-drawio': current.engine === 'drawio' }">
          <input v-model="current.title" class="title-input" placeholder="无标题画板" maxlength="200" @input="onTitleInput" />
          <!-- AI 生成：两种引擎都支持（excalidraw/drawio 各自实现转换层）；大按钮，与其它编辑器一致 -->
          <!-- drawio 是 iframe 无法注入其工具栏，AI 入口与标题一起悬浮在画布左上角（与记事本「AI 写作」同款紫色文字按钮） -->
          <button v-if="current.engine === 'drawio'" ref="aiBtnRef" type="button" class="wb-ai-btn" @click="onHeaderAi">
            <el-icon><MagicStick /></el-icon><span aria-live="polite">{{ aiToolbarText }}</span>
          </button>
          <div class="main-ops">
            <span class="save-state" :class="{ err: saveState === '保存失败' }">{{ saveState }}</span>
          </div>
        </div>
        <div class="editor-wrap">
          <!-- :key = 画板 id：切页时整体重建，content 只在挂载时读入 -->
          <component
            :is="current.engine === 'drawio' ? DrawioBoard : ExcalidrawBoard"
            :key="current.id"
            ref="editorRef" :initial="current.content" :ai-status-text="aiToolbarText" @change="onEditorChange"
            @ai="onToolbarAi"
          />
        </div>
      </template>
      <el-empty v-else description="选择左侧画板，或新建一个开始涂画" />
    </div>

    <!-- AI 自动判断需求；写入画布前展示变更说明并确认。 -->
    <AiPromptPanel
      :key="`${current?.id}-${aiDraftVersion}`" preserve-draft
      v-model="aiVisible" title="✨ AI 生成" :anchor="aiAnchor"
      placeholder="描述想做的事，例如：画一个举手的小人；把选中图形改成红色；总结一下画布" :loading="aiGenerating"
      hint="先预览生成效果，确认后应用。可附图按图生成"
      :confirmation="aiPending ? [] : null" visual-only
      :preview="aiPending?.preview || ''" :loading-text="aiStage"
      :application-mode="aiPending?.result.mode || ''" :allow-mode-change="aiPending?.allowModeChange || false"
      :result="summaryText" result-title="画布汇总" :error="aiError"
      @confirm="applyPendingAi" @cancel-confirmation="aiPending = null"
      @submit="onBoardAiSubmit"
    />


  </div>
</template>

<script setup>
// 画板页：界面模式对齐记事本（Notes.vue）——左树右编辑器 + 防抖自动保存。
// 双引擎：excalidraw 存其序列化 JSON；drawio 存 {"xml": ...}；前端不解析，直接透传存储。
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Brush, Connection, Expand, Fold, Folder, FolderAdd, MagicStick, MoreFilled, Plus, Search } from '@element-plus/icons-vue'
import {
  createWhiteboard, deleteWhiteboard, generateBoardContent, getWhiteboard,
  searchWhiteboards, updateWhiteboard, whiteboardTree,
} from '../api'
import ExcalidrawBoard from './whiteboard/ExcalidrawBoard.vue'
import DrawioBoard from './whiteboard/DrawioBoard.vue'
import AiPromptPanel from '../components/AiPromptPanel.vue'
import DndHandle from '../components/DndHandle.vue'
import { useTreeDnd } from '../composables/useTreeDnd.js'

const route = useRoute()
const router = useRouter()

const boards = ref([])          // 扁平列表（后端已排好序）
const treeLoading = ref(false)
const current = ref(null)       // 当前打开的画板（含 content JSON）
const keyword = ref('')
const searchResults = ref(null) // 非 null 时展示搜索结果（平铺）
const saveState = ref('')
const editorRef = ref(null)
const collapsed = ref(new Set())

// 目录栏：宽度可拖拽调节（200~480px，记住选择）；可整体收起为窄条
// 存储键带版本（_v3）：默认值调整时换版本，忽略旧键里的历史值
const sideWidth = ref(Number(localStorage.getItem('grt_wb_side_w_v3')) || 280)
const sideCollapsed = ref(localStorage.getItem('grt_wb_side_collapsed') === '1')
function collapseSide() { sideCollapsed.value = true; localStorage.setItem('grt_wb_side_collapsed', '1') }
function expandSide() { sideCollapsed.value = false; localStorage.setItem('grt_wb_side_collapsed', '0') }
function startSideResize(e) {
  const startX = e.clientX
  const startW = sideWidth.value
  const onMove = (ev) => { sideWidth.value = Math.min(480, Math.max(200, startW + ev.clientX - startX)) }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    // 只有真的拖过才记住宽度，避免误点分隔条把当前默认值存成"用户选择"
    if (sideWidth.value !== startW) localStorage.setItem('grt_wb_side_w_v3', String(sideWidth.value))
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

let latestContent = ''   // 编辑器最近一次 change 的 JSON（flushSave 以它为准）
let saveTimer = null
let saving = false
let dirty = false

// ---------- AI 生成（excalidraw/drawio 双引擎，编辑器各自实现 applyAiContent/getContext） ----------
const aiVisible = ref(false)
const aiDesc = ref('')
const aiImages = ref([])   // 附图（data URL），成功后清空
const aiGenerating = ref(false)
const aiStage = ref('AI 生成中…')
const aiPending = shallowRef(null)
const aiError = ref('')
const aiDraftVersion = ref(0)
const aiToolbarText = computed(() => aiGenerating.value ? aiStage.value
  : aiPending.value ? 'AI 待确认'
    : aiError.value ? 'AI 生成失败'
      : summaryText.value ? 'AI 查看汇总' : 'AI 生成')
let aiRequest = 0
watch(() => current.value?.id, () => {
  aiPending.value = null
  aiError.value = ''
  summaryText.value = ''
  aiVisible.value = false
  aiRequest++
  aiGenerating.value = false
}, { flush: 'sync' })
const aiBtnRef = ref(null)
// AI 面板锚点：drawio = 头部按钮；excalidraw = 画布工具栏最左侧注入的按钮（.wb-ai-tool）
const aiAnchor = ref(null)
function onToolbarAi() {
  aiAnchor.value = document.querySelector('.wb-excalidraw .wb-ai-tool')
  aiVisible.value = true
}
function onHeaderAi() {
  aiAnchor.value = aiBtnRef.value
  aiVisible.value = true
}
const summaryText = ref('')

// 面板提交：回填状态后走既有生成流程
function onBoardAiSubmit({ instruction, images }) {
  aiDesc.value = instruction
  aiImages.value = images
  generateAi()
}

async function generateAi() {
  if (aiGenerating.value) return
  const desc = aiDesc.value.trim()
  // 只传图不写字也允许：后端会按图片内容生成（视觉模型路径）
  if (!desc && !aiImages.value.length) {
    ElMessage.warning('先描述一下想做的事，或上传图片')
    return
  }
  const editor = editorRef.value
  const boardId = current.value?.id
  const ctx = editor?.getContext?.() || []
  const unchanged = () => current.value?.id === boardId && editorRef.value === editor
    && JSON.stringify(editor?.getContext?.() || []) === JSON.stringify(ctx)
  const request = ++aiRequest
  aiPending.value = null
  aiError.value = ''
  summaryText.value = ''
  aiGenerating.value = true
  aiStage.value = 'AI 生成中…'
  try {
    const d = await generateBoardContent(desc, 'auto', ctx, aiImages.value)
    if (request !== aiRequest) return
    if (current.value?.id !== boardId || editorRef.value !== editor) {
      ElMessage.info('画板已切换，本次生成结果未应用')
      return
    }
    if (d.mode === 'summarize') {
      summaryText.value = d.summary || ''
      aiDesc.value = ''
      aiImages.value = []
      return
    }
    if (!d.nodes?.length && !d.elements?.length && !d.parts?.length && !d.headers?.length && !d.edits?.length) {
      aiError.value = '没有生成有效内容，换个说法再试试'
      ElMessage.warning('没有生成有效内容，换个说法再试试')
      return
    }
    if (request !== aiRequest) return
    aiStage.value = 'AI 渲染预览中…'
    const preview = await editor.renderAiDraft(d, { fullScene: true, focusChanges: true })
    if (request !== aiRequest) return
    if (!preview) throw new Error('预览生成失败，请重试')
    const allowModeChange = ['append', 'replace'].includes(d.mode) && !d.attachTo && !d.parts?.some(p => p.attachTo)
    aiPending.value = { result: d, preview, editor, unchanged, allowModeChange }
  } catch (e) {
    if (request === aiRequest) aiError.value = e.message || '生成失败，请重试'
  } finally {
    if (request === aiRequest) aiGenerating.value = false
  }
}

function applyPendingAi(mode) {
  if (aiGenerating.value) return
  const pending = aiPending.value
  if (!pending) return
  if (!pending.unchanged()) {
    aiPending.value = null
    ElMessage.info('画布或选区已改变，请重新生成，避免覆盖新修改')
    return
  }
  try {
    const d = pending.allowModeChange && ['append', 'replace'].includes(mode) && mode !== pending.result.mode
      ? { ...pending.result, mode } : pending.result
    const applied = pending.editor.applyAiContent(d, { append: d.mode === 'append' })
    if (applied === false) {
      ElMessage.warning('画板还没加载好，稍候再试')
      return
    }
    aiPending.value = null
    aiVisible.value = false
    aiDraftVersion.value++
    aiDesc.value = ''
    aiImages.value = []
    ElMessage.success(`已生成「${d.title || '图'}」，可在画布上继续调整`)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

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

// ---------- 文件夹（新建 / 重命名，对齐智能表目录的 ⋯ 菜单） ----------

function isCancel(e) {
  return e === 'cancel' || e === 'close'
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', { inputValue: '未命名文件夹' })
    if (value == null) return
    await createWhiteboard({ kind: 'folder', title: value.trim() || '未命名文件夹' })
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
      await updateWhiteboard(n.id, { title: value.trim() })
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
  const byId = new Map(boards.value.map((n) => [n.id, { ...n, children: [] }]))
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
    boards.value = (await whiteboardTree()).whiteboards
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
    searchResults.value = (await searchWhiteboards(kw)).whiteboards.filter((x) => x.kind !== 'folder')
  } catch (e) {
    ElMessage.error(e.message)
  }
}, 300)

// ---------- 编辑器 ----------

function onEditorChange(json) {
  // 编辑器加载初始内容时也会触发一次 change，内容没变就不算脏
  if (json === latestContent) return
  latestContent = json
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
    const res = await updateWhiteboard(current.value.id, { content: latestContent })
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
    latestContent = editorRef.value.getContent()
    await flushSave()
  }
  saveState.value = ''
  try {
    // 先加载再切换：旧内容保持显示直到新画板就绪，避免清空 → 空态 → 新内容的闪烁
    const full = await getWhiteboard(n.id)
    current.value = full
    latestContent = full.content || ''
    dirty = false
    // 选中态同步到 URL query，F5 刷新后恢复
    router.replace({ query: { ...route.query, wbId: full.id } })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

const onTitleInput = debounce(async () => {
  if (!current.value) return
  try {
    await updateWhiteboard(current.value.id, { title: current.value.title })
    const item = boards.value.find((x) => x.id === current.value.id)
    if (item) item.title = current.value.title
    saveState.value = `已保存 ${new Date().toTimeString().slice(0, 5)}`
  } catch (e) {
    ElMessage.error(e.message)
  }
}, 600)

// ---------- 页面操作 ----------

async function createPage(parent = null, engine = 'excalidraw') {
  try {
    // 子页继承父页引擎（树上点 + 时不弹引擎选择）；顶级页用新建下拉选的引擎
    const eng = parent ? (parent.engine || 'excalidraw') : engine
    const res = await createWhiteboard(parent ? { parent_id: parent.id, engine: eng } : { engine: eng })
    await loadTree()
    ElMessage.success(parent ? `已在「${parent.title || '无标题画板'}」下新建子页` : '已新建画板')
    open(res)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 页面排序（纯顺序操作：上移 / 置顶，无"置顶状态"概念） ----------

// 目录拖拽排序（通用逻辑与样式：composables/useTreeDnd.js + styles/tree-dnd.css + components/DndHandle.vue）
const dnd = useTreeDnd({
  items: boards,
  visible: displayTree,
  persist: updateWhiteboard,
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
    await deleteWhiteboard(n.id)
    ElMessage.success('已删除')
    if (current.value?.id === n.id) {
      clearTimeout(saveTimer)
      dirty = false
      current.value = null
      const q = { ...route.query }
      delete q.wbId
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
  // F5 刷新后恢复上次选中的画板（URL ?wbId=）
  const qid = Number(route.query.wbId)
  if (qid) {
    const n = boards.value.find((x) => x.id === qid)
    if (n) open(n)
  }
})

onBeforeUnmount(async () => {
  aiRequest++
  clearTimeout(saveTimer)
  if (dirty && editorRef.value) {
    latestContent = editorRef.value.getContent()
    await flushSave()
  }
})
</script>

<style scoped>
.wb-page { display: flex; height: calc(100vh - var(--chrome-h, 48px)); }

/* 左侧画板树：与记事本一致的交互（折叠箭头 + 图标芯片 + 悬浮操作） */
.wb-side {
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
.wb-main {
  flex: 1; background: #fff; border-radius: 10px; box-shadow: 0 2px 12px rgba(31, 45, 61, .08);
  display: flex; flex-direction: column; overflow: hidden; position: relative;
}
/* 标题悬浮在画布左上角（不占独立行），画布占满整个右侧面板；高度固定 36px，两个引擎一致 */
.main-top {
  position: absolute; top: 18px; left: 12px; z-index: 20; max-width: 60%;
  display: flex; align-items: center; gap: 10px;
  height: 36px; box-sizing: border-box; padding: 0 12px; background: rgba(255, 255, 255, .92);
  border: 1px solid #ebeef5; border-radius: 8px; box-shadow: 0 2px 8px rgba(31, 45, 61, .08);
}
/* drawio 的 iframe 顶部自带菜单栏+工具栏（约 70px），左侧是图形库面板；
   悬浮条放到画布区右上角（drawio 在那里没有控件，也不受图形库面板宽度变化影响） */
.main-top-drawio { top: 31px; left: 800px; }
.title-input {
  flex: 1; max-width: 300px; border: none; outline: none; font-size: 15px; font-weight: 600; color: #303133;
  background: transparent; min-width: 0;
}
.title-input::placeholder { color: #c0c4cc; }
/* drawio 的 AI 入口：悬浮标题条内的紫色文字按钮（与记事本「AI 写作」/excalidraw 工具栏按钮同款） */
.wb-ai-btn {
  display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0;
  border: none; background: transparent; padding: 4px 6px; border-radius: 6px;
  color: var(--grt-ai, #7c5cff); font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap;
}
.wb-ai-btn:hover { background: #f4f0ff; }
/* AI 生成按钮贴标题左侧区域，保存状态靠右 */
.main-ops { display: flex; align-items: center; gap: 6px; flex-shrink: 0; margin-left: auto; }
.save-state { font-size: 12px; color: #909399; margin-right: 4px; }
.save-state.err { color: #f56c6c; }
.ai-hint { font-size: 12px; color: #909399; margin-top: 8px; }
.ai-modes { margin-bottom: 10px; }
.editor-wrap { flex: 1; min-height: 0; padding: 0; }
</style>
