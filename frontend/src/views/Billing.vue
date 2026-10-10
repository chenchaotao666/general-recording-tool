<template>
  <div>
    <div class="page-header">
      <h2>套餐与用量</h2>
      <el-button v-if="info?.my_role === 'admin'" type="primary" @click="$router.push('/billing/upgrade')">
        升级 / 续费
      </el-button>
    </div>

    <el-row :gutter="16" v-loading="loading">
      <el-col :span="8">
        <el-card>
          <template #header>当前套餐</template>
          <div v-if="info?.plan" class="plan-name">{{ info.plan.name }}</div>
          <div v-else class="plan-name">—</div>
          <div class="plan-meta">工作空间：{{ info?.tenant?.name }}（{{ typeLabel }}）</div>
          <div class="plan-meta" v-if="info?.plan && (info.plan.price_yearly || info.plan.price_monthly)">
            价格：¥{{ fen(info.plan.price_yearly) }}/年<span v-if="info.plan.price_monthly">（¥{{ fen(info.plan.price_monthly) }}/月）</span>
          </div>
          <div class="plan-meta">
            状态：
            <el-tag :type="statusTag.type" size="small">{{ statusTag.text }}</el-tag>
          </div>
          <div class="plan-meta" v-if="info?.subscription?.expires_at">到期时间：{{ info.subscription.expires_at }}</div>
          <div class="plan-meta" v-else>到期时间：永不到期</div>
          <div class="plan-meta" v-if="info?.subscription?.status === 'grace'">
            宽限期剩 {{ info.subscription.grace_remaining_days }} 天（至 {{ info.subscription.grace_until }}）
          </div>

        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card>
          <template #header>用量</template>
          <div v-for="q in quotaRows" :key="q.key" class="quota-row">
            <div class="quota-label">{{ q.label }}</div>
            <el-progress
              v-if="q.limit" :percentage="Math.min(q.percent || 0, 100)"
              :status="q.percent >= 100 ? 'exception' : q.percent >= 80 ? 'warning' : ''"
              class="quota-bar"
            />
            <div v-else class="quota-unlimited">不限</div>
            <div class="quota-value">{{ q.usedText }}<span v-if="q.limit"> / {{ q.limitText }}</span></div>
          </div>
          <el-alert
            v-if="!info?.writable" type="error" :closable="false" class="readonly-tip"
            title="订阅已过期：当前为只读状态，数据完整保留，续费后自动恢复"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 订单记录 -->
    <el-card v-if="orders.length" class="orders-card">
      <template #header>订单记录</template>
      <el-table :data="orders" border size="small">
        <el-table-column prop="created_at" label="下单时间" width="160" />
        <el-table-column prop="plan_name" label="套餐" min-width="130" />
        <el-table-column label="规格" width="150">
          <template #default="{ row }">{{ row.years }} 年<template v-if="row.seats > 1"> × {{ row.seats }} 席</template></template>
        </el-table-column>
        <el-table-column label="金额" width="110">
          <template #default="{ row }">¥{{ fen(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="{ paid: 'success', pending: 'warning', cancelled: 'info' }[row.status]" size="small">
              {{ { paid: '已支付', pending: '待支付', cancelled: '已取消' }[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="paid_at" label="支付时间" width="160" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCurrentTenant, listOrders } from '../api'

const info = ref(null)
const orders = ref([])
const loading = ref(false)

const fen = (v) => (v / 100).toFixed(v % 100 ? 2 : 0)
const typeLabel = computed(() => ({ personal: '个人版', enterprise: '企业版', private: '私有化' }[info.value?.tenant?.type] || ''))
const statusTag = computed(() => {
  const s = info.value?.subscription?.status
  return {
    trial: { type: 'warning', text: '试用中' },
    active: { type: 'success', text: '正常' },
    grace: { type: 'warning', text: '宽限期' },
    expired: { type: 'danger', text: '已过期（只读）' },
  }[s] || { type: 'info', text: s || '正常' }
})

const fmtBytes = (b) => {
  if (b >= 1024 ** 3) return (b / 1024 ** 3).toFixed(1) + ' GB'
  if (b >= 1024 ** 2) return (b / 1024 ** 2).toFixed(1) + ' MB'
  return (b / 1024).toFixed(1) + ' KB'
}

const quotaRows = computed(() => {
  const u = info.value?.usage || {}
  return [
    { key: 'tables', label: '数据表', ...u.tables, usedText: u.tables?.used ?? 0, limitText: u.tables?.limit },
    { key: 'rows', label: '记录总条数', ...u.rows, usedText: u.rows?.used ?? 0, limitText: u.rows?.limit },
    {
      key: 'storage', label: '存储空间', limit: u.storage?.limit, percent: u.storage?.percent,
      usedText: fmtBytes(u.storage?.used || 0), limitText: u.storage?.limit ? u.storage.limit + ' MB' : null,
    },
    { key: 'seats', label: '成员席位', ...u.seats, usedText: u.seats?.used ?? 0, limitText: u.seats?.limit },
  ]
})

async function load() {
  loading.value = true
  try {
    info.value = await getCurrentTenant()
    if (info.value?.my_role === 'admin') {
      orders.value = await listOrders().catch(() => [])
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

</script>

<style scoped>
.plan-name { font-size: 20px; font-weight: 600; margin-bottom: 8px; }
.plan-meta { color: #606266; font-size: 13px; margin-top: 6px; }
.upgrade-btn { margin-top: 12px; }
.quota-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
.quota-row:last-child { border-bottom: none; }
.quota-label { width: 90px; color: #606266; font-size: 13px; }
.quota-bar { flex: 1; }
.quota-unlimited { flex: 1; color: #909399; font-size: 13px; }
.quota-value { width: 160px; text-align: right; font-size: 13px; color: #303133; }
.readonly-tip { margin-top: 12px; }
.orders-card { margin-top: 16px; }
</style>
