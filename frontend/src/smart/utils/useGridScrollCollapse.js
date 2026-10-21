import { inject, watch } from 'vue'

export function useGridScrollCollapse(active, collapse) {
  const subscribe = inject('smartGridScrollCollapse', null)
  if (!subscribe) return
  watch(active, (visible, _, onCleanup) => {
    if (visible) onCleanup(subscribe(collapse))
  }, { immediate: true, flush: 'sync' })
}
