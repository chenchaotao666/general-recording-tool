<template>
  <!-- 表单填写态（「填写表单」页签与公开链接页共用）：按字段类型渲染题目控件；
       显示条件前端即时求值（服务端提交时复核）；计算类字段只读置灰（§12.2） -->
  <div class="ff" :class="{ 'without-cover': !coverSrc }">
    <div v-if="coverSrc" class="ff-cover"><img :src="coverSrc" alt="" /></div>
    <div class="ff-paper">
      <h1 class="ff-title">{{ def.title || '表单' }}</h1>
      <div v-if="def.description" class="ff-desc">{{ def.description }}</div>
      <div class="ff-line" />
      <template v-for="it in visibleItems" :key="it.fieldId">
        <div class="ff-q" :class="{ err: errors[it.fieldId] }">
          <div class="ff-q-title"><span v-if="it.required" class="ff-req">*</span>{{ it.title || it.field.label }}</div>
          <div v-if="it.description" class="ff-q-desc">{{ it.description }}</div>
          <FormControl :item="it" :model-value="data[it.fieldId]" :uploader="uploader" :members="members"
                       @update:model-value="(v) => setVal(it.fieldId, v)" />
          <div v-if="errors[it.fieldId]" class="ff-err">{{ errors[it.fieldId] }}</div>
        </div>
      </template>
      <el-button type="primary" class="ff-submit" :loading="submitting" @click="submit">提交</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import FormControl from './FormControl.vue'
import { isItemVisible } from './formLogic.js'

const props = defineProps({
  def: { type: Object, required: true },        // {title, description, cover, items:[{..., field}]}
  coverSrc: { type: String, default: '' },
  uploader: { type: Function, default: null },  // (file, kind) → Promise<{id, name}>
  members: { type: Array, default: null },      // 公开页为 null：人员题不可填
  submitting: Boolean,
})
const emit = defineEmits(['submit'])

const data = reactive({})
const errors = reactive({})
const fieldsByName = computed(() => new Map(props.def.items.map(it => [it.fieldId, it.field])))
const visibleItems = computed(() => props.def.items.filter(it => isItemVisible(it, data, fieldsByName.value)))

watch(() => props.def, () => {
  for (const k of Object.keys(data)) delete data[k]
  for (const k of Object.keys(errors)) delete errors[k]
})

function setVal(fn, v) { data[fn] = v; delete errors[fn] }
const isEmpty = (v) => v == null || v === '' || (Array.isArray(v) && !v.length)

function submit() {
  for (const k of Object.keys(errors)) delete errors[k]
  const payload = {}
  for (const it of visibleItems.value) {
    if (it.field.readonly) continue
    const v = data[it.fieldId]
    if (it.required && isEmpty(v)) errors[it.fieldId] = '此项为必填项'
    else if (!isEmpty(v)) payload[it.fieldId] = v
  }
  if (Object.keys(errors).length) return
  emit('submit', payload, () => { for (const k of Object.keys(data)) delete data[k] })
}
defineExpose({ setErrors: (errs) => Object.assign(errors, errs || {}) })
</script>

<style scoped>
.ff { max-width: 780px; margin: 0 auto; background: #F6F7F7; border-radius: 16px; padding: 0 24px 24px; }
.ff.without-cover { padding: 0; background: transparent; }
.ff-cover { margin: 0 -24px; }
.ff-cover img { width: 100%; height: 170px; object-fit: cover; border-radius: 16px 16px 0 0; display: block; }
.ff-paper { background: #fff; border-radius: 12px; padding: 36px 48px 40px; }
.ff-cover + .ff-paper { position: relative; margin-top: -44px; border-radius: 8px; }
.ff-title { font-size: var(--st-font-size-title); font-weight: 700; margin: 0 0 8px; color: var(--st-text-1); }
.ff-desc { font-size: var(--st-font-size); color: var(--st-text-2); white-space: pre-wrap; }
.ff-line { height: 1px; background: var(--st-border); margin: 20px 0 8px; }
.ff-q { padding: 18px 0 6px; }
.ff-q-title { font-size: var(--st-font-size); font-weight: 600; color: var(--st-text-1); margin-bottom: 10px; }
.ff-req { color: var(--el-color-danger); margin-right: 3px; }
.ff-q-desc { font-size: var(--st-font-size); color: var(--st-text-3); margin: -6px 0 10px; white-space: pre-wrap; }
.ff-err { color: var(--el-color-danger); font-size: var(--st-font-size); margin-top: 6px; }
.ff-submit { display: flex; width: 160px; max-width: 100%; height: 40px; margin: 40px auto 4px; border-radius: 4px; font-size: var(--st-font-size); }
@media (max-width: 600px) {
  .ff { padding: 0 12px 12px; }
  .ff-cover { margin: 0 -12px; }
  .ff-paper { padding: 24px 20px 32px; }
}
</style>
