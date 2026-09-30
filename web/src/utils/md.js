/** 极简 markdown 渲染（标题/表格/代码块/列表/粗体/行内码/链接），输入先整体转义。
 * 供 PluginDocDrawer 使用；独立成纯模块以便 node 直接断言（web/tests/md.test.mjs）。 */
export function renderMd(src) {
  const esc = (s) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  const inline = (s) =>
    esc(s)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
      .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
  const lines = src.split('\n')
  const out = []
  let i = 0
  const flushUl = (tag, pat) => {
    const items = []
    while (i < lines.length && pat.test(lines[i])) {
      items.push(`<li>${inline(lines[i].replace(pat, ''))}</li>`)
      i++
    }
    if (items.length) out.push(`<${tag}>${items.join('')}</${tag}>`)
  }
  while (i < lines.length) {
    const l = lines[i]
    if (l.startsWith('```')) {
      const buf = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++])
      i++
      out.push(`<pre>${esc(buf.join('\n'))}</pre>`)
    } else if (/^\|.*\|/.test(l)) {
      const rows = []
      while (i < lines.length && /^\|/.test(lines[i])) {
        const cells = lines[i].split('|').slice(1, -1).map((c) => c.trim())
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells) // 跳过分隔行
        i++
      }
      const row = (cells, tag) =>
        `<tr>${cells.map((c) => `<${tag}>${inline(c)}</${tag}>`).join('')}</tr>`
      out.push(
        rows.length
          ? `<table class="pdd-table"><tbody>${rows
              .map((r, k) => row(r, k === 0 ? 'th' : 'td'))
              .join('')}</tbody></table>`
          : '',
      )
    } else if (/^#{1,4} /.test(l)) {
      const h = l.match(/^(#+) /)[1].length
      out.push(`<h${h}>${inline(l.slice(h + 1))}</h${h}>`)
      i++
    } else if (/^\s*[-*] /.test(l)) {
      flushUl('ul', /^\s*[-*] /)
    } else if (/^\s*\d+\. /.test(l)) {
      flushUl('ol', /^\s*\d+\. /)
    } else if (!l.trim()) {
      i++
    } else {
      out.push(`<p>${inline(l)}</p>`)
      i++
    }
  }
  return out.filter(Boolean).join('\n')
}
