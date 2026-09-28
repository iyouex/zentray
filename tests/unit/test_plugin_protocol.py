from zentray.plugins.protocol import format_tray_text, parse_stdout_line


def test_parse_progress():
    p = parse_stdout_line("PROGRESS 2/4 刷新DNS")
    assert p.kind == "progress"
    assert p.progress is not None
    assert p.progress.current == 2
    assert p.progress.total == 4
    assert p.progress.message == "刷新DNS"


def test_parse_log_and_result():
    assert parse_stdout_line("LOG hello").kind == "log"
    r = parse_stdout_line("RESULT ok")
    assert r.kind == "result" and r.result_ok is True
    r2 = parse_stdout_line("RESULT fail boom")
    assert r2.result_ok is False


def test_format_tray_truncates():
    p = parse_stdout_line("PROGRESS 1/1 " + ("x" * 80))
    text = format_tray_text("name", p, max_len=50)
    assert len(text) <= 50
