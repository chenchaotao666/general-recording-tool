<template>
  <div>
    <div class="page-header">
      <h2>权限管理</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增权限</el-button>
    </div>

    <el-alert type="info" :closable="false" style="margin-bottom: 14px"
      title="权限点用于角色授权。内置权限（系统预置）不可删除；自定义权限可用于扩展业务约束。" />

    <el-table :data="permissions" v-loading="loading" border>
      <el-table-column prop="code" label="标识" width="200" />
      <el-table-column prop="name" label="名称" width="140" />
      <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
      <el-table-column label="类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_system ? 'info' : 'success'" size="small">{{ row.is_system ? '内置' : '自定义' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row.is_system" title="确定删除该权限？关联角色将同步失去该权限。" width="240" @confirm="del(row)">
            <template #reference><el-button text type="danger" size="small">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增权限" width="480px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="标识" required>
          <el-input v-model="form.code" placeholder="小写 snake_case，如 export_report" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：导出报表" />
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
import { createPermission, deletePermission, listPermissions } from '../api'

const permissions = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive({ code: '', name: '', description: '' })

async function load() {
  loading.value = true
  try {
    permissions.value = await listPermissions()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { code: '', name: '', description: '' })
  dialogVisible.value = true
}

async function save() {
  if (!form.code.trim() || !form.name.trim()) return ElMessage.warning('请填写标识和名称')
  saving.value = true
  try {
    await createPermission({ code: form.code.trim(), name: form.name.trim(), description: form.description })
    ElMessage.success('已创建')
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
    await deletePermission(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(load)
</script>
