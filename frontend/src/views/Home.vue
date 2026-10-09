<template>
  <div class="home-page">
    <!-- 操作按钮挂到全局顶栏（不占首页版面）；布局来源标签随行 -->
    <Teleport to="#topbarActions">
      <span class="bar-ops">
        <el-tag v-if="!editing && layoutSource === 'preset'" size="small" type="warning" effect="plain">全员默认布局</el-tag>
        <el-tag v-else-if="!editing && layoutSource === 'builtin'" size="small" type="info" effect="plain">系统默认布局</el-tag>
        <template v-if="!editing">
          <el-button size="small" :icon="EditPen" @click="startEdit">自定义</el-button>
        </template>
        <template v-else>
          <el-button size="small" :icon="Plus" @click="addSection">添加分区</el-button>
          <el-button v-if="isAdmin" size="small" :icon="Promotion" @click="saveAsDefault">存为全员默认</el-button>
          <el-button size="small" @click="resetDefault">恢复默认</el-button>
          <el-button size="small" @click="cancelEdit">取消</el-button>
          <el-button size="small" type="primary" :loading="saving" @click="saveEdit">保存</el-button>
        </template>
      </span>
    </Teleport>

    <div v-loading="loading" class="home-body">
      <GridLayout
        v-if="sections.length"
        :layout="glItems" :col-num="GRID.cols" :row-height="GRID.row" :margin="[0, 0]"
        :is-draggable="editing" :is-resizable="editing"
        @layout-updated="onLayoutUpdated"
      >
        <GridItem
          v-for="item in glItems" :key="item.i" v-bind="item"
          drag-allow-from=".sec-head" drag-ignore-from="button, a, input, .el-select"
        >
          <section :id="`home-${secOf(item.i).id}`" class="sec" :class="{ editing }">
            <!-- 分区头：查看态只有标题；编辑态可改名/删除/加分组/加卡片 -->
            <div class="sec-head">
              <span class="sec-title">
                <i class="sec-accent" :style="{ background: accentOf(secOf(item.i)) }" />{{ secOf(item.i).title }}
              </span>
              <span v-if="editing" class="sec-ops">
                <el-popover trigger="click" width="190" placement="bottom-end">
                  <template #reference>
                    <el-button text size="small" :icon="Brush" title="分区配色" @click.stop />
                  </template>
                  <div class="palette">
                    <span
                      v-for="c in SECTION_COLORS" :key="c.key" class="swatch"
                      :class="{ active: (secOf(item.i).color || '') === c.key }"
                      :style="{ background: c.color }" :title="c.name"
                      @click="secOf(item.i).color = c.key"
                    />
                  </div>
                </el-popover>
                <el-button text size="small" :icon="Plus" title="添加卡片"
                           @click.stop="openAddCard(secOf(item.i).id, null)" />
                <el-button text size="small" :icon="Collection" title="添加分组"
                           @click.stop="addGroup(secOf(item.i))" />
                <el-button text size="small" :icon="Edit" title="分区改名"
                           @click.stop="renameSection(secOf(item.i))" />
                <el-button text size="small" type="danger" :icon="Delete" title="删除分区"
                           @click.stop="removeSection(secOf(item.i))" />
              </span>
            </div>

            <div class="sec-body" :class="{ 'drop-zone': editing }"
                 @dragover.prevent="editing && onDragOver($event)"
                 @drop="onDrop($event, secOf(item.i).id, null, -1)">
              <template v-for="g in groupsOf(secOf(item.i))" :key="g.id">
                <div class="grp">
                  <div class="grp-head" :class="{ 'drop-zone': editing }"
                       @dragover.prevent="editing && onDragOver($event)"
                       @drop.stop="onDrop($event, secOf(item.i).id, g.id, -1)">
                    <el-icon class="grp-fold" @click="toggleGroup(g)">
                      <CaretBottom v-if="!g.collapsed" /><CaretRight v-else />
                    </el-icon>
                    <span class="grp-title">{{ g.title }}</span>
                    <span v-if="editing" class="grp-ops">
                      <el-button text size="small" :icon="ArrowUp" title="上移" @click.stop="moveGroup(secOf(item.i), g, -1)" />
                      <el-button text size="small" :icon="ArrowDown" title="下移" @click.stop="moveGroup(secOf(item.i), g, 1)" />
                      <el-button text size="small" :icon="Plus" title="添加卡片到此组"
                                 @click.stop="openAddCard(secOf(item.i).id, g.id)" />
                      <el-button text size="small" :icon="Edit" title="组改名" @click.stop="renameGroup(g)" />
                      <el-button text size="small" type="danger" :icon="Delete" title="删除分组（卡片移入未分组）"
                                 @click.stop="removeGroup(secOf(item.i), g)" />
                    </span>
                  </div>
                  <div v-show="!g.collapsed" class="cards"
                       @dragover.prevent="editing && onDragOver($event)"
                       @drop.stop="onDrop($event, secOf(item.i).id, g.id, -1)">
                    <div
                      v-for="(c, ci) in g.cards" :key="c.id" class="card-wrap"
                      :style="cardWrapStyle(c)"
                      :draggable="editing"
                      @dragstart="onCardDragStart($event, secOf(item.i).id, g.id, c.id)"
                      @dragover.prevent="editing && onDragOver($event)"
                      @drop.stop="onDrop($event, secOf(item.i).id, g.id, ci)"
                    >
                      <component :is="cardComponent(c)" :config="c.config" />
                      <span v-if="editing" class="card-ops">
                        <el-popover trigger="click" width="230" placement="bottom-end">
                          <template #reference>
                            <el-button text size="small" :icon="FullScreen" title="调整大小" @click.stop />
                          </template>
                          <div class="size-ctl">
                            <span class="sc-label">宽度</span>
                            <el-input-number :model-value="c.config?.span || 1" :min="1" :max="4" size="small"
                                             @update:model-value="(v) => setCardSize(c, 'span', v)" />
                          </div>
                          <div class="size-ctl">
                            <span class="sc-label">高度</span>
                            <el-input-number :model-value="c.config?.h || 0" :min="0" :max="4" size="small"
                                             @update:model-value="(v) => setCardSize(c, 'h', v)" />
                            <span class="sc-hint">0=自动</span>
                          </div>
                        </el-popover>
                        <el-button text size="small" :icon="Setting" title="卡片设置" @click.stop="openEditCard(c)" />
                        <el-button text size="small" type="danger" :icon="Close" title="移除卡片" @click.stop="removeCard(c.id)" />
                      </span>
                    </div>
                    <div v-if="!g.cards.length" class="cards-empty">拖拽卡片到此分组</div>
                  </div>
                </div>
              </template>

              <!-- 未分组卡片 -->
              <div class="cards" :class="{ 'drop-zone': editing }"
                   @dragover.prevent="editing && onDragOver($event)"
                   @drop.stop="onDrop($event, secOf(item.i).id, null, -1)">
                <div
                  v-for="(c, ci) in cardsOf(secOf(item.i))" :key="c.id" class="card-wrap"
                  :style="cardWrapStyle(c)"
                  :draggable="editing"
                  @dragstart="onCardDragStart($event, secOf(item.i).id, null, c.id)"
                  @dragover.prevent="editing && onDragOver($event)"
                  @drop.stop="onDrop($event, secOf(item.i).id, null, ci)"
                >
                  <component :is="cardComponent(c)" :config="c.config" />
                  <span v-if="editing" class="card-ops">
                    <el-popover trigger="click" width="230" placement="bottom-end">
                      <template #reference>
                        <el-button text size="small" :icon="FullScreen" title="调整大小" @click.stop />
                      </template>
                      <div class="size-ctl">
                        <span class="sc-label">宽度</span>
                        <el-input-number :model-value="c.config?.span || 1" :min="1" :max="4" size="small"
                                         @update:model-value="(v) => setCardSize(c, 'span', v)" />
                      </div>
                      <div class="size-ctl">
                        <span class="sc-label">高度</span>
                        <el-input-number :model-value="c.config?.h || 0" :min="0" :max="4" size="small"
                                         @update:model-value="(v) => setCardSize(c, 'h', v)" />
                        <span class="sc-hint">0=自动</span>
                      </div>
                    </el-popover>
                    <el-button text size="small" :icon="Setting" title="卡片设置" @click.stop="openEditCard(c)" />
                    <el-button text size="small" type="danger" :icon="Close" title="移除卡片" @click.stop="removeCard(c.id)" />
                  </span>
                </div>
                <div v-if="editing" class="cards-empty add" @click="openAddCard(secOf(item.i).id, null)">+ 添加卡片</div>
              </div>
            </div>
          </section>
        </GridItem>
      </GridLayout>
      <el-empty v-else-if="!loading" description="还没有内容，点右上角「自定义」开始布置工作台" />
    </div>

    <AddCardDialog
      v-model="cardDialogVisible" :mode="cardDialogMode" :initial="cardDialogInitial"
      @confirm="onCardConfirm"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDown, ArrowUp, Brush, CaretBottom, CaretRight, Close, Collection, Delete, Edit, EditPen, FullScreen, Plus, Promotion, Setting,
} from '@element-plus/icons-vue'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { deleteHomeLayout, getHomeLayout, saveDefaultHomeLayout, saveHomeLayout } from '../api'
import AddCardDialog from '../home/AddCardDialog.vue'
import { getCardType } from '../home/cardTypes'

const loading = ref(true)
const saving = ref(false)
const editing = ref(false)
const layoutSource = ref('builtin')   // mine / preset / builtin
const isAdmin = JSON.parse(localStorage.getItem('grt_user') || 'null')?.role === 'admin'

const layout = ref({ version: 1, sections: [] })   // 已保存的布局
const draft = reactive({ version: 1, sections: [] }) // 编辑草稿（保存时才落库）

// 栅格规格：36 列 × 36px 行（更细的拖动单位）。保存时带 grid 标记；
// 旧布局（无标记=12列×72；或更早的 24列×48）载入时按比例换算，保证视觉不变
const GRID = { cols: 36, row: 36 }

function normalizeLayout(lo) {
  const out = lo && typeof lo === 'object' ? lo : { version: 1, sections: [] }
  out.sections ||= []
  const g = out.grid
  const sx = GRID.cols / (g?.cols || 12)     // x/w 是列数：列变多则列数变多
  const sy = (g?.row || 72) / GRID.row       // h 是行数：行高变小则行数变多
  if (sx !== 1 || sy !== 1) {
    for (const s of out.sections) {
      s.x = Math.round((s.x ?? 0) * sx)
      s.w = Math.max(2, Math.round((s.w ?? 6) * sx))
      s.h = Math.max(2, Math.round((s.h ?? 4) * sy))
    }
  }
  return out
}

const payloadOf = (sections) => ({ version: 1, grid: { ...GRID }, sections })

const active = computed(() => (editing.value ? draft : layout.value))
const sections = computed(() => active.value.sections || [])
const glItems = computed(() =>
  sections.value.map((s) => ({ i: s.id, x: s.x ?? 0, y: s.y ?? 0, w: s.w ?? 18, h: s.h ?? 5 })))

const secOf = (id) => sections.value.find((s) => s.id === id)
const groupsOf = (sec) => sec.groups || []
const cardsOf = (sec) => sec.cards || []
const cardComponent = (c) => getCardType(c.type)?.component

onMounted(load)

async function load() {
  loading.value = true
  try {
    const res = await getHomeLayout()
    layout.value = normalizeLayout(res.layout)
    layoutSource.value = res.source || 'builtin'
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

// ---------- 编辑模式 ----------
function startEdit() {
  Object.assign(draft, JSON.parse(JSON.stringify(layout.value)))
  editing.value = true
}

function isDirty() {
  return JSON.stringify(draft.sections) !== JSON.stringify(layout.value.sections)
}

async function cancelEdit() {
  if (isDirty()) {
    try {
      await ElMessageBox.confirm('有未保存的布局修改，确定放弃吗？', '提示', {
        type: 'warning', confirmButtonText: '放弃修改', cancelButtonText: '继续编辑',
      })
    } catch { return }
  }
  editing.value = false
}

async function saveEdit() {
  saving.value = true
  try {
    await saveHomeLayout(payloadOf(draft.sections))
    layout.value = JSON.parse(JSON.stringify(draft))
    layoutSource.value = 'mine'
    editing.value = false
    ElMessage.success('布局已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

// 管理员：当前草稿布局存为全员默认（不影响自己已有的布局）
async function saveAsDefault() {
  try {
    await ElMessageBox.confirm(
      '把当前编辑中的布局设为全员默认？没有自己布局的用户将看到这份布局（已自定义的用户不受影响）。',
      '存为全员默认', { type: 'info', confirmButtonText: '设为默认', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await saveDefaultHomeLayout(payloadOf(draft.sections))
    ElMessage.success('已设为全员默认布局')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function resetDefault() {
  try {
    await ElMessageBox.confirm('将丢弃当前布局并恢复系统默认布局，确定吗？', '提示', { type: 'warning' })
  } catch { return }
  await deleteHomeLayout()   // 删除用户布局记录，后端 GET 时返回系统默认
  await load()
  editing.value = false
}

const uid = (p) => `${p}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

// 分区主题配色（key 存布局 JSON， hex 仅用于展示；默认=无强调色）
const SECTION_COLORS = [
  { key: '', name: '默认', color: '#c0c4cc' },
  { key: 'blue', name: '蓝色', color: '#409eff' },
  { key: 'green', name: '绿色', color: '#67c23a' },
  { key: 'orange', name: '橙色', color: '#e6a23c' },
  { key: 'red', name: '红色', color: '#f56c6c' },
  { key: 'purple', name: '紫色', color: '#9b59b6' },
  { key: 'teal', name: '青色', color: '#13c2c2' },
]
const accentOf = (sec) =>
  SECTION_COLORS.find((c) => c.key === (sec?.color || ''))?.color || 'transparent'

// ---------- 分区 ----------
function onLayoutUpdated(items) {
  if (!editing.value) return
  for (const it of items) {
    const s = secOf(it.i)
    if (s) Object.assign(s, { x: it.x, y: it.y, w: it.w, h: it.h })
  }
}

function addSection() {
  // 垂直压实模式下会自动落位，把新分区放到当前最低分区下方即可（库会再压实收拢）
  const bottom = draft.sections.reduce((m, s) => Math.max(m, (s.y || 0) + (s.h || 5)), 0)
  const id = uid('sec')
  draft.sections.push({ id, title: '新分区', x: 0, y: bottom, w: 18, h: 5, cards: [] })
  // 新分区可能落在首屏外，滚动过去给出可见反馈
  nextTick(() => {
    document.getElementById(`home-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
}

async function renameSection(sec) {
  try {
    const { value } = await ElMessageBox.prompt('分区名称', '重命名', {
      inputValue: sec.title, inputValidator: (v) => !!v?.trim() || '名称不能为空',
    })
    sec.title = value.trim()
  } catch { /* 取消 */ }
}

async function removeSection(sec) {
  try {
    await ElMessageBox.confirm(`确定删除分区「${sec.title}」？其中的卡片会一并移除。`, '提示', { type: 'warning' })
  } catch { return }
  draft.sections = draft.sections.filter((s) => s.id !== sec.id)
}

// ---------- 分组 ----------
async function addGroup(sec) {
  try {
    const { value } = await ElMessageBox.prompt('分组名称', '添加分组', {
      inputValidator: (v) => !!v?.trim() || '名称不能为空',
    })
    sec.groups ||= []
    sec.groups.push({ id: uid('grp'), title: value.trim(), collapsed: false, cards: [] })
  } catch { /* 取消 */ }
}

async function renameGroup(g) {
  try {
    const { value } = await ElMessageBox.prompt('分组名称', '重命名', {
      inputValue: g.title, inputValidator: (v) => !!v?.trim() || '名称不能为空',
    })
    g.title = value.trim()
  } catch { /* 取消 */ }
}

function moveGroup(sec, g, dir) {
  const arr = sec.groups || []
  const i = arr.findIndex((x) => x.id === g.id)
  const j = i + dir
  if (i < 0 || j < 0 || j >= arr.length) return
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

async function removeGroup(sec, g) {
  try {
    await ElMessageBox.confirm(`删除分组「${g.title}」？组内卡片会移到未分组。`, '提示', { type: 'warning' })
  } catch { return }
  sec.cards = [...(sec.cards || []), ...(g.cards || [])]
  sec.groups = (sec.groups || []).filter((x) => x.id !== g.id)
}

// 查看态也可折叠分组，状态直接静默保存
async function toggleGroup(g) {
  g.collapsed = !g.collapsed
  if (!editing.value) {
    try { await saveHomeLayout(payloadOf(layout.value.sections)) } catch { /* 忽略 */ }
  }
}

// ---------- 卡片 ----------
const cardDialogVisible = ref(false)
const cardDialogMode = ref('add')
const cardDialogInitial = ref(null)
let addTarget = { secId: null, groupId: null }
let editingCard = null

function openAddCard(secId, groupId) {
  addTarget = { secId, groupId }
  cardDialogMode.value = 'add'
  cardDialogInitial.value = null
  cardDialogVisible.value = true
}

function openEditCard(card) {
  editingCard = card
  cardDialogMode.value = 'edit'
  cardDialogInitial.value = { type: card.type, config: card.config }
  cardDialogVisible.value = true
}

function onCardConfirm({ type, config }) {
  if (cardDialogMode.value === 'edit' && editingCard) {
    editingCard.config = config
    return
  }
  const sec = secOf(addTarget.secId)
  if (!sec) return
  const card = { id: uid('card'), type, config }
  if (addTarget.groupId) {
    const g = (sec.groups || []).find((x) => x.id === addTarget.groupId)
    ;(g ? g.cards : (sec.cards ||= [])).push(card)
  } else {
    (sec.cards ||= []).push(card)
  }
}

// ---------- 卡片尺寸：宽度档位 span(1-4 列) / 高度档位 h(0=自动, 1-4 行×110px) ----------
function cardWrapStyle(c) {
  const span = Math.min(Math.max(Number(c.config?.span) || 1, 1), 4)
  const h = Math.min(Math.max(Number(c.config?.h) || 0, 0), 4)
  const st = {}
  if (span > 1) st.gridColumn = `span ${span}`
  if (h > 0) st.height = `${h * 110}px`
  return st
}

function setCardSize(c, key, v) {
  c.config ||= {}
  c.config[key] = v
}

function findCard(cardId) {
  for (const sec of draft.sections) {
    for (const g of sec.groups || []) {
      const i = (g.cards || []).findIndex((c) => c.id === cardId)
      if (i >= 0) return { sec, group: g, index: i }
    }
    const i = (sec.cards || []).findIndex((c) => c.id === cardId)
    if (i >= 0) return { sec, group: null, index: i }
  }
  return null
}

async function removeCard(cardId) {
  try {
    await ElMessageBox.confirm('移除这张卡片？', '提示', { type: 'warning' })
  } catch { return }
  const loc = findCard(cardId)
  if (!loc) return
  ;(loc.group ? loc.group.cards : loc.sec.cards).splice(loc.index, 1)
}

function moveCardTo(cardId, secId, groupId, index) {
  const from = findCard(cardId)
  if (!from) return
  const fromArr = from.group ? from.group.cards : from.sec.cards
  const [card] = fromArr.splice(from.index, 1)
  const sec = secOf(secId)
  if (!sec) return
  const toArr = groupId
    ? ((sec.groups || []).find((g) => g.id === groupId)?.cards ?? (sec.cards ||= []))
    : (sec.cards ||= [])
  if (index < 0 || index > toArr.length) toArr.push(card)
  else toArr.splice(index, 0, card)
}

// ---------- 卡片拖拽（HTML5 DnD；跨组/跨分区） ----------
let dragCardId = null

function onCardDragStart(e, secId, groupId, cardId) {
  dragCardId = cardId
  e.dataTransfer.effectAllowed = 'move'
  e.stopPropagation()
}

function onDragOver(e) {
  e.dataTransfer.dropEffect = 'move'
}

function onDrop(e, secId, groupId, index) {
  if (!dragCardId) return
  e.preventDefault()
  moveCardTo(dragCardId, secId, groupId, index)
  dragCardId = null
}
</script>

<style>
/* 首页卡片通用样式（卡片组件复用）：非 scoped，供 home/cards/* 共用
   基调：Linear/飞书式冷静清爽——层次靠留白和细阴影，不用硬边框 */
.hc {
  height: 100%; box-sizing: border-box; border: 1px solid #eef0f4; border-radius: 10px;
  background: #fff; padding: 12px 14px; cursor: pointer; overflow: auto;
  box-shadow: 0 1px 2px rgba(31, 45, 61, .04);
  transition: box-shadow .18s, transform .18s, border-color .18s;
  scrollbar-width: thin; scrollbar-color: rgba(31, 45, 61, .25) transparent;
  scrollbar-gutter: stable;   /* 卡片内部同理：滚动条占位恒定，内容宽度不抖 */
}
.hc::-webkit-scrollbar { width: 6px; height: 6px; }
.hc::-webkit-scrollbar-thumb { background: rgba(31, 45, 61, .18); border-radius: 3px; }
.hc::-webkit-scrollbar-track { background: transparent; }
.hc:hover {
  border-color: #d9e8ff; box-shadow: 0 6px 16px rgba(64, 158, 255, .14);
  transform: translateY(-2px);
}
.hc-loading { height: 48px; }
.hc-empty { color: #a8abb2; font-size: 12px; text-align: center; padding: 18px 0; }
.hc-invalid { color: #c0c4cc; font-size: 12px; display: flex; align-items: center; height: 100%; justify-content: center; }

/* 快捷入口类卡片：图标彩色柔色底（按类型分色调） */
.table-card, .menu-card { display: flex; align-items: center; gap: 12px; }
/* flex 子项不给 min-width:0 时内容不收缩，会把卡片顶出横向滚动条 */
.tc-main, .mc-main { flex: 1; min-width: 0; }
.tc-icon, .mc-icon {
  width: 42px; height: 42px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 21px;
}
.tc-icon { background: #e8f3ff; color: #409eff; }     /* 数据表=蓝 */
.mc-icon { background: #e6f7f6; color: #13c2c2; }     /* 菜单功能=青 */
.tc-name { font-size: 14px; font-weight: 600; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tc-sub { font-size: 12px; color: #a8abb2; margin-top: 3px; }
.tc-shared { margin-left: 6px; color: #e6a23c; }

/* 列表类卡片：行距更松、时间右对齐浅色 */
.tlc-row, .lc-row { display: flex; align-items: center; gap: 8px; padding: 7px 6px; border-radius: 6px; font-size: 13px; }
.tlc-row:hover, .lc-row:hover { background: #f5f7fa; }
.tlc-icon { color: #409eff; flex-shrink: 0; }
.tlc-name, .lc-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #303133; }
.tlc-count { color: #a8abb2; font-size: 12px; font-variant-numeric: tabular-nums; }
.tlc-more, .lc-more { font-size: 12px; color: #409eff; text-align: center; padding: 8px 0 2px; cursor: pointer; }
.lc-dot { width: 6px; height: 6px; border-radius: 50%; background: #dcdfe6; flex-shrink: 0; }
.lc-row.unread .lc-dot { background: #f56c6c; }
.lc-row.unread .lc-title { font-weight: 600; }
.lc-time, .lc-wf { color: #c0c4cc; font-size: 12px; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.lc-todo-icon { color: #e6a23c; flex-shrink: 0; }
</style>

<style scoped>
/* 首页自己提供内边距/底色，不依赖 .main 的规格：
   负边距抵消 .main 的 20px 24px，再用 18px 侧 padding——
   grid item 自带的 6px 水平内边距恰好补齐，分区可视边缘与报表页(24px)齐平 */
.home-page { margin: -20px -24px; padding: 20px 18px; background: #f5f7fa; }

.bar-ops { display: inline-flex; gap: 8px; align-items: center; }

/* 分区卡：白卡浮起、无硬边框。
   border 常驻（透明）——编辑态只是换色换虚线，避免两种状态盒尺寸不一致 */
.sec {
  height: 100%; display: flex; flex-direction: column; background: #fff;
  border: 1.5px solid transparent; border-radius: 12px; overflow: hidden;
  box-shadow: 0 1px 3px rgba(31, 45, 61, .07);
  box-sizing: border-box;
}
.sec.editing {
  border-color: #a0cfff; border-style: dashed; background: rgba(64, 158, 255, .03);
  box-shadow: none;
}
.sec-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px 6px; background: transparent; border-bottom: none;
  height: 40px; box-sizing: border-box; flex-shrink: 0;   /* 两种状态同高：编辑态按钮不再撑高头部 */
}
.editing .sec-head { cursor: move; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; display: inline-flex; align-items: center; gap: 7px; }
/* 分区配色：标题左侧的强调色条（默认色用浅灰示意，有色时突出） */
.sec-accent { width: 4px; height: 15px; border-radius: 2px; display: inline-block; }

/* ---- 编辑态操作按钮统一风格：浅灰图标、hover 上色、danger 变红 ---- */
.sec-ops, .grp-ops, .card-ops { display: inline-flex; align-items: center; gap: 6px; }
.sec-ops .el-button, .grp-ops .el-button, .card-ops .el-button {
  padding: 5px 6px; margin-left: 0 !important; color: #a8abb2; border-radius: 6px;
  font-size: 17px;   /* 图标放大一号，更醒目 */
}
.sec-ops .el-button:hover, .grp-ops .el-button:hover, .card-ops .el-button:hover {
  background: #eef4ff; color: #409eff;
}
.sec-ops .el-button[type="danger"]:hover, .grp-ops .el-button[type="danger"]:hover,
.card-ops .el-button[type="danger"]:hover {
  background: #fdeaea; color: #f56c6c;
}

/* 分区/分组操作：常驻平铺（卡片操作保持 hover 浮现，避免遮住内容） */

.palette { display: flex; gap: 8px; flex-wrap: wrap; }
.swatch {
  width: 22px; height: 22px; border-radius: 50%; cursor: pointer; display: inline-block;
  border: 2px solid transparent; box-sizing: border-box;
}
.swatch:hover { transform: scale(1.12); }
.swatch.active { border-color: #303133; }

.sec-body { flex: 1; overflow: auto; padding: 6px 12px 10px; }
/* 始终预留滚动条位置：否则分区宽度卡在临界点时，滚动条一出没，
   卡片每行个数会跳变（5 列↔4 列），拉高留白、拉矮截断 */
.sec-body { scrollbar-gutter: stable; }
/* 纤细半透滚动条：少占位，不与右下角的 resize 手柄抢视觉 */
.sec-body { scrollbar-width: thin; scrollbar-color: rgba(31, 45, 61, .25) transparent; }
.sec-body::-webkit-scrollbar { width: 6px; height: 6px; }
.sec-body::-webkit-scrollbar-thumb { background: rgba(31, 45, 61, .18); border-radius: 3px; }
.sec-body::-webkit-scrollbar-thumb:hover { background: rgba(31, 45, 61, .32); }
.sec-body::-webkit-scrollbar-track { background: transparent; }
.grp-head { display: flex; align-items: center; gap: 4px; padding: 6px 2px 4px; min-height: 32px; box-sizing: border-box; }
.grp-fold { cursor: pointer; color: #a8abb2; }
.grp-title { font-size: 12px; font-weight: 600; color: #909399; flex: 1; letter-spacing: .5px; }

/* min(180px,100%)：窄分区（窗口小/分区窄）里列宽下限不再顶出横向滚动条 */
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(180px, 100%), 1fr)); gap: 10px; padding: 4px 0; }
.cards-empty { color: #c0c4cc; font-size: 12px; text-align: center; padding: 12px; border: 1px dashed #e4e7ed; border-radius: 10px; }
.cards-empty.add { cursor: pointer; color: #409eff; }
.cards-empty.add:hover { border-color: #409eff; }

.card-wrap { position: relative; min-height: 66px; }
.editing .card-wrap { cursor: grab; outline: 1px dashed transparent; }
.editing .card-wrap:hover { outline-color: #a0cfff; }
.card-ops {
  position: absolute; top: 3px; right: 3px; z-index: 5; display: none;
  background: rgba(255, 255, 255, .96); border-radius: 8px; padding: 1px 3px;
  box-shadow: 0 2px 10px rgba(31, 45, 61, .14);
}
.card-wrap:hover .card-ops { display: inline-flex; }

/* 卡片大小调节 */
.size-ctl { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.size-ctl:last-child { margin-bottom: 0; }
.size-ctl :deep(.el-input-number) { width: 112px; flex-shrink: 0; }   /* 收窄给提示留位，防换行 */
.sc-label { font-size: 13px; color: #606266; width: 34px; flex-shrink: 0; }
.sc-hint { font-size: 12px; color: #a8abb2; white-space: nowrap; }

/* grid-layout-plus 占位块颜色与主题一致（库 1.1.x 的类名前缀是 vgl-）。
   background-clip: content-box——背景只铺 padding 以内的内容区，
   否则预览块比实际卡片大出一圈 padding */
:deep(.vgl-item--placeholder) {
  background-color: #c6e2ff; opacity: .3; border-radius: 12px;
  background-clip: content-box !important;
}
/* margin 设 [0,0] 让分区与报表页一样贴容器边缘；块间 12px 间距改由 item 内边距承担
   （这个版本的库没有 container-padding 属性） */
:deep(.vgl-item) { transition: all .18s ease; padding: 0 6px 12px; box-sizing: border-box; }
/* 拖动/缩放中必须关掉过渡：否则被拖元素每一帧都在"追赶"鼠标，感觉迟滞 */
:deep(.vgl-item--dragging),
:deep(.vgl-item--resizing) { transition: none !important; }
/* resize 手柄对齐到卡片可视角（item 有 6px/12px 内边距，默认贴 item 角会悬在卡片外） */
:deep(.vgl-item__resizer) { right: 10px !important; bottom: 16px !important; }
</style>

