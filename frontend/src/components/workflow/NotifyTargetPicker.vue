<template>
  <el-select :model-value="modelValue" multiple filterable size="small" style="width: 100%"
    placeholder="选择接收人（留空 = 发给工作流归属人）" :loading="loading"
    @update:model-value="$emit('update:modelValue', $event)">
    <el-option-group v-if="me" label="我">
      <el-option :label="`${me.username}（我自己）`" :value="`u:${me.id}`" />
    </el-option-group>
    <el-option-group v-if="friends.length" label="好友">
      <el-option v-for="f in friends" :key="`u:${f.user_id}`" :label="f.username" :value="`u:${f.user_id}`" />
    </el-option-group>
    <el-option-group v-if="groups.length" label="群组">
      <el-option v-for="g in groups" :key="`g:${g.id}`" :label="`${g.name}（${g.member_count} 人）`"
        :value="`g:${g.id}`" />
    </el-option-group>
    <!-- 兜底：已保存但好友/群组已被删除的目标，原样显示不丢值 -->
    <el-option-group v-if="unknowns.length" label="已失效">
      <el-option v-for="t in unknowns" :key="t" :label="`${t}（已失效）`" :value="t" />
    </el-option-group>
  </el-select>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { listFriends, listMyGroups } from '../../api'

// 站内通知接收人选择器：值是 ['u:用户id', 'g:群组id'] 字符串数组
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})
defineEmits(['update:modelValue'])

const loading = ref(true)
const friends = ref([])
const groups = ref([])

// 当前用户：「我自己」选项（值与好友一样是 u:<id>，后端无需特殊处理）
const me = computed(() => JSON.parse(localStorage.getItem('grt_user') || 'null'))

const known = computed(() => new Set([
  ...(me.value ? [`u:${me.value.id}`] : []),
  ...friends.value.map((f) => `u:${f.user_id}`),
  ...groups.value.map((g) => `g:${g.id}`),
]))
const unknowns = computed(() => (props.modelValue || []).filter((t) => !known.value.has(t)))

onMounted(async () => {
  try {
    ;[friends.value, groups.value] = await Promise.all([
      listFriends().catch(() => []),
      listMyGroups().catch(() => []),
    ])
  } finally {
    loading.value = false
  }
})
</script>
