import feedparser
import requests
import time
import os
from flask import Flask

# ========================================
# НАСТРОЙКИ БОТА
# ========================================
TOKEN = os.environ.get('TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# RSS источники бесплатных игр
RSS_URLS = [
    "https://www.reddit.com/r/FreeGamesOnSteam/.rss",
    "https://www.reddit.com/r/FreeGameFindings/.rss",
    "https://www.reddit.com/r/freegames/.rss"
]

seen_items = set()

# ========================================
# ФУНКЦИИ БОТА
# ========================================

def send_telegram(text):
    """Отправляет сообщение в Telegram"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID, 
        "text": text, 
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            return True
        else:
            print(f"Ошибка отправки: {response.status_code}")
            return False
    except Exception as e:
        print(f"Ошибка: {e}")
        return False

def check_rss():
    """Проверяет новые раздачи игр"""
    new_items_count = 0
    
    for rss_url in RSS_URLS:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:3]:  # Берем только 3 последних
                item_id = entry.link
                
                if item_id in seen_items:
                    continue
                    
                seen_items.add(item_id)
                
                # Фильтруем только посты с FREE или бесплатно
                title = entry.title
                if not any(word in title.lower() for word in ['free', 'бесплатно', 'раздача', 'халява', '100%']):
                    continue
                
                link = entry.link
                
                message = f"""
🎮 <b>БЕСПЛАТНАЯ ИГРА!</b>

🎁 {title}

🔗 {link}

⏰ <i>Успей забрать бесплатно!</i>
                """
                
                if send_telegram(message):
                    new_items_count += 1
                    print(f"✅ Отправлено: {title[:50]}...")
                    time.sleep(2)  # Пауза между сообщениями
                    
        except Exception as e:
            print(f"Ошибка парсинга {rss_url}: {e}")
    
    return new_items_count

# ========================================
# ЗАПУСК БОТА
# ========================================

print("=" * 50)
print("🎮 БОТ РАЗДАЧ ИГР ЗАПУСКАЕТСЯ...")
print("=" * 50)

# Первый запуск - запоминаем существующие посты
print("📥 Загружаю существующие раздачи...")
for rss_url in RSS_URLS:
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            seen_items.add(entry.link)
        print(f"✅ Загружено из {rss_url.split('/')[4]}: {len(feed.entries)} постов")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки {rss_url}: {e}")

print(f"✅ Всего загружено {len(seen_items)} постов")
print("👀 Начинаю мониторинг новых раздач...")
print("=" * 50)

# Отправляем уведомление о запуске
send_telegram("🎮 <b>Бот раздач игр запущен!</b>\n\n✅ Мониторю Reddit\n⏰ Проверка каждые 5 минут\n🎁 Буду присылать только бесплатные игры!")

# ========================================
# FLASK ДЛЯ RENDER (чтобы не засыпал)
# ========================================

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <html>
        <body style="background: #1a1a2e; color: #eee; font-family: Arial; text-align: center; padding: 50px;">
            <h1>🎮 Бот раздач игр работает!</h1>
            <p>Проверок выполнено: """ + str(len(seen_items)) + """</p>
            <p>Статус: ✅ Онлайн</p>
        </body>
    </html>
    """

@app.route('/health')
def health():
    return {"status": "ok", "items": len(seen_items)}

# ========================================
# ОСНОВНОЙ ЦИКЛ
# ========================================

def run_bot():
    """Основной цикл проверки раздач"""
    while True:
        try:
            current_time = time.strftime('%H:%M:%S')
            print(f"\n🔍 Проверяю новые раздачи... [{current_time}]")
            
            new_count = check_rss()
            
            if new_count > 0:
                print(f"✅ Найдено и отправлено новых раздач: {new_count}")
            else:
                print("ℹ️ Новых раздач не найдено")
            
            print(f"💤 Следующая проверка через 5 минут...")
            time.sleep(300)  # 5 минут
            
        except Exception as e:
            print(f"❌ Ошибка в основном цикле: {e}")
            time.sleep(60)  # При ошибке ждем 1 минуту

# ========================================
# ЗАПУСК В ПОТОКАХ
# ========================================

if __name__ == '__main__':
    import threading
    
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask для Render
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Flask запущен на порту {port}")
    app.run(host='0.0.0.0', port=port)
