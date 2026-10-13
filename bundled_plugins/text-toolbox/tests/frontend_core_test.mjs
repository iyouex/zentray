// 前端核心纯函数自测：从 ../index.html 抽取 //<<<CORE … //CORE>>> 内联脚本，
// 在 node vm 中执行同一份代码后断言。用法：
//   node tests/frontend_core_test.mjs            # 全量 + 产出 JS 侧 AES 向量
//   node tests/frontend_core_test.mjs --verify-py # 校验 python cryptography 产出的向量
import { readFileSync, writeFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert';
const j = x => JSON.stringify(x);  // vm 跨 realm 数组原型不同，序列化后比较

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const m = html.match(/\/\/<<<CORE[\s\S]*?\n\/\/CORE>>>/);
assert.ok(m, 'index.html 中未找到 CORE 标记块');
const ctx = vm.createContext({
  console, Math, Date, JSON, String, Number, RegExp, Object, Array,
  TextEncoder, TextDecoder, Uint8Array, Uint32Array, DataView,
  crypto: globalThis.crypto, btoa: globalThis.btoa, atob: globalThis.atob,
});
vm.runInContext(m[0], ctx);
const T = ctx.TT_CORE;
assert.ok(T, 'TT_CORE 未导出');

let n = 0;
const ok = name => { n++; console.log(`[PASS] ${name}`); };

/* ---------- MD5 已知向量 ---------- */
assert.equal(T.md5hex(''), 'd41d8cd98f00b204e9800998ecf8427e');
assert.equal(T.md5hex('abc'), '900150983cd24fb0d6963f7d28e17f72');
assert.equal(T.md5hex('message digest'), 'f96b697d7cb7938d525a2f31aaf161d0');
assert.equal(T.md5hex('abcdefghijklmnopqrstuvwxyz'), 'c3fcd3d76192e4007dfb496cca67e13b');
// 62 字符 → 两个 64B 块，验证跨块与长度填充
assert.equal(T.md5hex('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'),
  'd174ab98d277d9f5a5611c2c9f419d9f');
assert.equal(T.md5hex('中文摘要测试'), '782d3b349cf3d83f0dd0ff0459a8b32d');  // hashlib.md5 对照
ok('md5 已知向量 x5 + UTF-8 路径（python hashlib 对照向量）');

/* ---------- JSON 修复启发式 ---------- */
const cases = [
  ["{a: 1,}", { a: 1 }],
  ["{'x': 'it\\'s', 'y': \"q\"}", { x: "it's", y: 'q' }],
  ["[1, 2, 3,]", [1, 2, 3]],
  ["{a: 1, b: [True, False, None]}", { a: 1, b: [true, false, null] }],
  ["// 注释\n{\"k\": 1, /* 块注释 */ \"j\": 2,}", { k: 1, j: 2 }],
  ["{'嵌套': {'深': [1,]}}", { 嵌套: { 深: [1] } }],
];
for (const [src, want] of cases) {
  assert.equal(j(JSON.parse(T.jsonHeuristicRepair(src))), j(want), src);
}
assert.equal(T.jsonHeuristicRepair("{'a': 1}") === '{"a": 1}', true);
ok(`json 启发式修复 ${cases.length} 组`);
// jsonRepairBest 在无 CDN 全局时走 heuristic
assert.equal(T.jsonRepairBest('{a:1}').engine, 'heuristic');
assert.equal(j(JSON.parse(T.jsonRepairBest('{a:1,}').text)), j({ a: 1 }));
ok('jsonRepairBest 降级路径');
// jsonErrInfo：V8 position → 行/列（jsonlint 风格定位）
try { JSON.parse('{\n  "a": 1,\n  "b" oops\n}'); assert.fail('应抛错'); }
catch (e) {
  const info = T.jsonErrInfo(e, '{\n  "a": 1,\n  "b" oops\n}');
  assert.equal(info.name, 'SyntaxError');
  assert.equal(info.line, 3);
  assert.ok(info.col >= 4 && info.col <= 8, 'col 指向第 3 行出错字符: ' + info.col);
}
assert.deepEqual(
  { line: T.jsonErrInfo(new SyntaxError('x at position 3'), 'ab\ncd').line, col: T.jsonErrInfo(new SyntaxError('x at position 3'), 'ab\ncd').col },
  { line: 2, col: 1 });
ok('jsonErrInfo 行列提取');
// jsonStats：大小/键数/深度/对象/数组（jsonlint Valid JSON 横幅统计）
const st = T.jsonStats(JSON.parse('{"a":{"b":[1,{"c":2}]}}'), '{"a":{"b":[1,{"c":2}]}}');
assert.equal(j(st), j({ sizeFormatted: '23 bytes', keys: 3, depth: 4, objects: 3, arrays: 1 }));
assert.equal(T.jsonStats({}, 'x'.repeat(2048)).sizeFormatted, '2.0 KB');
ok('jsonStats 统计');

/* ---------- diff LCS ---------- */
const dl = T.diffLines('a\nb\nc\n', 'a\nx\nc\n');
assert.equal(j(dl), j([['=', 'a'], ['-', 'b'], ['+', 'x'], ['=', 'c'], ['=', '']]));
const dl2 = T.diffLines('1\n2\n3', '3\n2\n1');
assert.equal(dl2.filter(o => o[0] === '=').length, 1);   // LCS=1（2 或 3 之一）
assert.equal(dl2.filter(o => o[0] === '-').length, 2);
assert.equal(dl2.filter(o => o[0] === '+').length, 2);
const dl3 = T.diffLines('A\nb', 'a\nb', s => s.toLowerCase());
assert.equal(j(dl3), j([['=', 'A'], ['=', 'b']]));   // norm 只影响比较，保留原文
ok('diffLines LCS（含 norm 保原文）');
const dw = T.diffWords('the quick fox', 'the slow fox');
// 分词含独立空白 token：the | ' ' | quick→del | slow→add | ' ' | fox
assert.equal(j(dw), j([['=', 'the'], ['=', ' '], ['-', 'quick'], ['+', 'slow'], ['=', ' '], ['=', 'fox']]));
ok('diffWords LCS');

/* ---------- 时间戳 ---------- */
assert.equal(T.tsUnit('1700000000'), 's');
assert.equal(T.tsUnit('1700000000000'), 'ms');
assert.equal(T.tsToDate('1700000000').getTime(), 1700000000000);
assert.equal(T.tsToDate('1700000000000').getTime(), 1700000000000);
assert.equal(T.relTime(Date.now() - 30000), '30 秒前');
assert.equal(T.relTime(Date.now() - 3 * 3600 * 1000), '3 小时前');
assert.equal(T.relTime(Date.now() + 60000, Date.now()), '1 分钟后');
assert.match(T.fmtLocal(new Date(1700000000000)), /^2023-11-15 \d{2}:\d{2}:\d{2} GMT[+-]\d{2}:\d{2}$/);
ok('时间戳单位识别/转换/相对时间/本地格式');

/* ---------- 随机字符串 ---------- */
const seeded = bytes => { let s = 42; const b = new Uint8Array(bytes); for (let i = 0; i < bytes; i++) { s = (s * 1103515245 + 12345) & 0x7fffffff; b[i] = s & 0xff; } return b; };
const cs = T.buildCharset({ upper: true, lower: true, digit: true, symbol: true, noConfusable: true });
assert.ok(![...cs].some(c => T.CONFUSABLE.has(c)), '易混字符应被排除');
const r1 = T.randomString({ length: 20, upper: true, lower: true, digit: true, symbol: false, noConfusable: true, prefix: 'zt-' }, seeded);
assert.equal(r1.length, 23);          // 前缀 3 + 20
assert.ok(r1.startsWith('zt-'));
assert.ok([...r1.slice(3)].every(c => cs.includes(c)));
const r2 = T.randomString({ length: 32, upper: false, lower: true, digit: false, symbol: false, noConfusable: false });
assert.match(r2, /^[a-z]{32}$/);      // 真·crypto 路径
assert.equal(T.randomString({ length: 8, upper: false, lower: false, digit: false, symbol: false }), '');
ok('随机字符串：种子确定性 / 规则过滤 / crypto 路径 / 空字符集');

/* ---------- Unicode / URL ---------- */
assert.equal(T.unicodeEscape('A中😀'), 'A\\u4e2d\\ud83d\\ude00');
assert.equal(T.unicodeUnescape('A\\u4e2d\\ud83d\\ude00'), 'A中😀');
assert.equal(T.urlEncode('a 中/b'), encodeURIComponent('a 中/b'));
assert.equal(T.urlDecode('%E4%B8%AD%20123'), '中 123');
assert.equal(T.urlDecode('%E4%B8'), null);  // 非法序列返回 null
ok('Unicode \\uXXXX（含代理对）与 URL 百分号编解码');

/* ---------- base64 ---------- */
assert.equal(new TextDecoder().decode(T.b64decode(T.b64encode(new TextEncoder().encode('roundtrip ✓ 世界')))), 'roundtrip ✓ 世界');
ok('base64 字节回路');

/* ---------- AES-256-GCM（node webcrypto 同 API） ---------- */
const salt = new Uint8Array(16).fill(7), iv = new Uint8Array(12).fill(3);
const PASSWORD = '文本工具箱-P@ss 2026', PLAIN = 'hello 世界 🌍 AES-GCM roundtrip';
const enc = await T.aesEncrypt(PASSWORD, PLAIN, { salt, iv });
const dec = await T.aesDecrypt(PASSWORD, enc.b64);
assert.equal(dec, PLAIN);
try { await T.aesDecrypt('wrong-password', enc.b64); assert.fail('错口令应抛错'); }
catch (e) { assert.match(String(e), /OperationError|失败|invalid/i); }
ok('AES-256-GCM 加解密回路 + 错口令拒绝');

// 产出固定向量供 Python cryptography 对照（salt/iv 固定 → 密文确定）
const VECTOR_JS = '/tmp/text-toolbox-aes-js.json';
writeFileSync(VECTOR_JS, JSON.stringify({ password: PASSWORD, plaintext: PLAIN, b64: enc.b64, iter: T.AES_ITER }));
ok(`AES 向量已写出 ${VECTOR_JS}`);

/* ---------- SQL：扫描/去注释/粗检/降级格式化 ---------- */
assert.equal(T.sqlStrip("SELECT a -- 行注释\nFROM t /* 块\n注释 */ WHERE s = 'a  b--c'"),
  "SELECT a FROM t WHERE s = 'a  b--c'");
const issues = T.sqlCheck("SELEC a FROM t WHERE x IN ('1', '2'");
assert.ok(issues.some(s => s.includes('SELEC')), '应报 SELEC 拼写: ' + issues);
assert.ok(issues.some(s => s.includes('(') && s.includes('未闭合')), '应报括号未闭合: ' + issues);
const issues2 = T.sqlCheck("SELECT a FROM t WHERE s = 'it''s' AND b = (1+2)");
assert.equal(j(issues2), j([]), '合法 SQL 应无告警: ' + JSON.stringify(issues2));
const fmt = T.sqlNaiveFormat('select a,b from t where x=1 and y=2');
assert.ok(fmt.split('\n').length >= 3, '降级格式化应换行: ' + JSON.stringify(fmt));
assert.ok(/from/i.test(fmt) && /where/i.test(fmt));  // 保留原大小写
ok('SQL 去注释保字符串 / 粗检（拼写+配平）/ 降级格式化');

/* ---------- 对齐对照：hunk 分组 ---------- */
const dr = T.diffRows('a\nb\nc\nd', 'a\nx\nc');
assert.equal(dr.hunks.length, 2, '应有两个差异块');
assert.equal(j(dr.hunks[0]), j({ id: 0, dels: ['b'], adds: ['x'] }));
assert.equal(j(dr.hunks[1]), j({ id: 1, dels: ['d'], adds: [] }));
// 连续差异行归同一块、纯相同行间隔分开；rows 对齐：删除行右空、新增行左空
const dr2 = T.diffRows('1\n2\n3\n4\n5', '1\nX\nY\n4\n5');
assert.equal(dr2.hunks.length, 1);
assert.equal(j(dr2.hunks[0]), j({ id: 0, dels: ['2', '3'], adds: ['X', 'Y'] }));
assert.equal(j(dr2.rows), j([
  { l: '1', r: '1', h: null },
  { l: '2', r: 'X', h: 0 }, { l: '3', r: 'Y', h: 0 },
  { l: '4', r: '4', h: null }, { l: '5', r: '5', h: null }]));
const dr3 = T.diffRows('k\nA\nmid\nB', 'k\nX\nY\nmid\nZ');
assert.equal(dr3.hunks.length, 2, '相同行 mid 应分隔两个块: ' + j(dr3.hunks));
assert.ok(dr3.rows.some(r => r.l === null && r.r === 'Y'), '新增行左侧为 null 占位');
assert.ok(dr3.rows.some(r => r.l === 'A' && r.r === 'X'), '双侧同现行对齐');
ok('hunk 分组：连续差异归块 / 相同行分隔 / rows 对齐占位');

/* ---------- 接受替换（双向，含多行块） ---------- */
const AA = '1\n2\n3\n4', BB = '1\nX\nY\n4';
const m1 = T.applyAccepts(AA, BB, null, { 0: 'toA' });
assert.equal(m1.a, '1\nX\nY\n4', 'toA：A 吸收 B 块');
assert.equal(m1.b, BB, 'toA 不改 B');
const m2 = T.applyAccepts(AA, BB, null, { 0: 'toB' });
assert.equal(m2.b, AA, 'toB：B 吸收 A 块');
assert.equal(m2.a, AA, 'toB 不改 A');
// 纯删除/纯新增块的接受
const m3 = T.applyAccepts('a\nb', 'a', null, { 0: 'toB' });
assert.equal(m3.b, 'a\nb', 'toB 对纯删除块 = B 补回 A 行');
const m4 = T.applyAccepts('a', 'a\nc', null, { 0: 'toA' });
assert.equal(m4.a, 'a\nc', 'toA 对纯新增块 = A 补进 B 行');
ok('接受替换双向（含多行块与纯增/纯删块）');

/* ---------- 逐块独立应用、与顺序无关 ---------- */
const SA = 'h1\nA1\nA2\nmid\nB1\nh2', SB = 'h1\nX1\nmid\nY1\nY2\nh2';
const both1 = T.applyAccepts(SA, SB, null, { 0: 'toA', 1: 'toB' });
const both2 = T.applyAccepts(SA, SB, null, { 1: 'toB', 0: 'toA' });  // 插入序无关
assert.equal(both1.a, both2.a); assert.equal(both1.b, both2.b);
assert.equal(both1.a, 'h1\nX1\nmid\nB1\nh2');   // h0 吸收 B 的 X1，h1 保留 A 的 B1
assert.equal(both1.b, 'h1\nX1\nmid\nB1\nh2');   // 双向各接受一块后两侧收敛一致
ok('逐块独立应用顺序无关（混合方向）');

/* ---------- CJK 逐字 diff ---------- */
const cjkOps = T.inlineDiff('今天天气好', '今天天气差');
assert.equal(j(cjkOps), j([['=', '今'], ['=', '天'], ['=', '天'], ['=', '气'], ['-', '好'], ['+', '差']]));
const mix = T.tokenizeIntra('今天 weather 好!');
assert.equal(j(mix), j(['今', '天', ' ', 'weather', ' ', '好', '!']),
  '混合串：CJK 逐字 / 西文按词 / 空白独立: ' + j(mix));
ok('CJK 逐字 inlineDiff + 混合 tokenizer');

/* ---------- norm 开关：影响判定、保留原文 ---------- */
const dws = T.diffRows('ABC \nkeep', 'abc\nkeep', s => s.trim().toLowerCase());
assert.equal(dws.hunks.length, 0, '忽略空白+大小写后应无差异块');
assert.equal(dws.rows[0].l, 'ABC ', '判定用 norm，输出保留原文');
const dws2 = T.diffRows('ABC\nkeep', 'abc\nkeep');
assert.equal(dws2.hunks.length, 1, '不加 norm 时大小写视为差异');
ok('忽略空白/大小写开关（判定变化、原文保留）');

/* ---------- 相似度口径：字符级 LCS / max(字符数) ---------- */
assert.equal(T.similarity('abc', 'abc'), 1);
assert.equal(T.similarity('abc', 'xyz'), 0);
assert.equal(T.similarity('', ''), 1);
assert.equal(T.similarity('abcd', 'abef'), 0.5);   // LCS='ab'，max=4
assert.equal(T.similarity('aaaa', 'aa'), 0.5);     // LCS='aa'，max=4
ok('相似度口径断言（相同=1 / 全异=0 / 构造半同=精确值）');

/* ---------- 时间工具（自 time-toolbox 并入） ---------- */
const TZ_CN = Intl.DateTimeFormat().resolvedOptions().timeZone === 'Asia/Shanghai';
const D2 = (y, mo, d, h = 0, mi = 0, s = 0) => new Date(y, mo - 1, d, h, mi, s);

/* A. 农历（春节向量 ×27 是码表正确性主保障） */
const SPRINGS = [
  [2000,'2000-02-05'],[2001,'2001-01-24'],[2002,'2002-02-12'],[2003,'2003-02-01'],
  [2004,'2004-01-22'],[2005,'2005-02-09'],[2006,'2006-01-29'],[2007,'2007-02-18'],
  [2008,'2008-02-07'],[2009,'2009-01-26'],[2010,'2010-02-14'],[2011,'2011-02-03'],
  [2012,'2012-01-23'],[2013,'2013-02-10'],[2014,'2014-01-31'],[2015,'2015-02-19'],
  [2016,'2016-02-08'],[2017,'2017-01-28'],[2018,'2018-02-16'],[2019,'2019-02-05'],
  [2020,'2020-01-25'],[2021,'2021-02-12'],[2022,'2022-02-01'],[2023,'2023-01-22'],
  [2024,'2024-02-10'],[2025,'2025-01-29'],[2026,'2026-02-17'],
];
for (const [y, ds] of SPRINGS) {
  const [yy, mm, dd] = ds.split('-').map(Number);
  const l = T.solar2lunar(yy, mm, dd);
  assert.deepEqual(l && { y: l.year, m: l.month, d: l.day, leap: l.isLeap }, { y, m: 1, d: 1, leap: false }, ds);
}
assert.equal((() => { const l = T.solar2lunar(1900, 1, 31); return l && `${l.year}-${l.month}-${l.day}`; })(), '1900-1-1');
assert.equal(T.solar2lunar(1899, 6, 1), null);
assert.equal((() => { const l = T.solar2lunar(2025, 7, 25); return l && `${l.isLeap ? '闰' : ''}${l.month}-${l.day}`; })(), '闰6-1');
assert.equal((() => { const l = T.solar2lunar(2023, 3, 22); return l && `${l.isLeap ? '闰' : ''}${l.month}-${l.day}`; })(), '闰2-1');
assert.equal((() => { const l = T.solar2lunar(2020, 5, 23); return l && `${l.isLeap ? '闰' : ''}${l.month}-${l.day}`; })(), '闰4-1');
assert.equal(T.yearGZ(2025), '乙巳');
assert.equal(T.yearGZ(1984), '甲子');
assert.equal(T.yearSX(2025), '蛇');
assert.equal(T.lunarFull(T.solar2lunar(2025, 1, 29)), '乙巳年正月初一');
assert.ok(T.lLeapMonth(2025) === 6 && T.lLeapMonth(2023) === 2 && T.lLeapMonth(2020) === 4);
assert.ok([2020, 2023, 2025].every(y => T.lYearDays(y) >= 383 && T.lYearDays(y) <= 385));
ok('农历：春节向量 ×27 + 基准/越界/闰月 + 干支生肖 + 年天数自洽');

/* B. 节气 */
assert.equal(T.sTermDay(2025, 6), 4);
assert.equal(T.sTermDay(2025, 23), 21);
assert.equal(T.sTermDay(2024, 23), 21);
assert.equal(T.sTermDay(2025, 2), 3);
assert.equal(T.sTermDay(2024, 6), 4);
assert.equal(T.sTermDay(2025, 8), 5);
assert.equal(T.termOfDate(2025, 4, 4), '清明');
assert.equal(T.termOfDate(2025, 4, 9), null);
ok('节气分钟偏移表向量');

/* C. 节假日 */
assert.deepEqual(T.holidayOf(2025, 10, 1), { tag: 'rest', name: '国庆中秋' });
assert.equal(T.holidayOf(2025, 10, 11).tag, 'work');
assert.equal(T.holidayOf(2024, 4, 7).tag, 'work');
assert.equal(T.holidayOf(2023, 5, 3).tag, 'rest');
assert.equal(T.holidayOf(2022, 10, 7).tag, 'rest');
assert.deepEqual(T.holidayOf(2024, 10, 1), { tag: 'rest', name: '国庆节' });
assert.equal(T.holidayOf(2020, 10, 8).tag, 'rest');
assert.deepEqual(T.holidayOf(2025, 10, 18), { tag: 'rest', name: '周末' });
assert.equal(T.holidayOf(2025, 10, 9), null);
assert.ok(T.holidayOf(2019, 10, 5)?.tag === 'rest' && T.holidayOf(2019, 10, 8) === null);
ok('国务院休班数据 2020–2026 + 周末回落 + 范围外');

/* D. 节日 */
assert.equal(T.festFull(2025, 1, 1), '元旦');
assert.equal(T.festFull(2025, 10, 1), '国庆节');
assert.equal(T.festFull(2025, 5, 31), '端午节');
assert.equal(T.festFull(2025, 10, 6), '中秋节');
assert.equal(T.festFull(2025, 1, 28), '除夕');
assert.equal(T.festFull(2024, 2, 9), '除夕');
assert.equal(T.festFull(2025, 5, 11), '母亲节');
assert.equal(T.festFull(2025, 6, 15), '父亲节');
assert.equal(T.dayInfo(2025, 10, 1).label, '国庆节');
assert.equal(T.dayInfo(2025, 4, 4).label, '清明');
assert.ok(T.dayInfo(2025, 7, 25).label.includes('六月'));
ok('公历/农历/除夕/母亲父亲节 + dayInfo label 优先级');

/* E. parseDateTimeInput */
assert.equal(+T.parseDateTimeInput('2025-01-31 08:30:05'), +D2(2025, 1, 31, 8, 30, 5));
assert.equal(+T.parseDateTimeInput('2025-01-31 08:30'), +D2(2025, 1, 31, 8, 30, 0));
assert.equal(T.parseDateTimeInput('2025-13-99 88:00'), null);
assert.equal(new Date(1735660800000).toISOString(), '2024-12-31T16:00:00.000Z');
ok('parseDateTimeInput 回路/缺秒默认/非法拒绝');

/* F. dateAdd */
assert.equal(T.ymdhms(T.dateAdd(D2(2025, 1, 31), { mo: 1 })), '2025-02-28 00:00:00');
assert.equal(T.ymdhms(T.dateAdd(D2(2024, 2, 29), { y: 1 })), '2025-02-28 00:00:00');
assert.equal(T.ymdhms(T.dateAdd(D2(2025, 10, 1), { w: 2 })), '2025-10-15 00:00:00');
assert.equal(T.ymdhms(T.dateAdd(D2(2025, 10, 1, 23, 0), { mi: 90 })), '2025-10-02 00:30:00');
assert.equal(T.ymdhms(T.dateAdd(D2(2025, 1, 1), { d: -1 })), '2024-12-31 00:00:00');
assert.equal(T.ymdhms(T.dateAdd(D2(2024, 3, 10), { y: 1, mo: 2, d: 3 })), '2025-05-13 00:00:00');
assert.equal(T.ymdhms(T.dateAdd(D2(2025, 6, 15, 12, 30), {})), '2025-06-15 12:30:00');
ok('dateAdd 月末 clamp/跨日跨月/混合量');

/* G. dateDiff / workdays */
assert.deepEqual((() => { const r = T.dateDiff(D2(2024, 3, 10), D2(2025, 5, 20)); return { y: r.Y, mo: r.Mo, d: r.D }; })(), { y: 1, mo: 2, d: 10 });
assert.equal(T.dateDiff(D2(2025, 1, 1), D2(2025, 12, 31)).totalDays, 364);
assert.equal(T.dateDiff(D2(2024, 1, 1), D2(2024, 12, 31)).totalDays, 365);
assert.deepEqual((() => { const r = T.dateDiff(D2(2025, 1, 1), D2(2025, 1, 2, 3, 4, 5)); return { d: r.D, h: r.H, mi: r.Mi, s: r.S }; })(), { d: 1, h: 3, mi: 4, s: 5 });
assert.equal(T.dateDiff(D2(2025, 5, 20), D2(2024, 3, 10)).totalDays, T.dateDiff(D2(2024, 3, 10), D2(2025, 5, 20)).totalDays);
assert.equal(T.workdaysBetween(D2(2025, 10, 1), D2(2025, 10, 8)), 0);
assert.equal(T.workdaysBetween(D2(2025, 10, 9), D2(2025, 10, 17)), 8);
assert.equal(T.workdaysBetween(D2(2025, 4, 4), D2(2025, 4, 6)), 0);
assert.equal(T.workdaysBetween(D2(2025, 10, 20), D2(2025, 10, 24)), 5);
assert.equal(T.workdaysBetween(D2(2024, 2, 10), D2(2024, 2, 17)), 0);
assert.equal(T.workdaysBetween(D2(2024, 2, 18), D2(2024, 2, 18)), 1);
ok('dateDiff 自然差/总量/顺序无关 + workdays 6 边界');

/* H. 格式化 */
{
  const d = new Date(Date.UTC(2024, 11, 31, 16, 0, 0)); // = 北京 2025-01-01 00:00
  const f = Object.fromEntries(T.FORMATS.map(([nm, fn]) => [nm, fn(d)]));
  assert.equal(f['ISO 8601（UTC）'], '2024-12-31T16:00:00.000Z');
  assert.equal(f['ISO 8601 基本格式（UTC，无分隔）'], '20241231T160000Z');
  assert.equal(f['Unix 时间戳（秒）'], '1735660800');
  assert.equal(f['Unix 时间戳（毫秒）'], '1735660800000');
  assert.ok(Math.abs(Number(f['儒略日 JD（UT）']) - (2440587.5 + 1735660800000 / 86400000)) < 1e-6);
  if (TZ_CN) {
    assert.equal(f['一年中第几天（DDD）'], '001');
    assert.equal(f['ISO 8601（本地，含时区）'], '2025-01-01T00:00:00+08:00');
    assert.equal(f['RFC 2822'], 'Wed, 01 Jan 2025 00:00:00 +0800');
    assert.equal(f['yyyy年M月d日'], '2025年1月1日');
    assert.equal(f['星期X（中文全称）'], '星期三');
    assert.equal(f['当月第几个星期X'], '第1个星期三');
    assert.equal(f['yyyy年M月d日 星期X 上/下午h:mm'], '2025年1月1日 星期三 凌晨0:00');
  }
}
assert.equal((() => { const w = T.isoWeek(D2(2025, 1, 1)); return `${w.y}-W${String(w.w).padStart(2, '0')}`; })(), '2025-W01');
assert.equal((() => { const w = T.isoWeek(D2(2026, 1, 1)); return `${w.y}-W${String(w.w).padStart(2, '0')}`; })(), '2026-W01');
assert.equal((() => { const w = T.isoWeek(D2(2027, 1, 1)); return `${w.y}-W${String(w.w).padStart(2, '0')}`; })(), '2026-W53');
assert.equal(T.dayOfYear(D2(2024, 12, 31)), 366);
assert.equal(T.relativeNow(D2(2025, 1, 2), D2(2025, 1, 1)), '1 天后');
assert.ok(T.relativeNow(D2(2020, 1, 1), D2(2025, 1, 1)).includes('2020-01-01'));
ok('25 格式向量（UTC + 本地）+ ISO 周边界 + relativeNow 注入');

console.log(`\nfrontend core selftest: ${n} 组断言全部通过`);

/* ---------- 阶段 2：解 python cryptography 产出的向量 ---------- */
if (process.argv.includes('--verify-py')) {
  const v = JSON.parse(readFileSync('/tmp/text-toolbox-aes-py.json', 'utf8'));
  assert.equal(await T.aesDecrypt(v.password, v.b64), v.plaintext);
  console.log('[PASS] node/webcrypto 解密 python cryptography AES-GCM 向量');
}
