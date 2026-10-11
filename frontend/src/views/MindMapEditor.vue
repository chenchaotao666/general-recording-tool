<template>
  <div class="editor-page">
    <div class="editor-toolbar">
      <el-button :icon="Back" @click="back">返回</el-button>
      <el-input v-model="title" class="title-input" maxlength="200" placeholder="导图标题" />
      <span class="save-state" :class="{ dirty }">{{ dirty ? '未保存' : (savedAt ? `已保存 ${savedAt}` : '') }}</span>

      <!-- 前进/后退（库内置历史栈） -->
      <!-- 可用状态视觉区分：可用=蓝色实心，不可用=灰化 -->
      <el-button-group>
        <el-button size="small" title="后退（Ctrl+Z）" :disabled="!eng?.canUndo"
          :type="eng?.canUndo ? 'primary' : 'info'" :plain="!eng?.canUndo" @click="eng?.undo()">
          <el-icon><RefreshLeft /></el-icon>
        </el-button>
        <el-button size="small" title="前进（Ctrl+Y）" :disabled="!eng?.canRedo"
          :type="eng?.canRedo ? 'primary' : 'info'" :plain="!eng?.canRedo" @click="eng?.redo()">
          <el-icon><RefreshRight /></el-icon>
        </el-button>
      </el-button-group>

      <!-- 布局：图标下拉（小示意图 + 名称） -->
      <el-dropdown trigger="click" @command="(v) => { layout = v; eng?.setLayout(v) }">
        <el-button size="small" title="布局">
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
        <el-button size="small" title="分支样式">
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
      <el-select v-model="theme" size="small" style="width: 140px" @change="(v) => eng?.setTheme(v)">
        <el-option-group v-for="g in THEME_GROUPS" :key="g.label" :label="g.label">
          <el-option v-for="t in g.items" :key="t.value" :label="t.label" :value="t.value">
            <span class="theme-opt">
              <span class="theme-swatch" :style="{ background: themeSwatch(t.value) }" />
              {{ t.label }}
            </span>
          </el-option>
        </el-option-group>
      </el-select>

      <el-button size="small" @click="openOutline">大纲</el-button>
      <span class="shortcut-hint">双击编辑 · Tab 子节点 · Enter 同级节点 · Delete 删除 · 右键更多</span>
      <el-button size="small" @click="eng?.exportPng(title)">导出 PNG</el-button>
      <el-button type="primary" size="small" :loading="saving" @click="save">保存（Ctrl+S）</el-button>
    </div>

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
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Back, Check, RefreshLeft, RefreshRight } from '@element-plus/icons-vue'
import { getMindmap, updateMindmap } from '../api'
import MindmapSimple from '../components/MindmapSimple.vue'
import { useDirtyGuard } from '../utils/useDirtyGuard'

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
const saving = ref(false)
const eng = ref(null)
const theme = ref(localStorage.getItem('grt_mm_simple_theme') || 'default')
const layout = ref(localStorage.getItem('grt_mm_simple_layout') || 'logicalStructure')
const lineStyle = ref(localStorage.getItem('grt_mm_simple_linestyle') || 'straight')
const outlineVisible = ref(false)
const outlineItems = ref([])

// ---- 离开保护：画布/标题有未保存修改时拦截路由与浏览器关闭 ----
const dirty = ref(false)
const savedAt = ref('')   // 标题旁「已保存 HH:mm」状态（对齐记事本）
let dirtyReady = false   // 初始加载完成后才开始追踪
useDirtyGuard(dirty, '当前思维导图有未保存的修改，离开后修改将丢失。')

function onEngChange() {
  if (dirtyReady) dirty.value = true
}
// 标题/主题/布局/分支样式的修改
watch(title, () => { if (dirtyReady) dirty.value = true })
// 主题/布局/分支样式偏好写回 localStorage（下次新建导图沿用），并标 dirty
watch(theme, (v) => { if (dirtyReady) { dirty.value = true; localStorage.setItem('grt_mm_simple_theme', v) } })
watch(layout, (v) => { if (dirtyReady) { dirty.value = true; localStorage.setItem('grt_mm_simple_layout', v) } })
watch(lineStyle, (v) => { if (dirtyReady) { dirty.value = true; localStorage.setItem('grt_mm_simple_linestyle', v) } })

// 大纲：打开时从当前画布取一次中间格式快照
function openOutline() {
  outlineItems.value = eng.value ? flattenOutline(eng.value.getCanonical()) : []
  outlineVisible.value = true
}

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
    dirtyReady = true   // 加载完成，开始追踪修改
  } catch (e) {
    ElMessage.error(e.message)
    router.replace('/mindmaps')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (eng.value) currentData.value = eng.value.getDoc()
  saving.value = true
  try {
    await updateMindmap(id, { title: title.value, data: currentData.value })
    ElMessage.success('已保存')
    dirty.value = false
    savedAt.value = new Date().toTimeString().slice(0, 5)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function back() {
  router.push('/mindmaps')
}

// Ctrl+S 保存（拦浏览器默认的另存为）
function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    save()
  }
}

onMounted(() => {
  load()
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.editor-page { display: flex; flex-direction: column; height: calc(100vh - 120px); }
.save-state { font-size: 12px; color: #909399; flex-shrink: 0; }
.save-state.dirty { color: #e6a23c; }
.theme-opt { display: inline-flex; align-items: center; gap: 8px; }
.theme-swatch { width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(0, 0, 0, .08); flex-shrink: 0; }
.editor-toolbar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap;
}
.title-input { width: 240px; }
.shortcut-hint { font-size: 12px; color: #c0c4cc; flex: 1; }
.editor-body {
  flex: 1; background: #fff; border: 1px solid #e4e7ed; border-radius: 8px; overflow: hidden;
}
.dd-icon { display: inline-flex; vertical-align: -3px; }
.dd-icon :deep(svg) { width: 26px; height: 16px; }
.dd-item { display: flex; align-items: center; gap: 8px; }
.dd-item .dd-icon-lg :deep(svg) { width: 44px; height: 26px; }
.dd-check { margin-left: auto; color: #409eff; }
.outline-tree { font-size: 13px; color: #303133; line-height: 1.5; }
.outline-item {
  padding: 4px 6px; border-radius: 4px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.outline-item:hover { background: #f5f7fa; }
</style>
