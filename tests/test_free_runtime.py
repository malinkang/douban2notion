from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx
import requests
import pendulum
from notion_client.errors import APIErrorCode, APIResponseError

from douban2notion import douban
from douban2notion import heatmap_cli
from douban2notion import notion_helper
from douban2notion import utils


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

    def test_heatmap_counts_dated_pages_without_value_columns(self):
        loader = Mock(
            date_prop_name="日期",
            number_by_date_dict={"2026-11-08": 0},
            number_list=[],
        )
        loader.get_api_data.return_value = [
            {
                "properties": {
                    "日期": {"date": {"start": "2026-11-08T08:00:00+08:00"}}
                }
            },
            {
                "properties": {
                    "日期": {"date": {"start": "2026-11-08T20:00:00+08:00"}}
                }
            },
            {"properties": {"日期": {"date": None}}},
        ]

        heatmap_cli.count_tracks(loader)

        self.assertEqual(loader.number_by_date_dict["2026-11-08"], 2)
        self.assertIn(2, loader.number_list)

    def test_notion_client_retries_rate_limits_and_respects_retry_after(self):
        class RateLimitError(APIResponseError):
            def __init__(self):
                self.code = APIErrorCode.RateLimited
                self.headers = httpx.Headers({"Retry-After": "7"})

        rate_limited = RateLimitError()
        with patch.object(
            notion_helper.Client,
            "request",
            side_effect=[rate_limited, {"ok": True}],
        ) as request, patch("douban2notion.notion_helper.time.sleep") as sleep:
            client = notion_helper.RateLimitedNotionClient(
                auth="notion-token",
                min_request_interval=0,
                max_rate_limit_retries=2,
            )

            result = client.request("/search", "POST")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(7.0)

    def test_notion_client_paces_requests_below_rate_limit(self):
        with patch.object(
            notion_helper.Client,
            "request",
            return_value={"ok": True},
        ), patch(
            "douban2notion.notion_helper.time.monotonic",
            side_effect=[10.0, 10.1],
        ), patch(
            "douban2notion.notion_helper.time.sleep",
        ) as sleep:
            client = notion_helper.RateLimitedNotionClient(
                auth="notion-token",
                min_request_interval=0.5,
            )

            client.request("/first", "POST")
            client.request("/second", "POST")

        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.4)

    def test_book_database_id_can_be_configured_without_scanning_a_root_page(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as env_file:
            env_path = env_file.name
        try:
            with patch.dict(
                os.environ,
                {
                    "NOTION_TOKEN": "notion-token",
                    "BOOK_DATABASE_ID": "book-database-id",
                    "GITHUB_ENV": env_path,
                },
                clear=True,
            ), patch.object(notion_helper, "Client") as client:
                helper = notion_helper.NotionHelper("book")

            self.assertEqual(helper.book_database_id, "book-database-id")
            self.assertIsNone(helper.page_id)
            client.return_value.blocks.children.list.assert_not_called()
        finally:
            os.unlink(env_path)

    def test_missing_required_database_fails_before_querying_none(self):
        with patch.dict(
            os.environ,
            {"NOTION_TOKEN": "notion-token"},
            clear=True,
        ), patch.object(notion_helper, "Client"):
            with self.assertRaisesRegex(ValueError, "未找到书架数据库"):
                notion_helper.NotionHelper("book")

    def test_day_relation_omits_columns_missing_from_legacy_database(self):
        helper = notion_helper.NotionHelper.__new__(notion_helper.NotionHelper)
        helper.day_database_id = "day-database-id"
        helper.year_database_id = "year-database-id"
        helper.month_database_id = "month-database-id"
        helper.week_database_id = "week-database-id"
        helper._database_properties_cache = {
            "day-database-id": {
                "标题": {"type": "title"},
                "日期": {"type": "date"},
            }
        }
        helper.get_year_relation_id = Mock()
        helper.get_month_relation_id = Mock()
        helper.get_week_relation_id = Mock()
        helper.get_relation_id = Mock(return_value="day-page-id")

        helper.get_day_relation_id(pendulum.datetime(2026, 11, 8, 12, 0, 0))

        properties = helper.get_relation_id.call_args.args[3]
        self.assertEqual(set(properties), {"日期"})
        helper.get_year_relation_id.assert_not_called()
        helper.get_month_relation_id.assert_not_called()
        helper.get_week_relation_id.assert_not_called()

    def test_date_relations_are_only_added_when_target_columns_exist(self):
        helper = notion_helper.NotionHelper.__new__(notion_helper.NotionHelper)
        helper.target_database_id = "movie-database-id"
        helper.year_database_id = "year-database-id"
        helper.month_database_id = "month-database-id"
        helper.week_database_id = "week-database-id"
        helper.day_database_id = "day-database-id"
        helper._database_properties_cache = {
            "movie-database-id": {
                "电影名": {"type": "title"},
                "日期": {"type": "date"},
            }
        }
        for getter_name in (
            "get_year_relation_id",
            "get_month_relation_id",
            "get_week_relation_id",
            "get_day_relation_id",
        ):
            setattr(helper, getter_name, Mock())

        properties = {}
        helper.get_date_relation(
            properties,
            pendulum.datetime(2026, 11, 8, 12, 0, 0),
        )

        self.assertEqual(properties, {})
        for getter_name in (
            "get_year_relation_id",
            "get_month_relation_id",
            "get_week_relation_id",
            "get_day_relation_id",
        ):
            getattr(helper, getter_name).assert_not_called()

    def test_page_writes_skip_columns_missing_from_legacy_database(self):
        helper = notion_helper.NotionHelper.__new__(notion_helper.NotionHelper)
        helper.client = Mock()
        helper.client.pages.create.return_value = {"id": "new-page-id"}
        helper.client.pages.update.return_value = {"id": "existing-page-id"}
        helper.target_database_id = "movie-database-id"
        helper._database_properties_cache = {
            "movie-database-id": {
                "电影名": {"type": "title"},
                "日期": {"type": "date"},
            }
        }
        properties = {
            "电影名": {"title": []},
            "豆瓣链接": {"url": "https://movie.douban.com/subject/1/"},
            "封面": {"files": []},
        }

        helper.create_page(
            {"database_id": "movie-database-id", "type": "database_id"},
            properties,
            {"type": "external", "external": {"url": "https://example.com/a.jpg"}},
        )
        helper.update_page("existing-page-id", properties)

        expected = {"电影名": {"title": []}}
        self.assertEqual(
            helper.client.pages.create.call_args.kwargs["properties"], expected
        )
        self.assertEqual(
            helper.client.pages.update.call_args.kwargs["properties"], expected
        )

    def test_missing_optional_relation_database_is_skipped(self):
        helper = notion_helper.NotionHelper.__new__(notion_helper.NotionHelper)
        helper.client = Mock()
        helper._NotionHelper__cache = {}

        self.assertIsNone(
            helper.get_relation_id(
                "actor-name",
                None,
                notion_helper.USER_ICON_URL,
            )
        )
        helper.client.databases.query.assert_not_called()

    def test_relation_payloads_drop_empty_optional_ids(self):
        properties = utils.get_properties(
            {"演员": ["actor-page-id", None], "空的演员": [None]},
            {"演员": "relation", "空的演员": "relation"},
        )

        self.assertEqual(
            properties,
            {"演员": {"relation": [{"id": "actor-page-id"}]}},
        )

    def test_legacy_items_without_link_are_keyed_by_title(self):
        self.assertEqual(
            douban._notion_item_key(None, "  沃特希普陨落记  "),
            ("title", "沃特希普陨落记"),
        )
        self.assertEqual(
            douban._notion_item_key("https://movie.douban.com/subject/1/", "标题"),
            ("url", "https://movie.douban.com/subject/1/"),
        )
        self.assertIsNone(douban._notion_item_key("", "  "))


if __name__ == "__main__":
    unittest.main()
