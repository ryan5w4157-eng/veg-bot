from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import requests

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


def get_price(keyword):

    url = "https://data.moa.gov.tw/api/v1/AgricultureProductsTransType/"

    params = {
        "CropName": keyword,
        "Top": 1
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
    except:
        return "查詢失敗"

    if "Data" not in data or len(data["Data"]) == 0:
        return f"查不到「{keyword}」價格"

    item = data["Data"][0]

    name = item.get("CropName", keyword)
    price = item.get("AvgPrice", "無資料")

    return f"""{name} 今日批發價

平均價：{price} 元/kg
資料來源：農產品交易行情"""


@app.route("/")
def home():
    return "veg bot running"


@app.route("/callback", methods=["POST"])
def callback():

    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):

    text = event.message.text.strip()

    reply = get_price(text)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run()
