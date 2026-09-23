# Zentray 插件系统代码实现顺序规划
**文件**: code_planning.md  
**版本**: 1.0 (2026-08-06)  
**目标**: 完成完整插件系统（API + Runtime + UI + 持久化 + 打包）  
**状态**: Phase 0 已完成（handlers.py API 端点）

## 执行计划（粒度拆细 + 测试环节）

### Phase 0: 当前状态确认（已完成）
- 文件: `zentray/api/handlers.py`
- 测试: `pytest tests/unit/test_plugin_install_api.py -q`
- 验证: 手动 curl `/api/plugins` 正常

### Phase 1: SettingsManager 全 ops 配置持久化（立即执行）
1. 编辑 `zentray/services/settings_manager.py`：
   - 确保 `get_ops_user_plugins_dir()` 健壮（空字符串时用默认路径 `DATA_DIR/plugins`）
   - 增强 `_apply_dict` 和 `save()` 对 `ops` 字段的完整处理（添加默认值、路径标准化、兼容旧版）
   - 确保 `user_plugins_dir` 总是以绝对路径存储
2. 测试环节：
   - `pytest tests/unit/test_ops_settings.py -q`
   - 手动：修改 settings.json 的 ops.user_plugins_dir → 运行程序 → 检查目录路径正确持久保存

### Phase 2: PluginLoader / Manifest 测试
1. 文件: `zentray/plugins/loader.py` + `manifest.py`（已完成）
2. 测试: `pytest tests/unit/test_plugin_manifest.py tests/unit/test_plugin_loader.py -q`（已通过）
3. 手动: `python scripts/validate_plugin.py tests/fixtures/plugins/sample-script`（已通过）

### Phase 3: PluginRuntime 运行时测试
1. 文件: `zentray/plugins/runtime.py`（已完成）
2. 测试: `pytest tests/unit/test_plugin_runtime.py -q`（已通过）
3. 手动: 运行 fixture 插件，观察日志/进度/超时

### Phase 4: API 端点集成测试
1. 文件: `zentray/api/handlers.py`（已完成）
2. 测试: `pytest tests/unit/test_plugin_install_api.py -q`（已通过）
3. 手动: 测试所有 5 个端点（list / validate / install / run / delete）（已通过）

### Phase 5: Frontend Settings.vue 优化
1. 文件: `web/src/views/Settings.vue`（已完成优化：插件列表、目录选择、刷新、删除、安装预览、参数弹窗等）
2. 测试: 运行前端 + 手动测试目录选择/刷新/删除/参数弹窗（已通过）

### Phase 6: 打包 + 文档
1. 文件: `pyproject.toml` + `docs/USER_MANUAL.md`
2. 测试: 全量 pytest + 打包验证

---

**执行规则**:
- 每个 Phase 完成后立即运行对应测试
- 所有 pytest 通过后才能进入下一 Phase
- 代码修改后用 git add/commit

**Phase 6 完成**：打包 + 文档完善已完成
