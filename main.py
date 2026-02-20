import feedparser
import requests
import time
import os
from flask import Flask, request
from datetime import datetime
import threading
import json

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

def send_telegram(text, chat_id=None, reply_markup=None):
    """Отправляет сообщение в Telegram"""
    if chat_id is None:
        chat_id = CHAT_ID
        
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

def get_main_keyboard():
    """Постоянная клавиатура с командами"""
    return {
        "keyboard": [
            [
                {"text": "📊 Статус"},
                {"text": "🔍 Проверить"}
            ],
            [
                {"text": "❓ Помощь"},
                {"text": "⚙️ Настройки"}
            ]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def get_game_buttons(link):
    """Inline кнопки для сообщения с игрой"""
    return {
        "inline_keyboard": [
            [
                {"text": "🎁 Забрать игру", "url": link}
            ],
            [
                {"text": "🔍 Найти отзывы", "url": f"https://www.google.com/search?q={link}+reviews"},
                {"text": "📊 SteamDB", "url": f"https://steamdb.info/search/?a=app&q={link}"}
            ]
        ]
    }

def handle_command(text, chat_id):
    """Обрабатывает команды и кнопки"""
    
    # Команда /start или кнопка "Старт"
    if text == '/start' or text == '🏠 Главная':
        send_telegram("""
🎮 <b>Бот раздач игр активен!</b>

<b>Что я умею:</b>
🔍 Мониторю Reddit каждые 5 минут
🎁 Нахожу бесплатные игры
📱 Присылаю уведомления с кнопками!

<b>Используйте кнопки ниже для управления ⬇️</b>
        """, chat_id, get_main_keyboard())
    
    # Команда /status или кнопка "📊 Статус"
    elif text == '/status' or text == '📊 Статус':
        uptime = datetime.now() - stats['started_at']
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        
        last_check = stats['last_check'] or "Еще не было"
        
        # Inline кнопки для статуса
        status_buttons = {
            "inline_keyboard": [
                [
                    {"text": "🔄 Обновить", "callback_data": "refresh_status"}
                ],
                [
                    {"text": "📈 Полная статистика", "callback_data": "full_stats"}
                ]
            ]
        }
        
        send_telegram(f"""
📊 <b>СТАТУС БОТА</b>

✅ Работает: <b>{hours}ч {minutes}м</b>
🔍 Проверок: <b>{stats['total_checks']}</b>
🎮 Игр найдено: <b>{stats['games_found']}</b>
💾 Постов в памяти: <b>{len(seen_items)}</b>

⏰ Последняя проверка: <code>{last_check}</code>

📡 Мониторю Reddit каждые 5 минут
        """, chat_id, status_buttons)
    
    # Команда /test или кнопка "🔍 Проверить"
    elif text == '/test' or text == '🔍 Проверить':
        # Кнопки для проверки
        test_buttons = {
            "inline_keyboard": [
                [
                    {"text": "⏳ Проверка...", "callback_data": "checking"}
                ]
            ]
        }
        
        send_telegram("🔍 <b>Запускаю проверку Reddit...</b>", chat_id, test_buttons)
        
        found = check_games()
        
        if found > 0:
            send_telegram(f"✅ <b>Найдено новых игр: {found}</b>\n\nСмотрите выше ⬆️", chat_id)
        else:
            result_buttons = {
                "inline_keyboard": [
                    [
                        {"text": "🔄 Проверить еще раз", "callback_data": "test_again"}
                    ]
                ]
            }
            send_telegram("ℹ️ Новых раздач пока нет\n\n<i>Попробуйте через 10-15 минут</i>", chat_id, result_buttons)
    
    # Команда /help или кнопка "❓ Помощь"
    elif text == '/help' or text == '❓ Помощь':
        help_buttons = {
            "inline_keyboard": [
                [
                    {"text": "💬 Написать разработчику", "url": "https://t.me/your_username"}
                ],
                [
                    {"text": "⭐ Оценить бота", "url": "https://t.me/your_bot?start=rate"}
                ]
            ]
        }
        
        send_telegram("""
❓ <b>ПОМОЩЬ</b>

<b>Команды:</b>
📊 Статус - Узнать статус бота
🔍 Проверить - Проверить новые раздачи
⚙️ Настройки - Настроить уведомления

<b>Как работает:</b>
🔍 Каждые 5 минут бот проверяет Reddit
🎮 Находит бесплатные игры
📱 Присылает уведомления с кнопками
🎁 Нажимаете "Забрать" - переходите на раздачу

<b>Источники:</b>
• r/FreeGamesOnSteam
• r/FreeGameFindings  
• r/freegames

<b>Платформы:</b>
🎮 Steam, Epic Games, GOG, Xbox
        """, chat_id, help_buttons)
    
    # Кнопка "⚙️ Настройки"
    elif text == '⚙️ Настройки':
        settings_buttons = {
            "inline_keyboard": [
                [
                    {"text": "🔔 Уведомления: ВКЛ", "callback_data": "toggle_notifications"}
                ],
                [
                    {"text": "🎮 Только Steam", "callback_data": "filter_steam"},
                    {"text": "🎁 Все платформы", "callback_data": "filter_all"}
                ],
                [
                    {"text": "💰 Мин. цена: $0", "callback_data": "set_min_price"}
                ]
            ]
        }
        
        send_telegram("""
⚙️ <b>НАСТРОЙКИ</b>

<b>Уведомления:</b> ✅ Включены

<b>Фильтры:</b>
🎮 Платформы: Все
💰 Мин. цена: $0 (все раздачи)

<i>Используйте кнопки для настройки ⬇️</i>
        """, chat_id, settings_buttons)

def handle_callback(callback_query):
    """Обрабатывает нажатия на inline кнопки"""
    callback_id = callback_query['id']
    data = callback_query.get('data', '')
    chat_id = callback_query['message']['chat']['id']
    message_id = callback_query['message']['message_id']
    
    # Отправляем уведомление о нажатии
    answer_url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    
    if data == "refresh_status":
        requests.post(answer_url, json={"callback_query_id": callback_id, "text": "🔄 Обновляю..."})
        handle_command('/status', chat_id)
    
    elif data == "test_again":
        requests.post(answer_url, json={"callback_query_id": callback_id, "text": "🔍 Проверяю..."})
        handle_command('/test', chat_id)
    
    elif data == "full_stats":
        requests.post(answer_url, json={"callback_query_id": callback_id, "text": "📊 Показываю статистику..."})
        
        uptime = datetime.now() - stats['started_at']
        days = int(uptime.total_seconds() // 86400)
        hours = int((uptime.total_seconds() % 86400) // 3600)
        
        send_telegram(f"""
📈 <b>ПОЛНАЯ СТАТИСТИКА</b>

⏰ <b>Работает:</b> {days} дн. {hours} ч.
🔍 <b>Всего проверок:</b> {stats['total_checks']}
🎮 <b>Игр найдено:</b> {stats['games_found']}
💾 <b>Постов в памяти:</b> {len(seen_items)}

📊 <b>Средняя частота:</b>
• Проверок в час: {stats['total_checks'] / max(1, hours)}
• Игр в день: {stats['games_found'] * 24 / max(1, hours)}

🎯 <b>Эффективность:</b>
• Игр на проверку: {stats['games_found'] / max(1, stats['total_checks'])}
        """, chat_id)
    
    else:
        requests.post(answer_url, json={"callback_query_id": callback_id, "text": "⚠️ В разработке..."})

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
                
                # Определяем платформу
                platform = "🎮"
                if 'steam' in link.lower():
                    platform = "🎮 Steam"
                elif 'epicgames' in link.lower():
                    platform = "🎁 Epic Games"
                elif 'gog.com' in link.lower():
                    platform = "🎁 GOG"
                elif 'xbox' in link.lower():
                    platform = "🎮 Xbox"
                
                message = f"""
🎮 <b>БЕСПЛАТНАЯ ИГРА!</b>

🎁 <b>{title}</b>

📦 Платформа: {platform}

🔗 {link}

⏰ <i>Успей забрать бесплатно!</i>
                """
                
                # Кнопки для игры
                game_buttons = get_game_buttons(link)
                
                if send_telegram(message, reply_markup=game_buttons):
                    new_items_count += 1
                    stats['games_found'] += 1
                    print(f"✅ [ИГРА] {title[:50]}...")
                    time.sleep(2)
                    
        except Exception as e:
            print(f"Ошибка {rss_url}: {e}")
    
    return new_items_count

# ========================================
# FLASK + WEBHOOK
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

@app.route('/webhook', methods=['POST'])
def webhook():
    """Принимает сообщения от Telegram через webhook"""
    try:
        update = request.get_json()
        
        # Обработка callback (нажатия на кнопки)
        if 'callback_query' in update:
            handle_callback(update['callback_query'])
            return {"ok": True}
        
        # Обработка сообщений
        if 'message' in update:
            message = update['message']
            text = message.get('text', '')
            chat_id = message['chat']['id']
            
            # Проверяем что это наш чат
            if str(chat_id) == str(CHAT_ID):
                handle_command(text, chat_id)
        
        return {"ok": True}
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
        return {"ok": False}, 500

# ========================================
# НАСТРОЙКА WEBHOOK
# ========================================

def setup_webhook():
    """Устанавливает webhook для бота"""
    time.sleep(10)
    
    webhook_url = f"https://botiphone.onrender.com/webhook"
    api_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    
    try:
        response = requests.post(api_url, json={"url": webhook_url})
        if response.status_code == 200:
            print(f"✅ Webhook установлен: {webhook_url}")
        else:
            print(f"⚠️ Ошибка webhook: {response.text}")
    except Exception as e:
        print(f"❌ Ошибка установки webhook: {e}")

# ========================================
# ЗАПУСК БОТА
# ========================================

print("=" * 50)
print("🎮 БОТ С КНОПКАМИ ЗАПУСКАЕТСЯ...")
print("=" * 50)

# Загружаем существующие посты
print("📥 Загружаю существующие посты...")
for category, urls in RSS_SOURCES.items():
    for rss_url in urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                seen_items.add(entry.link)
            print(f"✅ Загружено: {len(feed.entries)} постов")
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")

print(f"✅ Всего загружено {len(seen_items)} постов")
print("=" * 50)

# ========================================
# ОСНОВНОЙ ЦИКЛ
# ========================================

def run_bot():
    """Основной цикл проверки"""
    time.sleep(15)
    
    while True:
        try:
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
    # Запускаем установку webhook
    webhook_thread = threading.Thread(target=setup_webhook, daemon=True)
    webhook_thread.start()
    
    # Запускаем бота
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
