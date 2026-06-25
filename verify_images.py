import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        # Serve the current directory
        import os
        path = os.path.abspath("index.html")
        await page.goto(f"file://{path}")
        await page.set_viewport_size({"width": 1280, "height": 1600})
        await page.screenshot(path="index_check.png", full_page=True)

        path_cv = os.path.abspath("cv.html")
        await page.goto(f"file://{path_cv}")
        await page.screenshot(path="cv_check.png", full_page=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
