<template>
  <div>
    <div class="page-header">
      <h2>角色管理</h2>
      <el-tooltip v-if="createDisabled" content="当前套餐不含自定义角色功能，升级企业版后可用" placement="bottom">
        <span><el-button type="primary" :icon="Plus" disabled>新建角色</el-button></span>
      </el-tooltip>
      <el-button v-else type="primary" :icon="Plus" @click="openCreate">新建角色</el-button>
    </div>
    <el-alert
      v-if="!isPlatformAdmin" type="info" :closable="false" style="margin-bottom: 12px"
      title="对全局内置角色的修改只影响本工作空间（租户级覆盖）；自定义角色为本空间独有。数据表权限管「能不能操作」，数据范围管「能看哪些记录」，两层叠加生效。" />

    <div class="role-layout">
      <!-- 左：角色列表 -->
      <div class="role-list">
        <div
          v-for="r in roles" :key="r.id" class="role-item"
          :class="{ active: selected?.id === r.id }" @click="select(r)"
        >
          <span class="role-name">{{ r.name }}</span>
          <el-tag v-if="!r.tenant_id" size="small" type="info">内置</el-tag>
          <el-tag v-else-if="r.tenant_id === currentTenantId" size="small" type="success">本空间</el-tag>
          <el-tag v-else size="small" type="warning">{{ r.tenant_name || `租户#${r.tenant_id}` }}</el-tag>
          <span v-if="r.code === 'admin'" class="role-code">{{ r.code }}</span>
        </div>
        <el-empty v-if="!roles.length && !loading" description="暂无角色" :image-size="60" />
      </div>

      <!-- 右：权限配置 -->
      <div v-if="selected" v-loading="loading" class="role-detail">
        <div class="detail-head">
          <div class="detail-title">
            <b>{{ selected.name }}</b>
            <span class="role-code">{{ selected.code }}</span>
            <el-tag v-if="isOverridden" size="small" type="warning" effect="plain">本空间已自定义</el-tag>
          </div>
          <div v-if="canRename(selected)" class="detail-actions">
            <el-button size="small" @click="openEdit(selected)">编辑名称/说明</el-button>
            <el-popconfirm
              v-if="!selected.is_system"
              :title="selected.member_count ? `该角色下还有 ${selected.member_count} 个成员，删除后他们将失去该角色的权限。确定删除？` : '确定删除该角色？'"
              width="260" @confirm="del(selected)"
            >
              <template #reference><el-button size="small" type="danger" plain>删除</el-button></template>
            </el-popconfirm>
          </div>
        </div>
        <div v-if="selected.description" class="role-desc">{{ selected.description }}</div>

        <!-- 变更暂存栏：所有勾选先存本地，统一保存/放弃（不再每次勾选即时落库） -->
        <div v-if="permDirty && editable(selected)" class="dirty-bar">
          <span>有未保存的权限修改</span>
          <el-button size="small" type="primary" :loading="savingPerms" @click="savePerms">保存修改</el-button>
          <el-button size="small" @click="discardPerms">放弃修改</el-button>
        </div>

        <el-alert
          v-if="selected.code === 'admin'" type="warning" :closable="false" class="admin-tip"
          title="管理员为代码级超级角色，恒拥有全部权限，无需配置" />

        <template v-else>
          <!-- 菜单功能 -->
          <div class="perm-section">
            <div class="section-title">菜单功能</div>
            <div class="perm-grid">
              <el-checkbox
                v-for="p in menuPerms" :key="p.id"
                :model-value="hasPerm(selected, p.id)" :disabled="!editable(selected)"
                @change="(v) => togglePerm(selected, p, v)"
              >{{ p.name.replace('菜单-', '') }}</el-checkbox>
            </div>
          </div>

          <!-- 功能权限 -->
          <div class="perm-section">
            <div class="section-title">功能权限</div>
            <div class="perm-grid">
              <el-tooltip
                v-for="p in funcPerms" :key="p.id" :disabled="!PERM_TIPS[p.code]"
                :content="PERM_TIPS[p.code]" placement="top"
              >
                <el-checkbox
                  :model-value="hasPerm(selected, p.id)" :disabled="!editable(selected)"
                  @change="(v) => togglePerm(selected, p, v)"
                >{{ p.name }}</el-checkbox>
              </el-tooltip>
            </div>
          </div>

          <!-- 数据表权限 -->
          <div class="perm-section">
            <div class="section-title">
              数据表权限
              <span class="section-hint">默认全部允许；仅收窄本空间成员的默认访问，表主/管理员/被显式分享者不受影响</span>
            </div>
            <el-table :data="tableRows" v-loading="loadingTablePerms" border size="small" max-height="420">
              <el-table-column prop="label" label="数据表" min-width="160" />
              <el-table-column v-for="op in TABLE_OPS" :key="op.key" :label="op.label" width="90" align="center">
                <template #default="{ row }">
                  <el-checkbox
                    :model-value="row.ops[op.key]" :disabled="!editable(selected)"
                    @change="(v) => toggleTableOp(row, op.key, v)"
                  />
                </template>
              </el-table-column>
              <template #empty><el-empty v-if="!loadingTablePerms" description="本空间还没有数据表" :image-size="60" /></template>
            </el-table>
          </div>

          <!-- 数据范围（记录级：能看哪些记录；依赖 feature_data_scope 套餐权益） -->
          <div v-if="hasDataScope" class="perm-section">
            <div class="section-title">
              数据范围
              <span class="section-hint">记录级过滤，按归属人/组织树收窄；表主/管理员/被显式分享者不受限</span>
              <el-button link type="primary" size="small" style="margin-left: 10px" @click="applyPresets">应用预设（经理=本部门及下级，员工=仅本人）</el-button>
            </div>
            <div class="scope-default">
              <span class="scope-label">默认范围（全部表）</span>
              <el-select
                :model-value="scopeDefault" size="small" style="width: 190px"
                :disabled="!editable(selected)" @change="(v) => setScope(null, v)"
              >
                <el-option v-for="o in SCOPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <!-- 各选项的「能看到什么」示例说明，跟随当前选中项 -->
              <div class="scope-desc">{{ SCOPE_DESCS[scopeDefault] }}</div>
            </div>
            <el-table :data="scopeOverrideRows" border size="small" max-height="300">
              <el-table-column label="按表覆盖" min-width="160">
                <template #default="{ row }">{{ tableLabelOf(row.table_id) }}</template>
              </el-table-column>
              <el-table-column label="范围" width="210">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.scope" size="small" style="width: 180px"
                    :disabled="!editable(selected)" @change="(v) => setScope(row.table_id, v)"
                  >
                    <el-option v-for="o in SCOPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80" align="center">
                <template #default="{ row }">
                  <el-button link type="danger" size="small" :disabled="!editable(selected)" @click="setScope(row.table_id, 'all')">移除</el-button>
                </template>
              </el-table-column>
              <template #empty><el-empty description="暂无按表覆盖，全部表使用上方默认范围" :image-size="60" /></template>
            </el-table>
            <div v-if="editable(selected)" class="scope-add">
              <el-select v-model="ovTableId" filterable size="small" placeholder="选择数据表" style="width: 200px">
                <el-option v-for="t in addableTables" :key="t.id" :label="t.label" :value="t.id" />
              </el-select>
              <el-select v-model="ovScope" size="small" style="width: 170px">
                <el-option v-for="o in SCOPE_OPTIONS.filter((x) => x.value !== 'all')" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <el-button size="small" @click="addOverride">+ 按表覆盖</el-button>
            </div>
          </div>
        </template>
      </div>
      <el-empty v-else description="请选择左侧角色" style="flex: 1" />
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑角色' : '新建角色'" width="480px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="标识" required>
          <el-input v-model="form.code" :disabled="!!editing" placeholder="小写 snake_case，如 sales_lead" />
        </el-form-item>
        <el-form-item label="角色名" required>
          <el-input v-model="form.name" placeholder="如：销售主管" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  applyScopePresets, createRole, deleteRole, getCurrentTenant, getRoleTablePerms, getScopes,
  listPermissions, listRoles, putRoleTablePerm, putScope, setRolePermissions, updateRole,
} from '../api'

const SCOPE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'dept_tree', label: '本部门及下级' },
  { value: 'subtree', label: '本人及下属' },
  { value: 'own', label: '仅本人' },
]
// 数据范围各选项的「能看到什么」示例说明
const SCOPE_DESCS = {
  all: '能看到本空间里的全部记录（不做记录级过滤）',
  dept_tree: '能看到自己所在部门及其下级部门成员录入的记录。例：张三在销售一部，可见销售一部和二部（子部门）所有人的记录',
  subtree: '能看到自己录入的记录 + 直属/间接下属录入的记录（按「直属上级」关系链）。例：王五的上级是张三，张三可见王五的记录',
  own: '只能看到自己录入的记录，看不到其他同事的（表主/管理员/被显式分享者除外）',
}

// 功能权限的术语说明（hover tooltip）
const PERM_TIPS = {
  share: '允许把数据表分享给本空间其他成员或用户组',
  create_physical_table: '允许创建独立物理表（性能更好，占套餐配额）',
  feature_print_templates: '打印模板：按模板把记录导出为格式化 Excel 工单',
  feature_automation: '自动化：工作流定时/触发执行（发通知、写表、调接口）',
  feature_api: 'API 接入：通过 MCP token 让外部 AI 客户端访问本空间数据',
  feature_data_scope: '数据范围：按归属人/组织树限制成员可见的记录',
  feature_owd: '默认共享（OWD）：成员默认互相可见全部记录，可被数据范围收窄',
  feature_share_rules: '共享规则：按条件把记录自动共享给指定角色',
  feature_perm_diagnose: '权限诊断：以某个成员的视角检查他对某张表的实际权限来源',
  feature_field_perm: '字段权限：按角色控制单个字段的可见/可编辑',
  feature_audit: '审计日志：查看记录级增删改操作留痕',
}

const TABLE_OPS = [
  { key: 'can_view', label: '查看' },
  { key: 'can_create', label: '新增' },
  { key: 'can_edit', label: '修改' },
  { key: 'can_delete', label: '删除' },
]

const roles = ref([])
const permissions = ref([])
const selected = ref(null)
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const form = reactive({ code: '', name: '', description: '' })

// 数据表权限矩阵
const tablePerms = ref({ tables: [], perms: {} })
const loadingTablePerms = ref(false)

// 数据范围（角色 × 表 的记录可见范围；随选中角色加载）
const scopeData = ref(null)
const ovTableId = ref(null)
const ovScope = ref('own')
const hasDataScope = computed(() => isPlatformAdmin.value || !!entitlements.value.feature_data_scope)
const scopeDefault = computed(() => scopeData.value?.default?.[selected.value?.id] || 'all')
const scopeOverrideRows = computed(() =>
  (scopeData.value?.overrides || []).filter((o) => o.role_id === selected.value?.id))
const tableLabelOf = (id) => tablePerms.value.tables.find((t) => t.id === id)?.label || `#${id}`
const addableTables = computed(() =>
  tablePerms.value.tables.filter((t) => !scopeOverrideRows.value.some((o) => o.table_id === t.id)))

const user = JSON.parse(localStorage.getItem('grt_user') || '{}')
const isPlatformAdmin = computed(() => !!user.is_platform_admin)
const currentTenantId = Number(localStorage.getItem('grt_tenant_id')) || user.tenant?.id || null
const entitlements = ref({})

const menuPerms = computed(() => permissions.value.filter((p) => p.code.startsWith('menu_')))
const funcPerms = computed(() => permissions.value.filter((p) => !p.code.startsWith('menu_') && p.code !== 'max_tables'))

// 权限勾选：除 admin 角色外都可配——平台超管改全局；租户 admin 对本空间自定义角色直接改，
// 对内置角色写租户级覆盖（仅影响本空间，后端自动分流）
function editable(row) {
  return row.code !== 'admin'
}

// 名称/说明/删除：平台超管任意角色；租户 admin 仅限本空间自定义角色
function canRename(row) {
  if (row.code === 'admin') return false
  if (isPlatformAdmin.value) return true
  return !row.is_system && !!row.tenant_id && row.tenant_id === currentTenantId
}

// 内置角色在本空间有覆盖行 → 标记「已自定义」
const isOverridden = computed(() =>
  !!selected.value && !selected.value.tenant_id && (selected.value.overridden_permission_ids || []).length > 0)

const createDisabled = computed(() =>
  !isPlatformAdmin.value && !entitlements.value.feature_custom_roles)

function hasPerm(role, permId) {
  return role.permissions.some((x) => x.id === permId)
}

const tableRows = computed(() => tablePerms.value.tables.map((t) => ({
  ...t,
  ops: tablePerms.value.perms[String(t.id)] || { can_view: true, can_create: true, can_edit: true, can_delete: true },
})))

async function load(keepSelected = true) {
  loading.value = true
  try {
    const [r, p] = await Promise.all([listRoles(), listPermissions()])
    roles.value = r
    permissions.value = p
    if (!isPlatformAdmin.value) {
      const t = await getCurrentTenant()
      entitlements.value = t.entitlements || {}
    }
    if (keepSelected && selected.value) {
      selected.value = r.find((x) => x.id === selected.value.id) || null
    }
    if (!selected.value && r.length) select(r[0])
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function select(r) {
  // 切换角色前：有未保存修改先确认放弃
  if (permDirty.value && selected.value && selected.value.id !== r.id && editable(selected.value)) {
    try {
      await ElMessageBox.confirm('当前角色的权限修改尚未保存，切换后将丢弃。', '未保存的修改', {
        type: 'warning', confirmButtonText: '丢弃并切换', cancelButtonText: '留下',
      })
    } catch { return }
  }
  permDirty.value = false
  changedTableIds.value.clear()
  selected.value = r
  tablePerms.value = { tables: [], perms: {} }
  scopeData.value = null
  ovTableId.value = null
  if (r.code === 'admin') return
  loadingTablePerms.value = true
  try {
    tablePerms.value = await getRoleTablePerms(r.id)
    if (hasDataScope.value) scopeData.value = await getScopes()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loadingTablePerms.value = false
  }
}

// ---------- 数据范围 ----------
async function setScope(tableId, scope) {
  try {
    await putScope(selected.value.id, tableId, scope)
    ElMessage.success('数据范围已更新')
    scopeData.value = await getScopes()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function addOverride() {
  if (!ovTableId.value) return ElMessage.warning('请选择数据表')
  await setScope(ovTableId.value, ovScope.value)
  ovTableId.value = null
}

async function applyPresets() {
  try {
    await ElMessageBox.confirm(
      '将把「经理」默认范围设为本部门及下级、「普通用户」设为仅本人（租户级默认，已被按表覆盖的不受影响）。继续？',
      '应用预设模板', { type: 'info' })
    await applyScopePresets()
    ElMessage.success('预设已应用')
    scopeData.value = await getScopes()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message) }
}

async function pushGrants(role) {
  const grants = role.permissions.map((x) => ({ permission_id: x.id, value: x.value ?? null }))
  const updated = await setRolePermissions(role.id, grants)
  Object.assign(role, updated)
}

// ---------- 权限修改：本地暂存 + 统一保存/放弃（不再每次勾选即时落库） ----------
const permDirty = ref(false)
const savingPerms = ref(false)
const changedTableIds = ref(new Set())

// 勾选只改本地状态并标记 dirty，不立刻发请求
function togglePerm(role, p, checked) {
  if (checked) {
    role.permissions.push({ id: p.id, code: p.code, name: p.name, value: null })
  } else {
    role.permissions = role.permissions.filter((x) => x.id !== p.id)
  }
  permDirty.value = true
}

function toggleTableOp(row, opKey, v) {
  const ops = { ...row.ops, [opKey]: v }
  row.ops = ops
  // 与后端「全允许则删行」口径对齐（本地先行更新，保存时统一提交）
  const perms = { ...tablePerms.value.perms }
  if (TABLE_OPS.every((o) => ops[o.key])) delete perms[String(row.id)]
  else perms[String(row.id)] = ops
  tablePerms.value = { ...tablePerms.value, perms }
  changedTableIds.value.add(row.id)
  permDirty.value = true
}

// 统一保存：菜单/功能权限 grants + 改动过的表权限行，一次提交
async function savePerms() {
  const role = selected.value
  savingPerms.value = true
  try {
    await pushGrants(role)
    for (const tid of changedTableIds.value) {
      const ops = tablePerms.value.perms[String(tid)] || { can_view: true, can_create: true, can_edit: true, can_delete: true }
      await putRoleTablePerm(role.id, { table_id: tid, ...ops })
    }
    ElMessage.success('权限修改已保存')
    permDirty.value = false
    changedTableIds.value.clear()
  } catch (e) {
    ElMessage.error(e.message)
    select(role)   // 失败回滚重载
  } finally {
    savingPerms.value = false
  }
}

async function discardPerms() {
  permDirty.value = false
  changedTableIds.value.clear()
  await select(selected.value)   // 重新加载，回到已保存状态
  ElMessage.info('已放弃未保存的修改')
}

function openCreate() {
  editing.value = null
  Object.assign(form, { code: '', name: '', description: '' })
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, { code: row.code, name: row.name, description: row.description || '' })
  dialogVisible.value = true
}

async function save() {
  if (!form.code.trim() || !form.name.trim()) return ElMessage.warning('请填写标识和角色名')
  saving.value = true
  try {
    if (editing.value) {
      await updateRole(editing.value.id, { name: form.name.trim(), description: form.description })
    } else {
      await createRole({ code: form.code.trim(), name: form.name.trim(), description: form.description })
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function del(row) {
  try {
    await deleteRole(row.id)
    ElMessage.success('已删除')
    selected.value = null
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => load(false))
</script>

<style scoped>
.dirty-bar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 12px; padding: 8px 12px;
  background: #fdf6ec; border: 1px solid #faecd8; border-radius: 6px; font-size: 13px; color: #b88230;
}
.scope-desc { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.5; }
.role-layout { display: flex; gap: 16px; align-items: flex-start; }
.role-list {
  width: 240px; flex-shrink: 0; background: #fff; border: 1px solid #e4e7ed;
  border-radius: 8px; padding: 6px; max-height: calc(100vh - 180px); overflow: auto;
}
.role-item {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  border-radius: 6px; cursor: pointer;
}
.role-item:hover { background: #f5f7fa; }
.role-item.active { background: #ecf5ff; }
.role-name { font-size: 14px; color: #303133; flex: 1; }
.role-code { font-size: 12px; color: #c0c4cc; }
.role-detail { flex: 1; min-width: 0; }
.detail-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.detail-title { display: flex; align-items: center; gap: 10px; font-size: 16px; }
.detail-actions { display: flex; gap: 8px; }
.role-desc { color: #909399; font-size: 13px; margin-bottom: 8px; }
.admin-tip { margin-top: 8px; }
.perm-section {
  background: #fff; border: 1px solid #e4e7ed; border-radius: 8px;
  padding: 14px 16px; margin-top: 14px;
}
.section-title { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 10px; }
.section-hint { font-size: 12px; font-weight: 400; color: #909399; margin-left: 10px; }
.perm-grid { display: flex; flex-wrap: wrap; gap: 4px 24px; }
.scope-default { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.scope-label { font-size: 13px; color: #606266; }
.scope-add { display: flex; gap: 8px; margin-top: 10px; }
</style>
