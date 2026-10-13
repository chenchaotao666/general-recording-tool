<template>
  <div class="editor-page">
    <div class="editor-toolbar">
      <el-button :icon="Back" @click="back">返回</el-button>
      <el-input v-model="title" class="title-input" maxlength="200" placeholder="导图标题" @input="scheduleSave" />
      <el-button class="ai-btn" :loading="ai.loading" @click="openAi">✨ AI 生成</el-button>

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

      <!-- 主题：分组下拉 + 预览色块 -->
      <el-select v-model="theme" style="width: 108px" @change="(v) => eng?.setTheme(v)">
        <el-option-group v-for="g in THEME_GROUPS" :key="g.label" :label="g.label">
          <el-option v-for="t in g.items" :key="t.value" :label="t.label" :value="t.value">
            <span class="theme-opt">
              <span class="theme-swatch" :style="{ background: themeSwatch(t.value) }" />
              {{ t.label }}
            </span>
          </el-option>
        </el-option-group>
      </el-select>

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
      <el-button @click="eng?.exportPng(title)">导出 PNG</el-button>
      <span class="shortcut-hint">双击编辑 · Tab 子节点 · Enter 同级 · Ctrl+点击 / 右键拖框多选 · 右键归纳/概要</span>
      
      <span class="save-state" :class="{ err: saveState === '保存失败' }">{{ saveState }}</span>
    </div>

    <!-- AI 生成：整图重建 / 在选中节点下扩写；生成后节点逐个出现（渐进渲染） -->
    <el-dialog v-model="ai.visible" title="AI 生成思维导图" width="520px" append-to-body destroy-on-close>
      <el-input
        v-model="ai.instruction" type="textarea" :rows="3"
        placeholder="描述导图主题，如：帮我整理一份 Vue3 学习路线 / 制定一次北京三日游计划"
      />
      <el-radio-group v-if="ai.canExpand" v-model="ai.mode" style="margin-top: 10px">
        <el-radio value="rebuild">重建整图（清空现有内容）</el-radio>
        <el-radio value="expand">在选中节点「{{ ai.nodeText }}」下扩写</el-radio>
      </el-radio-group>
      <div class="ai-hint">生成后节点会逐个出现在画布上，全程约几秒到十几秒</div>
      <template #footer>
        <el-button @click="ai.visible = false">取消</el-button>
        <el-button type="primary" :loading="ai.loading" @click="aiGenerate">生成</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="outlineVisible" title="大纲" size="360px">
      <div class="outline-tree">
        <div
          v-for="(item, i) in outlineItems" :key="i"
          class="outline-item" :style="{ paddingLeft: item.depth * 18 + 6 + 'px' }"
        >{{ item.text || '（空）' }}</div>
        <el-empty v-if="!outlineItems.length" description="暂无内容" :image-size="60" />
      </div>
    </el-drawer>

    <div class="editor-body" v-loading="loading">
      <MindmapSimple v-if="ready" ref="eng" :data="currentData" @change="onEngChange" />
    </div>
  </div>
</template>

<script setup>
// 思维导图编辑器：引擎定型 simple-mind-map；数据存引擎无关中间格式（{text, children[]}）
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, Back, Check, RefreshLeft, RefreshRight } from '@element-plus/icons-vue'
import { getMindmap, mindmapAiAssist, updateMindmap } from '../api'
import MindmapSimple from '../components/MindmapSimple.vue'

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

// ---------- AI 生成（渐进渲染：节点逐个出现在画布上） ----------
const ai = reactive({ visible: false, loading: false, instruction: '', mode: 'rebuild', canExpand: false, nodeText: '' })

function openAi() {
  // 选中非根节点时提供「在该节点下扩写」选项
  const target = eng.value?.getActiveNode?.()
  ai.canExpand = !!target && !target.isRoot
  ai.nodeText = target?.getData('text')?.replace(/<[^>]+>/g, '').slice(0, 20) || ''
  ai.mode = ai.canExpand ? 'expand' : 'rebuild'
  ai.visible = true
}

async function aiGenerate() {
  const instruction = ai.instruction.trim()
  if (!instruction || ai.loading) return
  ai.loading = true
  try {
    const expand = ai.canExpand && ai.mode === 'expand'
    const context = eng.value ? flattenOutline(eng.value.getCanonical()).map((i) => i.text).filter(Boolean) : []
    const res = await mindmapAiAssist({
      instruction,
      mode: expand ? 'expand' : 'rebuild',
      node_text: ai.nodeText,
      context: context.slice(-30),
    })
    ai.visible = false
    // 渐进渲染：节点逐个出现（每节点 ~150ms），期间 loading 保持，结束后自动保存由防抖兜底
    const ok = expand
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

// 大纲：打开时从当前画布取一次中间格式快照
function openOutline() {
  outlineItems.value = eng.value ? flattenOutline(eng.value.getCanonical()) : []
  outlineVisible.value = true
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
.save-state { font-size: 12px; color: #909399; flex-shrink: 0; }
.save-state.err { color: #f56c6c; }
.theme-opt { display: inline-flex; align-items: center; gap: 8px; }
.theme-swatch { width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(0, 0, 0, .08); flex-shrink: 0; }
.editor-toolbar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap;
}
/* 间距统一交给 flex gap：清掉相邻 el-button 默认的 12px 左外边距（否则两按钮相邻时间距翻倍） */
.editor-toolbar :deep(.el-button + .el-button) { margin-left: 0; }
.title-input { width: 240px; }
.shortcut-hint { font-size: 12px; color: #c0c4cc; margin-left: auto; }
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
.outline-item {
  padding: 4px 6px; border-radius: 4px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.outline-item:hover { background: #f5f7fa; }
</style>
