#!/bin/bash
# GitHub Runner 上验证 BOSS直聘 投递环境是否就绪
# 用途: workflow_dispatch 手动触发, 检查 Chrome + 登录态 + Python 环境
set -euo pipefail

PROFILE_DIR="${BOSS_PROFILE_DIR:-$HOME/boss-chrome-profile}"
DEBUG_PORT="${BOSS_DEBUG_PORT:-9222}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

echo "=== [1/5] 检查 Chrome ==="
if [ ! -x "$CHROME" ]; then
  echo "ERROR: Chrome 不存在: $CHROME"
  exit 1
fi
echo "OK: Chrome 存在"

echo "=== [2/5] 检查调试端口 $DEBUG_PORT ==="
if curl -s --connect-timeout 3 "http://127.0.0.1:$DEBUG_PORT/json/version" > /dev/null 2>&1; then
  echo "OK: 已有 Chrome 监听调试端口 (可复用)"
else
  echo "未检测到调试端口, 尝试启动 Chrome (profile: $PROFILE_DIR)"
  mkdir -p "$PROFILE_DIR"
  nohup "$CHROME" \
    --remote-debugging-port=$DEBUG_PORT \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    about:blank > /tmp/boss-chrome.log 2>&1 &
  CHROME_PID=$!
  echo "Chrome 启动中 (pid=$CHROME_PID)..."
  for i in $(seq 1 15); do
    if curl -s --connect-timeout 2 "http://127.0.0.1:$DEBUG_PORT/json/version" > /dev/null 2>&1; then
      echo "OK: 调试端口就绪 (第 ${i}s)"
      break
    fi
    sleep 1
  done
  if ! curl -s --connect-timeout 3 "http://127.0.0.1:$DEBUG_PORT/json/version" > /dev/null 2>&1; then
    echo "ERROR: Chrome 启动失败, 查看 /tmp/boss-chrome.log"
    exit 1
  fi
fi

echo "=== [3/5] 检查 BOSS直聘 登录态 ==="
# 从调试端口获取 tabs, 寻找 BOSS 页面
LOGIN_CHECK=$(curl -s --connect-timeout 5 "http://127.0.0.1:$DEBUG_PORT/json" | python3 -c "
import json,sys
try:
    tabs = json.load(sys.stdin)
    urls = [t.get('url','') for t in tabs]
    print('\\n'.join(urls))
except Exception as e:
    print(f'parse error: {e}')
" 2>/dev/null | grep -c "zhipin.com" || true)
echo "BOSS 相关标签页数: $LOGIN_CHECK"

# 用无头请求验证登录 cookie (通过 CDP 读取 localStorage 复杂, 先做存在性检查)
if [ -d "$PROFILE_DIR" ]; then
  COOKIE_FILES=$(find "$PROFILE_DIR" -name "Cookies" 2>/dev/null | head -3)
  echo "Profile cookies 文件:"
  echo "$COOKIE_FILES" | sed "s|$HOME|~|g" || echo "  (无)"
  if [ -n "$COOKIE_FILES" ]; then
    echo "OK: 检测到 Cookie 存储 (登录态大概率存在, 最终以页面验证为准)"
  fi
fi

echo "=== [4/5] 检查 Python 环境 ==="
python3 --version
python3 -m pip --version
if python3 -c "import mcp, websockets, dotenv" 2>/dev/null; then
  echo "OK: mcp/websockets/dotenv 已安装"
else
  echo "WARN: 缺少 mcp/websockets/dotenv, 投递前需要 pip install"
fi

echo "=== [5/5] 检查 .env 密钥 ==="
ENV_FILE="${BOSS_ENV_FILE:-$HOME/job-agent.env}"
if [ -f "$ENV_FILE" ]; then
  echo "OK: $ENV_FILE 存在 ($(wc -c < "$ENV_FILE" | tr -d ' ') bytes)"
  grep -oE "^[A-Z_]+=" "$ENV_FILE" | sed 's/=$//' || true
else
  echo "WARN: $ENV_FILE 不存在 (密钥需从 GitHub Secrets 注入或放置于此)"
fi

echo ""
echo "===== 环境检查完成 ====="
