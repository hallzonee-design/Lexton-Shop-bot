import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
import sqlite3
from datetime import datetime, timedelta
import random
import string
import time
import requests
import re
import hashlib
import threading
from urllib.parse import quote_plus
import os
import sys
import signal
import json

# ========== ТОКЕНЫ И НАСТРОЙКИ ==========
BOT_TOKEN = "7724795969:AAHEGIz3XZSW7B-nayBjh7GMpHZwQWjCCec"
ADMIN_ID = 8212217378  # Основной админ
ADMIN_ID2 = 8617203586  # Второй админ
ADMIN_USERNAME = "@lexxtoon"

NUMLOOKUP_API_KEY = "d113cd522f00e6d95479082f7719fcca"  # ваш ключ numverify
LEAKCHECK_API_KEY = ""  # если есть ключ от leakcheck.net, вставьте сюда
VK_API_TOKEN = ""

CRYPTO_BOT_LINK = "http://t.me/send?start=IVormTW8DXcU"
BOT_USERNAME = "LeextonShopbot"
SHOP_URL = "https://sites.google.com/view/dchcnvnchgx/home"
SBP_URL = "https://finance.ozon.ru/apps/sbp/ozonbankpay/019b01bd-6df5-7ae2-a466-f09a95dac173"
MIN_WITHDRAW_RUB = 500
MIN_WITHDRAW_STARS = 400
MIN_WITHDRAW_CRYPTO = 3.5

WITHDRAW_GIF = "https://static.wikia.nocookie.net/c3d738d0-1083-4e43-ae08-579f2f24dc1b/scale-to-width/755"

bot = telebot.TeleBot(BOT_TOKEN)
conn = sqlite3.connect('lexton_bot.db', check_same_thread=False)

# ========== ФУНКЦИЯ ПРОВЕРКИ АДМИНА ==========
def is_admin(user_id):
    return user_id == ADMIN_ID or user_id == ADMIN_ID2

# ========== БАЗА ДАННЫХ ==========
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0,
    stars_balance INTEGER DEFAULT 0,
    crypto_balance REAL DEFAULT 0,
    total_earned REAL DEFAULT 0,
    referral_code TEXT UNIQUE,
    invited_by INTEGER,
    reg_date TEXT,
    banned_until TEXT DEFAULT NULL
)''')

c.execute('''CREATE TABLE IF NOT EXISTS search_tariffs (
    user_id INTEGER,
    tariff_type TEXT,
    days INTEGER,
    expiry TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER,
    referred_username TEXT,
    reg_date TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    query TEXT,
    result_summary TEXT,
    date TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS purchase_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_username TEXT,
    buyer_id INTEGER,
    amount REAL,
    currency TEXT,
    date TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS balance_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    admin_username TEXT,
    target_username TEXT,
    target_id INTEGER,
    amount REAL,
    currency TEXT,
    action_type TEXT,
    reason TEXT,
    date TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    action TEXT,
    details TEXT,
    date TEXT
)''')
conn.commit()
c.close()

TARIFFS = {
    "30": {"name": "30 дней", "days": 30, "stars": 150, "crypto": 1.5, "rub": 150},
    "90": {"name": "90 дней", "days": 90, "stars": 350, "crypto": 3.5, "rub": 350},
    "120": {"name": "120 дней", "days": 120, "stars": 500, "crypto": 5.0, "rub": 500},
    "forever": {"name": "НАВСЕГДА", "days": 99999, "stars": 5000, "crypto": 50.0, "rub": 5000}
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def is_banned(uid):
    c = conn.cursor()
    c.execute('SELECT banned_until FROM users WHERE user_id = ?', (uid,))
    r = c.fetchone()
    c.close()
    return r and r[0] and datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") > datetime.now()

def has_access(uid):
    c = conn.cursor()
    c.execute('SELECT expiry FROM search_tariffs WHERE user_id = ? AND expiry > ?',
              (uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    r = c.fetchone()
    c.close()
    return r is not None

def get_days(uid):
    c = conn.cursor()
    c.execute('SELECT expiry FROM search_tariffs WHERE user_id = ? AND expiry > ?',
              (uid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    r = c.fetchone()
    c.close()
    if r:
        return max(0, (datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") - datetime.now()).days)
    return 0

def activate_access(uid, username, days):
    expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO search_tariffs VALUES (?, ?, ?, ?)', (uid, 'premium', days, expiry))
    conn.commit()
    c.close()
    log_activity(uid, username, "Активация доступа", f"Доступ активирован на {days} дней")

def add_purchase_history(uid, username, amount, currency):
    c = conn.cursor()
    c.execute('INSERT INTO purchase_history (buyer_username, buyer_id, amount, currency, date) VALUES (?, ?, ?, ?, ?)',
              (username, uid, amount, currency, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    c.close()

def add_balance_log(admin_id, admin_username, target_username, target_id, amount, currency, action_type, reason=""):
    c = conn.cursor()
    c.execute('INSERT INTO balance_logs (admin_id, admin_username, target_username, target_id, amount, currency, action_type, reason, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
              (admin_id, admin_username, target_username, target_id, amount, currency, action_type, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    c.close()

def log_activity(user_id, username, action, details=""):
    c = conn.cursor()
    c.execute('INSERT INTO activity_logs (user_id, username, action, details, date) VALUES (?, ?, ?, ?, ?)',
              (user_id, username, action, details, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    c.close()

def add_referral_bonus(uid, amount, currency):
    c = conn.cursor()
    c.execute('SELECT invited_by FROM users WHERE user_id = ?', (uid,))
    inviter = c.fetchone()
    if inviter and inviter[0]:
        bonus = amount * 0.1
        if currency == "STARS":
            c.execute('UPDATE users SET stars_balance = stars_balance + ? WHERE user_id = ?', (bonus, inviter[0]))
        elif currency == "USDT":
            c.execute('UPDATE users SET crypto_balance = crypto_balance + ? WHERE user_id = ?', (bonus, inviter[0]))
        else:
            c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (bonus, inviter[0]))
        c.execute('UPDATE users SET total_earned = total_earned + ? WHERE user_id = ?', (bonus, inviter[0]))

        c.execute('SELECT username FROM users WHERE user_id = ?', (inviter[0],))
        inv_username = c.fetchone()
        if inv_username:
            c2 = conn.cursor()
            c2.execute('INSERT INTO balance_logs (admin_id, admin_username, target_username, target_id, amount, currency, action_type, reason, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (0, "SYSTEM", inv_username[0], inviter[0], bonus, currency, "referral_bonus", f"Реферальный бонус от {uid}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            c2.close()
        conn.commit()
    c.close()

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("🛒 МАГАЗИН"), KeyboardButton("🔍 ПОИСК"))
    kb.add(KeyboardButton("🤝 РЕФЕРАЛЫ"), KeyboardButton("💸 ВЫВОД"))
    kb.add(KeyboardButton("👤 ПРОФИЛЬ"), KeyboardButton("❓ ПОМОЩЬ"))
    return kb

def search_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(KeyboardButton("📱 ПОИСК ПО НОМЕРУ"))
    kb.add(KeyboardButton("📧 ПОИСК ПО EMAIL"))
    kb.add(KeyboardButton("👤 ПОИСК ПО USERNAME"))
    kb.add(KeyboardButton("💳 КУПИТЬ ПОДПИСКУ"))
    kb.add(KeyboardButton("ℹ️ СТАТУС"))
    kb.add(KeyboardButton("🔙 НАЗАД"))
    return kb

# ===================== НОВЫЙ ГЛУБОКИЙ OSINT-МОДУЛЬ =====================
# Глобальные множества для отслеживания уже найденных данных
found_emails = set()
found_usernames = set()
found_phones = set()
found_social = {}  # платформа -> ссылка

def clear_found_sets():
    global found_emails, found_usernames, found_phones, found_social
    found_emails.clear()
    found_usernames.clear()
    found_phones.clear()
    found_social.clear()

def add_social(platform, url):
    if platform not in found_social:
        found_social[platform] = url

def extract_emails_from_text(text):
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    return [e for e in emails if 'example' not in e and len(e) < 100]

def extract_usernames_from_text(text):
    patterns = {
        'vk.com/': r'vk\.com/([a-zA-Z0-9_\.]+)',
        'instagram.com/': r'instagram\.com/([a-zA-Z0-9_\.]+)/?',
        't.me/': r't\.me/([a-zA-Z0-9_]+)',
        'twitter.com/': r'twitter\.com/([a-zA-Z0-9_]+)',
        'tiktok.com/@': r'tiktok\.com/@([a-zA-Z0-9_\.]+)',
        'youtube.com/@': r'youtube\.com/@([a-zA-Z0-9_\.]+)',
    }
    usernames = set()
    for platform, pattern in patterns.items():
        matches = re.findall(pattern, text)
        for m in matches:
            usernames.add(m)
    return list(usernames)

def search_social_by_username(username):
    platforms = {
        "Telegram": f"https://t.me/{username}",
        "VK": f"https://vk.com/{username}",
        "Instagram": f"https://www.instagram.com/{username}/",
        "Twitter": f"https://twitter.com/{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "YouTube": f"https://www.youtube.com/@{username}",
        "GitHub": f"https://github.com/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}",
    }
    found = []
    for name, url in platforms.items():
        try:
            r = requests.get(url, timeout=5, headers=HEADERS, allow_redirects=True)
            if r.status_code == 200:
                if name == "Telegram" and 'tgme_page_title' not in r.text:
                    continue
                if name == "Twitter" and ("This account doesn’t exist" in r.text or "Diese Seite existiert nicht" in r.text):
                    continue
                if name == "Reddit" and "page not found" in r.text.lower():
                    continue
                found.append(f"✅ {name}: {url}")
                add_social(name, url)
        except:
            pass
    return found

def search_email_social(email):
    results = []
    try:
        hash_md5 = hashlib.md5(email.lower().encode()).hexdigest()
        r = requests.get(f"https://www.gravatar.com/{hash_md5}.json", timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get('entry'):
                results.append("🖼 Gravatar: профиль найден")
    except:
        pass
    try:
        r = requests.get(f"https://psbdmp.ws/api/v3/search/email/{email}", timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data.get('count', 0) > 0:
                results.append(f"🔓 Утечки (psbdmp): {data['count']} записей")
                for leak in data.get('list', [])[:3]:
                    txt = leak.get('text', '')
                    if txt:
                        usernames = extract_usernames_from_text(txt)
                        for un in usernames:
                            if un not in found_usernames:
                                found_usernames.add(un)
    except:
        pass
    return results

def search_phone_deep(phone):
    clean_phone = ''.join(filter(str.isdigit, phone))
    results = []
    if clean_phone not in found_phones:
        found_phones.add(clean_phone)

    if clean_phone.startswith('7') and len(clean_phone) == 11:
        results.append(f"📡 ОПЕРАТОР: Россия (+7)")
    elif clean_phone.startswith('380'):
        results.append(f"📡 ОПЕРАТОР: Украина (+380)")
    elif clean_phone.startswith('375'):
        results.append(f"📡 ОПЕРАТОР: Беларусь (+375)")

    if NUMLOOKUP_API_KEY:
        try:
            url = f"http://apilayer.net/api/validate?access_key={NUMLOOKUP_API_KEY}&number={clean_phone}"
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if data.get('valid'):
                    country = data.get('country_name', '')
                    location = data.get('location', '')
                    carrier = data.get('carrier', '')
                    line_type = data.get('line_type', '')
                    results.append(f"📞 Numverify: {country}, {location}, {carrier}, {line_type}")
                else:
                    results.append("⚠️ Numverify: номер недействителен")
        except:
            results.append("⚠️ Numverify: ошибка доступа")

    try:
        r = requests.get(f"https://t.me/+{clean_phone}", timeout=8, allow_redirects=True)
        if "tgme_page_title" in r.text:
            name_match = re.search(r'<div class="tgme_page_title"><span dir="auto">(.*?)</span></div>', r.text)
            if name_match:
                results.append(f"✅ Telegram: аккаунт существует — {name_match.group(1)}")
            else:
                results.append("✅ Telegram: аккаунт существует")
        else:
            results.append("❌ Telegram: аккаунт не найден")
    except:
        results.append("⚠️ Telegram: ошибка проверки")

    try:
        r = requests.get(f"https://wa.me/{clean_phone}", timeout=6, allow_redirects=True)
        if r.status_code == 200:
            results.append("✅ WhatsApp: аккаунт существует")
    except:
        pass

    try:
        query = quote_plus(f'"{clean_phone}"')
        r = requests.get(f"https://www.google.com/search?q={query}&hl=ru&num=30", timeout=12, headers=HEADERS)
        if r.status_code == 200:
            text = r.text.lower()
            new_emails = extract_emails_from_text(text)
            for email in new_emails:
                if email not in found_emails:
                    found_emails.add(email)
                    results.append(f"📧 Найден email: {email}")
            new_usernames = extract_usernames_from_text(text)
            for un in new_usernames:
                if un not in found_usernames:
                    found_usernames.add(un)
                    results.append(f"👤 Найден username: @{un}")
            vk_links = re.findall(r'(https?://vk\.com/[a-zA-Z0-9_\.]+)', text)
            for link in vk_links[:2]:
                if "VK" not in found_social:
                    add_social("VK", link)
                    results.append(f"👤 VK: {link}")
            insta_links = re.findall(r'(https?://(www\.)?instagram\.com/[a-zA-Z0-9_\.]+/?[\w-]*)', text)
            for il in insta_links[:2]:
                if "Instagram" not in found_social:
                    add_social("Instagram", il[0])
                    results.append(f"📸 Instagram: {il[0]}")
    except:
        results.append("⚠️ Google: ошибка парсинга")

    try:
        r = requests.get(f"https://psbdmp.ws/api/v3/search/email/{clean_phone}@gmail.com", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('count', 0) > 0:
                results.append(f"🔓 Утечки (psbdmp) для номеров: {data['count']} записей")
                for leak in data.get('list', [])[:3]:
                    txt = leak.get('text', '')
                    if txt:
                        emails = extract_emails_from_text(txt)
                        for em in emails:
                            if em not in found_emails:
                                found_emails.add(em)
                                results.append(f"📧 Email из утечки: {em}")
    except:
        pass

    try:
        query_enc = quote_plus(clean_phone)
        r = requests.get(f"https://doxbin.org/search?query={query_enc}", timeout=10)
        if r.status_code == 200 and "paste" in r.text:
            results.append("📋 Doxbin: найдены упоминания")
    except:
        pass

    return results

def search_email_deep(email):
    results = [f"📧 EMAIL: {email}"]
    domain = email.split('@')[1]
    results.append(f"├ Домен: {domain}")
    try:
        r = requests.get(f"https://psbdmp.ws/api/v3/search/email/{email}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('count', 0) > 0:
                results.append(f"🔓 Утечки (psbdmp): {data['count']} записей")
                for leak in data.get('list', [])[:5]:
                    results.append(f"├ {leak.get('name', '?')} — {leak.get('date', '?')}")
                    txt = leak.get('text', '')
                    if txt:
                        usernames = extract_usernames_from_text(txt)
                        for un in usernames:
                            if un not in found_usernames:
                                found_usernames.add(un)
                                results.append(f"└ → Найден username: @{un}")
    except:
        results.append("⚠️ Утечки: ошибка")
    try:
        hash_md5 = hashlib.md5(email.lower().encode()).hexdigest()
        r = requests.get(f"https://www.gravatar.com/{hash_md5}.json", timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get('entry'):
                results.append("🖼 Gravatar: профиль найден")
    except:
        pass
    try:
        query = quote_plus(f'"{email}"')
        r = requests.get(f"https://www.google.com/search?q={query}&hl=ru&num=20", timeout=12, headers=HEADERS)
        if r.status_code == 200:
            text = r.text.lower()
            usernames = extract_usernames_from_text(text)
            for un in usernames:
                if un not in found_usernames:
                    found_usernames.add(un)
                    results.append(f"👤 Найден username через Google: @{un}")
            vk_links = re.findall(r'(https?://vk\.com/[a-zA-Z0-9_\.]+)', text)
            for link in vk_links[:2]:
                if "VK" not in found_social:
                    add_social("VK", link)
                    results.append(f"👤 VK: {link}")
    except:
        pass
    if LEAKCHECK_API_KEY:
        try:
            r = requests.get(f"https://leakcheck.net/api/public?key={LEAKCHECK_API_KEY}&check={email}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('found'):
                    results.append(f"🔓 Leakcheck: найдено в {data.get('sources', [])}")
        except:
            pass
    return results

def search_username_deep(username):
    clean = username.strip().lstrip('@')
    results = [f"🔍 USERNAME: @{clean}"]
    social_results = search_social_by_username(clean)
    results.extend(social_results)
    try:
        query = quote_plus(f'"{clean}" email')
        r = requests.get(f"https://www.google.com/search?q={query}&hl=ru&num=20", timeout=12, headers=HEADERS)
        if r.status_code == 200:
            emails = extract_emails_from_text(r.text)
            for email in emails:
                if email not in found_emails:
                    found_emails.add(email)
                    results.append(f"📧 Возможный email: {email}")
    except:
        pass
    try:
        r = requests.get(f"https://doxbin.org/search?query={clean}", timeout=8)
        if r.status_code == 200 and "paste" in r.text:
            results.append("📋 Doxbin: найдены упоминания")
    except:
        pass
    return results

def deep_osint_by_phone(phone, depth=0, max_depth=2):
    global found_emails, found_usernames, found_social
    all_results = []
    phone_results = search_phone_deep(phone)
    all_results.extend(phone_results)
    if depth >= max_depth:
        return all_results
    emails_to_search = list(found_emails.copy())
    usernames_to_search = list(found_usernames.copy())
