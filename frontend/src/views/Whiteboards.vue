<template>
  <div class="wb-page">
    <!-- 左侧：搜索 + 画板树（可折叠，与记事本一致的界面模式） -->
    <div class="wb-side">
      <div class="side-top">
        <el-input
          v-model="keyword" placeholder="搜索画板" clearable :prefix-icon="Search"
          @input="onSearchInput" @clear="searchResults = null"
        />
        <!-- 新建时选引擎；建好后引擎固定（数据格式不同不能互转）。文件夹仅作目录分组，无引擎 -->
        <el-dropdown trigger="click" @command="(eng) => eng === '__folder' ? createFolder() : createPage(null, eng)">
          <el-button type="primary" :icon="Plus">新建</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excalidraw">Excalidraw（手绘风）</el-dropdown-item>
              <el-dropdown-item command="drawio">drawio（图形库全）</el-dropdown-item>
              <el-dropdown-item command="__folder" divided>📂 新建文件夹</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div v-loading="treeLoading" class="tree">
        <template v-if="displayTree.length">
          <div
            v-for="n in displayTree" :key="n.id"
            class="tree-item" :class="{ active: current?.id === n.id }"
            :style="{ paddingLeft: 6 + n.level * 16 + 'px' }"
            @click="onItemClick(n)"
          >
            <span
              class="tree-chevron" :class="{ has: n.hasChildren, open: n.hasChildren && !collapsed.has(n.id) }"
              @click.stop="toggleCollapse(n)"
            >
              <el-icon v-if="n.hasChildren"><ArrowRight /></el-icon>
            </span>
            <el-icon class="tree-doc"><Folder v-if="n.kind === 'folder'" /><Brush v-else /></el-icon>
            <span class="tree-title">{{ n.title || (n.kind === 'folder' ? '未命名文件夹' : '无标题画板') }}</span>
            <el-tag v-if="n.kind !== 'folder' && n.engine === 'drawio'" size="small" type="warning" effect="plain" class="engine-tag">drawio</el-tag>
            <span class="tree-ops" @click.stop>
              <el-icon v-if="n.level < 2" title="新增子页" @click="createPage(n)"><Plus /></el-icon>
              <el-icon title="上移" @click="moveUp(n)"><ArrowUp /></el-icon>
              <el-icon title="置顶" @click="moveTop(n)"><Top /></el-icon>
              <el-dropdown trigger="click" placement="bottom-end" @command="(cmd) => onMenu(cmd, n)">
                <el-icon title="更多" class="tree-more"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="rename">重命名</el-dropdown-item>
                    <el-dropdown-item class="move-host">
                      <el-dropdown trigger="hover" placement="right-start" @command="(cmd) => onMovePick(cmd, n)">
                        <span class="tree-move-label">移入文件夹<el-icon><ArrowRight /></el-icon></span>
                        <template #dropdown>
                          <el-dropdown-menu>
                            <el-dropdown-item v-if="n.parent_id" command="__root">（移到根级）</el-dropdown-item>
                            <el-dropdown-item v-for="f in moveTargets(n)" :key="f.id" :command="f.id">
                              {{ f.title || '未命名文件夹' }}
                            </el-dropdown-item>
                            <el-dropdown-item command="__new" divided>＋ 新建文件夹</el-dropdown-item>
                          </el-dropdown-menu>
                        </template>
                      </el-dropdown>
                    </el-dropdown-item>
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

    <!-- 右侧：画布编辑器（Excalidraw / drawio，按画板 engine 分发） -->
    <div class="wb-main">
      <template v-if="current">
        <div class="main-top">
          <input v-model="current.title" class="title-input" placeholder="无标题画板" maxlength="200" @input="onTitleInput" />
          <!-- AI 生成：两种引擎都支持（excalidraw/drawio 各自实现转换层）；大按钮，与其它编辑器一致 -->
          <el-button ref="aiBtnRef" class="ai-btn" :icon="MagicStick" @click="aiVisible = true">AI 生成</el-button>
          <div class="main-ops">
            <span class="save-state" :class="{ err: saveState === '保存失败' }">{{ saveState }}</span>
          </div>
        </div>
        <div class="editor-wrap">
          <!-- :key = 画板 id：切页时整体重建，content 只在挂载时读入 -->
          <component
            :is="current.engine === 'drawio' ? DrawioBoard : ExcalidrawBoard"
            :key="current.id"
            ref="editorRef" :initial="current.content" @change="onEditorChange"
          />
        </div>
      </template>
      <el-empty v-else description="选择左侧画板，或新建一个开始涂画" />
    </div>

    <!-- AI 面板（统一 AiPromptPanel）：描述 + 模式（自动/替换/追加/修改/汇总）→ 后端 LLM → 编辑器转换渲染 -->
    <AiPromptPanel
      v-model="aiVisible" title="✨ AI 生成" :anchor="aiBtnRef"
      :modes="WB_AI_MODES" v-model:mode="aiMode"
      :placeholder="aiPlaceholder" :loading="aiGenerating"
      hint="替换/修改覆盖当前画布（执行前确认）；追加保留现有内容；汇总不动画布。可附图按图生成"
      @submit="onBoardAiSubmit"
    />

    <!-- 汇总结果：只读展示 + 一键复制 -->
    <el-dialog v-model="summaryVisible" title="画布汇总" width="520px">
      <el-input v-model="summaryText" type="textarea" :rows="10" readonly />
      <template #footer>
        <el-button @click="summaryVisible = false">关闭</el-button>
        <el-button type="primary" @click="copySummary">复制</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
// 画板页：界面模式对齐记事本（Notes.vue）——左树右编辑器 + 防抖自动保存。
// 双引擎：excalidraw 存其序列化 JSON；drawio 存 {"xml": ...}；前端不解析，直接透传存储。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, ArrowUp, Brush, Folder, MagicStick, MoreFilled, Plus, Search, Top } from '@element-plus/icons-vue'
import {
  createWhiteboard, deleteWhiteboard, generateBoardContent, getWhiteboard,
  searchWhiteboards, updateWhiteboard, whiteboardTree,
} from '../api'
import ExcalidrawBoard from './whiteboard/ExcalidrawBoard.vue'
import DrawioBoard from './whiteboard/DrawioBoard.vue'
import AiPromptPanel from '../components/AiPromptPanel.vue'

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

let latestContent = ''   // 编辑器最近一次 change 的 JSON（flushSave 以它为准）
let saveTimer = null
let saving = false
let dirty = false

// ---------- AI 生成（excalidraw/drawio 双引擎，编辑器各自实现 applyAiContent/getContext） ----------
const aiVisible = ref(false)
const aiDesc = ref('')
const aiMode = ref('auto')
const aiImages = ref([])   // 附图（data URL），成功后清空
const aiGenerating = ref(false)
const aiBtnRef = ref(null)
const summaryVisible = ref(false)
const summaryText = ref('')

const WB_AI_MODES = [
  { value: 'auto', label: '自动判断' },
  { value: 'replace', label: '替换画布' },
  { value: 'append', label: '追加内容' },
  { value: 'modify', label: '修改内容' },
  { value: 'summarize', label: '汇总画布' },
]

// 面板提交：回填状态后走既有生成流程
function onBoardAiSubmit({ instruction, images, mode }) {
  aiDesc.value = instruction
  aiImages.value = images
  if (mode) aiMode.value = mode
  generateAi()
}

const AI_PLACEHOLDERS = {
  auto: '描述想做的事，例如：画一个举手的小人；再加一个审批节点；把开始节点改成圆形；总结一下画布',
  replace: '描述想要的内容，例如：请假审批流程，主管审批通过后人事备案；或：画一个举手的小人',
  append: '描述要追加的内容，例如：在右侧再加一个人事复核节点；旁边再画一只猫',
  modify: '描述怎么改，例如：把主管审批改成部门经理审批；删除结束节点；把小人换成两个人',
  summarize: '可选：说明想怎么汇总，例如：按阶段分组概括这张流程图',
}
const aiPlaceholder = computed(() => AI_PLACEHOLDERS[aiMode.value] || AI_PLACEHOLDERS.auto)

async function generateAi() {
  const desc = aiDesc.value.trim()
  // 只传图不写字也允许：后端会按图片内容生成（视觉模型路径）
  if (!desc && !aiImages.value.length) {
    ElMessage.warning('先描述一下想做的事，或上传图片')
    return
  }
  const ctx = editorRef.value?.getContext?.() || []
  if (aiMode.value === 'summarize' && !ctx.length && !aiImages.value.length) {
    ElMessage.warning('画布是空的，没有内容可汇总')
    return
  }
  aiGenerating.value = true
  try {
    const d = await generateBoardContent(desc, aiMode.value, ctx, aiImages.value)
    if (d.mode === 'summarize') {
      summaryText.value = d.summary || ''
      summaryVisible.value = true
      aiVisible.value = false
      aiDesc.value = ''
      aiImages.value = []
      return
    }
    if (!d.nodes?.length && !d.elements?.length && !d.parts?.length && !d.headers?.length) {
      ElMessage.warning('没有生成有效内容，换个说法再试试')
      return
    }
    // 替换/修改是覆盖语义，画布已有内容时先确认；追加不动现有内容，无需确认。
    // 修改且有选中元素时是局部替换（excalidraw 支持），确认文案区分两种范围
    const selCount = ctx.filter((c) => c.selected).length
    if ((d.mode === 'replace' || d.mode === 'modify') && ctx.length) {
      const scoped = d.mode === 'modify' && selCount > 0
      try {
        await ElMessageBox.confirm(
          scoped ? `生成结果将替换选中的 ${selCount} 个元素，其余内容不变，继续？` : '生成结果将替换当前画布内容，继续？',
          'AI 生成', { confirmButtonText: scoped ? '替换选中' : '替换', cancelButtonText: '取消', type: 'warning' },
        )
      } catch { return }
    }
    const applied = editorRef.value?.applyAiContent(d, { append: d.mode === 'append' })
    if (applied === false) {
      ElMessage.warning('画板还没加载好，稍候再试')
      return
    }
    aiVisible.value = false
    aiDesc.value = ''
    aiImages.value = []
    ElMessage.success(`已生成「${d.title || '图'}」，可在画布上继续调整`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiGenerating.value = false
  }
}

async function copySummary() {
  try {
    await navigator.clipboard.writeText(summaryText.value)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择文字复制')
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

// ---------- 文件夹（新建 / 重命名 / 移入，对齐智能表目录的 ⋯ 菜单） ----------

const folders = computed(() => boards.value.filter((x) => x.kind === 'folder'))

// n 的子孙 id 集合：移入文件夹时排除自身与子孙（前端预过滤，后端仍有防环兜底）
function descendantIds(id) {
  const out = new Set()
  let grew = true
  while (grew) {
    grew = false
    for (const x of boards.value) {
      if (x.parent_id && (x.parent_id === id || out.has(x.parent_id)) && !out.has(x.id)) {
        out.add(x.id)
        grew = true
      }
    }
  }
  return out
}

// 可选目标文件夹：排除自身、子孙与当前所在文件夹
function moveTargets(n) {
  const excl = descendantIds(n.id)
  excl.add(n.id)
  if (n.parent_id) excl.add(n.parent_id)
  return folders.value.filter((f) => !excl.has(f.id))
}

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

// 移入文件夹二级菜单：__root=移到根级，__new=新建文件夹并移入，其余=目标文件夹 id
async function onMovePick(cmd, n) {
  try {
    if (cmd === '__root') {
      await updateWhiteboard(n.id, { parent_id: null })
    } else if (cmd === '__new') {
      const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', { inputValue: '未命名文件夹' })
      if (value == null) return
      const folder = await createWhiteboard({ kind: 'folder', title: value.trim() || '未命名文件夹' })
      await updateWhiteboard(n.id, { parent_id: folder.id })
    } else {
      await updateWhiteboard(n.id, { parent_id: cmd })
    }
    await loadTree()
  } catch (e) {
    if (!isCancel(e)) ElMessage.error(e.message || e)
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

// 同级兄弟按当前展示顺序（与后端一致：pinned > sort > updated_at）
function siblingsOf(n) {
  return boards.value
    .filter((x) => (x.parent_id || null) === (n.parent_id || null))
    .sort((a, b) => ((b.pinned - a.pinned) || (a.sort - b.sort)
      || (b.updated_at > a.updated_at ? 1 : b.updated_at < a.updated_at ? -1 : 0)))
}

// 按新顺序重排同级 sort（0,10,20…），顺带清掉旧的 pinned 标记
async function applyOrder(ordered) {
  const jobs = []
  ordered.forEach((n, i) => {
    const sort = i * 10
    if (n.sort !== sort || n.pinned) jobs.push(updateWhiteboard(n.id, { sort, pinned: false }))
  })
  await Promise.all(jobs)
  await loadTree()
}

async function moveUp(n) {
  const sibs = siblingsOf(n)
  const i = sibs.findIndex((x) => x.id === n.id)
  if (i <= 0) {
    ElMessage.info('已经在最前面了')
    return
  }
  ;[sibs[i - 1], sibs[i]] = [sibs[i], sibs[i - 1]]
  await applyOrder(sibs)
}

async function moveTop(n) {
  const sibs = siblingsOf(n)
  const i = sibs.findIndex((x) => x.id === n.id)
  if (i <= 0) {
    ElMessage.info('已经在最前面了')
    return
  }
  sibs.unshift(...sibs.splice(i, 1))
  await applyOrder(sibs)
  ElMessage.success('已置顶')
}

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
  clearTimeout(saveTimer)
  if (dirty && editorRef.value) {
    latestContent = editorRef.value.getContent()
    await flushSave()
  }
})
</script>

<style scoped>
.wb-page { display: flex; gap: 16px; height: calc(100vh - 110px); }

/* 左侧画板树：与记事本一致的交互（折叠箭头 + 图标 + 悬浮操作） */
.wb-side {
  width: 280px; flex-shrink: 0; background: #fff; border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .06); display: flex; flex-direction: column; overflow: hidden;
}
.side-top { display: flex; gap: 8px; padding: 12px; border-bottom: 1px solid #ebeef5; }
.tree { flex: 1; overflow-y: auto; padding: 8px 6px; }
.tree-item {
  display: flex; align-items: center; gap: 2px; height: 32px; padding: 0 6px;
  border-radius: 6px; cursor: pointer; font-size: 14px; color: #303133;
  transition: background-color .12s ease;
}
.tree-item:hover { background: #f5f7fa; }
.tree-item.active { background: #ecf5ff; color: #409eff; font-weight: 500; }
.tree-chevron {
  width: 20px; height: 20px; flex-shrink: 0; display: inline-flex;
  align-items: center; justify-content: center; border-radius: 4px; color: #909399;
}
.tree-chevron.has:hover { background: #e4e7ed; color: #303133; }
.tree-chevron .el-icon { font-size: 12px; transition: transform .15s ease; }
.tree-chevron.open .el-icon { transform: rotate(90deg); }
.tree-doc { color: #a8abb2; font-size: 15px; flex-shrink: 0; margin: 0 3px; }
.tree-item.active .tree-doc { color: #409eff; }
.tree-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.engine-tag { flex-shrink: 0; transform: scale(.85); transform-origin: left center; margin-right: 2px; }
.tree-ops { display: none; gap: 2px; flex-shrink: 0; color: #909399; align-items: center; }
.tree-item:hover .tree-ops { display: inline-flex; }
.tree-ops .el-icon { padding: 3px; border-radius: 4px; font-size: 14px; }
.tree-ops .el-icon:hover { background: #e4e7ed; color: #303133; }
.side-empty { padding: 40px 12px; text-align: center; color: #c0c4cc; font-size: 13px; }

/* 右侧编辑区 */
.wb-main {
  flex: 1; background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0, 0, 0, .06);
  display: flex; flex-direction: column; overflow: hidden; position: relative;
}
.main-top {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 24px 8px;
}
.title-input {
  flex: 1; max-width: 420px; border: none; outline: none; font-size: 24px; font-weight: 700; color: #303133;
  background: transparent; min-width: 0;
}
.title-input::placeholder { color: #c0c4cc; }
/* AI 生成按钮贴标题左侧区域，保存状态靠右 */
.main-ops { display: flex; align-items: center; gap: 6px; flex-shrink: 0; margin-left: auto; }
.save-state { font-size: 12px; color: #909399; margin-right: 4px; }
.save-state.err { color: #f56c6c; }
.ai-hint { font-size: 12px; color: #909399; margin-top: 8px; }
.ai-modes { margin-bottom: 10px; }
.editor-wrap { flex: 1; min-height: 0; padding: 4px 16px 16px; }
</style>

<!-- ⋯ 菜单的弹出层被 el-dropdown 传送到 body，scoped 样式够不到，这里用全局类（与 Notes.vue 保持一致） -->
<style>
.tree-move-label { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; }
.tree-move-label .el-icon { font-size: 12px; color: #909399; }
</style>
