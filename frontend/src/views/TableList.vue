<template>
  <div>
    <div class="page-header">
      <h2>数据表</h2>
      <el-button type="primary" :icon="Upload" @click="$router.push('/import')">导入 Excel 建表</el-button>
    </div>

    <el-empty v-if="!loading && tables.length === 0" description="还没有数据表，点击右上角导入 Excel 开始" />

    <el-row :gutter="16" v-loading="loading">
      <el-col v-for="t in tables" :key="t.id" :span="8" style="margin-bottom: 16px">
        <el-card shadow="hover">
          <div class="card-title">
            {{ t.label }}
            <el-tag v-if="t.storage_mode === 'physical'" size="small" type="warning" style="margin-left: 6px">独立表</el-tag>
            <el-tag v-if="!t.is_owner" size="small" style="margin-left: 6px">来自 {{ t.owner_label }} 的分享</el-tag>
          </div>
          <div class="card-sub">{{ t.name }} · {{ t.record_count }} 条记录</div>
          <div class="card-sub">创建于 {{ t.created_at }}</div>
          <div style="margin-top: 12px">
            <el-button type="primary" @click="$router.push(`/t/${t.id}`)">打开</el-button>
            <el-button v-if="canShare(t)" text type="primary" @click="openShare(t)">分享</el-button>
            <el-popconfirm v-if="t.is_owner || t.is_admin" title="将删除该表及全部数据，确定？" width="240" @confirm="del(t)">
              <template #reference>
                <el-button type="danger" text>删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 分享管理对话框 -->
    <el-dialog v-model="shareVisible" :title="`分享「${shareTable?.label}」`" width="680px">
      <el-tabs v-model="shareTab">
        <!-- 成员分享 -->
        <el-tab-pane label="成员分享" name="members">
          <el-form inline @submit.prevent>
            <el-form-item>
              <el-radio-group v-model="shareForm.target_type">
                <el-radio value="user">用户</el-radio>
                <el-radio value="group">用户组</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="shareForm.target_type === 'user'">
              <el-input v-model="shareForm.username" placeholder="对方用户名" style="width: 150px" />
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
          <el-table :data="shares" size="small" border>
            <el-table-column label="对象" width="160">
              <template #default="{ row }">
                {{ row.target }}
                <el-tag v-if="row.target_type === 'group'" size="small" type="warning" style="margin-left: 4px">组</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="查看" width="60" align="center"><template #default="{ row }">{{ row.can_view ? '✓' : '—' }}</template></el-table-column>
            <el-table-column label="新增" width="60" align="center"><template #default="{ row }">{{ row.can_create ? '✓' : '—' }}</template></el-table-column>
            <el-table-column label="编辑" width="60" align="center"><template #default="{ row }">{{ row.can_edit ? '✓' : '—' }}</template></el-table-column>
            <el-table-column label="删除" width="60" align="center"><template #default="{ row }">{{ row.can_delete ? '✓' : '—' }}</template></el-table-column>
            <el-table-column label="操作" align="center">
              <template #default="{ row }">
                <el-button text type="danger" size="small" @click="removeShare(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 链接分享 -->
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
          </el-table>
          <div v-if="!links.length" style="color: #c0c4cc; font-size: 13px; text-align: center; padding: 20px 0">
            还没有分享链接，生成后任何人凭链接可只读查看此表
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import {
  createShareLink, deleteShare, deleteShareLink, deleteTable, listGroups,
  listShareLinks, listShares, listTables, putShare,
} from '../api'

const tables = ref([])
const loading = ref(false)

const myRole = JSON.parse(localStorage.getItem('grt_user') || '{}').role

async function load() {
  loading.value = true
  try {
    tables.value = await listTables()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function canShare(t) {
  return (t.is_owner && ['vip', 'admin'].includes(myRole)) || t.is_admin
}

async function del(t) {
  try {
    await deleteTable(t.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 分享 ----------
const shareVisible = ref(false)
const shareTab = ref('members')
const shareTable = ref(null)
const shares = ref([])
const shareSaving = ref(false)
const groups = ref([])

// 角色预设：映射到 查看/新增/编辑/删除 四个开关
const ROLE_PRESETS = {
  viewer: { label: '查看者', perms: { can_view: true, can_create: false, can_edit: false, can_delete: false } },
  editor: { label: '编辑者', perms: { can_view: true, can_create: true, can_edit: true, can_delete: false } },
  manager: { label: '管理员', perms: { can_view: true, can_create: true, can_edit: true, can_delete: true } },
}

const shareForm = reactive({ target_type: 'user', username: '', group_id: null, preset: 'viewer' })

async function openShare(t) {
  shareTable.value = t
  shareVisible.value = true
  Object.assign(shareForm, { target_type: 'user', username: '', group_id: null, preset: 'viewer' })
  await Promise.all([loadShares(), loadGroups()])
  loadLinks()
}

async function loadShares() {
  try {
    shares.value = await listShares(shareTable.value.id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadGroups() {
  try {
    groups.value = await listGroups()
  } catch { /* 非 admin 看不到组列表时忽略 */ }
}

async function saveShare() {
  const payload = { ...ROLE_PRESETS[shareForm.preset].perms }
  if (shareForm.target_type === 'user') {
    if (!shareForm.username.trim()) return ElMessage.warning('请输入用户名')
    payload.username = shareForm.username.trim()
  } else {
    if (!shareForm.group_id) return ElMessage.warning('请选择用户组')
    payload.group_id = shareForm.group_id
  }
  shareSaving.value = true
  try {
    await putShare(shareTable.value.id, payload)
    ElMessage.success('已保存')
    shareForm.username = ''
    await loadShares()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    shareSaving.value = false
  }
}

async function removeShare(row) {
  try {
    await deleteShare(shareTable.value.id, row.id)
    ElMessage.success('已移除')
    await loadShares()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// ---------- 链接分享 ----------
const links = ref([])
const linkSaving = ref(false)
const linkForm = reactive({ password: '', expires_in_days: null })

function linkUrl(token) {
  return `${location.origin}/share/${token}`
}

async function loadLinks() {
  try {
    links.value = await listShareLinks(shareTable.value.id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function createLink() {
  linkSaving.value = true
  try {
    await createShareLink(shareTable.value.id, {
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
    await deleteShareLink(shareTable.value.id, row.id)
    ElMessage.success('已撤销')
    await loadLinks()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.card-title { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
.card-sub { font-size: 12px; color: #909399; margin-top: 4px; }
.link-url { font-size: 12px; color: #409eff; word-break: break-all; }
</style>
