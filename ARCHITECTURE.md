# 求职 Agent 架构

## 一句话

**代码只提供工具和上下文，所有决策由 LLM 自主做出。**

---

## 文件结构

```
job_agent/
├── loop.py              ~50行   极简循环（零业务逻辑）
├── tools.py             ~300行  纯原子操作函数（零决策）
├── system_prompt.py     ~80行   简历 + 工具文档 + 行为规则
├── config.py                    配置
├── pipeline/
│   └── llm.py                   原生 tool_calling 驱动
├── browser/
│   └── boss_session.py          CDP 封装
├── resume/
│   └── profile.json             简历数据
└── data/
    ├── history.json             投递历史
    └── state.json               会话状态
```

---

## 循环流程

```
loop.py:

  1. capture()
     ├─ 读取 badge 数
     ├─ 读取今日投递/回复统计
     ├─ 读取当前页面 URL
     ├─ 读取会话状态 state.json
     └─ 打包为 context dict

  2. LLM(context, tools)
     ├─ system prompt (含简历 + 规则)
     ├─ context（当前状态）
     ├─ tools（可调用函数列表）
     └─ 返回: {action: "tool_name", args: {...}}

  3. execute(action, args)
     └─ tools[action](**args)

  4. save()
     ├─ 更新 state.json
     └─ 追加 trace.jsonl

  5. goto 1
```

关键：**没有 if badge > 0 / if count < 50 / for kw in KWs**。全部由 LLM 看 context 后自主决定下一步。

---

## 工具列表（tools.py 定义的原子操作）

| 工具 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `search_jobs` | keyword, city | 搜索结果页 | 打开 BOSS 搜索页 |
| `scan_page` | 无 | job[] | 提取当前页岗位列表 |
| `inspect_company` | job_id | {eligible, reason} | 打开详情页验证公司规模 |
| `apply` | job_id | bool | 投递 + HR 自动回复 |
| `check_messages` | 无 | {count, previews} | 检测未读消息 |
| `read_conversation` | company | hr_message | 打开对话读取 HR 最新消息 |
| `reply_hr` | company, message | bool | 发送回复 |
| `detect_exchange_card` | 无 | card/null | 检测交换微信/电话卡片 |
| `accept_card` | 无 | bool | 同意交换 |
| `wait` | minutes | 无 | 等待指定时间 |
| `screenshot` | 无 | path | 截图保存 |
| `done` | 无 | 无 | 今日完成，退出 |

---

## 数据流

```
                   LLM
                  ↗    ↖
         context       tool_calls
          ↗                ↖
    capture()          execute()
         ↑                  ↑
    ┌────┴────┐       ┌────┴────┐
    │ Chrome  │       │ Python  │
    │ (DOM)   │       │ 函数     │
    └─────────┘       └─────────┘
                            ↑
                       ┌────┴────┐
                       │ state   │
                       │ history │
                       │ trace   │
                       └─────────┘
```

---

## 与旧架构的关键差异

| | 旧 | 新 |
|---|---|---|
| **决策主体** | Python if/else | LLM 思维链 |
| **代码类型** | 业务逻辑编排 | 纯工具层 |
| **LLM 角色** | 填空 | 驾驶员 |
| **坏 case 修复** | 改 Python 代码 | 改 system prompt 文字 |
| **扩展新功能** | 加 if/else 分支 | 加一个 tool function |
| **可观测性** | 文本日志 | 结构化 trace.jsonl |
| **复现性** | 随机 | seed=42 可复现 |
