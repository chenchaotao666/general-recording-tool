<template>
  <div ref="wrap" class="mm-wrap">
    <div ref="el" class="mm-canvas" />

    <!-- 自建右键菜单：npm 包只发 node_contextmenu 事件，菜单 UI 由使用方实现 -->
    <div v-if="menu.show" class="mm-menu" :style="{ left: menu.x + 'px', top: menu.y + 'px' }">
      <div
        v-for="item in menuItems" :key="item.label"
        class="mm-menu-item" :class="{ 'mm-menu-item-ai': item.ai }"
        @click="runItem(item)"
      ><span v-if="item.ai" class="mm-menu-icon" v-html="MAGIC_STICK_SVG" />{{ item.label }}</div>
    </div>

    <!-- 图片（非模态：出现在触发按钮附近，宽度与其它编辑弹窗统一 360px） -->
    <el-dialog v-model="dlg.image" title="插入图片" width="450px" :z-index="3100" :modal="false" modal-penetrable :lock-scroll="false" :style="popStyle" append-to-body destroy-on-close>
      <el-form label-width="70px" size="small">
        <el-form-item label="本地图片">
          <el-button size="small" @click="pickLocalImage">选择文件…</el-button>
          <span class="mm-dlg-hint" style="margin-left: 8px">自动压缩到 900px 内</span>
          <input ref="imageFileInput" type="file" accept="image/*" style="display: none" @change="onImageFileChange" />
        </el-form-item>
        <!-- 本地上传的图片 url 是超长 data URL，不提供编辑（改了图片就坏）；要换图就重新选择文件 -->
        <el-form-item v-if="!isLocalImage" label="图片URL">
          <el-input v-model="imageForm.url" placeholder="https://...（或上方选本地图片）" />
        </el-form-item>
        <el-form-item v-if="imageForm.url" label="预览">
          <div class="mm-img-preview-wrap">
            <img :src="imageForm.url" class="mm-img-preview" alt="图片预览" @error="imgPreviewErr = true" @load="imgPreviewErr = false" />
            <div class="mm-img-preview-side">
              <span v-if="imgPreviewErr" class="mm-img-preview-err">图片加载失败，请检查 URL</span>
              <el-button size="small" text type="danger" @click="imageForm.url = ''">移除</el-button>
            </div>
          </div>
        </el-form-item>
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
    <el-dialog v-model="dlg.link" title="插入超链接" width="450px" :z-index="3100" :modal="false" modal-penetrable :lock-scroll="false" :style="popStyle" append-to-body destroy-on-close>
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
    <el-dialog v-model="dlg.note" title="节点备注" width="450px" :z-index="3100" :modal="false" modal-penetrable :lock-scroll="false" :style="popStyle" append-to-body destroy-on-close>
      <el-input v-model="noteText" type="textarea" :rows="5" placeholder="支持多行文本" />
      <template #footer>
        <el-button @click="dlg.note = false">取消</el-button>
        <el-button type="primary" @click="applyNote">确定</el-button>
      </template>
    </el-dialog>

    <!-- 标签 -->
    <el-dialog v-model="dlg.tag" title="节点标签" width="450px" :z-index="3100" :modal="false" modal-penetrable :lock-scroll="false" :style="popStyle" append-to-body destroy-on-close>
      <el-input v-model="tagText" placeholder="多个标签用逗号分隔，如：重点，本周，跟进中" />
      <div class="mm-dlg-hint">标签显示在节点文字下方；清空提交 = 移除全部标签</div>
      <template #footer>
        <el-button @click="dlg.tag = false">取消</el-button>
        <el-button type="primary" @click="applyTag">确定</el-button>
      </template>
    </el-dialog>

    <!-- 图片/图标/超链接/备注/标签标记的操作浮层（单击标记弹出：✎ 编辑 / × 删除，链接含 ↗ 打开） -->
    <div
      v-if="opTip.show" class="mm-op-tip"
      :style="{ left: opTip.x + 'px', top: opTip.y + 'px' }"
      @click.stop
    >
      <button v-if="opTip.kind === 'link'" type="button" title="打开链接" @click="opOpen">↗</button>
      <button type="button" title="编辑" @click="opEdit">✎</button>
      <button type="button" class="danger" title="删除" @click="opDelete">×</button>
    </div>

    <!-- 备注浮层（customNoteContentShow 自定义，替代库默认纯文本 tooltip）：
         悬停备注图标显示，纯预览（编辑/删除改为单击备注图标弹出操作浮层） -->
    <div
      v-if="noteTip.show" class="mm-note-tip"
      :style="{ left: noteTip.left + 'px', top: noteTip.top + 'px' }"
      @mouseenter="cancelHideNoteTip" @mouseleave="scheduleHideNoteTip"
    >
      <div class="mm-note-tip-text">{{ noteTip.text }}</div>
    </div>

    <!-- 图片悬停操作：图片右上角 ✎ 编辑 / × 删除（替代库默认的右上角删除按钮，已用 CSS 隐藏） -->
    <div
      v-if="imgTip.show" class="mm-img-tip"
      :style="{ left: imgTip.left + 'px', top: imgTip.top + 'px' }"
      @mouseenter="cancelHideImgTip" @mouseleave="scheduleHideImgTip"
    >
      <button type="button" title="编辑图片" @click="editImgTip">✎</button>
      <button type="button" title="删除图片" @click="deleteImgTip">×</button>
    </div>

    <!-- 图标 -->
    <el-dialog v-model="dlg.icon" title="插入图标" width="540px" :z-index="3100" :modal="false" modal-penetrable :lock-scroll="false" :style="popStyle" append-to-body destroy-on-close>
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
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
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
  .usePlugin(OuterFrame).usePlugin(NodeBase64ImageStorage)

// 主题包注册（模块级一次）：defineTheme 进 MindMap 静态注册表
Themes.init(MindMap)

const props = defineProps({
  data: { type: Object, required: true },
  readonly: { type: Boolean, default: false },   // 分享页等只读场景
})
const emit = defineEmits(['change', 'ai'])   // change: data_change 时触发（离开保护的 dirty 追踪用）；ai: 右键菜单「AI 生成」
const wrap = ref(null)
const el = ref(null)
let mind = null

// 图标选择器数据（库内置 SVG 图标库，按分组展示）
const iconGroups = icons.nodeIconList || []

const menu = reactive({ show: false, x: 0, y: 0, cx: 0, cy: 0, node: null })   // x/y 相对画布（菜单定位）；cx/cy 屏幕坐标（AI 面板锚点）
let cutClipboard = null   // 剪切/复制的节点数据（CUT/COPY 作用于激活节点，回调取数）
let preContextSelection = []   // 右键前的激活选区快照（capture 阶段采集，恢复多选用）
const menuItems = reactive([])
const dlg = reactive({ image: false, link: false, note: false, icon: false, tag: false })

// ---------- 编辑弹窗定位（非模态，出现在触发的编辑按钮/菜单附近；宽度统一 450px，图标 540px） ----------
const POP_W = 450
const POP_W_ICON = 540
const popPos = reactive({ x: 8, y: 8, w: POP_W })   // 弹窗实际位置（屏幕坐标）
// 弹窗与所属节点的相对偏移：拖动/缩放/滚动时按偏移跟随。
// side=right 时 dx 相对节点右边缘，side=left 时 dx 相对节点左边缘（贴边翻转后不漂）
let popOff = null   // { dx, dy, side }
const popStyle = computed(() => ({
  position: 'absolute', margin: 0, maxHeight: '70vh', overflowY: 'auto',
  left: popPos.x + 'px', top: popPos.y + 'px',
}))
// 垂直方向按真实渲染高度钳制（按估算高度会把高弹窗底部裁出屏幕外）；
// 水平方向只做左缘兜底（右缘由翻转/打开定位负责，钳制会导致跟随时相对漂移）
function placePop(x, y) {
  const d = document.querySelector('.el-dialog')
  const H = d?.offsetHeight || 200
  popPos.x = Math.max(8, x)
  popPos.y = Math.max(8, Math.min(y, window.innerHeight - H - 8))
}
// 打开定位：点击点右侧放得下就放右侧 → 放不下翻节点左侧贴边 → 都不行钳制进视口。
// 必须打开就在视口内：否则伸出右缘后，第一次拖动/滚动触发跟随修正时弹窗会突然左跳
function computePopX(r, clientX, w) {
  if (clientX + 12 + w <= window.innerWidth - 8) return { x: clientX + 12, side: 'right' }
  if (r && r.left - 12 - w >= 8) return { x: r.left - w - 12, side: 'left' }
  return { x: Math.max(8, window.innerWidth - w - 8), side: 'right' }
}
function anchorPop(clientX, clientY, w = POP_W) {
  popPos.w = w
  // 等弹窗渲染出来再量真实高度定位，并记录与节点的相对偏移
  nextTick(() => requestAnimationFrame(() => {
    const r = _nodeContentRect(_liveNode(menu.node))
    const { x, side } = computePopX(r, clientX, w)
    placePop(x, clientY + 12)
    popOff = r ? { dx: popPos.x - (side === 'right' ? r.right : r.left), dy: popPos.y - r.top, side } : null
  }))
}
// 非模态没有遮罩，自己实现"点外部关闭"。用 click 而不是 mousedown：
// 画布拖动/框选只有 mousedown 没有 click，拖动时弹窗不关闭、跟随节点移动（syncPopToNode）
function onDocDownCloseDlg(e) {
  const open = Object.keys(dlg).find((k) => dlg[k])
  if (!open) return
  if (e.target.closest?.('.el-dialog')) return
  dlg[open] = false
}

// 节点内容区的屏幕矩形。排除所有随状态显隐的覆盖层——它们的显隐会改变 group 包围盒、导致弹窗漂移：
//   .smm-expand-btn（展开/收起按钮）、.smm-quick-create-child-btn（激活态"+"按钮）、
//   .smm-hover-node（悬停/激活高亮框，比节点本体大一圈）、无类名 rect（激活态宽度调节手柄）
function _nodeContentRect(node) {
  const g = node?.group?.node
  if (!g) return null
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity
  for (const child of g.children) {
    const cls = child.classList
    if (cls?.contains('smm-expand-btn') || cls?.contains('smm-quick-create-child-btn') || cls?.contains('smm-hover-node')) continue
    if (child.tagName === 'rect' && !cls?.length) continue   // 宽度调节手柄（激活态出现，无类名）
    const r = child.getBoundingClientRect()
    if (!r.width && !r.height) continue
    x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top)
    x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom)
  }
  if (x1 === Infinity) return g.getBoundingClientRect()
  return { left: x1, top: y1, right: x2, bottom: y2, width: x2 - x1, height: y2 - y1 }
}

// 画布拖动/缩放/重渲染/页面滚动时，非模态弹窗按打开时的相对偏移跟随所属节点
// （节点实例可能被重渲染重建，按 uid 找回活节点，顺便修掉 menu.node 的失效引用）
function _liveNode(node) {
  if (!node) return null
  if (node.group?.node?.isConnected) return node
  const uid = node.getData?.('uid')
  if (!uid) return null
  let found = null
  const walk = (n) => {
    if (found || !n) return
    if (n.getData('uid') === uid) { found = n; return }
    ;(n.children || []).forEach(walk)
  }
  walk(mind?.renderer?.root)
  return found
}
function syncPopToNode() {
  const open = Object.keys(dlg).find((k) => dlg[k])
  if (!open || !popOff) return
  const live = _liveNode(menu.node)
  const r = _nodeContentRect(live)
  if (!r || (!r.width && !r.height)) return
  menu.node = live
  let x = (popOff.side === 'right' ? r.right : r.left) + popOff.dx
  // 右侧放不下 → 翻到节点左侧贴边（继续跟随，不再被右缘钳制住而相对内容"向左漂"）；左侧出界 → 翻回右侧贴边
  if (popOff.side === 'right' && x + popPos.w > window.innerWidth - 8 && r.left - 12 - popPos.w >= 8) {
    popOff = { ...popOff, side: 'left', dx: -(popPos.w + 12) }
    x = r.left + popOff.dx
  } else if (popOff.side === 'left' && x < 8 && r.right + 12 + popPos.w <= window.innerWidth - 8) {
    popOff = { ...popOff, side: 'right', dx: 12 }
    x = r.right + popOff.dx
  }
  // 两侧都放不下（节点比视口还宽等极端情况）的兜底：钳进视口
  if (x + popPos.w > window.innerWidth - 8 && popOff.side === 'right') x = Math.max(8, window.innerWidth - popPos.w - 8)
  placePop(x, r.top + popOff.dy)
}

// 弹窗打开期间用 rAF 逐帧跟随（画布拖动/缩放/页面滚动/节点显隐按钮变化等任何情况都 16ms 内自愈，
// 不依赖事件时序——事件驱动在部分场景下会漏掉垂直方向的更新）
let popRafId = null
function startPopFollow() {
  if (popRafId) return
  const tick = () => {
    syncPopToNode()
    popRafId = requestAnimationFrame(tick)
  }
  popRafId = requestAnimationFrame(tick)
}
function stopPopFollow() {
  if (popRafId) cancelAnimationFrame(popRafId)
  popRafId = null
}
watch(dlg, () => {
  if (Object.values(dlg).some(Boolean)) startPopFollow()
  else stopPopFollow()
})
const imageForm = reactive({ url: '', width: 100, height: 100 })
// 本地上传的图片 url 是 data URL（不可手动编辑，编辑即损坏）；预览图加载失败提示
const isLocalImage = computed(() => imageForm.url.startsWith('data:'))
const imgPreviewErr = ref(false)

// 宽高最多 2 位小数（拖拽缩放换算会产生一长串小数）
const round2 = (v) => Math.round((Number(v) || 0) * 100) / 100

// 节点图片字段可能是 NodeBase64ImageStorage 的 key（smm_img_key_xxx）——真实 data URL 存在根节点 imgMap 里。
// 回填编辑对话框时必须解析，否则输入框显示 key、预览也加载不出来
function resolveImageUrl(url) {
  if (!url || !url.startsWith('smm_img_key_')) return url
  return mind?.renderer?.renderTree?.data?.imgMap?.[url] || ''
}
const linkForm = reactive({ url: '', title: '' })
const noteText = ref('')
const tagText = ref('')
const imageFileInput = ref(null)

// MagicStick 内联 SVG：右键菜单「AI 生成」图标，与全局 AI 按钮统一
const MAGIC_STICK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="14" height="14"><path fill="currentColor" d="M512 64h64v192h-64zm0 576h64v192h-64zM160 480v-64h192v64zm576 0v-64h192v64zM249.856 199.04l45.248-45.184L430.848 289.6 385.6 334.848 249.856 199.104zM657.152 606.4l45.248-45.248 135.744 135.744-45.248 45.248zM114.048 923.2 68.8 877.952l316.8-316.8 45.248 45.248zM702.4 334.848 657.152 289.6l135.744-135.744 45.248 45.248z"/></svg>'

const MENU = [
  { label: 'AI 生成', ai: true },   // 打开 AI 指令面板（作用于激活/选中节点，由父组件接管）；多选=批量
  { label: '插入子节点', cmd: 'INSERT_CHILD_NODE' },   // 库作用于全部激活节点，多选=每个节点各加一个子节点
  { label: '插入同级节点', cmd: 'INSERT_NODE', noRoot: true, singleOnly: true },
  { label: '插入父节点', cmd: 'INSERT_PARENT_NODE', noRoot: true, singleOnly: true },
  { label: '插入概要', cmd: 'ADD_OUTER_FRAME', noRoot: true },
  { label: '插入归纳', cmd: 'ADD_GENERALIZATION', noRoot: true },   // 作用于激活节点，右键拖框多选后归纳多个兄弟节点
  { label: '插入关联线', cmd: 'ADD_ASSOCIATIVE_LINE', noRoot: true, singleOnly: true },   // 需要单一源节点
  { label: '插入图标', dialog: 'icon', singleOnly: true },   // 装饰类编辑都只作用于 menu.node（右键的那一个）
  { label: '插入图片', dialog: 'image', singleOnly: true },
  { label: '插入超链接', dialog: 'link', singleOnly: true },
  { label: '节点标签', dialog: 'tag', singleOnly: true },
  { label: '节点备注', dialog: 'note', singleOnly: true },
  { label: '上移', cmd: 'UP_NODE', noRoot: true, singleOnly: true },
  { label: '下移', cmd: 'DOWN_NODE', noRoot: true, singleOnly: true },
  { label: '复制', cmd: 'COPY_NODE', noRoot: true },   // 库作用于全部激活节点
  { label: '剪切', cmd: 'CUT_NODE', noRoot: true },
  { label: '粘贴为子节点', cmd: 'PASTE_NODE', singleOnly: true },
  { label: '删除节点', cmd: 'REMOVE_NODE', noRoot: true },
]

function onNodeContextmenu(e, node) {
  // 右键时立即收掉备注/图片浮层：它们定位在光标处，否则菜单从光标展开时浮层会盖住菜单顶部项
  clearTimeout(noteTipTimer)
  clearTimeout(noteTipShowTimer)
  noteTip.show = false
  clearTimeout(imgTipTimer)
  imgTip.show = false
  // 多选状态下右键的是已选中的节点：库的 contextmenu 处理器会把选区重置为该单节点，
  // 这里恢复多选——归纳/概要/删除等才能作用于全部选中节点
  if (preContextSelection.length > 1
      && preContextSelection.some((n) => n.getData('uid') === node.getData('uid'))) {
    for (const n of preContextSelection) mind.renderer.addNodeToActiveList(n, true)
    mind.renderer.emitNodeActiveEvent(node)
  }
  const rect = wrap.value.getBoundingClientRect()
  menu.node = node
  const isRoot = !!node.isRoot   // Node 实例的布尔属性（nodeData.parent 不可靠）
  const canPaste = !!(cutClipboard || mind.renderer?.beingCopyData)
  // 多选（框选后右键选中节点之一，上面已恢复选区）：singleOnly 项直接隐藏；
  // 根节点不适用项、剪贴板为空的粘贴同理——不可操作的菜单项不显示
  const isMulti = (mind.renderer?.activeNodeList || []).length > 1
  menuItems.splice(0, menuItems.length,
    ...MENU.filter((m) =>
      !(m.noRoot && isRoot) && !(m.cmd === 'PASTE_NODE' && !canPaste) && !(m.singleOnly && isMulti)))
  // 防出界：靠近下/右边缘时向上/向左翻转（画布 overflow:hidden 会裁掉溢出部分）
  const menuH = menuItems.length * 33 + 10
  const menuW = 170
  menu.x = Math.min(e.clientX - rect.left, Math.max(0, rect.width - menuW - 4))
  menu.y = e.clientY - rect.top
  menu.cx = e.clientX
  menu.cy = e.clientY
  if (menu.y + menuH > rect.height) menu.y = Math.max(0, rect.height - menuH - 4)
  menu.show = true
}

// 注意：不要在这里主动 SET_NODE_ACTIVE——渲染会重建节点对象，旧引用激活无效反而清空激活列表；
// 右键时库已激活被点节点（node_contextmenu 前的 active()），CUT/PASTE 直接作用于它即可。
function runItem(item) {
  if (item.disabled) return
  menu.show = false
  // AI 生成：通知父组件打开 AI 面板（右键时已激活被点节点，多选也已恢复）；带右键点屏幕坐标做面板锚点
  if (item.ai) {
    emit('ai', { x: menu.cx, y: menu.cy })
    return
  }
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
    anchorPop(menu.cx, menu.cy, item.dialog === 'icon' ? POP_W_ICON : POP_W)   // 弹窗贴右键菜单位置
    // 回填现值：再次打开即编辑；清空提交即移除
    if (item.dialog === 'image') {
      Object.assign(imageForm, {
        url: resolveImageUrl(node?.getData('image') || ''),
        width: round2(node?.getData('imageSize')?.width || 100),
        height: round2(node?.getData('imageSize')?.height || 100),
      })
      imgPreviewErr.value = false
    }
    if (item.dialog === 'link') {
      Object.assign(linkForm, {
        url: node?.getData('hyperlink') || '',
        title: node?.getData('hyperlinkTitle') || '',
      })
    }
    if (item.dialog === 'note') noteText.value = node?.getData('note') || ''
    // 标签回填：tag 是数组（字符串或 {text} 对象）
    if (item.dialog === 'tag') {
      const tags = node?.getData('tag') || []
      tagText.value = tags.map((t) => (typeof t === 'string' ? t : t.text)).filter(Boolean).join('，')
    }
    dlg[item.dialog] = true
    return
  }
  try {
    if (item.cmd === 'ADD_ASSOCIATIVE_LINE') {
      // 创建入口是插件实例方法 createLine（进入连线模式，再点目标节点完成）
      ElMessage.info('连线模式：请点击要连接的目标节点，Esc 取消')
      mind.associativeLine.createLine(menu.node)
    } else if (item.cmd === 'ADD_GENERALIZATION') {
      // 归纳作用于当前激活节点列表（不能传 menu.node——它会被当作概要文本数据）
      addGeneralization()
    } else if (item.cmd === 'ADD_OUTER_FRAME') {
      // 概要（外框）传空数组 → 库回退到激活节点列表，多选时给整组兄弟节点加框
      mind.execCommand('ADD_OUTER_FRAME', [])
    } else {
      mind.execCommand(item.cmd, menu.node)
    }
  } catch { /* 根节点限制等由库兜底 */ }
}

// 归纳（概要卡片）：对激活节点加右侧大括号+概要节点；多选兄弟节点时合并归纳
function addGeneralization() {
  if (!mind) return
  const nodes = (mind.renderer?.activeNodeList || []).filter((n) => !n.isRoot)
  if (!nodes.length) return ElMessage.warning('请先选中要归纳的节点（右键拖框可多选）')
  mind.execCommand('ADD_GENERALIZATION')
}

// ---------- 图片/图标/超链接/备注/标签标记的操作浮层（✎ 编辑 / × 删除 图标按钮） ----------
const opTip = reactive({ show: false, x: 0, y: 0, cx: 0, cy: 0, kind: '', node: null })   // cx/cy 屏幕坐标（编辑弹窗锚点）

function openOpTip(kind, node, x, y) {
  const rect = wrap.value.getBoundingClientRect()
  Object.assign(opTip, { show: true, kind, node, x: x - rect.left + 8, y: y - rect.top - 10, cx: x, cy: y })
}

// 回填并打开对应编辑对话框（与右键菜单的编辑路径一致；图片不走这里，悬停图片右上角有专属操作条）
function opEdit() {
  menu.node = opTip.node
  anchorPop(opTip.cx, opTip.cy, opTip.kind === 'icon' ? POP_W_ICON : POP_W)   // 弹窗贴操作浮层位置
  const node = opTip.node
  if (opTip.kind === 'link') {
    Object.assign(linkForm, {
      url: node?.getData('hyperlink') || '',
      title: node?.getData('hyperlinkTitle') || '',
    })
    dlg.link = true
  } else if (opTip.kind === 'icon') {
    dlg.icon = true
  } else if (opTip.kind === 'note') {
    noteText.value = node?.getData('note') || ''
    dlg.note = true
  } else if (opTip.kind === 'tag') {
    const tags = node?.getData('tag') || []
    tagText.value = tags.map((t) => (typeof t === 'string' ? t : t.text)).filter(Boolean).join('，')
    dlg.tag = true
  }
  opTip.show = false
}

function opDelete() {
  const node = opTip.node
  if (node) {
    if (opTip.kind === 'link') mind.execCommand('SET_NODE_HYPERLINK', node, '', '')
    else if (opTip.kind === 'icon') mind.execCommand('SET_NODE_ICON', node, [])
    else if (opTip.kind === 'note') mind.execCommand('SET_NODE_NOTE', node, '')
    else if (opTip.kind === 'tag') mind.execCommand('SET_NODE_TAG', node, [])
    ElMessage.success('已删除')
  }
  opTip.show = false
}

function opOpen() {
  const url = opTip.node?.getData('hyperlink')
  if (url) window.open(url, '_blank', 'noopener')
  opTip.show = false
}

// 超链接标记点击（库 customHyperlinkJump 钩子，直接给节点实例，默认跳转已被库拦截）：
// 弹操作浮层（打开/编辑/删除），位置取节点组的屏幕矩形
function onHyperlinkJump(url, node) {
  const r = node?.group?.node?.getBoundingClientRect?.()
  openOpTip('link', node, r ? r.right + 4 : 100, r ? r.top : 100)
}

// 点空白处关闭操作浮层
function onWrapClick() {
  if (opTip.show) opTip.show = false
}

function onPreContextmenu() {
  preContextSelection = [...(mind?.renderer?.activeNodeList || [])]
}

function applyImage() {
  // 留空 = 移除图片
  mind.execCommand('SET_NODE_IMAGE', menu.node, {
    url: imageForm.url.trim(), title: '',
    width: round2(imageForm.width), height: round2(imageForm.height), custom: true,
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

// 标签配色：固定精选组按序取色，红色为主色（#debab7 灰粉调朱砂）；
// 第一个标签始终红色，其余依次蓝/绿/橙/紫/青
const TAG_COLORS = ['#fe5c5c', '#409eff', '#67c23a', '#e6a23c', '#9b59b6', '#13c2c2']
// 字符串标签 → {text, style} 对象（v0.10.3+ 支持），已是对象的保留原样
const withTagColor = (t, i) =>
  (typeof t === 'string' ? { text: t, style: { fill: TAG_COLORS[i % TAG_COLORS.length] } } : t)

// 遍历文档树给字符串标签上色（打开旧文档时调用一次）
function _beautifyTags(node) {
  if (!node) return
  const tags = node.data?.tag
  if (Array.isArray(tags)) node.data.tag = tags.map(withTagColor)
  ;(node.children || []).forEach(_beautifyTags)
}

// 浅色标签的文字改深色（库把标签文字写死成白色，#debab7 这类浅底色上白字看不清）：
// 每次渲染后按底色亮度修正（渲染会重建元素，所以需要每次重套）
const DARK_TAG_TEXT = '#5c4a48'
function _isLightColor(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || '')
  if (!m) return false
  const n = parseInt(m[1], 16)
  return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255 > 0.72
}
function _fixTagTextColor(node) {
  if (!node) return
  ;(node._tagData || []).forEach((t) => {
    const rect = t.node?.node?.querySelector('rect')
    const text = t.node?.node?.querySelector('text')
    const fill = rect?.getAttribute('fill')
    if (text && _isLightColor(fill)) text.setAttribute('fill', DARK_TAG_TEXT)
  })
  ;(node.children || []).forEach(_fixTagTextColor)
}

// 标签：逗号分隔的字符串数组（库原生渲染节点下方色块；空数组=移除）
function applyTag() {
  const tags = tagText.value.split(/[,，、\s]+/).map((s) => s.trim()).filter(Boolean).slice(0, 5)
  mind.execCommand('SET_NODE_TAG', menu.node, tags.map(withTagColor))
  dlg.tag = false
}

// 图片本地上传：读文件 → 超长边压缩到 900px → data URL 进节点（NodeBase64ImageStorage 随文档持久化）
function pickLocalImage() {
  imageFileInput.value?.click()
}

function onImageFileChange(e) {
  const file = e.target.files?.[0]
  e.target.value = ''   // 允许重复选同一文件
  if (!file) return
  if (!file.type.startsWith('image/')) return ElMessage.warning('请选择图片文件')
  const reader = new FileReader()
  reader.onload = () => {
    const img = new Image()
    img.onload = () => {
      const MAX = 900
      const scale = Math.min(1, MAX / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale)
      canvas.height = Math.round(img.height * scale)
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
      imageForm.url = canvas.toDataURL('image/png')
      imageForm.width = canvas.width
      imageForm.height = canvas.height
      ElMessage.success('图片已载入，点确定插入')
    }
    img.onerror = () => ElMessage.error('图片读取失败')
    img.src = reader.result
  }
  reader.readAsDataURL(file)
}

// ---------- 备注浮层（悬停备注图标 200ms 后显示，纯预览；编辑/删除走单击图标的操作浮层） ----------
const noteTip = reactive({ show: false, text: '', left: 0, top: 0, node: null })
let noteTipTimer = null
let noteTipShowTimer = null

function showNoteTip(note, left, top, node) {
  // 右键菜单/操作浮层开着时不弹备注浮层：都定位在光标附近，否则会盖住菜单（右键瞬间的 mouseover 可能晚于菜单打开）
  if (menu.show || opTip.show) return
  clearTimeout(noteTipShowTimer)
  clearTimeout(noteTipTimer)
  // 悬停 200ms 才出现，避免鼠标路过图标时浮层一闪而过
  noteTipShowTimer = setTimeout(() => {
    Object.assign(noteTip, { show: true, text: note, left, top, node })
  }, 200)
}
function cancelHideNoteTip() {
  clearTimeout(noteTipTimer)
}
// 库的 hide 在图标 mouseout 时触发：取消未出现的浮层 + 延迟隐藏，鼠标来得及移进浮层阅读
function scheduleHideNoteTip() {
  clearTimeout(noteTipShowTimer)
  clearTimeout(noteTipTimer)
  noteTipTimer = setTimeout(() => { noteTip.show = false }, 250)
}

// ---------- 图片悬停操作（右上角 ✎/×，替代库 NodeImgAdjust 的删除按钮） ----------
// 复用库的 node_img_mousemove/leave 事件；img.rbox() 是视口坐标，直接 fixed 定位
const imgTip = reactive({ show: false, left: 0, top: 0, node: null })
let imgTipTimer = null

function onNodeImgMousemove(node, img) {
  if (props.readonly || menu.show || opTip.show) return
  const r = img.rbox()
  clearTimeout(imgTipTimer)
  Object.assign(imgTip, { show: true, left: r.x2 - 48, top: r.y, node })
}
function cancelHideImgTip() {
  clearTimeout(imgTipTimer)
}
// 与备注浮层同款延迟隐藏：鼠标来得及从图片移到操作条上
function scheduleHideImgTip() {
  clearTimeout(imgTipTimer)
  imgTipTimer = setTimeout(() => { imgTip.show = false }, 250)
}
function editImgTip() {
  const node = imgTip.node
  menu.node = node
  anchorPop(imgTip.left, imgTip.top)   // 弹窗贴图片操作条位置（imgTip 本就是视口坐标）
  Object.assign(imageForm, {
    url: resolveImageUrl(node?.getData('image') || ''),
    width: round2(node?.getData('imageSize')?.width || 100),
    height: round2(node?.getData('imageSize')?.height || 100),
  })
  imgPreviewErr.value = false
  dlg.image = true
  imgTip.show = false
}
function deleteImgTip() {
  if (imgTip.node) {
    mind.execCommand('SET_NODE_IMAGE', imgTip.node, { url: '', title: '', width: 0, height: 0 })
    ElMessage.success('图片已删除')
  }
  imgTip.show = false
}

// ---------- AI 生成：渐进式插入（节点逐个出现，看得到"生长"过程） ----------
// 后端一次返回整棵树（含备注/超链接/颜色/图标装饰），前端按深度优先逐个 execCommand 插入
let aiBusy = false
const _sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// 节点的装饰字段直接进 appointData（note/hyperlink/color/fillColor/icon 都是节点数据键，渲染时自然生效）
function _aiNodeData(c) {
  const d = { text: c.text }
  if (c.note) d.note = c.note
  if (c.hyperlink) { d.hyperlink = c.hyperlink; d.hyperlinkTitle = '' }
  if (c.color) d.color = c.color
  if (c.fillColor) d.fillColor = c.fillColor
  if (c.icon?.length) d.icon = c.icon
  return d
}

async function _progressiveAdd(parent, children) {
  for (const c of children || []) {
    // appointNodes + appointData：openEdit=false（不进编辑态），新节点追加到 parent 末尾
    mind.execCommand('INSERT_CHILD_NODE', false, parent, _aiNodeData(c))
    await _sleep(30)
    const newNode = parent.children[parent.children.length - 1]
    if (!newNode) continue
    await _sleep(150)
    if (c.children?.length) await _progressiveAdd(newNode, c.children)
  }
}

// 按节点文字找节点实例（概要/关联线的 AI 引用解析；同名取第一个）
function _findNodeByText(text) {
  let found = null
  const walk = (node) => {
    if (found || !node) return
    const t = (node.getData('text') || '').replace(/<[^>]+>/g, '').trim()
    if (t === text) { found = node; return }
    for (const c of node.children || []) walk(c)
  }
  walk(mind?.renderer?.root)
  return found
}

// 构建完成后套用概要（归纳卡片）与关联线：引用解析失败的静默跳过
async function _applyAiOverlays({ generalizations = [], associativeLines = [] } = {}) {
  for (const g of generalizations) {
    const members = (g.members || []).map(_findNodeByText).filter(Boolean)
    if (members.length < 2) continue
    mind.renderer.clearActiveNodeList()
    for (const n of members) mind.renderer.addNodeToActiveList(n, true)
    mind.execCommand('ADD_GENERALIZATION', { text: g.text }, false)   // openEdit=false：不弹文本编辑框
    await _sleep(200)
  }
  for (const l of associativeLines) {
    const from = _findNodeByText(l.from)
    const to = _findNodeByText(l.to)
    if (from && to) {
      try { mind.associativeLine.addLine(from, to) } catch { /* 忽略 */ }
      await _sleep(150)
    }
  }
}

// 整图重建：根节点改名 + 清空子节点 + 渐进插入新分支 + 概要/关联线
async function aiRebuild(canonical) {
  if (!mind || aiBusy) return false
  aiBusy = true
  try {
    const root = mind.renderer.root
    mind.execCommand('SET_NODE_TEXT', root, canonical.text || '中心主题')
    for (const c of [...root.children]) mind.execCommand('REMOVE_NODE', c)
    await _sleep(250)
    await _progressiveAdd(root, canonical.children)
    await _applyAiOverlays(canonical)
    mind.renderer.clearActiveNodeList()
    mind.view?.fit?.()
    return true
  } finally { aiBusy = false }
}

// 在选中节点（默认根）下扩写：渐进插入 AI 生成的子分支 + 关联线/概要
async function aiExpand(children, overlays = {}) {
  if (!mind || aiBusy) return false
  const target = mind.renderer.activeNodeList[0] || mind.renderer.root
  aiBusy = true
  try {
    await _progressiveAdd(target, children)
    await _applyAiOverlays(overlays)
    mind.renderer.clearActiveNodeList()
    mind.view?.fit?.()
    return true
  } finally { aiBusy = false }
}

// ---------- 节点字体色/背景色（作用于激活节点，多选时批量） ----------
function setActiveStyle(prop, value) {
  if (!mind) return
  const nodes = mind.renderer?.activeNodeList || []
  if (!nodes.length) return ElMessage.warning('请先点击选中节点（右键拖框可多选）')
  // value 为 null/空串 → undefined：库的回退链是 节点自定义 !== undefined ? 自定义 : 主题，即恢复主题色
  const v = value || undefined
  for (const n of nodes) mind.execCommand('SET_NODE_STYLE', n, prop, v)
}

// 取第一个激活节点的生效颜色（含主题回退），用于取色器初始值同步
function getActiveStyle(prop) {
  const n = mind?.renderer?.activeNodeList?.[0]
  return n?.getStyle?.(prop) || null
}

// 当前激活节点（AI 扩写模式判断用）
function getActiveNode() {
  return mind?.renderer?.activeNodeList?.[0] || null
}

// 全部激活节点（左键拖框/Ctrl 点多选时 >1；AI 面板上下文条用）
function getActiveNodes() {
  return mind?.renderer?.activeNodeList || []
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
    // 自定义备注浮层：悬停预览（替代库默认 tooltip，显隐可控、样式统一）
    customNoteContentShow: { show: showNoteTip, hide: scheduleHideNoteTip },
    // 备注图标固定柔和琥珀色（库默认继承节点文字色，套配色后会变成杂色）
    noteIcon: { style: { color: '#e6a23c' } },
    // 超链接点击不直接跳转：弹操作浮层（打开/编辑/删除）
    customHyperlinkJump: onHyperlinkJump,
    // 左键框选多选节点、右键拖动视图（库原生开关，默认是反的）
    useLeftKeySelectionRightKeyDrag: true,
  })
  const d = props.data
  if (d && d.root) {
    // 原生文档：root 节点树（含图标/图片/链接/备注/概要/关联线）+ 布局 + 主题 + 视图全恢复
    // 旧文档的字符串标签统一套精选配色（否则按文字哈希出浊色）
    _beautifyTags(d.root)
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
    // 图标标记单击 → 操作浮层（编辑/删除）；图片不走这里：悬停图片右上角已有 ✎/× 操作条
    mind.on('node_icon_click', (node, _item, e, _g2) => openOpTip('icon', node, e.clientX, e.clientY))
    // 备注图标单击 → 操作浮层（悬停浮层只预览）；标签单击 → 操作浮层（位置取标签色块右上角）
    mind.on('node_note_click', (node, e) => openOpTip('note', node, e.clientX, e.clientY))
    mind.on('node_tag_click', (node, _item, _idx, tag) => {
      const r = tag.node?.getBoundingClientRect?.()
      openOpTip('tag', node, r ? r.right + 4 : 100, r ? r.top : 100)
    })
    // 图片悬停 → 右上角 ✎/× 操作条（缩放/重渲染后位置失效，直接隐藏待下次悬停）
    mind.on('node_img_mousemove', onNodeImgMousemove)
    mind.on('node_img_mouseleave', scheduleHideImgTip)
    mind.on('scale', scheduleHideImgTip)
    mind.on('node_tree_render_end', scheduleHideImgTip)
    // 非模态弹窗跟随：watch(dlg) 打开期间跑 rAF 逐帧同步（见 startPopFollow），不需要事件驱动
    wrap.value?.addEventListener('click', onWrapClick)   // 点空白关闭浮层
    // 右键前快照激活选区（capture：赶在库的 contextmenu 重置多选之前）
    wrap.value?.addEventListener('contextmenu', onPreContextmenu, true)
    document.addEventListener('click', hideMenu)
    document.addEventListener('click', onDocDownCloseDlg, true)   // 非模态编辑弹窗：点外部关闭（拖动画布不触发）
  }
  // 浅色标签的文字修正为深色（每次渲染后重套，元素会被重建；只读分享页也需要）
  mind.on('node_tree_render_end', () => _fixTagTextColor(mind.renderer.root))
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

// 导出多格式：pdf/xmind/svg 等（Export 插件内置同名方法）
async function exportFile(type, name) {
  if (!mind) return
  try {
    await mind.doExport.export(type, true, name || '思维导图')
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

// ---------- 智能配色：给一级分支成套上色；palette 为 null 时清除（回退主题色） ----------
// palette: [{fill, light, text}]，一级分支节点 fill+白字，子树文字 text 色 + 浅底 light
function applyPalette(palette) {
  if (!mind) return
  const root = mind.renderer.root
  if (!root) return
  root.children.forEach((branch, i) => {
    const c = palette ? palette[i % palette.length] : null
    mind.execCommand('SET_NODE_STYLE', branch, 'fillColor', c?.fill || undefined)
    mind.execCommand('SET_NODE_STYLE', branch, 'color', c ? '#fff' : undefined)
    const walk = (n) => {
      mind.execCommand('SET_NODE_STYLE', n, 'color', c?.text || undefined)
      mind.execCommand('SET_NODE_STYLE', n, 'fillColor', c?.light || undefined)
      ;(n.children || []).forEach(walk)
    }
    branch.children.forEach(walk)
  })
}

// ---------- AI 改写选中分支：清空其子树 + 渐进插入新分支 ----------
async function aiRewrite(children, overlays = {}) {
  if (!mind || aiBusy) return false
  const target = mind.renderer.activeNodeList[0] || mind.renderer.root
  aiBusy = true
  try {
    for (const c of [...target.children]) mind.execCommand('REMOVE_NODE', c)
    await _sleep(250)
    await _progressiveAdd(target, children)
    await _applyAiOverlays(overlays)
    mind.renderer.clearActiveNodeList()
    mind.view?.fit?.()
    return true
  } finally { aiBusy = false }
}

// ---------- AI 多选批量优化：按 uid 定向改写（不清选区不 fit，调用方循环后统一收尾） ----------
async function aiRewriteNode(uid, children) {
  if (!mind || aiBusy) return false
  const target = mind.renderer.findNodeByUid(uid)
  if (!target) return false
  aiBusy = true
  try {
    for (const c of [...target.children]) mind.execCommand('REMOVE_NODE', c)
    await _sleep(250)
    await _progressiveAdd(target, children)
    return true
  } finally { aiBusy = false }
}

// 指定 uid 节点的子树纯文本（AI 逐节点改写/选中分支总结的上下文）
function getSubtreeTexts(uid) {
  const n = mind?.renderer?.findNodeByUid(uid)
  if (!n) return []
  const out = []
  const walk = (node) => {
    const t = (node.getData('text') || '').replace(/<[^>]+>/g, '').trim()
    if (t) out.push(t)
    ;(node.children || []).forEach(walk)
  }
  walk(n)
  return out
}

function fitView() {
  mind?.view?.fit?.()
}

// ---------- 大纲双向编辑：活节点扁平列表 + 按 uid 的结构操作 ----------
function getOutlineLive() {
  // 渲染顺序扁平化（富文本剥标签取纯文字；uid 定位节点实例）
  const out = []
  const walk = (node, depth) => {
    if (!node) return
    out.push({
      uid: node.getData('uid'),
      text: (node.getData('text') || '').replace(/<[^>]+>/g, '').trim(),
      depth,
      isRoot: !!node.isRoot,
    })
    ;(node.children || []).forEach((c) => walk(c, depth + 1))
  }
  walk(mind?.renderer?.root, 0)
  return out.filter((x) => x.uid)
}

function outlineSetText(uid, text) {
  const n = mind?.renderer?.findNodeByUid(uid)
  if (n) mind.execCommand('SET_NODE_TEXT', n, text)
}

// 插入同级（asChild=false）/子级（true）节点，返回新节点 uid 供大纲聚焦
// 注意：库的命令渲染是异步的，插完要等一拍再取 children（与 _progressiveAdd 的 sleep 同理）
async function outlineInsert(uid, asChild) {
  const n = mind?.renderer?.findNodeByUid(uid)
  if (!n) return null
  const parent = asChild ? n : n.parent
  if (!parent) return null
  const before = new Set(parent.children.map((c) => c.getData('uid')))
  mind.execCommand(asChild ? 'INSERT_CHILD_NODE' : 'INSERT_NODE', false, n, { text: '' })
  await _sleep(50)
  const created = parent.children.find((c) => !before.has(c.getData('uid')))
  return created?.getData('uid') || null
}

function outlineRemove(uid) {
  const n = mind?.renderer?.findNodeByUid(uid)
  if (n && !n.isRoot) mind.execCommand('REMOVE_NODE', n)
}

defineExpose({ getDoc, getCanonical, setTheme, setLayout, setLineStyle, exportPng, exportFile, undo, redo, canUndo, canRedo, setActiveStyle, getActiveStyle, getActiveNode, getActiveNodes, addGeneralization, aiRebuild, aiExpand, aiRewrite, aiRewriteNode, getSubtreeTexts, fitView, applyPalette, getOutlineLive, outlineSetText, outlineInsert, outlineRemove })

onBeforeUnmount(() => {
  document.removeEventListener('click', hideMenu)
  document.removeEventListener('click', onDocDownCloseDlg, true)
  stopPopFollow()
  wrap.value?.removeEventListener('click', onWrapClick)
  wrap.value?.removeEventListener('contextmenu', onPreContextmenu, true)
  clearTimeout(noteTipTimer)
  clearTimeout(noteTipShowTimer)
  try { mind?.destroy?.() } catch { /* 忽略 */ }
  mind = null
})
</script>

<style scoped>
.mm-wrap { position: relative; width: 100%; height: 100%; }
.mm-canvas { width: 100%; height: 100%; }
/* 画布 SVG 文字（节点/标签等）不可选中，避免拖选时出现蓝色高亮；双击编辑态的输入框不受影响（在 foreignObject 里） */
.mm-canvas :deep(svg) { user-select: none; -webkit-user-select: none; }

/* RichText 插件用 foreignObject 渲染节点文字，<p> 默认 margin 会把文字挤出可视高度 */
.mm-canvas :deep(.smm-richtext-node-wrap p) { margin: 0; }

.mm-menu {
  position: absolute; z-index: 3000; min-width: 140px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, .12); padding: 4px;
  /* 菜单文字不可选中：右键按住移动/点菜单项时拖拽会把菜单文字选中成蓝色高亮 */
  user-select: none; -webkit-user-select: none;
}
.mm-menu-item {
  padding: 7px 14px; font-size: 13px; color: #303133;
  border-radius: 4px; cursor: pointer; white-space: nowrap;
}
.mm-menu-item:hover { background: #ecf5ff; color: #409eff; }
.mm-menu-item.disabled { color: #c0c4cc; cursor: not-allowed; }
.mm-menu-item.disabled:hover { background: none; color: #c0c4cc; }
/* 右键菜单「AI 生成」：紫色 + 魔法棒图标，与全局 AI 按钮统一；底部分隔线隔开节点操作 */
.mm-menu-item-ai {
  display: flex; align-items: center; gap: 6px;
  color: var(--grt-ai); font-weight: 600;
  border-bottom: 1px solid #ebeef5; border-radius: 4px 4px 0 0; margin-bottom: 3px; padding-bottom: 8px;
}
.mm-menu-item-ai:hover { color: var(--grt-ai-hover); }
.mm-menu-icon { display: inline-flex; flex-shrink: 0; }

.mm-dlg-hint { font-size: 12px; color: #909399; margin-top: 8px; line-height: 1.5; }

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

/* 备注浮层（fixed 定位，与库默认 tooltip 同风格；右上角操作按钮）
   user-select:none：右键点在备注图标上时浏览器会把光标/选区放进浮层文字（出现蓝色高亮），浮层只是预览不需选中 */
.mm-note-tip {
  position: fixed; z-index: 3000; max-width: 320px; display: flex; gap: 8px; align-items: flex-start;
  padding: 10px 12px; background: #fff; border-radius: 6px; border: 1px solid #e4e7ed;
  box-shadow: 0 4px 16px rgba(0, 0, 0, .14); font-size: 13px; color: #303133;
  user-select: none; -webkit-user-select: none;
}
.mm-note-tip-text { white-space: pre-wrap; word-break: break-word; line-height: 1.6; }

/* 标记单击的操作浮层：✎/×/↗ 图标按钮（22px 圆角小按钮，悬停高亮） */
.mm-op-tip {
  position: absolute; z-index: 3000; display: flex; gap: 2px; padding: 3px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 6px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, .12);
  user-select: none; -webkit-user-select: none;
}
.mm-op-tip button {
  width: 22px; height: 22px; border: none; border-radius: 4px; background: transparent;
  color: #909399; font-size: 14px; line-height: 1; cursor: pointer; padding: 0;
}
.mm-op-tip button:hover { background: #ecf5ff; color: #409eff; }
.mm-op-tip button.danger:hover { background: #fef0f0; color: #f56c6c; }

/* 图片对话框预览 */
.mm-img-preview-wrap { display: flex; align-items: flex-end; gap: 10px; }
.mm-img-preview {
  max-width: 220px; max-height: 140px; border-radius: 4px; border: 1px solid #e4e7ed;
  object-fit: contain; background: #f5f7fa;
}
.mm-img-preview-side { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.mm-img-preview-err { font-size: 12px; color: #f56c6c; }

/* 图片悬停操作条（fixed 定位；按钮样式与备注浮层一致） */
.mm-img-tip {
  position: fixed; z-index: 3000; display: flex; gap: 2px; padding: 2px;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 6px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, .12);
  user-select: none; -webkit-user-select: none;
}
.mm-img-tip button {
  width: 22px; height: 22px; border: none; border-radius: 4px; background: transparent;
  color: #909399; font-size: 14px; line-height: 1; cursor: pointer;
}
.mm-img-tip button:hover { background: #ecf5ff; color: #409eff; }
</style>

<!-- 库 NodeImgAdjust 插件挂在 body 上的元素，scoped 样式够不到，单独非 scoped 块 -->
<style>
/* 隐藏图片右上角库默认的删除按钮（改用组件内的 ✎/× 悬停操作条） */
.node-img-handle .node-image-remove { display: none !important; }
</style>
