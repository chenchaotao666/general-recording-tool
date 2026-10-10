<template>
  <div>
    <div class="page-header">
      <h2>升级套餐</h2>
      <el-button @click="$router.push('/billing')">返回套餐与用量</el-button>
    </div>

    <div v-loading="loading">
      <!-- 套餐卡片（个人版空间可看到两档：买企业版即自动升级空间类型） -->
      <template v-for="group in planGroups" :key="group.audience">
        <h3 v-if="planGroups.length > 1" class="audience-title">{{ group.title }}</h3>
        <el-row :gutter="16">
        <el-col v-for="p in group.plans" :key="p.code" :span="6">
          <el-card
            class="plan-card" :class="{ selected: selected?.code === p.code, current: p.code === currentPlanCode }"
            shadow="hover" @click="selectPlan(p)"
          >
            <div class="plan-name">{{ p.name }}
              <el-tag v-if="p.code === currentPlanCode" size="small" type="success">当前</el-tag>
            </div>
            <div class="plan-price">
              <template v-if="p.price_yearly">¥{{ fen(p.price_yearly) }}<span class="price-unit">/{{ p.audience === 'enterprise' ? '人/年' : '年' }}</span></template>
              <template v-else>免费</template>
            </div>
            <ul class="plan-ents">
              <li>{{ entText(p.entitlements.max_tables, '张数据表', '数据表不限') }}</li>
              <li>{{ entText(p.entitlements.max_rows, '条记录', '记录不限', true) }}</li>
              <li>{{ entText(p.entitlements.max_storage_mb, 'MB 存储', '存储不限') }}</li>
              <li v-if="p.audience === 'enterprise'">{{ entText(p.entitlements.max_seats, '席', '席位不限') }}</li>
              <li v-if="p.audience === 'enterprise' && isPersonal" class="upgrade-hint">✓ 购买即升级为企业空间</li>
              <li v-for="f in featureList(p.entitlements)" :key="f">✓ {{ f }}</li>
            </ul>
          </el-card>
        </el-col>
        </el-row>
      </template>

      <!-- 订单确认 -->
      <el-card v-if="selected" class="order-card">
        <template #header>确认订单</template>
        <el-form inline>
          <el-form-item v-if="selected.audience === 'enterprise'" label="席位数">
            <el-input-number v-model="seats" :min="selected.entitlements.min_seats || 1" :max="selected.entitlements.max_seats || 9999" />
            <span class="seat-hint">20–49 席 9 折，50 席以上 8 折</span>
          </el-form-item>
          <el-form-item label="购买时长">
            <el-select v-model="years" style="width: 120px">
              <el-option v-for="y in [1, 2, 3]" :key="y" :label="`${y} 年`" :value="y" />
            </el-select>
          </el-form-item>
          <el-form-item label="应付">
            <span class="amount">¥{{ fen(amount) }}</span>
            <span v-if="discount < 1" class="discount-tag">已含 {{ discount * 10 }} 折</span>
          </el-form-item>
        </el-form>
        <el-button type="primary" size="large" :loading="submitting" @click="submitOrder">
          提交订单并支付
        </el-button>
      </el-card>
    </div>

    <!-- 模拟支付 -->
    <el-dialog v-model="payVisible" title="收银台" width="400px" :close-on-click-modal="false" destroy-on-close>
      <div class="pay-box">
        <div class="pay-amount">¥{{ fen(order?.amount || 0) }}</div>
        <div class="pay-desc">{{ order?.plan_name }} × {{ order?.years }} 年<template v-if="order?.seats > 1"> × {{ order?.seats }} 席</template></div>
        <el-alert type="info" :closable="false" title="演示环境：点击「确认支付」直接成功（真实支付渠道接入点已预留）" />
      </div>
      <template #footer>
        <el-button @click="payVisible = false">取消</el-button>
        <el-button type="success" :loading="paying" @click="pay">确认支付</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { billingPlans, createOrder, payOrder } from '../api'

const router = useRouter()
const loading = ref(false)
const plans = ref([])
const currentPlanCode = ref('')
const isPersonal = ref(false)

const planGroups = computed(() => {
  const groups = []
  const ind = plans.value.filter((p) => p.audience === 'individual')
  const ent = plans.value.filter((p) => p.audience === 'enterprise')
  if (ind.length) groups.push({ audience: 'individual', title: '个人版', plans: ind })
  if (ent.length) groups.push({ audience: 'enterprise', title: '企业版（按人/年）', plans: ent })
  return groups
})

function selectPlan(p) {
  selected.value = p
  if (p.audience === 'enterprise') seats.value = Math.max(seats.value, p.entitlements.min_seats || 1)
}
const selected = ref(null)
const seats = ref(1)
const years = ref(1)
const submitting = ref(false)
const payVisible = ref(false)
const paying = ref(false)
const order = ref(null)

const fen = (v) => (v / 100).toFixed(v % 100 ? 2 : 0)
const entText = (v, unit, unlimitedText, big) => {
  if (v == null) return unlimitedText
  return (big && v >= 10000 ? (v / 10000) + ' 万' : v) + ' ' + unit
}
const FEATURE_LABELS = {
  feature_print_templates: '打印模板', feature_automation: '自动化', feature_api: 'API',
  feature_data_scope: '数据范围', feature_owd: '默认共享', feature_share_rules: '共享规则',
  feature_perm_diagnose: '权限诊断', feature_field_perm: '字段权限', feature_audit: '审计日志',
}
const featureList = (ents) => Object.keys(FEATURE_LABELS).filter((k) => ents[k]).map((k) => FEATURE_LABELS[k])

// 与后端 SEAT_DISCOUNT_TIERS 同口径（展示用，金额以后端订单为准）
const discount = computed(() => (seats.value >= 50 ? 0.8 : seats.value >= 20 ? 0.9 : 1))
const amount = computed(() => {
  if (!selected.value) return 0
  const yearly = selected.value.price_yearly || 0
  return selected.value.audience === 'enterprise'
    ? Math.round(yearly * seats.value * years.value * discount.value)
    : yearly * years.value
})

async function load() {
  loading.value = true
  try {
    const r = await billingPlans()
    plans.value = r.plans
    currentPlanCode.value = r.current_plan_code || ''
    isPersonal.value = r.tenant_type === 'personal'
    seats.value = 1
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function submitOrder() {
  if (!selected.value) return
  if (selected.value.code === currentPlanCode.value) return ElMessage.warning('已是当前套餐，如需续费请直接提交（时长将累加）')
  submitting.value = true
  try {
    order.value = await createOrder({
      plan_code: selected.value.code,
      seats: selected.value.audience === 'enterprise' ? seats.value : 1,
      years: years.value,
    })
    payVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function pay() {
  paying.value = true
  try {
    await payOrder(order.value.id)
    payVisible.value = false
    ElMessage.success('支付成功，套餐已生效')
    router.push('/billing')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    paying.value = false
  }
}
</script>

<style scoped>
.audience-title { margin: 18px 0 10px; font-size: 15px; color: #303133; }
.upgrade-hint { color: #67c23a; }
.plan-card { cursor: pointer; min-height: 250px; border: 2px solid transparent; }
.plan-card.selected { border-color: #409eff; }
.plan-card.current { border-color: #67c23a; }
.plan-name { font-size: 16px; font-weight: 600; display: flex; gap: 8px; align-items: center; }
.plan-price { font-size: 26px; font-weight: 700; color: #f56c6c; margin: 10px 0; }
.price-unit { font-size: 13px; font-weight: 400; color: #909399; }
.plan-ents { margin: 0; padding-left: 18px; color: #606266; font-size: 13px; line-height: 1.9; }
.order-card { margin-top: 16px; }
.amount { font-size: 22px; font-weight: 700; color: #f56c6c; }
.seat-hint { margin-left: 8px; color: #909399; font-size: 12px; }
.discount-tag { margin-left: 8px; color: #67c23a; font-size: 12px; }
.pay-box { text-align: center; }
.pay-amount { font-size: 32px; font-weight: 700; color: #f56c6c; margin-bottom: 8px; }
.pay-desc { color: #606266; margin-bottom: 16px; }
</style>
