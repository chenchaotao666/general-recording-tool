<template>
  <!-- 内容权限总览侧栏（§13.7，对齐参照 内容权限-全员权限列表.png）：
       全员权限卡（条目 + 等级摘要 ›）→ 分隔文案 → 指定成员组卡（备注名 + ⋯ +「包含 …」+ 组内各表等级行）→「＋ 为指定成员添加额外权限」 -->
  <transition name="pp-slide">
    <div v-if="visible" class="pp">
      <div class="pp-head">
        <div>
          <div class="pp-title">内容权限<span class="st-free-tag">限时免费</span></div>
          <el-tooltip :hide-after="0" placement="bottom" :content="'为不同成员设置可查看/可编辑的记录与字段：全员权限是基线，指定成员可额外叠加权限'">
            <div class="pp-help">了解功能用法和使用场景 <StIcon name="chevron-right" :size="12" /></div>
          </el-tooltip>
        </div>
        <span class="pp-x st-icon-action" @click="emit('close')"><StIcon name="close" :size="20" /></span>
      </div>
      <div v-loading="loading" class="pp-body">
        <div class="pp-card">
          <div class="pp-card-t">全员权限
            <el-tooltip :hide-after="0" content="全员权限对所有可编辑、仅浏览成员生效" placement="top"><StIcon name="info" :size="14" class="pp-i" /></el-tooltip>
          </div>
          <div v-for="e in overview.entries" :key="e.entry_id" class="pp-row" @click="openBase(e.entry_id)">
            <StIcon :name="entryIcon(e.type)" :size="16" class="pp-eicon" />
            <span class="pp-name">{{ e.name }}</span>
            <span class="pp-sum">{{ e.summary }}<StIcon name="chevron-right" :size="13" /></span>
          </div>
          <div v-if="!overview.entries.length" class="pp-empty">暂无条目</div>
        </div>

        <div v-if="overview.groups.length" class="pp-sep-text">以下指定成员还拥有额外的内容权限。</div>
        <div class="pp-card">
          <div v-for="(g, gi) in overview.groups" :key="g.id" class="pp-group" :class="{ first: gi === 0 }">
            <div class="pp-g-head">
              <div>
                <div class="pp-g-name">{{ g.name }}</div>
                <div class="pp-g-members">包含 {{ g.members.map(m => m.name).join('、') }}</div>
              </div>
              <el-dropdown :hide-after="0" v-if="overview.can_manage_groups" trigger="click" @command="(c) => groupAction(c, g)">
                <span class="pp-more st-icon-action"><StIcon name="more-h" :size="18" /></span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="grants">设置额外权限</el-dropdown-item>
                    <el-dropdown-item command="edit">修改指定成员</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div v-for="gr in g.grants" :key="gr.entry_id" class="pp-row pp-g-row" @click="openGroup(g, gr.entry_id)">
              <StIcon :name="entryIcon(gr.type)" :size="16" class="pp-eicon" />
              <span class="pp-name">{{ gr.name }}</span>
              <span class="pp-sum">{{ gr.summary }}<StIcon name="chevron-right" :size="13" /></span>
            </div>
            <div v-if="!g.grants.length" class="pp-g-empty" @click="openGroup(g)">暂未设置额外权限，点击设置</div>
          </div>
          <div v-if="overview.can_manage_groups" class="pp-add" :class="{ solo: !overview.groups.length }"
               @click="openMemberDialog(null)">
            <StIcon name="plus" :size="15" />为指定成员添加额外权限
          </div>
        </div>
      </div>

      <PermissionDialog :visible="dlg.visible" :mode="dlg.mode" :entries="overview.entries" :group="dlg.group"
                        :initial-entry-id="dlg.entryId" @close="dlg.visible = false" @saved="load"
                        @open-base="(id) => openBase(id)" @group-action="groupAction" />
      <MemberGroupDialog :visible="mg.visible" :doc-id="docId" :members="members" :group="mg.group"
                         @close="mg.visible = false" @saved="onGroupSaved" />
    </div>
  </transition>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import StIcon from '../icons/StIcon.vue'
import PermissionDialog from './PermissionDialog.vue'
import MemberGroupDialog from './MemberGroupDialog.vue'
import { smartDeletePermGroup, smartPermOverview } from '../../../api/index.js'

const props = defineProps({
  visible: Boolean,
  docId: Number,
  members: { type: Array, default: () => [] },
  focusEntryId: { type: Number, default: null },   // 打开时直接进入该条目的全员权限
})
const emit = defineEmits(['close', 'changed'])

const overview = ref({ entries: [], groups: [], can_manage_groups: false })
const loading = ref(false)
const dlg = reactive({ visible: false, mode: 'base', group: null, entryId: null })
const mg = reactive({ visible: false, group: null })

function entryIcon(t) { return { dashboard: 'dashboard', form: 'form', sheet: 'view-grid' }[t] || 'view-grid' }

async function load() {
  if (!props.docId) return
  loading.value = true
  try {
    overview.value = await smartPermOverview(props.docId)
    if (dlg.group) dlg.group = overview.value.groups.find(g => g.id === dlg.group.id) || null
    emit('changed')
  } catch (e) {
    ElMessage.error(e.message || '加载内容权限失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, async (v) => {
  if (!v) return
  await load()
  if (props.focusEntryId) openBase(props.focusEntryId)
})

function openBase(entryId) { Object.assign(dlg, { visible: true, mode: 'base', group: null, entryId }) }
function openGroup(g, entryId = null) { Object.assign(dlg, { visible: true, mode: 'group', group: g, entryId }) }
function openMemberDialog(group) { Object.assign(mg, { visible: true, group }) }

async function onGroupSaved(group, isNew) {
  mg.visible = false
  await load()
  const g = overview.value.groups.find(x => x.id === group.id)
  if (isNew && g) openGroup(g)   // 第 2 步：进入与全员权限同构的组权限对话框
}

async function groupAction(cmd, g) {
  if (cmd === 'grants') openGroup(g)
  else if (cmd === 'edit') openMemberDialog(g)
  else if (cmd === 'delete') {
    await ElMessageBox.confirm(`删除指定成员「${g.name}」？其额外权限将一并移除。`, '删除', { type: 'warning' })
    await smartDeletePermGroup(g.id)
    dlg.visible = false
    ElMessage.success('已删除')
    load()
  }
}
</script>

<style scoped>
.pp { position: fixed; top: 56px; right: 0; bottom: 0; width: 420px; z-index: 2000; background: #F7F8FA;
      box-shadow: -8px 0 24px rgba(0, 0, 0, .08); display: flex; flex-direction: column; --el-color-primary: var(--st-primary); }
.pp-head { display: flex; justify-content: space-between; align-items: flex-start; padding: 18px 20px 14px; background: #fff; border-bottom: 1px solid var(--st-border); }
.pp-title { font-size: 19px; font-weight: 700; color: var(--st-text-1); display: flex; align-items: center; }
.pp-help { font-size: 13px; color: var(--st-text-2); margin-top: 4px; cursor: pointer; display: inline-flex; align-items: center; gap: 2px; }
.pp-x { cursor: pointer; display: inline-flex; padding: 2px; }
.pp-body { flex: 1; overflow: auto; padding: 16px; }
.pp-card { background: #fff; border-radius: 12px; padding: 16px 12px 10px; margin-bottom: 12px; }
.pp-card-t { font-size: 15px; font-weight: 700; padding: 0 10px 8px; display: flex; align-items: center; gap: 4px; }
.pp-i { color: var(--st-text-3); }
.pp-row { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 8px; cursor: pointer; font-size: 14px; }
.pp-row:hover { background: var(--st-bg-hover); }
.pp-eicon { color: var(--st-text-2); flex: none; }
.pp-name { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--st-text-1); }
.pp-sum { display: inline-flex; align-items: center; gap: 2px; color: var(--st-text-3); font-size: 13px; flex: none; }
.pp-empty { color: var(--st-text-4); font-size: 13px; padding: 8px 10px; }
.pp-sep-text { font-size: 13px; color: var(--st-text-2); padding: 4px 12px 10px; }
.pp-group { padding-top: 14px; border-top: 1px solid var(--st-border); margin: 0 10px 6px; }
.pp-group.first { border-top: none; padding-top: 0; }
.pp-group .pp-row { margin: 0 -10px; }
.pp-g-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px; }
.pp-g-name { font-size: 15px; font-weight: 700; color: var(--st-text-1); }
.pp-g-members { font-size: 13px; color: var(--st-text-3); margin-top: 2px; }
.pp-more { cursor: pointer; display: inline-flex; padding: 4px; border-radius: 4px; color: var(--st-text-1); }
.pp-more:hover { background: var(--st-bg-hover); }
.pp-g-row { background: transparent; }
.pp-g-row:hover { background: var(--st-bg-active); }
.pp-g-empty { font-size: 13px; color: var(--st-primary); cursor: pointer; padding: 4px 0 8px; }
.pp-add { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 14px 0 6px; margin: 4px 10px 0;
          border-top: 1px solid var(--st-border); cursor: pointer; font-size: 15px; color: var(--st-text-1); }
.pp-add.solo { border-top: none; padding-top: 6px; }
.pp-add:hover { color: var(--st-primary); }
.pp-slide-enter-active, .pp-slide-leave-active { transition: transform .2s ease; }
.pp-slide-leave-active { transition-duration: var(--st-panel-close-duration, 80ms); }
.pp-slide-enter-from, .pp-slide-leave-to { transform: translateX(100%); }
</style>
