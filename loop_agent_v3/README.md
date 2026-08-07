# loop_agent_v3 —— 用 opencode loop 驱动的 BOSS 直聘求职 Agent

V2 的循环层(loop.py + llm.py 手写 tool-calling)交给 opencode Goal Loop,Python 只保留**浏览器原子操作**与**硬护栏**。

## 架构

```
opencode Goal Loop (job-hunter-v3 agent)
  │  mcp__boss_*  工具(每步决定下一步)
  ▼
boss MCP server (loop_agent_v3/server.py, MCP2.0 stdio)
  ├── tools/search.py      search_jobs / scan_page / page_text / screenshot
  ├── tools/inspect.py     inspect_company (含 404/下架检测)
  ├── tools/apply.py       apply (护栏内置 + 45s 看门狗)
  ├── tools/chat.py        check_messages
  └── guards.py            硬护栏:去重 / 每日上限50 / 验证码 / 公司规模复核
```

- 决策全归模型(opencode);护栏是安全红线,不掺业务取舍
- `browser/` CDP 层与 v2 共享,零改动
- `data/history.json`(v2 同款)作唯一去重源

## 文件

| 文件 | 说明 |
|---|---|
| `server.py` | MCP server,9 个工具,适配 MCP Python SDK 2.0 |
| `tools/` | 工具实现,从 v2 `tools.py` 迁移 |
| `guards.py` | apply 前 4 道护栏(顺序固定) |
| `history.py` / `salary_decode.py` | 从 v2 拷贝,原样复用 |
| `.opencode/agents/job-hunter-v3.md` | 主 agent 定义(权限:edit/write/bash deny) |
| `.opencode/skills/job-hunter-v3/SKILL.md` | 简历 + 域名知识 + 回复模板 |
| `opencode.json`(工作区根) | 注册 boss MCP |
| `cli.py` | 冒烟测试 CLI(不依赖 mcp 库) |

## 环境

- Python 3.14 venv:`.venv/`,依赖 mcp/openai/websockets/python-dotenv
- 安装命令(若重建):
  ```
  python3.14 -m venv .venv
  .venv/bin/pip install --only-binary=:all: -i https://pypi.tuna.tsinghua.edu.cn/simple mcp openai python-dotenv websockets
  ```

## 启动

1. Chrome 带调试端口运行,已登录 BOSS(Profile `/tmp/chrome-debug-profile`):
   ```
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug-profile about:blank &
   ```
2. 重启 opencode(加载 boss MCP + job-hunter-v3 agent)
3. 切到 job-hunter-v3 agent,下达目标:
   ```
   按 WORKFLOW 规则投递 AI产品经理,直到 data/history.json 今日投满 50
   或所有关键词×城市组合(及各SEO岗位)穷尽
   ```

## 冒烟测试(已完成验证)

```
.venv/bin/python cli.py search "AI产品经理" "深圳"   # ok
.venv/bin/python cli.py scan                        # 返回岗位列表(最多8条)
.venv/bin/python cli.py inspect <job_id>            # 合格/不合格(含404检测)
.venv/bin/python cli.py apply <job_id> [title] [company]  # 护栏拦截或真实投递
.venv/bin/python cli.py messages                    # 未读数
```
MCP stdio 客户端验证:握手成功、9 工具注册、check_messages/wait 真实调用通过。

## 失败 reason 类型(apply 返回)

`duplicate|` 已投过 · `limit|` 今日满50 → done · `captcha|` 验证码→done 不重试
`company|` / `dead|` 不合格/下架 · `timeout|` / `click|` / `error|` 偶发,换岗不重试