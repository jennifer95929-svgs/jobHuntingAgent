# Job Agent Architecture

## Design Principle

Pipeline architecture: **Rules for execution, LLM for decisions**.

LLM only intervenes at 3 points:
1. Batch filter (light model) — fast pass/skip
2. Company research (heavy model) — multi-step web search + synthesis
3. Match analysis (heavy model) — resume+JD+company report → score

Everything else (DOM interaction, click, navigation, dedup, pagination) = fixed rules.

## Model Assignment

| Phase | Model | Role |
|-------|-------|------|
| Orchestrator | GLM-4.7 / Qwen-Plus | Multi-step reasoning + tool orchestration |
| Batch filter | Doubao Seed Lite | Quick pass on title+salary |
| Company research | GLM-4.7 / Qwen-Plus | Web search chaining + synthesis |
| Match score | GLM-4.7 / Qwen-Plus | Core decision: resume+JD matching |
| Greeting gen | Doubao Seed Lite | Generation only |
| HR intent | GLM-4.7 / Qwen-Plus | Conversation context understanding |
| HR reply gen | Doubao Seed Lite | Text generation based on strategy |

## Pipeline Flow

```
Search (rules)
  → batch_filter (Doubao Lite, 1 call)
  → for each pass:
       company_report (GLM-4.7, multi-step)
       match_score (GLM-4.7, 1 call)
  → sort by score → apply top (rules)
  → next page or next keyword/city
```

## Cost Estimation

50 jobs/day:
- batch_filter: 1 call (Doubao) = ¥0.001
- company_report: ~5 calls (GLM-4.7) = ¥0.15
- match: ~5 calls (GLM-4.7) = ¥0.15
- greeting: ~5 calls (Doubao) = ¥0.005
- chat replies: ~5 calls (Doubao) = ¥0.005
- **Total: ~¥0.31/day**

## Tuning Points

- `config.py`: MODEL_LIGHT / MODEL_HEAVY — swap models per phase
- `pipeline/filter.py`: FILTER_TEMPLATE — adjust strictness
- `pipeline/research.py`: ANALYSIS_TEMPLATE — adjust analysis focus
- `pipeline/matcher.py`: MATCH_TEMPLATE — adjust scoring criteria
- `config.py`: MAX_APPLY_PER_DAY — daily limit
- `agent.py`: score threshold (currently >0 = apply)
