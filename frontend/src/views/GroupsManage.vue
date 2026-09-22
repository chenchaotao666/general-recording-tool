<template>
  <div>
    <div class="page-header">
      <h2>用户组</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增用户组</el-button>
    </div>

    <el-alert type="info" :closable="false" style="margin-bottom: 14px"
      title="用户组可用于批量分享：把表分享给组后，组内所有成员自动获得对应权限（与直接分享取并集）。" />

    <el-table :data="groups" v-loading="loading" border>
      <el-table-column prop="name" label="组名" width="160" />
      <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
      <el-table-column label="成员" min-width="300">
        <template #default="{ row }">
          <el-tag
            v-for="m in row.members" :key="m.id" closable size="small"
            style="margin-right: 6px" @close="removeMember(row, m)"
          >{{ m.username }}</el-tag>
          <el-button text type="primary" size="small" @click="openAddMember(row)">+ 添加成员</el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="删除组将同步取消其所有分享授权，确定？" width="240" @confirm="del(row)">
            <template #reference><el-button text type="danger" size="small">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增/编辑组 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户组' : '新增用户组'" width="440px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="组名" required>
          <el-input v-model="form.name" placeholder="如：生产部" />
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

    <!-- 添加成员 -->
    <el-dialog v-model="memberVisible" title="添加成员" width="400px" destroy-on-close>
      <el-input v-model="memberName" placeholder="输入用户名" @keyup.enter="addMember" />
      <template #footer>
        <el-button @click="memberVisible = false">取消</el-button>
        <el-button type="primary" :loading="memberSaving" @click="addMember">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  addGroupMember, createGroup, deleteGroup, listGroups, removeGroupMember, updateGroup,
} from '../api'

const groups = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const form = reactive({ name: '', description: '' })

const memberVisible = ref(false)
const memberSaving = ref(false)
const memberName = ref('')
const memberGroup = ref(null)

async function load() {
  loading.value = true
  try {
    groups.value = await listGroups()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', description: '' })
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写组名')
  saving.value = true
  try {
    if (editing.value) {
      await updateGroup(editing.value.id, { name: form.name.trim(), description: form.description })
    } else {
      await createGroup({ name: form.name.trim(), description: form.description })
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
    await deleteGroup(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function openAddMember(row) {
  memberGroup.value = row
  memberName.value = ''
  memberVisible.value = true
}

async function addMember() {
  if (!memberName.value.trim()) return ElMessage.warning('请输入用户名')
  memberSaving.value = true
  try {
    await addGroupMember(memberGroup.value.id, memberName.value.trim())
    ElMessage.success('已添加')
    memberVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    memberSaving.value = false
  }
}

async function removeMember(row, m) {
  try {
    await removeGroupMember(row.id, m.id)
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>
