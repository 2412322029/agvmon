import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vueDevTools from 'vite-plugin-vue-devtools'

const buildTimePlugin = {
  name: 'build-time',
  configResolved(config) {
    const buildTime = new Date().toLocaleString('zh-CN', { 
      year: 'numeric', 
      month: '2-digit', 
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
    config.define.__BUILD_TIME__ = JSON.stringify(buildTime);
  }
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    buildTimePlugin,
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => tag === 'view-json' || tag.startsWith('vscode-')
        }
      }
    }),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    // 配置代理服务器
    proxy: {
      // API 代理
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // 静态文件代理
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/static/, ''),
      },
      // Swagger UI 代理
      '/docs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/docs/, ''),
      },
      // ReDoc 代理
      '/redoc': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/redoc/, ''),
      },
      // openapi.json 代理
      '/openapi.json': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/openapi.json/, ''),
      },
      // WebSocket 代理
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
    // 监听端口
    port: 3000,
    // 自动打开浏览器
    open: true,
  },
})
