<template>
  <div class="wb-page">
    <!-- 左侧：搜索 + 画板树（可折叠，与记事本一致的界面模式） -->
    <div class="wb-side">
      <div class="side-top">
        <el-input
          v-model="keyword" placeholder="搜索画板" clearable :prefix-icon="Search"
          @input="onSearchInput" @clear="searchResults = null"
        />
        <!-- 新建时选引擎；建好后引擎固定（数据格式不同不能互转） -->
        <el-dropdown trigger="click" @command="(eng) => createPage(null, eng)">
          <el-button type="primary" :icon="Plus">新建</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excalidraw">Excalidraw（手绘风）</el-dropdown-item>
              <el-dropdown-item command="drawio">drawio（图形库全）</el-dropdown-item>
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
            @click="open(n)"
          >
            <span
              class="tree-chevron" :class="{ has: n.hasChildren, open: n.hasChildren && !collapsed.has(n.id) }"
              @click.stop="toggleCollapse(n)"
            >
              <el-icon v-if="n.hasChildren"><ArrowRight /></el-icon>
            </span>
            <el-icon class="tree-doc"><Brush /></el-icon>
            <span class="tree-title">{{ n.title || '无标题画板' }}</span>
            <el-tag v-if="n.engine === 'drawio'" size="small" type="warning" effect="plain" class="engine-tag">drawio</el-tag>
            <span class="tree-ops" @click.stop>
              <el-icon v-if="n.level < 2" title="新增子页" @click="createPage(n)"><Plus /></el-icon>
              <el-icon title="上移" @click="moveUp(n)"><ArrowUp /></el-icon>
              <el-icon title="置顶" @click="moveTop(n)"><Top /></el-icon>
              <el-icon title="删除" @click="del(n)"><Delete /></el-icon>
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
          <div class="main-ops">
            <span class="save-state" :class="{ err: saveState === '保存失败' }">{{ saveState }}</span>
            <!-- AI 生成：目前只支持 excalidraw 画板（drawio 引擎待接入） -->
            <el-button
              v-if="current.engine !== 'drawio'" size="small" type="primary" plain
              :icon="MagicStick" @click="aiVisible = true"
            >AI 生成</el-button>
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

    <!-- AI 生成对话框：描述 → 后端 LLM 产 nodes/edges → 编辑器转换渲染（替换当前画布，需确认） -->
    <el-dialog v-model="aiVisible" title="AI 生成图" width="520px" destroy-on-close>
      <el-input
        v-model="aiDesc" type="textarea" :rows="4" maxlength="500" show-word-limit
        placeholder="描述你想要的图，例如：请假审批流程，主管审批通过后人事备案，驳回则退回重新填写"
      />
      <div class="ai-hint">会替换当前画布内容；生成后可以继续在画布上手动调整</div>
      <template #footer>
        <el-button @click="aiVisible = false">取消</el-button>
        <el-button type="primary" :loading="aiGenerating" @click="generateAi">生成</el-button>
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
import { ArrowRight, ArrowUp, Brush, Delete, MagicStick, Plus, Search, Top } from '@element-plus/icons-vue'
import {
  createWhiteboard, deleteWhiteboard, generateDiagram, getWhiteboard,
  searchWhiteboards, updateWhiteboard, whiteboardTree,
} from '../api'
import ExcalidrawBoard from './whiteboard/ExcalidrawBoard.vue'
import DrawioBoard from './whiteboard/DrawioBoard.vue'

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

// ---------- AI 生成（excalidraw） ----------
const aiVisible = ref(false)
const aiDesc = ref('')
const aiGenerating = ref(false)

async function generateAi() {
  const desc = aiDesc.value.trim()
  if (!desc) {
    ElMessage.warning('先描述一下想要的图')
    return
  }
  aiGenerating.value = true
  try {
    const d = await generateDiagram(desc)
    if (!d.nodes?.length) {
      ElMessage.warning('没有生成有效内容，换个说法再试试')
      return
    }
    // 画布已有内容时先确认（生成是替换语义）
    let hasContent = false
    try { hasContent = (JSON.parse(latestContent || '{}').elements || []).length > 0 } catch { /* 空画布 */ }
    if (hasContent) {
      try {
        await ElMessageBox.confirm('生成结果将替换当前画布内容，继续？', 'AI 生成', {
          confirmButtonText: '替换', cancelButtonText: '取消', type: 'warning',
        })
      } catch { return }
    }
    editorRef.value?.applyDiagram(d)
    aiVisible.value = false
    aiDesc.value = ''
    ElMessage.success(`已生成「${d.title || '图'}」，可在画布上继续调整`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    aiGenerating.value = false
  }
}

function toggleCollapse(n) {
  if (!n.hasChildren) return
  const s = new Set(collapsed.value)
  if (s.has(n.id)) s.delete(n.id)
  else s.add(n.id)
  collapsed.value = s
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
    searchResults.value = (await searchWhiteboards(kw)).whiteboards
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
.tree-ops { display: none; gap: 2px; flex-shrink: 0; color: #909399; }
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
  flex: 1; border: none; outline: none; font-size: 24px; font-weight: 700; color: #303133;
  background: transparent; min-width: 0;
}
.title-input::placeholder { color: #c0c4cc; }
.main-ops { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.save-state { font-size: 12px; color: #909399; margin-right: 4px; }
.save-state.err { color: #f56c6c; }
.ai-hint { font-size: 12px; color: #909399; margin-top: 8px; }
.editor-wrap { flex: 1; min-height: 0; padding: 4px 16px 16px; }
</style>
