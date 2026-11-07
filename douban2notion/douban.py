import argparse
from email import feedparser
import json
import os
import re
from bs4 import BeautifulSoup
import pendulum
from retrying import retry
import requests
from douban2notion.notion_helper import NotionHelper
from douban2notion import utils
DOUBAN_API_HOST = os.getenv("DOUBAN_API_HOST", "frodo.douban.com")
DOUBAN_API_KEY = os.getenv("DOUBAN_API_KEY", "0ac44ae016490db2204ce0a042db2916")

from douban2notion.config import movie_properties_type_dict,book_properties_type_dict, TAG_ICON_URL, USER_ICON_URL
from douban2notion.utils import get_icon
from dotenv import load_dotenv
load_dotenv()
rating = {
    1: "⭐️",
    2: "⭐️⭐️",
    3: "⭐️⭐️⭐️",
    4: "⭐️⭐️⭐️⭐️",
    5: "⭐️⭐️⭐️⭐️⭐️",
}
movie_status = {
    "mark": "想看",
    "doing": "在看",
    "done": "看过",
}
book_status = {
    "mark": "想读",
    "doing": "在读",
    "done": "读过",
}
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
DOUBAN_REQUEST_TIMEOUT = (10, 30)

headers = {
    "host": DOUBAN_API_HOST,
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.16(0x18001023) NetType/WIFI Language/zh_CN",
    "referer": "https://servicewechat.com/wx2f9b06c1de1ccfca/84/page-frame.html",
}
INVALID_TOKEN_CODES = {103, 106, 109, 111, 112}


class DoubanApiError(RuntimeError):
    pass


def _request_headers(use_token):
    request_headers = dict(headers)
    if use_token and AUTH_TOKEN:
        request_headers["authorization"] = f"Bearer {AUTH_TOKEN}"
    return request_headers


def _response_error_code(response):
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if isinstance(code, bool):
        return None
    if isinstance(code, int):
        return code
    if isinstance(code, str) and code.isdigit() and len(code) <= 6:
        return int(code)
    return None


def _fetch_interest_page(user, type_, status, offset):
    url = f"https://{DOUBAN_API_HOST}/api/v2/user/{user}/interests"
    params = {
        "type": type_,
        "count": 50,
        "status": status,
        "start": offset,
        "apikey": DOUBAN_API_KEY,
    }
    response = requests.get(
        url,
        headers=_request_headers(True),
        params=params,
        timeout=DOUBAN_REQUEST_TIMEOUT,
    )
    error_code = None if response.ok else _response_error_code(response)
    if (
        not response.ok
        and AUTH_TOKEN
        and (
            response.status_code == 401
            or error_code in INVALID_TOKEN_CODES
        )
    ):
        # Public interests remain available when a saved mobile token expires.
        response = requests.get(
            url,
            headers=_request_headers(False),
            params=params,
            timeout=DOUBAN_REQUEST_TIMEOUT,
        )
        error_code = None if response.ok else _response_error_code(response)
    if not response.ok:
        code_detail = f", code={error_code}" if error_code is not None else ""
        raise DoubanApiError(
            f"Douban interests request failed with HTTP {response.status_code}{code_detail}"
        )
    payload = response.json()
    interests = payload.get("interests") if isinstance(payload, dict) else None
    if not isinstance(interests, list):
        raise DoubanApiError("Douban interests response is missing a list")
    return interests


@retry(stop_max_attempt_number=3, wait_fixed=5000)
def fetch_subjects(user, type_, status):
    offset = 0
    page = 0
    results = []
    while True:
        interests = _fetch_interest_page(user, type_, status, offset)
        if not interests:
            break
        results.extend(interests)
        print(f"size = {len(results)}")
        page += 1
        offset = page * 50
    return results


def _notion_item_key(link, title):
    for kind, value in (("url", link), ("title", title)):
        normalized = str(value or "").strip()
        if normalized:
            return kind, normalized
    return None



def insert_movie(douban_name,notion_helper):
    notion_movies = notion_helper.query_all(database_id=notion_helper.movie_database_id)
    notion_movie_dict = {}
    for i in notion_movies:
        movie = {}
        for key, value in i.get("properties").items():
            movie[key] = utils.get_property_value(value)
        item_key = _notion_item_key(movie.get("豆瓣链接"), movie.get("电影名"))
        if item_key:
            notion_movie_dict[item_key] = {
                "短评": movie.get("短评"),
                "状态": movie.get("状态"),
                "日期": movie.get("日期"),
                "评分": movie.get("评分"),
                "演员": movie.get("演员"),
                "IMDB": movie.get("IMDB"),
                "page_id": i.get("id")
            }
    results = []
    for i in movie_status.keys():
        results.extend(fetch_subjects(douban_name, "movie", i))
    for result in results:
        movie = {}
        if not result:
            print(result)
            continue
        subject = result.get("subject")
        movie["电影名"] = subject.get("title")
        create_time = result.get("create_time")
        create_time = pendulum.parse(create_time,tz=utils.tz)
        #时间上传到Notion会丢掉秒的信息，这里直接将秒设置为0
        create_time = create_time.replace(second=0)
        movie["日期"] = create_time.int_timestamp
        movie["豆瓣链接"] = subject.get("url")
        movie["状态"] = movie_status.get(result.get("status"))
        if result.get("rating"):
            movie["评分"] = rating.get(result.get("rating").get("value"))
        if result.get("comment"):
            movie["短评"] = result.get("comment")
        item_key = _notion_item_key(movie.get("豆瓣链接"), movie.get("电影名"))
        if item_key and notion_movie_dict.get(item_key):
            notion_movive = notion_movie_dict.get(item_key)
            if (
                notion_movive.get("日期") != movie.get("日期")
                or notion_movive.get("短评") != movie.get("短评")
                or notion_movive.get("状态") != movie.get("状态")
                or notion_movive.get("评分") != movie.get("评分")
                or not notion_movive.get("演员")
                or not notion_movive.get("IMDB")
            ):
                if not notion_movive.get("演员") and subject.get("actors"):
                    l = []
                    actors = subject.get("actors")[0:5]
                    for actor in actors:
                        if actor.get("name"):
                            if "/" in actor.get("name"):
                                l.extend(actor.get("name").split("/"))
                            else:
                                l.append(actor.get("name"))  
                    movie["演员"] = [
                        notion_helper.get_relation_id(
                            x.get("name"), notion_helper.actor_database_id, USER_ICON_URL
                        )
                        for x in actors
                    ]
                if not notion_movive.get("IMDB"):
                    movie["IMDB"] = get_imdb(movie.get("豆瓣链接"))
                properties = utils.get_properties(movie, movie_properties_type_dict)
                print(movie.get("电影名"))
                notion_helper.get_date_relation(properties,create_time)
                notion_helper.update_page(
                    page_id=notion_movive.get("page_id"),
                    properties=properties
            )

        else:
            print(f"插入{movie.get('电影名')}")
            cover = subject.get("pic").get("normal")
            if not cover.endswith('.webp'):
                cover = cover.rsplit('.', 1)[0] + '.webp'
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
                l = []
                actors = subject.get("actors")[0:5]
                for actor in actors:
                    if actor.get("name"):
                        if "/" in actor.get("name"):
                            l.extend(actor.get("name").split("/"))
                        else:
                            l.append(actor.get("name"))  
                movie["演员"] = [
                    notion_helper.get_relation_id(
                        x.get("name"), notion_helper.actor_database_id, USER_ICON_URL
                    )
                    for x in actors
                ]
            if subject.get("directors"):
                movie["导演"] = [
                    notion_helper.get_relation_id(
                        x.get("name"), notion_helper.director_database_id, USER_ICON_URL
                    )
                    for x in subject.get("directors")[0:5]
                ]
            properties = utils.get_properties(movie, movie_properties_type_dict)
            notion_helper.get_date_relation(properties,create_time)
            parent = {
                "database_id": notion_helper.movie_database_id,
                "type": "database_id",
            }
            notion_helper.create_page(
                parent=parent, properties=properties, icon=get_icon(cover)
            )
def get_imdb(link):
    if not link:
        return None
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36'}
    try:
        response = requests.get(link, headers=headers, timeout=DOUBAN_REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        # IMDb is optional enrichment; anti-bot responses must not discard the sync.
        return None
    soup = BeautifulSoup(response.content, features="lxml")
    info = soup.find(id='info')
    if info:
        for span in info.find_all('span', {'class': 'pl'}):
            if ('IMDb:' == span.string and span.next_sibling):
                return span.next_sibling.string.strip()
    return None

def insert_book(douban_name,notion_helper):
    notion_books = notion_helper.query_all(database_id=notion_helper.book_database_id)
    notion_book_dict = {}
    for i in notion_books:
        book = {}
        for key, value in i.get("properties").items():
            book[key] = utils.get_property_value(value)
        item_key = _notion_item_key(book.get("豆瓣链接"), book.get("书名"))
        if item_key:
            notion_book_dict[item_key] = {
                "短评": book.get("短评"),
                "状态": book.get("状态"),
                "日期": book.get("日期"),
                "评分": book.get("评分"),
                "封面": book.get("封面"),
                "page_id": i.get("id"),
            }
        print(i)
    print(f"notion {len(notion_book_dict)}")
    results = []
    for i in book_status.keys():
        results.extend(fetch_subjects(douban_name, "book", i))
    for result in results:
        book = {}
        if not result:
            continue
        subject = result.get("subject")
        book["书名"] = subject.get("title")
        create_time = result.get("create_time")
        create_time = pendulum.parse(create_time,tz=utils.tz)
        #时间上传到Notion会丢掉秒的信息，这里直接将秒设置为0
        create_time = create_time.replace(second=0)
        book["日期"] = create_time.int_timestamp
        book["豆瓣链接"] = subject.get("url")
        book["状态"] = book_status.get(result.get("status"))
        cover = subject.get("pic").get("large")
        if not cover.endswith('.webp'):
            cover = cover.rsplit('.', 1)[0] + '.webp'
        book["封面"] = cover
        if result.get("rating"):
            book["评分"] = rating.get(result.get("rating").get("value"))
        if result.get("comment"):
            book["短评"] = result.get("comment")
        item_key = _notion_item_key(book.get("豆瓣链接"), book.get("书名"))
        if item_key and notion_book_dict.get(item_key):
            notion_movive = notion_book_dict.get(item_key)
            if (
                notion_movive.get("封面") is None
                or notion_movive.get("封面") != book.get("封面")
                or notion_movive.get("日期") != book.get("日期")
                or notion_movive.get("短评") != book.get("短评")
                or notion_movive.get("状态") != book.get("状态")
                or notion_movive.get("评分") != book.get("评分")
            ):
                print(f"更新{book.get('书名')}")
                properties = utils.get_properties(book, book_properties_type_dict)
                notion_helper.get_date_relation(properties,create_time)
                notion_helper.update_page(
                    page_id=notion_movive.get("page_id"),
                    properties=properties
            )

        else:
            print(f"插入{book.get('书名')}")
            book["简介"] = subject.get("intro")
            press = []
            for i in subject.get("press"):
                press.extend(i.split(","))
            book["出版社"] = press
            book["类型"] = subject.get("type")
            if result.get("tags"):
                book["分类"] = [
                    notion_helper.get_relation_id(
                        x, notion_helper.category_database_id, TAG_ICON_URL
                    )
                    for x in result.get("tags")
                ]
            if subject.get("author"):
                book["作者"] = [
                    notion_helper.get_relation_id(
                        x, notion_helper.author_database_id, USER_ICON_URL
                    )
                    for x in subject.get("author")[0:100]
                ]
            properties = utils.get_properties(book, book_properties_type_dict)
            notion_helper.get_date_relation(properties,create_time)
            parent = {
                "database_id": notion_helper.book_database_id,
                "type": "database_id",
            }
            notion_helper.create_page(
                parent=parent, properties=properties, icon=get_icon(cover)
            )

     
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("type")
    options = parser.parse_args()
    type = options.type
    notion_helper = NotionHelper(type)
    is_movie = True if type=="movie" else False
    douban_name = os.getenv("DOUBAN_NAME", None)
    if is_movie:
        insert_movie(douban_name,notion_helper)
    else:
        insert_book(douban_name,notion_helper)
if __name__ == "__main__":
    main()
