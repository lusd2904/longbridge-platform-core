import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { setupNativeRuntime } from './utils/nativeRuntime.js'
import './styles/experience.scss'

import 'element-plus/theme-chalk/el-loading.css'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')

setupNativeRuntime(router).catch((error) => {
  console.warn('Native runtime 初始化失败', error)
})
