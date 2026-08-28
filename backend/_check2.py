import asyncio
from playwright.async_api import async_playwright

PAGES = [("/", "dashboard"), ("/market/raised-beds", "raised_beds")]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for path, name in PAGES:
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            resp = await page.goto(f"http://host.docker.internal:3000{path}", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(800)
            print(f"=== {name} status={resp.status if resp else None}")
            for e in errors:
                print("  CONSOLE:", e[:300])
            await page.screenshot(path=f"/app/_shot2_{name}.png", full_page=True)
            await page.close()
        await browser.close()


asyncio.run(main())
