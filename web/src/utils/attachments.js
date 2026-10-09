/**
 * 任务附件/链接的共用分类与展示辅助。
 * 附件在数据层是字符串数组：http(s) 开头 = 链接，其余 = 本地文件路径。
 */
const IMG_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico']
const TXT_EXTS = [
  'txt', 'md', 'markdown', 'json', 'log', 'csv', 'ini', 'conf', 'toml',
  'yml', 'yaml', 'xml', 'html', 'css', 'js', 'ts', 'vue', 'py', 'sh',
  'bat', 'ps1', 'java', 'c', 'h', 'cpp', 'go', 'rs', 'rb', 'sql',
]
const OFFICE_EXTS = ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'pdf']

export function isLink(a) {
  return /^https?:\/\//i.test(a)
}

function extOf(a) {
  const i = a.lastIndexOf('.')
  return i >= 0 ? a.slice(i + 1).toLowerCase() : ''
}

/** link | image | text | office | file（image 缩略图，link 走浏览器，其余系统默认应用） */
export function attKind(a) {
  if (isLink(a)) return 'link'
  const e = extOf(a)
  if (IMG_EXTS.includes(e)) return 'image'
  if (TXT_EXTS.includes(e)) return 'text'
  if (OFFICE_EXTS.includes(e)) return 'office'
  return 'file'
}

export function attIcon(a) {
  return { link: '🔗', image: '🖼️', text: '📄', office: '📊', file: '📎' }[attKind(a)]
}

export function attLabel(a) {
  if (isLink(a)) {
    try { return new URL(a).hostname } catch { return a }
  }
  const i = Math.max(a.lastIndexOf('/'), a.lastIndexOf('\\'))
  return i >= 0 ? a.slice(i + 1) : a
}

export function openHint(a) {
  if (isLink(a)) return '点击在浏览器打开'
  return `点击用系统默认应用打开：${a}`
}
