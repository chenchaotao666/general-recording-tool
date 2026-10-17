<template>
  <!-- 指定成员设置（§13.2 两步创建流第 1 步）：选择成员 + 备注名（可自由填写或从内置词典选择）
       对齐参照 内容权限-指定成员设置.png / 内容权限-指定成员.png -->
  <el-dialog :model-value="visible" width="540px" class="st-perm-dlg st-mg-dlg" :show-close="false" append-to-body
             @update:model-value="emit('close')">
    <template #header>
      <div class="mg-head">
        <span class="mg-title">指定成员设置<span class="st-free-tag">限时免费</span></span>
        <span class="mg-x" @click="emit('close')"><StIcon name="close" :size="18" /></span>
      </div>
    </template>
    <div class="mg-card">
      <div class="mg-t">指定成员</div>
      <div class="mg-d">指定成员可设置额外的内容权限</div>
      <div v-if="memberIds.length" class="mg-list">
        <div v-for="m in chosen" :key="m.id" class="mg-member">
          <span class="mg-av">{{ m.name[0] }}</span><span class="mg-name">{{ m.name }}</span>
          <span class="mg-rm" title="移除" @click="memberIds = memberIds.filter(x => x !== m.id)"><StIcon name="minus-circle" :size="16" /></span>
        </div>
      </div>
      <el-select v-if="picking || !memberIds.length" ref="pickRef" v-model="memberIds" multiple filterable
                 :teleported="false" class="mg-pick" placeholder="搜索成员" collapse-tags collapse-tags-tooltip>
        <el-option v-for="m in members" :key="m.id" :value="m.id" :label="m.name" />
      </el-select>
      <button v-if="!memberIds.length" class="mg-choose" @click="openPick">选择指定成员</button>
      <a v-else class="mg-add" @click="openPick"><StIcon name="plus" :size="13" />添加指定成员</a>
    </div>
    <div class="mg-card">
      <div class="mg-t">备注</div>
      <div class="mg-d">为指定成员添加名称，如“负责人”、“跟进人”等。指定成员也能看到这个名称。</div>
      <el-select v-model="name" filterable allow-create default-first-option :teleported="false" class="mg-remark"
                 placeholder="填写或选择备注" :reserve-keyword="false">
        <el-option-group v-for="c in dictionary" :key="c.category" :label="c.category">
          <el-option v-for="it in c.items" :key="`${c.category}-${it}`" :value="it" :label="it" />
        </el-option-group>
      </el-select>
    </div>
    <template #footer>
      <div class="mg-foot">
        <el-button type="primary" class="mg-btn" :loading="saving" @click="submit">{{ group ? '保存' : '继续添加权限' }}</el-button>
        <el-button class="mg-btn mg-cancel" @click="emit('close')">取消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import { smartCreatePermGroup, smartPermDictionary, smartUpdatePermGroup } from '../../../api/index.js'

const props = defineProps({
  visible: Boolean,
  docId: Number,
  members: { type: Array, default: () => [] },   // [{id, name}]
  group: { type: Object, default: null },        // 编辑已有组
})
const emit = defineEmits(['close', 'saved'])

const memberIds = ref([])
const name = ref('')
const picking = ref(false)
const pickRef = ref(null)
const saving = ref(false)
const dictionary = ref([])
const chosen = computed(() => memberIds.value.map(id => props.members.find(m => m.id === id) || { id, name: `#${id}` }))

watch(() => props.visible, async (v) => {
  if (!v) return
  memberIds.value = [...(props.group?.member_ids || [])]
  name.value = props.group?.name || ''
  picking.value = false
  if (!dictionary.value.length) dictionary.value = (await smartPermDictionary().catch(() => ({ categories: [] }))).categories
}, { immediate: true })

async function openPick() {
  picking.value = true
  await nextTick()
  pickRef.value?.toggleMenu?.()
  pickRef.value?.focus?.()
}

async function submit() {
  if (!memberIds.value.length) { ElMessage.warning('请选择指定成员'); return }
  if (!String(name.value || '').trim()) { ElMessage.warning('请填写或选择备注'); return }
  saving.value = true
  try {
    const payload = { name: String(name.value).trim(), member_ids: memberIds.value }
    const r = props.group ? await smartUpdatePermGroup(props.group.id, payload) : await smartCreatePermGroup(props.docId, payload)
    emit('saved', r.group, !props.group)
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.mg-head { display: flex; justify-content: space-between; align-items: center; }
.mg-title { font-size: 20px; font-weight: 700; display: inline-flex; align-items: center; }
.mg-x { cursor: pointer; display: inline-flex; }
.mg-card { background: #fff; border-radius: 10px; padding: 18px 22px; margin: 0 28px 14px; }
.mg-t { font-size: 17px; font-weight: 700; color: var(--st-text-1); }
.mg-d { font-size: 13px; color: var(--st-text-2); margin: 4px 0 14px; }
.mg-choose { width: 100%; height: 40px; border: none; border-radius: 8px; background: #F1F2F3; font-size: 15px; cursor: pointer; color: var(--st-text-1); }
.mg-choose:hover { background: #E8E9EB; }
.mg-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.mg-member { display: flex; align-items: center; gap: 10px; padding: 6px 4px; }
.mg-av { width: 26px; height: 26px; border-radius: 50%; background: #F6903D; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; }
.mg-name { flex: 1; font-size: 14px; }
.mg-rm { color: var(--st-text-4); cursor: pointer; display: inline-flex; }
.mg-rm:hover { color: var(--el-color-danger); }
.mg-pick, .mg-remark { width: 100%; }
.mg-pick { margin-bottom: 8px; }
.mg-add { display: inline-flex; align-items: center; gap: 4px; color: var(--st-primary); cursor: pointer; font-size: 14px; }
.mg-foot { display: flex; gap: 16px; padding: 0 8px; }
.mg-btn { flex: 1; height: 44px; font-size: 16px; }
.mg-cancel { background: #EEEFF1; border-color: #EEEFF1; }
</style>
<style>
.st-mg-dlg .el-dialog__footer { border-top: none; padding-top: 4px; }
</style>
