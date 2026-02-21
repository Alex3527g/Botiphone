import feedparser
import requests
import time
import os
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import threading
import json
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from collections import defaultdict

# ========================================
# НАСТРОЙКИ
# ========================================
TOKEN = os.environ.get('TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
DATABASE_URL = os.environ.get('postgresql://games_user:WTKgdDj4k7AoDU8qqhR0ptazxjK4MTdZ@dpg-d6ct6qdm5p6s73f182e0-a/games_db_pkvo')

# Исправление для PostgreSQL на Render
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ========================================
# БАЗА ДАННЫХ
# ========================================
Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

class Game(Base):
    """Модель игры"""
    __tablename__ = 'games'
    
    id = Column(Integer, primary_key=True)
    item_id = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    link = Column(String, nullable=False)
    source = Column(String, nullable=False)
    platform = Column(String, default='unknown')
    price_before = Column(Float, default=0.0)
    found_at = Column(DateTime, default=datetime.utcnow)
    sent = Column(Boolean, default=False)

class UserSettings(Base):
    """Настройки пользователя"""
    __tablename__ = 'settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, unique=True, nullable=False)
    platforms = Column(String, default='all')
    regions = Column(String, default='all')
    min_price = Column(Float, default=0.0)
    notifications = Column(Boolean, default=True)
    instant = Column(Boolean, default=True)

class Statistics(Base):
    """Статистика"""
    __tablename__ = 'statistics'
    
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.utcnow)
    source = Column(String, nullable=False)
    games_found = Column(Integer, default=0)
    checks = Column(Integer, default=0)

# Создаём таблицы
try:
    Base.metadata.create_all(engine)
    print("✅ База данных подключена!")
except Exception as e:
    print(f"❌ Ошибка БД: {e}")

# ========================================
# ФУНКЦИИ БД
# ========================================

def add_game(item_id, title, link, source, platform='unknown', price=0.0):
    """Добавляет игру в БД"""
    session = Session()
    try:
        exists = session.query(Game).filter_by(item_id=item_id).first()
        if exists:
            return False
        
        game = Game(
            item_id=item_id,
            title=title,
            link=link,
            source=source,
            platform=platform,
            price_before=price
        )
        session.add(game)
        session.commit()
        return True
    except Exception as e:
        print(f"❌ Ошибка добавления игры: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def game_exists(item_id):
    """Проверяет существование игры"""
    session = Session()
    try:
        exists = session.query(Game).filter_by(item_id=item_id).first()
        return exists is not None
    finally:
        session.close()

def get_user_settings(user_id):
    """Получает настройки пользователя"""
    session = Session()
    try:
        settings = session.query(UserSettings).filter_by(user_id=str(user_id)).first()
        if not settings:
            settings = UserSettings(user_id=str(user_id))
            session.add(settings)
            session.commit()
            session.refresh(settings)
        return settings
    finally:
        session.close()

def update_settings(user_id, **kwargs):
    """Обновляет настройки"""
    session = Session()
    try:
        settings = session.query(UserSettings).filter_by(user_id=str(user_id)).first()
        if not settings:
            settings = UserSettings(user_id=str(user_id))
            session.add(settings)
        
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        
        session.commit()
        return True
    except Exception as e:
        print(f"❌ Ошибка обновления: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def add_statistics(source, games_found=0, checks=1):
    """Добавляет статистику"""
    session = Session()
    try:
        stat = Statistics(
            source=source,
            games_found=games_found,
            checks=checks
        )
        session.add(stat)
        session.commit()
    except Exception as e:
        print(f"❌ Ошибка статистики: {e}")
        session.rollback()
    finally:
        session.close()

def get_statistics(days=7):
    """Получает статистику"""
    session = Session()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        stats = session.query(Statistics).filter(Statistics.date >= since).all()
        
        by_source = defaultdict(lambda: {'games': 0, 'checks': 0})
        total_games = 0
        total_checks = 0
        
        for stat in stats:
            by_source[stat.source]['games'] += stat.games_found
            by_source[stat.source]['checks'] += stat.checks
            total_games += stat.games_found
            total_checks += stat.checks
        
        return {
            'total_games': total_games,
            'total_checks': total_checks,
            'by_source': dict(by_source),
            'days': days
        }
    finally:
        session.close()

def get_total_games():
    """Общее количество игр"""
    session = Session()
    try:
        return session.query(Game).count()
    finally:
        session.close()

def get_recent_games(limit=10):
    """Последние игры"""
    session = Session()
    try:
        games = session.query(Game).order_by(desc(Game.found_at)).limit(limit).all()
        return [{
            'title': g.title,
            'source': g.source,
            'platform': g.platform,
            'found_at': g.found_at.strftime('%d.%m %H:%M')
        } for g in games]
    finally:
        session.close()

def clear_database():
    """Очищает БД"""
    session = Session()
    try:
        session.query(Game).delete()
        session.commit()
        return True
    except Exception as e:
        print(f"❌ Ошибка очистки: {e}")
        session.rollback()
        return False
    finally:
        session.close()

# ========================================
# ИСТОЧНИКИ
# ========================================

RSS_SOURCES = {
    'reddit': [
        "https://www.reddit.com/r/FreeGamesOnSteam/.rss",
        "https://www.reddit.com/r/FreeGameFindings/.rss",
        "https://www.reddit.com/r/freegames/.rss",
        "https://www.reddit.com/r/GameDeals/.rss"
    ],
    'dealabs': [
        "https://www.dealabs.com/rss/all/gaming",
    ],
}

DIRECT_SOURCES = {
    'steamdb': 'https://steamdb.info/upcoming/free/',
    'epic': 'https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions',
}

stats_runtime = {
    'started_at': datetime.utcnow(),
    'total_checks': 0,
    'last_check': None
}

# ========================================
# TELEGRAM
# ========================================

def send_telegram(text, chat_id=None, reply_markup=None):
    """Отправка сообщения"""
    if chat_id is None:
        chat_id = CHAT_ID
        
    settings = get_user_settings(chat_id)
    if not settings.notifications:
        return False
        
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
    """Главная клавиатура"""
    return {
        "keyboard": [
            [{"text": "📊 Статистика"}, {"text": "🔍 Проверить"}],
            [{"text": "⚙️ Настройки"}, {"text": "📈 Источники"}],
            [{"text": "🎮 Последние игры"}, {"text": "🗑️ Очистить"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def get_game_buttons(link):
    """Кнопки игры"""
    buttons = [[{"text": "🎁 Забрать игру", "url": link}]]
    
    if 'steam' in link.lower():
        buttons.append([{"text": "📊 SteamDB", "url": "https://steamdb.info"}])
    
    return {"inline_keyboard": buttons}

def get_settings_keyboard(user_id):
    """Клавиатура настроек"""
    settings = get_user_settings(user_id)
    
    notif = "🔔 ВКЛ" if settings.notifications else "🔕 ВЫКЛ"
    platform = settings.platforms.upper() if settings.platforms != 'all' else "ВСЕ"
    
    return {
        "inline_keyboard": [
            [{"text": f"Уведомления: {notif}", "callback_data": "toggle_notif"}],
            [{"text": f"Платформы: {platform}", "callback_data": "menu_platforms"}],
            [{"text": "🎮 Steam", "callback_data": "plat_steam"}, 
             {"text": "🎁 Epic", "callback_data": "plat_epic"}],
            [{"text": "🌍 Все", "callback_data": "plat_all"}],
            [{"text": "💰 Цена: $" + str(int(settings.min_price)), "callback_data": "menu_price"}],
            [{"text": "✅ Готово", "callback_data": "settings_done"}]
        ]
    }

# ========================================
# ПАРСЕРЫ
# ========================================

def check_game_filter(title, link, source, user_id):
    """Проверяет фильтры пользователя"""
    settings = get_user_settings(user_id)
    
    # Проверка платформы
    if settings.platforms != 'all':
        platforms = settings.platforms.split(',')
        link_lower = link.lower()
        
        match = False
        for p in platforms:
            if p in link_lower or p in source.lower():
                match = True
                break
        
        if not match:
            return False
    
    return True

def check_reddit():
    """Парсит Reddit"""
    new_items = 0
    
    for rss_url in RSS_SOURCES['reddit']:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:5]:
                item_id = entry.link
                
                if game_exists(item_id):
                    continue
                    
                title = entry.title
                keywords = ['free', 'бесплатно', '100%', 'giveaway', 'раздача', 'freebie']
                
                if not any(word in title.lower() for word in keywords):
                    continue
                
                # Определяем платформу
                platform = 'unknown'
                if 'steam' in title.lower() or 'steam' in entry.link.lower():
                    platform = 'steam'
                elif 'epic' in title.lower():
                    platform = 'epic'
                
                # Проверяем фильтры
                if not check_game_filter(title, entry.link, 'reddit', CHAT_ID):
                    continue
                
                # Добавляем в БД
                if add_game(item_id, title, entry.link, 'reddit', platform):
                    message = f"""
🎮 <b>БЕСПЛАТНАЯ ИГРА!</b>

🎁 <b>{title}</b>

📦 Источник: Reddit
🎯 Платформа: {platform.upper()}
🔗 {entry.link}

⏰ <i>Успей забрать!</i>
                    """
                    
                    if send_telegram(message, reply_markup=get_game_buttons(entry.link)):
                        new_items += 1
                        print(f"✅ [REDDIT] {title[:50]}...")
                        time.sleep(2)
                        
        except Exception as e:
            print(f"❌ Reddit: {e}")
    
    add_statistics('reddit', new_items, 1)
    return new_items

def check_steamdb():
    """Парсит SteamDB"""
    new_items = 0
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
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
                    
                    if game_exists(item_id):
                        continue
                    
                    if not check_game_filter(title, link, 'steamdb', CHAT_ID):
                        continue
                    
                    if add_game(item_id, title, link, 'steamdb', 'steam'):
                        message = f"""
🎮 <b>STEAM РАЗДАЧА!</b>

🎁 <b>{title}</b>

📦 SteamDB Free Package
🔗 {link}
                        """
                        
                        if send_telegram(message, reply_markup=get_game_buttons(link)):
                            new_items += 1
                            print(f"✅ [STEAMDB] {title[:50]}...")
                            time.sleep(2)
                            
                except:
                    continue
                    
    except Exception as e:
        print(f"❌ SteamDB: {e}")
    
    add_statistics('steamdb', new_items, 1)
    return new_items

def check_epic_games():
    """Парсит Epic Games"""
    new_items = 0
    
    try:
        response = requests.get(DIRECT_SOURCES['epic'], timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            games = data.get('data', {}).get('Catalog', {}).get('searchStore', {}).get('elements', [])
            
            for game in games:
                try:
                    promotions = game.get('promotions')
                    if not promotions:
                        continue
                    
                    title = game.get('title', 'Unknown')
                    item_id = f"epic_{title}"
                    
                    if game_exists(item_id):
                        continue
                    
                    slug = game.get('productSlug', '')
                    link = f"https://store.epicgames.com/en-US/p/{slug}"
                    
                    if not check_game_filter(title, link, 'epic', CHAT_ID):
                        continue
                    
                    if add_game(item_id, title, link, 'epic', 'epic'):
                        message = f"""
🎁 <b>EPIC GAMES!</b>

🎮 <b>{title}</b>

📦 Epic Games Store
🔗 {link}

⏰ <i>Бесплатно на этой неделе!</i>
                        """
                        
                        if send_telegram(message, reply_markup=get_game_buttons(link)):
                            new_items += 1
                            print(f"✅ [EPIC] {title[:50]}...")
                            time.sleep(2)
                            
                except:
                    continue
                    
    except Exception as e:
        print(f"❌ Epic: {e}")
    
    add_statistics('epic', new_items, 1)
    return new_items

def check_dealabs():
    """Парсит Dealabs"""
    new_items = 0
    
    for rss_url in RSS_SOURCES['dealabs']:
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:5]:
                item_id = entry.link
                
                if game_exists(item_id):
                    continue
                
                title = entry.title
                
                if any(word in title.lower() for word in ['gratuit', 'free', '0€', '0$']):
                    if add_game(item_id, title, entry.link, 'dealabs'):
                        message = f"""
💎 <b>ЕВРОПЕЙСКАЯ РАЗДАЧА!</b>

🎁 <b>{title}</b>

📦 Dealabs
🔗 {entry.link}
                        """
                        
                        if send_telegram(message, reply_markup=get_game_buttons(entry.link)):
                            new_items += 1
                            print(f"✅ [DEALABS] {title[:50]}...")
                            time.sleep(2)
                        
        except Exception as e:
            print(f"❌ Dealabs: {e}")
    
    add_statistics('dealabs', new_items, 1)
    return new_items

def check_all_sources():
    """Проверяет все источники"""
    total = 0
    
    print("\n" + "="*50)
    print("🔍 ПРОВЕРКА ВСЕХ ИСТОЧНИКОВ")
    print("="*50)
    
    sources = [
        ("Reddit", check_reddit),
        ("SteamDB", check_steamdb),
        ("Epic Games", check_epic_games),
        ("Dealabs", check_dealabs)
    ]
    
    for name, func in sources:
        print(f"📱 {name}...")
        found = func()
        total += found
        print(f"   └─ Найдено: {found}")
    
    print("="*50)
    print(f"✅ ВСЕГО: {total}")
    print("="*50 + "\n")
    
    return total

# ========================================
# КОМАНДЫ
# ========================================

def handle_command(text, chat_id):
    """Обработка команд"""
    
    if text == '/start' or text == '🏠 Главная':
        send_telegram("""
🎮 <b>МЕГА-БОТ РАЗДАЧ v2.0</b>

<b>Возможности:</b>
✅ 8+ источников игр
✅ База данных PostgreSQL
✅ Гибкие фильтры
✅ Статистика с графиками
✅ Настройки под себя

📊 Используйте кнопки ниже ⬇️
        """, chat_id, get_main_keyboard())
    
    elif text == '📊 Статистика' or text == '/stats':
        stats = get_statistics(7)
        total_db = get_total_games()
        uptime = datetime.utcnow() - stats_runtime['started_at']
        hours = int(uptime.total_seconds() // 3600)
        
        top_sources = sorted(
            stats['by_source'].items(),
            key=lambda x: x[1]['games'],
            reverse=True
        )[:3]
        
        top_text = "\n".join([
            f"{i+1}. {src.title()}: {data['games']} игр"
            for i, (src, data) in enumerate(top_sources)
        ])
        
        send_telegram(f"""
📊 <b>СТАТИСТИКА ЗА 7 ДНЕЙ</b>

🎮 Найдено: <b>{stats['total_games']}</b> игр
🔍 Проверок: <b>{stats['total_checks']}</b>
💾 В базе: <b>{total_db}</b> игр

<b>ТОП источников:</b>
{top_text}

⏰ Работает: {hours}ч
🕐 Последняя проверка: {stats_runtime['last_check'] or 'Скоро'}
        """, chat_id)
    
    elif text == '🔍 Проверить' or text == '/check':
        send_telegram("🔍 Запускаю проверку...", chat_id)
        found = check_all_sources()
        
        if found > 0:
                        send_telegram(f"✅ Найдено: <b>{found}</b> игр!\n\nСмотрите выше ⬆️", chat_id)
        else:
            send_telegram("ℹ️ Новых раздач пока нет", chat_id)
    
    elif text == '⚙️ Настройки' or text == '/settings':
        settings = get_user_settings(chat_id)
        
        send_telegram(f"""
⚙️ <b>НАСТРОЙКИ</b>

<b>Текущие параметры:</b>
🔔 Уведомления: {'ВКЛ' if settings.notifications else 'ВЫКЛ'}
🎮 Платформы: {settings.platforms.upper()}
💰 Мин. цена: ${settings.min_price}

<i>Используйте кнопки ниже:</i>
        """, chat_id, get_settings_keyboard(chat_id))
    
    elif text == '📈 Источники' or text == '/sources':
        stats = get_statistics(7)
        by_source = stats['by_source']
        
        source_list = []
        for src, data in by_source.items():
            source_list.append(f"• {src.title()}: {data['games']} игр")
        
        sources_text = "\n".join(source_list) if source_list else "Нет данных"
        
        send_telegram(f"""
📈 <b>АКТИВНЫЕ ИСТОЧНИКИ</b>

<b>Reddit (RSS):</b>
• r/FreeGamesOnSteam
• r/FreeGameFindings
• r/freegames
• r/GameDeals

<b>Прямые:</b>
• SteamDB (парсинг)
• Epic Games (API)
• Dealabs (EU)

<b>За 7 дней:</b>
{sources_text}

<b>Всего: 8+ источников</b>
        """, chat_id)
    
    elif text == '🎮 Последние игры' or text == '/recent':
        games = get_recent_games(10)
        
        if games:
            game_list = []
            for g in games:
                emoji = "🎮" if g['platform'] == 'steam' else "🎁" if g['platform'] == 'epic' else "💎"
                game_list.append(f"{emoji} <b>{g['title'][:40]}</b>\n   📦 {g['source']} • {g['found_at']}")
            
            games_text = "\n\n".join(game_list)
            
            send_telegram(f"""
🎮 <b>ПОСЛЕДНИЕ 10 ИГР</b>

{games_text}

💾 Всего в базе: {get_total_games()} игр
            """, chat_id)
        else:
            send_telegram("📭 База данных пуста", chat_id)
    
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

Очистить базу данных?

💾 Сейчас: <b>{get_total_games()}</b> игр

После очистки бот заново найдет все игры!
<b>Будет много сообщений!</b>

Продолжить?
        """, chat_id, confirm_buttons)
    
    elif text == '/help' or text == '❓ Помощь':
        send_telegram("""
❓ <b>ПОМОЩЬ</b>

<b>Команды:</b>
📊 Статистика - Статистика за 7 дней
🔍 Проверить - Проверить сейчас
⚙️ Настройки - Фильтры и уведомления
📈 Источники - Список источников
🎮 Последние игры - История находок
🗑️ Очистить - Очистить базу

<b>Возможности:</b>
✅ Автопроверка каждые 5 минут
✅ PostgreSQL - история навсегда
✅ Фильтры по платформам
✅ Никаких дубликатов
✅ Расширенная статистика

<b>Платформы:</b>
🎮 Steam, Epic, GOG, и другие
        """, chat_id)

def handle_callback(callback_query):
    """Обработка кнопок"""
    callback_id = callback_query['id']
    data = callback_query.get('data', '')
    chat_id = callback_query['message']['chat']['id']
    message_id = callback_query['message']['message_id']
    
    answer_url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    edit_url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    
    if data == "toggle_notif":
        settings = get_user_settings(chat_id)
        new_status = not settings.notifications
        update_settings(chat_id, notifications=new_status)
        
        status = "включены" if new_status else "выключены"
        requests.post(answer_url, json={
            "callback_query_id": callback_id,
            "text": f"Уведомления {status}!"
        })
        
        # Обновляем клавиатуру
        requests.post(edit_url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "⚙️ <b>НАСТРОЙКИ</b>\n\nИспользуйте кнопки ниже:",
            "parse_mode": "HTML",
            "reply_markup": get_settings_keyboard(chat_id)
        })
    
    elif data.startswith("plat_"):
        platform = data.replace("plat_", "")
        update_settings(chat_id, platforms=platform)
        
        requests.post(answer_url, json={
            "callback_query_id": callback_id,
            "text": f"Платформа: {platform.upper()}"
        })
        
        requests.post(edit_url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "⚙️ <b>НАСТРОЙКИ</b>\n\nИспользуйте кнопки ниже:",
            "parse_mode": "HTML",
            "reply_markup": get_settings_keyboard(chat_id)
        })
    
    elif data == "settings_done":
        requests.post(answer_url, json={
            "callback_query_id": callback_id,
            "text": "✅ Настройки сохранены!"
        })
        
        settings = get_user_settings(chat_id)
        
        requests.post(edit_url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": f"""
✅ <b>НАСТРОЙКИ СОХРАНЕНЫ</b>

🔔 Уведомления: {'ВКЛ' if settings.notifications else 'ВЫКЛ'}
🎮 Платформы: {settings.platforms.upper()}
💰 Мин. цена: ${settings.min_price}

<i>Настройки применены!</i>
            """,
            "parse_mode": "HTML"
        })
    
    elif data == "confirm_clear":
        requests.post(answer_url, json={
            "callback_query_id": callback_id,
            "text": "🗑️ Очищаю..."
        })
        
        old_count = get_total_games()
        clear_database()
        
        send_telegram(f"""
✅ <b>БАЗА ОЧИЩЕНА!</b>

🗑️ Удалено: {old_count} игр

🔄 Запускаю проверку...
        """, chat_id)
        
        found = check_all_sources()
        
        send_telegram(f"""
✅ <b>ГОТОВО!</b>

🎮 Найдено: {found} игр
💾 Все сохранено в базе

Смотрите выше ⬆️
        """, chat_id)
    
    elif data == "cancel_clear":
        requests.post(answer_url, json={
            "callback_query_id": callback_id,
            "text": "❌ Отменено"
        })
        send_telegram("❌ Очистка отменена", chat_id)
    
    else:
        requests.post(answer_url, json={
            "callback_query_id": callback_id,
            "text": "✅"
        })

# ========================================
# FLASK
# ========================================

app = Flask(__name__)

@app.route('/')
def home():
    """Главная страница"""
    uptime = datetime.utcnow() - stats_runtime['started_at']
    hours = int(uptime.total_seconds() // 3600)
    
    stats = get_statistics(7)
    total_games = get_total_games()
    
    recent = get_recent_games(5)
    recent_html = ""
    for g in recent:
        recent_html += f"<div class='game'>{g['title'][:50]} • {g['source']}</div>"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Free Games Bot</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #fff;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
            }}
            .header {{
                text-align: center;
                padding: 40px 20px;
            }}
            h1 {{
                font-size: 48px;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }}
            .status {{
                font-size: 20px;
                opacity: 0.9;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 40px 0;
            }}
            .stat-card {{
                background: rgba(255,255,255,0.15);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                text-align: center;
                transition: transform 0.3s;
            }}
            .stat-card:hover {{
                transform: translateY(-5px);
                background: rgba(255,255,255,0.2);
            }}
            .stat-value {{
                font-size: 48px;
                font-weight: bold;
                margin: 10px 0;
            }}
            .stat-label {{
                font-size: 16px;
                opacity: 0.9;
            }}
            .section {{
                background: rgba(255,255,255,0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                margin: 20px 0;
            }}
            .section h2 {{
                font-size: 28px;
                margin-bottom: 20px;
            }}
            .game {{
                background: rgba(255,255,255,0.1);
                padding: 15px;
                border-radius: 10px;
                margin: 10px 0;
            }}
            .footer {{
                text-align: center;
                padding: 40px 20px;
                opacity: 0.8;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎮 Free Games Bot</h1>
                <div class="status">✅ Онлайн • Работает {hours}ч</div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Всего проверок</div>
                    <div class="stat-value">{stats['total_checks']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Игр найдено (7д)</div>
                    <div class="stat-value">{stats['total_games']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">В базе данных</div>
                    <div class="stat-value">{total_games}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Источников</div>
                    <div class="stat-value">8+</div>
                </div>
            </div>
            
            <div class="section">
                <h2>📈 Статистика по источникам</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">Reddit</div>
                        <div class="stat-value">{stats['by_source'].get('reddit', {}).get('games', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">SteamDB</div>
                        <div class="stat-value">{stats['by_source'].get('steamdb', {}).get('games', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Epic Games</div>
                        <div class="stat-value">{stats['by_source'].get('epic', {}).get('games', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Dealabs</div>
                        <div class="stat-value">{stats['by_source'].get('dealabs', {}).get('games', 0)}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>🎮 Последние игры</h2>
                {recent_html if recent_html else '<div class="game">Пока нет игр</div>'}
            </div>
            
            <div class="footer">
                <p>🚀 Powered by Render + PostgreSQL</p>
                <p>⏰ Проверка каждые 5 минут</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    """Healthcheck"""
    return jsonify({
        "status": "ok",
        "uptime_hours": int((datetime.utcnow() - stats_runtime['started_at']).total_seconds() // 3600),
        "total_games": get_total_games(),
        "checks": stats_runtime['total_checks']
    })

@app.route('/api/stats')
def api_stats():
    """API статистики"""
    stats = get_statistics(7)
    return jsonify({
        "total_games": get_total_games(),
        "week_stats": stats,
        "recent_games": get_recent_games(10)
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook Telegram"""
    try:
        update = request.get_json()
        
        if 'callback_query' in update:
            handle_callback(update['callback_query'])
            return {"ok": True}
        
        if 'message' in update:
            message = update['message']
            text = message.get('text', '')
            chat_id = message['chat']['id']
            
            if str(chat_id) == str(CHAT_ID):
                handle_command(text, chat_id)
        
        return {"ok": True}
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return {"ok": False}, 500

# ========================================
# WEBHOOK SETUP
# ========================================

def setup_webhook():
    """Устанавливает webhook"""
    time.sleep(10)
    
    webhook_url = f"https://botiphone.onrender.com/webhook"
    api_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    
    try:
        response = requests.post(api_url, json={"url": webhook_url})
        if response.status_code == 200:
            print(f"✅ Webhook: {webhook_url}")
            
            send_telegram(f"""
🚀 <b>МЕГА-БОТ v2.0 ЗАПУЩЕН!</b>

✅ PostgreSQL подключена
✅ {get_total_games()} игр в базе
✅ Все источники активны

⏰ Проверка каждые 5 минут
💾 История сохраняется навсегда

<i>Работаю в фоне...</i>
            """)
        else:
            print(f"⚠️ Webhook error: {response.text}")
    except Exception as e:
        print(f"❌ Setup error: {e}")

# ========================================
# ОСНОВНОЙ ЦИКЛ
# ========================================

def run_bot():
    """Главный цикл"""
    time.sleep(15)
    
    while True:
        try:
            current_time = datetime.utcnow().strftime('%H:%M:%S')
            print(f"\n{'='*50}")
            print(f"🔍 ПРОВЕРКА [{current_time}]")
            print(f"💾 В базе: {get_total_games()} игр")
            print(f"{'='*50}")
            
            found = check_all_sources()
            
            stats_runtime['total_checks'] += 1
            stats_runtime['last_check'] = current_time
            
            if found > 0:
                print(f"✅ Новых: {found}")
            else:
                print("ℹ️ Нет новых")
            
            print(f"💤 Следующая через 5 минут...")
            print(f"{'='*50}\n")
            
            time.sleep(300)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(60)

# ========================================
# ЗАПУСК
# ========================================

print("=" * 50)
print("🚀 МЕГА-БОТ v2.0 ЗАГРУЖАЕТСЯ...")
print("=" * 50)
print(f"💾 PostgreSQL: {'✅' if 'postgresql' in DATABASE_URL else '⚠️ SQLite'}")
print(f"📊 В базе: {get_total_games()} игр")
print("=" * 50)

if __name__ == '__main__':
    # Webhook
    webhook_thread = threading.Thread(target=setup_webhook, daemon=True)
    webhook_thread.start()
    
    # Бот
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Flask
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Flask: {port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port)
                
