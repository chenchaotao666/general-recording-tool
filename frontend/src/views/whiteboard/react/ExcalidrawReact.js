// Excalidraw 的 React 组件封装（createElement 写法，无需 JSX/额外构建配置）
import React from 'react'
import { Excalidraw, MainMenu } from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'

const h = React.createElement

// 素材库面板精简（官方没有 props 开关，用 CSS 隐藏）：
// 1) 底部「浏览素材库」按钮（跳在线库浏览页）
// 2) 「个人素材库」区块——面板结构为 [个人区标题, 个人区内容, Excalidraw素材库标题, Excalidraw素材库网格]，
//    隐藏 Excalidraw 素材库标题之前的所有兄弟块即整个个人区（含其 ⋮ 菜单）
const LIB_CSS = `
  .wb-excalidraw .library-menu-browse-button { display: none !important; }
  .wb-excalidraw .library-menu-dropdown-container--in-heading { display: none !important; }
  .wb-excalidraw .library-menu-items-container__items > *:has(~ .library-menu-items-container__header--excal) {
    display: none !important;
  }
`

// props: initialData / onChange(elements, appState, files) / onApi(excalidrawAPI)
export default function ExcalidrawBoard({ initialData, onChange, onApi }) {
  return h(
    'div',
    { className: 'wb-excalidraw', style: { height: '100%', border: '1px solid #dcdfe6', borderRadius: 4, overflow: 'hidden' } },
    h('style', null, LIB_CSS),
    h(Excalidraw, {
      initialData,
      langCode: 'zh-CN',   // 内置简体中文语言包，工具栏/菜单/面板全翻译
      onChange: (elements, appState, files) => onChange?.(elements, appState, files),
      excalidrawAPI: (api) => onApi?.(api),
    },
      // 主菜单只保留：导出图片 / 查找文本 / 重置画布 / 画布背景
      // （打开/保存到/帮助/社交链接/深色模式去掉；本版「更多工具」菜单不含这几项，故放主菜单）
      h(MainMenu, null,
        h(MainMenu.DefaultItems.SaveAsImage),
        h(MainMenu.DefaultItems.SearchMenu),
        h(MainMenu.DefaultItems.ClearCanvas),
        h(MainMenu.DefaultItems.ChangeCanvasBackground)
      )
    )
  )
}
