#!/usr/bin/env bash
# 求职 Agent 启动入口
# 依赖: agent-browser (npm i -g agent-browser)
#        python3 + pip install -r requirements.txt
#
# 使用:
#   bash run.sh init     启动浏览器并登录
#   bash run.sh run      执行一轮投递
#   bash run.sh status   查看今日状态
#   bash run.sh chat     检查回复消息
#   bash run.sh edit     编辑简历
#   bash run.sh loop     持续运行（按日轮询）

set -e
cd "$(dirname "$0")"

CMD="${1:-status}"

case "$CMD" in
    init|run|chat|status|edit|profile|history)
        python3 agent.py "$CMD"
        ;;
    loop)
        echo "🔄 求职 Agent 持续模式已启动..."
        echo "   按 Ctrl+C 停止"
        echo ""
        while true; do
            python3 agent.py run
            echo ""
            echo "⏰ $(date '+%H:%M') 本轮完成，等待 2 小时后继续..."
            echo "   按 Ctrl+C 退出"
            echo ""
            sleep 7200
        done
        ;;
    *)
        echo "用法: bash run.sh <命令>"
        echo ""
        echo "命令:"
        echo "  init      启动浏览器并登录 BOSS 直聘（首次使用）"
        echo "  run       执行一轮搜索投递 + 回复消息"
        echo "  chat      仅检查并回复新消息"
        echo "  status    查看今日投递状态"
        echo "  edit      编辑简历信息"
        echo "  profile   查看简历摘要"
        echo "  history   查看完整历史"
        echo "  loop      持续运行（每 2 小时执行一轮）"
        ;;
esac
