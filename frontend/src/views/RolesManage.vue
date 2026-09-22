<template>
  <div>
    <div class="page-header">
      <h2>角色管理</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增角色</el-button>
    </div>

    <el-table :data="roles" v-loading="loading" border>
      <el-table-column prop="code" label="标识" width="130" />
      <el-table-column prop="name" label="角色名" width="130" />
      <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
      <el-table-column label="权限" min-width="320">
        <template #default="{ row }">
          <div class="perm-list">
            <div v-for="p in permissions" :key="p.id" class="perm-item">
              <el-checkbox
                :model-value="hasPerm(row, p.id)"
                @change="(v) => togglePerm(row, p, v)"
              >{{ p.name }}</el-checkbox>
              <el-input-number
                v-if="hasPerm(row, p.id) && isValuePerm(p)"
                :model-value="permValue(row, p.id)" :min="1" :max="9999" size="small"
                controls-position="right" style="width: 90px"
                placeholder="不限"
                @change="(v) => setPermValue(row, p, v)"
              />
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm v-if="!row.is_system" title="确定删除该角色？" width="220" @confirm="del(row)">
            <template #reference><el-button text type="danger" size="small">删除</el-button></template>
          </el-popconfirm>
          <el-tag v-else size="small" type="info">内置</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑角色' : '新增角色'" width="480px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="标识" required>
          <el-input v-model="form.code" :disabled="!!editing" placeholder="小写 snake_case，如 manager" />
        </el-form-item>
        <el-form-item label="角色名" required>
          <el-input v-model="form.name" placeholder="如：部门主管" />
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { createRole, deleteRole, listPermissions, listRoles, setRolePermissions, updateRole } from '../api'

const roles = ref([])
const permissions = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const form = reactive({ code: '', name: '', description: '' })

// 数值型权限（code 以 max_ 开头或已知列表）显示数值输入
function isValuePerm(p) {
  return p.code === 'max_tables'
}

function hasPerm(role, permId) {
  return role.permissions.some((x) => x.id === permId)
}

function permValue(role, permId) {
  const hit = role.permissions.find((x) => x.id === permId)
  return hit ? hit.value : null
}

async function load() {
  loading.value = true
  try {
    const [r, p] = await Promise.all([listRoles(), listPermissions()])
    roles.value = r
    permissions.value = p
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function pushGrants(role) {
  const grants = role.permissions.map((x) => ({ permission_id: x.id, value: x.value ?? null }))
  const updated = await setRolePermissions(role.id, grants)
  Object.assign(role, updated)
}

async function togglePerm(role, p, checked) {
  if (checked) {
    role.permissions.push({ id: p.id, code: p.code, name: p.name, value: isValuePerm(p) ? 10 : null })
  } else {
    role.permissions = role.permissions.filter((x) => x.id !== p.id)
  }
  try {
    await pushGrants(role)
  } catch (e) {
    ElMessage.error(e.message)
    load()
  }
}

async function setPermValue(role, p, v) {
  const hit = role.permissions.find((x) => x.id === p.id)
  if (hit) hit.value = v
  try {
    await pushGrants(role)
  } catch (e) {
    ElMessage.error(e.message)
  }
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
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>

<style scoped>
.perm-list { display: flex; flex-direction: column; gap: 2px; }
.perm-item { display: flex; align-items: center; gap: 8px; }
</style>
