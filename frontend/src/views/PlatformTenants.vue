<template>
  <div>
    <div class="page-header">
      <h2>平台租户</h2>
      <el-button type="primary" @click="createVisible = true">开租户</el-button>
    </div>

    <el-table :data="tenants" v-loading="loading" border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">{{ { personal: '个人', enterprise: '企业', private: '私有化' }[row.type] || row.type }}</template>
      </el-table-column>
      <el-table-column prop="owner" label="所有者" width="110" />
      <el-table-column label="套餐" width="130">
        <template #default="{ row }">{{ row.subscription.plan_name || row.subscription.plan_code || '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="{ active: 'success', trial: 'warning', grace: 'warning', expired: 'danger' }[row.subscription.status] || 'info'" size="small">
            {{ { active: '正常', trial: '试用', grace: '宽限', expired: '过期' }[row.subscription.status] || row.subscription.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="到期时间" width="160">
        <template #default="{ row }">{{ row.subscription.expires_at || '永不到期' }}</template>
      </el-table-column>
      <el-table-column label="用量（表/记录/席位）" width="170">
        <template #default="{ row }">{{ row.usage.table_count }} / {{ row.usage.row_count }} / {{ row.usage.seat_count }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openSub(row)">改订阅</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 改订阅（收银台） -->
    <el-dialog v-model="subVisible" :title="`改订阅：${current?.name}`" width="440px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="套餐">
          <el-select v-model="subForm.plan_code" style="width: 100%">
            <el-option v-for="p in plans" :key="p.code" :label="`${p.name}（${p.code}）`" :value="p.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="席位数">
          <el-input-number v-model="subForm.seats" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker
            v-model="subForm.expires_at" type="datetime" value-format="YYYY-MM-DD HH:mm:ss"
            placeholder="留空 = 永不到期" style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="subForm.status" style="width: 100%">
            <el-option v-for="s in ['trial', 'active', 'grace', 'expired']" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-alert type="info" :closable="false" title="到期时间改到未来且当前为宽限/过期时，自动恢复为正常（续费）" />
      </el-form>
      <template #footer>
        <el-button @click="subVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveSub">保存</el-button>
      </template>
    </el-dialog>

    <!-- 开租户 -->
    <el-dialog v-model="createVisible" title="开租户" width="440px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="所有者账号">
          <el-input v-model="createForm.username" placeholder="须为已注册用户" />
        </el-form-item>
        <el-form-item label="空间名称">
          <el-input v-model="createForm.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="createForm.type" style="width: 100%">
            <el-option label="企业版" value="enterprise" />
            <el-option label="私有化" value="private" />
            <el-option label="个人版" value="personal" />
          </el-select>
        </el-form-item>
        <el-form-item label="套餐">
          <el-select v-model="createForm.plan_code" style="width: 100%">
            <el-option v-for="p in plans" :key="p.code" :label="`${p.name}（${p.code}）`" :value="p.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createTenant">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { platformCreateTenant, platformListPlans, platformListTenants, platformSetSubscription } from '../api'

const tenants = ref([])
const plans = ref([])
const loading = ref(false)
const saving = ref(false)
const subVisible = ref(false)
const createVisible = ref(false)
const current = ref(null)
const subForm = reactive({ plan_code: null, seats: 1, expires_at: null, status: null })
const createForm = reactive({ username: '', name: '', type: 'enterprise', plan_code: 'ent_standard' })

async function load() {
  loading.value = true
  try {
    const [t, p] = await Promise.all([platformListTenants(), platformListPlans()])
    tenants.value = t
    plans.value = p
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function openSub(row) {
  current.value = row
  Object.assign(subForm, {
    plan_code: row.subscription.plan_code,
    seats: row.subscription.seats || 1,
    expires_at: row.subscription.expires_at,
    status: row.subscription.status,
  })
  subVisible.value = true
}

async function saveSub() {
  saving.value = true
  try {
    await platformSetSubscription(current.value.id, {
      plan_code: subForm.plan_code,
      seats: subForm.seats,
      expires_at: subForm.expires_at || '',
      status: subForm.status,
    })
    ElMessage.success('订阅已更新')
    subVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function createTenant() {
  if (!createForm.username.trim() || !createForm.name.trim()) return ElMessage.warning('请填写完整')
  saving.value = true
  try {
    await platformCreateTenant(createForm)
    ElMessage.success('租户已创建')
    createVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>
