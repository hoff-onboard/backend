"""
Open a browser, log in manually, then press Enter in the terminal to save the session.

Usage:
    python scripts/save_cookies.py [url] [output_file]

Examples:
    python scripts/save_cookies.py https://github.com
    python scripts/save_cookies.py https://github.com cookies/github.json
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

DEFAULT_URL = "https://github.com/login"
DEFAULT_OUTPUT = "cookies/github.json"


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    output = Path(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT)
    output.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url)

        input("\n>>> Log in in the browser, then press Enter here to save cookies...\n")

        await context.storage_state(path=str(output))
        await browser.close()

    print(f"Storage state saved to: {output.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
