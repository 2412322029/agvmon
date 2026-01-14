import axios from 'axios'
import { create, NLoadingBarProvider } from 'naive-ui'
import { createApp, h } from 'vue'
import App from './App.vue'
import router from './router'

// 创建Naive UI实例
const naive = create({
  // 全局配置
  configProvider: {
    theme: 'light',
  },
})

// 创建根组件，使用NLoadingBarProvider包裹
const Root = {
  render() {
    return h(NLoadingBarProvider, null, {
      default: () => h(App)
    })
  }
}

// 创建Vue应用实例
const app = createApp(Root)

// 配置axios
axios.defaults.baseURL = '/api'
app.config.globalProperties.$axios = axios

// 使用插件
app.use(router)
app.use(naive)

// 挂载应用
app.mount('#app')
