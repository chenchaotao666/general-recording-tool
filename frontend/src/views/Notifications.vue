<template>
  <div>
    <div class="page-header">
      <h2>通知</h2>
      <div class="header-actions">
        <el-radio-group v-model="onlyUnread" size="small" @change="reload">
          <el-radio-button :value="false">全部</el-radio-button>
          <el-radio-button :value="true">只看未读</el-radio-button>
        </el-radio-group>
        <el-button size="small" :disabled="!items.length" @click="readAll">全部已读</el-button>
        <el-button size="small" type="danger" plain @click="clearRead">清空已读</el-button>
      </div>
    </div>

    <!-- 通知列表 -->
    <section v-loading="loading" class="notify-list" aria-label="通知列表">
      <el-empty v-if="!items.length && !loading" :description="onlyUnread ? '没有未读通知' : '暂无通知'" />
      <article
        v-for="n in items" :key="n.id" class="notify-item" :class="{ unread: !n.read }"
        tabindex="0" @click="open(n)" @keydown.enter.self.prevent="open(n)"
      >
        <div class="notify-kind" :class="notificationType(n).kind">
          <el-icon :size="19"><component :is="notificationType(n).icon" /></el-icon>
          <i v-if="!n.read" class="notify-unread-dot" aria-label="未读" />
        </div>
        <div class="notify-body">
          <div class="notify-heading"><h3 class="notify-title">{{ n.title }}</h3><span class="notify-source">{{ notificationType(n).label }}</span></div>
          <div v-if="n.content" class="notify-content" :class="{ expanded: expandedMessages[n.id] }">{{ n.content }}</div>
          <button v-if="n.content && (n.content.length > 100 || n.content.includes('\n'))" type="button" class="notify-expand" @click.stop="expandedMessages[n.id] = !expandedMessages[n.id]">{{ expandedMessages[n.id] ? '收起正文' : '展开正文' }}</button>
        <!-- 邀请类通知：直接在条目上 接受/拒绝，已处理的显示结果标签 -->
        <div v-if="n.ref_type === 'tenant_invitation'" class="invite-inline" @click.stop>
          <template v-if="n.inv_status === 'invited'">
            <el-button type="primary" size="small" :loading="actingInvId === n.ref_id" @click="acceptInv(n)">接受</el-button>
            <el-button size="small" plain :loading="actingInvId === n.ref_id" @click="declineInv(n)">拒绝</el-button>
          </template>
          <el-tag v-else size="small" :type="invStatusTag(n).type">{{ invStatusTag(n).text }}</el-tag>
        </div>
        <!-- 历史邀请通知 link 指向 /notifications 自身，视同无详情 -->
        <div v-else-if="n.buttons?.length" class="notify-buttons">
          <button v-for="(b, i) in n.buttons" :key="i" type="button" class="notify-link" @click.stop="open(n, b.link)">{{ b.label }}</button>
        </div>
        <button v-else-if="n.link && n.link !== '/notifications'" type="button" class="notify-link" @click.stop="open(n)">{{ notificationAction(n) }}</button>
        </div>
        <div class="notify-side">
          <div class="notify-meta">
            <time class="notify-time" :title="n.created_at">{{ fmtRelative(n.created_at) }}</time>
            <button type="button" class="del-btn" aria-label="删除通知" title="删除通知" @click.stop="removeOne(n)"><el-icon><Delete /></el-icon></button>
          </div>
        </div>
      </article>
      <el-pagination
        v-if="total > pageSize" v-model:current-page="page" :page-size="pageSize" :total="total"
        layout="total, prev, pager, next" style="margin-top: 14px; justify-content: flex-end"
        @current-change="load"
      />
    </section>

  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Bell, Timer, UserFilled, Share, Wallet } from '@element-plus/icons-vue'
import { deleteNotifications, getMe, listMyInvitations, acceptInvitation, declineInvitation, listNotificationsPage, markRead } from '../api'
import { fmtRelative } from '../utils/format'

const router = useRouter()
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const onlyUnread = ref(false)
const expandedMessages = reactive({})
const messageTypes = {
  automation: { kind: 'automation', label: '自动化', icon: Timer },
  invitation: { kind: 'invitation', label: '企业邀请', icon: UserFilled },
  friend: { kind: 'friend', label: '好友消息', icon: UserFilled },
  share: { kind: 'share', label: '协作分享', icon: Share },
  billing: { kind: 'billing', label: '账户服务', icon: Wallet },
  system: { kind: 'system', label: '系统通知', icon: Bell },
}
function notificationType(n) {
  if (n.ref_type === 'smart_automation') return messageTypes.automation
  if (n.ref_type === 'tenant_invitation') return messageTypes.invitation
  if (n.link === '/friends') return messageTypes.friend
  if (n.link === '/billing') return messageTypes.billing
  if (['/tables', '/mindmaps', '/shares'].includes(n.link)) return messageTypes.share
  return messageTypes.system
}
function notificationAction(n) {
  if (n.ref_type === 'smart_automation') return n.link?.includes('record=') ? '查看记录' : '查看数据表'
  if (n.link === '/friends') return '查看好友'
  if (notificationType(n).kind === 'share') return '查看分享'
  if (n.link === '/billing') return '查看账户'
  return '查看详情'
}

// 工作空间邀请：inv_status 随通知下发（无二次请求、无闪动）；
// invitations 仅用于接受后 toast 里的空间名，历史通知（无 inv_status）走 handledInv/已处理 兜底
const invitations = ref([])
const handledInv = reactive({})   // { [member_id]: 'accepted' | 'rejected' }（仅本次会话内的历史通知用）
const actingInvId = ref(null)

function invStatusTag(n) {
  if (n.inv_status === 'active') return { type: 'success', text: '已接受' }
  if (n.inv_status === 'declined') return { type: 'info', text: '已拒绝' }
  if (handledInv[n.ref_id] === 'accepted') return { type: 'success', text: '已接受' }
  if (handledInv[n.ref_id] === 'rejected') return { type: 'info', text: '已拒绝' }
  return { type: 'info', text: '已处理' }
}

async function loadInvitations() {
  try {
    invitations.value = await listMyInvitations()
  } catch { /* 邀请列表失败不阻塞通知本体 */ }
}

// 接受后刷新 grt_user（tenants 列表变了），顶栏工作空间切换器才能看到新空间
async function refreshMe() {
  const me = await getMe()
  localStorage.setItem('grt_user', JSON.stringify(me))
}

async function acceptInv(n) {
  const inv = invitations.value.find((x) => x.id === n.ref_id)
  actingInvId.value = n.ref_id
  try {
    await acceptInvitation(n.ref_id)
    await refreshMe()
    invitations.value = invitations.value.filter((x) => x.id !== n.ref_id)
    handledInv[n.ref_id] = 'accepted'
    n.inv_status = 'active'
    markInvRead(n)
    // 给「立即进入」出口，不用自己找切换器
    try {
      await ElMessageBox.confirm(
        `已加入「${inv?.tenant_name || ''}」。现在切换到该空间吗？`,
        '加入成功',
        { confirmButtonText: '立即进入', cancelButtonText: '稍后自己切换', type: 'success' },
      )
      const tenant = (JSON.parse(localStorage.getItem('grt_user') || '{}').tenants || []).find((t) => t.name === inv?.tenant_name)
      if (tenant) {
        const { switchTenant } = await import('../api')
        const payload = await switchTenant(tenant.id)
        localStorage.setItem('grt_user', JSON.stringify(payload))
        localStorage.setItem('grt_tenant_id', payload.tenant?.id || tenant.id)
        location.reload()
      }
    } catch { /* 稍后自己切换 */ }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    actingInvId.value = null
  }
}

async function declineInv(n) {
  actingInvId.value = n.ref_id
  try {
    await declineInvitation(n.ref_id)
    ElMessage.success('已拒绝')
    invitations.value = invitations.value.filter((x) => x.id !== n.ref_id)
    handledInv[n.ref_id] = 'rejected'
    n.inv_status = 'declined'
    markInvRead(n)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    actingInvId.value = null
  }
}

// 处理后顺手把该通知标为已读（同步侧边未读角标）
function markInvRead(n) {
  if (n.read) return
  markRead({ ids: [n.id] }).catch(() => {})
  n.read = true
  window.dispatchEvent(new Event('grt-notify-refresh'))
}

async function load() {
  loading.value = true
  try {
    const r = await listNotificationsPage({ page: page.value, page_size: pageSize, only_unread: onlyUnread.value })
    items.value = r.items
    total.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
}

async function open(n, buttonLink) {
  if (!n.read) {
    await markRead({ ids: [n.id] }).catch(() => {})
    n.read = true
    window.dispatchEvent(new Event('grt-notify-refresh'))   // 同步侧边菜单的未读角标
  }
  const link = buttonLink || n.link
  if (!link || link === '/notifications' || n.ref_type === 'tenant_invitation') return
  if (/^https?:\/\/[^\s]+$/i.test(link) && !link.includes('\\')) window.open(link, '_blank', 'noopener,noreferrer')
  else if (/^\/(?!\/)[^\s\\]*$/.test(link)) router.push(link)
}

async function readAll() {
  await markRead({ all: true }).catch(() => {})
  items.value.forEach((n) => { n.read = true })
  window.dispatchEvent(new Event('grt-notify-refresh'))
  if (onlyUnread.value) reload()
}

// 删除单条（悬停显示删除按钮，不冒泡到打开通知）；删了未读要同步侧边未读角标
async function removeOne(n) {
  try {
    await deleteNotifications({ ids: [n.id] })
    items.value = items.value.filter((x) => x.id !== n.id)
    total.value -= 1
    if (!n.read) window.dispatchEvent(new Event('grt-notify-refresh'))
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

// 清空全部已读通知（未读保留），需确认
async function clearRead() {
  try {
    await ElMessageBox.confirm('删除全部已读通知？（未读通知会保留）', '清空已读',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' })
  } catch { return }
  try {
    const r = await deleteNotifications({ read_only: true })
    ElMessage.success(`已清空 ${r.deleted} 条已读通知`)
    reload()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => { load(); loadInvitations() })
</script>

<style scoped>
/* .page-header 用 App.vue 全局样式，不在此重复定义 */
.header-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.notify-list { background: #fff; border: 1px solid #e9ecf0; border-radius: 8px; min-height: 160px; overflow: hidden; }
.notify-item { display: flex; align-items: flex-start; gap: 14px; padding: 18px 20px; border-bottom: 1px solid #eef0f3; cursor: pointer; }
.notify-item:last-of-type { border-bottom: 0; }
.notify-item:hover { background: #f7f9fc; }
.notify-item.unread { background: #f8fbff; }
.notify-item.unread:hover { background: #f1f6fd; }
.notify-item:focus-visible { outline: 2px solid #409eff; outline-offset: -2px; }
.notify-kind { display: flex; align-items: center; justify-content: center; position: relative; width: 38px; height: 38px; flex: none; border-radius: 10px; color: #737c8c; background: #f0f2f5; }
.notify-kind.automation { color: #377ce8; background: #eaf2ff; }
.notify-kind.invitation, .notify-kind.friend { color: #3c9270; background: #eaf7f1; }
.notify-kind.share { color: #2d969e; background: #e8f6f7; }
.notify-kind.billing { color: #b77a29; background: #fff5e8; }
.notify-unread-dot { position: absolute; right: -2px; top: -2px; width: 7px; height: 7px; border: 2px solid #fff; border-radius: 50%; background: #409eff; }
.notify-body { flex: 1; min-width: 0; }
.notify-heading { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px 10px; }
.notify-title { margin: 0; font-size: 15px; line-height: 24px; font-weight: 500; color: #303743; overflow-wrap: anywhere; }
.notify-item.unread .notify-title { font-weight: 600; color: #202632; }
.notify-source { font-size: 11px; line-height: 18px; padding: 0 5px; border-radius: 3px; color: #8a929e; background: #f0f2f5; white-space: nowrap; }
.notify-content { font-size: 13px; color: #737c89; margin-top: 5px; white-space: pre-wrap; line-height: 21px; overflow-wrap: anywhere; }
.notify-body .notify-content { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.notify-body .notify-content.expanded { display: block; }
.notify-expand { border: 0; background: none; padding: 3px 0 0; font: inherit; font-size: 12px; color: #7f8b9c; cursor: pointer; }
.notify-expand:hover { color: #3378de; }
.notify-side { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; flex: none; min-width: 118px; }
.notify-meta { display: flex; align-items: center; gap: 8px; height: 24px; }
.notify-time { color: #9da5b1; font-size: 12px; flex-shrink: 0; }
.del-btn { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; padding: 0; border: none; background: transparent; border-radius: 4px; color: #909399; cursor: pointer; opacity: 0; }
.notify-item:hover .del-btn, .notify-item:focus-within .del-btn { opacity: 1; }
.del-btn:hover { color: #f56c6c; background: #fff0f0; }
.notify-link { display: block; margin-top: 10px; padding: 3px 9px; border: 1px solid #e3e8ef; border-radius: 5px; background: #fff; color: #4a77b7; font: inherit; font-size: 12px; line-height: 22px; cursor: pointer; }
.notify-link:hover { border-color: #b6cdf0; background: #f0f6ff; color: #3378de; }
.notify-buttons { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; margin-top: 10px; }
.notify-buttons .notify-link { flex: 0 1 auto; min-width: 80px; max-width: 100%; margin-top: 0; padding: 3px 14px; overflow-wrap: anywhere; }
.notify-link:focus-visible, .del-btn:focus-visible, .notify-expand:focus-visible { outline: 2px solid #409eff; outline-offset: 2px; }
.notify-list :deep(.el-pagination) { padding: 0 20px 16px; }
@media (max-width: 600px) {
  .notify-item { flex-wrap: wrap; padding: 14px; gap: 10px; }
  .notify-kind { width: 32px; height: 32px; border-radius: 8px; }
  .notify-body { flex-basis: calc(100% - 42px); }
  .notify-side { flex: 1; flex-direction: row; align-items: center; justify-content: space-between; margin-left: 42px; }
  .del-btn { opacity: 1; }
}
.invite-inline { margin-top: 8px; display: flex; align-items: center; gap: 8px; }
</style>
