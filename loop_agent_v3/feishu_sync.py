"""飞书投递记录同步 —— 投递成功后把公司信息写入飞书电子表格。

表格: 求职投递记录 (token + sheet_id 从 config/env 读取)
表头: 日期 | 时间 | 关键词 | 城市 | 公司 | 岗位 | 薪资 | 状态
"""
import os
import sys
import time
from datetime import date

import requests

V3_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_FEISHU_BASE = "https://open.feishu.cn"
_session = requests.Session()
_token_cache = {"token": "", "expires_at": 0}

_SPREADSHEET_TOKEN = os.getenv("JOB_SPREADSHEET_TOKEN", "HiuRsHvGRhXHZfteiIZcQsVwndh")
_SHEET_ID = os.getenv("JOB_SHEET_ID", "9554f5")


def _get_token() -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    resp = _session.post(
        f"{_FEISHU_BASE}/open-apis/auth/v3/tenant_access_token/internal",
        json={
            "app_id": os.getenv("FEISHU_APP_ID", ""),
            "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"飞书 token 获取失败: {data.get('msg')}")
    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires_at"] = now + data.get("expire", 7200) - 60
    return _token_cache["token"]


def _next_row(headers) -> int:
    """读 A 列找到最后有数据的行, 返回下一行行号。"""
    url = f"{_FEISHU_BASE}/open-apis/sheets/v2/spreadsheets/{_SPREADSHEET_TOKEN}/values/{_SHEET_ID}!A:A"
    resp = _session.get(url, headers=headers, timeout=10)
    rows = resp.json().get("data", {}).get("valueRange", {}).get("values", [])
    return max(len(rows), 1) + 1


def _batch_write(records: list, start_row: int, headers) -> bool:
    """批量写入多条记录到表格, 从 start_row 开始。返回是否成功。"""
    if not records:
        return True
    values = [[
        r.get("date", str(date.today())),
        r.get("time", time.strftime("%H:%M:%S")),
        r.get("keyword", ""),
        r.get("city", ""),
        r.get("company", ""),
        r.get("title", ""),
        r.get("salary", ""),
        "已投递",
    ] for r in records]
    end_row = start_row + len(values) - 1
    body = {"valueRange": {"range": f"{_SHEET_ID}!A{start_row}:H{end_row}", "values": values}}
    resp = _session.put(
        f"{_FEISHU_BASE}/open-apis/sheets/v2/spreadsheets/{_SPREADSHEET_TOKEN}/values",
        headers=headers,
        json=body,
        timeout=15,
    )
    return resp.json().get("code") == 0


def sync_to_feishu(job_info: dict) -> bool:
    """写入一条投递记录到飞书。返回是否成功。"""
    try:
        token = _get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        next_row = _next_row(headers)
        return _batch_write([job_info], next_row, headers)
    except Exception:
        return False


def backfill_from_history(history_path: str) -> dict:
    """把 history.json 中尚未同步到飞书的投递记录补录。

    返回 {"synced": n, "failed": m, "skipped": k}。
    """
    import json
    try:
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)
    except Exception as e:
        return {"synced": 0, "failed": 0, "skipped": 0, "error": str(e)}

    # 收集所有投递记录(带日期)
    records = []
    for day, day_data in history.items():
        if not isinstance(day_data, dict):
            continue
        for a in day_data.get("applied", []):
            records.append({**a, "date": day})

    # 与飞书现有数据去重(按 日期+公司+岗位)
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{_FEISHU_BASE}/open-apis/sheets/v2/spreadsheets/{_SPREADSHEET_TOKEN}/values/{_SHEET_ID}!A1:F500"
    resp = _session.get(url, headers=headers, timeout=10)
    existing = resp.json().get("data", {}).get("valueRange", {}).get("values", [])[1:]
    existing_keys = set()
    for row in existing:
        if len(row) >= 6:
            existing_keys.add((row[0], row[4], row[5]))

    synced = failed = skipped = 0
    # 批量写入: 每 50 条一批
    pending = []
    for rec in records:
        key = (rec.get("date", ""), rec.get("company", ""), rec.get("title", ""))
        if key in existing_keys:
            skipped += 1
            continue
        pending.append(rec)

    for i in range(0, len(pending), 50):
        batch = pending[i:i + 50]
        next_row = _next_row(headers)
        if _batch_write(batch, next_row, headers):
            synced += len(batch)
        else:
            failed += len(batch)

    return {"synced": synced, "failed": failed, "skipped": skipped}
