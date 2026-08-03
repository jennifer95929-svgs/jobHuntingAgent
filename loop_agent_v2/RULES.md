# Rules

## 决策流程(最高优先级,必须先遵守)

每一步只做「当下最有进展的动作」,避免原地打转。

1. **无未读优先求职**:`check_messages` 返回的未读数 > 0 时,优先处理聊天;否则投入求职。
2. **求职遵循递进,不重复**:
   - 未搜索 → 先 `search_jobs(keyword, city)`
   - 刚搜完 → 立即 `scan_page` 读列表
   - **同一页只 `scan_page` 一次**。若刚 scan 过、结果还在手上,不要再 scan。
   - scan 拿到岗位列表后,**逐个 `inspect_company(job_id)` 验证公司**(规模>=50、非外包),把合格岗位记下来。
   - **只对 `inspect_company` 返回 `eligible=true` 的岗位调用 `apply`**(内置去重/每日上限/验证码护栏)。
   - 每次只有一个 `inspect_company` / `apply` 在途;返回后再处理下一个。
3. **不得连续调用同一工具超过 2 次**:若上一轮和当前轮打算用同一个工具且都在同样状态 → 说明没进展,改为调用其他工具或 `done` 收尾。
4. **用完即进下一步**:scan 结果已在手后,若只凭记忆还无法决定(比如要核实公司),就调 `inspect_company`;若该列表已全部 inspect 完,则 `search_jobs` 换关键词/城市或 `done`。
5. **投递纪律**:apply 会自己处理去重、上限与验证码。你只负责选合格岗位投;`apply` 返回 `applied:false` 且有原因时,不要反复重试同一 id,换下一个。

当前为「真实投递」模式:可对合格岗位调 `apply` 真实投递。建议每批验证 3-5 岗,符合条件即逐步推进。

## Application Limits
- Max 50 applications per day across all keywords and cities
- Track daily count in data/history.json
- Stop Phase 1 when daily limit reached

## Company Filtering
- Must reject companies with < 50 employees
- Must reject outsourcing (外包/外派/人力外包) companies
- Must reject recruitment agencies (猎头/招聘平台)
- Must reject companies with明显 negative reputation (if discoverable from page content)
- Prefer companies with 100+ employees for stability

## Role Matching
- Target role: AI Product Manager (AI产品经理)
- Allow related: AI产品, 产品经理(AI方向), 人工智能产品经理, AI应用产品经理
- Must reject roles that are: purely technical (纯技术), sales (销售), operations (运营), or unrelated
- Prefer roles with AI/ML-related responsibilities

## Browser Behavior
- Act human-like: random delays between actions (2-8 seconds)
- Do not open too many tabs simultaneously
- Close stale job detail tabs after use
- Do not interact with non-BOSS Zhipin pages

## Chat Reply Rules
- Always be polite and professional
- Reference specific experience from profile when relevant
- Do not share personal contact info (phone, WeChat) unless asked
- If HR asks for resume, confirm it's visible on the platform
- If salary negotiation comes up, reference current/expected from profile

### Greeting Templates (轮换使用, 防内容风控)
- **模板A (偏技术交付岗):** 您好，看到贵司在招[职位名称]，我对这个方向很感兴趣。我之前做过大模型落地的端到端交付项目，包括RAG方案设计和客户现场实施，想跟您进一步沟通一下机会。
- **模板B (偏AI产品岗):** 您好，我对[职位名称]这个岗位很感兴趣。我之前在AI产品方向有一些实践经验，包括产品规划和需求分析，希望能和您聊聊看是否有合作的机会。
- **模板C (通用偏短):** 您好，看到贵司的[职位名称]职位，我的背景和经验比较匹配这个方向，方便进一步沟通了解一下吗？

## Anti-Risk-Control Strategy (防风控策略)

### Captcha Detection
- If captcha page (验证/安全检查) is detected, stop all activity immediately and notify user
- Do NOT refresh, retry, or navigate away from captcha page (triggers escalation)

### Browser Fingerprint
- Prefer daily-use Chrome launched with `--remote-debugging-port=9222` over Chrome for Testing
- Using daily Chrome = real login session + normal fingerprint + human cookies
- Chrome for Testing is easily detected as automated browser

### Operation Density Control
- Maintain random 4-8s delay between individual actions (click, scroll, back)
- Add 20-40s pause every 4 job cards processed (simulate "reading" time)
- Never process more than 15-20 job details in one continuous session
- Space 50 daily applications across 3-4 separate sessions (morning/noon/afternoon/evening)

### Human-like Browsing
- Before applying, scroll through JD naturally (2-3 smooth scrolls, not instant)
- Do not click "apply" immediately on page load; wait 3-6s as if reading
- Avoid opening multiple job detail tabs simultaneously
- Simulate hesitation: hover on button before clicking

### Anti-Captcha Operational Rules
- Max 4-5 apply actions before taking a 30s+ break
- Max 120 job detail page views per session before captcha is triggered
- If captcha appears for the first time in a session, stop completely — do not "continue from where left off"
- After captcha, user must manually clear it in the browser before next run
- Use "batch pause" scheduling: process Page 1 of keyword A, pause 2-3 min, then Page 1 of keyword B, etc.

## Error Handling
- If captcha appears, stop all activity and notify user
- If page fails to load, retry once after 5 seconds
- If apply button not found, skip this job and log it
- If any step fails 3 times, move to next item

## Data Recording
- After each successful apply, record in data/history.json:
  ```json
  {
    "YYYY-MM-DD": {
      "applied": [{"id": "...", "keyword": "...", "city": "...", "time": "...", "company": "...", "title": "..."}],
      "chats": []
    }
  }
  ```
- Read this file before applying to avoid duplicates
