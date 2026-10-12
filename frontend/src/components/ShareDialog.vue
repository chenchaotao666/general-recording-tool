<template>
  <!-- 通用分享对话框：数据表/思维导图共用（成员分享目前仅数据表支持，导图先用链接分享） -->
  <el-dialog
    :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
    :title="`分享「${resourceName}」`" width="680px" destroy-on-close
  >
    <el-tabs v-model="tab">
      <!-- 成员分享：数据表四开关；思维导图 查看/编辑 两开关 -->
      <el-tab-pane label="成员分享" name="members">
        <el-form inline @submit.prevent>
          <el-form-item>
            <el-radio-group v-model="shareForm.target_type">
              <el-radio value="user">用户</el-radio>
              <el-radio value="group">用户组</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="shareForm.target_type === 'user'">
            <el-select
              v-model="shareForm.user_id" filterable remote :remote-method="searchShareable"
              :loading="searching" placeholder="搜索好友/同组用户" style="width: 200px"
            >
              <el-option v-for="u in userOptions" :key="u.id" :label="u.username" :value="u.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-else>
            <el-select v-model="shareForm.group_id" placeholder="选择用户组" style="width: 150px">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-select v-model="shareForm.preset" style="width: 140px">
              <el-option v-for="(p, k) in ROLE_PRESETS" :key="k" :label="p.label" :value="k" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="shareSaving" @click="saveShare">添加/更新</el-button>
          </el-form-item>
        </el-form>
        <div style="color: #909399; font-size: 12px; margin-bottom: 10px">
          只能分享给好友或同组用户（左侧「好友」页可添加好友）；直发分享需对方接受后生效
        </div>
        <el-table :data="shares" size="small" border>
          <el-table-column label="对象" width="160">
            <template #default="{ row }">
              {{ row.target }}
              <el-tag v-if="row.target_type === 'group'" size="small" type="warning" style="margin-left: 4px">组</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.status === 'pending'" size="small" type="warning">待确认</el-tag>
              <el-tag v-else-if="row.status === 'rejected'" size="small" type="danger">已拒绝</el-tag>
              <span v-else style="color: #909399">已生效</span>
            </template>
          </el-table-column>
          <el-table-column label="查看" width="60" align="center"><template #default="{ row }">{{ row.can_view ? '✓' : '—' }}</template></el-table-column>
          <el-table-column v-if="resourceType === 'table'" label="新增" width="60" align="center"><template #default="{ row }">{{ row.can_create ? '✓' : '—' }}</template></el-table-column>
          <el-table-column label="编辑" width="60" align="center"><template #default="{ row }">{{ row.can_edit ? '✓' : '—' }}</template></el-table-column>
          <el-table-column v-if="resourceType === 'table'" label="删除" width="60" align="center"><template #default="{ row }">{{ row.can_delete ? '✓' : '—' }}</template></el-table-column>
          <el-table-column label="操作" align="center">
            <template #default="{ row }">
              <el-button v-if="row.status === 'rejected'" text type="primary" size="small" @click="reShare(row)">重新发起</el-button>
              <el-button text type="danger" size="small" @click="removeShare(row)">移除</el-button>
            </template>
          </el-table-column>
          <template #empty><el-empty description="还没有分享给任何人" :image-size="60" /></template>
        </el-table>
      </el-tab-pane>

      <!-- 链接分享（全资源通用） -->
      <el-tab-pane label="链接分享" name="links">
        <el-form inline @submit.prevent>
          <el-form-item>
            <el-input v-model="linkForm.password" placeholder="访问密码（可选）" style="width: 160px" show-password />
          </el-form-item>
          <el-form-item>
            <el-input-number v-model="linkForm.expires_in_days" :min="1" :max="365" placeholder="有效期" style="width: 130px" />
            <span style="margin-left: 6px; color: #909399">天（留空永久）</span>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="linkSaving" @click="createLink">生成链接</el-button>
          </el-form-item>
        </el-form>
        <el-table :data="links" size="small" border>
          <el-table-column label="链接" min-width="280">
            <template #default="{ row }">
              <span class="link-url">{{ linkUrl(row.token) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="密码" width="70" align="center">
            <template #default="{ row }">{{ row.has_password ? '有' : '—' }}</template>
          </el-table-column>
          <el-table-column label="有效期至" width="150">
            <template #default="{ row }">{{ row.expires_at || '永久' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="center">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="copyLink(row)">复制</el-button>
              <el-button text type="danger" size="small" @click="removeLink(row)">撤销</el-button>
            </template>
          </el-table-column>
          <template #empty><el-empty description="还没有分享链接，生成后任何人凭链接可只读查看" :image-size="60" /></template>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createResShareLink, deleteMindmapShare, deleteResShareLink, deleteShare, listMindmapShares,
  listMyGroups, listResShareLinks, listShares, putMindmapShare, putShare, searchUsers,
} from '../api'

const props = defineProps({
  modelValue: Boolean,
  resourceType: { type: String, required: true },   // table | mindmap
  resourceId: { type: Number, default: null },
  resourceName: { type: String, default: '' },
})
defineEmits(['update:modelValue'])

// 预设与 API 按资源类型分流（成员分享：表/导图各自后端，UI 同一套）
const ROLE_PRESETS = computed(() => props.resourceType === 'mindmap' ? MINDMAP_PRESETS : TABLE_PRESETS)
const shareApi = computed(() => props.resourceType === 'mindmap'
  ? { list: listMindmapShares, put: putMindmapShare, del: deleteMindmapShare }
  : { list: listShares, put: putShare, del: deleteShare })

// 角色预设：数据表映射 查看/新增/编辑/删除 四开关；思维导图只有 查看/编辑
const TABLE_PRESETS = {
  viewer: { label: '查看者', perms: { can_view: true, can_create: false, can_edit: false, can_delete: false } },
  editor: { label: '编辑者', perms: { can_view: true, can_create: true, can_edit: true, can_delete: false } },
  manager: { label: '管理员', perms: { can_view: true, can_create: true, can_edit: true, can_delete: true } },
}
const MINDMAP_PRESETS = {
  viewer: { label: '查看者', perms: { can_view: true, can_edit: false } },
  editor: { label: '编辑者', perms: { can_view: true, can_edit: true } },
}

const tab = ref('links')
const shares = ref([])
const shareSaving = ref(false)
const groups = ref([])
const shareForm = reactive({ target_type: 'user', user_id: null, group_id: null, preset: 'viewer' })
const userOptions = ref([])
const searching = ref(false)
const links = ref([])
const linkSaving = ref(false)
const linkForm = reactive({ password: '', expires_in_days: null })

// 打开时加载（导图的成员分享 tab 不存在，默认停在链接分享）
watch(() => props.modelValue, async (v) => {
  if (!v) return
  tab.value = 'members'
  Object.assign(shareForm, { target_type: 'user', user_id: null, group_id: null, preset: 'viewer' })
  await Promise.all([loadShares(), loadGroups(), searchShareable('')])
  loadLinks()
})

// ---------- 成员分享（数据表） ----------
async function searchShareable(q) {
  searching.value = true
  try {
    userOptions.value = await searchUsers(q, 'shareable')
  } catch {
    userOptions.value = []
  } finally {
    searching.value = false
  }
}

async function loadShares() {
  try {
    shares.value = await shareApi.value.list(props.resourceId)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadGroups() {
  try {
    groups.value = await listMyGroups()
  } catch { /* 不在任何组时为空列表 */ }
}

async function saveShare() {
  const payload = { ...ROLE_PRESETS.value[shareForm.preset].perms }
  if (shareForm.target_type === 'user') {
    if (!shareForm.user_id) return ElMessage.warning('请选择用户')
    payload.user_id = shareForm.user_id
  } else {
    if (!shareForm.group_id) return ElMessage.warning('请选择用户组')
    payload.group_id = shareForm.group_id
  }
  shareSaving.value = true
  try {
    await shareApi.value.put(props.resourceId, payload)
    ElMessage.success('已保存')
    shareForm.user_id = null
    await loadShares()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    shareSaving.value = false
  }
}

async function reShare(row) {
  try {
    const perms = props.resourceType === 'mindmap'
      ? { can_view: row.can_view, can_edit: row.can_edit }
      : { can_view: row.can_view, can_create: row.can_create, can_edit: row.can_edit, can_delete: row.can_delete }
    await shareApi.value.put(props.resourceId, { username: row.target, ...perms })
    ElMessage.success('已重新发起')
    await loadShares()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function removeShare(row) {
  try {
    await shareApi.value.del(props.resourceId, row.id)
    ElMessage.success('已移除')
    await loadShares()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 链接分享 ----------
function linkUrl(token) {
  return `${location.origin}/share/${token}`
}

async function loadLinks() {
  try {
    links.value = await listResShareLinks(props.resourceType, props.resourceId)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function createLink() {
  linkSaving.value = true
  try {
    await createResShareLink(props.resourceType, props.resourceId, {
      password: linkForm.password || null,
      expires_in_days: linkForm.expires_in_days || null,
    })
    ElMessage.success('链接已生成')
    linkForm.password = ''
    linkForm.expires_in_days = null
    await loadLinks()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    linkSaving.value = false
  }
}

async function copyLink(row) {
  try {
    await navigator.clipboard.writeText(linkUrl(row.token))
    ElMessage.success('链接已复制')
  } catch {
    ElMessage.info(linkUrl(row.token))
  }
}

async function removeLink(row) {
  try {
    await deleteResShareLink(props.resourceType, props.resourceId, row.id)
    ElMessage.success('已撤销')
    await loadLinks()
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>

<style scoped>
.link-url { font-size: 12px; color: #606266; word-break: break-all; }
</style>
