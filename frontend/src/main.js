import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

// 构建时间戳（排查"用户跑的是旧包"用）：控制台可见
console.info('[grt] build:', __BUILD_TIME__)
createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
