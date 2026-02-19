import feedparser
import requests
import time
import os

TOKEN = os.environ.get('TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

RSS_URL = "https://www.avito.ru/rossiya?q=iphone&pmax=25000&s=104&format=rss"

seen_items = set()

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Ошибка: {e}")

def check_rss():
    try:
        feed = feedparser.parse(RSS_URL)
        for entry in feed.entries[:5]:
            item_id = entry.link
            if item_id in seen_items:
                continue
            seen_items.add(item_id)
            title = entry.title
            link = entry.link
            message = f"""
🔥 НОВОЕ!

📱 {title}

🔗 {link}
            """
            send_telegram(message)
            print(f"✅ Отправлено: {title[:30]}...")
    except Exception as e:
        print(f"Ошибка: {e}")

print("🚀 Бот запускается...")
feed = feedparser.parse(RSS_URL)
for entry in feed.entries:
    seen_items.add(entry.link)
print(f"✅ Загружено {len(seen_items)} объявлений")

send_telegram("🤖 Бот запущен на Render!")

from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

if __name__ == '__main__':
    import threading
    def run_bot():
        while True:
            print(f"🔍 Проверяю... {time.strftime('%H:%M:%S')}")
            check_rss()
            time.sleep(300)
    
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
