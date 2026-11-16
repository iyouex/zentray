# 场景库：文本工具箱（六工具全覆盖；在 run.py 的 exec 命名空间内运行，
# 可直接用 group/Ctx/apply_cdn；勿 import run）
import json as _json
import time as _time

SET_VAL = "(el, v) => el.CodeMirror.setValue(v)"
GET_VAL = "el => el.CodeMirror.getValue()"


def cm_active(page):
    return page.evaluate("() => !!document.querySelector('#json-cm .CodeMirror')")


async def open_tb(ctx):
    await ctx.page.goto(ctx.tb_url + "/", wait_until="domcontentloaded", timeout=8000)
    dcl = await ctx.page.evaluate(
        "() => performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart"
    )
    ctx.check("DCL<800ms", dcl < 800, f"{dcl}ms")


async def set_json(page, text):
    if await cm_active(page):
        await page.eval_on_selector("#json-cm .CodeMirror", SET_VAL, text)
    else:
        await page.fill("#json-in", text)


async def get_json_value(page):
    if await cm_active(page):
        return await page.eval_on_selector("#json-cm .CodeMirror", GET_VAL)
    return await page.evaluate("() => document.querySelector('#json-in').value")


async def json_status(page):
    return await page.evaluate("() => document.querySelector('#json-status').textContent")


async def set_sql(page, text):
    if await page.evaluate("() => !!document.querySelector('#sql-cm-in .CodeMirror')"):
        await page.eval_on_selector("#sql-cm-in .CodeMirror", SET_VAL, text)
    else:
        await page.fill("#sql-in", text)


async def get_sql_out(page):
    if await page.evaluate("() => !!document.querySelector('#sql-cm-out .CodeMirror')"):
        return await page.eval_on_selector("#sql-cm-out .CodeMirror", GET_VAL)
    return await page.evaluate("() => document.querySelector('#sql-out').value")


@group("toolbox")
async def g_toolbox(ctx, scale):
    """六工具核心功能（normal=CM 全量 / blocked=textarea 降级全量）。"""
    p = ctx.page
    await open_tb(ctx)
    await p.wait_for_timeout(2000)  # CDN 注入窗口（blocked 下自然跳过）
    cm = await cm_active(p)
    ctx.check("CM按CDN态启用", cm if ctx.group_name.endswith("[normal]") else not cm)

    # ---- JSON ----
    await set_json(p, '{"a":1,"b":[1,2]}')
    await p.wait_for_timeout(400)
    ctx.check("json-校验合法", "Valid" in await json_status(p))
    await set_json(p, '{"a":}')
    await p.wait_for_timeout(400)
    ctx.check("json-校验非法", "Invalid" in await json_status(p))
    await set_json(p, '{"a":1,"b":{"c":2}}')
    await p.wait_for_timeout(300)
    await p.click("#json-prettify"); await p.wait_for_timeout(300)
    v = await get_json_value(p)
    ok_pretty = "\n" in v and "  " in v
    await p.click("#json-prettify"); await p.wait_for_timeout(300)
    v2 = await get_json_value(p)
    ctx.check("json-prettify/compress往返", ok_pretty and "\n" not in v2, v[:40])

    if ctx.group_name.endswith("[normal]"):
        await set_json(p, '{"a": 1,}')
        await p.wait_for_timeout(300)
        try:
            await p.click("#json-tryfix", timeout=2000); await p.wait_for_timeout(500)
            ctx.check("json-tryfix尾逗号", "Valid" in await json_status(p))
        except Exception as e:
            ctx.check("json-tryfix尾逗号", False, str(e)[:60])
    else:
        # 降级提示有 6s 兜底（onerror 可能迟到），轮询至最终态
        warn = False
        for _ in range(14):
            warn = await p.evaluate(
                "() => document.querySelector('#json-cdn-warn').classList.contains('show')"
            )
            if warn:
                break
            await p.wait_for_timeout(500)
        jr = await p.evaluate("() => typeof JSONRepair")
        ctx.check("json-CDN断降级提示", warn and jr == "undefined", f"warn={warn} jr={jr}")

    await p.click("#json-clear"); await p.wait_for_timeout(200)
    await p.click("#json-sample"); await p.wait_for_timeout(300)
    n1 = await p.evaluate("() => document.querySelector('#json-in').value.length")
    await p.click("#json-clear"); await p.wait_for_timeout(300)
    n2 = await p.evaluate("() => document.querySelector('#json-in').value.length")
    ctx.check("json-sample/clear", n1 > 10 and n2 == 0, f"{n1}->{n2}")

    # ---- SQL ----
    await p.click('button[data-tool="sql"]'); await p.wait_for_timeout(400)
    await set_sql(p, "SELECT a,b FROM t WHERE x=1")
    await p.click("#sql-format"); await p.wait_for_timeout(500)
    out = await get_sql_out(p)
    ctx.check("sql-格式化", "\n" in out, out[:50])
    await p.click("#sql-minify"); await p.wait_for_timeout(400)
    out2 = await get_sql_out(p)
    ctx.check("sql-压缩单行", "\n" not in out2, out2[:40])
    await set_sql(p, "SELEC 1 FROM t (")
    await p.click("#sql-check"); await p.wait_for_timeout(300)
    s = await p.evaluate("() => document.querySelector('#sql-msg').textContent")
    ctx.check("sql-语法粗检报错", "问题" in s, s[:50])

    # ---- diff（融合框 + canvas 连线/合并） ----
    await p.click('button[data-tool="diff"]'); await p.wait_for_timeout(300)
    await p.fill("#diff-l", "a\nb\nc")
    await p.fill("#diff-r", "a\nx\nc")
    await p.wait_for_timeout(700)
    st = await p.evaluate("() => document.querySelector('#diff-stats').textContent")
    ctx.check("diff-差异统计", "差异块" in st, st[:40])
    painted = await p.evaluate(
        "() => { const c = document.querySelector('#mg-canvas'); if (!c) return false;"
        " const ctx = c.getContext('2d'); const d = ctx.getImageData(0,0,c.width,Math.min(c.height,200)).data;"
        " return d.some((v, i) => i % 4 !== 3 && v > 0); }"
    )
    ctx.check("diff-连线画布绘制", painted)
    # 合并箭头（canvas 命中）：取首个差异行 y → canvas 中线点击
    try:
        y = await p.evaluate(
            "() => { const r = document.querySelector('#mg-view-l .mg-row');"
            " return r ? r.getBoundingClientRect().top : -1; }"
        )
        if y >= 0:
            await p.click("#mg-canvas", position={"x": 8, "y": 30}, timeout=1500)
            await p.wait_for_timeout(500)
        ctx.check("diff-合并箭头点击不崩", True)
    except Exception as e:
        ctx.check("diff-合并箭头点击不崩", False, str(e)[:60])
    # 大小写忽略开关
    await p.fill("#diff-l", "A"); await p.fill("#diff-r", "a")
    await p.wait_for_timeout(600)
    await p.check("#diff-ignorecase"); await p.wait_for_timeout(600)
    st2 = await p.evaluate("() => document.querySelector('#diff-stats').textContent")
    ctx.check("diff-忽略大小写", "一致" in st2 or "差异块" not in st2, st2[:30])

    # ---- time（万年历 + 当日任务联动） ----
    await p.click('button[data-tool="time"]'); await p.wait_for_timeout(600)
    cells = await p.evaluate("() => document.querySelectorAll('#cal-grid > div').length")
    ctx.check("time-万年历渲染", cells >= 28, str(cells))
    await p.click("#cal-today"); await p.wait_for_timeout(400)
    detail = await p.evaluate("() => document.querySelector('#cal-detail').textContent.length")
    ctx.check("time-今日详情", detail > 3, str(detail))
    cal_tasks = await p.evaluate(
        "() => { const el = document.querySelector('#cal-tasks'); return el ? el.textContent.length : -1; }"
    )
    ctx.check("time-当日任务区", cal_tasks >= 0, str(cal_tasks))

    # ---- random ----
    await p.click('button[data-tool="random"]'); await p.wait_for_timeout(300)
    await p.fill("#rnd-len", "64")
    await p.click("#rnd-gen"); await p.wait_for_timeout(300)
    rnd = await p.evaluate(
        "() => ({out: document.querySelector('#rnd-out').textContent,"
        " msg: document.querySelector('#rnd-msg').textContent,"
        " len: document.querySelector('#rnd-len').value})"
    )
    ctx.check(
        "random-生成64位",
        len(rnd["out"].strip()) >= 64,
        f"len={len(rnd['out'].strip())} msg={rnd['msg'][:40]} len字段={rnd['len']}",
    )

    # ---- crypto ----
    await p.click('button[data-tool="crypto"]'); await p.wait_for_timeout(300)
    await p.fill("#md5-in", "abc")
    await p.click("#md5-run"); await p.wait_for_timeout(400)
    md5 = await p.evaluate("() => document.querySelector('#md5-out').textContent")
    ctx.check("crypto-md5向量", "900150983cd24fb0d6963f7d28e17f72" in md5, md5[:40])
    await p.fill("#aes-plain", "自测明文")
    await p.fill("#aes-pass", "pw123")
    await p.click("#aes-enc"); await p.wait_for_timeout(900)
    blob = await p.evaluate("() => document.querySelector('#aes-blob').textContent")
    await p.fill("#aes-in", blob.strip())
    await p.fill("#aes-pass2", "pw123")
    await p.click("#aes-dec"); await p.wait_for_timeout(900)
    dec = await p.evaluate("() => document.querySelector('#aes-out').textContent")
    ctx.check("crypto-AES往返", dec.strip() == "自测明文", dec[:30])

    # ---- 真实粘贴路径（焦点+insert_text 模拟 Ctrl+V） ----
    await p.click('button[data-tool="json"]'); await p.wait_for_timeout(300)
    if await cm_active(p):
        await p.focus("#json-cm .CodeMirror textarea")
    else:
        await p.focus("#json-in")
    await p.keyboard.insert_text('{"k":"' + "x" * 200000 + '"}')
    await p.wait_for_timeout(900)
    ctx.check("真粘贴200KB", "Valid" in await json_status(p))


@group("toolbox_bigtext")
async def g_bigtext(ctx, scale):
    """大文本专项（normal CDN）。"""
    p = ctx.page
    await open_tb(ctx)
    await p.wait_for_timeout(2000)

    await p.click('button[data-tool="diff"]'); await p.wait_for_timeout(300)
    base = "比对样例行，内容足够长以模拟真实粘贴场景。\n" * 12000
    t0 = _time.monotonic()
    await p.evaluate(
        """([l, r]) => {
          for (const [sel, v] of [['#diff-l', l], ['#diff-r', r]]) {
            const el = document.querySelector(sel);
            el.value = v; el.dispatchEvent(new Event('input', {bubbles: true}));
          }
        }""",
        [base, base[:-15] + "差异行\n"],
    )
    await p.wait_for_timeout(1500)
    dt = _time.monotonic() - t0
    st = await p.evaluate("() => document.querySelector('#diff-stats').textContent")
    rows = await p.evaluate("() => document.querySelectorAll('#mg-view-l .mg-row').length")
    ctx.check("diff-12k行<3.5s", dt < 3.5, f"{dt:.1f}s")
    ctx.check("diff-12k统计", "差异块 1" in st, st[:40])
    ctx.check("diff-12k行渲染", rows >= 12000, str(rows))

    await p.click('button[data-tool="json"]'); await p.wait_for_timeout(300)
    big = _json.dumps({f"k{i}": {"n": i, "t": ["a", "b"]} for i in range(6000)})
    await set_json(p, big)
    await p.wait_for_timeout(900)
    ctx.check("json-6000键校验", "Valid" in await json_status(p))
    okw = await p.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1")
    ctx.check("json-大文本零横向溢出", okw)

    await p.click('button[data-tool="sql"]'); await p.wait_for_timeout(300)
    await set_sql(p, ";\n".join(f"SELECT a{i},b{i} FROM t{i} WHERE x={i}" for i in range(3000)))
    await p.click("#sql-format"); await p.wait_for_timeout(900)
    bounded = await p.evaluate(
        "() => document.documentElement.scrollWidth <= innerWidth + 1 && document.documentElement.scrollHeight < innerHeight * 4"
    )
    ctx.check("sql-3000语句页面有界", bounded)
    # CM 钳制回归线（2026-11-15：CSP 头拦截基础 css → 滚动容器 93 万 px 撑爆页面）
    cm_scroll = await p.evaluate(
        "() => { const el = document.querySelector('#sql-cm-out .CodeMirror-scroll');"
        " return el ? el.getBoundingClientRect().height : -1; }"
    )
    ctx.check("sql-CM钳制在pane内(<1000px)", 0 <= cm_scroll < 1000, f"{cm_scroll:.0f}px")


@group("cdn")
async def g_cdn(ctx, scale):
    """CDN hang（挂起 20s）态：页面必须即时可用并降级。"""
    p = ctx.page
    await open_tb(ctx)
    await p.wait_for_timeout(8000)  # 越过注入超时窗
    tools = await p.evaluate("() => document.querySelectorAll('button[data-tool]').length")
    ctx.check("hang-六工具齐", tools == 6, str(tools))
    await set_json(p, '{"ok":1}')
    await p.wait_for_timeout(400)
    ctx.check("hang-json可用", "Valid" in await json_status(p))
    warns = await p.evaluate(
        "() => document.querySelector('#json-cdn-warn').classList.contains('show') || document.querySelector('#sql-cdn-warn').classList.contains('show')"
    )
    ctx.check("hang-降级提示", warns)
    ctx.check("hang-CM未启用", not await cm_active(p))


# CDN 态矩阵接线（run.py 读 fn.cdn_modes，缺省 ["normal"]）
g_toolbox.cdn_modes = ["normal", "blocked"]
g_cdn.cdn_modes = ["hang"]
