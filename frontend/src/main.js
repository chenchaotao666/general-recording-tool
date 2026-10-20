import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import VxeUITable from 'vxe-table'
import 'vxe-table/lib/style.css'
import App from './App.vue'
import router from './router'
import './styles/tree-dnd.css'   // 树形目录拖拽排序通用样式（useTreeDnd/DndHandle 配套）
import './smart/tokens.css'   // 智慧表格设计令牌（对齐参照截图，docs/智慧表格差距分析.md §0）
import { installScrollbarHover } from './smart/utils/scrollbarHover.js'
import { installSmartTooltips } from './smart/utils/tooltips.js'
installScrollbarHover()   // 智能表格滚动条悬停加粗
const disposeSmartTooltips = installSmartTooltips()
if (import.meta.hot) import.meta.hot.dispose(disposeSmartTooltips)

// 构建时间戳（排查"用户跑的是旧包"用）：控制台可见
console.info('[grt] build:', __BUILD_TIME__)
createApp(App).use(router).use(ElementPlus, { locale: zhCn }).use(VxeUITable).mount('#app')
