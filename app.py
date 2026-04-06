from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# 常見口語名稱 → twfood 較常見搜尋詞
ALIASES = {
    "高麗菜": "甘藍",
    "高麗": "甘藍",
    "捲心菜": "甘藍",
    "小白菜": "小白菜",
    "大白菜": "白菜",
    "青江菜": "青江白菜",
    "青江白菜": "青江白菜",
    "青花菜": "花椰菜",
    "綠花椰菜": "花椰菜",
    "白花椰菜": "花椰菜",
    "香蕉": "香蕉",
    "番茄": "番茄",
    "牛番茄": "番茄",
    "洋蔥": "洋蔥",
    "胡蘿蔔": "胡蘿蔔",
    "紅蘿蔔": "胡蘿蔔",
}

REMOVE_WORDS = [
    "多少", "價格", "多少錢", "多少元",
    "今天", "今日", "現在", "菜價", "水果價", "批發價", "零售價"
]


def clean_keyword(text: str) -> str:
    keyword = text.strip()
    for w in REMOVE_WORDS:
        keyword = keyword.replace(w, "")
    return keyword.strip()


def normalize_keyword(keyword: str) -> str:
    keyword = keyword.strip()
    return ALIASES.get(keyword, keyword)


def find_detail_url(keyword: str) -> str | None:
    """
    先到 twfood 搜尋頁，抓第一個蔬果詳情頁連結
    """
    search_url = f"https://www.twfood.cc/?s={quote(keyword)}"

    try:
        r = requests.get(search_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # 收集所有可能的詳情頁
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()

        # 只收 twfood 詳情頁
        if "/vege/" in href or "/fruit/" in href:
            if href.startswith("/"):
                href = "https://www.twfood.cc" + href
            if href.startswith("https://www.twfood.cc") and href not in links:
                links.append(href)

    if not links:
        return None

    # 優先找連結文字或網址裡有關鍵字的
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


def parse_price_from_detail(detail_url: str, original_keyword: str) -> str:
    try:
        r = requests.get(detail_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return "目前無法連線到菜價網站，請稍後再試。"

    text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)

    # 品名：抓詳情頁標題附近
    name_match = re.search(r"####\s*(.+?)\s*本週平均批發價", text, re.S)
    item_name = original_keyword
    if name_match:
        item_name = " ".join(name_match.group(1).split()).strip()

    # 批發價（抓 元/公斤 與 元/台斤）
    wholesale_match = re.search(
        r"本週平均批發價:\s*([\d.]+)\s*\(元/公斤\)\s*([\d.]+)\s*\(元/台斤\)",
        text,
        re.S
    )

    # 零售價（抓 元/公斤 與 元/台斤）
    retail_match = re.search(
        r"預估零售價:\s*([\d.]+)\s*\(元/公斤\)\s*([\d.]+)\s*\(元/台斤\)",
        text,
        re.S
    )

    if not wholesale_match and not retail_match:
        return f"查不到「{original_keyword}」價格"

    lines = [f"{item_name} 今日價格", ""]

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
    normalized = normalize_keyword(keyword)
    detail_url = find_detail_url(normalized)

    if not detail_url:
        return f"查不到「{keyword}」價格"

    return parse_price_from_detail(detail_url, keyword)


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
