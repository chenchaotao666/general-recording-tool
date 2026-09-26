<template>
  <div class="approve-page" v-loading="loading">
    <el-card v-if="info" class="approve-card">
      <div class="wf-name">工作流：{{ info.workflow_name }}</div>
      <h2 class="title">{{ info.title }}</h2>
      <div v-if="info.detail" class="detail">{{ info.detail }}</div>
      <div class="time">发起时间：{{ info.created_at }}</div>

      <template v-if="info.status === 'waiting' && !done">
        <el-input v-model="comment" type="textarea" :rows="3" placeholder="审批意见（可选）" class="mb" />
        <el-alert v-if="error" :title="error" type="error" :closable="false" class="mb" />
        <div class="actions">
          <el-button type="success" size="large" :loading="acting" @click="act(true)">通 过</el-button>
          <el-button type="danger" size="large" plain :loading="acting" @click="act(false)">驳 回</el-button>
        </div>
      </template>
      <el-result
        v-else :icon="resultIcon" :title="resultTitle"
        :sub-title="info.comment ? `审批意见：${info.comment}` : undefined"
      />
    </el-card>
    <el-result v-else-if="error" icon="error" title="链接无效" :sub-title="error" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getPublicApproval, submitPublicApproval } from '../api'

const route = useRoute()
const token = route.params.token

const loading = ref(true)
const acting = ref(false)
const done = ref(false)
const info = ref(null)
const comment = ref('')
const error = ref('')

const resultIcon = computed(() => (info.value?.approved === false ? 'error' : 'success'))
const resultTitle = computed(() => {
  if (done.value) return info.value.approved ? '已通过，流程继续执行' : '已驳回'
  return info.value?.approved ? '该审批已通过' : '该审批已驳回'
})

async function act(approved) {
  acting.value = true
  error.value = ''
  try {
    await submitPublicApproval(token, approved, comment.value)
    info.value = { ...info.value, approved, comment: comment.value, status: 'success' }
    done.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    acting.value = false
  }
}

onMounted(async () => {
  try {
    info.value = await getPublicApproval(token)
    document.title = info.value.title
  } catch (e) {
    error.value = '审批链接无效或已过期'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.approve-page {
  min-height: 100vh; background: #f5f7fa; padding: 24px 16px;
  display: flex; justify-content: center; align-items: flex-start;
}
.approve-card { width: 100%; max-width: 560px; }
.wf-name { font-size: 12px; color: #909399; margin-bottom: 6px; }
.title { margin: 0 0 10px; font-size: 19px; color: #303133; }
.detail { font-size: 14px; color: #606266; white-space: pre-wrap; margin-bottom: 10px; }
.time { font-size: 12px; color: #c0c4cc; margin-bottom: 16px; }
.mb { margin-bottom: 12px; }
.actions { display: flex; gap: 12px; }
.actions .el-button { flex: 1; }
</style>
