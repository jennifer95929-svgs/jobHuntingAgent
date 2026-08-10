"""V3 投递工具 —— apply。

含硬安全护栏(guards.check_before_apply):去重、每日上限、验证码检测、公司规模复核。
投哪家由模型决定(传入 job_id);护栏是安全红线,不是业务取舍。
"""
import json
import os
import sys
import threading

V3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import guards
import history as hist

APPLY_WATCHDOG_SECONDS = 45  # 投递动作看门狗,防单次卡死拖垮整个 loop

_hr_reply_templates = [
    "您好,感谢回复。我看了贵司这个岗位,和我的AI产品经理背景比较匹配,想进一步了解下团队和业务方向。",
    "您好,很高兴收到回复。我在大模型落地的端到端交付上有过完整项目经验,如果方便的话可以聊聊机会。",
]


def _hr_reply_gen(hr_msg: str):
    """HR 首次回复时的自动应答(轮换模板防内容风控)。"""
    import random
    return random.choice(_hr_reply_templates)


def _session():
    from browser.boss_session import BossSession
    global _s
    if _s is None:
        _s = BossSession()
    return _s


_s = None


def apply(job_id: str, job_title: str = "", company: str = "", salary: str = "") -> dict:
    """投递指定岗位。硬护栏:去重、每日上限、验证码、公司规模(>=50/非外包/非404)、薪资范围。"""
    s = _session()

    gate = guards.check_before_apply(s, job_id, salary)
    if not gate["ok"]:
        return {"applied": False, "job_id": job_id, "reason": gate["reason"]}

    # 投递动作可能较慢/偶发卡死,用看门狗线程超时兜底。
    # 不用 multiprocessing:避免 pickling 持有 websocket 的 session。
    box = {}

    def _run():
        try:
            box["ok"] = s.click_apply(job_id, job_title=job_title, company=company, reply_fn=_hr_reply_gen)
        except BaseException as e:
            box["err"] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=APPLY_WATCHDOG_SECONDS)
    if t.is_alive():
        return {"applied": False, "job_id": job_id, "reason": "timeout|投递看门狗超时(可能页面卡住)"}
    if "err" in box:
        return {"applied": False, "job_id": job_id, "reason": f"error|投递异常: {box['err']}"}

    ok = box.get("ok", False)
    if ok:
        hist.record_apply(job_id, company=company, title=job_title)
        # 同步到飞书(失败不影响投递结果)
        try:
            from feishu_sync import sync_to_feishu
            sync_to_feishu({
                "company": company,
                "title": job_title,
                "keyword": "",
                "city": "",
                "salary": "",
            })
        except Exception:
            pass
        return {"applied": True, "job_id": job_id, "today": hist.today_count()}
    return {"applied": False, "job_id": job_id, "reason": "click|点击投递未成功"}