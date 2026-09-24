<template>
  <div>
    <div class="page-header">
      <h2>设置</h2>
    </div>

    <!-- 模型服务 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>模型服务</span>
          <el-button type="primary" :icon="Plus" @click="openCreate">添加模型服务</el-button>
        </div>
      </template>
      <el-alert type="info" :closable="false" style="margin-bottom: 14px"
        title="支持 OpenAI 兼容接口（DeepSeek、通义千问、智谱等）和 Claude。Excel 结构分析与图片识别会使用「默认」的启用服务。" />
      <el-table :data="providers" v-loading="loading" border>
        <el-table-column prop="name" label="名称" width="150" />
        <el-table-column label="类型" width="140">
          <template #default="{ row }">
            <el-tag size="small">{{ row.type === 'claude' ? 'Claude' : 'OpenAI 兼容' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="base_url" label="Base URL" min-width="220" show-overflow-tooltip />
        <el-table-column prop="model" label="模型" width="180" />
        <el-table-column label="默认" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
            <el-button v-else text size="small" @click="setDefault(row)">设为默认</el-button>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-switch :model-value="row.enabled" @change="(v) => toggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button text size="small" :loading="testingId === row.id" @click="test(row)">测试</el-button>
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确定删除该配置？" @confirm="del(row)">
              <template #reference><el-button text type="danger" size="small">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty>还没有模型服务，点击右上角添加</template>
      </el-table>
    </el-card>

    <!-- 通知渠道配置 -->
    <el-card style="margin-top: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>通知渠道配置（任务动作使用）</span>
          <el-button type="primary" :loading="generalSaving" @click="saveGeneral">保存</el-button>
        </div>
      </template>
      <el-form label-width="120px" style="max-width: 720px">
        <el-divider content-position="left">邮件（SMTP）</el-divider>
        <el-form-item label="SMTP 服务器">
          <el-input v-model="general.smtp.host" placeholder="如 smtp.qq.com / smtp.163.com" />
        </el-form-item>
        <el-form-item label="端口 / SSL">
          <el-input-number v-model="general.smtp.port" :min="1" :max="65535" controls-position="right" style="width: 120px" />
          <el-switch v-model="general.smtp.use_ssl" active-text="SSL" style="margin-left: 16px" />
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="general.smtp.username" placeholder="邮箱账号" />
        </el-form-item>
        <el-form-item label="密码/授权码">
          <el-input
            v-model="general.smtp.password" type="password" show-password
            :placeholder="general.smtp.has_password ? '已配置，留空则不修改' : '邮箱密码或授权码'"
          />
        </el-form-item>
        <el-form-item label="发件人地址">
          <el-input v-model="general.smtp.from_addr" placeholder="留空则使用账号" />
        </el-form-item>
        <el-form-item label="测试邮件">
          <el-input v-model="testEmailTo" placeholder="收件邮箱" style="width: 240px" />
          <el-button :loading="testEmailSending" style="margin-left: 8px" @click="sendTestEmail">发送测试</el-button>
        </el-form-item>
        <el-divider content-position="left">短信网关</el-divider>
        <el-form-item label="URL 模板">
          <el-input
            v-model="general.sms_gateway.url_template" type="textarea" :rows="2"
            placeholder="如 https://sms.example.com/send?phone={phone}&msg={content}&key=xxx"
          />
          <div style="font-size: 12px; color: #909399; margin-top: 4px">
            发送时用 GET 请求调用该 URL，{phone} 和 {content} 会被替换为手机号和通知内容，适配大多数短信 HTTP 接口。
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 联网搜索配置（AI 助手使用） -->
    <el-card style="margin-top: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>联网搜索（AI 助手使用）</span>
          <el-button type="primary" :loading="webSearchSaving" @click="saveWebSearch">保存</el-button>
        </div>
      </template>
      <el-form label-width="120px" style="max-width: 720px">
        <el-form-item label="搜索服务">
          <el-select v-model="general.web_search.provider" style="width: 160px">
            <el-option label="博查 Bocha" value="bocha" />
            <el-option label="Tavily" value="tavily" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="general.web_search.api_key" type="password" show-password style="width: 360px"
            :placeholder="general.web_search.has_api_key ? '已配置，留空则不修改' : '搜索服务的 API Key'"
          />
          <el-button :loading="testSearchSending" style="margin-left: 8px" @click="sendTestSearch">测试搜索</el-button>
          <div style="font-size: 12px; color: #909399; margin-top: 4px">
            配置后 AI 助手可以联网查询实时信息（电话、排班、招投标、新闻等）；保存后可点「测试搜索」验证
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑模型服务' : '添加模型服务'" width="560px" destroy-on-close>
      <el-form label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：DeepSeek" />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-radio-group v-model="form.type">
            <el-radio value="openai_compat">OpenAI 兼容</el-radio>
            <el-radio value="claude">Claude</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="form.base_url" :placeholder="baseUrlPlaceholder" />
        </el-form-item>
        <el-form-item label="API Key" :required="!editing">
          <el-input
            v-model="form.api_key" type="password" show-password
            :placeholder="editing ? '留空则不修改' : '请输入 API Key'"
          />
        </el-form-item>
        <el-form-item label="模型" required>
          <el-input v-model="form.model" placeholder="如：deepseek-chat / qwen-plus / claude-sonnet-4-5" />
        </el-form-item>
        <el-form-item label="视觉模型">
          <el-input v-model="form.vision_model" placeholder="图片识别用，如 qwen-vl-max，留空与模型一致" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  createProvider, deleteProvider, getGeneralSettings, listProviders,
  saveGeneralSettings, setDefaultProvider, testEmail, testProvider, testSearchSettings, updateProvider,
} from '../api'

const providers = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const testingId = ref(null)
const form = reactive({ name: '', type: 'openai_compat', base_url: '', api_key: '', model: '', vision_model: '', is_default: false })

// 通知渠道
const general = reactive({ smtp: {}, sms_gateway: {}, web_search: {} })
const generalSaving = ref(false)
const testEmailTo = ref('')
const testEmailSending = ref(false)
const webSearchSaving = ref(false)
const testSearchSending = ref(false)

async function loadGeneral() {
  try {
    const res = await getGeneralSettings()
    general.smtp = res.smtp || {}
    // SSL 开关未设置过时按端口给默认值，避免 465 端口却显示关闭
    if (general.smtp.use_ssl === undefined) {
      general.smtp.use_ssl = Number(general.smtp.port) === 465
    }
    general.sms_gateway = res.sms_gateway || {}
    general.web_search = { provider: 'bocha', ...(res.web_search || {}) }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function saveGeneral() {
  generalSaving.value = true
  try {
    await saveGeneralSettings({ smtp: general.smtp, sms_gateway: general.sms_gateway })
    ElMessage.success('已保存')
    loadGeneral()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    generalSaving.value = false
  }
}

// 联网搜索独立保存：只提交 web_search，避免和通知渠道互相影响
async function saveWebSearch() {
  webSearchSaving.value = true
  try {
    await saveGeneralSettings({ web_search: general.web_search })
    ElMessage.success('已保存')
    loadGeneral()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    webSearchSaving.value = false
  }
}

async function sendTestSearch() {
  testSearchSending.value = true
  try {
    const r = await testSearchSettings()
    ElMessage.success(`搜索正常，返回 ${r.count} 条结果${r.sample?.length ? '：' + r.sample[0] : ''}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    testSearchSending.value = false
  }
}

async function sendTestEmail() {
  if (!testEmailTo.value.trim()) return ElMessage.warning('请填写收件邮箱')
  testEmailSending.value = true
  try {
    await saveGeneral()   // 先保存配置再测试
    await testEmail(testEmailTo.value.trim())
    ElMessage.success('测试邮件已发送')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    testEmailSending.value = false
  }
}

const baseUrlPlaceholder = computed(() =>
  form.type === 'claude'
    ? 'https://api.anthropic.com（留空用默认）'
    : '如 https://api.deepseek.com/v1 或 https://dashscope.aliyuncs.com/compatible-mode/v1'
)

async function load() {
  loading.value = true
  try {
    providers.value = await listProviders()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, { name: '', type: 'openai_compat', base_url: '', api_key: '', model: '', vision_model: '', is_default: false })
}

function openCreate() {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    name: row.name, type: row.type, base_url: row.base_url || '', api_key: '',
    model: row.model, vision_model: row.vision_model || '', is_default: row.is_default,
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim() || !form.model.trim()) return ElMessage.warning('请填写名称和模型')
  saving.value = true
  try {
    const payload = { ...form, base_url: form.base_url || null, vision_model: form.vision_model || null }
    if (editing.value) {
      await updateProvider(editing.value.id, { ...payload, api_key: form.api_key || null })
    } else {
      await createProvider(payload)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function toggle(row, v) {
  try {
    await updateProvider(row.id, {
      name: row.name, type: row.type, base_url: row.base_url, api_key: null,
      model: row.model, vision_model: row.vision_model, is_default: row.is_default, enabled: v,
    })
    row.enabled = v
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function setDefault(row) {
  try {
    await setDefaultProvider(row.id)
    ElMessage.success('已设为默认')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function test(row) {
  testingId.value = row.id
  try {
    const res = await testProvider(row.id)
    ElMessage.success(`连接成功（${res.elapsed}s）：${res.reply}`)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    testingId.value = null
  }
}

async function del(row) {
  try {
    await deleteProvider(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => {
  load()
  loadGeneral()
})
</script>
