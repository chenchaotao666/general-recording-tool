/** 通用离开保护：有未保存修改时拦截浏览器关闭/刷新（beforeunload）与 SPA 路由跳转。
 *
 * 用法：
 *   const dirty = ref(false)           // 编辑时置 true，保存成功后置 false
 *   useDirtyGuard(() => dirty.value)   // 或用 computed/已有状态
 *
 * isDirty 传函数/ref/computed 均可；message 可自定义。
 */
import { onBeforeUnmount, onMounted, unref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'

export function useDirtyGuard(isDirty, message = '当前有未保存的修改，离开后修改将丢失。') {
  const check = () => (typeof isDirty === 'function' ? isDirty() : unref(isDirty))

  const onBeforeUnload = (e) => {
    if (check()) {
      e.preventDefault()
      e.returnValue = ''
    }
  }

  onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))

  onBeforeRouteLeave(async () => {
    if (!check()) return true
    try {
      await ElMessageBox.confirm(message, '未保存的修改', {
        type: 'warning',
        confirmButtonText: '离开',
        cancelButtonText: '留下',
      })
      return true
    } catch {
      return false
    }
  })
}
