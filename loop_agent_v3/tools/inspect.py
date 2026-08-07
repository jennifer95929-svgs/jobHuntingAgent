"""V3 岗位验证工具 —— inspect_company。

只读检查公司规模>=50、非外包、非404下架;不投递。
"""
import os
import sys

V3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _session():
    from browser.boss_session import BossSession
    global _s
    if _s is None:
        _s = BossSession()
    return _s


_s = None


def inspect_company(job_id: str) -> dict:
    """打开岗位详情页,只读检查公司规模是否>=50且非外包、非下架。不投递。"""
    eligible, reason = _session().check_company_eligible(job_id)
    return {"job_id": job_id, "eligible": eligible, "reason": reason}