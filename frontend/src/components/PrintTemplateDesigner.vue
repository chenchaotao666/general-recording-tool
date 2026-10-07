<template>
  <el-dialog
    :model-value="modelValue" :title="templateId ? '编辑打印模板' : '新建打印模板'"
    width="96vw" top="3vh" destroy-on-close class="pt-designer" :close-on-press-escape="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="designer-body">
      <!-- 左：配置 -->
      <div class="cfg">
        <el-form label-width="86px" size="small">
          <el-form-item label="模板名称" required>
            <el-input v-model="form.name" maxlength="64" />
          </el-form-item>
        </el-form>

        <div class="excel-panel">
          <el-alert v-if="!loadedHasExcel" type="info" :closable="false" class="cur-file"
                    title="已按表结构生成初始排版，直接在右侧编辑即可" />
          <el-alert type="info" :closable="false" class="syntax-help">
            <template #title>
              <div class="syntax-title">占位符：先点右侧单元格，再点下面按钮插入</div>
            </template>
            <div class="token-panel">
              <div class="token-group">
                <div class="tg-title">单据信息（取第一条记录）</div>
                <div class="tg-chips">
                  <span
                    v-for="f in mainTokenFields" :key="f.field_name" class="token-chip" @mousedown.prevent
                    :title="`插入 {${f.field_name}}`" @click="insertToken(`{${f.field_name}}`)"
                  >{{ f.label }}</span>
                </div>
              </div>
              <div class="token-group">
                <div class="tg-title">{{ subformCandidates.length ? '明细行（按子表行数展开）' : '明细行（每条记录一行）' }}</div>
                <div class="tg-chips">
                  <span class="token-chip" title="明细行序号" @mousedown.prevent @click="insertToken(detailTokens.index)">序号</span>
                  <span
                    v-for="c in detailTokenCols" :key="c.field_name" class="token-chip" @mousedown.prevent
                    :title="`插入 ${detailTokens.wrap(c.field_name)}`" @click="insertToken(detailTokens.wrap(c.field_name))"
                  >{{ c.label }}</span>
                </div>
              </div>
              <div class="token-group">
                <div class="tg-title">合计 / 特殊</div>
                <div class="tg-chips">
                  <span
                    v-for="c in sumTokenCols" :key="c.field_name" class="token-chip" @mousedown.prevent
                    :title="`插入 ${detailTokens.wrap(c.field_name, 'sum')}（${c.label}列合计）`"
                    @click="insertToken(detailTokens.wrap(c.field_name, 'sum'))"
                  >{{ c.label }}合计</span>
                  <span class="token-chip" title="明细金额人民币大写" @mousedown.prevent @click="insertToken('{_total_cn}')">大写金额</span>
                  <span class="token-chip" title="记录 ID" @mousedown.prevent @click="insertToken('{_id}')">记录ID</span>
                  <span class="token-chip" title="打印当天" @mousedown.prevent @click="insertToken('{_today}')">打印日期</span>
                </div>
              </div>
            </div>
          </el-alert>
        </div>
      </div>

      <!-- 右：在线编辑器 -->
      <div class="editor-side">
        <div class="editor-bar">
          <el-tag size="small" type="success">Excel 在线编辑</el-tag>
          <span class="bar-ops">
            <el-button size="small" type="primary" plain @click="openLibrary">选择模板</el-button>
            <el-upload
              :auto-upload="false" :show-file-list="false" accept=".xlsx"
              :on-change="onFilePicked" class="excel-upload bar-upload"
            >
              <el-button size="small" type="primary" plain>上传 xlsx 载入</el-button>
            </el-upload>
            <el-button
              size="small" type="primary" plain :loading="previewLoading"
              :disabled="!sheetReady" @click="onPreview"
            >预览效果</el-button>
          </span>
        </div>
        <div v-loading="sheetLoading" element-loading-text="正在加载表格编辑器…" class="sheet-wrap">
          <div id="ptSheetBox" class="sheet-box" />
        </div>
      </div>
    </div>

    <!-- 填充效果预览：与打印入口共用同一预览对话框（当前编辑器内容 + 当前筛选口径，不落盘） -->
    <PrintPreviewDialog
      v-model="previewVisible" title="模板预览" :loader="previewLoader"
      hint="版式预览只出一份样例（整表模板会带上全部明细行）；正式打印按列表筛选口径"
    />

    <!-- 模板库：docs/打印模板 样例（含原图对照），点选即载入编辑器 -->
    <el-dialog
      v-model="libVisible" title="选择模板（下面为版式原图，点卡片套用）"
      width="min(1100px, 94vw)" top="4vh" append-to-body destroy-on-close
    >
      <div v-loading="libLoading" class="lib-body">
        <div v-for="g in libGroups" :key="g.dir" class="lib-group">
          <div class="lib-dir">{{ g.dir }}（{{ g.items.length }}）</div>
          <div class="lib-cards">
            <div v-for="t in g.items" :key="t.file" class="lib-card" @click="onPickLib(t)">
              <el-image
                v-if="t.img" :src="libImgUrl(t.img)" :alt="t.name" fit="cover"
                :preview-src-list="[libImgUrl(t.img)]" preview-teleported lazy
                class="lib-img" @click.stop
              >
                <template #placeholder><div class="lib-noimg">加载中…</div></template>
              </el-image>
              <div v-else class="lib-noimg">无预览图</div>
              <div class="lib-name" :title="t.name">{{ t.name }}</div>
            </div>
          </div>
        </div>
        <el-empty v-if="!libLoading && !libGroups.length" description="模板库为空" :image-size="60" />
      </div>
    </el-dialog>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createPrintTemplate, getPrintTemplate, listPrintLibrary, previewPrintExcel, printExcelUrl,
  printLibraryFileUrl, printStarterUrl,
  savePrintExcelJson, updatePrintTemplate, uploadPrintExcel,
} from '../api'
import PrintPreviewDialog from './PrintPreviewDialog.vue'
import { loadLuckysheet } from '../utils/luckysheetLoader'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  tableId: { type: Number, required: true },
  fields: { type: Array, default: () => [] },
  templateId: { type: Number, default: null },   // null = 新建
  fillParams: { type: Object, default: null },   // 预览口径：打开设计器时的列表筛选/排序快照
})
const emit = defineEmits(['update:modelValue', 'saved'])

const loading = ref(false)
const saving = ref(false)

const form = reactive({ name: '', config: null })

// ---------- 在线编辑器（luckysheet + luckyexcel 导入 xlsx） ----------
const loadedHasExcel = ref(false)
const pendingFile = ref(null)      // 编辑器载入失败时的兜底：保存按原文件上传
const sheetLoading = ref(false)
const sheetReady = ref(false)      // 编辑器已挂载且有内容
const sheetDirty = ref(false)      // 编辑器内容有未保存修改
let sheetSeq = 0                   // 防重入：旧异步回调不覆盖新实例

// luckyexcel 也按需加载（含 jszip，~300KB）
let luckyExcelPromise = null
const loadLuckyExcel = () => (luckyExcelPromise ||= import('luckyexcel').then((m) => m.default))

function destroySheet() {
  try { window.luckysheet?.destroy() } catch { /* 忽略重复销毁 */ }
  sheetReady.value = false
  sheetDirty.value = false
}

function createSheet(sheets) {
  destroySheet()
  window.luckysheet.create({
    container: 'ptSheetBox',
    data: sheets,
    lang: 'zh',
    title: 'print-template',
    showinfobar: false,
    showsheetbar: sheets.length > 1,
    hook: { updated: () => { sheetDirty.value = true } },
  })
  sheetReady.value = true
  sheetDirty.value = false
}

// source='tpl' 载入已保存模板；'starter' 载入按表结构生成的起始模板
async function openEditor(source) {
  const seq = ++sheetSeq
  sheetLoading.value = true
  try {
    await loadLuckysheet()
    const LuckyExcel = await loadLuckyExcel()
    await nextTick()
    const url = source === 'tpl' && props.templateId && loadedHasExcel.value
      ? printExcelUrl(props.templateId)
      : printStarterUrl(props.tableId)
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('模板文件加载超时')), 15000)
      LuckyExcel.transformExcelToLuckyByUrl(url, 'template.xlsx', (exportJson) => {
        clearTimeout(timer)
        if (!exportJson?.sheets?.length) return reject(new Error('模板文件解析失败'))
        if (seq === sheetSeq) createSheet(exportJson.sheets)
        resolve()
      })
    })
  } catch (e) {
    ElMessage.error(`在线编辑器加载失败：${e.message}，可改用「上传 xlsx 载入」方式`)
  } finally {
    if (seq === sheetSeq) sheetLoading.value = false
  }
}

// el-upload 的 on-change：uploadFile.raw 是原生 File；show-file-list=false 时组件不维护状态，重复选同一文件也会触发
async function onFilePicked(uploadFile) {
  const f = uploadFile?.raw
  if (!f) return
  if (!f.name.toLowerCase().endsWith('.xlsx')) {
    ElMessage({
      type: 'warning',
      duration: 5000,
      message: `只支持 .xlsx 格式（你选的是 ${f.name}）。WPS/Excel 里用「另存为 → xlsx」转换后再上传`,
    })
    return
  }
  sheetLoading.value = true
  pendingFile.value = f   // 原始文件始终保留：保存时先传它（图片/特殊格式兜底），再写编辑器内容
  try {
    await loadLuckysheet()
    const LuckyExcel = await loadLuckyExcel()
    await nextTick()
    LuckyExcel.transformExcelToLucky(f, (exportJson) => {
      sheetLoading.value = false
      if (exportJson?.sheets?.length) {
        createSheet(exportJson.sheets)   // 载入编辑器；pendingFile 保留原文件（图片/特殊格式兜底），保存时先传原文件
        sheetDirty.value = true
        ElMessage.success(`已载入 ${f.name}，可继续编辑（图片等编辑器不显示的内容会原样保留）`)
      } else {
        pendingFile.value = f            // 载入失败兜底：保存时按原文件直接上传
        ElMessage.warning('文件未能载入编辑器，保存时将按原文件直接上传')
      }
    }, () => {
      sheetLoading.value = false
      pendingFile.value = f
      ElMessage.warning('文件未能载入编辑器，保存时将按原文件直接上传')
    })
  } catch (e) {
    sheetLoading.value = false
    pendingFile.value = f
    ElMessage.warning('编辑器初始化失败，保存时将按原文件直接上传')
  }
}

// ---------- 占位符点击插入 ----------
const subformCandidates = computed(() => props.fields.filter((f) => f.data_type === 'subform'))
const mainTokenFields = computed(() =>
  props.fields.filter((f) => !['subform', 'image'].includes(f.data_type))
)
// 明细区列：子表模式取子表列，平表模式取主表字段（_row 语法）
const detailTokenCols = computed(() => {
  const sub = subformCandidates.value[0]
  if (sub) return (sub.options?.columns || []).map((c) => ({ field_name: c.field_name, label: c.label || c.field_name, data_type: c.data_type }))
  return mainTokenFields.value.map((f) => ({ field_name: f.field_name, label: f.label, data_type: f.data_type }))
})
const sumTokenCols = computed(() =>
  detailTokenCols.value.filter((c) => ['int', 'decimal'].includes(c.data_type))
)
const detailTokens = computed(() => {
  const sub = subformCandidates.value[0]
  const prefix = sub ? sub.field_name : '_row'
  return {
    index: `{${prefix}._index}`,
    wrap: (col, agg) => `{${prefix}.${col}${agg ? '#' + agg : ''}}`,
  }
})

// 插入到右侧编辑器当前选中的单元格；编辑状态下插入到光标处；编辑器未就绪则复制到剪贴板
async function insertToken(token) {
  const ls = window.luckysheet
  if (!sheetReady.value || !ls) {
    try {
      await navigator.clipboard.writeText(token)
      ElMessage.info(`编辑器未就绪，已复制 ${token}，可粘贴到单元格`)
    } catch {
      ElMessage.warning('编辑器未就绪，请稍候再试')
    }
    return
  }
  // 单元格编辑中（输入框可见）才插到光标处；注意输入框停靠在屏幕外时焦点也可能在
  // 编辑器上（单击选格后），那种"假编辑"状态要走下面的 setCellValue 路径
  const box = document.getElementById('luckysheet-input-box')
  const editing = document.activeElement?.id === 'luckysheet-rich-text-editor'
    && !!box && Number.parseFloat(getComputedStyle(box).top) > 0
  if (editing) {
    document.execCommand('insertText', false, token)
    return
  }
  const range = ls.getRange()?.[0]
  if (!range) {
    ElMessage.warning('请先在右侧表格里点选一个单元格')
    return
  }
  ls.setCellValue(range.row[0], range.column[0], token)
  sheetDirty.value = true
}

watch(() => props.modelValue, async (v) => {
  if (!v) {
    destroySheet()
    return
  }
  loading.value = true
  pendingFile.value = null
  try {
    if (props.templateId) {
      const t = await getPrintTemplate(props.templateId)
      Object.assign(form, { name: t.name, config: t.config || {} })
      loadedHasExcel.value = !!t.has_excel
    } else {
      Object.assign(form, { name: '', config: {} })
      loadedHasExcel.value = false
    }
    openEditor('tpl')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
})

// ---------- 模板库（docs/打印模板 样例，带原图对照） ----------
const libVisible = ref(false)
const libLoading = ref(false)
const libGroups = ref([])

const libImgUrl = (imgPath) => printLibraryFileUrl(imgPath, 'img')

async function openLibrary() {
  libVisible.value = true
  if (libGroups.value.length) return   // 模板库内容不变，缓存一次即可
  libLoading.value = true
  try {
    const res = await listPrintLibrary()
    const byDir = new Map()
    for (const t of res.items || []) {
      if (!byDir.has(t.dir)) byDir.set(t.dir, [])
      byDir.get(t.dir).push(t)
    }
    libGroups.value = [...byDir.entries()].map(([dir, items]) => ({ dir, items }))
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    libLoading.value = false
  }
}

// 点选模板：把库里的 xlsx 载入编辑器（作为初始内容，保存后生效）
async function onPickLib(t) {
  if (sheetDirty.value) {
    try {
      await ElMessageBox.confirm(`套用「${t.name}」将覆盖当前未保存的修改，确定？`, '选择模板', { type: 'warning' })
    } catch { return }
  }
  libVisible.value = false
  sheetLoading.value = true
  try {
    await loadLuckysheet()
    const LuckyExcel = await loadLuckyExcel()
    await nextTick()
    const res = await fetch(printLibraryFileUrl(t.file, 'xlsx'))
    if (!res.ok) throw new Error(`模板文件读取失败（${res.status}）`)
    const blob = await res.blob()
    LuckyExcel.transformExcelToLucky(blob, (exportJson) => {
      sheetLoading.value = false
      if (exportJson?.sheets?.length) {
        createSheet(exportJson.sheets)
        pendingFile.value = null
        sheetDirty.value = true   // 套用库模板视为修改，保存时写回
        if (!form.name.trim()) form.name = t.name
        ElMessage.success(`已套用「${t.name}」，占位符字段名记得按本表调整（左侧芯片可快速插入）`)
      } else {
        ElMessage.error('模板解析失败')
      }
    }, () => {
      sheetLoading.value = false
      ElMessage.error('模板解析失败')
    })
  } catch (e) {
    sheetLoading.value = false
    ElMessage.error(e.message)
  }
}

// ---------- 填充效果预览（当前编辑器内容，不落盘；与打印预览同一对话框、同一筛选口径） ----------
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewLoader = (paper) =>
  previewPrintExcel(props.tableId, window.luckysheet.getAllSheets(), paper,
    { ...(props.fillParams || {}), template_id: props.templateId || undefined })

async function onPreview() {
  if (!sheetReady.value || !window.luckysheet) return
  previewLoading.value = true
  previewVisible.value = true   // 对话框打开后由它自己的 watch 调 loader；这里只控制按钮态
  setTimeout(() => { previewLoading.value = false }, 600)
}

async function onSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写模板名称')
    return
  }
  saving.value = true
  try {
    const payload = { name: form.name.trim() }
    const saved = props.templateId
      ? await updatePrintTemplate(props.templateId, payload)
      : await createPrintTemplate(props.tableId, payload)
    // 先传原文件（保留图片/特殊格式），再写编辑器内容（后端会把原文件图片带回）
    if (pendingFile.value) {
      await uploadPrintExcel(saved.id, pendingFile.value)
    }
    if (sheetReady.value && window.luckysheet) {
      await savePrintExcelJson(saved.id, window.luckysheet.getAllSheets())
    }
    pendingFile.value = null
    loadedHasExcel.value = true
    ElMessage.success(`已保存 ${saved.code} ${saved.name}`)
    emit('saved', saved)
    emit('update:modelValue', false)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style>
/* luckysheet 的工具栏下拉/右键菜单/单元格输入框挂在 body 下，默认 z-index(15~1004)
   低于 el-overlay(2000+)，会被对话框遮罩盖住导致"点了没反应/输入看不见"，这里抬升到对话框之上 */
.luckysheet-cols-menu,
.luckysheetpopover,
.luckysheet-modal-dialog-mask,
.luckysheet-modal-dialog,
.luckysheet-input-box,
.luckysheet-input-box-index {
  z-index: 3010 !important;
}
/* 单元格输入框文字垂直居中（原生 flex 布局但子元素顶对齐，文字偏上） */
.luckysheet-input-box { align-items: center; }
</style>

<style scoped>
.designer-body { display: flex; gap: 14px; height: 80vh; }
.cfg { width: 420px; flex-shrink: 0; overflow-y: auto; padding-right: 6px; }
.excel-panel { margin-top: 4px; }
.excel-panel .cur-file { margin-bottom: 8px; font-size: 13px; }
.excel-panel .muted { color: #909399; font-size: 12px; }
.bar-ops { display: inline-flex; gap: 8px; margin-left: 12px; }   /* 与左侧标签拉开间距 */
.bar-ops .el-button + .el-upload .el-button { margin-left: 0; }
.excel-upload { display: inline-block; }
.syntax-help { margin-top: 6px; }
.syntax-title { font-size: 13px; }
/* 占位符点击插入面板 */
.token-panel { font-size: 12px; color: #606266; }
.token-group { margin-bottom: 8px; }
.tg-title { font-weight: 600; margin-bottom: 4px; }
.tg-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.token-chip {
  padding: 2px 8px; background: #fff; border: 1px solid #c6e2ff; border-radius: 10px;
  color: #409eff; cursor: pointer; user-select: none; line-height: 1.6;
}
.token-chip:hover { background: #409eff; color: #fff; }
.token-tip { color: #909399; margin-top: 4px; line-height: 1.6; }
/* 在线编辑器 */
.editor-side { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.editor-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.editor-bar .muted { color: #909399; font-size: 12px; }
.bar-ops { display: inline-flex; gap: 8px; margin-left: 12px; }   /* 与左侧标签拉开间距 */
.bar-ops .el-button + .el-upload .el-button { margin-left: 0; }
.sheet-wrap { flex: 1; position: relative; min-height: 0; border: 1px solid #dcdfe6; }
.sheet-box { position: absolute; inset: 0; margin: 0; padding: 0; overflow: hidden; }
.bar-upload { display: inline-block; }
.bar-hint { margin-left: 4px; }
/* 模板库卡片 */
.lib-body { max-height: 74vh; overflow-y: auto; }
.lib-group { margin-bottom: 14px; }
.lib-dir { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.lib-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.lib-card { border: 1px solid #dcdfe6; border-radius: 6px; overflow: hidden; cursor: pointer; transition: all .15s; }
.lib-card:hover { border-color: #409eff; box-shadow: 0 2px 8px rgba(64, 158, 255, .25); }
.lib-card img, .lib-card .lib-img { width: 100%; height: 140px; display: block; background: #f5f7fa; }
.lib-card .lib-img :deep(img) { width: 100%; height: 140px; object-fit: cover; object-position: top; cursor: zoom-in; }
.lib-noimg { height: 140px; display: flex; align-items: center; justify-content: center; color: #909399; background: #f5f7fa; font-size: 12px; }
.lib-name { padding: 6px 8px; font-size: 12px; color: #606266; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
