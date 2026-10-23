<template>
  <!-- 列级精简版「记录变更提醒」（§11.3 入口 1，对齐参照 表头-记录变更提醒.png）：
       当 [字段 ▾] 有变更时 → 发送消息通知给 [成员]；「更多配置 ›」进入完整版编辑器 -->
  <el-dialog :model-value="visible" width="420px" class="st-qr-dlg" :show-close="false" append-to-body
             @update:model-value="emit('close')">
    <template #header><div class="qr-title">记录变更提醒</div></template>
    <div class="qr-steps">
      <div class="qr-line">
        <span class="qr-dot" />
        <span>当</span>
        <TbFieldSelect v-model="fieldName" :fields="fields" class="qr-field" />
        <span>有变更时</span>
      </div>
      <div class="qr-line">
        <span class="qr-dot" />
        <span>发送</span>
        <span>通知消息</span>
        <span>给</span>
      </div>
      <div class="qr-to">
        <el-select collapse-tags collapse-tags-tooltip v-model="to" multiple filterable class="st-control qr-members" placeholder="选择成员" :teleported="true">
          <el-option v-for="m in members" :key="m.id" :value="m.id" :label="m.name" />
        </el-select>
      </div>
    </div>
    <template #footer>
      <div class="qr-foot">
        <a class="qr-more" @click="more">更多配置<StIcon name="chevron-right" :size="12" /></a>
        <el-button type="primary" class="st-button st-button--large st-button--primary qr-btn" :loading="saving" @click="save">确定</el-button>
        <el-button class="st-button st-button--large qr-btn qr-cancel" @click="emit('close')">取消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { fieldIconName } from '../../../smart/registry/fieldIcons.js'
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import TbFieldSelect from '../panels/TbFieldSelect.vue'
import { smartCreateAutomation } from '../../../api/index.js'

const props = defineProps({
  visible: Boolean,
  tableId: Number,
  field: { type: Object, default: null },      // 默认监听当前列（可下拉改选）
  fields: { type: Array, default: () => [] },
  members: { type: Array, default: () => [] },
  me: { type: Number, default: null },
})
const emit = defineEmits(['close', 'more', 'saved'])

const fieldName = ref(null)
const to = ref([])
const saving = ref(false)
const field = computed(() => props.fields.find(f => f.field_name === fieldName.value))

watch(() => props.visible, (v) => {
  if (!v) return
  fieldName.value = props.field?.field_name || props.fields[0]?.field_name
  to.value = props.me ? [props.me] : []
})

function buildRule() {
  const f = field.value
  const primary = props.fields[0]
  const content = [
    { t: 'var', var: { kind: 'step', step: 1, key: 'operator' }, label: '第1步修改记录的 操作人' },
    { t: 'text', v: ' 修改了「' },
    ...(primary && primary.field_name !== f?.field_name
      ? [{ t: 'var', var: { kind: 'step', step: 1, key: 'field', field: primary.field_name }, label: `第1步修改记录的 ${primary.label}` }, { t: 'text', v: '」的' }]
      : [{ t: 'text', v: '记录」的' }]),
    { t: 'text', v: `「${f?.label || ''}」为：` },
    { t: 'var', var: { kind: 'step', step: 1, key: 'field', field: f?.field_name }, label: `第1步修改记录的 ${f?.label || ''}` },
  ]
  return {
    name: `「${f?.label || ''}」变更提醒`, enabled: true,
    trigger: { type: 'recordUpdated', watchFields: f ? [f.field_name] : [], filter: { match: 'all', conditions: [] } },
    actions: [{ id: `a${Date.now().toString(36)}`, type: 'sendMessage', channel: 'docMessage', to: to.value, toFields: [],
                webhookUrl: '', title: '记录修改提醒', content, buttons: [{ label: '查看记录' }] }],
  }
}

async function save() {
  if (!to.value.length) { ElMessage.warning('请选择接收消息的成员'); return }
  saving.value = true
  try {
    const rule = buildRule()
    await smartCreateAutomation(props.tableId, rule)
    ElMessage.success('已设置变更提醒')
    emit('saved')
    emit('close')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
function more() { emit('more', buildRule()); emit('close') }
</script>

<style scoped>
.qr-title { font-size: var(--st-font-size-title); font-weight: 600; }
.qr-steps { position: relative; padding-left: 4px; }
.qr-steps::before { content: ''; position: absolute; left: 8px; top: 18px; height: 38px; border-left: 1px solid var(--st-border); }
.qr-line { display: flex; align-items: center; gap: 8px; font-size: var(--st-font-size); color: var(--st-text-2); margin-bottom: 14px; }
.qr-dot { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--st-text-4); background: #fff; position: relative; z-index: 1; }
.qr-field { width: 170px; }
.qr-link { color: var(--st-primary); cursor: pointer; display: inline-flex; align-items: center; gap: 2px; }
.qr-to { padding-left: 17px; }
.qr-members { width: 100%; }
.qr-foot { display: flex; align-items: center; gap: 10px; }
.qr-more { margin-right: auto; color: var(--st-text-2); font-size: var(--st-font-size); cursor: pointer; display: inline-flex; align-items: center; gap: 2px; }
.qr-btn { width: 92px; }
.qr-cancel { background: #EEEFF1; border-color: #EEEFF1; }
</style>
