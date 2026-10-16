// 字段类型图标（对齐参照截图 docs/智慧表格/添加列-所有字段类型.png）：16×16 线性 SVG，stroke=currentColor 单色
// 字母/数字类用 <text> 绘制，其余为几何描边；StIcon 与 FieldHeader 共用此表（单一数据源）

const T = (txt, size = 11, x = 3, y = 12.5) =>
  `<text x="${x}" y="${y}" font-size="${size}" fill="currentColor" stroke="none" font-family="Arial, sans-serif">${txt}</text>`

const CALENDAR = '<rect x="2.5" y="3.5" width="11" height="10" rx="1.5"/><path d="M2.5 7h11M5.5 2v2.5M10.5 2v2.5"/>'
const PERSON = '<circle cx="8" cy="5.5" r="2.5"/><path d="M3.5 13.5a4.5 4.5 0 019 0"/>'

export const FIELD_TYPE_ICONS = {
  // 基础
  text: `<rect x="2" y="2" width="12" height="12" rx="2"/>${T('A', 9.5, 5, 11.8)}`,
  singleSelect: '<circle cx="8" cy="8" r="6"/><path d="M5.3 8.2l1.8 1.8 3.6-4.2"/>',
  multiSelect: '<path d="M2.4 8.4l1.7 1.7 3.2-3.6"/><path d="M8.8 4.2H14M8.8 8H14M8.8 11.8H14"/>',
  number: T('123', 8, 1.5, 12),
  percent: T('%'),
  currency: `<circle cx="8" cy="8" r="6"/>${T('¥', 9, 5.1, 11.9)}`,
  progress: '<rect x="2" y="4.5" width="12" height="3" rx="1.5"/><rect x="2" y="9.5" width="7" height="3" rx="1.5"/>',
  date: CALENDAR,
  checkbox: '<rect x="3" y="3" width="10" height="10" rx="2"/><path d="M5.5 8.2l1.8 1.8 3.4-4"/>',
  // 标识
  url: '<path d="M6.5 9.5l3-3"/><path d="M8.7 5.3l1.4-1.4a2.5 2.5 0 013.5 3.5L12.2 8.8"/><path d="M7.3 10.7l-1.4 1.4a2.5 2.5 0 01-3.5-3.5l1.4-1.4"/>',
  phone: '<path d="M5.2 2.8h1.8l.9 2.8-1.4 1a8.5 8.5 0 002.9 2.9l1-1.4 2.8.9v1.8a1.2 1.2 0 01-1.2 1.2A10.5 10.5 0 012 4a1.2 1.2 0 011.2-1.2z"/>',
  email: '<rect x="2.5" y="4" width="11" height="8.5" rx="1.5"/><path d="M3 5.5l5 3.5 5-3.5"/>',
  autoNumber: T('1↓', 8.5, 2, 12.5),
  barcode: '<path d="M2.5 3v10M5 3v10M7.5 3v10M10 3v10M12 3v10M13.5 3v10"/>',
  location: '<path d="M8 14.2s-4.6-4.1-4.6-7.7a4.6 4.6 0 019.2 0c0 3.6-4.6 7.7-4.6 7.7z"/><circle cx="8" cy="6.4" r="1.6"/>',
  // 协作
  member: PERSON,
  groupChat: '<circle cx="6" cy="5.5" r="2.3"/><path d="M1.8 13.2a4.2 4.2 0 018.4 0"/><path d="M10.6 3.4a2.3 2.3 0 010 4.2M11.4 9.6a4.2 4.2 0 012.8 3.6"/>',
  // 媒体
  image: '<rect x="2.5" y="3" width="11" height="10" rx="1.5"/><circle cx="5.6" cy="6.4" r="1"/><path d="M3 12l3.3-3.3 2.4 2.4 1.6-1.6L13 12"/>',
  file: '<path d="M2.5 4.6A1.6 1.6 0 014.1 3h2.4l1.6 2h3.8a1.6 1.6 0 011.6 1.6v4.8a1.6 1.6 0 01-1.6 1.6H4.1a1.6 1.6 0 01-1.6-1.6z"/>',
  // 关联
  relation: '<rect x="2" y="5.2" width="5" height="5.6" rx="1"/><rect x="9" y="5.2" width="5" height="5.6" rx="1"/><path d="M7 8h2"/>',
  lookup: '<rect x="2" y="2.5" width="7.5" height="7.5" rx="1"/><path d="M2 5.2h7.5M5.2 2.5V10"/><circle cx="11" cy="11" r="2.4"/><path d="M12.8 12.8L15 15"/>',
  // 计算
  formula: '<text x="2.8" y="12.5" font-size="10.5" font-style="italic" fill="currentColor" stroke="none" font-family="Georgia, serif">fx</text>',
  // 系统（参照：创建人/最后编辑人=单人轮廓，创建时间/最后编辑时间=日历）
  createdBy: PERSON,
  lastModifiedBy: PERSON,
  createdTime: CALENDAR,
  lastModifiedTime: CALENDAR,
}

export function fieldTypeIconSvg(fieldType, size = 14) {
  const inner = FIELD_TYPE_ICONS[fieldType] || FIELD_TYPE_ICONS.text
  return `<svg viewBox="0 0 16 16" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`
}
