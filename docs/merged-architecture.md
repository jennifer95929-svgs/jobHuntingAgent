# Merged Architecture: Loop Daemon + PDA Kernel

## 设计原理

```
你的 Loop（AI 在浏览器里操作）  ← 解决改版问题
我的 PDA（结构化决策 + 验证）   ← 解决信任问题
            ↓
     合并: Python 构建结构化指令 → AI 执行 → Python 验证
```

**核心信条**: 各取所长，不把任何事全交给单一主体。

| 谁擅长什么 | 交给谁 |
|-----------|--------|
| 读页面、适应改版、点击按钮 | AI（在浏览器里操作） |
| 追踪状态、计时、验证结果 | Python（工程代码） |
| 生成回复文本、分析策略 | LLM（轻量模型） |
| 排序、去重、记录、重试 | Python（工程代码） |

---

## 顶层循环

```
loop.py (Daemon)
────────────────────────────────────────────────────────────

while True:
    sleep(HEARTBEAT_INTERVAL)        # 默认 2.5s

    if BUSY:                         # ← 执行锁，防并发
        continue

    snapshot = perceive()            # 只检测变化（读 badge 计数 + 对比上次）

    if not snapshot.has_changes():
        # 每分钟检查一次沉默任务（如定时投递、面试预备）
        if not time_to_tick():
            continue

    BUSY = True

    state   = build_state()          # 收集完整状态（页面 + JSON 历史）
    plan    = decide_plan(state)     # 生成结构化执行计划

    for action in plan.actions:
        result = execute(action)     # 注入指令 → AI 执行
        verify(action, result)       # 读 DOM 验证
        update_json(action, result)  # 持久化

    BUSY = False
```

---

## 三层结构

```
┌─────────────────────────────────────────────────────────┐
│                    Loop Daemon                           │
│                     (loop.py)                            │
│                                                          │
│   心跳 + 脏检查 + 执行锁 + 结构化决策 + 验证 + 持久化     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────┐   ┌─────────────────┐              │
│  │  Perceive 感知层  │   │   Decide 决策层  │              │
│  │                  │   │                  │              │
│  │  read_badge()    │   │  LLM优先级排序    │              │
│  │  load_json()     │──▶│  生成 action list │              │
│  │  compare_state() │   │  每个action有:    │              │
│  │  collect_dom()   │   │  target, type,   │              │
│  └─────────────────┘   │  context, verify  │              │
│                         └────────┬─────────┘              │
│                                  │                         │
│                                  ▼                         │
│  ┌─────────────────────────────────────────────┐          │
│  │              Act 执行层                       │          │
│  │                                              │          │
│  │  build_instruction(action) → JSON struct    │          │
│  │  inject_prompt(instruction_json)            │          │
│  │  AI 在浏览器里执行操作                        │          │
│  │  verify_by_dom()   ← 验证结果               │          │
│  │  update_history()  ← 写入 JSON              │          │
│  └─────────────────────────────────────────────┘          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 数据结构

### 指令结构 (Python → AI)

```python
# Python 构建，注入给 AI
instruction = {
    "action_id": "act_001",           # 唯一ID，用于验证
    "type": "reply_hr",               # 动作类型
    "target": {
        "company": "赛托生物",
        "hr_name": "林先生"
    },
    "context": {                      # 注入上下文，减少AI的幻觉空间
        "hr_message": "是否有AI实战经验？",
        "resume_summary": "...",
        "reply_draft": "2年AI产品落地经验，之前在央企主导过AI Agent、RAG类5款..."
    },
    "verify_rule": {                  # 验证规则（Python 执行，不依赖AI）
        "after_action": "check_textarea_empty",
        "expected": True
    }
}
```

### 状态 JSON (持久化)

```json
{
  "2026-07-22": {
    "conversations": {
      "赛托生物": {
        "stage": "hr_asked",
        "priority": "high",
        "messages": [
          {"role": "hr", "text": "是否有AI实战经验？", "time": "14:00"},
          {"role": "me", "text": "2年AI产品经验...", "time": "14:01"}
        ],
        "reply_count": 1,
        "last_action_id": "act_001",
        "verified": true
      }
    },
    "meta": {
      "heartbeat_count": 1234,
      "action_count": 47,
      "success_count": 45,
      "fail_count": 2
    }
  }
}
```

---

## 执行流程详细

### 单次 action 执行

```
execute(action):
  1. build_instruction(action)        # Python 组装指令 JSON
  2. inject_prompt(instruction)       # 注入给 AI
  3. wait_for_ai(3s)                  # 等 AI 执行完毕
  4. result = verify(action)          # Python 读 DOM 验证
  5. if not result:
       retry(instruction)             # 重试 1 次
       if not verify():
         fallback(action)             # CDP 物理点击兜底
         verify()
  6. update_json(action, result)
  7. return result
```

### 验证规则表

| Action 类型 | 验证方法 |
|-------------|---------|
| `switch_conversation` | 读聊天区标题文本是否包含 target company |
| `send_message` | 读 textarea 是否已清空，聊天区最后一条消息是否匹配 |
| `click_exchange_card` | 检测 exchange card DOM 是否消失 |
| `search_jobs` | 读搜索结果列表是否有 job items |
| `apply_job` | 检测是否弹出聊天对话框 |

---

## 文件结构

```
loop_agent/
├── loop.py              # 主循环：心跳 + 脏检查 + 执行锁
├── config.py            # 配置
├── core/
│   ├── perceive.py      # 感知层：读 badge、读 DOM、比较状态
│   ├── decide.py        # 决策层：构建 plan、调用 LLM 排序
│   ├── execute.py       # 执行层：build_instruction → inject → verify
│   └── state.py         # JSON 读写 + 状态机
├── driver/
│   ├── injector.js      # 注入到页面的脚本（js-reverse-cloak）
│   └── cdp_bridge.py    # CDP 连接 + 通信
├── data/
│   └── state.json       # 持久化状态
└── pipeline/
    ├── llm.py           # LLM 调用（引用父项目接口）
    └── prompt.py        # 指令模板
```

---

## Phase 1 落地范围（确认用）

Phase 1 只改执行层的可靠性，不改你的 Loop 骨架。

| 改动 | 文件 | 说明 |
|------|------|------|
| 心跳 + 脏检查 | `loop.py`, `core/perceive.py` | 2.5s 循环，只读 badge 计数对比上次，有变化才进完整流程 |
| 执行锁 | `loop.py` | `BUSY` 标志位，并发跳过 |
| 验证 loop | `core/execute.py` | `verify_by_dom()` 函数，读 DOM 确认操作结果，失败→重试→fallback CDP |
| 结构化指令注入 | `core/execute.py` | Python 组装 `instruction` JSON，注入给 AI |
| 状态 JSON 升级 | `core/state.py` | 从线性历史改为 `{company: {stage, priority, messages, verified}}` |
| 决策层 | `core/decide.py` | 接收 badge + tick 信号，生成 action list |
| 定时任务 | `loop.py` | 每 60s tick 一次，检查沉默对话跟进 |

不改：
- AI 仍然在浏览器里操作（不改你的执行方式）
- `js-reverse-cloak` 仍然保留（不改你的反检测）
- `execCommand` 仍然使用（不改你的输入方式）

---

## 对比验证

```
合目前的问题
  消息发错人 → 无验证
  AI 说做了但实际没做 → 无验证
  心跳可能在执行中触发 → 无锁
  状态只有投递记录 → 无 conversation stage

合并后
  每次 action 后 verify() → 发错可发现
  verify() 读 DOM 不依赖 AI → 独立验证
  BUSY 锁 → 心跳不会并发
  state.json 含 stage/priority/verified → 可追踪
```

---

请核实以上设计，确认：
1. 整体架构方向是否符合你的预期
2. Phase 1 范围是否正确（只加验证+锁，不改你的执行方式）
3. 数据结构中的 `instruction` 和 `state.json` 格式是否需要调整
