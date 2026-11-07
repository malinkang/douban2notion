from pathlib import Path
import unittest
from unittest.mock import Mock, patch

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

    def test_interest_page_http_error_fails_instead_of_looping(self):
        response = Mock(ok=False, status_code=429)
        with patch("douban2notion.douban.requests.get", return_value=response):
            with self.assertRaisesRegex(douban.DoubanApiError, "HTTP 429"):
                douban._fetch_interest_page("user", "movie", "done", 0)

    def test_interest_page_missing_list_fails_instead_of_looping(self):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"message": "unexpected payload"}
        with patch("douban2notion.douban.requests.get", return_value=response):
            with self.assertRaisesRegex(douban.DoubanApiError, "missing a list"):
                douban._fetch_interest_page("user", "movie", "done", 0)


if __name__ == "__main__":
    unittest.main()
