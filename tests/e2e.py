"""End-to-end checks of the web app in a real browser (Microsoft Edge via Playwright).

Start the app first (cd web && npm run dev), then:
    python tests/e2e.py [--url http://localhost:5173]
Every check prints PASS/FAIL; the exit code is the number of failures.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys

from playwright.sync_api import sync_playwright

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  · ' + detail) if detail else ''}", flush=True)


def wait_ready(page) -> None:
    page.wait_for_selector("#loading.hide", state="attached", timeout=60000)
    page.wait_for_timeout(1500)


def run(url: str) -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # 1. India loads with real data
        page.goto(f"{url}/#aoi=punjab_haryana")
        wait_ready(page)
        brief = page.inner_text("#brief")
        check("India loads and brief renders", "fire units" in brief and "Punjab" in brief, brief.splitlines()[1][:80])
        check("KPI detections from data", page.inner_text("#kpi-dets").strip().endswith("M"), page.inner_text("#kpi-dets"))
        check("Status badge present", page.locator("#brief .status").count() == 1, page.inner_text("#brief .status"))
        check("Calendar legend rendered", page.locator("#cal-legend .sw").count() == 7)
        check("Coverage statement shown", "held-out" in page.inner_text("#cov-line"), page.inner_text("#cov-line")[:90])

        # 2. Map hover tooltip and click-to-analyse
        box = page.locator("#map").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.45, box["y"] + box["height"] * 0.45)
        page.wait_for_timeout(600)
        tip_ok = page.locator("#map-tip").is_visible() and "units" in page.inner_text("#map-tip")
        check("Map hover tooltip", tip_ok, page.inner_text("#map-tip").replace("\n", " ")[:80] if tip_ok else "")
        page.mouse.click(box["x"] + box["width"] * 0.45, box["y"] + box["height"] * 0.45)
        page.wait_for_timeout(1200)
        info = page.inner_text("#aoi-info")
        check("Click hexagon selects area", info.startswith("Area around"), info)

        # 3. Draw a box
        page.select_option("#preset", "all")
        page.wait_for_timeout(1200)
        page.click("#draw-rect")
        box = page.locator("#map").bounding_box()
        x0, y0 = box["x"] + box["width"] * 0.30, box["y"] + box["height"] * 0.30
        page.mouse.move(x0, y0); page.mouse.down()
        page.mouse.move(x0 + 120, y0 + 90, steps=8); page.mouse.up()
        page.wait_for_timeout(1200)
        check("Draw box creates custom area", page.inner_text("#aoi-info").startswith("Custom area"), page.inner_text("#aoi-info"))

        # 4. Naive toggle + colour modes
        page.select_option("#preset", "punjab_haryana")
        page.wait_for_timeout(1000)
        page.click("#mode-naive"); page.wait_for_timeout(600)
        check("Naive banner appears", page.locator("#naive-banner").is_visible())
        page.click("#mode-harm"); page.wait_for_timeout(600)
        check("Naive banner hides", not page.locator("#naive-banner").is_visible())
        page.check("input[name=cmode][value=anom]"); page.wait_for_timeout(500)
        check("Anomaly legend", "normal" in page.inner_text("#cal-legend"))
        page.check("input[name=cmode][value=pct]"); page.wait_for_timeout(500)
        check("Percentile legend", "90th" in page.inner_text("#cal-legend"))
        page.check("input[name=cmode][value=count]")

        # 5. Downloads with real content
        with page.expect_download(timeout=60000) as dl:
            page.click("#dl-cal")
        rows = list(csv.reader(io.StringIO(open(dl.value.path(), encoding="utf-8").read())))
        hdr = rows[0]
        check("Calendar CSV download", len(rows) > 300 and "harmonized_modis_eq_units" in hdr and "ci90_low" in hdr, f"{len(rows) - 1} months")
        page.fill("#p-from", "2026-11"); page.dispatch_event("#p-from", "change")
        page.fill("#p-to", "2026-11"); page.dispatch_event("#p-to", "change")
        with page.expect_download(timeout=180000) as dl:
            page.click("#dl-hot")
        hot = list(csv.reader(io.StringIO(open(dl.value.path(), encoding="utf-8").read())))
        sats = sorted({r[4] for r in hot[1:]})
        dates = sorted({r[2] for r in hot[1:]})
        check("Hotspot CSV download", len(hot) > 1000 and dates[0] >= "2026-11-01", f"{len(hot) - 1} rows, {dates[0]}..{dates[-1]}, {sats}")

        # 6. Share button
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page.click("#share"); page.wait_for_timeout(400)
        check("Share copies link", "copied" in page.inner_text("#share").lower(), page.inner_text("#share"))

        # 7. Argentina region
        page.goto(f"{url}/#region=argentina")
        page.reload()
        wait_ready(page)
        check("Argentina loads", "Argentina" in page.inner_text("#hdr-region") and "fire units" in page.inner_text("#brief"),
              page.inner_text("#brief").splitlines()[1][:80])
        check("Argentina presets", page.locator("#preset option").count() >= 6)

        # 8. Phone width: no horizontal overflow
        mob = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
        mp = mob.new_page()
        mp.goto(f"{url}/#aoi=punjab_haryana")
        wait_ready(mp)
        sw = mp.evaluate("document.documentElement.scrollWidth")
        check("Phone layout has no horizontal overflow", sw <= 375, f"scrollWidth={sw}")

        real_errors = [e for e in errors if "favicon" not in e and "ERR_CONNECTION_REFUSED" not in e]
        check("No browser console errors", not real_errors, "; ".join(real_errors)[:200])
        browser.close()
    fails = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{len(results) - fails}/{len(results)} checks passed")
    return fails


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5173")
    sys.exit(run(ap.parse_args().url))
