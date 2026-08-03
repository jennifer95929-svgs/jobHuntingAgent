import time
import sys
import os

LOOP_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(LOOP_ROOT, ".."))
sys.path.insert(0, LOOP_ROOT)
sys.path.insert(0, PROJECT_ROOT)

from core.perceive import perceive_badge, has_changed
from core.decide import build_plan
from core.execute import execute_action
from core.state import increment_heartbeat

HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "2.5"))
TICK_INTERVAL = int(os.environ.get("TICK_INTERVAL", "60"))

BUSY = False
last_badge = None
last_tick = 0.0


def _ensure_browser():
    from browser.boss_session import BossSession
    s = BossSession()
    s.ensure_browser(headed=True)
    return s


def main():
    global BUSY, last_badge, last_tick

    print(f"[loop] 启动 心跳={HEARTBEAT_INTERVAL}s 定时={TICK_INTERVAL}s")

    session = _ensure_browser()

    try:
        last_badge = perceive_badge()
        last_tick = time.time() - TICK_INTERVAL
        print(f"[loop] 初始 badge={last_badge}")
    except Exception as e:
        print(f"[loop] 初始感知失败: {e}")
        last_badge = -1
        last_tick = time.time() - TICK_INTERVAL

    while True:
        time.sleep(HEARTBEAT_INTERVAL)

        if BUSY:
            continue

        try:
            current_badge = perceive_badge()
        except Exception as e:
            print(f"[loop] 感知异常: {e}")
            continue

        dirty = has_changed(current_badge, last_badge)
        tick = (time.time() - last_tick) >= TICK_INTERVAL

        if not dirty and not tick:
            continue

        print(f"[loop] 触发: dirty={dirty} badge={current_badge} tick={tick}")
        BUSY = True

        try:
            plan = build_plan(badge=current_badge, is_tick=tick)
            for action in plan:
                atype = action.get("type")
                target = action.get("target", {}).get("company", "--")
                print(f"[loop] 执行: {atype} @ {target}")

                if atype == "apply_jobs":
                    from core.apply import try_apply
                    result = try_apply(session)
                    print(f"[loop] 投递结果: {result.get('applied')} 家 (今日 {result.get('total')})")
                else:
                    result = execute_action(action)
                    print(f"[loop] 结果: {result.get('status')} id={result.get('action_id','')}")
        except Exception as e:
            print(f"[loop] 执行异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            BUSY = False
            last_badge = current_badge
            if tick:
                last_tick = time.time()

        increment_heartbeat()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[loop] 用户中断")
        sys.exit(0)
