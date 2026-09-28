<template>
  <!-- 报表只读渲染：页签 + 栅格（<768px 降级单列流式）；无布局时自动生成栅格（旧模板打开即新版）。查看页/分享页共用。 -->
  <div ref="rootEl" class="rdash">
    <el-tabs v-if="pages.length > 1" v-model="activeTab" class="rdash-tabs">
      <el-tab-pane v-for="p in pages" :key="p.id" :label="p.title" :name="p.id" />
    </el-tabs>
    <div
      v-for="p in pages" v-show="p.id === activeTab" :key="p.id"
      class="grid-canvas" :class="{ narrow }" :style="narrow ? {} : canvasStyle(p)"
    >
      <template v-for="it in p.items" :key="it.block_id">
        <div v-if="showBlock(it.block_id)" class="grid-item" :style="narrow ? {} : itemStyle(it)">
          <ReportBlock
            :block="blockOf(it.block_id)" :drillable="drillable" fill
            v-bind="filterProps(it.block_id)"
            @drill="(pl) => emit('drill', pl)" @link="(pl) => emit('link', pl)"
          />
        </div>
      </template>
      <el-empty
        v-if="!p.items.length && pages.length > 1" description="该页签还没有区块，去布局设计器添加"
        :image-size="60" class="grid-empty"
      />
    </div>
    <template v-if="unplaced.length">
      <div class="unplaced-title">其他</div>
      <div class="flow">
        <ReportBlock
          v-for="b in unplaced" :key="b.id" :block="b" :drillable="drillable"
          v-bind="filterProps(b.id)"
          @drill="(pl) => emit('drill', pl)" @link="(pl) => emit('link', pl)"
        />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import ReportBlock from './ReportBlock.vue'
import { GRID_COLS, GRID_MARGIN, ROW_HEIGHT, autoLayout, normalizeLayout, unplacedBlocks } from '../utils/reportLayout'

const props = defineProps({
  blocks: { type: Array, default: () => [] },   // run 结果的 blocks
  layout: { type: Object, default: null },      // 模板 layout（可空，空则自动布局）
  drillable: { type: Boolean, default: false },
  filterable: { type: Boolean, default: true }, // 只读场景（分享页）隐藏筛选组件块
})
const emit = defineEmits(['drill', 'link', 'viewer-filter'])

// 筛选组件在只读场景不渲染（控件无法生效）
function showBlock(blockId) {
  const b = blockOf(blockId)
  return b && (props.filterable || b.type !== 'filter')
}

// 筛选组件的控件值（按区块 id 保存，重跑后保持）+ 变化上抛
const filterState = reactive({})

function filterProps(blockId) {
  return {
    modelValue: filterState[blockId] ?? null,
    'onUpdate:modelValue': (v) => {
      filterState[blockId] = v
      const b = blockOf(blockId)
      emit('viewer-filter', {
        block_id: blockId, field: b?.field, value: v,
        data_type: b?.data_type, widget: b?.widget, dataset: b?.dataset_id,
      })
    },
  }
}

// 无布局模板 → autoLayout 兜底（新版栅格视图；不落库，设计器保存后生效）
const layout = computed(() => {
  const src = props.layout?.pages?.length ? props.layout : autoLayout(props.blocks)
  return normalizeLayout(src, props.blocks)
})
const pages = computed(() => layout.value.pages)
const unplaced = computed(() =>
  unplacedBlocks(layout.value, props.blocks).filter((b) => props.filterable || b.type !== 'filter')
)

const activeTab = ref('')
watch(pages, (ps) => {
  if (ps.length && !ps.some((p) => p.id === activeTab.value)) activeTab.value = ps[0].id
}, { immediate: true })

function blockOf(id) {
  return props.blocks.find((b) => b.id === id)
}

// ---------- 栅格定位（宽屏绝对定位；<768px 单列降级） ----------
const rootEl = ref(null)
const rootWidth = ref(1200)
let ro = null
const narrow = computed(() => rootWidth.value < 768)

const colWidth = computed(() => (rootWidth.value - (GRID_COLS - 1) * GRID_MARGIN) / GRID_COLS)

function itemStyle(it) {
  const cw = colWidth.value
  return {
    left: `${it.x * (cw + GRID_MARGIN)}px`,
    top: `${it.y * (ROW_HEIGHT + GRID_MARGIN)}px`,
    width: `${it.w * cw + (it.w - 1) * GRID_MARGIN}px`,
    height: `${it.h * ROW_HEIGHT + (it.h - 1) * GRID_MARGIN}px`,
  }
}

function canvasStyle(page) {
  const rows = (page.items || []).reduce((m, it) => Math.max(m, it.y + it.h), 0)
  return { height: `${rows ? rows * ROW_HEIGHT + (rows - 1) * GRID_MARGIN : 0}px` }
}

onMounted(() => {
  if (rootEl.value) rootWidth.value = rootEl.value.clientWidth || 1200
  ro = new ResizeObserver((entries) => {
    const w = entries[0]?.contentRect?.width
    if (w) rootWidth.value = w
  })
  if (rootEl.value) ro.observe(rootEl.value)
})

onBeforeUnmount(() => ro?.disconnect())
</script>

<style scoped>
.rdash-tabs { margin-bottom: 4px; }
.rdash-tabs :deep(.el-tabs__header) { margin-bottom: 12px; }

.grid-canvas { position: relative; }
.grid-item { position: absolute; }
.grid-canvas.narrow { position: static; display: flex; flex-direction: column; gap: 12px; }
.grid-canvas.narrow .grid-item { position: static; }
.grid-empty { padding: 24px 0; }

.unplaced-title { margin: 20px 0 10px; font-size: 14px; color: #909399; border-left: 4px solid #dcdfe6; padding-left: 8px; }

.flow > * + * { margin-top: 16px; }
</style>

