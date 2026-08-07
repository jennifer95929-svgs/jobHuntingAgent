"""BOSS 薪资字体解码 —— PUA 数字还原。

原理:BOSS 用私有字体把薪资数字渲染成 PUA 字符(e030-e03f 段)。经过多轮验证,
码位->数字 的映射在页面间是稳定的:
  e031=0  e032=1  e033=2  e038=3  e034=4
  e035=5  e036=6  e037=7  e039=8  e03a=9

策略:
  1. 先用固定映射直接解码(快, 99% 场景生效)
  2. 对解码结果做合理性校验(薪资低<高, 月薪12-17)
  3. 若校验失败, 才抓取动态字体用 fontTools 分析 glyph 特征重识别映射
"""
import json
import base64
import asyncio
import urllib.request
import tempfile
import os
import re

# 已验证的稳定映射: PUA 码点 -> 数字
FIXED_MAPPING = {
    0xe031: 0, 0xe032: 1, 0xe033: 2, 0xe038: 3, 0xe034: 4,
    0xe035: 5, 0xe036: 6, 0xe037: 7, 0xe039: 8, 0xe03a: 9,
}


def build_decoder_js() -> str:
    """返回在页面内执行的 JS, 提取所有薪资文本的 PUA 码点序列。"""
    return r"""
(() => {
  const els = [...document.querySelectorAll('.job-card-box .job-salary')];
  return JSON.stringify(els.map(el => {
    const cps = [];
    for (const c of el.textContent.trim()) {
      const cp = c.codePointAt(0);
      cps.push((cp >= 0xe000 && cp <= 0xf8ff) ? cp : c);
    }
    return cps;
  }));
})()
"""


def _get_boss_tab():
    """找到 BOSS 页面 tab。"""
    try:
        tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=5).read())
        for t in tabs:
            if t.get("type") == "page" and "zhipin.com" in (t.get("url") or ""):
                return t
    except Exception:
        pass
    return None


async def _read_salaries(ws_url: str) -> list:
    """通过 CDP 读取页面薪资 PUA 文本。"""
    import websockets
    from browser.agent_browser_cli import CDPClient

    async def go():
        async with websockets.connect(ws_url, close_timeout=10) as w:
            c = CDPClient("")
            c._ws = w
            raw = await c.evaluate(build_decoder_js())
            try:
                return json.loads(raw)
            except Exception:
                return []

    return await go()


async def _capture_font(ws_url: str) -> bytes:
    """通过 CDP Network 监听抓取动态加密字体(含 PUA glyph)。"""
    import websockets
    async with websockets.connect(ws_url, close_timeout=10) as w:
        await w.send(json.dumps({"id": 1, "method": "Network.enable"}))
        await w.send(json.dumps({"id": 2, "method": "Page.enable"}))
        await w.send(json.dumps({"id": 3, "method": "Page.reload", "params": {"ignoreCache": True}}))
        found = {}
        try:
            while len(found) < 4:
                msg = json.loads(await asyncio.wait_for(w.recv(), timeout=25))
                if msg.get("method") == "Network.responseReceived":
                    url = msg["params"]["response"]["url"]
                    if "bosszhipin.com/static/file" in url and any(
                        x in url for x in [".woff2", ".ttf"]
                    ):
                        found[msg["params"]["requestId"]] = url
        except (asyncio.TimeoutError, Exception):
            pass
        for rid, url in found.items():
            await w.send(json.dumps({
                "id": 200 + len(found),
                "method": "Network.getResponseBody",
                "params": {"requestId": rid},
            }))
        collected = {}
        try:
            while len(collected) < len(found):
                msg = json.loads(await asyncio.wait_for(w.recv(), timeout=8))
                if msg.get("id", 0) >= 200:
                    collected[msg["id"]] = msg.get("result", {}).get("body", "")
        except (asyncio.TimeoutError, Exception):
            pass
        for body in collected.values():
            try:
                data = base64.b64decode(body)
            except Exception:
                data = body.encode()
            if data:
                return data
        return b""


def _analyze_font(font_path: str) -> dict:
    """用 fontTools 分析字体 glyph 特征, 返回 {pua_codepoint: digit}。

    特征: 孔洞数(0/1/2) + 宽高比 + 水平/垂直投影分布, 与标准数字模板投票。
    """
    try:
        from fontTools.ttLib import TTFont
        from fontTools.pens.recordingPen import RecordingPen
        import numpy as np
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from scipy import ndimage
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {}

    font = TTFont(font_path)
    gs = font.getGlyphSet()
    upm = font["head"].unitsPerEm
    cmap = font.getBestCmap()

    pua_glyphs = {}
    for cp, gname in cmap.items():
        if 0xe000 <= cp <= 0xf8ff:
            pua_glyphs[gname] = cp
    if len(pua_glyphs) < 10:
        return {}

    def glyph_to_path(gname, size=200):
        recorder = RecordingPen()
        gs[gname].draw(recorder)
        scale = size / upm * 0.8
        vertices, codes = [], []
        for op, args in recorder.value:
            if op == "moveTo":
                vertices.append((args[0][0]*scale, size - args[0][1]*scale))
                codes.append(Path.MOVETO)
            elif op == "lineTo":
                vertices.append((args[0][0]*scale, size - args[0][1]*scale))
                codes.append(Path.LINETO)
            elif op == "qCurveTo":
                p0 = vertices[-1]
                p1 = (args[0][0]*scale, size - args[0][1]*scale)
                p2 = (args[-1][0]*scale, size - args[-1][1]*scale)
                vertices.extend([
                    (p0[0]+2/3*(p1[0]-p0[0]), p0[1]+2/3*(p1[1]-p0[1])),
                    (p2[0]+2/3*(p1[0]-p2[0]), p2[1]+2/3*(p1[1]-p2[1])),
                    p2,
                ])
                codes.extend([Path.CURVE4]*3)
            elif op == "curveTo":
                vertices.extend([(a[0]*scale, size - a[1]*scale) for a in args])
                codes.extend([Path.CURVE4]*3)
            elif op == "closePath":
                codes.append(Path.CLOSEPOLY)
                vertices.append(vertices[0] if vertices else (0, 0))
        return Path(vertices, codes)

    def render_glyph(gname, size=200):
        path = glyph_to_path(gname, size)
        fig = plt.figure(figsize=(1, 1), dpi=size)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, size)
        ax.set_ylim(0, size)
        ax.axis("off")
        ax.add_patch(PathPatch(path, facecolor="black", edgecolor="none", fill=True))
        fig.canvas.draw()
        buf = getattr(fig.canvas, "buffer_rgba", None)
        if buf is None:
            arr = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8).reshape(size, size, 3)
            arr = arr[:, :, 0]
        else:
            arr = np.frombuffer(buf(), dtype=np.uint8).reshape(size, size, 4)[:, :, 0]
        plt.close(fig)
        return arr < 128

    def features(mask):
        ys, xs = np.where(mask)
        if len(xs) == 0:
            return None
        crop = mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
        h, w = crop.shape
        ratio = w / max(1, h)
        inv = ~crop
        labeled, n = ndimage.label(inv)
        border = set(np.unique(labeled[0, :])) | set(np.unique(labeled[-1, :])) | \
                 set(np.unique(labeled[:, 0])) | set(np.unique(labeled[:, -1]))
        holes = sum(1 for l in range(1, n+1) if l not in border)
        hproj = crop.sum(axis=1) / max(1, crop.sum())
        vproj = crop.sum(axis=0) / max(1, crop.sum())

        def ds(p, n=16):
            out = []
            for i in range(n):
                s = i * len(p) // n
                e = (i + 1) * len(p) // n
                out.append(p[s:e].sum() if e > s else 0)
            return np.array(out)

        return ratio, holes, ds(hproj), ds(vproj)

    _sys_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 110)

    def ascii_mask(ch, size=200):
        img = Image.new("L", (size, size), 255)
        d = ImageDraw.Draw(img)
        d.text((20, 12), ch, font=_sys_font, fill=0)
        return np.array(img) < 128

    def proj_dist(a, b):
        return float(np.mean(np.abs(a - b)))

    sys_feats = {}
    for n in range(10):
        f = features(ascii_mask(str(n)))
        if f:
            sys_feats[n] = f

    glyph_scores = {}
    for gname, cp in pua_glyphs.items():
        mask = render_glyph(gname)
        f = features(mask)
        if not f:
            continue
        ratio, holes, hproj, vproj = f
        scores = {}
        for n in range(10):
            sr, sh, shp, svp = sys_feats[n]
            hole_ok = 1.0 if holes == sh else (0.5 if abs(holes - sh) <= 1 else 0.0)
            ratio_ok = max(0, 1 - abs(ratio - sr) * 3)
            proj_ok = 1 - min(proj_dist(hproj, shp), proj_dist(vproj, svp)) * 10
            scores[n] = 0.5 * hole_ok + 0.2 * ratio_ok + 0.3 * proj_ok
        glyph_scores[gname] = (cp, scores)

    mapping = {}
    used = set()
    for gname in sorted(
        glyph_scores,
        key=lambda g: -max(s for d, s in glyph_scores[g][1].items() if d not in used),
    ):
        cp, scores = glyph_scores[gname]
        best_n, best_s = None, -1
        for n, s in sorted(scores.items(), key=lambda x: -x[1]):
            if n not in used and s > best_s:
                best_n, best_s = n, s
        if best_n is None:
            for n in range(10):
                if n not in used:
                    best_n = n
                    break
        if best_n is not None:
            mapping[cp] = best_n
            used.add(best_n)
    return mapping


def _plausibility(decoded_list) -> float:
    """合理性: 薪资低<高 + 月薪 12-17 的通过率。"""
    ok = total = 0
    for s in decoded_list:
        m = re.match(r"^(\d{1,2})-(\d{1,2})K", s)
        if m:
            total += 1
            if int(m.group(1)) < int(m.group(2)):
                ok += 1
        m2 = re.search(r"·(\d{1,2})薪", s)
        if m2:
            total += 1
            if 12 <= int(m2.group(1)) <= 17:
                ok += 1
    return ok / max(1, total)


def _decode_rows(rows, mapping) -> list:
    decoded = []
    for row in rows:
        out = []
        for item in row:
            if isinstance(item, int) and item in mapping:
                out.append(str(mapping[item]))
            else:
                out.append(str(item))
        decoded.append("".join(out))
    return decoded


def decode_salaries_from_page() -> list:
    """解码页面薪资: 固定映射 -> 校验 -> 字体解析修正。"""
    tab = _get_boss_tab()
    if not tab:
        return []
    ws_url = tab["webSocketDebuggerUrl"]

    loop = asyncio.new_event_loop()
    try:
        rows = loop.run_until_complete(_read_salaries(ws_url))
    finally:
        loop.close()
    if not rows:
        return []

    # 1. 固定映射
    decoded = _decode_rows(rows, FIXED_MAPPING)
    if _plausibility(decoded) >= 0.8:
        return decoded

    # 2. 固定映射不通过 -> 抓字体重新分析
    loop = asyncio.new_event_loop()
    try:
        font_bytes = loop.run_until_complete(_capture_font(ws_url))
    finally:
        loop.close()
    if font_bytes:
        tmp = tempfile.NamedTemporaryFile(suffix=".woff2", delete=False)
        tmp.write(font_bytes)
        tmp.close()
        try:
            mapping = _analyze_font(tmp.name)
        finally:
            os.unlink(tmp.name)
        if len(mapping) >= 10:
            decoded = _decode_rows(rows, mapping)
            if _plausibility(decoded) >= 0.7:
                return decoded

    return decoded
