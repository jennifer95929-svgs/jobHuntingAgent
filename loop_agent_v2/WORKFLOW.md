# Workflow

## Phase 1: Search & Apply Jobs

### Step 1 - Navigate to Jobs Page
- Go to the BOSS Zhipin jobs search page
- URL pattern: `https://www.zhipin.com/web/geek/jobs`

### Step 2 - Search by Keyword and City
Keywords (try in order): AI产品经理, AI产品, 产品经理(AI方向), 人工智能产品经理, AI应用产品经理
Cities (try in order): 深圳, 北京, 上海, 广州, 杭州

Per keyword+city combination:
1. Enter keyword in search input field (placeholder contains "搜索")
2. Press Enter to search
3. Wait for job cards to load (selector: `.job-card-box`)

### Step 3 - Extract Job List
- Read all `.job-card-box` elements from the page
- For each card, extract:
  - Job ID from `a[href*="/job_detail/"]` href attribute (regex: `/job_detail/([^/]+?)\.html`)
  - Title from `.job-name`
  - Salary from `.job-salary`
  - Company from `.boss-name`

### Step 4 - Filter Out Already Applied
- Check history.json in data/ directory for today's applied jobs
- Skip jobs with matching IDs

### Step 5 - LLM Batch Filter
- For remaining jobs, use LLM to filter out:
  - Outsourcing companies (外包/外派)
  - Companies with less than 50 employees
  - Roles not matching AI Product Manager profile
- Keep at most 5 eligible jobs per page

### Step 6 - Company Validation
- Click into each job detail page to verify company
- Check employee count displayed on the page (must be >= 50 people)
- Verify it's not an outsourcing position
- If valid, proceed to apply

### Step 7 - Apply
- Look for and click the apply button (投递)
- Wait for confirmation
- Record in history.json under today's date

### Step 8 - Pagination
- Click next page button (selector: `.page-next` or similar)
- Repeat Steps 3-8 until no more pages or daily limit reached

### Step 9 - Next City/Keyword
- Move to next city in the list
- When all cities done, move to next keyword
- When all keywords done, cycle is complete

## Phase 2: Check & Reply HR Messages

### Step 1 - Navigate to Chat
- Go to `https://www.zhipin.com/web/geek/chat`

### Step 2 - Check Unread
- Look for badge/unread indicators (selectors: `[class*="badge"]`, `[class*="msg-num"]`, `.unread`)
- Count unread conversations

### Step 3 - Process Each Unread
- Click on the unread conversation
- Read the HR's message from the chat area
- Read the candidate profile from PROFILE.md
- Generate a context-appropriate reply based on:
  - HR's message content
  - Job position mentioned
  - Candidate's experience and preferences
- Type reply into textarea
- Press Enter to send

### Step 4 - Repeat
- Process all unread conversations
- Return to Phase 1 if daily apply limit not reached

## Phase 3: Continuous Loop
- After completing all phases, wait before next cycle
- Prioritize unread messages over new applications
- Run until max daily applications (50) is reached
