import feedparser
import requests
import time
import os
from flask import Flask
from datetime import datetime

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
    ]
}

seen_items = set()
stats = {
    'last_check': None,
    'games_found': 0,
    'total_checks': 0,
    'started_at': datetime.now()
}

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
        return response.status_code == 200
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

def get_updates():
    """Получает обновления от Telegram (для команд)"""
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get('result', [])
    except:
        pass
    return []

def handle_commands():
    """Обрабатывает команды от пользователя"""
    updates = get_updates()
    
    for update in updates:
        if 'message' in update:
            message = update['message']
            text = message.get('text', '')
            chat_id = message['chat']['id']
            
            # Проверяем что это наш чат
            if str(chat_id) != str(CHAT_ID):
                continue
            
            # Команда /start
            if text == '/start':
                send_telegram("""
🎮 <b>Бот раздач игр активен!</b>

<b>Доступные команды:</b>

/status - Статус бота
/test - Проверить прямо сейчас
/help - Помощь

⏰ Автопроверка каждые 5 минут
🎁 Присылаю только бесплатные игры!
                """)
            
            # Команда /status
            elif text == '/status':
                uptime = datetime.now() - stats['started_at']
                hours = int(uptime.total_seconds() // 3600)
                minutes = int((uptime.total_seconds() % 3600) // 60)
                
                last_check = stats['last_check'] or "Еще не было"
                
                send_telegram(f"""
📊 <b>СТАТУС БОТА</b>

✅ Работает: {hours}ч {minutes}м
🔍 Проверок выполнено: {stats['total_checks']}
🎮 Игр найдено: {stats['games_found']}
💾 Постов в памяти: {len(seen_items)}

⏰ Последняя проверка: {last_check}

📡 Мониторю Reddit каждые 5 минут
                """)
            
            # Команда /test
            elif text == '/test':
                send_telegram("🔍 Запускаю проверку...")
                found = check_games()
                if found > 0:
                    send_telegram(f"✅ Найдено новых игр: {found}")
                else:
                    send_telegram("ℹ️ Новых раздач пока нет")
            
            # Команда /help
            elif text == '/help':
                send_telegram("""
❓ <b>ПОМОЩЬ</b>

<b>Команды:</b>
/status - Узнать статус бота
/test - Проверить новые раздачи
/start - Главное меню

<b>Как работает:</b>
🔍 Каждые 5 минут бот проверяет Reddit
🎮 Находит бесплатные игры
📱 Присылает вам уведомление

<b>Источники:</b>
• r/FreeGamesOnSteam
• r/FreeGameFindings  
• r/freegames
                """)

def check_games():
    """Проверяет новые раздачи игр"""
    new_items_count = 0
    
    for rss_url in RSS_SOURCES['games']:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:5]:
                item_id = entry.link
                
                if item_id in seen_items:
                    continue
                    
                seen_items.add(item_id)
                
                title = entry.title
                
                # Фильтр на бесплатные игры
                if not any(word in title.lower() for word in ['free', 'бесплатно', 'раздача', '100%', 'giveaway']):
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
                    stats['games_found'] += 1
                    print(f"✅ [ИГРА] {title[:50]}...")
                    time.sleep(2)
                    
        except Exception as e:
            print(f"Ошибка {rss_url}: {e}")
    
    return new_items_count

# ========================================
# FLASK ДЛЯ RENDER
# ========================================

app = Flask(__name__)

@app.route('/')
def home():
    uptime = datetime.now() - stats['started_at']
    hours = int(uptime.total_seconds() // 3600)
    
    return f"""
    <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: #fff;
                    font-family: 'Segoe UI', Arial;
                    text-align: center;
                    padding: 50px;
                    margin: 0;
                }}
                .container {{
                    background: rgba(255,255,255,0.1);
                    padding: 40px;
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                    max-width: 600px;
                    margin: 0 auto;
                }}
                h1 {{ font-size: 48px; margin: 0 0 20px 0; }}
                .status {{ font-size: 24px; margin: 20px 0; }}
                .stats {{ 
                    display: grid; 
                    grid-template-columns: 1fr 1fr; 
                    gap: 20px; 
                    margin-top: 30px;
                }}
                .stat {{
                    background: rgba(255,255,255,0.2);
                    padding: 20px;
                    border-radius: 15px;
                }}
                .stat-value {{ font-size: 32px; font-weight: bold; }}
                .stat-label {{ font-size: 14px; opacity: 0.8; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎮 Free Games Bot</h1>
                <div class="status">✅ Онлайн и работает!</div>
                
                <div class="stats">
                    <div class="stat">
                        <div class="stat-value">{hours}ч</div>
                        <div class="stat-label">Работает</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{stats['total_checks']}</div>
                        <div class="stat-label">Проверок</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{stats['games_found']}</div>
                        <div class="stat-label">Игр найдено</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{len(seen_items)}</div>
                        <div class="stat-label">В памяти</div>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """

@app.route('/health')
def health():
    return {
        "status": "ok", 
        "items": len(seen_items),
        "games_found": stats['games_found'],
        "checks": stats['total_checks']
    }

# ========================================
# ЗАПУСК БОТА
# ========================================

print("=" * 50)
print("🎮 БОТ ЗАПУСКАЕТСЯ (БЕЗ УВЕДОМЛЕНИЙ)...")
print("=" * 50)

# Первый запуск - загружаем существующие посты
print("📥 Загружаю существующие посты...")
for category, urls in RSS_SOURCES.items():
    for rss_url in urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                seen_items.add(entry.link)
            print(f"✅ Загружено: {len(feed.entries)} постов")
        except Exception as e:
            print(f"⚠️ Ошибка {rss_url}: {e}")

print(f"✅ Всего загружено {len(seen_items)} постов")
print("=" * 50)

# БЕЗ АВТОМАТИЧЕСКОГО СООБЩЕНИЯ "БОТ ЗАПУЩЕН"!
# Только команды /start, /status, /test работают!

# ========================================
# ОСНОВНОЙ ЦИКЛ
# ========================================

def run_bot():
    """Основной цикл"""
    # Небольшая задержка чтобы Flask запустился
    time.sleep(5)
    
    while True:
        try:
            # Проверяем команды
            handle_commands()
            
            # Проверяем игры
            current_time = time.strftime('%H:%M:%S')
            print(f"\n🔍 Проверяю Reddit... [{current_time}]")
            
            found = check_games()
            stats['total_checks'] += 1
            stats['last_check'] = current_time
            
            if found > 0:
                print(f"✅ Найдено игр: {found}")
            else:
                print("ℹ️ Новых раздач нет")
            
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
    
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
