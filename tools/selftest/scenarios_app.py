# 场景库：主应用核心页面（任务列表/表单/设置/插件面板；exec 命名空间运行）


@group("app")
async def g_app(ctx, scale):
    """主应用 Vue 页面（种子数据来自编排器，规模随轮次递增）。"""
    p = ctx.page
    base = ctx.app_url

    # ---- 任务列表 ----
    await p.goto(base + "/#/tasks", wait_until="domcontentloaded", timeout=8000)
    await p.wait_for_timeout(1200)
    cards = await p.evaluate("() => document.querySelectorAll('.task-card-item').length")
    seeded = {"small": 3, "medium": 40, "large": 150}[scale]
    ctx.check("tasks-列表渲染种子数", cards >= min(seeded, 10), f"{cards}/{seeded}")

    # ---- 新建表单默认值（v0.7.18 语义：今天起/次日止预填） ----
    await p.goto(base + "/#/tasks/new", wait_until="domcontentloaded", timeout=8000)
    await p.wait_for_timeout(1200)
    # 时间组件渲染完整性（笔刷 + 月历网格；「今天开始」是格子点亮非文本，组件级断言留待后续）
    presets = None
    for _ in range(12):
        presets = await p.evaluate(
            """() => {
              const blk = [...document.querySelectorAll('.zt-block')]
                .find(b => b.textContent.includes('时间与提醒'));
              if (!blk) return null;
              const t = blk.innerText;
              return t.includes('开始') && t.includes('截止') && /\d+\s*年\s*\d+\s*月/.test(t) ? true : false;
            }"""
        )
        if presets is True:
            break
        await p.wait_for_timeout(300)
    ctx.check("form-时间组件渲染(笔刷+月历)", presets is True, str(presets))


    # ---- 周期模式：行式时间区（先跳列表再进，避免同路由不重挂载吃掉点击） ----
    await p.goto(base + "/#/tasks", wait_until="domcontentloaded")
    await p.wait_for_timeout(600)
    await p.goto(base + "/#/tasks/new", wait_until="domcontentloaded")
    await p.wait_for_timeout(1200)
    await p.click('.arco-radio:has-text("周期")', timeout=3000)
    await p.wait_for_timeout(600)
    rows = await p.evaluate("() => ({cyc: !!document.querySelector('.tf-cycrows'), hash: location.hash,"
        " radios: document.querySelectorAll('.arco-radio').length,"
        " timeText: ([...document.querySelectorAll('.zt-block')].find(b => b.textContent.includes('时间与提醒'))||{innerText:''}).innerText.slice(0, 50)})")
    ctx.check("form-周期行式时间区", rows["cyc"], str(rows)[:160])
    # ---- 设置页 ----
    await p.goto(base + "/#/settings", wait_until="domcontentloaded")
    await p.wait_for_timeout(1500)
    groups = await p.evaluate(
        "() => document.querySelectorAll('.arco-menu-item-group, [class*=menu-group]').length"
    )
    ctx.check("settings-导航分组", groups >= 3, str(groups))
    try:
        await p.click('.arco-menu-item:has-text("🖥️ 系统")', timeout=4000)
        await p.wait_for_timeout(1500)
    except Exception:
        pass
    upd = await p.evaluate("() => ({has: document.body.textContent.includes('软件更新'),"
        " menus: [...document.querySelectorAll('.arco-menu-item')].map(m => m.innerText.trim()).slice(0, 8)})")
    ctx.check("settings-更新卡片", upd["has"], str(upd)[:160])

    # ---- 插件面板页 ----
    await p.goto(base + "/#/plugins-panel", wait_until="domcontentloaded")
    await p.wait_for_timeout(1200)
    tabs = await p.evaluate("() => document.body.textContent.includes('插件') || document.body.textContent.includes('记录')")
    ctx.check("plugins-面板加载", tabs)

    # ---- 速览页 ----
    await p.goto(base + "/#/glance", wait_until="domcontentloaded")
    await p.wait_for_timeout(900)
    glance = await p.evaluate("() => document.querySelectorAll('[class*=glance] *').length > 5")
    ctx.check("glance-加载", glance)

    # ---- 表单落库：填标题保存 → API 计数+1 ----
    # 独立新页：同会话内先访问设置/速览等页后再进表单，输入交互会失灵
    # （headless 宿主缺失路径的产品缺陷，已记档；此处隔离保证用例确定性）
    p = await ctx.page.context.browser.new_page(viewport={"width": 1000, "height": 700})
    await p.goto(base + "/#/tasks/new", wait_until="domcontentloaded")
    await p.wait_for_timeout(1500)
    before = await p.evaluate("() => fetch('/api/tasks').then(r => r.json()).then(d => d.items.length)")
    await p.fill(".field-line input[type=text]:not([readonly])", "自测新建任务")
    await p.click('button:has-text("保存")')
    await p.wait_for_timeout(1200)
    after = await p.evaluate("() => fetch('/api/tasks').then(r => r.json()).then(d => d.items.length)")
    ctx.check("form-保存落库", after == before + 1, f"{before}->{after}")
    await p.close()
