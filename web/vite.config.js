import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vueDevTools from "vite-plugin-vue-devtools";

const buildTimePlugin = {
  name: "build-time",
  configResolved(config) {
    const buildTime = new Date().toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    config.define.__BUILD_TIME__ = JSON.stringify(buildTime);
  },
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    buildTimePlugin,
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) =>
            tag === "view-json" || tag.startsWith("vscode-"),
        },
      },
    }),
    vueDevTools(),
  ],
  build: {
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            // monaco（VS Code 编辑器内核，~3.4MB）是「用户脚本」页里动态 import 进来的，
            // 这里返回 undefined 交给 rolldown 自动分包：只有打开那个页面才会下载。
            // 注意别把 monaco 塞进 vendor —— 那样每个页面首屏都要多下 3.4MB；
            // 也别给它手工指定 chunk 名 —— 试过，preload helper 会被一起塞进那个
            // chunk，反而让入口 chunk 静态 import 它，同样变成首屏加载。
            if (id.includes("monaco-editor")) {
              return undefined;
            }
            return "vendor";
          }
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // 允许 dev server 读取 web/ 目录之外的仓库根目录文件（LUA_SCRIPT_GUIDE.md 用 ?raw 引入）
    fs: {
      allow: ['..'],
    },
    // 配置代理服务器
    proxy: {
      // API 代理
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // 静态文件代理
      "/static": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/static/, ''),
      },
      // Swagger UI 代理
      "/docs": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/docs/, ''),
      },
      // ReDoc 代理
      "/redoc": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/redoc/, ''),
      },
      // openapi.json 代理
      "/openapi.json": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/openapi.json/, ''),
      },
      // WebSocket 代理
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
    // 监听端口
    port: 3000,
    // 自动打开浏览器
    open: true,
  },
});
