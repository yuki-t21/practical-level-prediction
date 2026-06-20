import json
from unittest.mock import AsyncMock, patch

import pytest
from flask import Flask

from main import handler


@pytest.fixture
def app():  # type: ignore
    """
    テスト用の Flask アプリケーションを初期化します。
    """
    return Flask("test_app")


@patch("main.scrape_certifications", new_callable=AsyncMock)
def test_handler_success(mock_scrape, app):  # type: ignore
    """
    スクレイピングが成功した場合に、正しいレスポンスが返ることを確認します。
    """
    mock_scrape.return_value = [
        {
            "title": "Associate Cloud Engineer",
            "level": "Associate",
            "url": "https://example.com/ace",
        }
    ]

    payload = {"calls": [[]]}

    with app.test_request_context(path="/", method="POST", json=payload) as ctx:
        response = handler(ctx.request)
        assert response.status_code == 200

        data = response.get_json()
        assert "replies" in data
        assert len(data["replies"]) == 1

        # Verify the JSON string inside replies
        reply_data = json.loads(data["replies"][0])
        assert len(reply_data) == 1
        assert reply_data[0]["title"] == "Associate Cloud Engineer"
        assert reply_data[0]["level"] == "Associate"


def test_handler_missing_calls(app):  # type: ignore
    """
    'calls' キーが欠けている場合に、400 Bad Request を返すことを確認します。
    """
    with app.test_request_context(path="/", method="POST", json={}) as ctx:
        response = handler(ctx.request)
        assert response.status_code == 400
        data = response.get_json()
        assert "errorMessage" in data
