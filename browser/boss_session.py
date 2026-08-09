import time
import random
import json
import os
import re
import asyncio
import websockets
import urllib.request
from config import SESSION_NAME, MIN_DELAY, MAX_DELAY
from browser.agent_browser_cli import AgentBrowser, CDPClient


def city_code(city: str) -> str:
    codes = {
        "北京": "101010100", "上海": "101020100",
        "广州": "101280100", "深圳": "101280600",
        "杭州": "101210100", "成都": "101270100",
        "南京": "101190100", "武汉": "101200100",
    }
    return codes.get(city, "101280600")


def search_url(keyword: str, city: str) -> str:
    cc = city_code(city)
    return f"https://www.zhipin.com/web/geek/jobs?query={keyword}&city={cc}"


def job_detail_url(job_id: str) -> str:
    return f"https://www.zhipin.com/job_detail/{job_id}.html"


class BossSession:
    def __init__(self):
        self.browser = AgentBrowser(session=SESSION_NAME)
        self._search_tab_ws = None

    def ensure_browser(self, headed: bool = True):
        ok = self.browser.check_alive()
        if not ok:
            print("Chrome 未连接，请确保 Chrome 已启动并开放调试端口 9222")
        return self.browser

    def search_jobs(self, keyword: str, city: str):
        url = search_url(keyword, city)
        self._search_tab_ws = None

        target_id = self.browser.create_tab(url)
        if not target_id:
            return False

        tab = None
        for _ in range(10):
            time.sleep(1)
            tab = self.browser.get_tab_by_id(target_id)
            if tab:
                ws = tab["webSocketDebuggerUrl"]
                raw = self.browser.evaluate_in_tab(ws, "document.body ? document.body.innerText.length : 0")
                body_len = int(str(raw)) if raw is not None else 0
                if body_len > 100:
                    self._search_tab_ws = ws
                    break
                tab = None

        if not self._search_tab_ws:
            self.browser.close_tab(target_id)
            return False

        js_search = f"""
        (() => {{
            const inp = document.querySelector('input[placeholder*="搜索"]');
            if (!inp) return 'no_input';
            inp.value = {json.dumps(keyword)};
            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
            inp.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter', keyCode:13, which:13, bubbles:true}}));
            inp.dispatchEvent(new KeyboardEvent('keypress', {{key:'Enter', keyCode:13, which:13, bubbles:true}}));
            inp.dispatchEvent(new KeyboardEvent('keyup', {{key:'Enter', keyCode:13, which:13, bubbles:true}}));
            return 'searched';
        }})()
        """
        self.browser.evaluate_in_tab(self._search_tab_ws, js_search)

        for _ in range(15):
            self.random_delay(1, 1.5)
            raw = self.browser.evaluate_in_tab(self._search_tab_ws,
                "document.body ? document.querySelectorAll('.job-card-box').length : 0")
            count = int(str(raw)) if raw is not None else 0
            if count > 0:
                break

        return True

    def get_page_text(self) -> str:
        if self._search_tab_ws:
            result = self.browser.evaluate_in_tab(self._search_tab_ws,
                "document.body ? document.body.innerText : ''")
            return str(result) if result else ""
        return self.browser.get_text() or ""

    def extract_job_list(self) -> list:
        if not self._search_tab_ws:
            return []

        js = """
        (() => {
            const cards = document.querySelectorAll('.job-card-box');
            return Array.from(cards).map(card => {
                const link = card.querySelector('a[href*=\"/job_detail/\"]');
                const titleEl = card.querySelector('.job-name');
                const salaryEl = card.querySelector('.job-salary');
                const companyEl = card.querySelector('.boss-name');
                const href = link ? link.getAttribute('href') : '';
                const match = href.match(/\\/job_detail\\/([^\\/]+?)\\.html/);
                return {
                    id: match ? match[1] : '',
                    title: titleEl ? titleEl.textContent.trim() : '',
                    salary: salaryEl ? salaryEl.textContent.trim() : '',
                    company: companyEl ? companyEl.textContent.trim() : '',
                };
            }).filter(j => j.id);
        })()
        """
        result = self.browser.evaluate_in_tab(self._search_tab_ws, js)
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return []
        return result if isinstance(result, list) else []

    def check_company_eligible(self, job_id: str) -> tuple:
        """打开岗位详情页，检查公司规模是否 >= 50人 且非外包。
        返回 (eligible: bool, reason: str)"""
        url = f"https://www.zhipin.com/job_detail/{job_id}.html"
        target_id = self.browser.create_tab(url)
        if not target_id:
            return False, "无法创建页面"

        tab_ws = None
        dead = False
        for _ in range(10):
            time.sleep(1)
            tab = self.browser.get_tab_by_id(target_id)
            if tab:
                ws_url = tab["webSocketDebuggerUrl"]
                async def check():
                    async with websockets.connect(ws_url, close_timeout=8) as ws:
                        c = CDPClient(""); c._ws = ws
                        # 必须同时满足:仍在 job_detail 页 + 正文非空 + 无 404/下架文案。
                        # BOSS 404 页 4 秒后会跳转首页,拿首页当详情页就是误判漏网。
                        raw = await c.evaluate("""(() => {
                            const t = document.body ? document.body.innerText : '';
                            return JSON.stringify({
                                bl: t.length,
                                onDetail: location.pathname.includes('/job_detail/'),
                                dead: /页面不存在|Oops|职位已下线|该职位已停止招聘|职位不存在|已下架|404/.test(t)
                            });
                        })()""") or ""
                        try:
                            import json as _j
                            d = _j.loads(raw)
                        except Exception:
                            d = {"bl": 0, "onDetail": False, "dead404": False}
                        return d
                loop = asyncio.new_event_loop()
                try:
                    d = loop.run_until_complete(check())
                except:
                    d = {"bl": 0, "onDetail": False, "dead404": False}
                finally:
                    loop.close()
                if d.get("dead404"):
                    dead = True
                    break
                if d.get("bl", 0) > 100 and d.get("onDetail"):
                    tab_ws = ws_url
                    break

        if dead:
            self.browser.close_tab(target_id)
            return False, "岗位已下架/过期"

        if not tab_ws:
            self.browser.close_tab(target_id)
            return False, "页面加载失败"

        async def get_info():
            async with websockets.connect(tab_ws, close_timeout=8) as ws:
                c = CDPClient(""); c._ws = ws
                info = await c.evaluate("""
                    (() => {
                        const text = document.body.innerText;
                        // 岗位已下架/过期:404 页无投递按钮,直接判不合格,别再让模型误投
                        if (text.includes('页面不存在') || text.includes('Oops') || text.includes('职位已下线') || text.includes('该职位已停止招聘') || text.includes('404')) {
                            return JSON.stringify({scale: '', company: '', isOutsource: false, dead: true});
                        }
                        // 找公司名
                        let company = '';
                        const nameSelectors = ['.company-info .company-name', '.job-sec-company', '.company-name', '[class*="company-name"]', '[class*="company"] a'];
                        for (const sel of nameSelectors) {
                            const el = document.querySelector(sel);
                            if (el && el.textContent.trim()) {
                                company = el.textContent.trim();
                                break;
                            }
                        }
                        // 关键修复: 只在"公司基本信息"区域内找规模, 避免匹配到筛选器/推荐职位的规模
                        let scale = '';
                        const infoBlocks = [...document.querySelectorAll('[class*="company"]')];
                        for (const blk of infoBlocks) {
                            const bt = blk.innerText || '';
                            // 规模通常与"融资"、"领域"、公司名同区块
                            const m = bt.match(/(\\d+[-~]\\d+人|少于\\d+人|\\d+人以上|\\d+[-~]\\d+人以上)/);
                            if (m) {
                                scale = m[1];
                                break;
                            }
                        }
                        // 兜底: 若公司基本信息块没找到, 用全文首个规模(仅当公司名出现于附近)
                        if (!scale) {
                            const m = text.match(/(\\d+[-~]\\d+人|少于\\d+人|\\d+人以上|\\d+[-~]\\d+人以上)/);
                            scale = m ? m[1] : '';
                        }
                        const isOutsource = /外包|派遣/.test(company);
                        return JSON.stringify({scale, company, isOutsource, dead: false});
                    })()
                """)
                return info

        loop = asyncio.new_event_loop()
        try:
            raw = loop.run_until_complete(get_info())
        except:
            raw = '{}'
        finally:
            loop.close()

        self.browser.close_tab(target_id)
        self.random_delay(1, 2)

        try:
            info = json.loads(raw)
        except:
            return False, "解析失败"

        scale = info.get("scale", "")
        company = info.get("company", "")
        is_out = info.get("isOutsource", False)
        if info.get("dead"):
            return False, f"岗位已下架/过期: {company}"

        # 判断规模
        if is_out:
            return False, f"外包/人力派遣公司: {company}"
        if scale:
            # 解析规模数字
            nums = re.findall(r'\d+', scale)
            if nums:
                min_scale = int(nums[0])
                if min_scale < 100:
                    return False, f"公司规模小于100人 ({scale}): {company}"
        return True, f"合格: {company} ({scale})"

    def click_apply(self, job_id: str = None, job_title: str = "", company: str = "", reply_fn=None) -> bool:
        """点击投递，若 reply_fn 提供则检测 HR 回复并自动应答。
        reply_fn(msg_text) → 返回要回复的文本或 None 表示不回复。
        """
        if not job_id:
            return False

        url = f"https://www.zhipin.com/job_detail/{job_id}.html"
        target_id = self.browser.create_tab(url)
        if not target_id:
            return False

        import asyncio, websockets
        from browser.agent_browser_cli import CDPClient

        tab_ws = None
        dead = False
        for _ in range(15):
            time.sleep(1)
            tab = self.browser.get_tab_by_id(target_id)
            if tab:
                ws_url = tab["webSocketDebuggerUrl"]
                async def check_body():
                    async with websockets.connect(ws_url, close_timeout=10) as ws:
                        c = CDPClient(""); c._ws = ws
                        raw = await c.evaluate("""(() => {
                            const t = document.body ? document.body.innerText : '';
                            return JSON.stringify({
                                bl: t.length,
                                onDetail: location.pathname.includes('/job_detail/'),
                                dead: /页面不存在|Oops|职位已下线|该职位已停止招聘|职位不存在|已下架|404/.test(t)
                            });
                        })()""") or ""
                        try:
                            import json as _j
                            return _j.loads(raw)
                        except Exception:
                            return {"bl": 0, "onDetail": False, "dead": False}
                loop = asyncio.new_event_loop()
                try:
                    d = loop.run_until_complete(check_body())
                except:
                    d = {"bl": 0, "onDetail": False, "dead": False}
                finally:
                    loop.close()
                if d.get("dead"):
                    dead = True
                    break
                if d.get("bl", 0) > 100 and d.get("onDetail"):
                    tab_ws = ws_url
                    break

        if dead:
            self.browser.close_tab(target_id)
            return False

        if not tab_ws:
            self.browser.close_tab(target_id)
            return False

        async def do_apply():
            async with websockets.connect(tab_ws, close_timeout=10) as ws:
                c = CDPClient(""); c._ws = ws

                status = await c.evaluate("""
                    (() => {
                        const b = document.body.innerText;
                        if (b.includes('404') || b.includes('不存在')) return '404';
                        if (b.includes('安全验证')) return 'captcha';
                        return 'ok';
                    })()
                """) or ""
                if status != "ok":
                    return False

                result = await c.evaluate("""
                (() => {
                    const texts = ['立即沟通', '投递', '立即投递'];
                    for (const el of document.querySelectorAll('a, button, span')) {
                        const t = el.textContent.trim();
                        if (texts.includes(t) && el.offsetParent !== null) {
                            el.scrollIntoView({block: 'center'});
                            el.click();
                            return 'clicked_' + t;
                        }
                    }
                    return 'not_found';
                })()
                """)
                applied = bool(result and str(result).startswith("clicked_"))

                if applied and reply_fn:
                    # 等待 HR 回复（最多 15s）
                    hr_msg = None
                    for wait_i in range(10):
                        await asyncio.sleep(1.5)
                        msgs = await c.evaluate("""
                        (() => {
                            const all = document.querySelectorAll('[class*="chat"] [class*="message"], [class*="msg"], .message-item, [class*="bubble"]');
                            if (!all.length) return '';
                            const last = all[all.length - 1];
                            return last.textContent.trim();
                        })()
                        """)
                        if msgs and len(msgs) > 5:
                            # 检查是否是 HR 发的（不是自己发的）
                            self_msgs = await c.evaluate("""
                            (() => {
                                const my = document.querySelectorAll('[class*="self"] [class*="message"], [class*="self"] [class*="bubble"], [class*="my"] [class*="message"]');
                                if (!my.length) return '';
                                return my[my.length - 1].textContent.trim();
                            })()
                            """)
                            # 如果最新消息不是自己发的，说明是 HR 回复
                            if not self_msgs or msgs != self_msgs:
                                hr_msg = msgs
                                break

                    if hr_msg:
                        reply_text = reply_fn(hr_msg)
                        if reply_text:
                            await asyncio.sleep(0.5)
                            await c.evaluate(f"""
                            (() => {{
                                const inp = document.querySelector('textarea, [contenteditable="true"], input[placeholder*="请输入"], input[placeholder*="说点什么"]');
                                if (!inp) return;
                                if (inp.tagName === 'TEXTAREA' || inp.tagName === 'INPUT') {{
                                    inp.value = {json.dumps(reply_text)};
                                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                }} else {{
                                    inp.textContent = {json.dumps(reply_text)};
                                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                }}
                                // 自动点击发送
                                setTimeout(() => {{
                                    for (const el of document.querySelectorAll('a, button, span')) {{
                                        if (el.textContent.trim() === '发送' && el.offsetParent !== null) {{ el.click(); break; }}
                                    }}
                                }}, 300);
                            }})()
                            """)
                            import sys
                            print(f"  [HR自动回复] {reply_text[:60]}...", file=sys.stderr)
                            await asyncio.sleep(2)

                if applied:
                    await asyncio.sleep(2)
                    await c.evaluate("""
                    (() => {
                        const closeTexts = ['关闭', 'x', '×', 'X', '取消'];
                        for (const el of document.querySelectorAll('a, button, span, i, svg')) {
                            const t = el.textContent.trim().toLowerCase();
                            const cls = (el.className || '').toLowerCase();
                            if (closeTexts.includes(t) || cls.includes('close') || cls.includes('dialog-close') || el.getAttribute('aria-label') === '关闭' || el.getAttribute('aria-label') === 'Close') {
                                if (el.offsetParent !== null) {
                                    el.click();
                                    return 'closed';
                                }
                            }
                        }
                        const selectors = ['.dialog-close', '.icon-close', '.close-btn', '.chat-dialog-close', '[class*="close"]', '[class*="dialog"] i', '.popup-close'];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent !== null) { el.click(); return 'closed_sel'; }
                        }
                        return 'no_close_btn';
                    })()
                    """)

                return applied

        loop = asyncio.new_event_loop()
        try:
            applied = loop.run_until_complete(do_apply())
        except:
            applied = False
        finally:
            loop.close()

        if applied:
            time.sleep(1)
        self.browser.close_tab(target_id)
        self.random_delay(1, 2)
        return applied

    def click_chat_by_company(self, company: str) -> bool:
        """点击侧边栏中指定公司的聊天"""
        ws = self._search_tab_ws
        if not ws:
            return False
        import asyncio, websockets
        from browser.agent_browser_cli import CDPClient
        async def do():
            async with websockets.connect(ws, close_timeout=10) as wss:
                c = CDPClient(""); c._ws = wss
                result = await c.evaluate(f"""
                (() => {{
                    const all = document.querySelectorAll('[class*="friend"], [class*="list"], div');
                    for (const el of all) {{
                        if (el.textContent.includes('{company}') && el.offsetParent !== null) {{
                            const r = el.getBoundingClientRect();
                            if (r.width > 100 && r.height > 20) {{
                                el.click();
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }})()
                """)
                return bool(result)
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(do())
        except:
            return False
        finally:
            loop.close()

    def send_message(self, text: str):
        if not self._search_tab_ws:
            return False
        ws = self._search_tab_ws
        import asyncio, websockets
        from browser.agent_browser_cli import CDPClient

        async def do_send():
            async with websockets.connect(ws, close_timeout=10) as wss:
                c = CDPClient(""); c._ws = wss
                await c.evaluate("document.querySelector('textarea')?.focus()")
                await asyncio.sleep(0.2)
                for ch in text:
                    await c.send("Input.insertText", {"text": ch})
                    await asyncio.sleep(0.005)
                await asyncio.sleep(0.5)
                await c.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter", "windowsVirtualKeyCode": 13, "code": "Enter"})
                await asyncio.sleep(0.05)
                await c.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "windowsVirtualKeyCode": 13, "code": "Enter"})
                await asyncio.sleep(1)
                remaining = await c.evaluate("document.querySelector('textarea')?.value.length || 0")
                return remaining == 0

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(do_send())
        except:
            return False
        finally:
            loop.close()

    def check_chat_notifications(self) -> int:
        text = self.get_page_text()
        if not text:
            return 0
        import re
        matches = re.findall(r'消息\s*(\d+)', text)
        if matches:
            return max(int(m) for m in matches)
        return 0

    def navigate_to_chats(self):
        url = "https://www.zhipin.com/web/geek/chat"
        target_id = self.browser.create_tab(url)
        if target_id:
            self._search_tab_ws = None
            import asyncio, websockets
            from browser.agent_browser_cli import CDPClient
            tab_ws = None
            for _ in range(15):
                time.sleep(1)
                tab = self.browser.get_tab_by_id(target_id)
                if tab:
                    ws_url = tab["webSocketDebuggerUrl"]
                    async def check():
                        async with websockets.connect(ws_url, close_timeout=5) as ws:
                            c = CDPClient(""); c._ws = ws
                            val = await c.evaluate("document.body ? document.body.innerText.length : 0")
                            return int(str(val)) if val else 0
                    loop = asyncio.new_event_loop()
                    try:
                        bl = loop.run_until_complete(check())
                    except:
                        bl = 0
                    finally:
                        loop.close()
                    if bl > 50:
                        tab_ws = ws_url
                        break
            if tab_ws:
                self._search_tab_ws = tab_ws

    def screenshot(self, path: str = None):
        ws = self._search_tab_ws
        if ws:
            self.browser.screenshot_in_tab(ws, path)
        else:
            self.browser.screenshot(path)

    def close(self):
        if not self._search_tab_ws:
            return
        tab_id = None
        for _ in range(5):
            try:
                tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
            except:
                break
            for t in tabs:
                if t.get('type') == 'page' and self._search_tab_ws in (t.get('webSocketDebuggerUrl') or ''):
                    tab_id = t.get('id')
                    break
            if tab_id:
                break
            time.sleep(1)
        if tab_id:
            try:
                browser_ws = json.loads(
                    urllib.request.urlopen("http://localhost:9222/json/version", timeout=3).read()
                )["webSocketDebuggerUrl"]
                async def do_close():
                    async with websockets.connect(browser_ws, close_timeout=5) as ws:
                        c = CDPClient(""); c._ws = ws
                        await c.send("Target.closeTarget", {"targetId": tab_id})
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(do_close())
                finally:
                    loop.close()
            except:
                pass
        self._search_tab_ws = None

    def random_delay(self, min_s: float = None, max_s: float = None):
        delay = random.uniform(min_s or MIN_DELAY, max_s or MAX_DELAY)
        time.sleep(delay)
