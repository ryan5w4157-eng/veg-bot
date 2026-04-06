from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


def clean_keyword(text):
    remove_words = [
        "多少", "價格", "多少錢", "多少元",
        "今天", "今日", "現在", "菜價"
    ]
    keyword = text.strip()
    for w in remove_words:
        keyword = keyword.replace(w, "")
    return keyword.strip()


def get_price(keyword):
    url = f"https://www.twfood.cc/?s={keyword}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
    except Exception:
        return "目前無法連線到菜價網站，請稍後再試。"

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    pattern = r"本週平均批發價:\s*(.*?)\s+預估零售價:\s*(.*?)\s"
    match = re.search(pattern, text, re.S)

    if match:
        wholesale = match.group(1).strip()
        retail = match.group(2).strip()
        return f"{keyword} 今日價格\n\n批發價：{wholesale}\n零售價：{retail}"

    return f"查不到「{keyword}」價格"


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
        reply = "請輸入蔬菜或水果名稱，例如：高麗菜、番茄、香蕉"
    else:
        reply = get_price(keyword)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run()
