#!/usr/bin/env python3
"""Browser-driven, read-only QA for M7Legal.

Runs on a GitHub Actions hosted runner, NEVER on LABNED production servers.
No form submits, no browser login and no data modifications. Saves PNG and JSON
artifacts for review after every run.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

MAIN_SITES = ["https://labned.ru/", "https://m7legal.ru/"]
STAGING_ROUTES = ["", "o-kompanii/", "komanda/", "praktika/", "uslugi/", "tseny/", "kontakty/", "uslugi/mezhdunarodnye-sdelki/"]
VIEWPORTS = [(320, 720), (390, 844), (768, 1024), (1440, 900)]


def run(base_url: str, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    base_url = base_url.rstrip("/") + "/"
    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "browser": "Playwright Chromium",
        "staging": base_url,
        "checks": [],
        "errors": [],
        "screenshots": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"]
        )
        try:
            for width, height in VIEWPORTS:
                page = browser.new_page(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                    reduced_motion="reduce",
                )
                page_errors = []
                page.on("pageerror", lambda exc: page_errors.append(str(exc)[:350]))
                for route in STAGING_ROUTES:
                    url = base_url + route
                    issues = []
                    page_errors.clear()
                    try:
                        response = page.goto(
                            url, wait_until="domcontentloaded", timeout=25000
                        )
                        page.wait_for_timeout(200)
                        measurements = page.evaluate(
                            """() => ({
                                viewport: innerWidth,
                                document: document.documentElement.scrollWidth,
                                body: document.body.scrollWidth,
                                title: document.title,
                                h1: !!document.querySelector("h1"),
                                formCount: document.querySelectorAll("form").length,
                                hasPreviewScript: !!document.querySelector('script[src*="preview.js"]')
                            })"""
                        )
                        status = response.status if response else None
                        if status != 200:
                            issues.append(f"Unexpected HTTP {status}")
                        if max(measurements["document"], measurements["body"]) > width + 1:
                            issues.append("Horizontal scrolling outside viewport")
                        if not measurements["h1"]:
                            issues.append("Missing h1")
                        if not measurements["hasPreviewScript"]:
                            issues.append("Missing staging safety script")
                        if page_errors:
                            issues.extend("JS: " + error for error in page_errors)

                        if page.locator(".site-header").count() == 1:
                            if page.locator(".utility").count() != 0:
                                issues.append("Old dark header strip was not removed")
                            if page.locator(".nav-contact .nav-phone").count() != 1:
                                issues.append("New-design phone contact not found")
                            if page.locator('.nav-contact .nav-email[href="mailto:info@m7legal.ru"]').count() != 1:
                                issues.append("Header email not positioned below telephone")
                        if route in ("", "o-kompanii/"):
                            selector = ".m7-award-strip" if route == "" else ".m7-award-about"
                            award = page.locator(selector)
                            if award.count() != 1:
                                issues.append("Missing award trust section " + selector)
                            else:
                                if "M7Legal (группа компаний LABNED)" not in award.inner_text():
                                    issues.append("Incorrect group award attribution")
                                if award.locator('a[href="https://labned.ru/blog/labned-pobeditel-loyalty-cx-awards-2026/"]').count() < 1:
                                    issues.append("Original award news link missing")
                                img = award.locator("img").first
                                if img.count() != 1:
                                    issues.append("Real award photograph missing")
                                else:
                                    award.scroll_into_view_if_needed()
                                    try:
                                        page.wait_for_function(
                                            """sel => {
                                                const image = document.querySelector(sel + ' img');
                                                return image && image.complete && image.naturalWidth > 100;
                                            }""", arg=selector, timeout=11000
                                        )
                                    except Exception:
                                        issues.append("Original award photograph failed to load")
                                if width in (390, 1440):
                                    label = "homepage" if route == "" else "about"
                                    shot = f"award-{label}-{width}px.png"
                                    award.screenshot(path=str(output / shot), animations="disabled")
                                    result["screenshots"].append(shot)
                        if route == "":
                            if page.locator(".m7-china-entry").count() > 0:
                                issues.append("Removed China promotion block still shown on homepage")
                        if route == "uslugi/mezhdunarodnye-sdelki/":
                            old_style = page.locator('link[href*="assets/legacy-home.css"]')
                            if old_style.count() != 1:
                                issues.append("Original site CSS missing from international deals page")
                            heading = page.locator("h1").first.inner_text().strip()
                            if "Проверка контрагентов из Китая" not in heading:
                                issues.append("Original China landing headline missing")
                            if page.locator('script[src*="m7-form.js"]').count() != 0:
                                issues.append("Unexpected live lead-sender on staging China page")

                        if route == "o-kompanii/":
                            group_photo = page.locator(".m7-team-figure img")
                            if group_photo.count() != 1:
                                issues.append("Missing original team photograph")
                            else:
                                group_photo.scroll_into_view_if_needed()
                                try:
                                    page.wait_for_function(
                                        """() => {
                                          const img = document.querySelector(".m7-team-figure img");
                                          return img && img.complete && img.naturalWidth >= 1400;
                                        }""",
                                        timeout=12500,
                                    )
                                except Exception:
                                    issues.append("Team photograph not fully loaded")
                                # Avoid accidental placeholder capture: wait for image first.
                                page.wait_for_timeout(150)

                        if (width, route) in (
                            (390, ""), (390, "o-kompanii/"),
                            (1440, ""), (1440, "o-kompanii/"),
                            (390, "uslugi/mezhdunarodnye-sdelki/"),
                            (1440, "uslugi/mezhdunarodnye-sdelki/"),
                        ):
                            label = route.strip("/") or "home"
                            filename = f"{label}-{width}px.png"
                            page.screenshot(
                                path=str(output / filename),
                                full_page=False,
                                animations="disabled",
                            )
                            result["screenshots"].append(filename)

                        if route == "" and width == 390:
                            button = page.locator(".menu-toggle")
                            if button.count() == 1:
                                button.click(timeout=4000)
                                if button.get_attribute("aria-expanded") != "true":
                                    issues.append("Mobile menu did not open")
                                button.click(timeout=4000)
                                if button.get_attribute("aria-expanded") != "false":
                                    issues.append("Mobile menu did not close")
                    except Exception as exc:
                        status = None
                        measurements = {}
                        issues.append(type(exc).__name__ + ": " + str(exc)[:350])
                    item = {
                        "device_width": width,
                        "route": route or "/",
                        "http": status,
                        "measurements": measurements,
                        "issues": issues,
                    }
                    result["checks"].append(item)
                    if issues:
                        result["errors"].append(item)
                page.close()

            context = browser.new_context()
            check_page = context.new_page()
            for url in MAIN_SITES:
                try:
                    response = check_page.goto(
                        url, wait_until="domcontentloaded", timeout=22000
                    )
                    code = response.status if response else None
                    issues = [] if code == 200 else [f"HTTP {code}"]
                    item = {"url": url, "http": code, "issues": issues}
                except Exception as exc:
                    item = {
                        "url": url, "http": None,
                        "issues": [type(exc).__name__ + ": " + str(exc)[:350]],
                    }
                result["checks"].append(item)
                if item["issues"]:
                    result["errors"].append(item)
            context.close()
        finally:
            browser.close()

    result["summary"] = {
        "total": len(result["checks"]),
        "passed": len(result["checks"]) - len(result["errors"]),
        "failed": len(result["errors"]),
    }
    (output / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    for item in result["errors"]:
        print("FAIL:", json.dumps(item, ensure_ascii=False)[:700])
    return not result["errors"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="https://dev.labned.ru/m7legal-preview-20261009/",
    )
    parser.add_argument("--output", type=Path, default=Path("qa-artifacts"))
    args = parser.parse_args()
    sys.exit(0 if run(args.base_url, args.output) else 1)
