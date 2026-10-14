<template>
  <div class="editor-page">
    <div class="editor-toolbar">
      <el-button :icon="Back" @click="back">返回</el-button>
      <el-input v-model="title" class="title-input" maxlength="200" placeholder="导图标题" @input="scheduleSave" />
      <!-- AI：浮动指令面板（统一 AiPromptPanel），贴按钮弹出；改写/总结入口在面板内 -->
      <el-button ref="aiBtnRef" class="ai-btn" :icon="MagicStick" :loading="ai.loading" @click="openAi()">AI 生成</el-button>

      <!-- 前进/后退（库内置历史栈） -->
      <!-- 可用状态视觉区分：可用=蓝色实心，不可用=灰化 -->
      <el-button-group>
        <el-button title="后退（Ctrl+Z）" :disabled="!eng?.canUndo"
          :type="eng?.canUndo ? 'primary' : 'info'" :plain="!eng?.canUndo" @click="eng?.undo()">
          <el-icon><RefreshLeft /></el-icon>
        </el-button>
        <el-button title="前进（Ctrl+Y）" :disabled="!eng?.canRedo"
          :type="eng?.canRedo ? 'primary' : 'info'" :plain="!eng?.canRedo" @click="eng?.redo()">
          <el-icon><RefreshRight /></el-icon>
        </el-button>
      </el-button-group>

      <!-- 布局：图标下拉（小示意图 + 名称） -->
      <el-dropdown trigger="click" @command="(v) => { layout = v; eng?.setLayout(v) }">
        <el-button title="布局">
          <span class="dd-icon" v-html="LAYOUT_ICONS[layout]" />
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="l in LAYOUTS" :key="l.value" :command="l.value">
              <span class="dd-item">
                <span class="dd-icon dd-icon-lg" v-html="LAYOUT_ICONS[l.value]" />
                <span>{{ l.label }}</span>
                <el-icon v-if="layout === l.value" class="dd-check"><Check /></el-icon>
              </span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 分支样式：图标下拉 -->
      <el-dropdown trigger="click" @command="(v) => { lineStyle = v; eng?.setLineStyle(v) }">
        <el-button title="分支样式">
          <span class="dd-icon" v-html="LINE_ICONS[lineStyle]" />
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="l in LINE_STYLES" :key="l.value" :command="l.value">
              <span class="dd-item">
                <span class="dd-icon dd-icon-lg" v-html="LINE_ICONS[l.value]" />
                <span>{{ l.label }}</span>
                <el-icon v-if="lineStyle === l.value" class="dd-check"><Check /></el-icon>
              </span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 主题：与配色同款下拉按钮（按钮显示当前主题色块+名称；列表分组 + 勾选当前项） -->
      <el-dropdown trigger="click" popper-class="mm-theme-popper" @command="(v) => { theme = v; eng?.setTheme(v) }">
        <el-button title="主题皮肤">
          <span class="palette-item">
            <span class="palette-dot" :style="{ background: themeSwatch(theme) }" />
            {{ themeLabel }}
          </span>
          <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <template v-for="g in THEME_GROUPS" :key="g.label">
              <div class="theme-group-label">{{ g.label }}</div>
              <el-dropdown-item v-for="t in g.items" :key="t.value" :command="t.value">
                <span class="palette-item">
                  <span class="palette-dot" :style="{ background: themeSwatch(t.value) }" />
                  {{ t.label }}
                  <el-icon v-if="theme === t.value" class="dd-check"><Check /></el-icon>
                </span>
              </el-dropdown-item>
            </template>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 智能配色：成套预设一键应用（作用于各一级分支）；按钮上显示当前选中的配色 -->
      <el-dropdown trigger="click" @command="applyPaletteCmd">
        <el-button title="智能配色">
          <span v-if="activePalette" class="palette-item">
            <span v-for="c in activePaletteColors" :key="c" class="palette-dot" :style="{ background: c }" />
            {{ activePalette }}
          </span>
          <span v-else>配色</span>
          <el-icon><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="p in PALETTES" :key="p.name" :command="p.name">
              <span class="palette-item">
                <span v-for="c in p.colors.slice(0, 4)" :key="c.fill" class="palette-dot" :style="{ background: c.fill }" />
                {{ p.name }}
                <el-icon v-if="activePalette === p.name" class="dd-check"><Check /></el-icon>
              </span>
            </el-dropdown-item>
            <el-dropdown-item divided command="__clear">清除配色（跟随主题）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 字体色/背景色：色块网格面板（点一下直接应用），作用于选中节点（右键拖框多选可批量）。
           第一格 ∅ = 清除自定义色，跟随主题 -->
      <el-popover
        v-for="cp in COLOR_CONTROLS" :key="cp.prop" v-model:visible="cpVisible[cp.prop]"
        trigger="click" placement="bottom" :width="252" @show="syncColors"
      >
        <template #reference>
          <span class="cp-group">
            <span class="cp-label">{{ cp.label }}</span>
            <span class="cp-trigger" :title="cp.title">
              <span class="cp-swatch" :class="{ empty: !colors[cp.prop] }"
                :style="colors[cp.prop] ? { background: colors[cp.prop] } : {}" />
              <el-icon class="cp-caret"><ArrowDown /></el-icon>
            </span>
          </span>
        </template>
        <div class="cp-grid">
          <span class="cp-cell cp-cell-theme" title="跟随主题（清除自定义色）" @click="applyStyle(cp.prop, null)">∅</span>
          <span
            v-for="c in cp.presets" :key="c" class="cp-cell"
            :class="{ active: colors[cp.prop]?.toLowerCase() === c.toLowerCase() }"
            :style="{ background: c }" :title="c" @click="applyStyle(cp.prop, c)"
          />
        </div>
      </el-popover>

      <el-button @click="openOutline">大纲</el-button>

      <!-- 导出：PNG / PDF / XMind -->
      <el-dropdown trigger="click" @command="(t) => eng?.exportFile(t, title)">
        <el-button>导出<el-icon><ArrowDown /></el-icon></el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="png">PNG 图片</el-dropdown-item>
            <el-dropdown-item command="pdf">PDF 文档</el-dropdown-item>
            <el-dropdown-item command="xmind">XMind 文件</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="shortcut-hint">双击编辑 · Tab 子节点 · Enter 同级 · 左键拖框多选 · 右键拖动视图 · 右键菜单更多</span>
      
      <span class="save-state" :class="{ err: saveState === '保存失败' }">{{ saveState }}</span>
    </div>

    <!-- AI 生成：选中节点时顶部显示上下文条 + 建议操作 chips（记事本同款）；渐进渲染 -->
    <AiPromptPanel
      v-model="ai.visible" title="✨ AI 生成思维导图" :anchor="aiAnchor"
      :context-note="aiContextNote"
      :chips="mmAiChips"
      :placeholder="ai.canExpand
        ? '对选中节点做什么？如：扩写 / 优化 / 改写（直接回车 = 扩写）；也可重建整图'
        : ai.activeTexts.length
          ? '对选中的几个分支做什么？如：优化表达 / 补充细节（也可总结选中分支）'
          : '描述导图主题，如：帮我整理一份 Vue3 学习路线 / 制定一次北京三日游计划；也可附图，从图片中提取结构'"
      :rows="2"
      :loading="ai.loading"
      :result="ai.result" :result-title="ai.resultTitle"
      @submit="onAiSubmit"
    />

    <!-- 大纲（双向编辑）：改文字同步到画布；Enter 加同级、Tab 加子级、空行再按退格删除 -->
    <el-drawer v-model="outlineVisible" title="大纲（可直接编辑）" size="400px">
      <div class="outline-tree">
        <div
          v-for="item in outlineItems" :key="item.uid"
          class="outline-row" :style="{ paddingLeft: item.depth * 18 + 2 + 'px' }"
        >
          <el-input
            :ref="(el) => setOutlineInputRef(item.uid, el)"
            v-model="item.text" size="small" class="outline-input" placeholder="（空）"
            @change="(v) => outlineChange(item, v)"
            @keydown="(e) => outlineKeydown(e, item)"
          />
          <el-icon v-if="!item.isRoot" class="outline-del" title="删除节点" @click="outlineDel(item)"><Delete /></el-icon>
        </div>
        <el-empty v-if="!outlineItems.length" description="暂无内容" :image-size="60" />
      </div>
      <div class="outline-hint">编辑会同步到画布 · Enter 同级 · Tab 子级 · 清空后按退格删除</div>
    </el-drawer>

    <div class="editor-body" v-loading="loading">
      <MindmapSimple v-if="ready" ref="eng" :data="currentData" @change="onEngChange" @ai="openAi" />
    </div>
  </div>
</template>

<script setup>
// 思维导图编辑器：引擎定型 simple-mind-map；数据存引擎无关中间格式（{text, children[]}）
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, Back, Check, Delete, MagicStick, RefreshLeft, RefreshRight } from '@element-plus/icons-vue'
import { getMindmap, mindmapAiAssist, updateMindmap } from '../api'
import MindmapSimple from '../components/MindmapSimple.vue'
import AiPromptPanel from '../components/AiPromptPanel.vue'

// simple-mind-map 主题（simple-mind-map-plugin-themes 注册；中文标签为本项目翻译）
// 分组展示 + 预览色块（swatch 为各主题主色，近似即可）
const THEME_GROUPS = [
  { label: '简约', items: [
    { value: 'default', label: '默认' }, { value: 'classic', label: '经典' },
    { value: 'classicGreen', label: '经典绿' }, { value: 'mint', label: '薄荷' },
    { value: 'oreo', label: '奥利奥' }, { value: 'morandi', label: '莫兰迪' },
  ] },
  { label: '彩色', items: [
    { value: 'blueSky', label: '蓝天' }, { value: 'brainImpairedPink', label: '粉红' },
    { value: 'earthYellow', label: '土黄' }, { value: 'freshGreen', label: '清新绿' },
    { value: 'freshRed', label: '清新红' }, { value: 'romanticPurple', label: '浪漫紫' },
    { value: 'pinkGrape', label: '粉葡萄' }, { value: 'gold', label: '金色' },
    { value: 'vitalityOrange', label: '活力橙' }, { value: 'greenLeaf', label: '绿叶' },
    { value: 'minions', label: '小黄人' }, { value: 'avocado', label: '牛油果' },
    { value: 'autumn', label: '秋天' }, { value: 'shallowSea', label: '浅海' },
    { value: 'lemonBubbles', label: '柠檬气泡' }, { value: 'rose', label: '玫瑰' },
    { value: 'seaBlueLine', label: '海蓝线' }, { value: 'cactus', label: '仙人掌' },
    { value: 'coffee', label: '咖啡' },
  ] },
  { label: '深色', items: [
    { value: 'dark', label: '暗夜' }, { value: 'neonLamp', label: '霓虹灯' },
    { value: 'blackGold', label: '黑金' },
  ] },
]
// 各主题主色（预览色块用，近似值）
const THEME_SWATCH = {
  default: '#5c8df6', classic: '#c8a97e', classicGreen: '#9ccc65', blueSky: '#03a9f4',
  brainImpairedPink: '#f48fb1', earthYellow: '#c9a063', freshGreen: '#80c683', freshRed: '#ef6c6c',
  romanticPurple: '#ab47bc', pinkGrape: '#d16ba5', mint: '#4db6ac', gold: '#d4af37',
  vitalityOrange: '#fb8c00', greenLeaf: '#66bb6a', minions: '#fdd835', coffee: '#8d6e63',
  avocado: '#7cb342', autumn: '#e65100', oreo: '#424242', shallowSea: '#4fc3f7',
  lemonBubbles: '#dce775', rose: '#ec407a', seaBlueLine: '#1e88e5', morandi: '#90a4ae',
  cactus: '#388e3c', dark: '#263238', neonLamp: '#7c4dff', blackGold: '#bfa45f',
}
const themeSwatch = (v) => THEME_SWATCH[v] || '#909399'
// 当前主题的中文名（皮肤按钮上显示）
const themeLabel = computed(() =>
  THEME_GROUPS.flatMap((g) => g.items).find((t) => t.value === theme.value)?.label || '主题'
)

const LAYOUTS = [
  { value: 'logicalStructure', label: '逻辑结构图' },
  { value: 'logicalStructureLeft', label: '向左逻辑结构图' },
  { value: 'mindMap', label: '思维导图' },
  { value: 'organizationStructure', label: '组织结构图' },
  { value: 'catalogOrganization', label: '目录组织图' },
  { value: 'timeline', label: '时间轴' },
  { value: 'timeline2', label: '时间轴（下）' },
  { value: 'verticalTimeline', label: '竖向时间轴' },
  { value: 'fishbone', label: '鱼骨图' },
  { value: 'fishbone2', label: '鱼骨图（下）' },
  { value: 'rightFishbone', label: '向右鱼骨图' },
]

const LINE_STYLES = [
  { value: 'curve', label: '曲线' },
  { value: 'straight', label: '直线' },
  { value: 'direct', label: '直连' },
]

// 布局/分支样式的小示意图（stroke 跟随文字颜色）
const _svg = (inner, vb = '0 0 48 28') =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb}" fill="none" stroke="currentColor" stroke-width="1.6">${inner}</svg>`
const _r = (x, y, w = 9, h = 6) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="2" fill="currentColor" stroke="none"/>`
const LAYOUT_ICONS = {
  logicalStructure: _svg(`${_r(2, 11)}<path d="M11 14h7m0-7v14m0-7h8m-8 7h8" />${_r(26, 4)}${_r(26, 18)}`),
  logicalStructureLeft: _svg(`${_r(37, 11)}<path d="M37 14h-7m0-7v14m0-7h-8m8 7h-8" />${_r(11, 4)}${_r(11, 18)}`),
  mindMap: _svg(`${_r(19, 11)}<path d="M19 14h-6m0-6v12m0-6h-7m7 6h-7M29 14h6m0-6v12m0-6h7m-7 6h7" />${_r(3, 5)}${_r(3, 17)}${_r(38, 5)}${_r(38, 17)}`),
  organizationStructure: _svg(`${_r(19, 2)}<path d="M24 8v5m0 0H10m14 0h14M10 13v4m14-4v4" />${_r(5, 17)}${_r(24, 17)}`),
  catalogOrganization: _svg(`${_r(4, 2)}<path d="M9 8v4h8m-8 0v10h8" />${_r(21, 9)}${_r(21, 19)}`),
  timeline: _svg('<path d="M4 18h40" />' + _r(8, 8) + _r(22, 8) + _r(36, 8) + '<path d="M12 14v4m15-4v4m14-4v4" />'),
  timeline2: _svg('<path d="M4 10h40" />' + _r(8, 16) + _r(22, 16) + _r(36, 16) + '<path d="M12 10v6m15-6v6m14-6v6" />'),
  verticalTimeline: _svg('<path d="M12 2v24" />' + _r(18, 3) + _r(18, 12) + _r(18, 21) + '<path d="M12 6h6m-6 9h6m-6 9h6" />'),
  fishbone: _svg('<path d="M4 14h38m-6-8 6 8-6 8M16 4l8 10M16 24l8-10M28 4l8 10M28 24l8-10" />'),
  fishbone2: _svg('<path d="M4 14h38m-6-8 6 8-6 8M16 4l8 10M16 24l8-10M28 4l8 10M28 24l8-10" />'),
  rightFishbone: _svg('<path d="M6 14h38m-38 0 6-8m-6 8 6 8M20 4l8 10M20 24l8-10M32 4l8 10M32 24l8-10" />'),
}
const LINE_ICONS = {
  curve: _svg('<path d="M4 22 C 12 22 16 6 24 6" />', '0 0 28 28'),
  straight: _svg('<path d="M4 22 V14 H14 V6 H24" />', '0 0 28 28'),
  direct: _svg('<path d="M4 22 L24 6" />', '0 0 28 28'),
}

// 大纲：中间格式树 → 扁平列表（项目用 vue runtime-only，SFC 里不能用 template 字符串递归组件）
function flattenOutline(node, depth = 0, out = []) {
  if (!node) return out
  out.push({ text: node.text, depth })
  ;(node.children || []).forEach((c) => flattenOutline(c, depth + 1, out))
  return out
}

const route = useRoute()
const router = useRouter()
const id = route.params.id

const title = ref('')
const currentData = ref(null)
const ready = ref(false)
const loading = ref(false)
const eng = ref(null)
const theme = ref(localStorage.getItem('grt_mm_simple_theme') || 'default')
const layout = ref(localStorage.getItem('grt_mm_simple_layout') || 'logicalStructure')
const lineStyle = ref(localStorage.getItem('grt_mm_simple_linestyle') || 'straight')
const outlineVisible = ref(false)
const outlineItems = ref([])

// 字体色/背景色：色块网格面板。∅ = 清除自定义色（回退主题色）
// 字体色用常规/深色系（20 色），背景色用浅色系（20 色，深色背景会吞掉文字）
const FONT_PRESETS = [
  '#303133', '#606266', '#909399', '#c0c4cc', '#000000',
  '#f56c6c', '#e6a23c', '#b88230', '#67c23a', '#2f9e6e',
  '#409eff', '#36a3f7', '#00bcd4', '#7c5cff', '#a259e6',
  '#eb2f96', '#f78fb3', '#8d6e63', '#5c8df6', '#ffffff',
]
const BG_PRESETS = [
  '#ffffff', '#f5f5f5', '#f4f0ff', '#ecf5ff', '#e8f7f7',
  '#fef0f0', '#fdeef5', '#fdf6ec', '#fffce8', '#f0f9eb',
  '#ffd591', '#ffc069', '#a0cfff', '#b7eb8f', '#ffadd2',
  '#f8c3cd', '#d3adf7', '#87e8de', '#ffe58f', '#d9d9d9',
]
const COLOR_CONTROLS = [
  { prop: 'color', label: '字体', title: '字体颜色（先选中节点，可多选）', presets: FONT_PRESETS },
  { prop: 'fillColor', label: '背景', title: '节点背景颜色（先选中节点，可多选）', presets: BG_PRESETS },
]
const colors = reactive({ color: null, fillColor: null })
const cpVisible = reactive({ color: false, fillColor: false })
function syncColors() {
  colors.color = eng.value?.getActiveStyle?.('color') || null
  colors.fillColor = eng.value?.getActiveStyle?.('fillColor') || null
}
function applyStyle(prop, v) {
  colors[prop] = v
  eng.value?.setActiveStyle?.(prop, v)   // null = 清除，回退主题色
  cpVisible[prop] = false                // 点色块即应用并收起面板
}

// ---------- AI（生成/扩写/改写分支、总结全文、改进建议；文本类结果在面板内展示） ----------
const ai = reactive({
  visible: false, loading: false, instruction: '', mode: 'rebuild',
  canExpand: false, nodeText: '', activeTexts: [], activeNodes: [], images: [],
  result: '', resultTitle: '导图总结',
  anchorPoint: null,   // 右键菜单唤起时的面板锚点（{x, y} 屏幕坐标）；null = 贴工具栏按钮
})
const aiBtnRef = ref(null)
// 面板锚点：右键唤起 → 右键点的虚拟矩形；按钮唤起 → 按钮元素
const aiAnchor = computed(() =>
  ai.anchorPoint
    ? { left: ai.anchorPoint.x, top: ai.anchorPoint.y, bottom: ai.anchorPoint.y }
    : aiBtnRef.value
)

// 上下文条：单选=基于该节点；多选=列出全部选中（扩写/改写只对单选开放）
const aiContextNote = computed(() => {
  const n = ai.activeTexts.length
  if (!n) return ''
  if (n === 1) return `基于选中节点：「${ai.nodeText}」`
  const list = ai.activeTexts.slice(0, 3).map((t) => `「${t.slice(0, 12)}」`).join(' ')
  return `已选中 ${n} 个节点：${list}${n > 3 ? ' …' : ''}`
})

// 建议操作 chips：全部只填入输入框，由用户回车/点生成触发。
// 选中单个节点 → 针对选中内容的操作（扩写/优化/改写）；未选中 → XMind 同款整图示例
const mmAiChips = computed(() => {
  const chips = []
  if (ai.canExpand) {
    chips.push(
      { label: `扩写「${ai.nodeText}」`, value: `扩写「${ai.nodeText}」这个分支`, mode: 'expand' },
      { label: `优化「${ai.nodeText}」的表达`, value: '优化这个分支的表达与结构：节点文字更精炼、层次更清晰，不增减信息量', mode: 'rewrite' },
      { label: `改写「${ai.nodeText}」子树`, mode: 'rewrite' },
    )
  } else if (!ai.activeTexts.length) {
    chips.push(
      { label: '调研一个主题并总结要点', value: '调研 [过去一年的金价走势] 及其背后的原因', mode: 'rebuild' },
      { label: '把一个项目拆解成执行计划', value: '在 [2 个月] 内推出一款 [任务管理] App 的首个版本——涵盖用户调研、原型设计、开发、测试与上线，做成带工期和依赖的执行计划', mode: 'rebuild' },
      { label: '探索某个领域的最新趋势', value: '梳理 [AI] 领域的最新趋势和方向', mode: 'rebuild' },
      { label: '分析我的思维导图，给出改进建议', value: '从[结构、完整性、表达]几方面为这张思维导图提出改进建议，编号列出。暂不修改导图，请我确认要采纳哪几条。', mode: 'advise' },
    )
  } else {
    // 多选：逐节点批量优化（rewrite 循环）/ 只总结选中的分支
    const n = ai.activeTexts.length
    chips.push(
      { label: `优化这 ${n} 个节点的表达`, value: '优化这些分支的表达与结构：节点文字更精炼、层次更清晰，不增减信息量', mode: 'multi-rewrite' },
      { label: `总结这 ${n} 个分支`, value: '总结这几个分支的核心内容', mode: 'multi-summarize' },
    )
  }
  chips.push({ label: '总结当前导图全文', value: '总结当前导图全文', mode: 'summarize' })
  return chips
})

// 面板提交：回填状态后按模式路由；文本类结果（总结/建议）留在面板内展示，生成类才关面板
async function onAiSubmit({ instruction, images, mode }) {
  ai.instruction = instruction
  ai.images = images
  if (mode) ai.mode = mode
  ai.result = ''
  if (ai.mode === 'advise') return aiAdvise()
  if (ai.mode === 'summarize') return aiSummarize()
  if (ai.mode === 'multi-summarize') {
    // 只取选中分支的子树作为上下文
    return aiSummarize(ai.activeNodes.flatMap((n) => eng.value?.getSubtreeTexts?.(n.uid) || []), '分支总结')
  }
  if (ai.mode === 'multi-rewrite') return aiMultiRewrite()
  await aiGenerate()
}

// 多选批量优化：对每个选中节点分别调用 rewrite，逐节点替换其子树（不改动未选中部分）
async function aiMultiRewrite() {
  if (!ai.instruction.trim()) {
    ElMessage.warning('先描述一下要怎么做')
    return
  }
  const nodes = [...ai.activeNodes]
  if (nodes.length < 2) return aiGenerate()   // 兜底：单选走普通流程
  ai.loading = true
  try {
    let done = 0
    for (const nd of nodes) {
      const context = eng.value?.getSubtreeTexts?.(nd.uid) || []
      const res = await mindmapAiAssist({
        instruction: ai.instruction, mode: 'rewrite', node_text: nd.text.slice(0, 100), context: context.slice(-30),
      })
      if (await eng.value?.aiRewriteNode?.(nd.uid, res.children)) done++
    }
    eng.value?.fitView?.()
    ai.visible = false
    ElMessage.success(`已优化 ${done}/${nodes.length} 个节点`)
  } catch (e) {
    ElMessage.error(e.message || e)
  } finally {
    ai.loading = false
  }
}

// 改进建议：分析整图但不改图，结果在面板内展示（用户确认后再手动采纳）
async function aiAdvise() {
  const context = eng.value ? flattenOutline(eng.value.getCanonical()).map((i) => i.text).filter(Boolean) : []
  if (context.length <= 1) return ElMessage.warning('导图还没有内容')
  ai.loading = true
  try {
    const res = await mindmapAiAssist({ instruction: ai.instruction, mode: 'summarize', context })
    ai.resultTitle = '改进建议'
    ai.result = res.summary || ''
  } catch (e) {
    ElMessage.error(e.message || e)
  } finally {
    ai.loading = false
  }
}

// 总结：结果在面板内展示，可继续追问/复制
async function aiSummarize(contextOverride = null, title = '导图总结') {
  const context = contextOverride
    || (eng.value ? flattenOutline(eng.value.getCanonical()).map((i) => i.text).filter(Boolean) : [])
  if (context.length <= 1) return ElMessage.warning('导图还没有内容')
  ai.loading = true
  try {
    const res = await mindmapAiAssist({ instruction: '', mode: 'summarize', context })
    ai.resultTitle = title
    ai.result = res.summary || ''
  } catch (e) {
    ElMessage.error(e.message || e)
  } finally {
    ai.loading = false
  }
}

// ---------- 智能配色（成套预设；分支循环取色） ----------
const PALETTES = [
  { name: '活力', colors: [
    { fill: '#409eff', light: '#ecf5ff', text: '#3375b9' },
    { fill: '#67c23a', light: '#f0f9eb', text: '#529b2e' },
    { fill: '#e6a23c', light: '#fdf6ec', text: '#b88230' },
    { fill: '#f56c6c', light: '#fef0f0', text: '#c45656' },
    { fill: '#9b59b6', light: '#f4f0ff', text: '#7d3c98' },
  ] },
  { name: '莫兰迪', colors: [
    { fill: '#90a4ae', light: '#eceff1', text: '#607d8b' },
    { fill: '#a1887f', light: '#efebe9', text: '#795548' },
    { fill: '#81c784', light: '#e8f5e9', text: '#558b2f' },
    { fill: '#7986cb', light: '#e8eaf6', text: '#5c6bc0' },
    { fill: '#e08283', light: '#fbe9e7', text: '#c05b4d' },
  ] },
  { name: '马卡龙', colors: [
    { fill: '#f78fb3', light: '#fdeef5', text: '#d6306f' },
    { fill: '#63cdda', light: '#e3f7fa', text: '#3b9aa8' },
    { fill: '#f5cd79', light: '#fef6e0', text: '#b8860b' },
    { fill: '#7dbed6', light: '#e8f4f8', text: '#4a90a4' },
    { fill: '#cf6a87', light: '#f9e8ec', text: '#a54863' },
  ] },
  { name: '海洋', colors: [
    { fill: '#1e88e5', light: '#e3f2fd', text: '#1565c0' },
    { fill: '#00acc1', light: '#e0f7fa', text: '#00838f' },
    { fill: '#26a69a', light: '#e0f2f1', text: '#00796b' },
    { fill: '#5c6bc0', light: '#e8eaf6', text: '#3949ab' },
    { fill: '#4fc3f7', light: '#e1f5fe', text: '#0288d1' },
  ] },
  { name: '森林', colors: [
    { fill: '#43a047', light: '#e8f5e9', text: '#2e7d32' },
    { fill: '#7cb342', light: '#f1f8e9', text: '#558b2f' },
    { fill: '#00897b', light: '#e0f2f1', text: '#00695c' },
    { fill: '#c0ca33', light: '#f9fbe7', text: '#9e9d24' },
    { fill: '#6d4c41', light: '#efebe9', text: '#4e342e' },
  ] },
  { name: '日落', colors: [
    { fill: '#fb8c00', light: '#fff3e0', text: '#e65100' },
    { fill: '#f4511e', light: '#fbe9e7', text: '#d84315' },
    { fill: '#ec407a', light: '#fce4ec', text: '#c2185b' },
    { fill: '#ab47bc', light: '#f3e5f5', text: '#7b1fa2' },
    { fill: '#ffb300', light: '#fff8e1', text: '#ff8f00' },
  ] },
  { name: '商务', colors: [
    { fill: '#37474f', light: '#eceff1', text: '#263238' },
    { fill: '#1976d2', light: '#e3f2fd', text: '#0d47a1' },
    { fill: '#00796b', light: '#e0f2f1', text: '#004d40' },
    { fill: '#5d4037', light: '#efebe9', text: '#3e2723' },
    { fill: '#455a64', light: '#eceff1', text: '#263238' },
  ] },
  { name: '糖果', colors: [
    { fill: '#ff5c8a', light: '#ffebf1', text: '#d81b60' },
    { fill: '#ffa726', light: '#fff3e0', text: '#ef6c00' },
    { fill: '#66bb6a', light: '#e8f5e9', text: '#388e3c' },
    { fill: '#42a5f5', light: '#e3f2fd', text: '#1565c0' },
    { fill: '#ba68c8', light: '#f3e5f5', text: '#8e24aa' },
  ] },
  { name: '极光', colors: [
    { fill: '#7c4dff', light: '#ede7f6', text: '#651fff' },
    { fill: '#00bcd4', light: '#e0f7fa', text: '#0097a7' },
    { fill: '#69f0ae', light: '#e8f5e9', text: '#00a152' },
    { fill: '#ff4081', light: '#fce4ec', text: '#c2185b' },
    { fill: '#448aff', light: '#e3f2fd', text: '#2962ff' },
  ] },
  { name: '咖啡', colors: [
    { fill: '#8d6e63', light: '#efebe9', text: '#5d4037' },
    { fill: '#a1887f', light: '#f5f0ee', text: '#6d4c41' },
    { fill: '#bcaaa4', light: '#f7f4f2', text: '#795548' },
    { fill: '#795548', light: '#efebe9', text: '#4e342e' },
    { fill: '#d7ccc8', light: '#faf8f7', text: '#6d4c41' },
  ] },
]

// 当前应用的配色名（用于下拉列表勾选态 + 按钮显示）；__clear 时置空
const activePalette = ref('')
const activePaletteColors = computed(() =>
  (PALETTES.find((x) => x.name === activePalette.value)?.colors || []).slice(0, 4).map((c) => c.fill)
)

function applyPaletteCmd(name) {
  const p = PALETTES.find((x) => x.name === name)
  eng.value?.applyPalette?.(p ? p.colors : null)   // __clear → null → 清除自定义色
  activePalette.value = p ? p.name : ''
  ElMessage.success(p ? `已应用「${p.name}」配色` : '已清除配色')
}

function openAi(pos) {
  // 右键菜单唤起时带右键点屏幕坐标，面板贴右键点弹出；工具栏按钮唤起走按钮锚点
  ai.anchorPoint = (pos && typeof pos.x === 'number') ? pos : null
  // 全部选中节点（不含根，带 uid 供批量定向改写）：单选开放扩写/优化/改写；多选开放批量优化/选中分支总结
  const nodes = (eng.value?.getActiveNodes?.() || []).filter((n) => !n.isRoot)
  ai.activeNodes = nodes
    .map((n) => ({ uid: n.getData('uid'), text: (n.getData('text') || '').replace(/<[^>]+>/g, '').trim() }))
    .filter((n) => n.uid && n.text)
  ai.activeTexts = ai.activeNodes.map((n) => n.text)
  ai.canExpand = ai.activeTexts.length === 1
  ai.nodeText = ai.activeTexts[0]?.slice(0, 20) || ''
  // 单选默认扩写；多选默认逐节点改写（空指令时会提示先描述）；未选中默认整图重建
  ai.mode = ai.canExpand ? 'expand' : (ai.activeTexts.length ? 'multi-rewrite' : 'rebuild')
  ai.images = []
  ai.result = ''
  ai.visible = true
}

async function aiGenerate() {
  let instruction = ai.instruction.trim()
  // 选中节点时空回车 = 默认「扩写」（记事本空提交=润色同款）；改写必须描述怎么改
  if (!instruction && ai.canExpand && ai.mode === 'expand') instruction = `扩写「${ai.nodeText}」这个分支`
  if (!instruction && ai.canExpand && ai.mode === 'rewrite') {
    ElMessage.warning('先描述一下怎么改写')
    return
  }
  // 只传图不写字也允许：后端按图片内容生成导图
  if ((!instruction && !(ai.images || []).length) || ai.loading) return
  ai.loading = true
  try {
    const expand = ai.canExpand && ai.mode === 'expand'
    const rewrite = ai.canExpand && ai.mode === 'rewrite'
    const context = eng.value ? flattenOutline(eng.value.getCanonical()).map((i) => i.text).filter(Boolean) : []
    const res = await mindmapAiAssist({
      instruction,
      // rebuild 模式优先：选中节点时点了整图类建议项（调研/拆解/趋势）不应误扩写
      mode: expand || rewrite ? ai.mode : 'rebuild',
      node_text: ai.nodeText,
      context: context.slice(-30),
      images: ai.images,
    })
    ai.visible = false
    // 渐进渲染：节点逐个出现（每节点 ~150ms），期间 loading 保持，结束后自动保存由防抖兜底
    const ok = rewrite
      ? await eng.value?.aiRewrite?.(res.children, res)
      : expand
        ? await eng.value?.aiExpand?.(res.children)
        : await eng.value?.aiRebuild?.(res)
    if (ok) ElMessage.success('已生成')
  } catch (e) {
    ElMessage.error(e.message || e)
  } finally {
    ai.loading = false
  }
}

// ---- 自动保存（与记事本/画板一致：1s 防抖；标题/画布/主题布局修改统一入口） ----
const saveState = ref('')
let loadReady = false   // 初始装载期间的 data_change 不触发保存
let saveTimer = null
let saving = false

function onEngChange() {
  if (!loadReady) return
  scheduleSave()
}

function scheduleSave() {
  if (!loadReady) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(flushSave, 1000)
}

async function flushSave() {
  clearTimeout(saveTimer)
  if (saving || !loadReady) return
  saving = true
  saveState.value = '保存中…'
  try {
    if (eng.value) currentData.value = eng.value.getDoc()
    await updateMindmap(id, { title: title.value, data: currentData.value })
    saveState.value = `已保存 ${new Date().toTimeString().slice(0, 5)}`
  } catch (e) {
    saveState.value = '保存失败'
    ElMessage.error(e.message)
  } finally {
    saving = false
  }
}

// ---------- 大纲（双向编辑）：行内改文字 / Enter 同级 / Tab 子级 / 空行退格删除 ----------
const outlineInputRefs = new Map()
let outlineBusy = false

function setOutlineInputRef(uid, el) {
  if (el) outlineInputRefs.set(uid, el)
  else outlineInputRefs.delete(uid)
}

function refreshOutline() {
  outlineItems.value = eng.value?.getOutlineLive?.() || []
}

function openOutline() {
  refreshOutline()
  outlineVisible.value = true
}

function outlineChange(item, v) {
  const text = (v || '').trim()
  if (!text) return refreshOutline()   // 空文本不改名，刷新还原
  eng.value?.outlineSetText(item.uid, text)
}

async function outlineKeydown(e, item) {
  if (e.key === 'Enter') {
    e.preventDefault()
    await outlineAdd(item, item.isRoot)   // 根节点无同级，Enter=加子级
  } else if (e.key === 'Tab') {
    e.preventDefault()
    await outlineAdd(item, true)
  } else if (e.key === 'Backspace' && !item.text.trim() && !item.isRoot) {
    e.preventDefault()
    outlineDel(item)
  }
}

async function outlineAdd(item, asChild) {
  if (outlineBusy) return
  outlineBusy = true
  try {
    // Enter/Tab 先于 input 的 change 事件：先把本行未提交的编辑写回画布，再插入新行
    const text = (item.text || '').trim()
    if (text) eng.value?.outlineSetText(item.uid, text)
    const newUid = await eng.value?.outlineInsert(item.uid, asChild)
    refreshOutline()
    if (newUid) {
      await nextTick()
      outlineInputRefs.get(newUid)?.focus?.()
    }
  } finally {
    outlineBusy = false
  }
}

function outlineDel(item) {
  eng.value?.outlineRemove(item.uid)
  refreshOutline()
}

// 主题/布局/分支样式偏好写回 localStorage（下次新建导图沿用）+ 触发自动保存
watch(theme, (v) => { localStorage.setItem('grt_mm_simple_theme', v); scheduleSave() })
watch(layout, (v) => { localStorage.setItem('grt_mm_simple_layout', v); scheduleSave() })
watch(lineStyle, (v) => { localStorage.setItem('grt_mm_simple_linestyle', v); scheduleSave() })

async function load() {
  loading.value = true
  try {
    const m = await getMindmap(id)
    title.value = m.title
    currentData.value = m.data
    // 原生文档：工具栏同步文档内保存的 主题/布局/分支样式
    if (m.data?.root) {
      theme.value = m.data.theme?.template || 'default'
      layout.value = m.data.layout || 'logicalStructure'
      lineStyle.value = m.data.theme?.config?.lineStyle || 'straight'
    }
    ready.value = true
    // 等下一拍：引擎装载完（装载期的 data_change 由 loadReady 挡掉），再开启自动保存
    setTimeout(() => { loadReady = true }, 500)
  } catch (e) {
    ElMessage.error(e.message)
    router.replace('/mindmaps')
  } finally {
    loading.value = false
  }
}

async function back() {
  await flushSave()   // 返回前补存未落盘的修改
  router.push('/mindmaps')
}

// Ctrl+S 立即保存（拦浏览器默认的另存为；平时靠 1s 防抖自动保存）
function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    flushSave()
  }
}

onMounted(() => {
  load()
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  clearTimeout(saveTimer)
  flushSave()   // 离开页面前补存（异步尽力而为）
})
</script>

<style scoped>
.editor-page { display: flex; flex-direction: column; height: calc(100vh - 120px); }
.save-state { font-size: 12px; color: #909399; flex-shrink: 0; margin-left: auto; }
.save-state.err { color: #f56c6c; }
/* 主题下拉的分组小标题（滚动时吸附顶部，白底防止列表文字透过来） */
.theme-group-label {
  padding: 6px 16px 2px; font-size: 12px; color: #909399; line-height: 1.4;
  cursor: default; user-select: none;
  position: sticky; top: -6px; background: #fff; z-index: 1;
}
.editor-toolbar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap;
}
/* 间距统一交给 flex gap：清掉相邻 el-button 默认的 12px 左外边距（否则两按钮相邻时间距翻倍） */
.editor-toolbar :deep(.el-button + .el-button) { margin-left: 0; }
.title-input { width: 240px; }
.shortcut-hint { font-size: 12px; color: #c0c4cc; }
.editor-body {
  flex: 1; background: #fff; border: 1px solid #e4e7ed; border-radius: 8px; overflow: hidden;
}
.dd-icon { display: inline-flex; vertical-align: -3px; }
.dd-icon :deep(svg) { width: 34px; height: 22px; }
.dd-item { display: flex; align-items: center; gap: 8px; }
.dd-item .dd-icon-lg :deep(svg) { width: 44px; height: 26px; }
.dd-check { margin-left: auto; color: #409eff; }
/* 色块选择器（字体/背景） */
.cp-group { display: inline-flex; align-items: center; gap: 4px; }
.cp-label { font-size: 12px; color: #909399; }
.cp-trigger {
  display: inline-flex; align-items: center; gap: 2px; padding: 3px 4px;
  border: 1px solid #dcdfe6; border-radius: 6px; cursor: pointer; background: #fff;
}
.cp-trigger:hover { border-color: #409eff; }
.cp-swatch { width: 18px; height: 18px; border-radius: 4px; border: 1px solid rgba(0, 0, 0, .1); }
.cp-swatch.empty { background: repeating-conic-gradient(#eee 0 25%, #fff 0 50%) 0 0 / 8px 8px; }
.cp-caret { font-size: 12px; color: #909399; }
/* 色块网格面板（popover 内容teleport到body，slot 保留本组件 scope id，scoped 样式有效） */
.cp-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; }
.cp-cell {
  width: 26px; height: 26px; border-radius: 6px; cursor: pointer;
  border: 2px solid rgba(0, 0, 0, .08); box-sizing: border-box;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 14px; color: #909399;
}
.cp-cell:hover { transform: scale(1.12); border-color: #409eff; }
.cp-cell.active { border-color: #409eff; box-shadow: 0 0 0 2px #d9ecff; }
.cp-cell-theme { background: repeating-conic-gradient(#eee 0 25%, #fff 0 50%) 0 0 / 8px 8px; }
/* AI 生成对话框提示 */
.ai-hint { font-size: 12px; color: #c0c4cc; margin-top: 8px; }
.outline-tree { font-size: 13px; color: #303133; line-height: 1.5; }
.outline-row { display: flex; align-items: center; gap: 4px; padding: 2px 0; }
.outline-input :deep(.el-input__wrapper) {
  box-shadow: none; border-radius: 4px; padding: 0 6px; background: transparent;
}
.outline-input :deep(.el-input__wrapper:hover),
.outline-input :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px #dcdfe6 inset; background: #fff; }
.outline-del { color: #c0c4cc; cursor: pointer; flex-shrink: 0; display: none; }
.outline-row:hover .outline-del { display: inline-flex; }
.outline-del:hover { color: #f56c6c; }
.outline-hint { margin-top: 12px; font-size: 12px; color: #c0c4cc; }
.palette-item { display: flex; align-items: center; gap: 6px; }
.palette-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
</style>

<!-- 主题下拉 popper 挂在 body 上，scoped 够不到，单独非 scoped 块 -->
<style>
/* 主题列表限高滚动：24 个主题全展开太高 */
.mm-theme-popper .el-dropdown-menu { max-height: 420px; overflow-y: auto; }
</style>
