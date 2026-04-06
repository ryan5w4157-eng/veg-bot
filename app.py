from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote
from difflib import get_close_matches

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

REMOVE_WORDS = [
    "多少", "價格", "多少錢", "多少元",
    "今天", "今日", "現在", "菜價", "水果價", "批發價", "零售價"
]

# 使用者常講的名字
DISPLAY_NAMES = [
    "高麗菜",
    "高麗",
    "捲心菜",
    "小白菜",
    "大白菜",
    "青江菜",
    "青江白菜",
    "花椰菜",
    "青花菜",
    "白花椰菜",
    "香蕉",
    "番茄",
    "牛番茄",
    "洋蔥",
    "胡蘿蔔",
    "紅蘿蔔",
    "地瓜",
    "馬鈴薯",
    "玉米",
    "芋頭",
    "菠菜",
    "空心菜",
    "茄子",
    "絲瓜",
    "苦瓜",
    "小黃瓜",
    "南瓜",
    "芹菜",
    "韭菜",
    "蔥",
    "蒜頭",
    "辣椒",
    "豆芽菜",
    "高麗菜苗"
]

# twfood / 搜尋用關鍵字映射
ALIASES = {
    "高麗菜": "甘藍",
    "高麗": "甘藍",
    "捲心菜": "甘藍",
    "小白菜": "小白菜",
    "大白菜": "白菜",
    "青江菜": "青江白菜",
    "青江白菜": "青江白菜",
    "青江": "青江白菜",
    "花椰菜": "花椰菜",
    "花椰": "花椰菜",
    "青花菜": "花椰菜",
    "白花椰菜": "花椰菜",
    "香蕉": "香蕉",
    "番茄": "番茄",
    "牛番茄": "番茄",
    "洋蔥": "洋蔥",
    "胡蘿蔔": "胡蘿蔔",
    "紅蘿蔔": "胡蘿蔔",
    "地瓜": "甘藷",
    "馬鈴薯": "馬鈴薯",
    "玉米": "玉米",
    "芋頭": "芋",
    "菠菜": "菠菜",
    "空心菜": "蕹菜",
    "茄子": "茄子",
    "絲瓜": "絲瓜",
    "苦瓜": "苦瓜",
    "小黃瓜": "胡瓜",
    "南瓜": "南瓜",
    "芹菜": "芹菜",
    "韭菜": "韭菜",
    "蔥": "蔥",
    "蒜頭": "蒜頭",
    "辣椒": "辣椒",
    "豆芽菜": "豆芽菜",
    "高麗菜苗": "甘藍"
}


def clean_keyword(text: str) -> str:
    keyword = text.strip()
    for w in REMOVE_WORDS:
        keyword = keyword.replace(w, "")
    return keyword.strip()


def suggest_keyword(keyword: str) -> str | None:
    # 先做簡單包含判斷
    for name in DISPLAY_NAMES:
        if keyword in name or name in keyword:
            return name

    # 再做模糊比對
    matches = get_close_matches(keyword, DISPLAY_NAMES, n=1, cutoff=0.4)
    if matches:
        return matches[0]

    return None


def normalize_keyword(keyword: str) -> str:
    if keyword in ALIASES:
        return ALIASES[keyword]

    suggestion = suggest_keyword(keyword)
    if suggestion and suggestion in ALIASES:
        return ALIASES[suggestion]

    return keyword


def find_detail_url(keyword: str) -> str | None:
    search_url = f"https://www.twfood.cc/?s={quote(keyword)}"

    try:
        r = requests.get(search_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()

        if "/vege/" in href or "/fruit/" in href:
            if href.startswith("/"):
                href = "https://www.twfood.cc" + href
            if href.startswith("https://www.twfood.cc") and href not in links:
                links.append(href)

    if not links:
        return None

    keyword_clean = keyword.replace(" ", "").lower()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).replace(" ", "").lower()

        if "/vege/" in href or "/fruit/" in href:
            full_href = href
            if href.startswith("/"):
                full_href = "https://www.twfood.cc" + href

            if keyword_clean in text or keyword_clean in full_href.lower():
                return full_href

    return links[0]


def parse_price_from_detail(detail_url: str, display_name: str) -> str:
    try:
        r = requests.get(detail_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return "目前無法連線到菜價網站，請稍後再試。"

    text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)

    wholesale_match = re.search(
        r"本週平均批發價:\s*([\d.]+)\s*\(元/公斤\)\s*([\d.]+)\s*\(元/台斤\)",
        text,
        re.S
    )

    retail_match = re.search(
        r"預估零售價:\s*([\d.]+)\s*\(元/公斤\)\s*([\d.]+)\s*\(元/台斤\)",
        text,
        re.S
    )

    if not wholesale_match and not retail_match:
        return f"查不到「{display_name}」價格"

    lines = [f"{display_name} 今日價格", ""]

    if wholesale_match:
        lines.append(
            f"批發價：{wholesale_match.group(1)} (元/公斤) {wholesale_match.group(2)} (元/台斤)"
        )

    if retail_match:
        lines.append(
            f"零售價：{retail_match.group(1)} (元/公斤) {retail_match.group(2)} (元/台斤)"
        )

    return "\n".join(lines)


def get_price(keyword: str) -> str:
    suggestion = suggest_keyword(keyword)

    # 使用者原字詞若沒有明確映射，先用建議詞
    display_name = suggestion if suggestion else keyword
    normalized = normalize_keyword(display_name)

    detail_url = find_detail_url(normalized)

    if not detail_url:
        if suggestion and suggestion != keyword:
            return f"查不到「{keyword}」價格，你要查的是「{suggestion}」嗎？"
        return f"查不到「{keyword}」價格"

    result = parse_price_from_detail(detail_url, display_name)

    # 如果詳情頁也抓不到價格，再提示推薦
    if result.startswith("查不到") and suggestion and suggestion != keyword:
        return f"查不到「{keyword}」價格，你要查的是「{suggestion}」嗎？"

    return result


@app.route("/")
def home():
    return "veg bot running"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    keyword = clean_keyword(text)

    if not keyword:
        reply = "請輸入蔬菜或水果名稱，例如：高麗菜、小白菜、青江菜、香蕉"
    else:
        reply = get_price(keyword)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run()
