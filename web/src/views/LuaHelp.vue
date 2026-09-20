<template>
  <div class="lua-help-page">
    <!-- 顶部说明条 -->
    <n-card size="small" :bordered="false" class="head-card">
      <div class="head">
        <div class="head-main">
          <h2 class="title">
            Lua 帮助
            <n-tag size="tiny" :bordered="false" type="info">随前端打包</n-tag>
          </h2>
          <p class="desc">
            本页内容来自仓库根目录的 <code>LUA_SCRIPT_GUIDE.md</code>，通过 Vite
            <code>?raw</code> 在构建时打包进前端，与后端实现保持同源、无需联网即可查看。
            要写 / 跑脚本，请前往
            <router-link to="/user-script">用户脚本</router-link> 页。
          </p>
        </div>
        <n-space align="center" size="small">
          <n-button size="small" type="primary" @click="backToEditor">去写脚本</n-button>
        </n-space>
      </div>
    </n-card>

    <!-- 指南正文 -->
    <n-card size="small" :bordered="false">
      <div class="lua-guide-markdown" v-html="html"></div>
    </n-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NSpace, NTag } from 'naive-ui'
import { marked } from 'marked'
// Vite 的 `?raw`：把 markdown 当纯文本打包进 bundle，而不是复制文件到 public
import guideRaw from '../../../LUA_SCRIPT_GUIDE.md?raw'

const router = useRouter()

/**
 * 生成 GitHub 风格的标题 id，让文内目录里的 `#1-30-秒速览先看这个` 这类锚点能跳转。
 * 算法与 GitHub 一致：转小写、去掉标点（保留 CJK / 字母 / 数字 / 连字符）、空格转 `-`。
 */
function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, '')
    .trim()
    .replace(/\s+/g, '-')
}

// 给标题注入 id；其余元素全部用 marked 默认渲染器（GFM：表格 / 围栏代码块等）
marked.use({
  gfm: true,
  renderer: {
    heading({ tokens, depth }) {
      const inner = this.parser.parseInline(tokens)
      const plain = inner.replace(/<[^>]+>/g, '')
      return `<h${depth} id="${slugify(plain)}">${inner}</h${depth}>\n`
    },
  },
})

const html = computed(() => marked.parse(guideRaw))

function backToEditor() {
  router.push('/user-script')
}
</script>

<style>
/* v-html 内容不会带上 scoped 属性，所以这里用非 scoped 样式，并统一收敛到
   .lua-guide-markdown 前缀下，避免污染其它页面。 */
.lua-help-page {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lua-help-page .head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.lua-help-page .title {
  margin: 0 0 4px;
  font-size: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.lua-help-page .desc {
  margin: 0;
  font-size: 13px;
  color: #8a8a8a;
  line-height: 1.6;
  max-width: 900px;
}

.lua-help-page .desc code {
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(128, 128, 128, 0.16);
  font-family: ui-monospace, Consolas, monospace;
}

.lua-guide-markdown {
  font-size: 14px;
  line-height: 1.75;
  color: #333;
  word-wrap: break-word;
}

.lua-guide-markdown h1 {
  font-size: 24px;
  line-height: 1.3;
  border-bottom: 1px solid #e5e5e5;
  padding-bottom: 8px;
  margin: 20px 0 14px;
}

.lua-guide-markdown h2 {
  font-size: 20px;
  border-bottom: 1px solid #eee;
  padding-bottom: 6px;
  margin: 22px 0 10px;
}

.lua-guide-markdown h3 {
  font-size: 16px;
  margin: 18px 0 8px;
}

.lua-guide-markdown h4 {
  font-size: 14px;
  margin: 14px 0 6px;
}

.lua-guide-markdown p {
  margin: 0 0 10px;
}

.lua-guide-markdown a {
  color: #1890ff;
  text-decoration: none;
}

.lua-guide-markdown a:hover {
  text-decoration: underline;
}

.lua-guide-markdown code {
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(128, 128, 128, 0.16);
  font-family: ui-monospace, SFMono-Regular, Consolas, 'Cascadia Mono', monospace;
  font-size: 13px;
}

.lua-guide-markdown pre {
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(128, 128, 128, 0.12);
  overflow-x: auto;
  margin: 0 0 12px;
}

.lua-guide-markdown pre code {
  padding: 0;
  background: transparent;
  font-size: 12.5px;
  line-height: 1.6;
}

.lua-guide-markdown table {
  border-collapse: collapse;
  display: block;
  width: 100%;
  overflow-x: auto;
  margin: 10px 0 14px;
}

.lua-guide-markdown th,
.lua-guide-markdown td {
  border: 1px solid #ddd;
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}

.lua-guide-markdown th {
  background: rgba(128, 128, 128, 0.12);
  font-weight: 600;
  white-space: nowrap;
}

.lua-guide-markdown blockquote {
  margin: 0 0 12px;
  padding: 4px 14px;
  border-left: 4px solid #1890ff;
  color: #666;
  background: rgba(24, 144, 255, 0.06);
  border-radius: 0 4px 4px 0;
}

.lua-guide-markdown blockquote p {
  margin: 4px 0;
}

.lua-guide-markdown ul,
.lua-guide-markdown ol {
  padding-left: 22px;
  margin: 0 0 10px;
}

.lua-guide-markdown li {
  margin: 2px 0;
}

.lua-guide-markdown hr {
  border: none;
  border-top: 1px solid #e5e5e5;
  margin: 18px 0;
}

.lua-guide-markdown img {
  max-width: 100%;
}

/* 暗色主题 */
[data-theme='dark'] .lua-guide-markdown {
  color: #d5d5d5;
}

[data-theme='dark'] .lua-guide-markdown h1,
[data-theme='dark'] .lua-guide-markdown h2 {
  border-color: #444;
}

[data-theme='dark'] .lua-guide-markdown th,
[data-theme='dark'] .lua-guide-markdown td {
  border-color: #444;
}

[data-theme='dark'] .lua-guide-markdown th {
  background: rgba(255, 255, 255, 0.08);
}

[data-theme='dark'] .lua-guide-markdown blockquote {
  color: #bbb;
  background: rgba(24, 144, 255, 0.1);
}

[data-theme='dark'] .lua-guide-markdown pre {
  background: rgba(0, 0, 0, 0.35);
}

[data-theme='dark'] .lua-guide-markdown hr {
  border-top-color: #444;
}
</style>
