# loop_agent_v2 变更记录 (CHANGELOG)

记录 V2 投递架构的每次演进。约定:
- 变更不碰 V1 / opencode 共享的 `browser/` 层,只在 `loop_agent_v2/` 内完成。
- 架构图事实源 = `draw_diagram.py`;改动架构后重新生成 PNG。

---

## 2026-08-03 — 真实投递 + 稳定性 + 方案3(每投N家自动停)

**背景**:V2 从"只读联调"切换到"真实投递"。模型完全自主决策投哪家、下一步干嘛;代码仅提供动作工具 + 安全护栏。

### 新增 / 修改文件
- `history.py`(新):读写真实 `data/history.json`,含去重、每日上限、计数。护栏,非决策。
- `tools.py`(改):
  - 加回 `apply` 工具 —— 复用 V1 `BossSession.click_apply`,含 HR 自动回复。
  - `apply` 内置硬护栏:去重、每日上限、验证码检测、投前规模复核(不合格不投)。
  - `apply` 投递动作加**看门狗线程超时(45s)**,避免单次卡死拖垮整个 loop。
  - 新增 `_close_stale_job_tabs()`:每个 `search_jobs` 后清理堆积的岗位列表 tab(只动 `web/geek/jobs`,不动 chat/详情)。**解决长时运行 tab 累积累耗导致的硬崩**。
- `llm.py`(改):真模型调 DeepSeek(litellm 4000,带 master_key);`_http_chat` 加**裁剪重试**:遇到 DeepSeek 偶发的 `insufficient tool messages` 400 时,裁剪最近一组 assistant+tool 历史重试,**绕开其严格的 tool 配对校验**。
- `loop.py`(改):
  - 启动文案改真实投递模式。
  - `llm_call` 包 try/except —— 持久失败时优雅收尾,不再整进程崩溃。
  - **方案3**:新增 `V2_RUN_TARGET`(默认 5),本跑投满 N 家即干净退出,由外部重启 `loop.py` 续投(去重护栏自动跳过已投)。规避长时运行的脆弱点。
- `RULES.md`(改):新增「决策流程(最高优先级)」+「投递纪律」—— 只投 `inspect_company` 合格岗、不反复重试同一岗位。
- `draw_diagram.py` + `loop_agent_v2_架构图.png`(本日早前):架构图。

### 运行时
```
V2_RUN_TARGET=5 python3 -u loop.py   # 每跑投满 5 家即停,重启续投
V2_MAX_ITERATIONS=400                 # 兜底护栏,实际停止由批次/上限/验证码决定
```

### 关键决策
- **护栏 ≠ 决策**:`apply`/`history` 的护栏拦"不能投"(重复/超限/风控/规模),**不替模型决定投哪家** —— 岗位选择完全在 LLM。
- **不碰 V1**:所有稳定性修复都在 `loop_agent_v2/` 内完成,不动 opencode 共用的 `browser/`。

### 已修复的稳定性问题(演进顺序)
1. tab 堆积 → 崩溃:加 `_close_stale_job_tabs()`。
2. DeepSeek 偶发 400(insufficient tool messages):加裁剪重试。
3. 长时运行偶发卡死:加优雅收尾 + 方案3 批次停止。

---

## 变更记录模板(以后新增往里加)
```
## YYYY-MM-DD — 简述
**目标**:...
**改动文件**:...
**运行时**:...
**关键决策**:...
```
