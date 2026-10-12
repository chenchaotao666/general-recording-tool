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
        <!-- 搜索（客户端，成员多时不用肉眼扫） -->
        <div v-if="members.length > 10" class="members-filter">
          <el-input v-model="kw" placeholder="搜索用户名" clearable size="small" :prefix-icon="SearchIcon" style="width: 200px" />
          <span class="hint">{{ filteredMembers.length }} 人</span>
        </div>
        <el-table :data="pagedMembers" v-loading="loading" border>
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
          <el-table-column label="加入时间" width="150" :formatter="(r) => fmtTime(r.created_at)" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button
                v-if="row.user_id !== ownerId" type="danger" link size="small"
                @click="remove(row)"
              >移除</el-button>
              <el-tag v-else size="small" effect="plain">所有者</el-tag>
            </template>
          </el-table-column>
          <template #empty><el-empty description="暂无成员" /></template>
        </el-table>
        <el-pagination
          v-if="filteredMembers.length > pageSize" v-model:current-page="page" :page-size="pageSize"
          :total="filteredMembers.length" layout="total, prev, pager, next"
          style="margin-top: 12px; justify-content: flex-end"
        />
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
                    <el-dropdown trigger="click" @command="(cmd) => onDeptCommand(cmd, data)">
                      <el-button link size="small" @click.stop>更多</el-button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="edit">编辑</el-dropdown-item>
                          <el-dropdown-item command="move">移动</el-dropdown-item>
                          <el-dropdown-item command="toggle">{{ data.enabled ? '停用' : '启用' }}</el-dropdown-item>
                          <el-dropdown-item command="delete"><span style="color: #f56c6c">删除</span></el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
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

    </el-tabs>

    <!-- 邀请 -->
    <el-dialog v-model="inviteVisible" title="邀请成员" width="420px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="inviteForm.username" placeholder="对方需已注册账号" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="inviteForm.role" style="width: 100%">
            <!-- 邀请不设 admin：管理员只能由现有管理员在成员列表里逐个调整（防一次误操作放权） -->
            <el-option v-for="r in invitableRoles" :key="r.code" :label="`${r.name}（${r.code}）`" :value="r.code" />
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

  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Search as SearchIcon } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createDepartment, deleteDepartment, getCurrentTenant,
  inviteMember, listDepartments, listMembers, listRoles, moveDepartment,
  removeMember, setMemberOrg, setMemberRole, updateDepartment,
} from '../api'
import { fmtTime } from '../utils/format'

const tab = ref('members')
const members = ref([])
const roles = ref([])
const departments = ref([])
const loading = ref(false)
const loadingDepts = ref(false)
const saving = ref(false)
const inviting = ref(false)
const inviteVisible = ref(false)
const inviteForm = reactive({ username: '', role: 'user' })

// ---------- 成员搜索/分页 ----------
const kw = ref('')
const page = ref(1)
const pageSize = 20
const filteredMembers = computed(() => {
  const k = kw.value.trim().toLowerCase()
  if (!k) return members.value
  return members.value.filter((m) => m.username.toLowerCase().includes(k))
})
const pagedMembers = computed(() => filteredMembers.value.slice((page.value - 1) * pageSize, page.value * pageSize))

// 邀请可选角色：排除 admin（管理员由现有管理员在成员列表里逐个调整，不开放直接邀请）
const invitableRoles = computed(() => roles.value.filter((r) => r.code !== 'admin'))

// 部门树节点的「更多」菜单
function onDeptCommand(cmd, data) {
  if (cmd === 'edit') openDeptEdit(data)
  else if (cmd === 'move') openMove(data)
  else if (cmd === 'toggle') toggleDept(data)
  else if (cmd === 'delete') delDept(data)
}
const tenant = ref(null)
const ownerId = ref(0)


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


async function load() {
  loading.value = true
  try {
    const [m, r, t, d] = await Promise.all([listMembers(), listRoles(), getCurrentTenant(), listDepartments()])
    members.value = m
    roles.value = r   // 全量角色（成员列表改角色可选全部；邀请时下拉已排除 admin）
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

onMounted(load)

// ---------- 成员 ----------
// L3 权限变更即生效：先确认；给自己降权额外强提醒（可能立刻失去管理权限）
async function changeRole(row, role) {
  const me = JSON.parse(localStorage.getItem('grt_user') || 'null')
  const isSelf = row.user_id === me?.id
  const roleName = roles.value.find((r) => r.code === role)?.name || role
  try {
    await ElMessageBox.confirm(
      isSelf
        ? `你正在把自己「${row.username}」的角色改为「${roleName}」，如果不是管理员，你将立刻失去本页面的管理权限。确定继续？`
        : `确定把成员「${row.username}」的角色改为「${roleName}」？`,
      '调整角色',
      { type: 'warning', confirmButtonText: '确定调整', cancelButtonText: '取消' },
    )
  } catch { return }   // 取消：select 是 :model-value 非受控回写，界面自然保持原值
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

</script>

<style scoped>
.members-filter { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.members-filter .hint { font-size: 12px; color: #909399; }
.seat-tip { margin-bottom: 12px; }
.dept-node { display: flex; justify-content: space-between; align-items: center; width: 100%; padding-right: 8px; }
.dept-meta { color: #909399; font-size: 12px; margin-left: 8px; }
.dept-disabled { color: #909399; text-decoration: line-through; }
</style>
