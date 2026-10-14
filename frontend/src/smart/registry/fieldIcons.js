// 字段类型图标（设计稿 PixPin_2026-10-15_00-04-29 风格）：16×16 线性 SVG，stroke=currentColor 单色
// 字母类用 <text> 绘制，其余为简单几何描边；供 FieldHeader 等处以 v-html 内联渲染

const T = (txt, size = 11, x = 3, y = 12.5) =>
  `<text x="${x}" y="${y}" font-size="${size}" fill="currentColor" stroke="none" font-family="Arial, sans-serif">${txt}</text>`

export const FIELD_TYPE_ICONS = {
  text: T('A'),
  singleSelect: '<circle cx="8" cy="8" r="5.5"/><circle cx="8" cy="8" r="2" fill="currentColor" stroke="none"/>',
  multiSelect: '<path d="M3 4.5h10M3 8h10M3 11.5h10"/>',
  number: T('123', 8, 1.5, 12),   // 9px 时三位数字宽出 16 视口被裁，缩到 8px
  percent: T('%'),
  currency: T('¥'),
  date: '<rect x="2.5" y="3.5" width="11" height="10" rx="1.5"/><path d="M2.5 7h11M5.5 2v2.5M10.5 2v2.5"/>',
  checkbox: '<rect x="3" y="3" width="10" height="10" rx="2"/><path d="M5.5 8.2l1.8 1.8 3.4-4"/>',
  url: '<path d="M6.5 9.5l3-3"/><path d="M8.7 5.3l1.4-1.4a2.5 2.5 0 013.5 3.5L12.2 8.8"/><path d="M7.3 10.7l-1.4 1.4a2.5 2.5 0 01-3.5-3.5l1.4-1.4"/>',
  phone: '<path d="M5.2 2.8h1.8l.9 2.8-1.4 1a8.5 8.5 0 002.9 2.9l1-1.4 2.8.9v1.8a1.2 1.2 0 01-1.2 1.2A10.5 10.5 0 012 4a1.2 1.2 0 011.2-1.2z"/>',
  email: '<rect x="2.5" y="4" width="11" height="8.5" rx="1.5"/><path d="M3 5.5l5 3.5 5-3.5"/>',
  member: '<circle cx="8" cy="5.5" r="2.5"/><path d="M3.5 13.5a4.5 4.5 0 019 0"/>',
  progress: '<rect x="2" y="6" width="12" height="4" rx="2"/><rect x="2" y="6" width="7" height="4" rx="2" fill="currentColor" stroke="none"/>',
  image: '<rect x="2.5" y="3" width="11" height="10" rx="1.5"/><circle cx="5.6" cy="6.4" r="1"/><path d="M3 12l3.3-3.3 2.4 2.4 1.6-1.6L13 12"/>',
  file: '<path d="M4.8 2.8h4.2l3 2.8v7.6a.8.8 0 01-.8.8H4.8a.8.8 0 01-.8-.8V3.6a.8.8 0 01.8-.8z"/><path d="M9 2.8v2.8h3"/>',
  autoNumber: T('1↓', 8.5, 2, 12.5),
  relation: '<rect x="2" y="5.2" width="5" height="5.6" rx="1"/><rect x="9" y="5.2" width="5" height="5.6" rx="1"/><path d="M7 8h2"/>',
  lookup: '<circle cx="7" cy="7" r="3.6"/><path d="M9.6 9.6L13 13"/>',
  formula: '<text x="2.8" y="12.5" font-size="10.5" font-style="italic" fill="currentColor" stroke="none" font-family="Georgia, serif">fx</text>',
  createdBy: '<circle cx="8" cy="5.5" r="2.5"/><path d="M3.5 13.5a4.5 4.5 0 019 0"/>',
  lastModifiedBy: '<circle cx="8" cy="5.5" r="2.5"/><path d="M3.5 13.5a4.5 4.5 0 019 0"/>',
  createdTime: '<circle cx="8" cy="8" r="5.5"/><path d="M8 4.8V8l2.4 1.5"/>',
  lastModifiedTime: '<circle cx="8" cy="8" r="5.5"/><path d="M8 4.8V8l2.4 1.5"/>',
}

export function fieldTypeIconSvg(fieldType) {
  const inner = FIELD_TYPE_ICONS[fieldType] || FIELD_TYPE_ICONS.text
  return `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`
}
