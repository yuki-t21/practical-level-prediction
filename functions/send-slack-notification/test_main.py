import json
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

# Import the function to be tested
import main


class TestSendSlackNotification(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        # Reset globals before each test
        main.sm_client = None

    @patch("main.get_slack_webhook_url")
    @patch("main.post_message_to_slack")
    def test_send_slack_notification_success(
        self, mock_post: MagicMock, mock_get_webhook: MagicMock
    ) -> None:
        mock_get_webhook.return_value = "https://hooks.slack.com/services/fake-webhook"
        mock_post.side_effect = ["success", "success"]

        payload = {
            "calls": [
                ["#channel-1", "test message 1"],
                ["#channel-2", "test message 2"],
            ]
        }

        with self.app.test_request_context(
            path="/", method="POST", json=payload
        ) as ctx:
            response = main.send_slack_notification(ctx.request)
            self.assertEqual(response.status_code, 200)

            res_data = json.loads(response.get_data(as_text=True))
            self.assertEqual(res_data["replies"], ["success", "success"])
            self.assertEqual(mock_post.call_count, 2)
            mock_post.assert_any_call(
                "https://hooks.slack.com/services/fake-webhook",
                "#channel-1",
                "test message 1",
            )
            mock_post.assert_any_call(
                "https://hooks.slack.com/services/fake-webhook",
                "#channel-2",
                "test message 2",
            )

    @patch("main.get_slack_webhook_url")
    def test_send_slack_notification_missing_args(
        self, mock_get_webhook: MagicMock
    ) -> None:
        mock_get_webhook.return_value = "https://hooks.slack.com/services/fake-webhook"

        payload = {
            "calls": [
                ["#channel-1"],  # Missing message
                ["", "text"],  # Empty channel
                ["#channel-3", ""],  # Empty text
            ]
        }

        with self.app.test_request_context(
            path="/", method="POST", json=payload
        ) as ctx:
            response = main.send_slack_notification(ctx.request)
            self.assertEqual(response.status_code, 200)

            res_data = json.loads(response.get_data(as_text=True))
            self.assertEqual(
                res_data["replies"][0],
                "error: insufficient arguments (require channel and text)",
            )
            self.assertEqual(res_data["replies"][1], "error: channel or text is empty")
            self.assertEqual(res_data["replies"][2], "error: channel or text is empty")

    def test_send_slack_notification_invalid_payload(self) -> None:
        payload = {"invalid_key": "some_value"}

        with self.app.test_request_context(
            path="/", method="POST", json=payload
        ) as ctx:
            response = main.send_slack_notification(ctx.request)
            self.assertEqual(response.status_code, 400)

            res_data = json.loads(response.get_data(as_text=True))
            self.assertIn("errorMessage", res_data)

    @patch("main.get_slack_webhook_url")
    def test_send_slack_notification_secret_manager_error(
        self, mock_get_webhook: MagicMock
    ) -> None:
        mock_get_webhook.side_effect = Exception("Secret Manager Connection Failed")

        payload = {"calls": [["#channel", "message"]]}

        with self.app.test_request_context(
            path="/", method="POST", json=payload
        ) as ctx:
            response = main.send_slack_notification(ctx.request)
            self.assertEqual(response.status_code, 500)

            res_data = json.loads(response.get_data(as_text=True))
            self.assertIn("errorMessage", res_data)

    @patch("os.environ.get")
    def test_get_slack_webhook_url_missing_env(self, mock_env_get: MagicMock) -> None:
        mock_env_get.return_value = None
        with self.assertRaises(ValueError):
            main.get_slack_webhook_url()

    @patch("os.environ.get")
    @patch("main.get_sm_client")
    def test_get_slack_webhook_url_success(
        self, mock_get_sm: MagicMock, mock_env_get: MagicMock
    ) -> None:
        mock_env_get.return_value = "projects/12345/secrets/SLACK_TOKEN/versions/1"

        mock_sm_client = MagicMock()
        mock_get_sm.return_value = mock_sm_client

        # Mock payload structure of Secret Manager response
        mock_version_response = MagicMock()
        mock_version_response.payload.data = (
            b"https://hooks.slack.com/services/fake-webhook\n"
        )
        mock_sm_client.access_secret_version.return_value = mock_version_response

        webhook_url = main.get_slack_webhook_url()
        self.assertEqual(webhook_url, "https://hooks.slack.com/services/fake-webhook")
        mock_sm_client.access_secret_version.assert_called_once_with(
            request={"name": "projects/12345/secrets/SLACK_TOKEN/versions/1"}
        )

    @patch("urllib.request.urlopen")
    def test_post_message_to_slack_success(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"ok"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = main.post_message_to_slack(
            "https://hooks.slack.com/services/fake-webhook", "#channel", "hello"
        )
        self.assertEqual(result, "success")

    @patch("urllib.request.urlopen")
    def test_post_message_to_slack_api_error(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b"invalid_token"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = main.post_message_to_slack(
            "https://hooks.slack.com/services/fake-webhook", "#channel", "hello"
        )
        self.assertEqual(result, "error: invalid_token")


if __name__ == "__main__":
    unittest.main()
