import json
import os
import pendulum
from retrying import retry
import requests
from notion_helper import NotionHelper
import utils

DOUBAN_API_HOST = os.getenv("DOUBAN_API_HOST", "frodo.douban.com")
DOUBAN_API_KEY = os.getenv("DOUBAN_API_KEY", "0ac44ae016490db2204ce0a042db2916")

from config import movie_properties_type_dict, TAG_ICON_URL, USER_ICON_URL
from utils import get_icon

rating = {
    1: "⭐️",
    2: "⭐️⭐️",
    3: "⭐️⭐️⭐️",
    4: "⭐️⭐️⭐️⭐️",
    5: "⭐️⭐️⭐️⭐️⭐️",
}
status = {
    "mark": "想看",
    "doing": "在看",
    "done": "看过",
}
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

headers = {
    "host": DOUBAN_API_HOST,
    "authorization": f"Bearer {AUTH_TOKEN}" if AUTH_TOKEN else "",
    "user-agent": "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 15_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.16(0x18001023) NetType/WIFI Language/zh_CN",
    "referer": "https://servicewechat.com/wx2f9b06c1de1ccfca/84/page-frame.html",
}

@retry(stop_max_attempt_number=3, wait_fixed=5000)
def fetch_subjects(user, type_, status):
    offset = 0
    page = 0
    url = f"https://{DOUBAN_API_HOST}/api/v2/user/{user}/interests"
    total = 0
    results = []
    has_next = True
    while has_next:
        params = {
            "type": type_,
            "count": 50,
            "status": status,
            "start": offset,
            "apiKey": DOUBAN_API_KEY,
        }
        response = requests.get(url, headers=headers, params=params)
        print(response.status_code)
        response = response.json()
        results.extend(response.get("interests"))
        total = response.get("total")
        print(total)
        page += 1
        offset = page * 50
        has_next = len(results) < total
        print(f"offset = {offset}")
    return results



if __name__ == "__main__":
    notion_helper = NotionHelper()
    douban_name = os.getenv("DOUBAN_NAME", None)
    notion_movies = notion_helper.query_all(database_id=notion_helper.book_database_id)
    notion_movie_dict = {}
    for i in notion_movies:
        movie = {}
        for key, value in i.get("properties").items():
            movie[key] = utils.get_property_value(value)
        notion_movie_dict[movie.get("豆瓣链接")] = {
            "短评": movie.get("短评"),
            "状态": movie.get("状态"),
            "日期": movie.get("日期"),
            "评分": movie.get("评分"),
            "page_id": i.get("id")
        }
    print(f"notion {len(notion_movie_dict)}")
    results = []
    for i in status.keys():
        results.extend(fetch_subjects("malinkang", "movie", "done"))
    for result in results:
        movie = {}
        subject = result.get("subject")
        movie["电影名"] = subject.get("title")
        create_time = result.get("create_time")
        create_time = pendulum.parse(create_time)
        movie["日期"] = create_time.int_timestamp
        movie["豆瓣链接"] = subject.get("url")
        movie["状态"] = status.get(result.get("status"))
        print(f"status = {status.get(result.get('status'))}")
        if result.get("rating"):
            movie["评分"] = rating.get(result.get("rating").get("value"))
        if result.get("comment"):
            print(f"评论 {result.get('comment')}")
            movie["短评"] = result.get("comment")
        if notion_movie_dict.get(movie.get("豆瓣链接")):
            notion_movive = notion_movie_dict.get(movie.get("豆瓣链接"))
            if (
                notion_movive.get("日期") != movie.get("日期")
                or notion_movive.get("短评") != movie.get("短评")
                or notion_movive.get("状态") != movie.get("状态")
                or notion_movive.get("评分") != movie.get("评分")
            ):

                print(f"更新{movie.get('电影名')}")
                print(notion_movive.get("日期") != movie.get("日期"))
                print(notion_movive.get("短评") != movie.get("短评"))
                print(notion_movive.get("状态") != movie.get("状态"))
                print(notion_movive.get("评分") != movie.get("评分"))
                properties = utils.get_properties(movie, movie_properties_type_dict)
                notion_helper.get_date_relation(properties,create_time)
                notion_helper.update_page(
                    page_id=notion_movive.get("page_id"),
                    properties=properties
            )

        else:
            print(f"插入{movie.get('电影名')}")
            cover = subject.get("pic").get("large")
            movie["封面"] = cover
            movie["类型"] = subject.get("type")
            if subject.get("genres"):
                movie["分类"] = [
                    notion_helper.get_relation_id(
                        x, notion_helper.category_database_id, TAG_ICON_URL
                    )
                    for x in subject.get("genres")
                ]
            if subject.get("actors"):
                movie["演员"] = [
                    notion_helper.get_relation_id(
                        x.get("name"), notion_helper.actor_database_id, USER_ICON_URL
                    )
                    for x in subject.get("actors")[0:100]
                ]
            if subject.get("directors"):
                movie["导演"] = [
                    notion_helper.get_relation_id(
                        x.get("name"), notion_helper.director_database_id, USER_ICON_URL
                    )
                    for x in subject.get("directors")[0:100]
                ]
            properties = utils.get_properties(movie, movie_properties_type_dict)
            notion_helper.get_date_relation(properties,create_time)
            parent = {
                "database_id": notion_helper.book_database_id,
                "type": "database_id",
            }
            notion_helper.create_page(
                parent=parent, properties=properties, icon=get_icon(cover)
            )
