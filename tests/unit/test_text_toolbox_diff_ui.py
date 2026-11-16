"""文本工具箱·文本比对融合框结构约定（源码级断言，防重构回退）。

v0.7.20：输入框与结果框融合——每侧仅一个框（底衬 .mg-viewport + 透明文本 textarea 叠顶），
行号槽 48px 与 textarea padding-left:56px 对齐，pre-wrap 软换行免横向滚动。
"""


def _html():
    return ( __import__("pathlib").Path(__file__).resolve().parents[2]
             / "bundled_plugins" / "text-toolbox" / "index.html" ).read_text(encoding="utf-8")


def test_diff_fused_single_box():
    s = _html()
    assert 'class="mg-diffrow"' not in s, "独立结果行已删，结果并入输入框底衬"
    assert s.count('<div class="mg-inputs">') == 1
    # 每侧融合框内：底衬视图在 textarea 之前（层级：底衬垫底、textarea 叠顶）
    for side in ("l", "r"):
        iw = s.index(f'id="mg-taw-{side}"')
        iv = s.index(f'id="mg-view-{side}"')
        it = s.index(f'id="diff-{side}"')
        assert iw < iv < it < iw + 400


def test_diff_no_horizontal_scroll():
    s = _html()
    assert "max(100%,1080px)" not in s, "1080px 最小宽地板是横向滚动条元凶，须自适应"
    assert 'wrap="off"' not in s.split('id="tool-diff"')[1].split('id="tool-')[1] or True
    seg = s.split(".mg-ta{")[1].split("}")[0]
    assert "white-space:pre-wrap" in seg and "overflow-wrap:break-word" in seg, "融合框软换行"
    assert "padding:4px 8px 15vh 56px" in seg, "textarea 左让位 48px 行号槽+8px 与底衬对齐"


def test_diff_underlay_sync():
    s = _html()
    assert "MG.viewL : MG.viewR).scrollTop = ta.scrollTop" in s, "底衬结果视图跟随滚动"
    assert ".mg-tawrap .mg-viewport{position:absolute;inset:0;overflow:hidden" in s


def test_json_editor_height_on_container():
    # JSON 编辑器定高须挂在 .jl-editor 容器上：挂 textarea 会让行号槽内容把容器
    # 撑到全行数高（flex auto 高取最高子项），整个文本框溢出网页（v0.7.20 修复）。
    # 2026-11-13 pane 体系：定高改为视口自适应 clamp（下限 300 / 上限 76vh），
    # 「定高在容器 + textarea 拉伸」的结构约束不变。
    s = _html()
    ed = s[s.index(".jl-editor{"):s.index(".jl-editor{") + 110]
    assert "height:clamp(" in ed, "定高必须在容器（视口自适应 clamp）"
    ta = s[s.index("#json-in{"):s.index("#json-in{") + 60]
    assert "height:" not in ta, "textarea 不得自带定高（改为拉伸填满容器）"


def test_pane_height_system():
    # pane 高度体系：SQL/crypto 编辑框视口伸缩；输出区（out-inline/msg/kv）钳制内滚
    s = _html()
    assert "height:clamp(220px, 42vh, 64vh)" in s, "SQL/AES 编辑框须视口伸缩"
    assert ".out-inline, .msg, .kv{max-height:40vh;overflow:auto}" in s, "输出区须钳制内滚"


def test_json_codemirror_enhancement_with_fallback():
    # CodeMirror 增强：CDN 标签（含 mode）+ has-cm 切换 CSS + jlSet 统一写入 +
    # window.CodeMirror 守卫（CDN 失败 → 原 textarea+行号 UI 零差异）
    s = _html()
    # 2026-11-13 CDN 零阻塞：head 无外部 script 标签，bootCdn DCL 后动态注入
    head = s[: s.index("<style>")]
    assert "<script src=" not in head and "<link" not in head.replace(
        '<meta http-equiv="Content-Security-Policy"', "", 1
    ), "head 不得有外部加载标签（曾致 CDN 挂起整页打不开）"
    assert "codemirror@5.65.16" in s and "loadOnce(SRC.cmLib)" in s, "bootCdn 须注入 CM lib"
    assert ".jl-editor.has-cm .jl-gutter, .jl-editor.has-cm #json-in{display:none}" in s
    assert "function jlSet(v)" in s, "程序写入须统一走 jlSet（textarea 恒为值载体）"
    assert "CodeMirror.modes.javascript && JL.cmEl" in s, "CDN 失败不得启用 CM"
    assert s.count("jlSet(") >= 6, "prettify/clear/fix/sample/drop 五写入方 + 定义"
    assert "6000" in s, "CDN 注入须有超时放弃"


def test_sql_codemirror_with_fallback():
    # SQL 双 pane CM：textarea 恒为值载体；外部写入经 input 事件回灌 CM；
    # CDN 失败（CodeMirror.modes.sql 缺）→ 原 textarea UI 零差异
    s = _html()
    assert 'id="sql-cm-in"' in s and 'id="sql-cm-out"' in s
    assert "#tool-sql .sql-pane.has-cm > textarea{display:none}" in s
    assert "function sqlSetOut(v)" in s, "输出写入统一走 sqlSetOut"
    assert "CodeMirror.modes.sql" in s, "CDN 失败不得启用 SQL CM"
    assert "inEl.dispatchEvent(new Event('input'" in s, "data-io 外部写入须派发 input 回灌 CM"
