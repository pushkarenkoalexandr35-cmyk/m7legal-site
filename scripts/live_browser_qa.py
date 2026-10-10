#!/usr/bin/env python3
"""Read-only Chromium QA for the LIVE M7Legal site.

Never submits forms or changes production data. Runs on an external GitHub
Actions runner, with memory isolated from production VPS.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://m7legal.ru/"
ROUTES = [
    "", "uslugi/", "kontakty/", "tseny/", "praktika/", "komanda/",
    "o-kompanii/", "uslugi/mezhdunarodnye-sdelki/",
    "proverka-kompanii-kitaya/",
]
VIEWPORTS = [(320, 720), (390, 844), (768, 1024), (1440, 900)]


def run():
    folder = Path("live-browser-artifacts")
    folder.mkdir(exist_ok=True)
    result = {"mode": "production-live", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "checks": [], "failures": [], "screenshots": []}
    with sync_playwright() as tool:
        browser = tool.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        try:
            for width, height in VIEWPORTS:
                page = browser.new_page(viewport={"width": width, "height": height},
                                        device_scale_factor=1, reduced_motion="reduce")
                js_errors = []
                page.on("pageerror", lambda error: js_errors.append(str(error)[:350]))
                for route in ROUTES:
                    url = BASE + route
                    issues = []
                    js_errors.clear()
                    try:
                        response = page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(225)
                        code = response.status if response else None
                        if code != 200:
                            issues.append("HTTP " + str(code))
                        dims = page.evaluate("""() => ({
                            viewport: innerWidth,
                            scrollWidth: Math.max(document.documentElement.scrollWidth,
                                                  document.body.scrollWidth),
                            title: document.title,
                            hasH1: !!document.querySelector('h1'),
                            forms: document.querySelectorAll('form').length,
                            css: document.styleSheets.length,
                            robots: document.querySelector('meta[name="robots"]')?.content || '',
                            preview: !!document.querySelector('.m7-preview-banner')
                        })""")
                        if dims["scrollWidth"] > width + 1:
                            issues.append("Horizontal overflow")
                        if not dims["hasH1"]:
                            issues.append("H1 missing")
                        if dims["css"] == 0:
                            issues.append("No stylesheets")
                        if dims["preview"] or "noindex" in dims["robots"].lower():
                            issues.append("Production has staging or noindex content")
                        if dims["forms"] and page.locator('script[src*="m7-form.js"]').count() == 0:
                            issues.append("Missing production form sender")
                        if js_errors:
                            issues.extend("JS error: " + error for error in js_errors)
                        if route == "":
                            if "Правовые решения" not in page.locator("h1").first.inner_text():
                                issues.append("Wrong new homepage")
                            if page.locator(".utility").count():
                                issues.append("Removed top strip still present")
                            if page.locator('.nav-contact .nav-email[href="mailto:info@m7legal.ru"]').count() != 1:
                                issues.append("New contact stack missing")
                            if width == 390:
                                menu = page.locator(".menu-toggle")
                                if menu.count() != 1:
                                    issues.append("Mobile menu missing")
                                else:
                                    menu.click(timeout=3000)
                                    if menu.get_attribute("aria-expanded") != "true":
                                        issues.append("Mobile menu cannot open")
                                    menu.click(timeout=3000)
                                    if menu.get_attribute("aria-expanded") != "false":
                                        issues.append("Mobile menu cannot close")
                        if route == "uslugi/mezhdunarodnye-sdelki/":
                            if "Проверка контрагентов из Китая" not in page.locator("h1").first.inner_text():
                                issues.append("Original China landing not shown")
                            if page.locator('link[href*="assets/legacy-home.css"]').count() != 1:
                                issues.append("Original China stylesheet missing")
                        if route == "komanda/":
                            img = page.locator("img[src*='m7legal-team.webp']")
                            if img.count() == 0:
                                issues.append("Original team image missing")
                            else:
                                try:
                                    img.scroll_into_view_if_needed()
                                    page.wait_for_function(
                                        """() => [...document.images].some(img =>
                                          img.src.includes('m7legal-team.webp') &&
                                          img.complete && img.naturalWidth >= 1400)""",
                                        timeout=12000,
                                    )
                                except Exception:
                                    issues.append("Original team image not loaded")
                        if width in (390, 1440) and route in ("", "kontakty/", "komanda/",
                                                             "uslugi/mezhdunarodnye-sdelki/"):
                            slug = route.strip("/").replace("/", "-") or "home"
                            screenshot = slug + "-" + str(width) + "px.png"
                            page.screenshot(path=str(folder / screenshot), full_page=False,
                                            animations="disabled")
                            result["screenshots"].append(screenshot)
                    except Exception as e:
                        code = None
                        dims = {}
                        issues.append(type(e).__name__ + ": " + str(e)[:400])
                    item = {"route": "/" + route, "width": width, "status": code,
                            "measurements": dims, "issues": issues}
                    result["checks"].append(item)
                    if issues:
                        result["failures"].append(item)
                page.close()
        finally:
            browser.close()
    result["summary"] = {"checks": len(result["checks"]),
                         "passed": len(result["checks"]) - len(result["failures"]),
                         "failed": len(result["failures"])}
    (folder / "live-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    for item in result["failures"]:
        print("FAIL:", json.dumps(item, ensure_ascii=False)[:850])
    return not result["failures"]


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
