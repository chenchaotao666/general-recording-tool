<template>
  <div>
    <div class="page-header">
      <h2>组织与成员</h2>
      <el-button v-if="tab === 'members'" type="primary" @click="inviteVisible = true">邀请成员</el-button>
      <el-button v-else-if="tab === 'depts'" type="primary" @click="openDeptEdit(null)">新建根部门</el-button>
    </div>

    <el-tabs v-model="tab">
      <!-- ============ 成员 ============ -->
      <el-tab-pane label="成员" name="members">
        <el-alert
          v-if="seatTip" :type="seatTip.type" :closable="false" class="seat-tip" :title="seatTip.text" />
        <el-table :data="members" v-loading="loading" border>
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column label="角色" width="170">
            <template #default="{ row }">
              <el-select
                :model-value="row.role" size="small" style="width: 150px"
                :disabled="row.user_id === ownerId"
                @change="(v) => changeRole(row, v)"
              >
                <el-option v-for="r in roles" :key="r.code" :label="`${r.name}（${r.code}）`" :value="r.code" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="所属部门" width="180">
            <template #default="{ row }">
              <el-tree-select
                :model-value="row.department_id" size="small" clearable placeholder="未分配"
                :data="deptTree" :props="{ label: 'name', value: 'id', children: 'children' }"
                check-strictly :render-after-expand="false" style="width: 160px"
                @change="(v) => changeOrg(row, v ?? null, row.manager_id)"
              />
            </template>
          </el-table-column>
          <el-table-column label="直属上级" width="150">
            <template #default="{ row }">
              <el-select
                :model-value="row.manager_id" size="small" clearable placeholder="无"
                style="width: 130px"
                @change="(v) => changeOrg(row, row.department_id, v ?? null)"
              >
                <el-option
                  v-for="m in members.filter((x) => x.user_id !== row.user_id && x.status === 'active')"
                  :key="m.user_id" :label="m.username" :value="m.user_id" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="{ active: 'success', invited: 'warning', disabled: 'info' }[row.status] || 'info'" size="small">
                {{ { active: '已加入', invited: '待接受', disabled: '已停用' }[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="加入时间" width="160" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button
                v-if="row.user_id !== ownerId" type="danger" link size="small"
                @click="remove(row)"
              >移除</el-button>
              <el-tag v-else size="small" effect="plain">所有者</el-tag>
            </template>
          </el-table-column>
          <template #empty>暂无成员</template>
        </el-table>
      </el-tab-pane>

      <!-- ============ 部门树 ============ -->
      <el-tab-pane label="部门树" name="depts">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-tree
              :data="deptTree" :props="{ label: 'name', children: 'children' }"
              node-key="id" default-expand-all :expand-on-click-node="false"
              v-loading="loadingDepts"
            >
              <template #default="{ data }">
                <div class="dept-node">
                  <span :class="{ 'dept-disabled': !data.enabled }">
                    {{ data.name }}
                    <el-tag v-if="!data.enabled" size="small" type="info">已停用</el-tag>
                    <span class="dept-meta">{{ data.member_count }}人<template v-if="data.leader_name"> · 负责人 {{ data.leader_name }}</template></span>
                  </span>
                  <span class="dept-ops">
                    <el-button link size="small" type="primary" @click.stop="openDeptEdit(null, data.id)">加子部门</el-button>
                    <el-button link size="small" @click.stop="openDeptEdit(data)">编辑</el-button>
                    <el-button link size="small" @click.stop="openMove(data)">移动</el-button>
                    <el-button link size="small" :type="data.enabled ? 'warning' : 'success'" @click.stop="toggleDept(data)">
                      {{ data.enabled ? '停用' : '启用' }}
                    </el-button>
                    <el-button link size="small" type="danger" @click.stop="delDept(data)">删除</el-button>
                  </span>
                </div>
              </template>
            </el-tree>
            <el-empty v-if="!deptTree.length && !loadingDepts" description="还没有部门，点右上角「新建根部门」" :image-size="60" />
          </el-col>
          <el-col :span="12">
            <el-alert type="info" :closable="false"
              title="说明：一个用户只属于一个部门；停用部门后其成员在「本部门及下级」范围下视同未分配（只看自己）；删除部门前须先迁出成员与子部门。" />
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ============ 数据范围 ============ -->
      <el-tab-pane v-if="hasDataScope" label="数据范围" name="scopes">
        <el-alert type="info" :closable="false" class="seat-tip"
          title="数据范围 = 角色 × 数据表 的记录可见范围（按记录归属人过滤）。「全部」不限制；显式分享的表不受范围限制；管理员恒为全部。" />
        <div class="scope-toolbar">
          <el-button type="primary" plain @click="applyPresets">应用预设模板（经理=本部门及下级，员工=仅本人）</el-button>
        </div>
        <el-table :data="scopeRows" v-loading="loadingScopes" border>
          <el-table-column label="角色" width="160">
            <template #default="{ row }">{{ row.name }}（{{ row.code }}）</template>
          </el-table-column>
          <el-table-column label="默认范围（全部表）" width="220">
            <template #default="{ row }">
              <el-select
                :model-value="row.defaultScope" size="small" style="width: 190px"
                @change="(v) => setScope(row.id, null, v)"
              >
                <el-option v-for="o in SCOPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="按表覆盖" min-width="320">
            <template #default="{ row }">
              <div v-for="ov in row.overrides" :key="ov.table_id" class="scope-ov">
                <span class="ov-table">{{ tableLabel(ov.table_id) }}</span>
                <el-select
                  :model-value="ov.scope" size="small" style="width: 160px"
                  @change="(v) => setScope(row.id, ov.table_id, v)"
                >
                  <el-option v-for="o in SCOPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
                <el-button link type="danger" size="small" @click="setScope(row.id, ov.table_id, 'all')">移除</el-button>
              </div>
              <el-button size="small" @click="openOverride(row)">+ 按表覆盖</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 邀请 -->
    <el-dialog v-model="inviteVisible" title="邀请成员" width="420px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="inviteForm.username" placeholder="对方需已注册账号" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="inviteForm.role" style="width: 100%">
            <el-option v-for="r in roles" :key="r.code" :label="`${r.name}（${r.code}）`" :value="r.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inviteVisible = false">取消</el-button>
        <el-button type="primary" :loading="inviting" @click="invite">邀请</el-button>
      </template>
    </el-dialog>

    <!-- 部门编辑 -->
    <el-dialog v-model="deptVisible" :title="deptForm.id ? '编辑部门' : '新建部门'" width="420px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="deptForm.name" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="deptForm.leader_id" clearable placeholder="可选" style="width: 100%">
            <el-option v-for="m in members.filter((x) => x.status === 'active')" :key="m.user_id" :label="m.username" :value="m.user_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="deptForm.sort" :min="0" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deptVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDept">保存</el-button>
      </template>
    </el-dialog>

    <!-- 部门移动 -->
    <el-dialog v-model="moveVisible" :title="`移动部门：${moveTarget?.name}`" width="420px" destroy-on-close>
      <el-tree-select
        v-model="moveParentId" clearable placeholder="留空 = 移到根级"
        :data="deptTree" :props="{ label: 'name', value: 'id', children: 'children' }"
        check-strictly :render-after-expand="false" style="width: 100%"
      />
      <template #footer>
        <el-button @click="moveVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doMove">确定</el-button>
      </template>
    </el-dialog>

    <!-- 按表覆盖 -->
    <el-dialog v-model="ovVisible" :title="`按表覆盖：${ovRole?.name}`" width="420px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="数据表">
          <el-select v-model="ovTableId" filterable style="width: 100%">
            <el-option v-for="t in allTables" :key="t.id" :label="t.label" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="范围">
          <el-select v-model="ovScope" style="width: 100%">
            <el-option v-for="o in SCOPE_OPTIONS.filter((x) => x.value !== 'all')" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ovVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveOverride">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  applyScopePresets, createDepartment, deleteDepartment, getCurrentTenant, getScopes,
  inviteMember, listDepartments, listMembers, listRoles, listTables, moveDepartment,
  putScope, removeMember, setMemberOrg, setMemberRole, updateDepartment,
} from '../api'

const SCOPE_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'dept_tree', label: '本部门及下级' },
  { value: 'subtree', label: '本人及下属' },
  { value: 'own', label: '仅本人' },
]

const tab = ref('members')
const members = ref([])
const roles = ref([])
const departments = ref([])
const allTables = ref([])
const loading = ref(false)
const loadingDepts = ref(false)
const loadingScopes = ref(false)
const saving = ref(false)
const inviting = ref(false)
const inviteVisible = ref(false)
const inviteForm = reactive({ username: '', role: 'user' })
const tenant = ref(null)
const ownerId = ref(0)
const scopeData = ref(null)

const hasDataScope = computed(() => !!tenant.value?.entitlements?.feature_data_scope)

const seatTip = computed(() => {
  const seats = tenant.value?.usage?.seats
  if (!seats?.limit) return null
  if (seats.percent >= 100) return { type: 'error', text: `席位已满（${seats.used}/${seats.limit}），邀请将进入宽限期或被拒绝，请升级套餐` }
  if (seats.percent >= 80) return { type: 'warning', text: `席位即将用完（${seats.used}/${seats.limit}）` }
  return { type: 'info', text: `席位：${seats.used}/${seats.limit}` }
})

// 平铺部门 → 树
const deptTree = computed(() => {
  const map = new Map(departments.value.map((d) => [d.id, { ...d, children: [] }]))
  const roots = []
  for (const d of map.values()) {
    if (d.parent_id && map.has(d.parent_id)) map.get(d.parent_id).children.push(d)
    else roots.push(d)
  }
  const dropEmpty = (list) => list.forEach((d) => { dropEmpty(d.children); if (!d.children.length) delete d.children })
  dropEmpty(roots)
  return roots
})

const scopeRows = computed(() => {
  if (!scopeData.value) return []
  return scopeData.value.roles.map((r) => ({
    ...r,
    defaultScope: scopeData.value.default[r.id] || 'all',
    overrides: scopeData.value.overrides.filter((o) => o.role_id === r.id),
  }))
})

const tableLabel = (id) => allTables.value.find((t) => t.id === id)?.label || `#${id}`

async function load() {
  loading.value = true
  try {
    const [m, r, t, d] = await Promise.all([listMembers(), listRoles(), getCurrentTenant(), listDepartments()])
    members.value = m
    roles.value = r.filter((x) => x.code !== 'admin' || true)
    tenant.value = t
    departments.value = d
    ownerId.value = m.find((x) => x.status === 'active' && x.user_id === t?.tenant?.owner_user_id)?.user_id
      ?? m[0]?.user_id ?? 0
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadScopes() {
  if (!hasDataScope.value) return
  loadingScopes.value = true
  try {
    const [sc, ts] = await Promise.all([getScopes(), listTables({ all: 1 })])
    scopeData.value = sc
    allTables.value = ts
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loadingScopes.value = false
  }
}

onMounted(async () => {
  await load()          // 先拿到租户权益（feature_data_scope 判定依赖它）
  loadScopes()
})

// ---------- 成员 ----------
async function changeRole(row, role) {
  try {
    await setMemberRole(row.id, role)
    row.role = role
    ElMessage.success('角色已调整')
  } catch (e) { ElMessage.error(e.message) }
}

async function changeOrg(row, departmentId, managerId) {
  try {
    await setMemberOrg(row.id, departmentId, managerId)
    ElMessage.success('组织归属已更新')
    load()
  } catch (e) {
    ElMessage.error(e.message)
    load()
  }
}

async function invite() {
  if (!inviteForm.username.trim()) return ElMessage.warning('请输入用户名')
  inviting.value = true
  try {
    await inviteMember(inviteForm.username.trim(), inviteForm.role)
    ElMessage.success('已发出邀请，对方接受后加入')
    inviteVisible.value = false
    inviteForm.username = ''
    load()
  } catch (e) { ElMessage.error(e.message) } finally { inviting.value = false }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定把 ${row.username} 移出本工作空间？其账号与数据不受影响。`, '移除成员', { type: 'warning' })
    await removeMember(row.id)
    ElMessage.success('已移除')
    load()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message) }
}

// ---------- 部门树 ----------
const deptVisible = ref(false)
const deptForm = reactive({ id: null, name: '', parent_id: null, leader_id: null, sort: 0 })
const moveVisible = ref(false)
const moveTarget = ref(null)
const moveParentId = ref(null)

function openDeptEdit(dept, parentId = null) {
  Object.assign(deptForm, dept
    ? { id: dept.id, name: dept.name, parent_id: dept.parent_id, leader_id: dept.leader_id, sort: dept.sort }
    : { id: null, name: '', parent_id: parentId, leader_id: null, sort: 0 })
  deptVisible.value = true
}

async function saveDept() {
  if (!deptForm.name.trim()) return ElMessage.warning('请填写部门名称')
  saving.value = true
  try {
    if (deptForm.id) {
      await updateDepartment(deptForm.id, { name: deptForm.name, leader_id: deptForm.leader_id, sort: deptForm.sort })
    } else {
      await createDepartment({ name: deptForm.name, parent_id: deptForm.parent_id, leader_id: deptForm.leader_id, sort: deptForm.sort })
    }
    ElMessage.success('已保存')
    deptVisible.value = false
    load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

function openMove(dept) {
  moveTarget.value = dept
  moveParentId.value = dept.parent_id
  moveVisible.value = true
}

async function doMove() {
  saving.value = true
  try {
    await moveDepartment(moveTarget.value.id, moveParentId.value ?? null)
    ElMessage.success('已移动')
    moveVisible.value = false
    load()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function toggleDept(dept) {
  try {
    await updateDepartment(dept.id, { enabled: !dept.enabled })
    load()
  } catch (e) { ElMessage.error(e.message) }
}

async function delDept(dept) {
  try {
    await ElMessageBox.confirm(`确定删除部门「${dept.name}」？须先迁出成员与子部门。`, '删除部门', { type: 'warning' })
    await deleteDepartment(dept.id)
    ElMessage.success('已删除')
    load()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message) }
}

// ---------- 数据范围 ----------
const ovVisible = ref(false)
const ovRole = ref(null)
const ovTableId = ref(null)
const ovScope = ref('own')

async function setScope(roleId, tableId, scope) {
  try {
    await putScope(roleId, tableId, scope)
    ElMessage.success('数据范围已更新')
    loadScopes()
  } catch (e) {
    ElMessage.error(e.message)
    loadScopes()
  }
}

function openOverride(row) {
  ovRole.value = row
  ovTableId.value = null
  ovScope.value = 'own'
  ovVisible.value = true
}

async function saveOverride() {
  if (!ovTableId.value) return ElMessage.warning('请选择数据表')
  saving.value = true
  try {
    await putScope(ovRole.value.id, ovTableId.value, ovScope.value)
    ElMessage.success('已添加按表覆盖')
    ovVisible.value = false
    loadScopes()
  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }
}

async function applyPresets() {
  try {
    await ElMessageBox.confirm('将把「经理」默认范围设为本部门及下级、「普通用户」设为仅本人（租户级默认，已被按表覆盖的不受影响）。继续？', '应用预设模板', { type: 'info' })
    await applyScopePresets()
    ElMessage.success('预设已应用')
    loadScopes()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.message) }
}
</script>

<style scoped>
.seat-tip { margin-bottom: 12px; }
.scope-toolbar { margin-bottom: 12px; }
.scope-ov { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.ov-table { min-width: 110px; color: #303133; }
.dept-node { display: flex; justify-content: space-between; align-items: center; width: 100%; padding-right: 8px; }
.dept-meta { color: #909399; font-size: 12px; margin-left: 8px; }
.dept-disabled { color: #909399; text-decoration: line-through; }
</style>
