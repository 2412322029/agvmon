/**
 * Monaco（VS Code 同款编辑器内核）接线：注册 Lua 语言、主题、补全与悬浮文档。
 *
 * 只有 LuaEditor.vue 会 **动态 import** 本模块，所以 monaco 是独立 chunk，
 * 不进首屏包；加载失败时组件会退回纯 textarea 编辑器（见 LuaEditor.vue）。
 *
 * 关于体积：0.56 起 `editor.all.js` 没了，全部特性集中在 editor.main.js，而它还把
 * 60 多种语法和 TS/JSON/CSS 语言服务全带上。这里改成"editor.api + 按需 contrib"，
 * 只要能撑起 VS Code 手感的那部分：查找替换、智能提示、参数提示、悬浮文档、括号匹配、
 * 折叠、多光标、注释切换、粘性滚动。
 *
 * 注意 0.56 的 package.json exports 是 `"./*": "./esm/vs/*.js"`，所以子模块路径要写成
 * `monaco-editor/editor/...`；老写法 `monaco-editor/esm/vs/editor/...` 会被拼成
 * `esm/vs/esm/vs/...` 直接解析失败（vite build 会报 Rolldown failed to resolve）。
 */
import * as monaco from 'monaco-editor/editor/editor.api.js'

import 'monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching.js'
import 'monaco-editor/editor/contrib/clipboard/browser/clipboard.js'
import 'monaco-editor/editor/contrib/comment/browser/comment.js'
import 'monaco-editor/editor/contrib/contextmenu/browser/contextmenu.js'
import 'monaco-editor/editor/contrib/cursorUndo/browser/cursorUndo.js'
import 'monaco-editor/editor/contrib/find/browser/findController.js'
import 'monaco-editor/editor/contrib/folding/browser/folding.js'
import 'monaco-editor/editor/contrib/hover/browser/hoverContribution.js'
import 'monaco-editor/editor/contrib/indentation/browser/indentation.js'
import 'monaco-editor/editor/contrib/linesOperations/browser/linesOperations.js'
import 'monaco-editor/editor/contrib/multicursor/browser/multicursor.js'
import 'monaco-editor/editor/contrib/parameterHints/browser/parameterHints.js'
import 'monaco-editor/editor/contrib/smartSelect/browser/smartSelect.js'
import 'monaco-editor/editor/contrib/snippet/browser/snippetController2.js'
import 'monaco-editor/editor/contrib/stickyScroll/browser/stickyScrollContribution.js'
import 'monaco-editor/editor/contrib/suggest/browser/suggestController.js'
import 'monaco-editor/editor/contrib/unicodeHighlighter/browser/unicodeHighlighter.js'
import 'monaco-editor/editor/contrib/wordHighlighter/browser/wordHighlighter.js'
import 'monaco-editor/editor/contrib/wordOperations/browser/wordOperations.js'
import 'monaco-editor/editor/standalone/browser/quickAccess/standaloneCommandsQuickAccess.js'
import 'monaco-editor/editor/standalone/browser/quickAccess/standaloneGotoLineQuickAccess.js'
import 'monaco-editor/editor/standalone/browser/quickAccess/standaloneHelpQuickAccess.js'

// 词建议等少数特性跑在 worker 里；不给 worker 时 monaco 会在控制台报错。
//
// 必须用 `?worker&inline`：后端 CSP 是 `worker-src blob:`（backend/app.py 的
// add_security_headers），只允许 blob: 的 worker。默认的 `?worker` 会产出一个
// 同源文件 assets/editor.worker-*.js，浏览器会直接以
// "Creating a worker from 'http://…/assets/editor.worker-*.js' violates … worker-src blob:"
// 拦掉，monaco 只能退回主线程（控制台还会跟一条 uncaught Event）。
// &inline 让 vite 把 worker 打成 base64、运行时 URL.createObjectURL 出 blob: —— 体积
// 走 gzip 后与"单独一个 worker 文件"基本等价。改这里请同步改 test_user_script.py 的
// lua_worker_csp_problems()。
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker&inline'

import {
  CTX_MEMBERS,
  LUA_LANGUAGE_CONFIGURATION,
  LUA_LANGUAGE_ID,
  LUA_MONARCH,
  completionsFor,
  hoverDocFor,
} from './luaLanguage.js'

export { monaco }

const THEME_LIGHT = 'agvmon-lua-light'
const THEME_DARK = 'agvmon-lua-dark'

const FONT_FAMILY =
  "'Cascadia Mono', 'JetBrains Mono', Consolas, 'Courier New', ui-monospace, monospace"

// 语言配置里 indentAction 写的是字符串，这里映射成 monaco 的枚举
const INDENT_ACTIONS = {
  none: monaco.languages.IndentAction.None,
  indent: monaco.languages.IndentAction.Indent,
  outdent: monaco.languages.IndentAction.Outdent,
  indentOutdent: monaco.languages.IndentAction.IndentOutdent,
}

const COMPLETION_KINDS = {
  snippet: monaco.languages.CompletionItemKind.Snippet,
  keyword: monaco.languages.CompletionItemKind.Keyword,
  function: monaco.languages.CompletionItemKind.Function,
  property: monaco.languages.CompletionItemKind.Property,
  variable: monaco.languages.CompletionItemKind.Variable,
  constant: monaco.languages.CompletionItemKind.Constant,
}

let configured = false

/** 配置 monaco 的 worker 工厂（只做一次） */
function configureWorker() {
  const env = (globalThis.MonacoEnvironment = globalThis.MonacoEnvironment || {})
  if (typeof env.getWorker === 'function') return
  env.getWorker = () => new EditorWorker()
}

function defineThemes() {
  monaco.editor.defineTheme(THEME_LIGHT, {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'comment.lua', foreground: '7a8b99', fontStyle: 'italic' },
      { token: 'keyword.lua', foreground: '0000ff' },
      { token: 'string.lua', foreground: 'a31515' },
      { token: 'string.escape.lua', foreground: 'ee0000' },
      { token: 'string.escape.invalid.lua', foreground: 'ff0000' },
      { token: 'number.lua', foreground: '098658' },
      { token: 'type.identifier.lua', foreground: '795e26' },
      { token: 'variable.predefined.lua', foreground: '0070c1' },
      { token: 'property.lua', foreground: '001080' },
      { token: 'operator.lua', foreground: '000000' },
    ],
    colors: {
      'editor.background': '#ffffff',
      'editor.foreground': '#1f1f1f',
      'editorLineNumber.foreground': '#9aa0a6',
      'editorLineNumber.activeForeground': '#1677ff',
      'editor.lineHighlightBackground': '#f5f7fa',
      'editor.selectionBackground': '#add6ff',
      'editorCursor.foreground': '#1677ff',
      'editorIndentGuide.background1': '#ececec',
      'editorIndentGuide.activeBackground1': '#c9c9c9',
      'editorBracketMatch.background': '#d7e8ff',
      'editorBracketMatch.border': '#1677ff',
      'editorGutter.background': '#ffffff',
      'editorWidget.background': '#ffffff',
      'editorSuggestWidget.background': '#ffffff',
      'editorSuggestWidget.selectedBackground': '#e6f0ff',
      'minimap.background': '#fafafa',
      'scrollbarSlider.background': '#0000001a',
      'scrollbarSlider.hoverBackground': '#00000033',
    },
  })

  monaco.editor.defineTheme(THEME_DARK, {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment.lua', foreground: '6a9955', fontStyle: 'italic' },
      { token: 'keyword.lua', foreground: '569cd6' },
      { token: 'string.lua', foreground: 'ce9178' },
      { token: 'string.escape.lua', foreground: 'd7ba7d' },
      { token: 'string.escape.invalid.lua', foreground: 'f44747' },
      { token: 'number.lua', foreground: 'b5cea8' },
      { token: 'type.identifier.lua', foreground: 'dcdcaa' },
      { token: 'variable.predefined.lua', foreground: '4fc1ff' },
      { token: 'property.lua', foreground: '9cdcfe' },
      { token: 'operator.lua', foreground: 'd4d4d4' },
    ],
    colors: {
      'editor.background': '#1e1e1e',
      'editor.foreground': '#d4d4d4',
      'editorLineNumber.foreground': '#6b6b6b',
      'editorLineNumber.activeForeground': '#7cc4ff',
      'editor.lineHighlightBackground': '#262626',
      'editor.selectionBackground': '#264f78',
      'editorCursor.foreground': '#7cc4ff',
      'editorIndentGuide.background1': '#2b2b2b',
      'editorIndentGuide.activeBackground1': '#4a4a4a',
      'editorBracketMatch.background': '#1d3a5c',
      'editorBracketMatch.border': '#7cc4ff',
      'editorGutter.background': '#1e1e1e',
      'editorWidget.background': '#252526',
      'editorSuggestWidget.background': '#252526',
      'editorSuggestWidget.selectedBackground': '#094771',
      'minimap.background': '#1a1a1a',
      'scrollbarSlider.background': '#ffffff1a',
      'scrollbarSlider.hoverBackground': '#ffffff33',
    },
  })
}

/** 补全上下文：当前单词 + 单词之前的文本（用于判断 `json.` 这类成员访问） */
function completionItems(model, position) {
  const word = model.getWordUntilPosition(position)
  const line = model.getLineContent(position.lineNumber)
  const beforeWord = line.slice(0, Math.max(0, word.startColumn - 1))
  const range = new monaco.Range(
    position.lineNumber,
    word.startColumn,
    position.lineNumber,
    word.endColumn,
  )
  return {
    suggestions: completionsFor(word.word || '', beforeWord).map((item) => {
      const snippet = item.kind === 'snippet' && item.insertText
      return {
        label: item.label,
        kind: COMPLETION_KINDS[item.kind] || monaco.languages.CompletionItemKind.Text,
        detail: item.detail,
        documentation: item.documentation ? { value: item.documentation } : undefined,
        insertText: item.insertText || item.label,
        insertTextRules: snippet
          ? monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
          : undefined,
        sortText: item.sortText,
        range,
      }
    }),
  }
}

function hoverAt(model, position) {
  const word = model.getWordAtPosition(position)
  if (!word) return null
  const line = model.getLineContent(position.lineNumber)
  const before = line.slice(0, Math.max(0, word.startColumn - 1))
  const dotted = /([A-Za-z_]\w*)\.\s*$/.exec(before)
  const names = dotted ? [`${dotted[1]}.${word.word}`, word.word] : [word.word]

  for (const name of names) {
    const hit = hoverDocFor(name)
    if (!hit) continue
    const range = dotted && name.includes('.')
      ? new monaco.Range(position.lineNumber, word.startColumn - dotted[1].length - 1, position.lineNumber, word.endColumn)
      : new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn)
    return {
      range,
      contents: [{ value: `**\`${name}\`**` }, { value: hit.doc }],
    }
  }
  return null
}

export function setupLuaMonaco() {
  if (configured) return monaco
  configured = true

  configureWorker()

  monaco.languages.register({
    id: LUA_LANGUAGE_ID,
    extensions: ['.lua'],
    aliases: ['Lua', 'lua'],
  })

  monaco.languages.setLanguageConfiguration(LUA_LANGUAGE_ID, {
    ...LUA_LANGUAGE_CONFIGURATION,
    onEnterRules: (LUA_LANGUAGE_CONFIGURATION.onEnterRules || []).map((rule) => ({
      ...rule,
      action: {
        indentAction:
          INDENT_ACTIONS[rule.action?.indentAction] ?? monaco.languages.IndentAction.None,
      },
    })),
  })

  monaco.languages.setMonarchTokensProvider(LUA_LANGUAGE_ID, LUA_MONARCH)

  monaco.languages.registerCompletionItemProvider(LUA_LANGUAGE_ID, {
    triggerCharacters: ['.'],
    provideCompletionItems: completionItems,
  })

  monaco.languages.registerHoverProvider(LUA_LANGUAGE_ID, {
    provideHover: hoverAt,
  })

  defineThemes()
  return monaco
}

/** 当前 app 主题（App.vue 把主题写在 <html data-theme>） */
export function currentThemeName() {
  return document.documentElement.dataset.theme === 'dark' ? THEME_DARK : THEME_LIGHT
}

/** 监听主题切换，返回取消函数 */
export function watchTheme(callback) {
  const observer = new MutationObserver(() => callback(currentThemeName()))
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  })
  return () => observer.disconnect()
}

/**
 * 创建编辑器。
 *
 * @returns {{editor: object, dispose: Function}}
 */
export function createLuaEditor(container, options = {}) {
  const {
    value = '',
    readOnly = false,
    placeholder = '',
    onChange,
    onRun,
    onSave,
  } = options

  const editor = monaco.editor.create(container, {
    value,
    language: LUA_LANGUAGE_ID,
    theme: currentThemeName(),
    readOnly,
    placeholder: placeholder || undefined,
    automaticLayout: true,
    fontFamily: FONT_FAMILY,
    fontSize: 13,
    lineHeight: 20,
    fontLigatures: true,
    tabSize: 2,
    insertSpaces: true,
    detectIndentation: false,
    trimAutoWhitespace: false,
    minimap: { enabled: true, renderCharacters: false, maxColumn: 80, showSlider: 'mouseover' },
    scrollBeyondLastLine: false,
    smoothScrolling: true,
    cursorBlinking: 'smooth',
    cursorSmoothCaretAnimation: 'on',
    bracketPairColorization: { enabled: true },
    guides: { bracketPairs: 'active', indentation: true, highlightActiveIndentation: true },
    renderWhitespace: 'selection',
    renderLineHighlight: 'all',
    roundedSelection: true,
    wordWrap: 'off',
    fixedOverflowWidgets: true,
    suggest: {
      showWords: true,
      preview: true,
      snippetsPreventQuickSuggestions: false,
      insertMode: 'replace',
    },
    quickSuggestions: { other: true, comments: false, strings: false },
    suggestOnTriggerCharacters: true,
    tabCompletion: 'off',
    acceptSuggestionOnEnter: 'smart',
    hover: { enabled: true, delay: 200, above: false },
    parameterHints: { enabled: true, cycle: true },
    folding: true,
    showFoldingControls: 'mouseover',
    unfoldOnClickAfterEndOfLine: true,
    glyphMargin: false,
    lineNumbersMinChars: 3,
    lineDecorationsWidth: 8,
    padding: { top: 8, bottom: 12 },
    scrollbar: {
      verticalScrollbarSize: 10,
      horizontalScrollbarSize: 10,
      useShadows: false,
      alwaysConsumeMouseWheel: false,
    },
    stickyScroll: { enabled: true, maxLineCount: 3 },
    // 中文注释里全是"歧义字符"，别让它到处画框
    unicodeHighlight: { ambiguousCharacters: false, nonBasicASCII: false },
    renderControlCharacters: false,
    wordBasedSuggestions: 'currentDocument',
    scrollBeyondLastColumn: 4,
    stickyTabStops: false,
  })

  const runAction = () => onRun && onRun()
  const saveAction = () => onSave && onSave()
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, runAction)
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveAction)
  // Ctrl+Enter 在部分键盘布局下也走这个
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.Enter, runAction)

  const subscription = editor.onDidChangeModelContent(() => {
    if (onChange) onChange(editor.getValue())
  })

  return {
    editor,
    monaco,
    /** 整篇替换，但保留撤销栈（外部改动用，比如打开另一个脚本） */
    replaceAll(text) {
      const model = editor.getModel()
      if (!model || model.getValue() === text) return
      editor.pushUndoStop()
      editor.executeEdits('lua-editor-sync', [
        { range: model.getFullModelRange(), text: text ?? '', forceMoveMarkers: true },
      ])
      editor.pushUndoStop()
    },
    setReadOnly(flag) {
      editor.updateOptions({ readOnly: !!flag })
    },
    setTheme(name) {
      monaco.editor.setTheme(name)
    },
    dispose() {
      subscription.dispose()
      const model = editor.getModel()
      editor.dispose()
      if (model) model.dispose()
    },
  }
}

/** 供测试/调试：目录里有哪些名字 */
export const LUA_CTX_MEMBERS = CTX_MEMBERS
