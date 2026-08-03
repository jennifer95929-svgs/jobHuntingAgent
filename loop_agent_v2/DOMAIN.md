# BOSS Zhipin Domain Knowledge

## Page URLs
- Login/Home: `https://www.zhipin.com/`
- Jobs Search: `https://www.zhipin.com/web/geek/jobs?query={keyword}&city={city_code}`
- Chat: `https://www.zhipin.com/web/geek/chat`
- Job Detail: `https://www.zhipin.com/job_detail/{job_id}.html`

## City Codes
- 北京: 101010100, 上海: 101020100, 广州: 101280100
- 深圳: 101280600, 杭州: 101210100, 成都: 101270100, 南京: 101190100

## Key DOM Selectors

### Job List Page
- Job cards container: `.job-card-box`
- Job title: `.job-name`
- Salary: `.job-salary`
- Company name: `.boss-name`
- Job link: `a[href*="/job_detail/"]`
- Search input: `input[placeholder*="搜索"]`
- Next page button: `.page-next`, `.next`, or `a:has(.icon-arrow-right)`

### Job Detail Page
- Company size: look for text patterns like "人数", "规模", "员工"
- Apply button: button/span/a containing text "投递" or "立即沟通"
- Already applied indicator: text like "已投递", "已沟通"

### Chat Page
- Conversation list items: `li` elements in the chat sidebar
- Unread indicator: `[class*="badge"]`, `[class*="msg-num"]`, `.unread`, `li[class*="unread"]`
- Message area: `.chat-content`, `[class*="message"]`, or similar
- Text input: `textarea`
- Send button: button containing "发送" or "发送消息"
- Chat header: `[class*="chat-header"]`, `[class*="dialog-header"]`

## Important Behaviors
- BOSS Zhipin uses dynamic rendering (React/SPA)
- Page content loads asynchronously; wait for `.job-card-box` to appear before reading
- Some pages have a security check (验证) that redirects to captcha
- After applying, the job card may change appearance (e.g., "已投递" label)
- Chat page uses WebSocket for real-time messages

## Common Issues
- If search returns 0 results, try the next keyword/city
- If page shows "暂无相关职位", the keyword+city combination has no results
- Login session expires after ~24 hours; if redirected to login page, notify user
