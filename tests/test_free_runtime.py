from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import requests

from douban2notion import douban


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "douban2notion"
BLOCKED_HOSTS = (
    "wereadassets.malinkang.com",
    "i.malinkang.com",
    "notionhub.app",
    "heatmap.malinkang.com",
    "notion-icon.malinkang.com",
)


class FreeRuntimeTest(unittest.TestCase):
    def test_source_does_not_call_notionhub_services(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in SOURCE.rglob("*.py")
        )
        for host in BLOCKED_HOSTS:
            self.assertNotIn(host, source)

    def test_free_scope_is_movie_and_book(self):
        source = (SOURCE / "update_heatmap.py").read_text(encoding="utf-8")
        self.assertIn('{"movie", "book"}', source)

    def test_interest_page_uses_a_bounded_timeout(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"interests": [{"subject": {}}]}
        with patch("douban2notion.douban.requests.get", return_value=response) as get:
            interests = douban._fetch_interest_page("user", "movie", "done", 50)

        self.assertEqual(interests, [{"subject": {}}])
        self.assertEqual(get.call_args.kwargs["timeout"], (10, 30))
        self.assertEqual(get.call_args.kwargs["params"]["start"], 50)
        self.assertEqual(get.call_args.kwargs["params"]["apikey"], douban.DOUBAN_API_KEY)

    def test_interest_page_http_error_fails_instead_of_looping(self):
        response = Mock(ok=False, status_code=429)
        response.json.return_value = {"code": 429}
        with patch("douban2notion.douban.requests.get", return_value=response):
            with self.assertRaisesRegex(douban.DoubanApiError, "HTTP 429"):
                douban._fetch_interest_page("user", "movie", "done", 0)

    def test_expired_token_retries_public_interests_without_authorization(self):
        expired = Mock(ok=False, status_code=400)
        expired.json.return_value = {"code": 106, "msg": "access_token_has_expired"}
        public = Mock(ok=True, status_code=200)
        public.json.return_value = {"interests": [{"subject": {}}]}
        with patch.object(douban, "AUTH_TOKEN", "expired-token"), patch(
            "douban2notion.douban.requests.get",
            side_effect=[expired, public],
        ) as get:
            interests = douban._fetch_interest_page("user", "movie", "done", 0)

        self.assertEqual(interests, [{"subject": {}}])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args_list[0].kwargs["headers"]["authorization"],
            "Bearer expired-token",
        )
        self.assertNotIn("authorization", get.call_args_list[1].kwargs["headers"])
        self.assertFalse(
            get.call_args_list[1].kwargs["headers"]["user-agent"].startswith(
                "User-Agent:"
            )
        )

    def test_non_token_http_error_is_not_retried(self):
        response = Mock(ok=False, status_code=429)
        response.json.return_value = {"code": 429}
        with patch.object(douban, "AUTH_TOKEN", "current-token"), patch(
            "douban2notion.douban.requests.get",
            return_value=response,
        ) as get:
            with self.assertRaisesRegex(douban.DoubanApiError, "code=429"):
                douban._fetch_interest_page("user", "movie", "done", 0)

        self.assertEqual(get.call_count, 1)

    def test_interest_page_missing_list_fails_instead_of_looping(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"message": "unexpected payload"}
        with patch("douban2notion.douban.requests.get", return_value=response):
            with self.assertRaisesRegex(douban.DoubanApiError, "missing a list"):
                douban._fetch_interest_page("user", "movie", "done", 0)

    def test_optional_imdb_http_error_does_not_abort_the_sync(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("HTTP 403")
        with patch(
            "douban2notion.douban.requests.get",
            return_value=response,
        ) as get:
            self.assertIsNone(douban.get_imdb("https://movie.douban.com/subject/1/"))

        self.assertEqual(
            get.call_args.kwargs["timeout"],
            douban.DOUBAN_REQUEST_TIMEOUT,
        )


if __name__ == "__main__":
    unittest.main()
