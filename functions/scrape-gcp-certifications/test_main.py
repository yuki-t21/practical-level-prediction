import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@patch("main.scrape_certifications", new_callable=AsyncMock)
def test_handler_success(mock_scrape):  # type: ignore
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

    response = client.post("/", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "replies" in data
    assert len(data["replies"]) == 1

    # Verify the JSON string inside replies
    reply_data = json.loads(data["replies"][0])
    assert len(reply_data) == 1
    assert reply_data[0]["title"] == "Associate Cloud Engineer"
    assert reply_data[0]["level"] == "Associate"


def test_handler_missing_calls():  # type: ignore
    """
    'calls' キーが欠けている場合に、バリデーションエラー(422)が返ることを確認します。
    """
    response = client.post("/", json={})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_health_check():  # type: ignore
    """
    ヘルスチェックエンドポイントが正常に応答することを確認します。
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
