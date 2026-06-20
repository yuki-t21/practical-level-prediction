import asyncio
import json
import logging
from typing import Any, cast

import functions_framework
from flask import Request, Response
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def scrape_certifications() -> list[dict[str, str]]:
    """
    Google Cloud 認定資格の一覧ページを Playwright でスクレイピングし、
    資格名、レベル、URL のリストを取得します。

    Returns
    -------
    list[dict[str, str]]
        認定資格情報のリスト。各要素は {"title": str, "level": str, "url": str}。

    Raises
    ------
    Exception
        ページの遷移または評価に失敗した場合。
    """
    url = "https://cloud.google.com/learn/certification?hl=en"
    logger.info(f"Starting scraping for Google Cloud certifications from {url}")

    async with async_playwright() as p:
        # Launch browser with options optimized for container environments
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        try:
            page = await browser.new_page()
            # Set user agent to prevent basic bot blocking
            await page.set_extra_http_headers(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                }
            )

            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Extract certifications using JS evaluation to traverse DOM robustly
            # Based on headers containing Foundational/Associate/Professional certifications
            data = await page.evaluate("""
                () => {
                    const headers = Array.from(document.querySelectorAll('h3, h2'));
                    const results = [];
                    for (const header of headers) {
                        const text = header.textContent.trim();
                        let level = "";
                        if (text.includes("Foundational certification")) {
                            level = "Foundational";
                        } else if (text.includes("Associate certification")) {
                            level = "Associate";
                        } else if (text.includes("Professional certification")) {
                            level = "Professional";
                        }

                        if (level) {
                            let container = header.parentElement;
                            // Search up the DOM tree to find the container holding certification links
                            while (container && !container.querySelector('a[href*="/certification/"]') && container.tagName !== 'BODY') {
                                container = container.parentElement;
                            }

                            if (container) {
                                const links = container.querySelectorAll('a[href*="/certification/"]');
                                for (const link of links) {
                                    const title = link.textContent.replace(/\\s+/g, ' ').trim();
                                    const href = link.href;
                                    if (title && href && !results.some(r => r.url === href)) {
                                        results.push({ title, level, url: href });
                                    }
                                }
                            }
                        }
                    }
                    return results;
                }
                """)
            logger.info(f"Successfully scraped {len(data)} certifications.")
            return cast(list[dict[str, str]], data)
        except Exception as e:
            logger.error(f"Error during page evaluation or navigation: {str(e)}")
            raise
        finally:
            await browser.close()


@functions_framework.http
def handler(request: Request) -> Response:
    """
    BigQuery リモート関数からの HTTP リクエストを処理し、
    Google Cloud 認定資格の一覧を JSON 文字列として返します。

    Parameters
    ----------
    request : flask.Request
        HTTP リクエストオブジェクト。

    Returns
    -------
    flask.Response
        HTTP レスポンスオブジェクト。
    """
    try:
        request_json = request.get_json(silent=True)
        if not request_json or "calls" not in request_json:
            error_response = {"errorMessage": "Invalid request: missing 'calls'"}
            return Response(
                response=json.dumps(error_response),
                status=400,
                mimetype="application/json",
            )

        calls: list[list[Any]] = request_json["calls"]

        # Run async scraping function using asyncio
        try:
            certifications = asyncio.run(scrape_certifications())
            certs_json_str = json.dumps(certifications, ensure_ascii=False)
        except Exception as se:
            logger.exception("Failed to scrape certifications")
            error_response = {"errorMessage": f"Scraping error: {str(se)}"}
            return Response(
                response=json.dumps(error_response),
                status=500,
                mimetype="application/json",
            )

        # BigQuery expects one reply for each call in the batch
        replies = [certs_json_str for _ in calls]
        return Response(
            response=json.dumps({"replies": replies}),
            status=200,
            mimetype="application/json",
        )

    except Exception as e:
        logger.exception("Unexpected error in handler")
        error_response = {"errorMessage": f"System error: {str(e)}"}
        return Response(
            response=json.dumps(error_response),
            status=500,
            mimetype="application/json",
        )
