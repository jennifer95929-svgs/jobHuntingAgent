#!/usr/bin/env python3
"""批量投递 job_ids.json 中的职位, 结果写入 /tmp/apply_results.json。

用法:
  apply_jobs.py <max_apply> [job_ids_path] [project_dir]
"""
import json
import os
import subprocess
import sys

MAX_APPLY = int(sys.argv[1]) if len(sys.argv) > 1 else 5
JOB_IDS = sys.argv[2] if len(sys.argv) > 2 else "/tmp/job_ids.json"
PROJECT = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/job-agent")
OUT = "/tmp/apply_results.json"


def main() -> int:
    if not os.path.exists(JOB_IDS):
        print("没有职位 ID 文件, 跳过投递")
        return 0
    with open(JOB_IDS, encoding="utf-8") as f:
        jobs = json.load(f)

    venv_py = os.path.join(PROJECT, "loop_agent_v3", ".venv", "bin", "python")
    cli = os.path.join(PROJECT, "loop_agent_v3", "cli.py")
    if not os.path.exists(venv_py):
        venv_py = "python3"

    print(f"=== 开始投递 (最多 {MAX_APPLY} 个) ===")
    results = []
    for idx, j in enumerate(jobs[:MAX_APPLY], 1):
        jid = j.get("id", "")
        if not jid:
            continue
        title = j.get("title", "")
        company = j.get("company", "")
        print(f"[{idx}] 投递: {title} ({company}) id={jid}", flush=True)
        try:
            r = subprocess.run(
                [venv_py, cli, "apply", jid, title, company],
                capture_output=True, text=True, timeout=70,
            )
            out = r.stdout.strip() or r.stderr.strip()
        except subprocess.TimeoutExpired:
            out = "timeout|单个投递超时70s"
        except Exception as e:  # noqa: BLE001
            out = f"error|{e}"
        print(f"  结果: {out}", flush=True)
        try:
            parsed = json.loads(out)
            results.append({
                "job_id": jid, "title": title,
                "applied": parsed.get("applied"),
                "reason": parsed.get("reason", ""),
            })
        except Exception:
            results.append({"job_id": jid, "title": title, "applied": False, "reason": out[:100]})

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    applied = sum(1 for r in results if r.get("applied"))
    skipped = len(results) - applied
    print(f"=== 投递完成: 成功 {applied}, 跳过/失败 {skipped} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
