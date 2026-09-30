// renderMd 回归断言（node web/tests/md.test.mjs）——重点：列表消费必须推进游标。
// 由来：PluginDocDrawer 内联版 flushUl 缺 i++，README 含列表即死循环卡死面板。
import assert from 'node:assert/strict'
import { renderMd } from '../src/utils/md.js'

// 1) 列表终止 + 正确渲染（原 bug：此用例永不返回）
assert.equal(renderMd('- 甲\n- 乙'), '<ul><li>甲</li><li>乙</li></ul>')
// 2) 有序列表 + 列表后段落继续解析
assert.equal(renderMd('1. 一\n2. 二\n\n尾巴'), '<ol><li>一</li><li>二</li></ol>\n<p>尾巴</p>')
// 3) 列表与段落交界（flushUl 必须停在非列表行）
assert.equal(renderMd('开头\n* 项\n结尾'), '<p>开头</p>\n<ul><li>项</li></ul>\n<p>结尾</p>')
// 4) 大列表有界耗时（防退化回死循环）
{
  const t0 = Date.now()
  renderMd('- 项\n'.repeat(5000))
  assert.ok(Date.now() - t0 < 2000, '大列表渲染应线性完成')
}
// 5) 表格/代码块/标题/行内语法
assert.ok(renderMd('| a | b |\n|---|---|\n| 1 | 2 |').includes('<th>a</th>'))
assert.ok(renderMd('```\n<x>&\n```').includes('&lt;x&gt;&amp;'))
assert.ok(renderMd('## 标').startsWith('<h2>'))
assert.ok(renderMd('**粗** `码` [链](https://a.b)').includes('<b>粗</b>'))
// 6) 转义：README 原文 HTML 不落地
assert.ok(!renderMd('<script>x</script>').includes('<script>'))
console.log('md.test.mjs: 6/6 PASS')
