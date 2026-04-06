from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re  # 匯入正則表達式套件，用來模糊比對文字

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


def get_price(keyword):
    # 1. 處理中文關鍵字網址編碼
    encoded_keyword = urllib.parse.quote(keyword)
    
    # 2. 構造 twfood 的搜尋網址 (利用網站本身的模糊搜尋)
    url = f"https://www.twfood.cc/search?q={encoded_keyword}"

    # 模擬真實瀏覽器
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        
        soup = BeautifulSoup(r.text, 'html.parser')

        # 嘗試抓取菜名 (如果抓不到就預設顯示使用者輸入的關鍵字)
        # 注意：'.title' 是預設猜測，若實際抓不到菜名可以改成真實的 class
        name_tag = soup.select_first('.title') 
        name = name_tag.text.strip() if name_tag else keyword

        # =========================================================
        # 升級版抓法：直接在網頁文字中尋找「批發價」與「預估零售價」
        # =========================================================
        wholesale_label = soup.find(string=re.compile("批發價"))
        retail_label = soup.find(string=re.compile("預估零售價"))

        # find_next() 的作用是：找到標籤文字後，抓取它旁邊緊接的下一個 HTML 標籤(通常就是價格數字)
        wholesale_price = wholesale_label.find_next().text.strip() if wholesale_label else "無資料"
        retail_price = retail_label.find_next().text.strip() if retail_label else "無資料"

        # 組合回覆訊息
        return f"""🥬 {name} 今日菜價

📦 批發價：{wholesale_price}
🛒 預估零售價：{retail_price}

資料來源：twfood.cc"""

    except Exception as e:
        print(f"爬蟲發生錯誤: {e}")
        return "查詢失敗，無法連線至資料來源或網頁結構未符合預期。"


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
