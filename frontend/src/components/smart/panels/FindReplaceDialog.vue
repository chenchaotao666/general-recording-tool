<template>
  <!-- 查找替换（设计文档 §7.5）：查找定位 → 替换/全部替换 -->
  <el-dialog :model-value="visible" title="查找替换" width="420px" @update:model-value="$emit('close')">
    <div class="fr">
      <el-input v-model="find" placeholder="输入查找内容" clearable @input="searched = false" />
      <el-input v-model="replace" placeholder="替换为" clearable />
      <div class="ops">
        <el-button type="primary" :disabled="!find" @click="doFind">查找</el-button>
        <el-button :disabled="!searched || !matches.length" @click="doReplace">全部替换</el-button>
      </div>
      <div v-if="searched" class="result">
        <div class="cnt">找到 {{ matches.length }} 处</div>
        <div v-for="(m, i) in matches.slice(0, 50)" :key="i" class="m-row">
          <span class="m-field">{{ m.fieldLabel }}</span>
          <span class="m-val">{{ m.value }}</span>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { smartSearchReplace } from '../../../api/index.js'

const props = defineProps({ visible: Boolean, tableId: Number })
const emit = defineEmits(['close', 'replaced'])

const find = ref('')
const replace = ref('')
const matches = ref([])
const searched = ref(false)

async function doFind() {
  const res = await smartSearchReplace(props.tableId, { find: find.value })
  matches.value = res.matches
  searched.value = true
}
async function doReplace() {
  const res = await smartSearchReplace(props.tableId, { find: find.value, replace: replace.value, replace_all: true })
  ElMessage.success(`已替换 ${res.replaced} 条记录`)
  emit('replaced')
  emit('close')
}
</script>

<style scoped>
.fr { display: flex; flex-direction: column; gap: 10px; }
.ops { display: flex; gap: 8px; }
.result { max-height: 240px; overflow: auto; border-top: 1px solid var(--el-border-color-lighter); padding-top: 8px; }
.cnt { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.m-row { display: flex; gap: 8px; font-size: 12px; padding: 2px 0; }
.m-field { color: var(--el-color-primary); min-width: 80px; }
.m-val { color: var(--el-text-color-regular); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
