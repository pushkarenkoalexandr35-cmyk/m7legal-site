#!/usr/bin/env python3
"""Read-only Chromium audit of Yandex Metrika and Top.Mail.Ru on every M7Legal URL."""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
from playwright.sync_api import sync_playwright

SITE = "https://m7legal.ru/"
COUNTER = "111107130"
TRACKER = "mc.yandex.ru/metrika/tag.js"
MAIL_TRACKER = "top-fwz1.mail.ru/js/code.js"
MAIL_ID = "3801161"
REPORT_DIR = Path("metrika-audit-artifacts")

def live_routes():
    req = urllib.request.Request(SITE + "sitemap.xml", headers={"User-Agent": "M7Legal-Metrika-Audit/1.0"})
    with urllib.request.urlopen(req, timeout=16) as response:
        sitemap = ElementTree.fromstring(response.read())
    routes = sorted({elem.text for elem in sitemap.iter() if elem.tag.endswith("loc") and elem.text})
    if len(routes) != 37 or any(not url.startswith(SITE) for url in routes):
        raise RuntimeError("Unexpected sitemap pages: " + str(len(routes)))
    return routes

def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        try:
            for url in live_routes():
                page = browser.new_page(viewport={"width": 1240, "height": 840})
                tag_responses = []
                tag_failures = []
                mail_responses = []
                mail_failures = []
                errors = []
                page.on("response", lambda r: tag_responses.append({"status": r.status, "url": r.url})
                        if TRACKER in r.url else None)
                page.on("requestfailed", lambda r: tag_failures.append({"url": r.url, "failure": r.failure})
                        if TRACKER in r.url else None)
                page.on("response", lambda r: mail_responses.append({"status": r.status, "url": r.url})
                        if MAIL_TRACKER in r.url else None)
                page.on("requestfailed", lambda r: mail_failures.append({"url": r.url, "failure": r.failure})
                        if MAIL_TRACKER in r.url else None)
                page.on("pageerror", lambda e: errors.append(str(e)[:280]))
                row = {"url": url}
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    row["http"] = response.status if response else None
                    try:
                        page.wait_for_function("""() => typeof window.ym === 'function' &&
                            [...document.querySelectorAll('script[src]')].some(
                              s => s.src.includes('mc.yandex.ru/metrika/tag.js?id=111107130')
                            )""", timeout=9000)
                    except Exception:
                        pass
                    page.wait_for_timeout(800)
                    diag = page.evaluate("""() => ({
                        ym_defined: typeof window.ym === 'function',
                        metrika_tag_scripts: [...document.querySelectorAll('script[src]')]
                            .filter(s => s.src.includes('mc.yandex.ru/metrika/tag.js'))
                            .map(s => s.src),
                        topmail_script_urls: [...document.querySelectorAll('script[id="tmr-code"]')]
                            .map(s => s.src),
                        topmail_inline_pageviews: [...document.scripts].filter(s =>
                            (s.textContent || '').includes('_tmr.push({id: "3801161", type: "pageView"')
                        ).length,
                        topmail_queue_exists: Array.isArray(window._tmr),
                        site_js: [...document.querySelectorAll('script[src]')]
                            .filter(s => /site\\.js/.test(s.src)).map(s => s.src),
                        inline_init: [...document.scripts].some(s =>
                            (s.textContent || '').includes('ym(111107130,"init"') ||
                            (s.textContent || '').includes('ym(111107130, "init"')
                        ),
                        resource_entries: performance.getEntriesByType('resource')
                            .filter(x => x.name.includes('mc.yandex.ru/metrika/tag.js'))
                            .map(x => ({name: x.name, duration: Math.round(x.duration)}))
                    })""")
                    row.update(diag)
                    row["tag_responses"] = tag_responses[:5]
                    row["tag_failures"] = tag_failures[:5]
                    row["topmail_responses"] = mail_responses[:5]
                    row["topmail_failures"] = mail_failures[:5]
                    row["topmail_pixel_in_html"] = "top-fwz1.mail.ru/counter?id=3801161;js=na" in (response.text() if response else "")
                    row["page_errors"] = errors[:5]
                    row["passed"] = (row["http"] == 200 and row["ym_defined"] and
                                     len(row["metrika_tag_scripts"]) == 1 and
                                     "id=" + COUNTER in row["metrika_tag_scripts"][0] and
                                     len(row["site_js"]) == 1 and
                                     len(row["topmail_script_urls"]) == 1 and
                                     MAIL_TRACKER in row["topmail_script_urls"][0] and
                                     row["topmail_inline_pageviews"] == 1 and
                                     row["topmail_pixel_in_html"] and
                                     not errors)
                except Exception as e:
                    row["passed"] = False
                    row["error"] = type(e).__name__ + ": " + str(e)[:360]
                finally:
                    page.close()
                results.append(row)
        finally:
            browser.close()
    summary = {
        "pages_checked": len(results),
        "passed": sum(1 for x in results if x.get("passed")),
        "failed": sum(1 for x in results if not x.get("passed")),
        "tag_http_200_pages": sum(1 for x in results if any(r["status"] == 200 for r in x.get("tag_responses", []))),
        "page_errors": sum(len(x.get("page_errors", [])) for x in results),
        "single_counter_id": COUNTER,
        "single_topmail_id": MAIL_ID,
        "topmail_http_200_pages": sum(1 for x in results if any(r["status"] == 200 for r in x.get("topmail_responses", []))),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    (REPORT_DIR / "metrika-report.json").write_text(
        json.dumps({"summary": summary, "pages": results}, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(summary, ensure_ascii=False))
    for item in results:
        if not item.get("passed"):
            print("FAIL", json.dumps(item, ensure_ascii=False)[:1100])
    return 0 if summary["failed"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
