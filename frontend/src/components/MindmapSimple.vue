<template>
  <div ref="wrap" class="mm-wrap">
    <div ref="el" class="mm-canvas" />

    <!-- 自建右键菜单：npm 包只发 node_contextmenu 事件，菜单 UI 由使用方实现 -->
    <div v-if="menu.show" class="mm-menu" :style="{ left: menu.x + 'px', top: menu.y + 'px' }">
      <div
        v-for="item in menuItems" :key="item.label"
        class="mm-menu-item" :class="{ disabled: item.disabled }"
        @click="runItem(item)"
      >{{ item.label }}</div>
    </div>

    <!-- 图片 -->
    <el-dialog v-model="dlg.image" title="插入图片" width="420px" append-to-body destroy-on-close>
      <el-form label-width="70px" size="small">
        <el-form-item label="图片URL" required><el-input v-model="imageForm.url" placeholder="https://..." /></el-form-item>
        <el-form-item label="标题"><el-input v-model="imageForm.title" /></el-form-item>
        <el-form-item label="宽高">
          <el-input-number v-model="imageForm.width" :min="10" :max="500" size="small" /> ×
          <el-input-number v-model="imageForm.height" :min="10" :max="500" size="small" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.image = false">取消</el-button>
        <el-button type="primary" @click="applyImage">确定</el-button>
      </template>
    </el-dialog>

    <!-- 超链接 -->
    <el-dialog v-model="dlg.link" title="插入超链接" width="420px" append-to-body destroy-on-close>
      <el-form label-width="70px" size="small">
        <el-form-item label="链接" required><el-input v-model="linkForm.url" placeholder="https://..." /></el-form-item>
        <el-form-item label="标题"><el-input v-model="linkForm.title" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.link = false">取消</el-button>
        <el-button type="primary" @click="applyLink">确定</el-button>
      </template>
    </el-dialog>

    <!-- 备注 -->
    <el-dialog v-model="dlg.note" title="节点备注" width="480px" append-to-body destroy-on-close>
      <el-input v-model="noteText" type="textarea" :rows="5" placeholder="支持多行文本" />
      <template #footer>
        <el-button @click="dlg.note = false">取消</el-button>
        <el-button type="primary" @click="applyNote">确定</el-button>
      </template>
    </el-dialog>

    <!-- 图标 -->
    <el-dialog v-model="dlg.icon" title="插入图标" width="560px" append-to-body destroy-on-close>
      <div class="icon-toolbar">
        <el-button size="small" plain type="danger" @click="clearIcon">清除节点图标</el-button>
      </div>
      <div v-for="g in iconGroups" :key="g.type" class="icon-group">
        <div class="icon-group-name">{{ g.name }}</div>
        <div class="icon-grid">
          <span
            v-for="ic in g.list" :key="ic.name" class="icon-cell" :title="ic.name"
            @click="applyIcon(g.type + '_' + ic.name)"
          ><span class="icon-svg" v-html="ic.icon" /></span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
// simple-mind-map 全量插件（手动注册，排除 Scrollbar——它会把画布拖动钳制在内容范围内，体验像"拖不动"）：
// 富文本节点、拖拽、多选、关联线、概要（外框）、导出、搜索、小地图、彩虹线条、公式、触摸板等。
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import MindMap from 'simple-mind-map'
import MiniMap from 'simple-mind-map/src/plugins/MiniMap.js'
import Watermark from 'simple-mind-map/src/plugins/Watermark.js'
import KeyboardNavigation from 'simple-mind-map/src/plugins/KeyboardNavigation.js'
import ExportXMind from 'simple-mind-map/src/plugins/ExportXMind.js'
import ExportPDF from 'simple-mind-map/src/plugins/ExportPDF.js'
import Export from 'simple-mind-map/src/plugins/Export.js'
import Drag from 'simple-mind-map/src/plugins/Drag.js'
import Select from 'simple-mind-map/src/plugins/Select.js'
import AssociativeLine from 'simple-mind-map/src/plugins/AssociativeLine'
import RichText from 'simple-mind-map/src/plugins/RichText'
import NodeImgAdjust from 'simple-mind-map/src/plugins/NodeImgAdjust.js'
import TouchEvent from 'simple-mind-map/src/plugins/TouchEvent.js'
import Search from 'simple-mind-map/src/plugins/Search.js'
import Painter from 'simple-mind-map/src/plugins/Painter.js'
import Formula from 'simple-mind-map/src/plugins/Formula.js'
import RainbowLines from 'simple-mind-map/src/plugins/RainbowLines.js'
import Demonstrate from 'simple-mind-map/src/plugins/Demonstrate.js'
import OuterFrame from 'simple-mind-map/src/plugins/OuterFrame.js'
import NodeBase64ImageStorage from 'simple-mind-map/src/plugins/NodeBase64ImageStorage.js'
import icons from 'simple-mind-map/src/svg/icons.js'
import Themes from 'simple-mind-map-plugin-themes'
import { canonicalToSimple, simpleToCanonical } from '../mindmap/convert'

MindMap
  .usePlugin(MiniMap).usePlugin(Watermark).usePlugin(Drag).usePlugin(KeyboardNavigation)
  .usePlugin(ExportXMind).usePlugin(ExportPDF).usePlugin(Export).usePlugin(Select)
  .usePlugin(AssociativeLine).usePlugin(RichText).usePlugin(TouchEvent).usePlugin(NodeImgAdjust)
  .usePlugin(Search).usePlugin(Painter).usePlugin(Formula).usePlugin(RainbowLines)
  .usePlugin(Demonstrate).usePlugin(OuterFrame).usePlugin(NodeBase64ImageStorage)

// 主题包注册（模块级一次）：defineTheme 进 MindMap 静态注册表
Themes.init(MindMap)

const props = defineProps({
  data: { type: Object, required: true },
  readonly: { type: Boolean, default: false },   // 分享页等只读场景
})
const emit = defineEmits(['change'])   // data_change 时触发（离开保护的 dirty 追踪用）
const wrap = ref(null)
const el = ref(null)
let mind = null

// 图标选择器数据（库内置 SVG 图标库，按分组展示）
const iconGroups = icons.nodeIconList || []

const menu = reactive({ show: false, x: 0, y: 0, node: null })
let cutClipboard = null   // 剪切/复制的节点数据（CUT/COPY 作用于激活节点，回调取数）
const menuItems = reactive([])
const dlg = reactive({ image: false, link: false, note: false, icon: false })
const imageForm = reactive({ url: '', title: '', width: 100, height: 100 })
const linkForm = reactive({ url: '', title: '' })
const noteText = ref('')

const MENU = [
  { label: '插入子节点', cmd: 'INSERT_CHILD_NODE' },
  { label: '插入同级节点', cmd: 'INSERT_NODE', noRoot: true },
  { label: '插入父节点', cmd: 'INSERT_PARENT_NODE', noRoot: true },
  { label: '插入概要', cmd: 'ADD_OUTER_FRAME', noRoot: true },
  { label: '插入关联线', cmd: 'ADD_ASSOCIATIVE_LINE', noRoot: true },
  { label: '插入图标', dialog: 'icon' },
  { label: '插入图片', dialog: 'image' },
  { label: '插入超链接', dialog: 'link' },
  { label: '节点备注', dialog: 'note' },
  { label: '上移', cmd: 'UP_NODE', noRoot: true },
  { label: '下移', cmd: 'DOWN_NODE', noRoot: true },
  { label: '复制', cmd: 'COPY_NODE', noRoot: true },
  { label: '剪切', cmd: 'CUT_NODE', noRoot: true },
  { label: '粘贴为子节点', cmd: 'PASTE_NODE' },
  { label: '删除节点', cmd: 'REMOVE_NODE', noRoot: true },
]

function onNodeContextmenu(e, node) {
  const rect = wrap.value.getBoundingClientRect()
  menu.x = e.clientX - rect.left
  menu.y = e.clientY - rect.top
  menu.node = node
  menu.show = true
  const isRoot = !!node.isRoot   // Node 实例的布尔属性（nodeData.parent 不可靠）
  const canPaste = !!(cutClipboard || mind.renderer?.beingCopyData)
  menuItems.splice(0, menuItems.length,
    ...MENU.map((m) => ({ ...m, disabled: !!(m.noRoot && isRoot) || (m.cmd === 'PASTE_NODE' && !canPaste) })))
}

// 注意：不要在这里主动 SET_NODE_ACTIVE——渲染会重建节点对象，旧引用激活无效反而清空激活列表；
// 右键时库已激活被点节点（node_contextmenu 前的 active()），CUT/PASTE 直接作用于它即可。
function runItem(item) {
  if (item.disabled) return
  menu.show = false
  // 剪切：作用于激活节点，回调接收剪贴数据（节点随即被移除）
  // 复制：renderer.copyNode() 取当前激活节点数据（不删原节点）
  if (item.cmd === 'COPY_NODE') {
    const data = mind.renderer.copyNode()
    if (data) {
      cutClipboard = data
      ElMessage.success('已复制，可在目标节点右键「粘贴为子节点」')
    }
    return
  }
  if (item.cmd === 'CUT_NODE') {
    mind.execCommand('CUT_NODE', (data) => { cutClipboard = data })
    return
  }
  // 粘贴：目标是激活节点（右键时已激活被点节点），数据来自剪切/复制（兼容 Ctrl+C 的内部剪贴板）
  if (item.cmd === 'PASTE_NODE') {
    const data = cutClipboard || mind.renderer.beingCopyData
    if (!data) return ElMessage.warning('请先剪切或复制一个节点')
    mind.execCommand('PASTE_NODE', data)
    return
  }
  if (item.dialog) {
    const node = menu.node
    // 回填现值：再次打开即编辑；清空提交即移除
    if (item.dialog === 'image') {
      Object.assign(imageForm, {
        url: node?.getData('image') || '',
        title: node?.getData('imageTitle') || '',
        width: node?.getData('imageSize')?.width || 100,
        height: node?.getData('imageSize')?.height || 100,
      })
    }
    if (item.dialog === 'link') {
      Object.assign(linkForm, {
        url: node?.getData('hyperlink') || '',
        title: node?.getData('hyperlinkTitle') || '',
      })
    }
    if (item.dialog === 'note') noteText.value = node?.getData('note') || ''
    dlg[item.dialog] = true
    return
  }
  try {
    if (item.cmd === 'ADD_ASSOCIATIVE_LINE') {
      // 创建入口是插件实例方法 createLine（进入连线模式，再点目标节点完成）
      ElMessage.info('连线模式：请点击要连接的目标节点，Esc 取消')
      mind.associativeLine.createLine(menu.node)
    } else {
      mind.execCommand(item.cmd, menu.node)
    }
  } catch { /* 根节点限制等由库兜底 */ }
}

function applyImage() {
  // 留空 = 移除图片
  mind.execCommand('SET_NODE_IMAGE', menu.node, {
    url: imageForm.url.trim(), title: imageForm.title.trim(),
    width: imageForm.width, height: imageForm.height, custom: true,
  })
  dlg.image = false
}

function applyLink() {
  // 留空 = 移除超链接
  mind.execCommand('SET_NODE_HYPERLINK', menu.node, linkForm.url.trim(), linkForm.title.trim())
  dlg.link = false
}

function applyNote() {
  mind.execCommand('SET_NODE_NOTE', menu.node, noteText.value)
  dlg.note = false
}

function applyIcon(name) {
  // 图标数据的 key 格式是「分组_名称」（如 priority_1），库按此格式查表渲染
  mind.execCommand('SET_NODE_ICON', menu.node, [name])
  dlg.icon = false
}

function clearIcon() {
  mind.execCommand('SET_NODE_ICON', menu.node, [])
  dlg.icon = false
}

function hideMenu() {
  menu.show = false
}

onMounted(() => {
  // 先以空文档初始化，再按存储格式装载
  mind = new MindMap({
    el: el.value,
    readonly: props.readonly,
    data: canonicalToSimple({ text: '中心主题', children: [] }),
  })
  const d = props.data
  if (d && d.root) {
    // 原生文档：root 节点树（含图标/图片/链接/备注/概要/关联线）+ 布局 + 主题 + 视图全恢复
    mind.setFullData(d)
  } else {
    // 旧中间格式 {text, children[]}：转纯文本树；主题/布局/分支样式取本地偏好
    mind.setData(canonicalToSimple(d && typeof d.text === 'string' ? d : { text: '中心主题', children: [] }))
    const t = localStorage.getItem('grt_mm_simple_theme')
    if (t) mind.setTheme(t)
    const lo = localStorage.getItem('grt_mm_simple_layout')
    if (lo) mind.setLayout(lo)
    const ls = localStorage.getItem('grt_mm_simple_linestyle')
    if (ls) mind.setThemeConfig({ lineStyle: ls })
  }
  if (!props.readonly) {
    mind.on('node_contextmenu', onNodeContextmenu)
    document.addEventListener('click', hideMenu)
  }
  // 历史栈状态同步（驱动 前进/后退 按钮灰化）
  mind.on('data_change', () => { syncHistoryState(); emit('change') })
  mind.on('back_forward', syncHistoryState)
  // 装载过程（初始空文档→文档数据）产生的历史清掉：刚打开不应可"后退"到空文档
  mind.command.history = []
  mind.command.activeHistoryIndex = -1
  syncHistoryState()
})

// 保存：完整原生文档（节点全字段 + 布局/主题/视图），装饰数据不再丢失
function getDoc() {
  return mind ? mind.getData(true) : props.data
}

// 大纲用：从原生节点树抽纯文本中间格式
function getCanonical() {
  if (!mind) return props.data
  return simpleToCanonical(mind.getData())
}

function setTheme(name) {
  mind?.setTheme(name)
  localStorage.setItem('grt_mm_simple_theme', name)
}

// 导出 PNG（Export 插件实例名 doExport）
async function exportPng(name) {
  if (!mind) return
  try {
    await mind.doExport.export('png', true, name || '思维导图')
  } catch (e) {
    ElMessage.error('导出失败：' + (e?.message || e))
  }
}

function setLayout(name) {
  mind?.setLayout(name)
  localStorage.setItem('grt_mm_simple_layout', name)
}

// 分支样式：曲线 curve / 直线 straight / 直连 direct（部分布局不支持时库自行降级）
function setLineStyle(style) {
  mind?.setThemeConfig({ lineStyle: style })
  localStorage.setItem('grt_mm_simple_linestyle', style)
}

// 前进/后退（库内置历史栈：BACK/FORWARD 命令）+ 可用状态（按钮灰化）
const canUndo = ref(false)
const canRedo = ref(false)

function syncHistoryState() {
  if (!mind) return
  const { history, activeHistoryIndex } = mind.command
  canUndo.value = activeHistoryIndex > 0
  canRedo.value = activeHistoryIndex < history.length - 1
}

function undo() {
  mind?.execCommand('BACK')
}

function redo() {
  mind?.execCommand('FORWARD')
}

defineExpose({ getDoc, getCanonical, setTheme, setLayout, setLineStyle, exportPng, undo, redo, canUndo, canRedo })

onBeforeUnmount(() => {
  document.removeEventListener('click', hideMenu)
  try { mind?.destroy?.() } catch { /* 忽略 */ }
  mind = null
})
</script>

<style scoped>
.mm-wrap { position: relative; width: 100%; height: 100%; }
.mm-canvas { width: 100%; height: 100%; }

/* RichText 插件用 foreignObject 渲染节点文字，<p> 默认 margin 会把文字挤出可视高度 */
.mm-canvas :deep(.smm-richtext-node-wrap p) { margin: 0; }

.mm-menu {
  position: absolute; z-index: 3000; min-width: 140px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, .12); padding: 4px;
}
.mm-menu-item {
  padding: 7px 14px; font-size: 13px; color: #303133;
  border-radius: 4px; cursor: pointer; white-space: nowrap;
}
.mm-menu-item:hover { background: #ecf5ff; color: #409eff; }
.mm-menu-item.disabled { color: #c0c4cc; cursor: not-allowed; }
.mm-menu-item.disabled:hover { background: none; color: #c0c4cc; }

.icon-toolbar { margin-bottom: 10px; }
.icon-group { margin-bottom: 10px; }
.icon-group-name { font-size: 12px; color: #909399; margin-bottom: 6px; }
.icon-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.icon-cell {
  width: 34px; height: 34px; display: flex; align-items: center; justify-content: center;
  border: 1px solid #e4e7ed; border-radius: 6px; cursor: pointer;
}
.icon-cell:hover { border-color: #409eff; background: #ecf5ff; }
.icon-svg { display: flex; }
.icon-svg :deep(svg) { width: 20px; height: 20px; }
</style>
