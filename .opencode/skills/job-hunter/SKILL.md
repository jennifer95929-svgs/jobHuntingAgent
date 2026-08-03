---
name: job-hunter
description: BOSS直聘自动投递与HR沟通——架构配置存于此，供后续调优参考
metadata:
  daily_limit: "50"
  models:
    orchestrator: GLM-4.7
    batch_filter: Doubao Seed 2.0 Lite
    greeting: Doubao Seed 2.0 Lite
---

## Architecture Overview

```
OpenCode Agent Loop (GLM-4.7 orchestrator)
  │
  ├── ① Search (rules, no LLM)
  │     → boss_search(keywords, cities)
  │     → CDP: createTab → wait cards → extract [{id, title, salary, company, jd, industry}]
  │
  ├── ② Batch Filter (Doubao Lite, 1 call per batch)
  │     → boss_batch_filter(jobs, resume)
  │     → 快速排除外包/薪资不符/方向不对
  │     → 输出 pass/skip + 简短理由
  │
  ├── ③ Company Research (GLM-4.7, multi-step)
  │     → for each candidate:
  │         web_search("融资历史")
  │         web_search("产品口碑")
  │         web_search("赛道竞争")
  │         LLM综合 → {prospect, advantage, weakness, recommend}
  │
  ├── ④ Match Analysis (GLM-4.7)
  │     → boss_match(jd, company_report, resume)
  │     → {score, reason, strategy}
  │
  ├── ⑤ Apply (rules, no LLM)
  │     → for score > 70:
  │         boss_apply(job_id) → CDP click
  │
  └── ⑥ Chat Monitor (every 10min)
        → check_unread (rules)
        → LLM intent analysis (GLM-4.7)
        → LLM reply generation (Doubao Lite)
        → send_message (rules)
```

## Model Assignment Rationale

| Phase | Model | Why |
|-------|-------|-----|
| Orchestration | GLM-4.7 | Needs multi-step reasoning + tool orchestration |
| Batch filter | Doubao Lite | Fast keyword+semantic pass, no deep reasoning |
| Company research | GLM-4.7 | Needs web search chaining + synthesis |
| Match score | GLM-4.7 | Core decision, needs resume+JD understanding |
| Greeting gen | Doubao Lite | Generation task, shallow reasoning needed |
| HR intent | GLM-4.7 | Needs conversation context understanding |
| HR reply gen | Doubao Lite | Generation based on strategy |

## Tuning Points

- batch_filter threshold: adjust pass rate by modifying prompt strictness
- company_research sources: add/remove search queries
- match_score threshold: currently 70, adjust for aggressiveness
- daily_limit: config.py MAX_APPLY_PER_DAY
- model swap: change model name in config.py for generation tasks
