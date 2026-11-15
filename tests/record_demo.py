"""Record a ~30-second captioned screen recording of the live app (real data, real interactions).

Start the app (cd web && npm run dev), then:
    python tests/record_demo.py [--url http://localhost:5173] [--out docs/demo]
Writes a .webm video (1280x720) into --out.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright

CAPTION_JS = """(t) => {
  let el = document.getElementById('__cap');
  if (!el) {
    el = document.createElement('div'); el.id = '__cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:99999;' +
      'background:rgba(11,12,16,.92);color:#fff;border:1px solid #ff8a3d;border-radius:12px;padding:12px 20px;' +
      'font:600 22px Inter,system-ui,sans-serif;max-width:88vw;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.5)';
    document.body.appendChild(el);
  }
  el.textContent = t;
}"""


def run(url: str, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "_raw"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(tmp),
                                  record_video_size={"width": 1280, "height": 720})
        page = ctx.new_page()
        page.goto(f"{url}/#aoi=punjab_haryana")
        page.wait_for_selector("#loading.hide", state="attached", timeout=60000)
        page.add_style_tag(content="html{scroll-behavior:smooth}")
        page.wait_for_timeout(2500)
        cap = lambda t: page.evaluate(CAPTION_JS, t)
        scroll_to = lambda sel: page.evaluate(f"document.querySelector('{sel}').scrollIntoView({{behavior:'smooth',block:'start'}})")

        cap("26 years of NASA FIRMS fire hotspots · MODIS × VIIRS → one consistent record")
        page.wait_for_timeout(3500)
        cap("Situation brief: this month vs the same days in every past year")
        page.wait_for_timeout(3500)
        scroll_to("#calendar"); page.wait_for_timeout(1200)
        page.click("#mode-naive")
        cap("Naive splice of FIRMS points: the 2012 jump is a new sensor, not more fire")
        page.wait_for_timeout(3800)
        page.click("#mode-harm")
        cap("Thermal Twins: physics-based harmonization removes 5 sensor artifacts")
        page.wait_for_timeout(3500)
        page.check("input[name=cmode][value=anom]")
        cap("Every month vs its 2003–2022 median — Punjab's Oct–Nov burning season")
        page.wait_for_timeout(3500)
        page.check("input[name=cmode][value=count]")
        page.evaluate("window.scrollTo({top:0,behavior:'smooth'})"); page.wait_for_timeout(1200)
        cap("Discovery: drifting Aqua sees 5.7× more fire than 13:30 VIIRS — burning is moving later in the day")
        page.wait_for_timeout(4200)
        box = page.locator("#map").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.45, box["y"] + box["height"] * 0.45, steps=12)
        cap("Click any area to analyse it · download calendar & raw hotspot CSVs")
        page.wait_for_timeout(1500)
        page.mouse.click(box["x"] + box["width"] * 0.45, box["y"] + box["height"] * 0.45)
        page.wait_for_timeout(2500)
        video = page.video
        ctx.close()
        browser.close()
        src = Path(video.path())
    dst = out / "thermal_twins_demo.webm"
    shutil.move(str(src), dst)
    shutil.rmtree(tmp, ignore_errors=True)
    print("wrote", dst, f"{dst.stat().st_size / 1e6:.1f} MB")
    return dst


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5173")
    ap.add_argument("--out", default="docs/demo")
    a = ap.parse_args()
    run(a.url, Path(a.out))
