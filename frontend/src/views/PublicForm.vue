<template>
  <div class="public-form-page" v-loading="loading">
    <el-card v-if="meta" class="form-card">
      <div class="form-head">
        <h2 class="form-title">{{ meta.name }}</h2>
        <div v-if="meta.description" class="form-desc">{{ meta.description }}</div>
      </div>

      <el-result v-if="submitted" icon="success" title="提交成功" sub-title="感谢填写，信息已收到">
        <template #extra>
          <el-button type="primary" @click="reset">再填一份</el-button>
        </template>
      </el-result>

      <el-form v-else ref="formRef" :model="form" :rules="rules" label-position="top" size="large">
        <el-form-item v-for="f in meta.fields" :key="f.field_name" :label="f.label" :prop="f.field_name">
          <el-input v-if="f.widget === 'textarea'" v-model="form[f.field_name]" type="textarea" :rows="5"
            :placeholder="'请输入' + f.label" />
          <el-input-number v-else-if="f.widget === 'number'" v-model="form[f.field_name]" style="width: 100%"
            controls-position="right" />
          <el-date-picker v-else-if="f.widget === 'date-picker'" v-model="form[f.field_name]" type="date"
            value-format="YYYY-MM-DD" :placeholder="'请选择' + f.label" style="width: 100%" />
          <el-date-picker v-else-if="f.widget === 'datetime-picker'" v-model="form[f.field_name]" type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss" :placeholder="'请选择' + f.label" style="width: 100%" />
          <el-select v-else-if="f.widget === 'select'" v-model="form[f.field_name]" clearable
            :placeholder="'请选择' + f.label" style="width: 100%">
            <el-option v-for="opt in fieldOptions(f)" :key="String(opt)" :label="String(opt)" :value="opt" />
          </el-select>
          <el-switch v-else-if="f.widget === 'switch'" v-model="form[f.field_name]" />
          <el-input v-else v-model="form[f.field_name]" clearable :placeholder="'请输入' + f.label" />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" :closable="false" class="mb" />
        <el-button type="primary" style="width: 100%" :loading="submitting" @click="onSubmit">提交</el-button>
      </el-form>
    </el-card>

    <el-result v-else-if="error" icon="warning" title="链接无效" :sub-title="error" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getPublicForm, submitPublicForm } from '../api'

const route = useRoute()
const { wfId, secret } = route.params

const loading = ref(true)
const submitting = ref(false)
const submitted = ref(false)
const meta = ref(null)
const error = ref('')
const formRef = ref()
const form = reactive({})

function fillDefaults() {
  for (const key of Object.keys(form)) delete form[key]
  for (const f of meta.value?.fields || []) {
    form[f.field_name] =
      f.widget === 'switch' ? false : (f.default_value ?? null)
  }
}

const rules = computed(() => {
  const r = {}
  for (const f of meta.value?.fields || []) {
    if (!f.nullable) {
      r[f.field_name] = [{ required: true, message: `请填写${f.label}`, trigger: ['blur', 'change'] }]
    }
  }
  return r
})

const fieldOptions = (f) => f.options?.options || []

async function onSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  error.value = ''
  try {
    await submitPublicForm(wfId, secret, { ...form })
    submitted.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}

function reset() {
  submitted.value = false
  fillDefaults()
}

onMounted(async () => {
  try {
    meta.value = await getPublicForm(wfId, secret)
    fillDefaults()
    document.title = meta.value.name
  } catch (e) {
    error.value = '表单不存在或已停用'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.public-form-page {
  min-height: 100vh; background: #f5f7fa; padding: 24px 16px;
  display: flex; justify-content: center; align-items: flex-start;
}
.form-card { width: 100%; max-width: 560px; }
.form-head { margin-bottom: 16px; }
.form-title { margin: 0; font-size: 20px; color: #303133; }
.form-desc { margin-top: 6px; font-size: 13px; color: #909399; white-space: pre-wrap; }
.mb { margin-bottom: 12px; }
</style>
