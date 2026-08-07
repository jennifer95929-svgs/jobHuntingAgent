#!/bin/bash
# GitHub 自托管 Runner 一键注册脚本
# 用法: ./setup_runner.sh <OWNER/REPO> <REGISTRATION_TOKEN>
# 例:  ./setup_runner.sh jennifer95929-svgs/jobHuntingAgent AT...xxx

set -e

if [ $# -lt 2 ]; then
  echo "用法: $0 <OWNER/REPO> <REGISTRATION_TOKEN>"
  echo "例:   $0 jennifer95929-svgs/jobHuntingAgent AT...xxx"
  exit 1
fi

REPO="$1"
TOKEN="$2"
RUNNER_DIR="$HOME/actions-runner"

if [ ! -x "$RUNNER_DIR/config.sh" ]; then
  echo "错误: $RUNNER_DIR/config.sh 不存在，请先安装 runner"
  exit 1
fi

cd "$RUNNER_DIR"

# 清理旧配置（如已注册过）
if [ -f ".runner" ]; then
  echo "检测到已注册配置，先移除..."
  ./config.sh remove --token "$TOKEN" 2>/dev/null || true
  rm -f .runner .credentials .credentials_rsaparams
fi

# 注册（无交互模式）
./config.sh --url "https://github.com/$REPO" \
  --token "$TOKEN" \
  --name "mac-agent-$(hostname | tr -d ' ')" \
  --labels "macos,local,x64" \
  --unattended --replace

echo ""
echo "===== 注册成功 ====="
echo "Runner: $(hostname) / labels: macos,local,x64"
echo ""
echo "启动前台运行（调试）:   ~/actions-runner/run.sh"
echo "注册为系统服务（后台）: ~/actions-runner/svc.sh install && ~/actions-runner/svc.sh start"
