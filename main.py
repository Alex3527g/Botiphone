import feedparser
import requests
import time
import os
from flask import Flask, request
from datetime import datetime
import threading
import json
from bs4 import BeautifulSoup

# ========================================
# НАСТРОЙКИ БОТА
# ========================================
TOKEN = os.environ.get('TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

# Файл для хранения истории
HISTORY_FILE = 'seen_items.json'

# ========================================
# ФУНКЦИИ СОХРАНЕНИЯ/ЗАГРУЗКИ
# ========================================

def load_history():
    """Загружает историю из файла"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📥 Загружено из истории: {len(data)} постов")
                return set(data)
    except Exception as e:
        print(f"⚠️ Ошибка загрузки истории: {e}")
    return set()

def save_history():
    """Сохраняет историю в файл"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(seen_items), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения: {e}")

# ========================================
# ВСЕ ИСТОЧНИКИ
# ========================================

RSS_SOURCES = {
    # Reddit
    'reddit': [
        "https://www.reddit.com/r/FreeGamesOnSteam/.rss",
        "https://www.reddit.com/r/FreeGameFindings/.rss",
        "https://www.reddit.com/r/freegames/.rss",
        "https://www.reddit.com/r/GameDeals/.rss"
    ],
    
    # Dealabs (Европа)
    'dealabs': [
        "https://www.dealabs.com/rss/all/gaming",
    ],
    
    # Slickdeals (США)
    'slickdeals': [
        "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1&filter[]=gaming",
    ],
}

# Прямые ссылки
DIRECT_SOURCES = {
    'steamdb': 'https://steamdb.info/upcoming/free/',
    'epic': 'https://store.epicgames.com/en-US/free-games',
}

# Загружаем историю при старте
seen_items = load_history()

stats = {
    'last_check': None,
    'games_found': 0,
    'total_checks': 0,
    'started_at': datetime.now(),
    'sources': {
        'reddit': 0,
        'steamdb': 0,
        'epic': 0,
        'other': 0
    }
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
    """Постоянная клавиатура"""
    return {
        "keyboard": [
            [
                {"text": "📊 Статус"},
                {"text": "🔍 Проверить"}
            ],
            [
                {"text": "📈 Источники"},
                {"text": "🗑️ Очистить"}
            ]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def get_game_buttons(link, source=''):
    """Inline кнопки для игры"""
    buttons = [
        [{"text": "🎁 Забрать игру", "url": link}]
    ]
    
    if 'steam' in link.lower():
        buttons.append([
            {"text": "📊 SteamDB", "url": f"https://steamdb.info/search/?a=app&q={link}"}
        ])
    elif 'epicgames' in link.lower():
        buttons.append([
            {"text": "📊 Epic Store", "url": "https://www.epicgames.com/store/free-games"}
        ])
    
    return {"inline_keyboard": buttons}

# ========================================
# ПАРСЕРЫ ИСТОЧНИКОВ
# ========================================

def check_reddit():
    """Проверяет Reddit RSS"""
    new_items = 0
    
    for rss_url in RSS_SOURCES['reddit']:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:5]:
                item_id = entry.link
                
                if item_id in seen_items:
                    continue
                    
                title = entry.title
                
                # Фильтр
                keywords = ['free', 'бесплатно', '100%', 'giveaway', 'раздача', 'freebie']
                if not any(word in title.lower() for word in keywords):
                    continue
                
                seen_items.add(item_id)
                save_history()  # Сохраняем сразу!
                
                link = entry.link
                
                message = f"""
🎮 <b>БЕСПЛАТНАЯ ИГРА!</b>

🎁 <b>{title}</b>

📦 Источник: Reddit
🔗 {link}

⏰ <i>Успей забрать!</i>
                """
                
                if send_telegram(message, reply_markup=get_game_buttons(link, 'reddit')):
                    new_items += 1
                    stats['games_found'] += 1
                    stats['sources']['reddit'] += 1
                    print(f"✅ [REDDIT] {title[:50]}...")
                    time.sleep(2)
                    
        except Exception as e:
            print(f"❌ Ошибка Reddit: {e}")
    
    return new_items

def check_steamdb():
    """Проверяет SteamDB (парсинг HTML)"""
    new_items = 0
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(DIRECT_SOURCES['steamdb'], headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            packages = soup.find_all('tr', limit=10)
            
            for package in packages:
                try:
                    link_tag = package.find('a')
                    if not link_tag:
                        continue
                    
                    title = link_tag.text.strip()
                    link = f"https://steamdb.info{link_tag['href']}"
                    
                    item_id = link
                    
                    if item_id in seen_items:
                        continue
                    
                    seen_items.add(item_id)
                    save_history()  # Сохраняем!
                    
                    message = f"""
🎮 <b>STEAM РАЗДАЧА!</b>

🎁 <b>{title}</b>

📦 Источник: SteamDB
🔗 {link}

⏰ <i>Бесплатный пакет Steam!</i>
                    """
                    
                    if send_telegram(message, reply_markup=get_game_buttons(link, 'steamdb')):
                        new_items += 1
                        stats['games_found'] += 1
                        stats['sources']['steamdb'] += 1
                        print(f"✅ [STEAMDB] {title[:50]}...")
                        time.sleep(2)
                        
                except Exception as e:
                    continue
                    
    except Exception as e:
        print(f"❌ Ошибка SteamDB: {e}")
    
    return new_items

def check_epic_games():
    """Проверяет раздачи Epic Games"""
    new_items = 0
    
    try:
        api_url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            games = data.get('data', {}).get('Catalog', {}).get('searchStore', {}).get('elements', [])
            
            for game in games:
                try:
                    promotions = game.get('promotions')
                    if not promotions:
                        continue
                    
                    title = game.get('title', 'Unknown Game')
                    description = game.get('description', '')
                    
                    item_id = f"epic_{title}"
                    
                    if item_id in seen_items:
                        continue
                    
                    seen_items.add(item_id)
                    save_history()  # Сохраняем!
                    
                    product_slug = game.get('productSlug', game.get('catalogNs', {}).get('mappings', [{}])[0].get('pageSlug', ''))
                    link = f"https://store.epicgames.com/en-US/p/{product_slug}"
                    
                    message = f"""
🎁 <b>EPIC GAMES РАЗДАЧА!</b>

🎮 <b>{title}</b>

📝 {description[:200]}...

📦 Источник: Epic Games Store
🔗 {link}

⏰ <i>Бесплатно на этой неделе!</i>
                    """
                    
                    if send_telegram(message, reply_markup=get_game_buttons(link, 'epic')):
                        new_items += 1
                        stats['games_found'] += 1
                        stats['sources']['epic'] += 1
                        print(f"✅ [EPIC] {title[:50]}...")
                        time.sleep(2)
                        
                except Exception as e:
                    continue
                    
    except Exception as e:
        print(f"❌ Ошибка Epic: {e}")
    
    return new_items

def check_dealabs():
    """Проверяет Dealabs (Европа)"""
    new_items = 0
    
    for rss_url in RSS_SOURCES['dealabs']:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:5]:
                item_id = entry.link
                
                if item_id in seen_items:
                    continue
                
                title = entry.title
                
                if 'gratuit' in title.lower() or 'free' in title.lower() or '0€' in title or '0$' in title:
                    seen_items.add(item_id)
                    save_history()  # Сохраняем!
                    
                    link = entry.link
                    
                    message = f"""
💎 <b>ЕВРОПЕЙСКАЯ РАЗДАЧА!</b>

🎁 <b>{title}</b>

📦 Источник: Dealabs
🔗 {link}

⏰ <i>Только для Европы!</i>
                    """
                    
                    if send_telegram(message, reply_markup=get_game_buttons(link, 'dealabs')):
                        new_items += 1
                        stats['games_found'] += 1
                        stats['sources']['other'] += 1
                        print(f"✅ [DEALABS] {title[:50]}...")
                        time.sleep(2)
                        
        except Exception as e:
            print(f"❌ Ошибка Dealabs: {e}")
    
    return new_items

def check_all_sources():
    """Проверяет ВСЕ источники"""
    total_found = 0
    
    print("\n" + "="*50)
    print("🔍 ПРОВЕРЯЮ ВСЕ ИСТОЧНИКИ...")
    print("="*50)
    
    # Reddit
    print("📱 Проверяю Reddit...")
    found = check_reddit()
    total_found += found
    print(f"   └─ Найдено: {found}")
    
    # SteamDB
    print("🎮 Проверяю SteamDB...")
    found = check_steamdb()
    total_found += found
    print(f"   └─ Найдено: {found}")
    
    # Epic Games
    print("🎁 Проверяю Epic Games...")
    found = check_epic_games()
    total_found += found
    print(f"   └─ Найдено: {found}")
    
    # Dealabs
    print("💎 Проверяю Dealabs...")
    found = check_dealabs()
    total_found += found
    print(f"   └─ Найдено: {found}")
    
    print("="*50)
    print(f"✅ ВСЕГО НАЙДЕНО: {total_found}")
    print("="*50 + "\n")
    
    # Сохраняем историю после проверки
    save_history()
    
    return total_found

# ========================================
# КОМАНДЫ БОТА
# ========================================

def handle_command(text, chat_id):
    """Обрабатывает команды"""
    
    if text == '/start' or text == '🏠 Главная':
        send_telegram("""
🎮 <b>Мультиисточниковый бот раздач!</b>

<b>Мониторю источники:</b>
📱 Reddit (4 канала)
🎮 SteamDB
🎁 Epic Games
💎 Dealabs

⏰ Проверка каждые 5 минут
💾 История сохраняется!

📊 Используйте кнопки ниже ⬇️
        """, chat_id, get_main_keyboard())
    
    elif text == '/status' or text == '📊 Статус':
        uptime = datetime.now() - stats['started_at']
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        
        send_telegram(f"""
📊 <b>СТАТУС БОТА</b>

✅ Работает: <b>{hours}ч {minutes}м</b>
🔍 Проверок: <b>{stats['total_checks']}</b>
🎮 Игр найдено: <b>{stats['games_found']}</b>
💾 В памяти: <b>{len(seen_items)}</b> постов

📈 <b>По источникам:</b>
📱 Reddit: {stats['sources']['reddit']}
🎮 SteamDB: {stats['sources']['steamdb']}
🎁 Epic: {stats['sources']['epic']}
💎 Другие: {stats['sources']['other']}

⏰ Последняя проверка: {stats['last_check'] or 'Скоро...'}
        """, chat_id)
    
    elif text == '/test' or text == '🔍 Проверить':
        send_telegram("🔍 <b>Запускаю полную проверку...</b>", chat_id)
        
        found = check_all_sources()
        
        if found > 0:
            send_telegram(f"✅ <b>Найдено: {found} раздач!</b>\n\nСмотрите выше ⬆️", chat_id)
        else:
            send_telegram("ℹ️ Новых раздач пока нет\n\n<i>История сохранена!</i>", chat_id)
    
    elif text == '📈 Источники':
        send_telegram(f"""
📈 <b>АКТИВНЫЕ ИСТОЧНИКИ</b>

<b>Reddit (RSS):</b>
• r/FreeGamesOnSteam
• r/FreeGameFindings
• r/freegames
• r/GameDeals

<b>Прямые источники:</b>
• SteamDB (парсинг)
• Epic Games (API)

<b>Европа/США:</b>
• Dealabs (🇪🇺)
• Slickdeals (🇺🇸)

<b>Всего источников: 8+</b>
💾 <b>В памяти: {len(seen_items)} постов</b>
        """, chat_id)
    
    elif text == '🗑️ Очистить' or text == '/clear':
        confirm_buttons = {
            "inline_keyboard": [
                [
                    {"text": "✅ Да, очистить", "callback_data": "confirm_clear"},
                    {"text": "❌ Отмена", "callback_data": "cancel_clear"}
                ]
            ]
        }
        
        send_telegram(f"""
⚠️ <b>ВНИМАНИЕ!</b>

Вы хотите очистить историю?

💾 Сейчас в памяти: <b>{len(seen_items)}</b> постов

После очистки бот заново загрузит все игры!
<b>Будет много сообщений!</b>

Продолжить?
        """, chat_id, confirm_buttons)
    
    elif text == '/help' or text == '❓ Помощь':
        send_telegram("""
❓ <b>ПОМОЩЬ</b>

<b>Команды:</b>
📊 Статус - Статистика
🔍 Проверить - Проверить сейчас
📈 Источники - Список источников
🗑️ Очистить - Очистить историю

<b>Как работает:</b>
🔍 Каждые 5 минут проверяю 8+ источников
🎮 Нахожу бесплатные игры
💾 Сохраняю историю (не дублирую)
📱 Присылаю с кнопками

<b>Платформы:</b>
🎮 Steam, Epic, GOG
        """, chat_id)

def handle_callback(callback_query):
    """Обрабатывает нажатия кнопок"""
    callback_id = callback_query['id']
    data = callback_query.get('data', '')
    chat_id = callback_query['message']['chat']['id']
    
    answer_url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    
    if data == "confirm_clear":
        requests.post(answer_url, json={"callback_query_id": callback_id, "text": "🗑️ Очищаю..."})
        
        old_count = len(seen_items)
        seen_items.clear()
        save_history()
        
        send_telegram(f"""
✅ <b>История очищена!</b>

🗑️ Удалено: {old_count} постов

🔄 Сейчас запущу проверку...
Приготовьтесь к сообщениям! 😅
        """, chat_id)
        
        found = check_all_sources()
        
        send_telegram(f"""
✅ <b>Проверка завершена!</b>

🎮 Найдено и отправлено: {found} игр

💾 История обновлена!
        """, chat_id)
    
    elif data == "cancel_clear":
        requests.post(answer_url, json={"callback_query_id": callback_id, "text": "❌ Отменено"})
        send_telegram("❌ Очистка отменена", chat_id)
    
    else:
        requests.post(answer_url, json={"callback_query_id": callback_id, "text": "✅"})

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
                    font-family: Arial;
                    text-align: center;
                    padding: 50px;
                }}
                .container {{
                    background: rgba(255,255,255,0.1);
                    padding: 40px;
                    border-radius: 20px;
                    max-width: 800px;
                    margin: 0 auto;
                }}
                h1 {{ font-size: 48px; }}
                .stats {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 20px;
                    margin-top: 30px;
                }}
                .stat {{
                    background: rgba(255,255,255,0.2);
                    padding: 20px;
                    border-radius: 15px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎮 Multi-Source Bot</h1>
                <p>✅ Онлайн • Работает {hours}ч</p>
                
                <div class="stats">
                    <div class="stat">
                        <div style="font-size:32px">{stats['total_checks']}</div>
                                                <div>Проверок</div>
                    </div>
                    <div class="stat">
                        <div style="font-size:32px">{stats['games_found']}</div>
                        <div>Игр найдено</div>
                    </div>
                    <div class="stat">
                        <div style="font-size:32px">{len(seen_items)}</div>
                        <div>В памяти</div>
                    </div>
                    <div class="stat">
                        <div style="font-size:32px">{stats['sources']['reddit']}</div>
                        <div>Reddit</div>
                    </div>
                    <div class="stat">
                        <div style="font-size:32px">{stats['sources']['steamdb']}</div>
                        <div>SteamDB</div>
                    </div>
                    <div class="stat">
                        <div style="font-size:32px">{stats['sources']['epic']}</div>
                        <div>Epic Games</div>
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
        "checks": stats['total_checks'],
        "sources": stats['sources']
    }

@app.route('/webhook', methods=['POST'])
def webhook():
    """Принимает сообщения от Telegram"""
    try:
        update = request.get_json()
        
        # Callback (кнопки)
        if 'callback_query' in update:
            handle_callback(update['callback_query'])
            return {"ok": True}
        
        # Сообщения
        if 'message' in update:
            message = update['message']
            text = message.get('text', '')
            chat_id = message['chat']['id']
            
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
    """Устанавливает webhook"""
    time.sleep(10)
    
    webhook_url = f"https://botiphone.onrender.com/webhook"
    api_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    
    try:
        response = requests.post(api_url, json={"url": webhook_url})
        if response.status_code == 200:
            print(f"✅ Webhook установлен: {webhook_url}")
            
            # Отправляем уведомление о запуске
            send_telegram(f"""
🚀 <b>БОТ ЗАПУЩЕН!</b>

✅ Все источники активны
💾 История загружена: {len(seen_items)} постов
⏰ Первая проверка через минуту

<i>Работаю в фоне...</i>
            """)
        else:
            print(f"⚠️ Ошибка webhook: {response.text}")
    except Exception as e:
        print(f"❌ Ошибка установки webhook: {e}")

# ========================================
# ЗАПУСК БОТА
# ========================================

print("=" * 50)
print("🎮 МУЛЬТИИСТОЧНИКОВЫЙ БОТ С СОХРАНЕНИЕМ")
print("=" * 50)

# НЕ загружаем посты в память при старте!
# История уже загружена через load_history()
print(f"💾 В истории: {len(seen_items)} постов")
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
            print(f"\n{'='*50}")
            print(f"🔍 ПРОВЕРКА [{current_time}]")
            print(f"💾 В памяти: {len(seen_items)} постов")
            print(f"{'='*50}")
            
            # Проверяем все источники
            found = check_all_sources()
            
            stats['total_checks'] += 1
            stats['last_check'] = current_time
            
            if found > 0:
                print(f"✅ Найдено новых игр: {found}")
            else:
                print("ℹ️ Новых раздач нет")
            
            print(f"💤 Следующая проверка через 5 минут...")
            print(f"{'='*50}\n")
            
            time.sleep(300)  # 5 минут
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(60)

# ========================================
# ЗАПУСК
# ========================================

if __name__ == '__main__':
    # Устанавливаем webhook
    webhook_thread = threading.Thread(target=setup_webhook, daemon=True)
    webhook_thread.start()
    
    # Запускаем бота
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Flask запускается на порту {port}")
    print(f"💾 История будет сохраняться автоматически")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port)
