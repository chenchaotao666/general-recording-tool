<template>
  <!-- AI 生成公式（§9 与公式编辑器打通 / 场景市场「写公式」）：自然语言 → 公式表达式（服务端校验语法与字段） -->
  <el-dialog :model-value="visible" title="AI 写公式" width="560px" append-to-body class="st-ai-dlg" @update:model-value="emit('close')">
    <div class="afd">
      <div class="afd-l">用一句话描述你想计算什么</div>
      <el-input v-model="prompt" type="textarea" :rows="3" placeholder="例如：单价乘以数量，再打九折；如果状态是已完成则显示“完成”否则显示“进行中”"
                @keydown.ctrl.enter="generate" />
      <div class="afd-fields">
        <span v-for="f in fields.slice(0, 16)" :key="f.field_name" class="afd-f" @click="prompt += f.label">{{ f.label }}</span>
      </div>
      <el-button type="primary" class="afd-gen" :loading="loading" :disabled="!prompt.trim()" @click="generate">
        <StIcon name="sparkle" :size="14" />生成公式
      </el-button>
      <div v-if="result" class="afd-result">
        <div class="afd-l">生成结果</div>
        <code class="afd-code">{{ result.display }}</code>
        <div class="afd-exp">{{ result.explanation }}（返回{{ result.returnType === 'number' ? '数字' : '文本' }}）</div>
        <el-input v-if="withName" v-model="name" size="small" placeholder="字段名称" />
      </div>
    </div>
    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :disabled="!result" @click="apply">使用此公式</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import { smartAiGenerateFormula } from '../../../api/index.js'

const props = defineProps({
  visible: Boolean,
  tableId: Number,
  fields: { type: Array, default: () => [] },
  withName: { type: Boolean, default: false },   // 从场景市场进入：同时命名新公式列
})
const emit = defineEmits(['close', 'apply'])
const prompt = ref('')
const loading = ref(false)
const result = ref(null)
const name = ref('公式')
watch(() => props.visible, (v) => { if (v) { prompt.value = ''; result.value = null; name.value = '公式' } })

async function generate() {
  loading.value = true
  try {
    result.value = await smartAiGenerateFormula(props.tableId, prompt.value.trim())
  } catch (e) {
    ElMessage.error(e.message || '生成失败')
  } finally {
    loading.value = false
  }
}
function apply() { emit('apply', { ...result.value, label: name.value || '公式' }) }
</script>

<style scoped>
.afd { display: flex; flex-direction: column; gap: 10px; }
.afd-l { font-size: 13px; color: var(--st-text-2); }
.afd-fields { display: flex; flex-wrap: wrap; gap: 4px; }
.afd-f { font-size: 12px; background: #F2F3F5; border-radius: 4px; padding: 1px 6px; cursor: pointer; }
.afd-f:hover { background: var(--st-primary-weak); color: var(--st-primary); }
.afd-gen { align-self: flex-start; gap: 4px; background: linear-gradient(135deg, #7F3FF1, #4C8DFF); border: none; }
.afd-gen .st-icon { margin-right: 4px; }
.afd-result { background: #F7F8FA; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.afd-code { font-family: Consolas, monospace; background: #fff; border: 1px solid var(--st-border); border-radius: 4px; padding: 8px 10px; font-size: 14px; word-break: break-all; }
.afd-exp { font-size: 13px; color: var(--st-text-2); }
</style>
