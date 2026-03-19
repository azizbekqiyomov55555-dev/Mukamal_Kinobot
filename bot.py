#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot - Full Featured
Admin Panel + Video Management + Payment System + Statistics
"""

import asyncio
import logging
import os
import json
import io
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputFile, BufferedInputFile
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ─────────────────────────── SOZLAMALAR ───────────────────────────
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_IDS = [123456789]  # Admin Telegram ID larini kiriting
PAYMENT_CARD = "8600 0000 0000 0000"  # Karta raqamingiz
DB_PATH = "bot_database.db"

# Toshkent vaqt zonasi (UTC+5)
TASHKENT_TZ = timezone(timedelta(hours=5))

def tashkent_now():
    return datetime.now(TASHKENT_TZ)

def fmt_dt(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return dt_str

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────── FSM STATES ───────────────────────────
class AdminStates(StatesGroup):
    # Video qo'shish
    waiting_video = State()
    waiting_video_part = State()
    waiting_more_parts = State()
    waiting_part_text = State()
    waiting_video_code = State()
    waiting_video_price = State()
    waiting_video_title = State()
    # Start xabar
    waiting_start_text = State()
    waiting_start_photo = State()
    waiting_start_msg_type = State()
    waiting_start_quote_link = State()
    # Kanal/bot qo'shish
    waiting_channel_id = State()
    waiting_channel_name = State()
    waiting_bot_token_add = State()
    waiting_bot_name = State()
    # Instagram/YouTube
    waiting_instagram = State()
    waiting_youtube = State()
    # Foydalanuvchiga xabar
    waiting_broadcast_content = State()
    # Pul qo'shish
    waiting_add_balance_id = State()
    waiting_add_balance_amount = State()
    waiting_add_all_balance = State()
    # Ban
    waiting_ban_id = State()
    waiting_unban_id = State()

class UserStates(StatesGroup):
    waiting_code = State()
    waiting_payment_check = State()
    waiting_top_up_amount = State()
    waiting_top_up_check = State()
    waiting_help_msg = State()

# ─────────────────────────── DATABASE ───────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            language TEXT DEFAULT 'uz',
            balance REAL DEFAULT 0,
            total_spent REAL DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            joined_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE NOT NULL,
            channel_name TEXT NOT NULL,
            added_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS linked_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT UNIQUE NOT NULL,
            bot_name TEXT NOT NULL,
            added_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS social_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            price REAL DEFAULT 0,
            total_parts INTEGER DEFAULT 1,
            added_at TEXT NOT NULL,
            added_by INTEGER
        );

        CREATE TABLE IF NOT EXISTS video_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            part_number INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY(video_id) REFERENCES videos(id)
        );

        CREATE TABLE IF NOT EXISTS user_purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_id INTEGER NOT NULL,
            paid_amount REAL DEFAULT 0,
            paid_at TEXT NOT NULL,
            UNIQUE(user_id, video_id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_id INTEGER,
            payment_type TEXT NOT NULL,
            amount REAL NOT NULL,
            check_file_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            confirmed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS top_up_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            check_file_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            confirmed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS start_message (
            id INTEGER PRIMARY KEY DEFAULT 1,
            msg_type TEXT DEFAULT 'text',
            content TEXT,
            photo_id TEXT,
            quote_or_link TEXT
        );

        CREATE TABLE IF NOT EXISTS help_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT,
            file_id TEXT,
            msg_type TEXT,
            sent_at TEXT NOT NULL
        );
        """)
        await db.commit()
    logger.info("Database initialized.")

# ─────────────────────────── HELPERS ───────────────────────────
async def get_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as cur:
            return await cur.fetchone()

async def ensure_user(msg: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO users (telegram_id, username, full_name, language, joined_at)
            VALUES (?,?,?,?,?)
        """, (msg.from_user.id, msg.from_user.username, msg.from_user.full_name,
              'uz', tashkent_now().isoformat()))
        await db.execute("""
            UPDATE users SET username=?, full_name=? WHERE telegram_id=?
        """, (msg.from_user.username, msg.from_user.full_name, msg.from_user.id))
        await db.commit()

async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def is_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    return user and user['is_banned'] == 1

async def check_subscriptions(bot: Bot, user_id: int) -> list:
    """Obuna bo'lmagan kanallar ro'yxatini qaytaradi"""
    not_subscribed = []
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM channels") as cur:
            channels = await cur.fetchall()
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch[1], user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                not_subscribed.append(ch)
        except:
            not_subscribed.append(ch)
    return not_subscribed

async def get_start_message():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM start_message WHERE id=1") as cur:
            return await cur.fetchone()

def get_lang(user_row) -> str:
    if user_row:
        return user_row['language']
    return 'uz'

# ─────────────────────────── TRANSLATIONS ───────────────────────────
T = {
    'uz': {
        'choose_lang': "🌐 Tilni tanlang / Выберите язык:",
        'lang_set': "✅ Til o'rnatildi: O'zbek",
        'main_menu': "🏠 Bosh menyu",
        'btn_videos': "🎬 Videolar",
        'btn_account': "💳 Hisobim",
        'btn_help': "❓ Yordam / Help",
        'btn_admin': "⚙️ Admin panel",
        'enter_code': "🔑 Video kodini kiriting:",
        'code_not_found': "❌ Bunday kod topilmadi.",
        'choose_part': "🎬 {title}\n\nQaysi qismni ko'rmoqchisiz?",
        'paid_video': "💰 Bu video pullik: {price} so'm\n\nTo'lov usulini tanlang:",
        'btn_pay_card': "💳 Karta orqali to'lov",
        'btn_pay_balance': "💰 Balansdan to'lov",
        'btn_share': "📤 Do'stlarga ulashish",
        'btn_close': "❌ Yopish",
        'send_check': "📎 Chek (rasm yoki fayl) yuboring.\nKarta: <code>{card}</code>\nSumma: {amount} so'm",
        'check_sent': "✅ Chekingiz adminga yuborildi. Tasdiqlash kutilmoqda.",
        'balance_info': "💳 Hisobingiz\n\nID: <code>{id}</code>\nBalans: {balance} so'm\nJami sarflangan: {spent} so'm",
        'btn_top_up': "➕ Hisobni to'ldirish",
        'enter_top_up': "Qancha so'm kiritmoqchisiz? (raqam kiriting)",
        'send_top_up_check': "📎 To'lov chekini yuboring.\nKarta: <code>{card}</code>\nSumma: {amount} so'm",
        'top_up_sent': "✅ So'rovingiz yuborildi. Admin tasdiqlashini kuting.",
        'not_subscribed': "❗ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
        'btn_check_sub': "✅ Tekshirish",
        'help_send': "✍️ Xabar, rasm, stiker yoki ovozli xabar yuboring. Admin javob beradi.",
        'help_sent': "✅ Xabaringiz adminga yuborildi.",
        'btn_reply': "↩️ Javob yuborish",
        'balance_added': "✅ Hisobingizga {amount} so'm qo'shildi.",
        'payment_confirmed': "✅ To'lovingiz tasdiqlandi! Video qismini yuklashingiz mumkin.",
        'payment_rejected': "❌ To'lovingiz rad etildi. Muammo bo'lsa adminga murojaat qiling.",
        'banned': "🚫 Siz ban qilindingiz.",
        'welcome': "👋 Xush kelibsiz!",
        'insufficient_balance': "❌ Balansingiz yetarli emas. Hisobni to'ldiring.",
        'already_purchased': "✅ Siz bu videoni allaqachon sotib olgansi. Qismni tanlang:",
        'video_free': "✅ Bu video bepul!",
    },
    'ru': {
        'choose_lang': "🌐 Tilni tanlang / Выберите язык:",
        'lang_set': "✅ Язык установлен: Русский",
        'main_menu': "🏠 Главное меню",
        'btn_videos': "🎬 Видео",
        'btn_account': "💳 Мой счёт",
        'btn_help': "❓ Помощь / Help",
        'btn_admin': "⚙️ Админ панель",
        'enter_code': "🔑 Введите код видео:",
        'code_not_found': "❌ Такой код не найден.",
        'choose_part': "🎬 {title}\n\nКакую часть хотите посмотреть?",
        'paid_video': "💰 Это платное видео: {price} сум\n\nВыберите способ оплаты:",
        'btn_pay_card': "💳 Оплата картой",
        'btn_pay_balance': "💰 Оплата с баланса",
        'btn_share': "📤 Поделиться с друзьями",
        'btn_close': "❌ Закрыть",
        'send_check': "📎 Отправьте чек (фото или файл).\nКарта: <code>{card}</code>\nСумма: {amount} сум",
        'check_sent': "✅ Ваш чек отправлен администратору. Ожидайте подтверждения.",
        'balance_info': "💳 Ваш счёт\n\nID: <code>{id}</code>\nБаланс: {balance} сум\nВсего потрачено: {spent} сум",
        'btn_top_up': "➕ Пополнить счёт",
        'enter_top_up': "Сколько сум хотите внести? (введите число)",
        'send_top_up_check': "📎 Отправьте чек оплаты.\nКарта: <code>{card}</code>\nСумма: {amount} сум",
        'top_up_sent': "✅ Ваш запрос отправлен. Ожидайте подтверждения администратора.",
        'not_subscribed': "❗ Для использования бота подпишитесь на следующие каналы:",
        'btn_check_sub': "✅ Проверить",
        'help_send': "✍️ Отправьте сообщение, фото, стикер или голосовое. Администратор ответит.",
        'help_sent': "✅ Ваше сообщение отправлено администратору.",
        'btn_reply': "↩️ Ответить",
        'balance_added': "✅ На ваш счёт добавлено {amount} сум.",
        'payment_confirmed': "✅ Оплата подтверждена! Теперь вы можете смотреть видео.",
        'payment_rejected': "❌ Ваш платёж отклонён. Обратитесь к администратору.",
        'banned': "🚫 Вы заблокированы.",
        'welcome': "👋 Добро пожаловать!",
        'insufficient_balance': "❌ Недостаточно средств. Пополните баланс.",
        'already_purchased': "✅ Вы уже купили это видео. Выберите часть:",
        'video_free': "✅ Это видео бесплатное!",
    }
}

def t(lang: str, key: str, **kwargs) -> str:
    text = T.get(lang, T['uz']).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text

# ─────────────────────────── KEYBOARD BUILDERS ───────────────────────────
def main_menu_kb(lang: str, is_adm: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=t(lang, 'btn_videos'))],
        [KeyboardButton(text=t(lang, 'btn_account')), KeyboardButton(text=t(lang, 'btn_help'))],
    ]
    if is_adm:
        buttons.append([KeyboardButton(text=t(lang, 'btn_admin'))])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="set_lang:uz"),
         InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru")]
    ])

def subscribe_kb(channels: list) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        ch_id = ch[1] if isinstance(ch, (list, tuple)) else ch['channel_id']
        ch_name = ch[2] if isinstance(ch, (list, tuple)) else ch['channel_name']
        link = ch_id if ch_id.startswith("http") else f"https://t.me/{ch_id.lstrip('@')}"
        rows.append([InlineKeyboardButton(text=f"📢 {ch_name}", url=link)])
    rows.append([InlineKeyboardButton(text="✅ Tekshirish / Проверить", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def parts_kb(video_id: int, total_parts: int, lang: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i in range(1, total_parts + 1):
        row.append(InlineKeyboardButton(text=f"{i}-qism" if lang=='uz' else f"Часть {i}",
                                        callback_data=f"watch:{video_id}:{i}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text=t(lang, 'btn_share'), callback_data=f"share:{video_id}"),
        InlineKeyboardButton(text=t(lang, 'btn_close'), callback_data="close_video")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def payment_kb(lang: str, video_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, 'btn_pay_card'), callback_data=f"pay_card:{video_id}")],
        [InlineKeyboardButton(text=t(lang, 'btn_pay_balance'), callback_data=f"pay_balance:{video_id}")],
        [InlineKeyboardButton(text=t(lang, 'btn_close'), callback_data="close_video")]
    ])

def confirm_payment_kb(payment_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_pay:{payment_id}:{user_id}"),
         InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_pay:{payment_id}:{user_id}")]
    ])

def confirm_topup_kb(topup_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_topup:{topup_id}:{user_id}"),
         InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_topup:{topup_id}:{user_id}")]
    ])

def go_user_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Xabar yuborish", url=f"tg://user?id={user_id}")]
    ])

def reply_to_user_kb(user_id: int, help_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Javob yuborish", callback_data=f"reply_help:{user_id}:{help_id}")]
    ])

# ─────────────────────────── ADMIN PANEL ───────────────────────────
def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Video qo'shish", callback_data="admin:add_video")],
        [InlineKeyboardButton(text="📢 Kanal qo'shish", callback_data="admin:add_channel"),
         InlineKeyboardButton(text="🤖 Bot qo'shish", callback_data="admin:add_bot")],
        [InlineKeyboardButton(text="📸 Instagram", callback_data="admin:instagram"),
         InlineKeyboardButton(text="▶️ YouTube", callback_data="admin:youtube")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin:stats"),
         InlineKeyboardButton(text="📈 Statistika (rasm)", callback_data="admin:stats_img")],
        [InlineKeyboardButton(text="👥 Obunchilar", callback_data="admin:subscribers")],
        [InlineKeyboardButton(text="📣 Xabar yuborish", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="💰 ID ga pul qo'sh", callback_data="admin:add_balance")],
        [InlineKeyboardButton(text="💰 Barchaga pul qo'sh", callback_data="admin:add_all_balance")],
        [InlineKeyboardButton(text="🚫 Ban qilish", callback_data="admin:ban"),
         InlineKeyboardButton(text="✅ Bandan chiqarish", callback_data="admin:unban")],
        [InlineKeyboardButton(text="✏️ Start xabar", callback_data="admin:start_msg")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="admin:close")],
    ])

# ─────────────────────────── STATISTICS IMAGE ───────────────────────────
async def generate_stats_image() -> bytes:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned=0") as cur:
            active_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM videos") as cur:
            total_videos = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(paid_amount),0) FROM user_purchases") as cur:
            total_revenue = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM payments WHERE status='confirmed'") as cur:
            confirmed_payments = (await cur.fetchone())[0]
        # Last 7 days users
        days_data = []
        for i in range(6, -1, -1):
            day = tashkent_now() - timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{day_str}%",)
            ) as cur:
                count = (await cur.fetchone())[0]
            days_data.append((day.strftime("%d.%m"), count))

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.patch.set_facecolor('#0d1117')

    for ax in axes.flat:
        ax.set_facecolor('#161b22')

    # Pie chart
    ax1 = axes[0][0]
    vals = [active_users, total_users - active_users]
    labels = [f"Faol: {active_users}", f"Ban: {total_users - active_users}"]
    colors = ['#2ea043', '#da3633']
    ax1.pie(vals if sum(vals) > 0 else [1, 0], labels=labels, colors=colors,
            autopct='%1.0f%%', textprops={'color': 'white', 'fontsize': 11})
    ax1.set_title("Foydalanuvchilar", color='white', fontsize=13, fontweight='bold')

    # Bar: last 7 days
    ax2 = axes[0][1]
    xlabels = [d[0] for d in days_data]
    ycounts = [d[1] for d in days_data]
    bars = ax2.bar(xlabels, ycounts, color='#1f6feb', edgecolor='#388bfd')
    ax2.set_title("So'nggi 7 kun - yangi foydalanuvchilar", color='white', fontsize=11, fontweight='bold')
    ax2.tick_params(colors='white')
    for spine in ax2.spines.values():
        spine.set_edgecolor('#30363d')
    ax2.yaxis.label.set_color('white')
    for bar in bars:
        h = bar.get_height()
        if h > 0:
            ax2.annotate(f'{int(h)}', xy=(bar.get_x() + bar.get_width()/2, h),
                        xytext=(0, 3), textcoords="offset points", ha='center', color='white', fontsize=9)

    # Stats summary
    ax3 = axes[1][0]
    ax3.axis('off')
    summary = (
        f"📊 STATISTIKA\n\n"
        f"👥 Jami foydalanuvchilar: {total_users}\n"
        f"✅ Faol: {active_users}\n"
        f"🚫 Banned: {total_users - active_users}\n"
        f"🎬 Jami videolar: {total_videos}\n"
        f"💰 Jami daromad: {total_revenue:,.0f} so'm\n"
        f"✅ Tasdiqlangan to'lovlar: {confirmed_payments}\n\n"
        f"🕐 {tashkent_now().strftime('%d.%m.%Y %H:%M')} (Toshkent)"
    )
    ax3.text(0.05, 0.95, summary, transform=ax3.transAxes, fontsize=12,
             verticalalignment='top', color='white',
             bbox=dict(boxstyle='round', facecolor='#21262d', edgecolor='#30363d'))

    # Revenue bar
    ax4 = axes[1][1]
    async with aiosqlite.connect(DB_PATH) as db:
        month_revenue = []
        for i in range(4, -1, -1):
            m = tashkent_now() - timedelta(days=30*i)
            month_str = m.strftime("%Y-%m")
            async with db.execute(
                "SELECT COALESCE(SUM(paid_amount),0) FROM user_purchases WHERE paid_at LIKE ?",
                (f"{month_str}%",)
            ) as cur:
                rev = (await cur.fetchone())[0]
            month_revenue.append((m.strftime("%m.%Y"), rev))

    mx = [d[0] for d in month_revenue]
    my = [d[1] for d in month_revenue]
    ax4.bar(mx, my, color='#3fb950', edgecolor='#56d364')
    ax4.set_title("Oylik daromad (so'm)", color='white', fontsize=11, fontweight='bold')
    ax4.tick_params(colors='white')
    for spine in ax4.spines.values():
        spine.set_edgecolor('#30363d')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    buf.seek(0)
    return buf.read()

# ─────────────────────────── ROUTER ───────────────────────────
router = Router()

# ═══════════════════════════ /start ═══════════════════════════
@router.message(CommandStart())
async def cmd_start(msg: Message, bot: Bot, state: FSMContext):
    await state.clear()
    await ensure_user(msg)
    user = await get_user(msg.from_user.id)

    if await is_banned(msg.from_user.id):
        await msg.answer(t(get_lang(user), 'banned'))
        return

    not_subbed = await check_subscriptions(bot, msg.from_user.id)
    if not_subbed:
        lang = get_lang(user)
        await msg.answer(t(lang, 'not_subscribed'), reply_markup=subscribe_kb(not_subbed))
        return

    # Til tanlanmagan bo'lsa
    if not user or user['language'] not in ('uz', 'ru'):
        await msg.answer(t('uz', 'choose_lang'), reply_markup=lang_kb())
        return

    await send_start_message(msg, bot, user)

async def send_start_message(msg: Message, bot: Bot, user):
    lang = get_lang(user)
    is_adm = await is_admin(msg.from_user.id)
    start_msg = await get_start_message()
    kb = main_menu_kb(lang, is_adm)

    if start_msg:
        msg_type = start_msg['msg_type']
        content = start_msg['content'] or t(lang, 'welcome')
        photo_id = start_msg['photo_id']
        quote_link = start_msg['quote_or_link']

        if msg_type == 'photo' and photo_id:
            await msg.answer_photo(photo_id, caption=content, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif msg_type == 'quote' and quote_link:
            text = f"💬 <i>{content}</i>\n\n🔗 {quote_link}" if quote_link else f"💬 <i>{content}</i>"
            await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif msg_type == 'link' and quote_link:
            text = f"{content}\n\n🔗 {quote_link}"
            await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await msg.answer(content, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await msg.answer(t(lang, 'welcome'), reply_markup=kb)

# ═══════════════════════════ TIL TANLASH ═══════════════════════════
@router.callback_query(F.data.startswith("set_lang:"))
async def set_lang(call: CallbackQuery, bot: Bot):
    lang = call.data.split(":")[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET language=? WHERE telegram_id=?", (lang, call.from_user.id))
        await db.commit()
    user = await get_user(call.from_user.id)
    await call.answer(t(lang, 'lang_set'))
    await call.message.delete()
    is_adm = await is_admin(call.from_user.id)
    not_subbed = await check_subscriptions(bot, call.from_user.id)
    if not_subbed:
        await call.message.answer(t(lang, 'not_subscribed'), reply_markup=subscribe_kb(not_subbed))
        return
    await send_start_message(call.message, bot, user)

# ═══════════════════════════ OBUNA TEKSHIRISH ═══════════════════════════
@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot: Bot):
    user = await get_user(call.from_user.id)
    lang = get_lang(user)
    not_subbed = await check_subscriptions(bot, call.from_user.id)
    if not_subbed:
        await call.answer("❌ Hali obuna bo'lmagan kanallar bor!", show_alert=True)
    else:
        await call.message.delete()
        await send_start_message(call.message, bot, user)

# ═══════════════════════════ VIDEOLAR ═══════════════════════════
@router.message(F.text.in_(["🎬 Videolar", "🎬 Видео"]))
async def videos_menu(msg: Message, state: FSMContext):
    user = await get_user(msg.from_user.id)
    lang = get_lang(user)
    await state.set_state(UserStates.waiting_code)
    await msg.answer(t(lang, 'enter_code'), reply_markup=ReplyKeyboardRemove())

@router.message(UserStates.waiting_code)
async def process_code(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = await get_user(msg.from_user.id)
    lang = get_lang(user)
    code = msg.text.strip()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE code=?", (code,)) as cur:
            video = await cur.fetchone()

    if not video:
        await msg.answer(t(lang, 'code_not_found'),
                         reply_markup=main_menu_kb(lang, await is_admin(msg.from_user.id)))
        return

    # Sotib olinganmi tekshir
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM user_purchases WHERE user_id=? AND video_id=?",
            (msg.from_user.id, video['id'])
        ) as cur:
            purchased = await cur.fetchone()

    if video['price'] > 0 and not purchased:
        text = t(lang, 'paid_video', price=f"{video['price']:,.0f}")
        await msg.answer(f"🎬 <b>{video['title']}</b>\n\n{text}",
                         parse_mode=ParseMode.HTML,
                         reply_markup=payment_kb(lang, video['id']))
    else:
        if purchased:
            await msg.answer(t(lang, 'already_purchased'))
        else:
            await msg.answer(t(lang, 'video_free'))
        await show_video_parts(msg, video, lang)

async def show_video_parts(msg: Message, video, lang: str):
    text = t(lang, 'choose_part', title=video['title'])
    await msg.answer(text, reply_markup=parts_kb(video['id'], video['total_parts'], lang))

# ═══════════════════════════ VIDEO QISMLARINI KO'RISH ═══════════════════════════
@router.callback_query(F.data.startswith("watch:"))
async def watch_part(call: CallbackQuery, bot: Bot):
    _, video_id, part_num = call.data.split(":")
    video_id, part_num = int(video_id), int(part_num)
    user = await get_user(call.from_user.id)
    lang = get_lang(user)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM video_parts WHERE video_id=? AND part_number=?",
                               (video_id, part_num)) as cur:
            part = await cur.fetchone()
        async with db.execute("SELECT * FROM videos WHERE id=?", (video_id,)) as cur:
            video = await cur.fetchone()

    if not part:
        await call.answer("❌ Qism topilmadi.", show_alert=True)
        return

    close_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, 'btn_share'), callback_data=f"share:{video_id}"),
         InlineKeyboardButton(text=t(lang, 'btn_close'), callback_data="close_video")]
    ])

    caption = f"🎬 <b>{video['title']}</b> - {part_num}-qism\n\n"
    if part['description']:
        caption += part['description']

    await call.message.answer_video(part['file_id'], caption=caption,
                                    parse_mode=ParseMode.HTML, reply_markup=close_kb)
    await call.answer()

@router.callback_query(F.data == "close_video")
async def close_video(call: CallbackQuery):
    await call.message.delete()
    await call.answer()

@router.callback_query(F.data.startswith("share:"))
async def share_video(call: CallbackQuery, bot: Bot):
    video_id = call.data.split(":")[1]
    bot_info = await bot.get_me()
    share_text = f"https://t.me/{bot_info.username}"
    await call.message.answer(f"📤 Do'stlarga ulashing:\n{share_text}")
    await call.answer()

# ═══════════════════════════ TO'LOV (KARTA) ═══════════════════════════
@router.callback_query(F.data.startswith("pay_card:"))
async def pay_card(call: CallbackQuery, state: FSMContext):
    video_id = int(call.data.split(":")[1])
    user = await get_user(call.from_user.id)
    lang = get_lang(user)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE id=?", (video_id,)) as cur:
            video = await cur.fetchone()

    await state.set_data({"video_id": video_id, "amount": video['price']})
    await state.set_state(UserStates.waiting_payment_check)
    await call.message.answer(
        t(lang, 'send_check', card=PAYMENT_CARD, amount=f"{video['price']:,.0f}"),
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.message(UserStates.waiting_payment_check, F.photo | F.document)
async def receive_payment_check(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    video_id = data.get("video_id")
    amount = data.get("amount", 0)
    await state.clear()

    user = await get_user(msg.from_user.id)
    lang = get_lang(user)

    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO payments (user_id, video_id, payment_type, amount, check_file_id, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (msg.from_user.id, video_id, 'video', amount, file_id, 'pending', tashkent_now().isoformat())
        )
        pay_id = cur.lastrowid
        await db.commit()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE id=?", (video_id,)) as cur:
            video = await cur.fetchone()

    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"💰 <b>Yangi to'lov so'rovi!</b>\n\n"
                f"👤 Foydalanuvchi: {msg.from_user.full_name} (<code>{msg.from_user.id}</code>)\n"
                f"🎬 Video: {video['title'] if video else '?'}\n"
                f"💵 Summa: {amount:,.0f} so'm\n"
                f"🕐 Vaqt: {tashkent_now().strftime('%d.%m.%Y %H:%M')}"
            )
            if msg.photo:
                await bot.send_photo(admin_id, file_id, caption=admin_text,
                                     parse_mode=ParseMode.HTML,
                                     reply_markup=confirm_payment_kb(pay_id, msg.from_user.id))
            else:
                await bot.send_document(admin_id, file_id, caption=admin_text,
                                        parse_mode=ParseMode.HTML,
                                        reply_markup=confirm_payment_kb(pay_id, msg.from_user.id))
        except:
            pass

    await msg.answer(t(lang, 'check_sent'),
                     reply_markup=main_menu_kb(lang, await is_admin(msg.from_user.id)))

# ═══════════════════════════ TO'LOV (BALANSDAN) ═══════════════════════════
@router.callback_query(F.data.startswith("pay_balance:"))
async def pay_balance(call: CallbackQuery, bot: Bot):
    video_id = int(call.data.split(":")[1])
    user = await get_user(call.from_user.id)
    lang = get_lang(user)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE id=?", (video_id,)) as cur:
            video = await cur.fetchone()

    if user['balance'] < video['price']:
        await call.answer(t(lang, 'insufficient_balance'), show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance-?, total_spent=total_spent+? WHERE telegram_id=?",
                         (video['price'], video['price'], call.from_user.id))
        await db.execute(
            "INSERT OR IGNORE INTO user_purchases (user_id, video_id, paid_amount, paid_at) VALUES (?,?,?,?)",
            (call.from_user.id, video_id, video['price'], tashkent_now().isoformat())
        )
        await db.execute(
            "INSERT INTO payments (user_id, video_id, payment_type, amount, status, created_at, confirmed_at) VALUES (?,?,?,?,?,?,?)",
            (call.from_user.id, video_id, 'balance', video['price'], 'confirmed',
             tashkent_now().isoformat(), tashkent_now().isoformat())
        )
        await db.commit()

    await call.message.delete()
    await call.message.answer(t(lang, 'payment_confirmed'))
    await show_video_parts(call.message, video, lang)
    await call.answer()

# ═══════════════════════════ ADMIN: TO'LOV TASDIQLASH ═══════════════════════════
@router.callback_query(F.data.startswith("confirm_pay:"))
async def admin_confirm_pay(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    _, pay_id, user_id = call.data.split(":")
    pay_id, user_id = int(pay_id), int(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payments WHERE id=?", (pay_id,)) as cur:
            payment = await cur.fetchone()
        if payment and payment['status'] == 'pending':
            await db.execute("UPDATE payments SET status='confirmed', confirmed_at=? WHERE id=?",
                             (tashkent_now().isoformat(), pay_id))
            await db.execute(
                "INSERT OR IGNORE INTO user_purchases (user_id, video_id, paid_amount, paid_at) VALUES (?,?,?,?)",
                (user_id, payment['video_id'], payment['amount'], tashkent_now().isoformat())
            )
            await db.commit()

    user = await get_user(user_id)
    lang = get_lang(user)
    try:
        await bot.send_message(user_id, t(lang, 'payment_confirmed'))
        # Video qismlarini ko'rsatish
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM videos WHERE id=?", (payment['video_id'],)) as cur:
                video = await cur.fetchone()
        if video:
            await bot.send_message(
                user_id,
                t(lang, 'choose_part', title=video['title']),
                reply_markup=parts_kb(video['id'], video['total_parts'], lang)
            )
    except:
        pass

    await call.message.edit_caption(call.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
                                    parse_mode=ParseMode.HTML, reply_markup=None)
    await call.answer("✅ Tasdiqlandi")

@router.callback_query(F.data.startswith("reject_pay:"))
async def admin_reject_pay(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    _, pay_id, user_id = call.data.split(":")
    pay_id, user_id = int(pay_id), int(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE payments SET status='rejected' WHERE id=?", (pay_id,))
        await db.commit()

    user = await get_user(user_id)
    lang = get_lang(user)
    try:
        await bot.send_message(user_id, t(lang, 'payment_rejected'))
    except:
        pass

    await call.message.edit_caption(call.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
                                    parse_mode=ParseMode.HTML, reply_markup=None)
    await call.answer("❌ Rad etildi")

# ═══════════════════════════ HISOBIM ═══════════════════════════
@router.message(F.text.in_(["💳 Hisobim", "💳 Мой счёт"]))
async def account_menu(msg: Message):
    user = await get_user(msg.from_user.id)
    lang = get_lang(user)
    text = t(lang, 'balance_info',
             id=msg.from_user.id,
             balance=f"{user['balance']:,.0f}",
             spent=f"{user['total_spent']:,.0f}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, 'btn_top_up'), callback_data="top_up")]
    ])
    await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data == "top_up")
async def top_up_start(call: CallbackQuery, state: FSMContext):
    user = await get_user(call.from_user.id)
    lang = get_lang(user)
    await state.set_state(UserStates.waiting_top_up_amount)
    await call.message.answer(t(lang, 'enter_top_up'))
    await call.answer()

@router.message(UserStates.waiting_top_up_amount)
async def top_up_amount(msg: Message, state: FSMContext):
    user = await get_user(msg.from_user.id)
    lang = get_lang(user)
    try:
        amount = float(msg.text.strip())
    except:
        await msg.answer("❌ Raqam kiriting!")
        return
    await state.set_data({"top_up_amount": amount})
    await state.set_state(UserStates.waiting_top_up_check)
    await msg.answer(t(lang, 'send_top_up_check', card=PAYMENT_CARD, amount=f"{amount:,.0f}"),
                     parse_mode=ParseMode.HTML)

@router.message(UserStates.waiting_top_up_check, F.photo | F.document)
async def top_up_check(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get("top_up_amount", 0)
    await state.clear()

    user = await get_user(msg.from_user.id)
    lang = get_lang(user)
    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO top_up_payments (user_id, amount, check_file_id, status, created_at) VALUES (?,?,?,?,?)",
            (msg.from_user.id, amount, file_id, 'pending', tashkent_now().isoformat())
        )
        topup_id = cur.lastrowid
        await db.commit()

    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"💳 <b>Hisobni to'ldirish so'rovi!</b>\n\n"
                f"👤 {msg.from_user.full_name} (<code>{msg.from_user.id}</code>)\n"
                f"💵 Summa: {amount:,.0f} so'm\n"
                f"🕐 {tashkent_now().strftime('%d.%m.%Y %H:%M')}"
            )
            if msg.photo:
                await bot.send_photo(admin_id, file_id, caption=admin_text,
                                     parse_mode=ParseMode.HTML,
                                     reply_markup=confirm_topup_kb(topup_id, msg.from_user.id))
            else:
                await bot.send_document(admin_id, file_id, caption=admin_text,
                                        parse_mode=ParseMode.HTML,
                                        reply_markup=confirm_topup_kb(topup_id, msg.from_user.id))
        except:
            pass

    await msg.answer(t(lang, 'top_up_sent'),
                     reply_markup=main_menu_kb(lang, await is_admin(msg.from_user.id)))

@router.callback_query(F.data.startswith("confirm_topup:"))
async def confirm_topup(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    _, topup_id, user_id = call.data.split(":")
    topup_id, user_id = int(topup_id), int(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM top_up_payments WHERE id=?", (topup_id,)) as cur:
            topup = await cur.fetchone()
        if topup and topup['status'] == 'pending':
            await db.execute("UPDATE top_up_payments SET status='confirmed', confirmed_at=? WHERE id=?",
                             (tashkent_now().isoformat(), topup_id))
            await db.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?",
                             (topup['amount'], user_id))
            await db.commit()

    user = await get_user(user_id)
    lang = get_lang(user)
    try:
        await bot.send_message(user_id, t(lang, 'balance_added', amount=f"{topup['amount']:,.0f}"))
    except:
        pass

    await call.message.edit_caption(call.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
                                    parse_mode=ParseMode.HTML, reply_markup=None)
    await call.answer("✅ Tasdiqlandi")

@router.callback_query(F.data.startswith("reject_topup:"))
async def reject_topup(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    _, topup_id, user_id = call.data.split(":")
    topup_id, user_id = int(topup_id), int(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE top_up_payments SET status='rejected' WHERE id=?", (topup_id,))
        await db.commit()

    user = await get_user(user_id)
    lang = get_lang(user)
    try:
        await bot.send_message(user_id, t(lang, 'payment_rejected'))
    except:
        pass

    await call.message.edit_caption(call.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
                                    parse_mode=ParseMode.HTML, reply_markup=None)
    await call.answer("❌ Rad etildi")

# ═══════════════════════════ YORDAM / HELP ═══════════════════════════
@router.message(F.text.in_(["❓ Yordam / Help", "❓ Помощь / Help"]))
async def help_menu(msg: Message, state: FSMContext):
    user = await get_user(msg.from_user.id)
    lang = get_lang(user)
    await state.set_state(UserStates.waiting_help_msg)
    await msg.answer(t(lang, 'help_send'), reply_markup=ReplyKeyboardRemove())

@router.message(UserStates.waiting_help_msg)
async def receive_help_msg(msg: Message, state: FSMContext, bot: Bot):
    user = await get_user(msg.from_user.id)
    lang = get_lang(user)
    await state.clear()

    file_id = None
    msg_type = 'text'
    content = msg.text or msg.caption or ""

    if msg.photo:
        file_id = msg.photo[-1].file_id
        msg_type = 'photo'
    elif msg.document:
        file_id = msg.document.file_id
        msg_type = 'document'
    elif msg.sticker:
        file_id = msg.sticker.file_id
        msg_type = 'sticker'
    elif msg.voice:
        file_id = msg.voice.file_id
        msg_type = 'voice'
    elif msg.video:
        file_id = msg.video.file_id
        msg_type = 'video'

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO help_messages (user_id, content, file_id, msg_type, sent_at) VALUES (?,?,?,?,?)",
            (msg.from_user.id, content, file_id, msg_type, tashkent_now().isoformat())
        )
        help_id = cur.lastrowid
        await db.commit()

    admin_text = (
        f"❓ <b>Yordam so'rovi</b>\n\n"
        f"👤 {msg.from_user.full_name} (<code>{msg.from_user.id}</code>)\n"
        f"🕐 {tashkent_now().strftime('%d.%m.%Y %H:%M')}"
    )
    if content:
        admin_text += f"\n\n💬 {content}"

    reply_kb = reply_to_user_kb(msg.from_user.id, help_id)

    for admin_id in ADMIN_IDS:
        try:
            if msg_type == 'photo':
                await bot.send_photo(admin_id, file_id, caption=admin_text,
                                     parse_mode=ParseMode.HTML, reply_markup=reply_kb)
            elif msg_type == 'document':
                await bot.send_document(admin_id, file_id, caption=admin_text,
                                        parse_mode=ParseMode.HTML, reply_markup=reply_kb)
            elif msg_type == 'sticker':
                await bot.send_message(admin_id, admin_text, parse_mode=ParseMode.HTML)
                await bot.send_sticker(admin_id, file_id)
                await bot.send_message(admin_id, "👆 Stiker", reply_markup=reply_kb)
            elif msg_type == 'voice':
                await bot.send_voice(admin_id, file_id, caption=admin_text,
                                     parse_mode=ParseMode.HTML, reply_markup=reply_kb)
            elif msg_type == 'video':
                await bot.send_video(admin_id, file_id, caption=admin_text,
                                     parse_mode=ParseMode.HTML, reply_markup=reply_kb)
            else:
                await bot.send_message(admin_id, admin_text, parse_mode=ParseMode.HTML,
                                       reply_markup=reply_kb)
        except:
            pass

    await msg.answer(t(lang, 'help_sent'),
                     reply_markup=main_menu_kb(lang, await is_admin(msg.from_user.id)))

# Admin: foydalanuvchiga javob
@router.callback_query(F.data.startswith("reply_help:"))
async def admin_reply_help(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    _, user_id, help_id = call.data.split(":")
    await state.set_data({"reply_to_user": int(user_id)})
    await state.set_state(AdminStates.waiting_broadcast_content)
    await call.message.answer(f"✍️ Foydalanuvchiga javob yuboring (ID: {user_id}):")
    await call.answer()

# ═══════════════════════════ ADMIN PANEL ═══════════════════════════
@router.message(F.text.in_(["⚙️ Admin panel", "⚙️ Админ панель"]))
async def admin_panel(msg: Message):
    if not await is_admin(msg.from_user.id):
        return
    await msg.answer("⚙️ <b>Admin panel</b>", parse_mode=ParseMode.HTML,
                     reply_markup=admin_panel_kb())

@router.callback_query(F.data == "admin:close")
async def admin_close(call: CallbackQuery):
    await call.message.delete()

# ─────── VIDEO QO'SHISH ───────
@router.callback_query(F.data == "admin:add_video")
async def admin_add_video(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_video)
    await call.message.answer("🎬 Video yuboring (birinchi qism):")
    await call.answer()

@router.message(AdminStates.waiting_video, F.video)
async def admin_receive_video(msg: Message, state: FSMContext):
    await state.update_data({"parts": [{"file_id": msg.video.file_id, "part": 1}], "current_part": 1})
    await state.set_state(AdminStates.waiting_video_part)
    await msg.answer(
        "✅ 1-qism qabul qilindi.\n\nYana boshqa qismlar kiritasizmi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ha, yana qism", callback_data="more_parts:yes"),
             InlineKeyboardButton(text="❌ Yo'q, o'tkazib yuborish", callback_data="more_parts:no")]
        ])
    )

@router.callback_query(F.data == "more_parts:yes")
async def more_parts_yes(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    next_part = data['current_part'] + 1
    await state.update_data({"current_part": next_part})
    await state.set_state(AdminStates.waiting_video)
    await call.message.answer(f"🎬 {next_part}-qismni yuboring:")
    await call.answer()

@router.callback_query(F.data == "more_parts:no")
async def more_parts_no(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_part_text)
    data = await state.get_data()
    parts = data.get('parts', [])
    await call.message.answer(
        f"✅ {len(parts)} ta qism qabul qilindi.\n\n"
        "📝 Har bir qism uchun tavsif matnini kiriting.\n"
        "1-qism uchun matn:"
    )
    await state.update_data({"part_texts": [], "text_index": 0})
    await call.answer()

@router.message(AdminStates.waiting_part_text)
async def admin_part_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    texts = data.get('part_texts', [])
    texts.append(msg.text)
    parts = data.get('parts', [])

    if len(texts) < len(parts):
        await state.update_data({"part_texts": texts})
        await msg.answer(f"{len(texts)+1}-qism uchun matn:")
    else:
        await state.update_data({"part_texts": texts})
        await state.set_state(AdminStates.waiting_video_title)
        await msg.answer("📌 Video nomini kiriting:")

@router.message(AdminStates.waiting_video_title)
async def admin_video_title(msg: Message, state: FSMContext):
    await state.update_data({"title": msg.text})
    await state.set_state(AdminStates.waiting_video_code)
    await msg.answer("🔑 Video uchun kod kiriting (foydalanuvchilar shu kodni kiritadi):")

@router.message(AdminStates.waiting_video_code)
async def admin_video_code(msg: Message, state: FSMContext):
    await state.update_data({"code": msg.text.strip()})
    await state.set_state(AdminStates.waiting_video_price)
    await msg.answer("💰 Narxni kiriting (bepul bo'lsa 0 kiriting):")

@router.message(AdminStates.waiting_video_price)
async def admin_video_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.strip())
    except:
        await msg.answer("❌ Raqam kiriting!")
        return

    data = await state.get_data()
    await state.clear()

    parts = data.get('parts', [])
    part_texts = data.get('part_texts', [''] * len(parts))
    title = data.get('title', 'Nomsiz')
    code = data.get('code', 'CODE')

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute(
                "INSERT INTO videos (title, code, price, total_parts, added_at, added_by) VALUES (?,?,?,?,?,?)",
                (title, code, price, len(parts), tashkent_now().isoformat(), msg.from_user.id)
            )
            video_id = cur.lastrowid
            for i, part in enumerate(parts):
                desc = part_texts[i] if i < len(part_texts) else ""
                await db.execute(
                    "INSERT INTO video_parts (video_id, part_number, file_id, description) VALUES (?,?,?,?)",
                    (video_id, part['part'], part['file_id'], desc)
                )
            await db.commit()
            await msg.answer(
                f"✅ Video qo'shildi!\n\n"
                f"📌 Nom: {title}\n"
                f"🔑 Kod: <code>{code}</code>\n"
                f"💰 Narx: {price:,.0f} so'm\n"
                f"🎬 Qismlar: {len(parts)}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await msg.answer(f"❌ Xato: {e}")

# ─────── KANAL QO'SHISH ───────
@router.callback_query(F.data == "admin:add_channel")
async def admin_add_channel(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_channel_id)
    await call.message.answer("📢 Kanal ID yoki username kiriting\n(masalan: @mychanel yoki -1001234567890):")
    await call.answer()

@router.message(AdminStates.waiting_channel_id)
async def admin_channel_id(msg: Message, state: FSMContext):
    await state.update_data({"channel_id": msg.text.strip()})
    await state.set_state(AdminStates.waiting_channel_name)
    await msg.answer("📝 Kanal nomini kiriting:")

@router.message(AdminStates.waiting_channel_name)
async def admin_channel_name(msg: Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data['channel_id']
    channel_name = msg.text.strip()
    await state.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT OR REPLACE INTO channels (channel_id, channel_name, added_at) VALUES (?,?,?)",
                (channel_id, channel_name, tashkent_now().isoformat())
            )
            await db.commit()
            await msg.answer(f"✅ Kanal qo'shildi: {channel_name}")
        except Exception as e:
            await msg.answer(f"❌ Xato: {e}")

# ─────── BOT QO'SHISH ───────
@router.callback_query(F.data == "admin:add_bot")
async def admin_add_bot(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_bot_token_add)
    await call.message.answer("🤖 Bot token kiriting:")
    await call.answer()

@router.message(AdminStates.waiting_bot_token_add)
async def admin_bot_token(msg: Message, state: FSMContext):
    await state.update_data({"bot_token": msg.text.strip()})
    await state.set_state(AdminStates.waiting_bot_name)
    await msg.answer("📝 Bot nomini kiriting:")

@router.message(AdminStates.waiting_bot_name)
async def admin_bot_name(msg: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO linked_bots (bot_token, bot_name, added_at) VALUES (?,?,?)",
            (data['bot_token'], msg.text.strip(), tashkent_now().isoformat())
        )
        await db.commit()
    await state.clear()
    await msg.answer(f"✅ Bot qo'shildi: {msg.text.strip()}")

# ─────── INSTAGRAM / YOUTUBE ───────
@router.callback_query(F.data == "admin:instagram")
async def admin_instagram(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_instagram)
    await call.message.answer("📸 Instagram havolasini kiriting:")
    await call.answer()

@router.message(AdminStates.waiting_instagram)
async def save_instagram(msg: Message, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO social_links (platform, url) VALUES (?,?)",
                         ('instagram', msg.text.strip()))
        await db.commit()
    await state.clear()
    await msg.answer("✅ Instagram havolasi saqlandi.")

@router.callback_query(F.data == "admin:youtube")
async def admin_youtube(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_youtube)
    await call.message.answer("▶️ YouTube havolasini kiriting:")
    await call.answer()

@router.message(AdminStates.waiting_youtube)
async def save_youtube(msg: Message, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO social_links (platform, url) VALUES (?,?)",
                         ('youtube', msg.text.strip()))
        await db.commit()
    await state.clear()
    await msg.answer("✅ YouTube havolasi saqlandi.")

# ─────── STATISTIKA ───────
@router.callback_query(F.data == "admin:stats")
async def admin_stats(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned=0") as cur:
            active = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM videos") as cur:
            videos = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(paid_amount),0) FROM user_purchases") as cur:
            revenue = (await cur.fetchone())[0]

    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total}</b>\n"
        f"✅ Faol: <b>{active}</b>\n"
        f"🚫 Banned: <b>{total - active}</b>\n"
        f"🎬 Videolar: <b>{videos}</b>\n"
        f"💰 Jami daromad: <b>{revenue:,.0f} so'm</b>\n\n"
        f"🕐 {tashkent_now().strftime('%d.%m.%Y %H:%M')} (Toshkent)"
    )
    await call.message.answer(text, parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data == "admin:stats_img")
async def admin_stats_img(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    await call.answer("📊 Rasm tayyorlanmoqda...")
    img_bytes = await generate_stats_image()
    await bot.send_photo(
        call.from_user.id,
        BufferedInputFile(img_bytes, filename="stats.png"),
        caption=f"📊 Statistika rasmi\n🕐 {tashkent_now().strftime('%d.%m.%Y %H:%M')}"
    )

# ─────── OBUNCHILAR ───────
@router.callback_query(F.data == "admin:subscribers")
async def admin_subscribers(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY joined_at DESC LIMIT 20") as cur:
            users = await cur.fetchall()

    if not users:
        await call.message.answer("👥 Foydalanuvchilar yo'q.")
        return

    for u in users:
        name = u['full_name'] or "Noma'lum"
        username = f"@{u['username']}" if u['username'] else "—"
        joined = fmt_dt(u['joined_at'])
        text = (
            f"👤 <b>{name}</b> ({username})\n"
            f"🆔 ID: <code>{u['telegram_id']}</code>\n"
            f"📅 Qo'shilgan: {joined}\n"
            f"💰 Balans: {u['balance']:,.0f} so'm"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Xabar yuborish",
                                  url=f"tg://user?id={u['telegram_id']}")]
        ])
        await call.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)

    await call.answer()

# ─────── XABAR YUBORISH (BROADCAST) ───────
@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_broadcast_content)
    await state.update_data({"reply_to_user": None})
    await call.message.answer("📣 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabarni yuboring:")
    await call.answer()

@router.message(AdminStates.waiting_broadcast_content)
async def admin_broadcast_send(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    reply_to_user = data.get("reply_to_user")
    await state.clear()

    if reply_to_user:
        # Bitta foydalanuvchiga javob
        try:
            if msg.photo:
                await bot.send_photo(reply_to_user, msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.document:
                await bot.send_document(reply_to_user, msg.document.file_id, caption=msg.caption or "")
            elif msg.voice:
                await bot.send_voice(reply_to_user, msg.voice.file_id)
            elif msg.video:
                await bot.send_video(reply_to_user, msg.video.file_id, caption=msg.caption or "")
            elif msg.sticker:
                await bot.send_sticker(reply_to_user, msg.sticker.file_id)
            else:
                await bot.send_message(reply_to_user, msg.text or "")
            await msg.answer(f"✅ Javob {reply_to_user} ga yuborildi.")
        except Exception as e:
            await msg.answer(f"❌ Xato: {e}")
        return

    # Broadcast
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT telegram_id FROM users WHERE is_banned=0") as cur:
            users = await cur.fetchall()

    sent, failed = 0, 0
    for (uid,) in users:
        try:
            if msg.photo:
                await bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "",
                                     parse_mode=ParseMode.HTML)
            elif msg.document:
                await bot.send_document(uid, msg.document.file_id, caption=msg.caption or "",
                                        parse_mode=ParseMode.HTML)
            elif msg.voice:
                await bot.send_voice(uid, msg.voice.file_id)
            elif msg.video:
                await bot.send_video(uid, msg.video.file_id, caption=msg.caption or "",
                                     parse_mode=ParseMode.HTML)
            elif msg.sticker:
                await bot.send_sticker(uid, msg.sticker.file_id)
            else:
                await bot.send_message(uid, msg.text or "", parse_mode=ParseMode.HTML)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)

    await msg.answer(f"✅ Xabar yuborildi!\n✅ Muvaffaqiyatli: {sent}\n❌ Xato: {failed}")

# ─────── PUL QO'SHISH ───────
@router.callback_query(F.data == "admin:add_balance")
async def admin_add_balance(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_add_balance_id)
    await call.message.answer("🆔 Foydalanuvchi ID raqamini kiriting:")
    await call.answer()

@router.message(AdminStates.waiting_add_balance_id)
async def admin_add_balance_id(msg: Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        await state.update_data({"target_uid": uid})
        await state.set_state(AdminStates.waiting_add_balance_amount)
        await msg.answer("💰 Qo'shiladigan summani kiriting:")
    except:
        await msg.answer("❌ ID raqam kiriting!")

@router.message(AdminStates.waiting_add_balance_amount)
async def admin_add_balance_amount(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data['target_uid']
    await state.clear()
    try:
        amount = float(msg.text.strip())
    except:
        await msg.answer("❌ Raqam kiriting!")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (amount, uid))
        await db.commit()

    user = await get_user(uid)
    lang = get_lang(user)
    try:
        await bot.send_message(uid, t(lang, 'balance_added', amount=f"{amount:,.0f}"))
    except:
        pass
    await msg.answer(f"✅ {uid} ga {amount:,.0f} so'm qo'shildi.")

@router.callback_query(F.data == "admin:add_all_balance")
async def admin_add_all_balance(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_add_all_balance)
    await call.message.answer("💰 Barcha foydalanuvchilarga qo'shiladigan summani kiriting:")
    await call.answer()

@router.message(AdminStates.waiting_add_all_balance)
async def admin_add_all_balance_amount(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    try:
        amount = float(msg.text.strip())
    except:
        await msg.answer("❌ Raqam kiriting!")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE is_banned=0", (amount,))
        await db.commit()
        async with db.execute("SELECT telegram_id FROM users WHERE is_banned=0") as cur:
            users = await cur.fetchall()

    for (uid,) in users:
        try:
            user = await get_user(uid)
            lang = get_lang(user)
            await bot.send_message(uid, t(lang, 'balance_added', amount=f"{amount:,.0f}"))
        except:
            pass
        await asyncio.sleep(0.05)

    await msg.answer(f"✅ Barcha foydalanuvchilarga {amount:,.0f} so'm qo'shildi.")

# ─────── BAN / UNBAN ───────
@router.callback_query(F.data == "admin:ban")
async def admin_ban(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_ban_id)
    await call.message.answer("🚫 Ban qilinuvchi foydalanuvchi ID raqamini kiriting:")
    await call.answer()

@router.message(AdminStates.waiting_ban_id)
async def admin_ban_user(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    try:
        uid = int(msg.text.strip())
    except:
        await msg.answer("❌ ID raqam kiriting!")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=1 WHERE telegram_id=?", (uid,))
        await db.commit()

    try:
        await bot.send_message(uid, "🚫 Siz ban qilindingiz.")
    except:
        pass
    await msg.answer(f"✅ {uid} ban qilindi.")

@router.callback_query(F.data == "admin:unban")
async def admin_unban(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_unban_id)
    await call.message.answer("✅ Bandan chiqariluvchi foydalanuvchi ID raqamini kiriting:")
    await call.answer()

@router.message(AdminStates.waiting_unban_id)
async def admin_unban_user(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    try:
        uid = int(msg.text.strip())
    except:
        await msg.answer("❌ ID raqam kiriting!")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=0 WHERE telegram_id=?", (uid,))
        await db.commit()

    try:
        await bot.send_message(uid, "✅ Bandan chiqarildingiz.")
    except:
        pass
    await msg.answer(f"✅ {uid} bandan chiqarildi.")

# ─────── START XABAR ───────
@router.callback_query(F.data == "admin:start_msg")
async def admin_start_msg(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_start_msg_type)
    await call.message.answer(
        "✏️ Start xabar turini tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Oddiy matn", callback_data="start_type:text")],
            [InlineKeyboardButton(text="🖼 Rasm + matn", callback_data="start_type:photo")],
            [InlineKeyboardButton(text="💬 Iqtibos xabar", callback_data="start_type:quote")],
            [InlineKeyboardButton(text="🔗 Link xabar", callback_data="start_type:link")],
        ])
    )
    await call.answer()

@router.callback_query(F.data.startswith("start_type:"))
async def start_type_selected(call: CallbackQuery, state: FSMContext):
    msg_type = call.data.split(":")[1]
    await state.update_data({"start_msg_type": msg_type})

    if msg_type == 'photo':
        await state.set_state(AdminStates.waiting_start_photo)
        await call.message.answer("🖼 Rasm yuboring:")
    elif msg_type in ('quote', 'link'):
        await state.set_state(AdminStates.waiting_start_text)
        await call.message.answer("✏️ Matn kiriting:")
    else:
        await state.set_state(AdminStates.waiting_start_text)
        await call.message.answer("✏️ Matn kiriting:")
    await call.answer()

@router.message(AdminStates.waiting_start_photo, F.photo)
async def start_photo_received(msg: Message, state: FSMContext):
    await state.update_data({"start_photo_id": msg.photo[-1].file_id})
    await state.set_state(AdminStates.waiting_start_text)
    await msg.answer("✏️ Rasm uchun matn kiriting:")

@router.message(AdminStates.waiting_start_text)
async def start_text_received(msg: Message, state: FSMContext):
    data = await state.get_data()
    msg_type = data.get('start_msg_type', 'text')
    await state.update_data({"start_text": msg.text})

    if msg_type in ('quote', 'link'):
        await state.set_state(AdminStates.waiting_start_quote_link)
        label = "Iqtibos manbasi yoki havola:" if msg_type == 'quote' else "Havola (URL) kiriting:"
        await msg.answer(f"🔗 {label}")
    else:
        # Save
        await save_start_message(msg, state, data)

@router.message(AdminStates.waiting_start_quote_link)
async def start_quote_link_received(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data({"start_quote_link": msg.text})
    await save_start_message(msg, state, data)

async def save_start_message(msg: Message, state: FSMContext, data: dict = None):
    if data is None:
        data = await state.get_data()
    await state.clear()

    msg_type = data.get('start_msg_type', 'text')
    content = data.get('start_text', '')
    photo_id = data.get('start_photo_id')
    quote_link = data.get('start_quote_link')

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM start_message")
        await db.execute(
            "INSERT INTO start_message (id, msg_type, content, photo_id, quote_or_link) VALUES (1,?,?,?,?)",
            (msg_type, content, photo_id, quote_link)
        )
        await db.commit()

    await msg.answer(
        f"✅ Start xabar saqlandi!\n"
        f"Tur: {msg_type}\n"
        f"Matn: {content[:50] if content else '—'}"
    )

# ═══════════════════════════ MAIN ═══════════════════════════
async def main():
    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logger.info("Bot ishga tushirildi!")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
