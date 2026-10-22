<template>
  <!-- 单个题目控件：preview=true 为编辑画布上的占位态（灰底「待填写人完成」，对齐参照 右上角工具栏-生成表单-编辑.png） -->
  <div class="fc" :class="{ preview }">
    <div v-if="readonly" class="fc-ph fc-ro">{{ readonlyHint(ft) }}</div>

    <!-- 单选：平铺 radio（默认）/ 下拉 -->
    <template v-else-if="ft === 'singleSelect'">
      <el-select v-if="item.widget === 'dropdown'" :model-value="modelValue" class="fc-in" :disabled="preview"
                 placeholder="请选择" clearable @update:model-value="emitV">
        <el-option v-for="o in options" :key="o.id" :value="o.id" :label="o.label" />
      </el-select>
      <div v-else class="fc-opts">
        <label v-for="o in options" :key="o.id" class="fc-opt" @click="!preview && emitV(modelValue === o.id ? null : o.id)">
          <span class="fc-radio" :class="{ on: modelValue === o.id }" />{{ o.label }}
        </label>
      </div>
    </template>
    <div v-else-if="ft === 'multiSelect'" class="fc-opts">
      <label v-for="o in options" :key="o.id" class="fc-opt" @click="!preview && toggleMulti(o.id)">
        <span class="fc-check" :class="{ on: (modelValue || []).includes(o.id) }" />{{ o.label }}
      </label>
    </div>
    <span v-else-if="ft === 'checkbox'" class="fc-check fc-check-lg" :class="{ on: !!modelValue }"
          @click="!preview && emitV(!modelValue)" />

    <!-- 图片 / 文件：上传区 -->
    <div v-else-if="ft === 'image' || ft === 'file'" class="fc-upload" :class="{ big: ft === 'image' }"
         @click="!preview && pickFile()">
      <template v-if="!(modelValue || []).length">
        <span class="fc-up-ph">{{ preview ? '待填写人完成' : (ft === 'image' ? '点击上传图片' : '点击上传文件') }}</span>
      </template>
      <div v-else class="fc-files">
        <span v-for="(f, i) in modelValue" :key="i" class="fc-file">{{ ft === 'image' ? `图片 ${i + 1}` : (f.name || f) }}
          <span class="fc-x" @click.stop="emitV(modelValue.filter((_, j) => j !== i))">✕</span></span>
        <span class="fc-up-more">＋ 继续上传</span>
      </div>
      <span v-if="uploading" class="fc-uploading">上传中…</span>
      <input ref="fileRef" type="file" class="fc-file-input" :accept="ft === 'image' ? 'image/*' : undefined" @change="onFile" />
    </div>

    <!-- 人员 -->
    <template v-else-if="ft === 'member'">
      <div v-if="preview || !members" class="fc-ph">{{ preview ? '待填写人完成' : '该题仅限登录成员填写' }}</div>
      <el-select v-else :model-value="modelValue || []" multiple filterable class="fc-in" placeholder="选择人员" @update:model-value="emitV">
        <el-option v-for="m in members" :key="m.id" :value="m.id" :label="m.name" />
      </el-select>
    </template>

    <!-- 日期 -->
    <el-date-picker v-else-if="ft === 'date' && !preview" :model-value="modelValue" class="fc-in"
                    :type="item.field.options?.includeTime ? 'datetime' : 'date'"
                    :value-format="item.field.options?.includeTime ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD'"
                    placeholder="选择日期" @update:model-value="emitV" />
    <!-- 数字类 -->
    <el-slider v-else-if="ft === 'progress' && !preview" :model-value="Number(modelValue) || 0"
               :min="item.field.options?.range?.min ?? 0" :max="item.field.options?.range?.max ?? 100" @update:model-value="emitV" />
    <el-input-number v-else-if="isNumber && !preview" :model-value="modelValue" class="fc-in fc-num" controls-position="right"
                     @update:model-value="emitV" />
    <!-- 链接：{url, text} -->
    <el-input v-else-if="ft === 'url' && !preview" :model-value="modelValue?.url || ''" class="fc-in" placeholder="https://"
              @update:model-value="(v) => emitV(v ? { url: v, text: v } : null)" />
    <div v-else-if="ft === 'relation'" class="fc-ph">{{ preview ? '待填写人完成' : '关联记录请在表格中填写' }}</div>
    <!-- 文本类 / 预览占位 -->
    <div v-else-if="preview" class="fc-ph">待填写人完成</div>
    <el-input v-else :model-value="modelValue" class="fc-in" :type="ft === 'text' ? 'textarea' : 'text'" :autosize="{ minRows: 1, maxRows: 6 }"
              placeholder="请输入" @update:model-value="emitV" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { readonlyHint } from './formLogic.js'

const props = defineProps({
  item: { type: Object, required: true },
  modelValue: { type: [String, Number, Boolean, Array, Object], default: null },
  preview: Boolean,
  uploader: { type: Function, default: null },
  members: { type: Array, default: null },
})
const emit = defineEmits(['update:modelValue'])

const ft = computed(() => props.item.field.field_type || 'text')
const readonly = computed(() => !!props.item.field.readonly || ['formula', 'lookup', 'autoNumber', 'ai'].includes(ft.value))
const options = computed(() => props.item.field.options?.options || [])
const isNumber = computed(() => ['number', 'percent', 'currency'].includes(ft.value))
const fileRef = ref(null)
const uploading = ref(false)

function emitV(v) { emit('update:modelValue', v) }
function toggleMulti(id) {
  const cur = props.modelValue || []
  emitV(cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id])
}
function pickFile() { fileRef.value?.click() }
async function onFile(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file || !props.uploader) return
  uploading.value = true
  try {
    const r = await props.uploader(file, ft.value)
    const list = [...(props.modelValue || [])]
    list.push(ft.value === 'image' ? String(r.id) : { id: r.id, name: r.name || file.name })
    emitV(list)
  } catch (err) {
    ElMessage.error(err.message || '上传失败')
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.fc-in { width: 100%; }
.fc-num { width: 240px; }
.fc-ph { background: #F5F6F7; border: 1px solid #ECEDEF; border-radius: 4px; padding: 9px 12px; font-size: var(--st-font-size); color: var(--st-text-4); }
.fc-ro { color: var(--st-text-3); }
.fc-opts { display: flex; flex-direction: column; gap: 12px; }
.fc-opt { display: inline-flex; align-items: center; gap: 10px; font-size: var(--st-font-size); color: var(--st-text-2); cursor: pointer; }
.preview .fc-opt { cursor: default; }
.fc-radio { width: 16px; height: 16px; border-radius: 50%; border: 1px solid #D0D3D6; background: #F5F6F7; box-sizing: border-box; flex: none; }
.fc-radio.on { border: 5px solid var(--st-primary); background: #fff; }
.fc-check { width: 16px; height: 16px; border-radius: 3px; border: 1px solid #D0D3D6; background: #F5F6F7; display: inline-flex; align-items: center; justify-content: center; flex: none; cursor: pointer; }
.fc-check.on { background: var(--st-primary); border-color: var(--st-primary); }
.fc-check.on::after { content: '✓'; color: #fff; font-size: 11px; }
.fc-check-lg { width: 20px; height: 20px; }
.fc-upload { position: relative; background: #F5F6F7; border: 1px solid #ECEDEF; border-radius: 4px; min-height: 46px; display: flex; align-items: center; justify-content: center; cursor: pointer; padding: 8px; }
.fc-upload.big { min-height: 150px; }
.preview .fc-upload { cursor: default; }
.fc-up-ph { color: var(--st-text-4); font-size: var(--st-font-size); }
.fc-files { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.fc-file { background: #fff; border: 1px solid var(--st-border); border-radius: 4px; padding: 3px 8px; font-size: var(--st-font-size); display: inline-flex; gap: 6px; }
.fc-x { color: var(--st-text-3); cursor: pointer; }
.fc-up-more { color: var(--st-primary); font-size: var(--st-font-size); }
.fc-uploading { position: absolute; right: 10px; bottom: 6px; font-size: var(--st-font-size); color: var(--st-text-3); }
.fc-file-input { display: none; }
</style>
