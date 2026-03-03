from playwright.async_api import async_playwright

from app.domain.branding.models import Brand

BRAND_JS = """\
(() => {
    const body = document.body;
    const bodyStyle = window.getComputedStyle(body);

    function rgbToHex(rgb) {
        if (!rgb) return '';
        const match = rgb.match(/\\d+/g);
        if (!match || match.length < 3) return rgb;
        return '#' + match.slice(0, 3).map(x =>
            parseInt(x).toString(16).padStart(2, '0')
        ).join('').toUpperCase();
    }

    const selectors = [
        'a.btn-primary', 'button.btn-primary',
        '[class*="Button--primary"]', '[class*="btn-success"]',
        'button[type="submit"]', '.btn',
        'a[href]:not([href="#"]):not([href=""])'
    ];
    let btn = null;
    for (const sel of selectors) {
        btn = document.querySelector(sel);
        if (btn) break;
    }
    const btnStyle = btn ? window.getComputedStyle(btn) : null;

    // Find a secondary color from links or other accents
    const link = document.querySelector('a[href]:not([href="#"]):not([href=""])');
    const linkStyle = link ? window.getComputedStyle(link) : null;
    const secondaryColor = linkStyle ? rgbToHex(linkStyle.color) : '';

    return {
        primary: btnStyle ? rgbToHex(btnStyle.backgroundColor) : '',
        secondary: secondaryColor,
        background: rgbToHex(bodyStyle.backgroundColor),
        text: rgbToHex(bodyStyle.color),
        fontFamily: bodyStyle.fontFamily,
        borderRadius: btnStyle ? btnStyle.borderRadius : '0px'
    };
})()
"""


async def extract_brand(url: str, cookies_file: str | None = None) -> Brand:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=cookies_file if cookies_file else None,
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        raw = await page.evaluate(BRAND_JS)
        await browser.close()

    return Brand(**raw)
