<template>
  <el-dialog :model-value="modelValue" :title="titles[mode]" width="600px" destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)">
    <div v-loading="loading" class="enterprise-panel">
      <template v-if="mode === 'create'">
        <p class="intro">为团队建立独立的数据空间。你可以创建多个企业，也可以加入其他企业。</p>
        <div class="category-grid">
          <button v-for="item in categories" :key="item.name" type="button" class="category"
            :class="{ selected: form.category === item.name }" @click="form.category = item.name">
            <span>{{ item.icon }}</span><strong>{{ item.name }}</strong><small>{{ item.hint }}</small>
          </button>
        </div>
        <el-form label-position="top" @submit.prevent="create">
          <el-form-item label="企业名称" required><el-input v-model="form.name" maxlength="64" show-word-limit placeholder="例如：星河设计工作室" /></el-form-item>
          <div class="form-row">
            <el-form-item label="行业（选填）"><el-select v-model="form.industry" filterable allow-create default-first-option placeholder="选择或输入行业" clearable>
              <el-option v-for="item in industries" :key="item" :value="item" />
            </el-select></el-form-item>
            <el-form-item label="团队规模（选填）"><el-select v-model="form.size" placeholder="选择规模" clearable>
              <el-option v-for="item in sizes" :key="item" :value="item" />
            </el-select></el-form-item>
          </div>
        </el-form>
        <p class="hint">数据表由创建者和企业管理员管理，分享后同事即可协作。新企业使用轻企业免费版，具体配额可在“套餐与用量”查看。</p>
      </template>

      <template v-else-if="mode === 'join'">
        <p class="intro">输入企业创建者提供的邀请码，或接受下方的企业邀请。</p>
        <el-input v-model="code" placeholder="粘贴企业邀请码" maxlength="128" :disabled="busy" clearable @input="preview = null" @keyup.enter="checkCode" />
        <el-button class="check-button" :loading="busy" :disabled="!code.trim()" @click="checkCode">查看企业</el-button>
        <div v-if="preview" class="preview"><span class="enterprise-avatar">{{ preview.name[0] }}</span><div><strong>{{ preview.name }}</strong><p>{{ preview.category }} · 确认后加入此企业</p></div></div>
        <h4>收到的邀请</h4>
        <el-empty v-if="!invitations.length" description="暂无待处理的邀请" :image-size="56" />
        <div v-for="inv in invitations" :key="inv.id" class="invitation-row">
          <strong>{{ inv.tenant_name }}</strong>
          <div><el-button text :disabled="busy" @click="decline(inv)">忽略</el-button><el-button type="primary" plain :loading="busy" @click="accept(inv)">加入</el-button></div>
        </div>
      </template>

      <template v-else-if="info">
        <div class="enterprise-summary"><span class="enterprise-avatar">{{ info.name[0] }}</span><div><strong>{{ info.name }}</strong><p>{{ [info.category, info.industry, info.size].filter(Boolean).join(' · ') }}</p></div></div>
        <el-tabs v-model="detailTab">
          <el-tab-pane label="企业同事" name="members">
            <p class="hint">共 {{ info.members.length }} 人。在数据表的分享窗口中，可直接选择企业同事。</p>
            <el-input v-model="memberSearch" placeholder="搜索同事" clearable />
            <div class="member-list"><div v-for="member in filteredMembers" :key="member.id" class="member-row">
              <span class="member-avatar">{{ member.name[0] }}</span><span>{{ member.name }}</span><el-tag v-if="member.is_owner" size="small" effect="plain">创建者</el-tag>
            </div><el-empty v-if="!filteredMembers.length" description="没有匹配的同事" :image-size="50" /></div>
          </el-tab-pane>
          <el-tab-pane v-if="info.can_manage" label="邀请同事" name="invite">
            <p class="hint">将邀请码发给同事，对方登录后在“加入企业”中输入即可加入。邀请码 7 天有效，重新生成后旧码立即失效。</p>
            <el-button :loading="busy" @click="generateCode">{{ invitationCode ? '重新生成邀请码' : '生成邀请码' }}</el-button>
            <div v-if="invitationCode" class="code-box"><el-input :model-value="invitationCode.code" readonly /><el-button @click="copyCode">复制</el-button></div>
            <p v-if="invitationCode" class="hint">有效期至 {{ new Date(invitationCode.expires_at).toLocaleString() }}</p>
            <h4>按账号邀请</h4>
            <div class="code-box"><el-input v-model="username" placeholder="输入同事已注册的完整用户名" maxlength="64" @keyup.enter="invite" /><el-button type="primary" :loading="busy" :disabled="!username.trim()" @click="invite">发送邀请</el-button></div>
          </el-tab-pane>
          <el-tab-pane v-if="info.can_manage" label="企业信息" name="profile">
            <el-form label-position="top" @submit.prevent="save">
              <el-form-item label="企业名称"><el-input v-model="form.name" maxlength="64" /></el-form-item>
              <el-form-item label="类型"><el-select v-model="form.category"><el-option v-for="c in categories" :key="c.name" :value="c.name" /></el-select></el-form-item>
              <el-form-item label="行业"><el-input v-model="form.industry" maxlength="64" /></el-form-item>
              <el-form-item label="团队规模"><el-select v-model="form.size" clearable><el-option v-for="s in sizes" :key="s" :value="s" /></el-select></el-form-item>
              <el-button type="primary" :loading="busy" @click="save">保存企业信息</el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
      <el-button v-if="mode === 'create'" type="primary" :loading="busy" :disabled="!form.name.trim()" @click="create">创建并进入企业</el-button>
      <el-button v-if="mode === 'join' && preview" type="primary" :loading="busy" @click="join">确认加入 {{ preview.name }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createEnterprise, getEnterprise, updateEnterprise, createEnterpriseInvitation, previewEnterprise,
  joinEnterprise, listMyInvitations, acceptInvitation, declineInvitation, inviteMember, switchTenant } from '../api'

const props = defineProps({ modelValue: Boolean, mode: { type: String, default: 'create' } })
const emit = defineEmits(['update:modelValue', 'enter', 'updated'])
const titles = { create: '新建企业', join: '加入企业', current: '我的企业' }
const categories = [
  { name: '企业', icon: '▥', hint: '公司、工作室与团队' }, { name: '学校/教育局', icon: '▱', hint: '学校及教育组织' },
  { name: '政府', icon: '▤', hint: '政府与公共机构' }, { name: '其他', icon: '◇', hint: '社群及其他组织' },
]
const industries = ['互联网与软件', '制造业', '批发与零售', '专业服务', '医疗健康', '教育', '建筑与房地产', '文化传媒', '其他']
const sizes = ['1–10 人', '11–50 人', '51–100 人', '101–500 人', '500 人以上']
const form = reactive({ name: '', category: '企业', industry: '', size: '' })
const loading = ref(false), busy = ref(false), info = ref(null), code = ref(''), preview = ref(null)
const invitations = ref([]), invitationCode = ref(null), username = ref(''), memberSearch = ref(''), detailTab = ref('members')
const filteredMembers = computed(() => (info.value?.members || []).filter(m => m.name.toLowerCase().includes(memberSearch.value.toLowerCase())))
watch(() => [props.modelValue, props.mode], async ([open]) => {
  if (!open) return
  Object.assign(form, { name: '', category: '企业', industry: '', size: '' })
  code.value = ''; preview.value = null; invitationCode.value = null; info.value = null
  username.value = ''; memberSearch.value = ''; detailTab.value = 'members'; invitations.value = []
  loading.value = true
  try {
    if (props.mode === 'join') invitations.value = await listMyInvitations()
    if (props.mode === 'current') {
      info.value = await getEnterprise()
      Object.assign(form, { name: info.value.name, category: info.value.category, industry: info.value.industry, size: info.value.size })
    }
  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }
})
async function run(action) {
  if (busy.value) return
  busy.value = true
  try { await action() } catch (e) { ElMessage.error(e.message) } finally { busy.value = false }
}
const create = () => run(async () => emit('enter', await createEnterprise({ ...form, name: form.name.trim() })))
const checkCode = () => run(async () => { preview.value = null; preview.value = await previewEnterprise(code.value.trim()) })
const join = () => run(async () => emit('enter', await joinEnterprise(code.value.trim())))
const accept = inv => run(async () => { await acceptInvitation(inv.id); emit('enter', await switchTenant(inv.tenant_id)) })
const decline = inv => run(async () => { await declineInvitation(inv.id); invitations.value = invitations.value.filter(i => i.id !== inv.id) })
const generateCode = () => run(async () => { invitationCode.value = await createEnterpriseInvitation() })
const invite = () => run(async () => { await inviteMember(username.value.trim()); username.value = ''; ElMessage.success('邀请已发送，对方可在“加入企业”中接受') })
const save = () => run(async () => { info.value = await updateEnterprise({ ...form, name: form.name.trim() }); emit('updated', info.value); ElMessage.success('企业信息已保存') })
async function copyCode() {
  try { await navigator.clipboard.writeText(invitationCode.value.code); ElMessage.success('邀请码已复制') }
  catch { ElMessage.info('请选中邀请码手动复制') }
}
</script>

<style scoped>
.intro { color: #606b7b; margin: 0 0 22px; line-height: 1.7; }
.hint { color: #8490a2; font-size: 13px; line-height: 1.7; }
.category-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; }
.category { text-align: left; display: grid; grid-template-columns: 32px 1fr; gap: 5px 8px; background: #f8fafc; border: 1px solid #e6eaf0; border-radius: 10px; padding: 16px; cursor: pointer; color: #364152; }
.category.selected { border-color: #409eff; background: #edf6ff; }
.category span { grid-row: span 2; color: #409eff; font-size: 26px; }
.category small { color: #8490a2; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-row .el-select { width: 100%; }
.check-button { margin-top: 12px; }
.enterprise-summary, .preview { display: flex; gap: 14px; align-items: center; padding: 16px 0 22px; }
.preview { margin-top: 18px; }
.enterprise-avatar { width: 46px; height: 46px; display: grid; place-items: center; background: #eaf3ff; color: #409eff; border-radius: 12px; font-size: 22px; }
.enterprise-summary strong { font-size: 19px; }
.enterprise-summary p, .preview p { margin: 6px 0 0; color: #8490a2; font-size: 13px; }
.invitation-row, .member-row { display: flex; align-items: center; gap: 12px; padding: 13px 0; border-bottom: 1px solid #f0f2f5; }
.invitation-row { justify-content: space-between; }
.member-list { max-height: 280px; overflow: auto; }
.member-avatar { width: 30px; height: 30px; display: grid; place-items: center; background: #f0f5fc; color: #6084ae; border-radius: 8px; }
.code-box { display: flex; gap: 8px; margin-top: 16px; }
@media (max-width: 600px) { .category-grid, .form-row { grid-template-columns: 1fr; } }
</style>
