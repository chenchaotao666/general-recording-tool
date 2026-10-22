import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import 'element-plus/dist/index.css'
import VxeUITable from 'vxe-table'
import 'vxe-table/lib/style.css'
import App from './App.vue'
import router from './router'
import { mountAfterRouteReady } from './bootstrap.js'
import './styles/tree-dnd.css'   // 树形目录拖拽排序通用样式（useTreeDnd/DndHandle 配套）
import './smart/tokens.css'   // 智慧表格设计令牌（对齐参照截图，docs/智慧表格差距分析.md §0）
import './smart/scrollbars.css'
import './smart/reorder.css'
import { installScrollbarHover } from './smart/utils/scrollbarHover.js'
import { installSmartTooltips } from './smart/utils/tooltips.js'
const disposeScrollbarHover = installScrollbarHover()
if (import.meta.hot) import.meta.hot.dispose(disposeScrollbarHover)
const disposeSmartTooltips = installSmartTooltips()
if (import.meta.hot) import.meta.hot.dispose(disposeSmartTooltips)

// 构建时间戳（排查"用户跑的是旧包"用）：控制台可见
console.info('[grt] build:', __BUILD_TIME__)
dayjs.locale('zh-cn')
const app = createApp(App).use(router).use(ElementPlus, { locale: zhCn }).use(VxeUITable)
mountAfterRouteReady(app, router).catch(error => {
  console.error('[grt] startup failed:', error)
  document.getElementById('app').textContent = '页面加载失败，请刷新重试。'
})
