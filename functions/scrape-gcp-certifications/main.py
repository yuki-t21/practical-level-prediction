import json
import logging
from typing import Any, cast

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="scrape-gcp-certifications", version="0.1.0")


class BigQueryRemoteFunctionRequest(BaseModel):
    """
    BigQuery リモート関数からのリクエストデータモデル。

    Attributes
    ----------
    requestId : str | None
        リクエスト ID。
    caller : str | None
        呼び出し元。
    userDefinedContext : dict[str, Any] | None
        ユーザー定義のコンテキスト。
    calls : list[list[Any]]
        BigQuery から渡される引数のバッチリスト。
    """

    requestId: str | None = Field(default=None, description="リクエスト ID")
    caller: str | None = Field(default=None, description="呼び出し元")
    userDefinedContext: dict[str, Any] | None = Field(
        default=None, description="ユーザー定義コンテキスト"
    )
    calls: list[list[Any]] = Field(..., description="引数のバッチリスト")


class BigQueryRemoteFunctionResponse(BaseModel):
    """
    BigQuery リモート関数へのレスポンスデータモデル。

    Attributes
    ----------
    replies : list[str]
        各呼び出しに対する応答メッセージのリスト。
    errorMessage : str | None
        エラーが発生した場合のメッセージ。
    """

    replies: list[str] = Field(default=[], description="応答メッセージのリスト")
    errorMessage: str | None = Field(default=None, description="エラーメッセージ")


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


@app.get("/")
async def health_check() -> dict[str, str]:
    """
    サービスの起動状態を確認するヘルスチェックエンドポイント。

    Returns
    -------
    dict[str, str]
        ステータス情報。
    """
    return {"status": "ok"}


@app.post("/", response_model=BigQueryRemoteFunctionResponse)
async def handler(
    request_payload: BigQueryRemoteFunctionRequest,
) -> Any:
    """
    BigQuery リモート関数からの HTTP リクエストを処理し、
    Google Cloud 認定資格の一覧を JSON 文字列として返します。

    Parameters
    ----------
    request_payload : BigQueryRemoteFunctionRequest
        HTTP リクエストボディを表す Pydantic モデル。

    Returns
    -------
    Any
        BigQuery リモート関数の仕様に沿ったレスポンス。
    """
    try:
        calls = request_payload.calls

        # Run async scraping function directly
        try:
            certifications = await scrape_certifications()
            certs_json_str = json.dumps(certifications, ensure_ascii=False)
        except Exception as se:
            logger.exception("Failed to scrape certifications")
            return JSONResponse(
                status_code=500,
                content={"errorMessage": f"Scraping error: {str(se)}"},
            )

        # BigQuery expects one reply for each call in the batch
        replies = [certs_json_str for _ in calls]
        return BigQueryRemoteFunctionResponse(replies=replies)

    except Exception as e:
        logger.exception("Unexpected error in handler")
        return JSONResponse(
            status_code=500,
            content={"errorMessage": f"System error: {str(e)}"},
        )
