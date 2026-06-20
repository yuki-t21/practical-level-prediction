import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

import functions_framework
from flask import Request, Response
from google.cloud import secretmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize client lazily
sm_client: secretmanager.SecretManagerServiceClient | None = None


def get_sm_client() -> secretmanager.SecretManagerServiceClient:
    """
    Secret Manager クライアントを遅延初期化して返します。

    Returns
    -------
    google.cloud.secretmanager.SecretManagerServiceClient
        初期化済みの Secret Manager クライアント。
    """
    global sm_client
    if sm_client is None:
        sm_client = secretmanager.SecretManagerServiceClient()
    return sm_client


def get_slack_webhook_url() -> str:
    """
    環境変数で指定された Secret Manager のパスから Slack Webhook URL を取得します。

    Returns
    -------
    str
        取得した Slack Webhook URL。

    Raises
    ------
    ValueError
        SLACK_TOKEN_SECRET_NAME 環境変数が設定されていない場合。
    """
    secret_name = os.environ.get("SLACK_TOKEN_SECRET_NAME")
    if not secret_name:
        raise ValueError("SLACK_TOKEN_SECRET_NAME environment variable is not set.")

    logger.info(f"Accessing Secret Manager for Slack Webhook URL: {secret_name}")
    response = get_sm_client().access_secret_version(request={"name": secret_name})
    return response.payload.data.decode("UTF-8").strip()


def post_message_to_slack(webhook_url: str, channel: str, text: str) -> str:
    """
    Slack Incoming Webhook URL を使用して、指定されたチャンネルにメッセージを送信します。

    Parameters
    ----------
    webhook_url : str
        Slack Incoming Webhook URL。
    channel : str
        送信先のチャンネル名（例: "#general"）。Webhook側の設定によっては無視されます。
    text : str
        送信するメッセージテキスト。

    Returns
    -------
    str
        送信ステータス。成功した場合は "success"、失敗した場合は "error: <理由>"。
    """
    headers = {
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = {
        "text": text,
    }
    if channel:
        payload["channel"] = channel

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8").strip()
            if body != "ok":
                logger.error(f"Slack Webhook error: {body}")
                return f"error: {body}"
            logger.info("Successfully sent Slack notification via Webhook.")
            return "success"
    except urllib.error.URLError as e:
        logger.error(f"HTTP request to Slack Webhook failed: {str(e)}")
        return f"error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error when sending Slack notification: {str(e)}")
        return f"error: {str(e)}"


@functions_framework.http
def send_slack_notification(request: Request) -> Response:
    """
    BigQuery リモート関数からの HTTP リクエストを処理して Slack 通知を送信します。

    BigQuery Remote Function の呼び出し規約に従い、JSON 形式でリクエストを受理し、
    結果を JSON 形式で返します。

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
        replies: list[str] = []

        try:
            webhook_url = get_slack_webhook_url()
        except Exception as se:
            logger.error(
                f"Failed to fetch Slack Webhook URL from Secret Manager: {str(se)}"
            )
            # トークン取得自体が失敗した場合は、すべての行をエラーにする
            error_response = {"errorMessage": f"Configuration error: {str(se)}"}
            return Response(
                response=json.dumps(error_response),
                status=500,
                mimetype="application/json",
            )

        for call in calls:
            if len(call) < 2:
                replies.append(
                    "error: insufficient arguments (require channel and text)"
                )
                continue

            channel = call[0]
            text = call[1]

            if not channel or not text:
                replies.append("error: channel or text is empty")
                continue

            # Ensure channel and text are strings
            channel_str = str(channel).strip()
            text_str = str(text).strip()

            result = post_message_to_slack(webhook_url, channel_str, text_str)
            replies.append(result)

        return Response(
            response=json.dumps({"replies": replies}),
            status=200,
            mimetype="application/json",
        )

    except Exception as e:
        logger.exception("Unexpected error in send_slack_notification")
        error_response = {"errorMessage": f"System error: {str(e)}"}
        return Response(
            response=json.dumps(error_response),
            status=500,
            mimetype="application/json",
        )
