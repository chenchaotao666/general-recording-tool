<template>
  <!-- 思维导图：与记事本/画板同款布局——左目录树（文件夹/搜索/拖拽排序）+ 右侧嵌入编辑器 -->
  <div class="mm-page">
    <div v-show="!sideCollapsed" class="mm-side" :style="{ width: sideWidth + 'px' }">
      <div class="side-top">
        <div class="side-top-row">
          <el-icon class="side-fold" title="收起目录" @click="collapseSide"><Fold /></el-icon>
          <el-input
            v-model="keyword" placeholder="搜索导图" clearable :prefix-icon="Search"
            @input="onSearchInput" @clear="searchResults = null"
          />
        </div>
        <div class="side-top-row">
          <el-button type="primary" :icon="Plus" class="side-new" @click="createMap()">新建</el-button>
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
            <el-icon class="tree-doc"><Folder v-if="n.kind === 'folder'" /><Share v-else /></el-icon>
            <span class="tree-title">{{ n.title || (n.kind === 'folder' ? '未命名文件夹' : '未命名导图') }}</span>
            <span class="tree-ops" @click.stop>
              <el-icon v-if="n.kind === 'folder' && n.level < 2" title="新增子导图" @click="createMap(n)"><Plus /></el-icon>
              <el-dropdown trigger="click" placement="bottom-end" @command="(cmd) => onMenu(cmd, n)">
                <el-icon title="更多" class="tree-more"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="rename">重命名</el-dropdown-item>
                    <el-dropdown-item v-if="n.kind !== 'folder'" command="share">分享</el-dropdown-item>
                    <el-dropdown-item v-if="n.can_delete" command="delete" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </span>
          </div>
        </template>
        <div v-else-if="!treeLoading" class="side-empty">
          {{ keyword ? '没有匹配的导图' : '还没有思维导图，点上方「新建」开始' }}
        </div>

        <!-- 分享给我的（跨租户成员分享，不进目录层级） -->
        <template v-if="searchResults === null && sharedMaps.length">
          <div class="shared-label">分享给我的</div>
          <div
            v-for="m in sharedMaps" :key="'s' + m.id"
            class="tree-item" :class="{ active: current?.id === m.id }"
            @click="openMap(m)"
          >
            <span class="tree-chevron" />
            <el-icon class="tree-doc"><Share /></el-icon>
            <span class="tree-title">{{ m.title }}</span>
            <el-tag size="small" :type="m.can_edit ? 'success' : 'info'" effect="plain" class="shared-tag">
              {{ m.can_edit ? '可编辑' : '只读' }}
            </el-tag>
          </div>
        </template>
      </div>
    </div>
    <!-- 分隔条：拖拽调节目录栏宽度 -->
    <div v-show="!sideCollapsed" class="side-resizer" @mousedown.prevent="startSideResize" />
    <!-- 收起后的窄条：点击展开 -->
    <div v-show="sideCollapsed" class="side-expand" title="展开目录" @click="expandSide">
      <el-icon><Expand /></el-icon>
    </div>

    <!-- 右侧：导图编辑器（嵌入，悬浮工具栏/标题条在组件内） -->
    <div class="mm-main">
      <MindMapEditor
        v-if="current" :id="current.id" :key="current.id"
        @saved="loadTree" @close="closeCurrent"
      />
      <el-empty v-else description="选择左侧导图，或新建一个开始" />
    </div>

    <!-- 分享（与数据表共用同一个对话框组件） -->
    <ShareDialog
      v-model="shareVisible" resource-type="mindmap"
      :resource-id="shareTarget?.id" :resource-name="shareTarget?.title"
    />
  </div>
</template>

<script setup>
// 思维导图目录页：扁平列表（含 kind=folder 目录节点）前端组装树，交互与记事本/画板一致
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Expand, Fold, Folder, FolderAdd, MoreFilled, Plus, Search, Share } from '@element-plus/icons-vue'
import {
  createMindmap, deleteMindmap, listMindmaps, mindmapTree, searchMindmaps, updateMindmap,
} from '../api'
import MindMapEditor from './MindMapEditor.vue'
import ShareDialog from '../components/ShareDialog.vue'
import DndHandle from '../components/DndHandle.vue'
import { useTreeDnd } from '../composables/useTreeDnd.js'

const route = useRoute()
const router = useRouter()

const maps = ref([])            // 本租户扁平列表（含文件夹）
const sharedMaps = ref([])      // 分享给我的（跨租户，平铺展示在目录底部）
const treeLoading = ref(false)
const current = ref(null)       // 当前打开的导图（仅需 id，编辑器自行加载内容）
const keyword = ref('')
const searchResults = ref(null) // 非 null 时展示搜索结果（平铺）
const collapsed = ref(new Set())

// 分享
const shareVisible = ref(false)
const shareTarget = ref(null)

// 目录栏：宽度可拖拽调节（200~480px，记住选择）；可整体收起为窄条
const sideWidth = ref(Number(localStorage.getItem('grt_mm_side_w')) || 280)
const sideCollapsed = ref(localStorage.getItem('grt_mm_side_collapsed') === '1')
function collapseSide() { sideCollapsed.value = true; localStorage.setItem('grt_mm_side_collapsed', '1') }
function expandSide() { sideCollapsed.value = false; localStorage.setItem('grt_mm_side_collapsed', '0') }
function startSideResize(e) {
  const startX = e.clientX
  const startW = sideWidth.value
  const onMove = (ev) => { sideWidth.value = Math.min(480, Math.max(200, startW + ev.clientX - startX)) }
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    // 只有真的拖过才记住宽度，避免误点分隔条把当前默认值存成"用户选择"
    if (sideWidth.value !== startW) localStorage.setItem('grt_mm_side_w', String(sideWidth.value))
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

function toggleCollapse(n) {
  if (!n.hasChildren) return
  const s = new Set(collapsed.value)
  if (s.has(n.id)) s.delete(n.id)
  else s.add(n.id)
  collapsed.value = s
}

// 扁平列表 → 带层级的树（平铺展示，用 level 缩进；收起的文件夹不显示其子树）
const displayTree = computed(() => {
  if (searchResults.value !== null) return searchResults.value.map((n) => ({ ...n, level: 0, hasChildren: false }))
  const byId = new Map(maps.value.map((n) => [n.id, { ...n, children: [] }]))
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

// 目录拖拽排序（通用逻辑与样式：composables/useTreeDnd.js + styles/tree-dnd.css + components/DndHandle.vue）
const dnd = useTreeDnd({
  items: maps,
  visible: displayTree,
  persist: updateMindmap,
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

async function loadTree() {
  treeLoading.value = true
  try {
    const d = await mindmapTree()
    maps.value = d.maps || []
    // 分享区走列表接口（含跨租户分享标记）；目录树只含本租户
    const all = await listMindmaps()
    sharedMaps.value = all.filter((m) => m.shared)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    treeLoading.value = false
  }
}

let searchTimer = null
function onSearchInput() {
  clearTimeout(searchTimer)
  const kw = keyword.value.trim()
  if (!kw) { searchResults.value = null; return }
  searchTimer = setTimeout(async () => {
    try {
      const d = await searchMindmaps(kw)
      searchResults.value = d.maps || []
    } catch (e) {
      ElMessage.error(e.message)
    }
  }, 300)
}

function openMap(n) {
  if (n.kind === 'folder') return
  current.value = { id: n.id }
  router.replace({ query: { ...route.query, id: n.id } })
}

function closeCurrent() {
  current.value = null
  const q = { ...route.query }
  delete q.id
  router.replace({ query: q })
}

function onItemClick(n) {
  if (n.kind === 'folder') { toggleCollapse(n); return }
  openMap(n)
}

function isCancel(e) {
  return e === 'cancel' || e === 'close'
}

async function createMap(parent) {
  try {
    const m = await createMindmap({ parent_id: parent?.id })
    await loadTree()
    openMap(m)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', { inputValue: '未命名文件夹' })
    if (value == null) return
    await createMindmap({ kind: 'folder', title: value.trim() || '未命名文件夹' })
    await loadTree()
  } catch (e) {
    if (!isCancel(e)) ElMessage.error(e.message)
  }
}

async function onMenu(cmd, n) {
  if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('名称', '重命名', { inputValue: n.title })
      if (!value?.trim()) return
      await updateMindmap(n.id, { title: value.trim() })
      await loadTree()
    } catch (e) {
      if (!isCancel(e)) ElMessage.error(e.message)
    }
  } else if (cmd === 'share') {
    shareTarget.value = n
    shareVisible.value = true
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(`确定删除「${n.title || '未命名'}」？`, '删除', { type: 'warning' })
    } catch { return }
    try {
      await deleteMindmap(n.id)
      ElMessage.success('已删除')
      if (current.value?.id === n.id) closeCurrent()
      await loadTree()
    } catch (e) {
      ElMessage.error(e.message)
    }
  }
}

onMounted(async () => {
  await loadTree()
  // 深链：/mindmaps?id=xx（/mindmaps/:id 旧链接已重定向到这里）
  const qid = Number(route.query.id)
  if (qid) current.value = { id: qid }
})
</script>

<style scoped>
.mm-page { display: flex; height: calc(100vh - var(--chrome-h, 48px)); }

/* 左侧目录树：与记事本/画板同款 */
.mm-side {
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
/* 分享给我的区块 */
.shared-label { padding: 12px 8px 4px; font-size: 12px; color: #b1b5bd; }
.shared-tag { flex-shrink: 0; transform: scale(.85); transform-origin: right center; }

/* 右侧编辑区 */
.mm-main {
  flex: 1; background: #fff; border-radius: 10px; box-shadow: 0 2px 12px rgba(31, 45, 61, .08);
  display: flex; flex-direction: column; overflow: hidden; position: relative;
}
/* 编辑器根元素自带 100vh 计算高度，嵌入时改为撑满容器 */
.mm-main :deep(.editor-page) { height: 100%; }
</style>
