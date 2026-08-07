#!/usr/bin/env python3
"""合并 scan 结果到 job_ids 集合(去重), 或打印汇总。

用法:
  merge_jobs.py <scan_result.json> <job_ids.json>            # 合并
  merge_jobs.py <job_ids.json> <job_ids.json> --summary      # 只打印汇总
"""
import json
import os
import sys


def load(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def main() -> int:
    args = sys.argv[1:]
    if len(args) >= 2 and args[-1] == "--summary":
        jobs = load(args[0])
        print(f"累计收集 {len(jobs)} 个职位:")
        for j in jobs[:15]:
            print(f"  - {j.get('title','?')} | {j.get('company','?')} | {j.get('salary','?')} | id={j.get('id','?')}")
        return 0

    scan_path, out_path = args[0], args[1]
    scan = load(scan_path)
    data = scan.get("jobs", []) if isinstance(scan, dict) else scan

    print(f"找到 {len(data)} 个职位:")
    for j in data:
        print(f"  - {j.get('title','?')} | {j.get('company','?')} | {j.get('salary','?')} | id={j.get('id','?')}")

    ids = load(out_path)
    existing = {j.get("id") for j in ids}
    for j in data:
        jid = j.get("id", "")
        if jid and jid not in existing:
            ids.append({
                "id": jid,
                "title": j.get("title", ""),
                "company": j.get("company", ""),
                "salary": j.get("salary", ""),
            })
            existing.add(jid)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
