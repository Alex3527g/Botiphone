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

# RSS источники
RSS_SOURCES = {
    'games': [
        "https://www.reddit.com/r/FreeGamesOnSteam/.rss",
        "https://www.reddit.com/r/FreeGameFindings/.rss",
        "https://www.reddit.com/r/freegames/.rss"
    ],
    'avito': [
        "https://www.avito.ru/rossiya?q=отдам+даром&s=104&format=rss",
        "https://www.avito.ru/moskva?q=бесплатно&s=104&format=rss"
    ]
}

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

def check_games():
    """Проверяет новые раздачи игр"""
    new_items_count = 0
    
    for rss_url in RSS_SOURCES['games']:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:3]:
                item_id = entry.link
                
                if item_id in seen_items:
                    continue
                    
                seen_items.add(item_id)
                
                title = entry.title
                if not any(word in title.lower() for word in ['free', 'бесплатно', 'раздача', '100%']):
                    continue
                
                link = entry.link
                
                message = f"""
🎮 <b>БЕСПЛАТНАЯ ИГРА!</b>

🎁 {title}

🔗 {link}

⏰ <i>Успей забрать!</i>
                """
                
                if send_telegram(message):
                    new_items_count += 1
                    print(f"✅ [ИГРА] {title[:50]}...")
                    time.sleep(2)
                    
        except Exception as e:
            print(f"Ошибка игр {rss_url}: {e}")
    
    return new_items_count

def check_avito():
    """Проверяет халяву на Авито"""
    new_items_count = 0
    
    for rss_url in RSS_SOURCES['avito']:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:5]:
                item_id = entry.link
                
                if item_id in seen_items:
                    continue
                    
                seen_items.add(item_id)
                
                title = entry.title
                link = entry.link
                
                # Извлекаем город если есть
                location = "Россия"
                if hasattr(entry, 'summary'):
                    summary = entry.summary
                    if 'Адрес:' in summary:
                        location = summary.split('Адрес:')[1].split('<')[0].strip()
                
                message = f"""
💎 <b>ХАЛЯВА АВИТО!</b>

🎁 {title}

📍 {location}

🔗 {link}

⏰ <i>Забирай бесплатно!</i>
                """
                
                if send_telegram(message):
                    new_items_count += 1
                    print(f"✅ [АВИТО] {title[:50]}...")
                    time.sleep(2)
                    
        except Exception as e:
            print(f"Ошибка Авито {rss_url}: {e}")
    
    return new_items_count

# ========================================
# ЗАПУСК БОТА
# ========================================

print("=" * 50)
print("🎮💎 БОТ ИГРЫ + АВИТО ЗАПУСКАЕТСЯ...")
print("=" * 50)

# Первый запуск - запоминаем существующие
print("📥 Загружаю существующие посты...")
for category, urls in RSS_SOURCES.items():
    for rss_url in urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                seen_items.add(entry.link)
            print(f"✅ [{category.upper()}] Загружено: {len(feed.entries)} постов")
        except Exception as e:
            print(f"⚠️ Ошибка {rss_url}: {e}")

print(f"✅ Всего загружено {len(seen_items)} постов")
print("=" * 50)

# Уведомление о запуске
send_telegram("""
🎮💎 <b>БОТ ЗАПУЩЕН!</b>

✅ <b>Мониторю:</b>
🎮 Reddit - бесплатные игры
💎 Авито - отдам даром

⏰ Проверка каждые 5 минут
🎁 Только лучшие находки!
""")

# ========================================
# FLASK ДЛЯ RENDER
# ========================================

app = Flask(__name__)

@app.route('/')
def home():
    return f"""
    <html>
        <body style="background: #1a1a2e; color: #eee; font-family: Arial; text-align: center; padding: 50px;">
            <h1>🎮💎 Бот игр + Авито работает!</h1>
            <p>Проверок: {len(seen_items)}</p>
            <p>Статус: ✅ Онлайн</p>
            <p>🎮 Игры + 💎 Авито</p>
        </body>
    </html>
    """

@app.route('/health')
def health():
    return {"status": "ok", "items": len(seen_items), "sources": ["games", "avito"]}

# ========================================
# ОСНОВНОЙ ЦИКЛ
# ========================================

def run_bot():
    """Основной цикл"""
    while True:
        try:
            current_time = time.strftime('%H:%M:%S')
            print(f"\n🔍 Проверяю находки... [{current_time}]")
            
            games = check_games()
            avito = check_avito()
            
            total = games + avito
            
            if total > 0:
                print(f"✅ Найдено: 🎮 {games} игр, 💎 {avito} халявы")
            else:
                print("ℹ️ Новых находок нет")
            
            print(f"💤 Следующая проверка через 5 минут...")
            time.sleep(300)
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(60)

# ========================================
# ЗАПУСК
# ========================================

if __name__ == '__main__':
    import threading
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
