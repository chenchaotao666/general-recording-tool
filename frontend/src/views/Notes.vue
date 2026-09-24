<template>
  <div class="notes-page">
    <!-- 左侧：搜索 + 页面树 -->
    <div class="notes-side">
      <div class="side-top">
        <el-input
          v-model="keyword" placeholder="搜索笔记" clearable :prefix-icon="Search"
          @input="onSearchInput" @clear="searchResults = null"
        />
        <el-button type="primary" :icon="Plus" @click="createPage()">新建</el-button>
      </div>
      <div v-loading="treeLoading" class="tree">
        <template v-if="displayTree.length">
          <div
            v-for="n in displayTree" :key="n.id"
            class="tree-item" :class="{ active: current?.id === n.id, pinned: n.pinned }"
            :style="{ paddingLeft: 10 + n.level * 18 + 'px' }"
            @click="open(n)"
          >
            <el-icon v-if="n.pinned" class="pin-flag"><Top /></el-icon>
            <span class="tree-title">{{ n.title || '无标题页面' }}</span>
            <span class="tree-ops" @click.stop>
              <el-icon title="新增子页" @click="createPage(n)"><Plus /></el-icon>
              <el-icon :title="n.pinned ? '取消置顶' : '置顶'" @click="togglePin(n)"><Top /></el-icon>
              <el-icon title="删除" @click="del(n)"><Delete /></el-icon>
            </span>
          </div>
        </template>
        <div v-else-if="!treeLoading" class="side-empty">
          {{ keyword ? '没有匹配的笔记' : '还没有笔记，点上方「新建」开始' }}
        </div>
      </div>
    </div>

    <!-- 右侧：块编辑器 -->
    <div class="notes-main">
      <template v-if="current">
        <div class="main-top">
          <input v-model="current.title" class="title-input" placeholder="无标题页面" maxlength="200" @input="onTitleInput" />
          <div class="main-ops">
            <span class="save-state" :class="{ err: saveState === '保存失败' }">{{ saveState }}</span>
            <el-button text :icon="Top" :type="current.pinned ? 'primary' : ''" @click="togglePin(current)">
              {{ current.pinned ? '已置顶' : '置顶' }}
            </el-button>
            <el-button text :icon="Plus" @click="createPage(current)">子页</el-button>
            <el-popconfirm title="删除该页面？（有子页时需先处理子页）" width="240" @confirm="del(current)">
              <template #reference><el-button text type="danger" :icon="Delete">删除</el-button></template>
            </el-popconfirm>
          </div>
        </div>
        <div :key="current.id" ref="editorEl" class="editor-holder" />
        <!-- AI 写作面板：Teleport 到当前块后面的锚点，内嵌在文档流里（占实际位置，推挤后续内容） -->
        <Teleport v-if="ai.visible && ai.anchor" :to="ai.anchor">
          <div class="ai-panel" @keydown.stop>
            <div class="ai-panel-head">✨ AI 写作</div>
            <input
              ref="aiInputRef" v-model="ai.instruction" class="ai-input"
              placeholder="描述要生成的内容，如：写一份本周工作总结"
              @keydown.enter.prevent="aiGenerate" @keydown.esc.prevent="aiDiscard"
            />
            <!-- 生成结果预览：确认「插入」后才写入文档 -->
            <div v-if="ai.preview" class="ai-preview">
              <div v-for="(r, i) in previewRows(ai.preview)" :key="i" class="pv" :class="r.cls" v-html="r.html" />
            </div>
            <div class="ai-panel-ops">
              <span class="ai-hint">{{ ai.preview ? '确认后插入 · Esc 丢弃' : 'Enter 生成 · Esc 取消' }}</span>
              <div>
                <template v-if="ai.preview">
                  <el-button size="small" text @click="aiDiscard">丢弃</el-button>
                  <el-button size="small" :loading="ai.loading" @click="aiGenerate">重新生成</el-button>
                  <el-button size="small" type="primary" @click="aiInsert">插入</el-button>
                </template>
                <el-button v-else size="small" type="primary" :loading="ai.loading" @click="aiGenerate">生成</el-button>
              </div>
            </div>
            <div v-if="ai.error" class="ai-error">{{ ai.error }}</div>
          </div>
        </Teleport>
        <!-- / 块菜单：Teleport 到 body + fixed 定位，彻底避开编辑器滚动容器的裁剪 -->
        <Teleport to="body">
          <div v-if="slash.visible" class="slash-menu" :style="{ left: slash.x + 'px', top: slash.y + 'px' }" @mousedown.prevent>
            <div class="slash-group">基本区块</div>
            <div
              v-for="(it, i) in slashItems" :key="it.label"
              class="slash-item" :class="{ active: i === slash.active }"
              @mouseenter="slash.active = i" @click="slashSelect(it)"
            >
              <span class="slash-icon">{{ it.icon }}</span>
              <span class="slash-label">{{ it.label }}</span>
              <span class="slash-hint">{{ it.hint }}</span>
            </div>
            <div v-if="!slashItems.length" class="slash-empty">没有匹配的块类型</div>
            <div class="slash-foot">关闭菜单 <span class="slash-key">esc</span></div>
          </div>
        </Teleport>
        <div class="editor-tip"># 空格=标题　- 空格=列表　1. 空格=编号　[] 空格=待办　&gt; 空格=折叠　---=分割线　/ =块菜单　空行空格=AI</div>
      </template>
      <el-empty v-else description="选择左侧页面，或新建一个开始记录" />
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Plus, Search, Top } from '@element-plus/icons-vue'
import EditorJS from '@editorjs/editorjs'
import Header from '@editorjs/header'
import List from '@editorjs/list'
import Checklist from '@editorjs/checklist'
import Quote from '@editorjs/quote'
import Delimiter from '@editorjs/delimiter'
import CodeTool from '@editorjs/code'
import { createNote, deleteNote, getNote, noteAiAssist, noteTree, searchNotes, updateNote } from '../api'

// ---------- 自定义折叠块（toggle）：▸/▾ + 标题 + 可折叠内容区（Notion 的 > 空格） ----------
class ToggleTool {
  static get toolbox() {
    return {
      title: '折叠块',
      icon: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
    }
  }

  // 与其他块互转：导出标题文本，导入为标题
  static get conversionConfig() {
    return {
      export: (d) => d.text || '',
      import: (t) => ({ text: t, content: '', expanded: true }),
    }
  }

  constructor({ data, block }) {
    this.block = block
    this.data = {
      text: data.text || '',
      content: data.content || '',
      expanded: data.expanded !== false,
    }
  }

  render() {
    const wrap = document.createElement('div')
    wrap.className = 'toggle-block'

    const head = document.createElement('div')
    head.className = 'toggle-head'
    const arrow = document.createElement('span')
    arrow.className = 'toggle-arrow'
    arrow.contentEditable = 'false'
    const title = document.createElement('div')
    title.className = 'toggle-title'
    title.contentEditable = 'true'
    title.innerHTML = this.data.text
    head.append(arrow, title)

    const body = document.createElement('div')
    body.className = 'toggle-body'
    body.contentEditable = 'true'
    body.innerHTML = this.data.content

    const sync = () => {
      arrow.textContent = this.data.expanded ? '▾' : '▸'
      body.style.display = this.data.expanded ? '' : 'none'
      wrap.classList.toggle('collapsed', !this.data.expanded)
    }
    const placeCaretEnd = (el) => {
      el.focus()
      const range = document.createRange()
      range.selectNodeContents(el)
      range.collapse(false)
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(range)
    }
    arrow.addEventListener('click', () => {
      this.data.expanded = !this.data.expanded
      sync()
      this.block?.dispatchChange()
    })
    // Enter：标题里 → 进入内容区（自动展开）；内容区里 → 区内换行。
    // 都 stopPropagation，避免 Editor.js 拦截 Enter 在下方新建块跳出折叠块
    title.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        e.stopPropagation()
        if (!this.data.expanded) {
          this.data.expanded = true
          sync()
        }
        placeCaretEnd(body)
      }
    })
    body.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        e.stopPropagation()
        document.execCommand('insertLineBreak')
      }
    })

    this._title = title
    this._body = body
    sync()
    wrap.append(head, body)
    return wrap
  }

  save() {
    return {
      text: this._title.innerHTML,
      content: this._body.innerHTML,
      expanded: this.data.expanded,
    }
  }
}

// 「转换为」菜单补全：code 插件不带 conversionConfig，子类补上即可参与块间互转
class ConvertibleCode extends CodeTool {
  static get conversionConfig() {
    return {
      export: (d) => d.code || '',
      import: (t) => ({ code: t }),
    }
  }
}

// list v2 的 toolbox 自带 checklist 样式，与独立待办插件重复（菜单里出现两个「待办清单」）：子类过滤掉
class ListNoCheck extends List {
  static get toolbox() {
    return super.toolbox.filter((t) => t.data?.style !== 'checklist')
  }
}

const notes = ref([])          // 扁平列表（后端已排好序）
const treeLoading = ref(false)
const current = ref(null)      // 当前打开的页面（含 blocks）
const keyword = ref('')
const searchResults = ref(null) // 非 null 时展示搜索结果（平铺）
const saveState = ref('')
const editorEl = ref(null)

// AI 写作面板（空块空格唤起；内嵌文档流，不占绝对定位）
const ai = ref({ visible: false, loading: false, instruction: '', error: '', index: -1, preview: null, anchor: null })
const aiInputRef = ref(null)

// / 块菜单（仿 Notion）：空段落输入 / 唤起，输入即过滤，↑↓ 选择、Enter 插入、Esc 关闭
const slash = ref({ visible: false, query: '', active: 0, x: 0, y: 0, index: -1 })
let slashPending = null  // keydown 记下的候选空段落，keyup 确认 '/' 已落入块中再开菜单

const SLASH_ITEMS = [
  { type: 'paragraph', label: '文本', hint: '', keys: 'wenben wb text', icon: 'T' },
  { type: 'header', label: '标题 1', hint: '#', keys: 'biaoti bt heading h1', icon: 'H1', level: 1 },
  { type: 'header', label: '标题 2', hint: '##', keys: 'biaoti bt heading h2', icon: 'H2', level: 2 },
  { type: 'header', label: '标题 3', hint: '###', keys: 'biaoti bt heading h3', icon: 'H3', level: 3 },
  { type: 'list', label: '无序列表', hint: '-', keys: 'wuxu wx liebiao lb list ul bullet', icon: '•', style: 'unordered' },
  { type: 'list', label: '有序列表', hint: '1.', keys: 'youxu yx liebiao lb list ol number', icon: '1.', style: 'ordered' },
  { type: 'checklist', label: '待办事项', hint: '[]', keys: 'daiban db todo checklist', icon: '☐' },
  { type: 'toggle', label: '折叠块', hint: '>', keys: 'zhedie zd toggle collapse', icon: '▸' },
  { type: 'quote', label: '引用', hint: '"', keys: 'yinyong yy quote', icon: '❝' },
  { type: 'delimiter', label: '分割线', hint: '---', keys: 'fenge fg divider hr', icon: '—' },
  { type: 'code', label: '代码块', hint: '```', keys: 'daima dm code', icon: '</>' },
]

const slashItems = computed(() => {
  const q = slash.value.query.trim().toLowerCase()
  if (!q) return SLASH_ITEMS
  return SLASH_ITEMS.filter((it) => `${it.label} ${it.keys}`.toLowerCase().includes(q))
})

let editor = null
let saveTimer = null
let titleTimer = null
let saving = false
let dirty = false

// 扁平列表 → 带层级的树（平铺展示，用 level 缩进）
const displayTree = computed(() => {
  if (searchResults.value !== null) return searchResults.value.map((n) => ({ ...n, level: 0 }))
  const byId = new Map(notes.value.map((n) => [n.id, { ...n, children: [] }]))
  const roots = []
  for (const n of byId.values()) {
    if (n.parent_id && byId.has(n.parent_id)) byId.get(n.parent_id).children.push(n)
    else roots.push(n)
  }
  const out = []
  const walk = (list, level) => list.forEach((n) => {
    out.push({ ...n, level })
    walk(n.children, level + 1)
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
    searchResults.value = (await searchNotes(kw)).notes
  } catch (e) {
    ElMessage.error(e.message)
  }
}, 300)

// ---------- 编辑器 ----------

const EDITOR_I18N = {
  messages: {
    ui: {
      blockTunes: { toggler: { 'Click to tune': '点击调整', 'or drag to move': '或拖动移动' } },
      inlineToolbar: { converter: { 'Convert to': '转换为' } },
      toolbar: { toolbox: { Add: '添加', Filter: '搜索' } },
    },
    toolNames: {
      Text: '正文', Heading: '标题', List: '列表', Checklist: '待办清单',
      'Unordered List': '无序列表', 'Ordered List': '有序列表',
      Quote: '引用', Delimiter: '分割线', Code: '代码',
      Bold: '加粗', Italic: '斜体', InlineCode: '行内代码',
    },
    blockTunes: {
      delete: { Delete: '删除', 'Click to delete': '确认删除' },
      moveUp: { 'Move up': '上移' },
      moveDown: { 'Move down': '下移' },
    },
  },
}

function initEditor(blocks) {
  editor = new EditorJS({
    holder: editorEl.value,
    data: { blocks: blocks || [] },
    placeholder: '写点什么… 空行按空格唤起 AI，按 / 插入块',
    i18n: EDITOR_I18N,
    tools: {
      header: { class: Header, inlineToolbar: true, config: { levels: [1, 2, 3], defaultLevel: 2 } },
      list: { class: ListNoCheck, inlineToolbar: true, config: { defaultStyle: 'unordered' } },
      checklist: { class: Checklist, inlineToolbar: true },
      quote: { class: Quote, inlineToolbar: true },
      toggle: ToggleTool,
      delimiter: Delimiter,
      code: ConvertibleCode,
    },
    onChange: () => {
      dirty = true
      scheduleSave()
    },
  })
  // Editor.js 核心不带 Markdown 快捷输入，自己实现：
  // 段落块首输入 # / - / 1. / [] / > 后按空格（或输入 ---）即转换为对应块
  editor.isReady.then(() => {
    editorEl.value?.addEventListener('keyup', mdShortcut)
    // 捕获阶段：/ 菜单的 Enter/方向键要先于 Editor.js 自己的 keydown 处理拦截
    editorEl.value?.addEventListener('keydown', onEditorKeydown, true)
  }).catch(() => {})
}

// ---------- 空块交互：空格 → AI 写作；/ → 块命令菜单 ----------

function currentEmptyParagraph() {
  const index = editor.blocks.getCurrentBlockIndex()
  if (index < 0) return null
  const block = editor.blocks.getBlockByIndex(index)
  if (!block || block.name !== 'paragraph') return null
  if ((block.holder.textContent || '').trim()) return null
  return { index, block }
}

// / 菜单可整体替换的空块（列表/待办等结构性块不在其列，/ 只作为普通字符输入）
const SLASH_CONVERTIBLE = ['paragraph', 'header', 'quote']

function currentEmptyBlock() {
  const index = editor.blocks.getCurrentBlockIndex()
  if (index < 0) return null
  const block = editor.blocks.getBlockByIndex(index)
  if (!block || (block.holder.textContent || '').trim()) return null
  return { index, block }
}

function onEditorKeydown(e) {
  if (!editor) return
  // / 菜单打开期间的键盘导航（捕获阶段拦截，避免 Editor.js 抢先响应 Enter/方向键）
  if (slash.value.visible) {
    const n = slashItems.value.length
    if (e.key === 'ArrowDown' && n) {
      e.preventDefault()
      e.stopPropagation()
      slash.value.active = (slash.value.active + 1) % n
    } else if (e.key === 'ArrowUp' && n) {
      e.preventDefault()
      e.stopPropagation()
      slash.value.active = (slash.value.active - 1 + n) % n
    } else if (e.key === 'Enter') {
      e.preventDefault()
      e.stopPropagation()
      slashSelect(slashItems.value[slash.value.active])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      closeSlash(true)
    } else if (e.key === ' ') {
      closeSlash()  // 空格结束命令，保留已输入文本照常输入
    }
    return
  }
  if (ai.value.loading) return
  if (e.key === '/') {
    // Editor.js 核心对任何空块的 / 都有自己的处理（插入字符并打开原生 toolbox 抢焦点），
    // 捕获阶段一律 stopPropagation 拦掉；可整体替换的空块（段落/标题/引用）再拉起自定义菜单。
    // 不 preventDefault —— '/' 照常落入块中作为查询前缀（非白名单块则只是普通字符）
    const ctx = currentEmptyBlock()
    if (!ctx) return
    e.stopPropagation()
    if (SLASH_CONVERTIBLE.includes(ctx.block.name)) slashPending = ctx
    return
  }
  if (e.key === ' ') {
    const ctx = currentEmptyParagraph()
    if (!ctx) return
    e.preventDefault()  // 空格不落入空块，直接唤起 AI 面板
    openAi(ctx)
  }
}

// ---------- / 块菜单 ----------

// 菜单定位：光标 rect 优先，空块 rect 可能全 0 则退到块元素；右/下越界时向内收
function slashPosition(block) {
  const sel = window.getSelection()
  let rect = sel.rangeCount ? sel.getRangeAt(0).getBoundingClientRect() : null
  if (!rect || (!rect.top && !rect.bottom)) rect = block.holder.getBoundingClientRect()
  const W = 250
  const H = 380
  const x = Math.max(12, Math.min(rect.left, window.innerWidth - W - 12))
  let y = rect.bottom + 6
  if (y + H > window.innerHeight) y = Math.max(12, rect.top - H - 6)
  return { x, y }
}

function openSlash(ctx) {
  const { x, y } = slashPosition(ctx.block)
  slash.value = { visible: true, query: '', active: 0, x, y, index: ctx.index }
  document.addEventListener('mousedown', onSlashDocDown, true)
}

function onSlashDocDown(e) {
  const menu = document.querySelector('.slash-menu')
  if (menu && !menu.contains(e.target)) closeSlash()  // 点外面：保留已输入的 /query 文本
}

// 关闭菜单；clearText=true（Esc）时把已输入的 /query 文本一并清掉
function closeSlash(clearText = false) {
  const { index } = slash.value
  slash.value.visible = false
  document.removeEventListener('mousedown', onSlashDocDown, true)
  if (!clearText || !editor) return
  const block = editor.blocks.getBlockByIndex(index)
  if (block && SLASH_CONVERTIBLE.includes(block.name) && (block.holder.textContent || '').startsWith('/')) {
    const nb = editor.blocks.insert('paragraph', { text: '' }, {}, index, true, true)
    setTimeout(() => focusBlockEnd(nb), 50)
  }
}

function slashData(it) {
  switch (it.type) {
    case 'header': return { text: '', level: it.level }
    case 'list': return { style: it.style, items: [{ content: '', items: [] }] }
    case 'checklist': return { items: [{ text: '', checked: false }] }
    case 'toggle': return { text: '', content: '', expanded: true }
    case 'quote': return { text: '', alignment: 'left' }
    case 'code': return { code: '' }
    default: return {}  // paragraph / delimiter
  }
}

function slashSelect(it) {
  if (!it || !editor) return
  const index = slash.value.index
  closeSlash()  // 选中后原空段落（含 /query）被整体替换，无需清文本
  const newBlock = editor.blocks.insert(it.type, slashData(it), {}, index, true, true)
  if (it.type === 'delimiter') {
    // 分割线不可聚焦：下方补一个空段落承接光标
    const p = editor.blocks.insert('paragraph', { text: '' }, {}, index + 1, true, false)
    setTimeout(() => focusBlockEnd(p), 50)
  } else {
    setTimeout(() => {
      const active = document.activeElement
      if (active && newBlock.holder?.contains(active)) return
      focusBlockEnd(newBlock)
    }, 50)
  }
}

function openAi(ctx) {
  // 在当前块后面插入锚点，面板 Teleport 进去——内嵌在块流里，实际占位推挤后续内容
  closeAiAnchor()
  const anchor = document.createElement('div')
  anchor.className = 'ai-anchor'
  ctx.block.holder.insertAdjacentElement('afterend', anchor)
  ai.value = {
    visible: true, loading: false, instruction: '', error: '', preview: null,
    index: ctx.index, anchor,
  }
  // 失去焦点（点击面板外）即隐藏，等价于丢弃
  document.addEventListener('mousedown', onDocMouseDown, true)
  nextTick(() => aiInputRef.value?.focus())
}

function onDocMouseDown(e) {
  const panel = document.querySelector('.ai-panel')
  if (panel && !panel.contains(e.target)) closeAi(false)
}

function closeAiAnchor() {
  ai.value.anchor?.remove()
  ai.value.anchor = null
}

function closeAi(refocus = true) {
  ai.value.visible = false
  ai.value.preview = null
  closeAiAnchor()
  document.removeEventListener('mousedown', onDocMouseDown, true)
  // Esc 主动取消时焦点还给空段落；点击别处失焦时不抢焦点（让用户点击正常生效）
  if (!refocus) return
  const block = editor?.blocks.getBlockByIndex(ai.value.index)
  if (block) focusBlockEnd(block)
}

// 丢弃生成结果（Esc / 丢弃按钮）：不写入文档
function aiDiscard() {
  closeAi()
}

function blockText(b) {
  const d = b.data || {}
  const strip = (s) => String(s || '').replace(/<[^>]+>/g, '')
  if (Array.isArray(d.items)) return d.items.map((i) => strip(i.content ?? i.text ?? i)).join(' / ')
  return strip(d.text || d.code)
}

async function aiGenerate() {
  const instruction = ai.value.instruction.trim()
  if (!instruction || ai.value.loading) return
  ai.value.loading = true
  ai.value.error = ''
  try {
    const data = await editor.save()
    const context = data.blocks.map(blockText).filter(Boolean)
    const res = await noteAiAssist({ instruction, note_title: current.value?.title || '', context })
    ai.value.preview = res.blocks  // 只预览，不写入；用户点「插入」才进文档
  } catch (e) {
    ai.value.error = e.message
  } finally {
    ai.value.loading = false
  }
}

// 预览渲染：转义 HTML 后仅放行 <b> 加粗
function rich(s) {
  return String(s || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/&lt;b&gt;/g, '<b>').replace(/&lt;\/b&gt;/g, '</b>')
}

function previewRows(blocks) {
  const rows = []
  for (const b of blocks || []) {
    const d = b.data || {}
    if (b.type === 'header') rows.push({ cls: `pv-h${d.level || 2}`, html: rich(d.text) })
    else if (b.type === 'paragraph') rows.push({ cls: 'pv-p', html: rich(d.text) })
    else if (b.type === 'quote') rows.push({ cls: 'pv-quote', html: rich(d.text) })
    else if (b.type === 'list') {
      ;(d.items || []).forEach((it, j) =>
        rows.push({ cls: 'pv-li', html: `${d.style === 'ordered' ? `${j + 1}.` : '•'} ${rich(it.content)}` }))
    } else if (b.type === 'checklist') {
      ;(d.items || []).forEach((it) =>
        rows.push({ cls: 'pv-li', html: `${it.checked ? '☑' : '☐'} ${rich(it.text)}` }))
    }
  }
  return rows
}

// 确认插入：预览块写入文档并替换原空段落
function aiInsert() {
  if (!ai.value.preview?.length) return
  const index = ai.value.index
  editor.blocks.insertMany(ai.value.preview, index)
  editor.blocks.delete(index + ai.value.preview.length)
  ai.value.visible = false
  ai.value.preview = null
  closeAiAnchor()
  document.removeEventListener('mousedown', onDocMouseDown, true)
  const first = editor.blocks.getBlockByIndex(index)
  if (first) focusBlockEnd(first)
}

// 段落开头文本 → 目标块（Editor.js 各插件的数据结构）
function matchMd(text) {
  let m = text.match(/^(#{1,3})\s([\s\S]*)$/)
  if (m) return { type: 'header', data: { text: m[2], level: m[1].length } }
  m = text.match(/^[-*]\s([\s\S]*)$/)
  if (m) return { type: 'list', data: { style: 'unordered', items: [{ content: m[1], items: [] }] } }
  m = text.match(/^\d{1,2}\.\s([\s\S]*)$/)
  if (m) return { type: 'list', data: { style: 'ordered', items: [{ content: m[1], items: [] }] } }
  m = text.match(/^\[\s?\]\s([\s\S]*)$/)
  if (m) return { type: 'checklist', data: { items: [{ text: m[1], checked: false }] } }
  m = text.match(/^>\s([\s\S]*)$/)
  if (m) return { type: 'toggle', data: { text: m[1], content: '', expanded: true } }  // > 空格 = 折叠块（Notion 行为）
  if (/^---+\s*$/.test(text)) return { type: 'delimiter', data: {} }
  return null
}

function mdShortcut(e) {
  if (!editor) return
  // '/' 落入空块 → 拉起块菜单；菜单打开期间每次输入都同步查询词、重置选中项并跟随光标
  if (slashPending || slash.value.visible) {
    const index = editor.blocks.getCurrentBlockIndex()
    const block = index >= 0 ? editor.blocks.getBlockByIndex(index) : null
    const text = block && SLASH_CONVERTIBLE.includes(block.name) ? (block.holder.textContent || '') : ''
    if (slashPending) {
      if (block && text.startsWith('/')) openSlash({ index, block })
      slashPending = null
      return
    }
    if (!block || !text.startsWith('/')) {
      closeSlash()  // 用户删掉了 '/' 或光标移走：关菜单
      return
    }
    const q = text.slice(1)
    if (q !== slash.value.query) {
      slash.value.query = q
      slash.value.active = 0  // 查询词变化才重置高亮（ArrowDown/Enter 的 keyup 不能冲掉选择）
    }
    slash.value.index = index
    const { x, y } = slashPosition(block)
    slash.value.x = x
    slash.value.y = y
    return
  }
  if (e.key === 'Backspace') return emptyBlockFallback(e)
  if (e.key !== ' ' && e.key !== '-') return  // 空格触发前缀转换；连打 - 触发分割线
  const index = editor.blocks.getCurrentBlockIndex()
  if (index < 0) return
  const block = editor.blocks.getBlockByIndex(index)
  if (!block || block.name !== 'paragraph') return  // 只在段落块上转换
  const text = (block.holder.textContent || '').replace(/ /g, ' ')
  const rule = matchMd(text)
  if (!rule) return
  // insert 是同步 API（返回 BlockAPI，不是 Promise）：转换立即完成
  const newBlock = editor.blocks.insert(rule.type, rule.data, {}, index, true, true)
  setTimeout(() => {
    // 原生聚焦（needToFocus）失败时兜底：直接把选区放到新块 contenteditable 末尾
    const active = document.activeElement
    if (active && newBlock.holder?.contains(active)) return
    focusBlockEnd(newBlock)
  }, 50)
}

function focusBlockEnd(blockApi) {
  const el = blockApi?.holder?.querySelector('[contenteditable="true"]')
  if (!el) return
  el.focus()
  const range = document.createRange()
  range.selectNodeContents(el)
  range.collapse(false)  // 折叠到末尾
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
}

// Editor.js 的 Backspace 处理在"空块且没有上一个块"时直接 return，
// 空的标题/引用等块会永远保持样式；补 Notion 行为：空的非段落块 + Backspace → 转回段落
function emptyBlockFallback(e) {
  const index = editor.blocks.getCurrentBlockIndex()
  if (index < 0) return
  const block = editor.blocks.getBlockByIndex(index)
  // 多块场景 Editor.js 已在 keydown 删除空块并把光标移到上一段（段落），这里不会命中；
  // 列表/待办的空项由插件自己处理（keydown 时已转成段落），也不会命中
  if (!block || block.name === 'paragraph') return
  // 判空时剔除折叠块的三角字符与空白（折叠块的 textContent 永远含 ▸/▾）
  if ((block.holder.textContent || '').replace(/[▸▾]/g, '').trim()) return
  const newBlock = editor.blocks.insert('paragraph', { text: '' }, {}, index, true, true)
  setTimeout(() => {
    const active = document.activeElement
    if (active && newBlock.holder?.contains(active)) return
    focusBlockEnd(newBlock)
  }, 50)
}

async function destroyEditor() {
  if (saveTimer) clearTimeout(saveTimer)
  if (dirty) await flushSave()
  ai.value.visible = false
  ai.value.preview = null
  closeAiAnchor()
  slash.value.visible = false
  slashPending = null
  document.removeEventListener('mousedown', onDocMouseDown, true)
  document.removeEventListener('mousedown', onSlashDocDown, true)
  editorEl.value?.removeEventListener('keyup', mdShortcut)
  editorEl.value?.removeEventListener('keydown', onEditorKeydown, true)
  if (editor?.destroy) {
    try { await editor.destroy() } catch { /* 已销毁 */ }
  }
  editor = null
}

const scheduleSave = () => {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(flushSave, 1000)
}

async function flushSave() {
  if (!editor || !current.value || saving) return
  saving = true
  saveState.value = '保存中…'
  try {
    const data = await editor.save()
    const res = await updateNote(current.value.id, { blocks: data.blocks })
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
  await destroyEditor()
  current.value = null
  saveState.value = ''
  try {
    const full = await getNote(n.id)
    current.value = full
    await nextTick()
    initEditor(full.blocks)
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

async function togglePin(n) {
  try {
    const res = await updateNote(n.id, { pinned: !n.pinned })
    if (current.value?.id === n.id) current.value.pinned = res.pinned
    await loadTree()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function del(n) {
  try {
    await deleteNote(n.id)
    ElMessage.success('已删除')
    if (current.value?.id === n.id) {
      await destroyEditor()
      current.value = null
    }
    await loadTree()
    if (searchResults.value !== null) onSearchInput()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(loadTree)
onBeforeUnmount(destroyEditor)
</script>

<style scoped>
.notes-page { display: flex; gap: 16px; height: calc(100vh - 110px); }

/* 左侧页面树 */
.notes-side {
  width: 280px; flex-shrink: 0; background: #fff; border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .06); display: flex; flex-direction: column; overflow: hidden;
}
.side-top { display: flex; gap: 8px; padding: 12px; border-bottom: 1px solid #ebeef5; }
.tree { flex: 1; overflow-y: auto; padding: 6px 4px; }
.tree-item {
  display: flex; align-items: center; gap: 4px; padding: 7px 8px; border-radius: 6px;
  cursor: pointer; font-size: 14px; color: #303133;
}
.tree-item:hover { background: #f5f7fa; }
.tree-item.active { background: #ecf5ff; color: #409eff; }
.pin-flag { color: #e6a23c; font-size: 13px; flex-shrink: 0; }
.tree-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-ops { display: none; gap: 2px; flex-shrink: 0; color: #909399; }
.tree-item:hover .tree-ops { display: inline-flex; }
.tree-ops .el-icon { padding: 2px; border-radius: 4px; font-size: 14px; }
.tree-ops .el-icon:hover { background: #e4e7ed; color: #303133; }
.side-empty { padding: 40px 12px; text-align: center; color: #c0c4cc; font-size: 13px; }

/* 右侧编辑区 */
.notes-main {
  flex: 1; background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0, 0, 0, .06);
  display: flex; flex-direction: column; overflow: hidden; position: relative;
}

/* AI 写作面板：内嵌文档流，占实际位置 */
.ai-panel {
  margin: 2px 0 8px; padding: 12px 14px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .08);
  display: flex; flex-direction: column;
}
.ai-panel-head { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.ai-input {
  width: 100%; border: none; outline: none; font-size: 14px; color: #303133;
  padding: 6px 0; background: transparent; box-sizing: border-box;
}
.ai-input::placeholder { color: #c0c4cc; }
.ai-panel-ops { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.ai-hint { font-size: 12px; color: #c0c4cc; }
.ai-error { font-size: 12px; color: #f56c6c; margin-top: 6px; }
.ai-preview {
  max-height: 40vh; overflow-y: auto; margin-top: 8px; padding: 8px 2px 2px;
  border-top: 1px dashed #e4e7ed;
}
.pv { font-size: 14px; line-height: 1.8; color: #303133; }
.pv-h1 { font-size: 20px; font-weight: 700; margin-top: 6px; }
.pv-h2 { font-size: 17px; font-weight: 700; margin-top: 4px; }
.pv-h3 { font-size: 15px; font-weight: 600; margin-top: 2px; }
.pv-li { padding-left: 18px; }
.pv-quote { border-left: 3px solid #dcdfe6; padding-left: 10px; color: #606266; }
.main-top {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 24px 8px;
}
.title-input {
  flex: 1; border: none; outline: none; font-size: 24px; font-weight: 700; color: #303133;
  background: transparent; min-width: 0;
}
.title-input::placeholder { color: #c0c4cc; }
.main-ops { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.save-state { font-size: 12px; color: #909399; margin-right: 8px; }
.save-state.err { color: #f56c6c; }
.editor-holder { flex: 1; overflow-y: auto; padding: 4px 24px 24px; }
.editor-tip { padding: 8px 24px; font-size: 12px; color: #c0c4cc; border-top: 1px solid #f2f6fc; }

/* Editor.js 主题微调：更像 Notion 的留白与字号 */
.editor-holder :deep(.ce-block__content) { max-width: 100%; }
.editor-holder :deep(.ce-toolbar__content) { max-width: 100%; }
.editor-holder :deep(.codex-editor__redactor) { padding-bottom: 120px !important; }
.editor-holder :deep(.ce-paragraph) { line-height: 1.8; font-size: 15px; }
/* 显式声明标题字号：不依赖 UA 默认样式，保证转换后大小确定 */
.editor-holder :deep(h1.ce-header) { font-size: 28px; font-weight: 700; }
.editor-holder :deep(h2.ce-header) { font-size: 23px; font-weight: 700; }
.editor-holder :deep(h3.ce-header) { font-size: 19px; font-weight: 600; }
.editor-holder :deep(.ce-header) { padding: 0.6em 0 0.3em; margin: 0; }

/* 引用块：隐藏 caption 题注框（避免"两个框"），Notion 式左边框 */
.editor-holder :deep(.cdx-quote__caption) { display: none; }
.editor-holder :deep(.cdx-quote__text) { min-height: 0 !important; margin-bottom: 0 !important; }

/* 折叠块（toggle） */
.editor-holder :deep(.toggle-block) { line-height: 1.8; }
.editor-holder :deep(.toggle-head) { display: flex; align-items: center; gap: 2px; }
.editor-holder :deep(.toggle-arrow) {
  width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; border-radius: 4px; color: #606266; user-select: none; font-size: 15px; flex-shrink: 0;
}
.editor-holder :deep(.toggle-arrow:hover) { background: #f0f2f5; }
.editor-holder :deep(.toggle-title) { flex: 1; outline: none; font-weight: 600; color: #303133; }
.editor-holder :deep(.toggle-body) {
  margin-left: 28px; outline: none; color: #606266;
  border-left: 2px solid #ebeef5; padding-left: 10px;
}
.editor-holder :deep(.toggle-block.collapsed .toggle-body) { display: none; }

/* / 块菜单（仿 Notion）：Teleport 到 body，fixed 定位不被编辑器容器裁剪 */
.slash-menu {
  position: fixed; z-index: 3000; width: 250px; max-height: 380px; overflow-y: auto;
  background: #fff; border-radius: 10px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, .12), 0 0 0 1px rgba(0, 0, 0, .04);
  padding: 6px 4px 0;
}
.slash-group { padding: 6px 12px 2px; font-size: 12px; color: #909399; }
.slash-item { display: flex; align-items: center; gap: 10px; padding: 5px 10px; border-radius: 6px; cursor: pointer; }
.slash-item.active { background: #f5f7fa; }
.slash-icon {
  width: 26px; height: 26px; flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid #e4e7ed; border-radius: 6px; background: #fff; font-size: 11px; color: #606266;
}
.slash-label { flex: 1; font-size: 14px; color: #303133; }
.slash-hint { font-size: 12px; color: #c0c4cc; }
.slash-empty { padding: 16px 12px; font-size: 13px; color: #c0c4cc; }
.slash-foot {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 4px; padding: 8px 12px; border-top: 1px solid #f2f6fc; font-size: 12px; color: #909399;
}
.slash-key { padding: 1px 6px; border: 1px solid #e4e7ed; border-radius: 4px; background: #f5f7fa; font-size: 11px; }
</style>
