// 卡片级自动刷新：config.refresh（秒，0=关闭）驱动定时重取数据
import { onUnmounted, watch } from 'vue'

export function useAutoRefresh(getConfig, reload) {
  let timer = null
  const setup = () => {
    if (timer) { clearInterval(timer); timer = null }
    const sec = Number(getConfig()?.refresh) || 0
    if (sec > 0) timer = setInterval(reload, sec * 1000)
  }
  watch(() => getConfig()?.refresh, setup, { immediate: true })
  onUnmounted(() => { if (timer) clearInterval(timer) })
}
