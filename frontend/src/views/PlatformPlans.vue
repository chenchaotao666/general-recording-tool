<template>
  <div>
    <div class="page-header">
      <h2>套餐配置</h2>
      <el-button type="primary" @click="openCreate">新建套餐</el-button>
    </div>
    <el-alert
      type="info" :closable="false" class="tip"
      title="价格、配额、功能开关、宽限天数全部即时生效（订阅该套餐的所有租户）。权益值留空 = 不限；feature_* 键 1=开通。" />

    <el-table :data="plans" v-loading="loading" border>
      <el-table-column prop="sort" label="排序" width="60" />
      <el-table-column prop="code" label="标识" width="150" />
      <el-table-column prop="name" label="名称" width="130" />
      <el-table-column label="客群" width="90">
        <template #default="{ row }">{{ { individual: '个人', enterprise: '企业', private: '私有化' }[row.audience] || row.audience }}</template>
      </el-table-column>
      <el-table-column label="价格（月/年）" width="130">
        <template #default="{ row }">¥{{ fen(row.price_monthly) }} / ¥{{ fen(row.price_yearly) }}</template>
      </el-table-column>
      <el-table-column label="上架" width="70">
        <template #default="{ row }">
          <el-tag :type="row.is_public ? 'success' : 'info'" size="small">{{ row.is_public ? '上架' : '隐藏' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="关键权益" min-width="260">
        <template #default="{ row }">
          <span class="ent-brief">{{ entBrief(row.entitlements) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link size="small" @click="openEnts(row)">权益配置</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 套餐基本信息 -->
    <el-dialog v-model="editVisible" :title="isCreate ? '新建套餐' : `编辑套餐：${current?.code}`" width="440px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item v-if="isCreate" label="标识 code">
          <el-input v-model="form.code" placeholder="如 ent_custom" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="客群">
          <el-select v-model="form.audience" style="width: 100%">
            <el-option label="个人" value="individual" />
            <el-option label="企业" value="enterprise" />
            <el-option label="私有化" value="private" />
          </el-select>
        </el-form-item>
        <el-form-item label="月价（分）">
          <el-input-number v-model="form.price_monthly" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="年价（分）">
          <el-input-number v-model="form.price_yearly" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="上架">
          <el-switch v-model="form.is_public" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 权益编辑器（全量替换） -->
    <el-dialog v-model="entsVisible" :title="`权益配置：${current?.name}（${current?.code}）`" width="640px" destroy-on-close>
      <el-table :data="entRows" border size="small">
        <el-table-column label="键" min-width="200">
          <template #default="{ row }">
            <el-select v-model="row.key" filterable allow-create placeholder="选择或输入键" style="width: 100%">
              <el-option v-for="k in KNOWN_KEYS" :key="k.value" :label="`${k.value}（${k.label}）`" :value="k.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="值（空=不限 / 开关 1=开）" width="220">
          <template #default="{ row }">
            <el-input-number v-model="row.value" :min="0" placeholder="空=不限" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="" width="60">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="entRows.splice($index, 1)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button class="add-ent" size="small" @click="entRows.push({ key: '', value: null })">+ 添加键</el-button>
      <template #footer>
        <el-button @click="entsVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEnts">保存（对全部订阅租户生效）</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { platformCreatePlan, platformListPlans, platformSetEntitlements, platformUpdatePlan } from '../api'

const KNOWN_KEYS = [
  { value: 'max_tables', label: '数据表上限' },
  { value: 'max_rows', label: '记录总条数上限' },
  { value: 'max_storage_mb', label: '存储上限 MB' },
  { value: 'max_seats', label: '席位上限' },
  { value: 'min_seats', label: '最低起购席位' },
  { value: 'quota_grace_days', label: '超配额宽限天数' },
  { value: 'sub_grace_days', label: '订阅到期宽限天数' },
  { value: 'trash_retention_days', label: '回收站保留天数' },
  { value: 'audit_retention_days', label: '审计保留天数' },
  { value: 'feature_print_templates', label: '功能：打印模板' },
  { value: 'feature_automation', label: '功能：自动化' },
  { value: 'feature_api', label: '功能：API' },
  { value: 'feature_data_scope', label: '功能：数据范围' },
  { value: 'feature_owd', label: '功能：默认共享' },
  { value: 'feature_share_rules', label: '功能：共享规则' },
  { value: 'feature_perm_diagnose', label: '功能：权限诊断' },
  { value: 'feature_field_perm', label: '功能：字段权限' },
  { value: 'feature_audit', label: '功能：审计日志' },
]

const plans = ref([])
const loading = ref(false)
const saving = ref(false)
const editVisible = ref(false)
const entsVisible = ref(false)
const isCreate = ref(false)
const current = ref(null)
const form = reactive({ code: '', name: '', audience: 'individual', price_monthly: 0, price_yearly: 0, sort: 0, is_public: true })
const entRows = ref([])

const fen = (v) => ((v || 0) / 100).toFixed(v % 100 ? 2 : 0)

function entBrief(ents) {
  const parts = []
  if (ents.max_tables != null) parts.push(`表${ents.max_tables}`)
  if (ents.max_rows != null) parts.push(`记录${ents.max_rows}`)
  if (ents.max_storage_mb != null) parts.push(`存储${ents.max_storage_mb}MB`)
  if (ents.max_seats != null) parts.push(`席位${ents.max_seats}`)
  const feats = Object.keys(ents).filter((k) => k.startsWith('feature_') && ents[k]).length
  if (feats) parts.push(`功能×${feats}`)
  return parts.join(' · ') || '不限'
}

async function load() {
  loading.value = true
  try {
    plans.value = await platformListPlans()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function openCreate() {
  isCreate.value = true
  Object.assign(form, { code: '', name: '', audience: 'individual', price_monthly: 0, price_yearly: 0, sort: 0, is_public: true })
  editVisible.value = true
}

function openEdit(row) {
  isCreate.value = false
  current.value = row
  Object.assign(form, {
    code: row.code, name: row.name, audience: row.audience,
    price_monthly: row.price_monthly, price_yearly: row.price_yearly,
    sort: row.sort, is_public: row.is_public,
  })
  editVisible.value = true
}

async function save() {
  saving.value = true
  try {
    if (isCreate.value) {
      if (!form.code.trim() || !form.name.trim()) return ElMessage.warning('请填写标识与名称')
      await platformCreatePlan(form)
    } else {
      await platformUpdatePlan(current.value.id, {
        name: form.name, audience: form.audience,
        price_monthly: form.price_monthly, price_yearly: form.price_yearly,
        sort: form.sort, is_public: form.is_public,
      })
    }
    ElMessage.success('已保存')
    editVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function openEnts(row) {
  current.value = row
  entRows.value = Object.entries(row.entitlements || {}).map(([key, value]) => ({ key, value }))
  entsVisible.value = true
}

async function saveEnts() {
  const ents = {}
  for (const r of entRows.value) {
    if (!r.key?.trim()) continue
    ents[r.key.trim()] = r.value ?? null
  }
  saving.value = true
  try {
    await platformSetEntitlements(current.value.id, ents)
    ElMessage.success('权益已更新，即时生效')
    entsVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.tip { margin-bottom: 12px; }
.ent-brief { font-size: 12px; color: #606266; }
.add-ent { margin-top: 8px; }
</style>
