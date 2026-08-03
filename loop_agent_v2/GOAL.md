# Job Agent V2 - Auto Job Hunter on BOSS Zhipin

## Mission
Autonomously search, filter, and apply to AI Product Manager positions on BOSS Zhipin (zhipin.com). Monitor and reply to HR chat messages. Run persistently until daily limits are reached.

## How to Operate
- Read WORKFLOW.md for step-by-step job hunting process
- Read RULES.md for constraints and business logic
- Read DOMAIN.md for page structure and selectors
- Read PROFILE.md for candidate resume

## Browser Setup
- Chrome is already running with remote debugging on port 9222
- User is logged into BOSS Zhipin
- Use `agent-browser` MCP tools to control the browser

## Available Tools
- `agent-browser` MCP tools: `browser_navigate`, `browser_click`, `browser_snapshot`, `browser_fill_form`, etc.
- `browser_snapshot` to read page content
- `browser_click` with CSS selectors to interact with elements

## Daily Goal
Apply to up to 50 jobs per day across keywords and cities. Monitor and reply to unread HR messages.
