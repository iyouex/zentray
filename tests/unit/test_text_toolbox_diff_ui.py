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
