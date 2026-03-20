import os
import logging
from datetime import datetime
import pytz
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
import sqlite3
import asyncio

# ===================== SOZLAMALAR =====================
BOT_TOKEN = "8655776547:AAEKHHQfCjvdwIgn_y4PH7de-b3g2Jd5iYs"  # Bot tokenini shu yerga kiriting
ADMIN_IDS = [8537782289]  # Admin Telegram ID larini shu yerga kiriting
TASHKENT_TZ = pytz.timezone("Asia/Tashkent")

# ===================== DATABASE =====================
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        tg_id INTEGER UNIQUE,
        username TEXT,
        full_name TEXT,
        phone TEXT,
        balance REAL DEFAULT 0,
        joined_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        title TEXT,
        info1 TEXT,
        info2 TEXT,
        file_id1 TEXT,
        file_id2 TEXT,
        price1 REAL DEFAULT 0,
        price2 REAL DEFAULT 0,
        created_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS movie_parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        part_number INTEGER,
        file_id TEXT,
        info TEXT,
        price REAL DEFAULT 0
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER,
        amount REAL,
        type TEXT,
        movie_code TEXT,
        status TEXT DEFAULT 'pending',
        check_file_id TEXT,
        created_at TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT,
        channel_link TEXT,
        channel_name TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        url TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER,
        message_id INTEGER,
        admin_message_id INTEGER,
        status TEXT DEFAULT 'open'
    )""")
    
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect("bot.db")

def get_user(tg_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
    row = c.fetchone()
    conn.close()
    return row

def register_user(tg_id, username, full_name):
    conn = db()
    c = conn.cursor()
    now = datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR IGNORE INTO users (tg_id, username, full_name, joined_at) VALUES (?,?,?,?)",
              (tg_id, username, full_name, now))
    conn.commit()
    conn.close()

def get_balance(tg_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE tg_id=?", (tg_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def add_balance(tg_id, amount):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE tg_id=?", (amount, tg_id))
    conn.commit()
    conn.close()

def deduct_balance(tg_id, amount):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance - ? WHERE tg_id=?", (amount, tg_id))
    conn.commit()
    conn.close()

def get_movie(code):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM movies WHERE code=?", (code,))
    row = c.fetchone()
    conn.close()
    return row

def get_movie_parts(code):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM movie_parts WHERE code=? ORDER BY part_number", (code,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_setting(key, default=""):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

def get_channels():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM channels")
    rows = c.fetchall()
    conn.close()
    return rows

def get_links():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM links")
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_users():
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY joined_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def now_tashkent():
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S")

# ===================== CONVERSATION STATES =====================
(
    WAIT_CODE, WAIT_TOPUP_AMOUNT, WAIT_CHECK,
    WAIT_SUPPORT_MSG, WAIT_ADMIN_REPLY,
    # Admin states
    ADM_VIDEO1, ADM_VIDEO2, ADM_INFO1, ADM_INFO2,
    ADM_PRICE1, ADM_PRICE2, ADM_MOVIE_CODE,
    ADM_CONTINUATION_CODE, ADM_CONT_VIDEO, ADM_CONT_INFO, ADM_CONT_PRICE, ADM_CONT_PART_NUM,
    ADM_START_MSG, ADM_START_PHOTO,
    ADM_CHANNEL_ID, ADM_CHANNEL_LINK, ADM_CHANNEL_NAME,
    ADM_LINK_TITLE, ADM_LINK_URL,
    ADM_BROADCAST_MSG,
    ADM_SEND_USER_ID, ADM_SEND_USER_MSG,
    ADM_ADD_BALANCE_ID, ADM_ADD_BALANCE_AMOUNT,
    ADM_ADD_ALL_BALANCE,
    ADM_APPROVE_CHECK,
    ADM_TOPUP_CARD,
) = range(32)

# ===================== HELPERS =====================
async def check_subscription(bot, user_id):
    channels = get_channels()
    not_joined = []
    for ch in channels:
        ch_id = ch[1]
        try:
            member = await bot.get_chat_member(ch_id, user_id)
            if member.status in ["left", "kicked", "banned"]:
                not_joined.append(ch)
        except:
            not_joined.append(ch)
    return not_joined

def is_admin(user_id):
    return user_id in ADMIN_IDS

def main_menu():
    keyboard = [
        [KeyboardButton("💰 Hisobim"), KeyboardButton("🆘 Yordam")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def admin_menu():
    keyboard = [
        ["🎬 Kino qo'shish", "➕ Kino davomini qo'shish"],
        ["📢 Kanal qo'shish", "🔗 Link qo'shish"],
        ["📨 Barcha foydalanuvchilarga xabar", "📩 ID orqali xabar"],
        ["💵 ID orqali pul qo'shish", "💰 Barcha hisobiga pul qo'shish"],
        ["📊 Statistika", "⚙️ Start xabarini o'zgartirish"],
        ["🏠 Asosiy menyu"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ===================== START =====================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username, user.full_name)
    
    not_joined = await check_subscription(ctx.bot, user.id)
    if not_joined:
        btns = []
        for ch in not_joined:
            btns.append([InlineKeyboardButton(f"📢 {ch[3]}", url=ch[2])])
        btns.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=InlineKeyboardMarkup(btns)
        )
        return
    
    start_photo = get_setting("start_photo")
    start_text = get_setting("start_text", "🎬 Kino botga xush kelibsiz!\n\nKino kodini yuboring.")
    
    if start_photo:
        await update.message.reply_photo(
            photo=start_photo,
            caption=start_text,
            reply_markup=main_menu()
        )
    else:
        await update.message.reply_text(start_text, reply_markup=main_menu())

async def check_sub_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    not_joined = await check_subscription(ctx.bot, query.from_user.id)
    if not_joined:
        btns = []
        for ch in not_joined:
            btns.append([InlineKeyboardButton(f"📢 {ch[3]}", url=ch[2])])
        btns.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
        await query.edit_message_text(
            "⚠️ Hali obuna bo'lmagan kanallar mavjud:",
            reply_markup=InlineKeyboardMarkup(btns)
        )
    else:
        user = query.from_user
        start_photo = get_setting("start_photo")
        start_text = get_setting("start_text", "🎬 Kino botga xush kelibsiz!\n\nKino kodini yuboring.")
        await query.message.delete()
        if start_photo:
            await ctx.bot.send_photo(
                chat_id=query.from_user.id,
                photo=start_photo,
                caption=start_text,
                reply_markup=main_menu()
            )
        else:
            await ctx.bot.send_message(
                chat_id=query.from_user.id,
                text=start_text,
                reply_markup=main_menu()
            )

# ===================== HISOBIM =====================
async def my_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    balance = get_balance(user.id)
    
    # Oxirgi tranzaksiyalar
    conn = db()
    c = conn.cursor()
    c.execute("""SELECT amount, type, movie_code, created_at FROM transactions 
                 WHERE tg_id=? AND status='approved' ORDER BY created_at DESC LIMIT 5""", (user.id,))
    txs = c.fetchall()
    conn.close()
    
    tx_text = ""
    for tx in txs:
        tx_text += f"\n  {'➕' if tx[1]=='topup' else '🎬'} {tx[0]:,.0f} so'm - {tx[3]}"
    
    text = (
        f"👤 <b>Hisobim</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Ism: {user.full_name}\n"
        f"💰 Balans: <b>{balance:,.0f} so'm</b>\n"
    )
    if tx_text:
        text += f"\n📋 <b>Oxirgi amallar:</b>{tx_text}"
    
    keyboard = [[InlineKeyboardButton("💳 Hisobni to'ldirish", callback_data="topup")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def topup_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("💵 Qancha pul kiritmoqchisiz? (so'mda kiriting, masalan: 50000)")
    return WAIT_TOPUP_AMOUNT

async def topup_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Faqat raqam kiriting!")
        return WAIT_TOPUP_AMOUNT
    amount = int(text)
    ctx.user_data["topup_amount"] = amount
    
    card = get_setting("topup_card", "Karta raqam kiritilmagan")
    await update.message.reply_text(
        f"💳 To'lov kartasi: <b>{card}</b>\n\n"
        f"💰 Miqdor: <b>{amount:,.0f} so'm</b>\n\n"
        f"Yuqoridagi kartaga pul o'tkazing va chekni yuboring.",
        parse_mode=ParseMode.HTML
    )
    return WAIT_CHECK

async def receive_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount = ctx.user_data.get("topup_amount", 0)
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Chek (rasm yoki fayl) yuboring!")
        return WAIT_CHECK
    
    conn = db()
    c = conn.cursor()
    now = now_tashkent()
    c.execute("INSERT INTO transactions (tg_id, amount, type, status, check_file_id, created_at) VALUES (?,?,?,?,?,?)",
              (user.id, amount, "topup", "pending", file_id, now))
    tx_id = c.lastrowid
    conn.commit()
    conn.close()
    
    for admin_id in ADMIN_IDS:
        try:
            btns = [
                [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_topup_{tx_id}_{user.id}_{amount}"),
                 InlineKeyboardButton("❌ Bekor qilish", callback_data=f"reject_topup_{tx_id}_{user.id}")]
            ]
            caption = (
                f"💰 <b>Hisobni to'ldirish so'rovi</b>\n\n"
                f"👤 Foydalanuvchi: {user.full_name}\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"📱 Username: @{user.username or 'yo\'q'}\n"
                f"💵 Miqdor: <b>{amount:,.0f} so'm</b>\n"
                f"🕐 Vaqt: {now}"
            )
            await ctx.bot.send_photo(chat_id=admin_id, photo=file_id, caption=caption,
                                     reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
        except:
            pass
    
    await update.message.reply_text(
        "✅ Chekingiz adminga yuborildi. Tez orada hisobingiz to'ldiriladi!",
        reply_markup=main_menu()
    )
    return ConversationHandler.END

async def approve_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split("_")
    tx_id = int(parts[2])
    user_tg_id = int(parts[3])
    amount = float(parts[4])
    
    add_balance(user_tg_id, amount)
    
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE transactions SET status='approved' WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()
    
    try:
        await ctx.bot.send_message(
            chat_id=user_tg_id,
            text=f"✅ Hisobingiz <b>{amount:,.0f} so'm</b>ga to'ldirildi!\n💰 Balans: {get_balance(user_tg_id):,.0f} so'm",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await query.edit_message_caption(caption=query.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode=ParseMode.HTML)

async def reject_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    
    parts = query.data.split("_")
    tx_id = int(parts[2])
    user_tg_id = int(parts[3])
    
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE transactions SET status='rejected' WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()
    
    try:
        await ctx.bot.send_message(chat_id=user_tg_id, text="❌ To'lov tasdiqlanmadi. Admin bilan bog'laning.")
    except:
        pass
    
    await query.edit_message_caption(caption=query.message.caption + "\n\n❌ <b>BEKOR QILINDI</b>", parse_mode=ParseMode.HTML)

# ===================== KINO KODI =====================
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    
    if text == "💰 Hisobim":
        return await my_account(update, ctx)
    elif text == "🆘 Yordam":
        return await support_start(update, ctx)
    elif text == "🎬 Kino qo'shish" and is_admin(user.id):
        return await adm_add_movie_start(update, ctx)
    elif text == "➕ Kino davomini qo'shish" and is_admin(user.id):
        return await adm_continuation_start(update, ctx)
    elif text == "📢 Kanal qo'shish" and is_admin(user.id):
        return await adm_add_channel_start(update, ctx)
    elif text == "🔗 Link qo'shish" and is_admin(user.id):
        return await adm_add_link_start(update, ctx)
    elif text == "📨 Barcha foydalanuvchilarga xabar" and is_admin(user.id):
        return await adm_broadcast_start(update, ctx)
    elif text == "📩 ID orqali xabar" and is_admin(user.id):
        return await adm_send_user_start(update, ctx)
    elif text == "💵 ID orqali pul qo'shish" and is_admin(user.id):
        return await adm_add_balance_start(update, ctx)
    elif text == "💰 Barcha hisobiga pul qo'shish" and is_admin(user.id):
        return await adm_add_all_balance_start(update, ctx)
    elif text == "📊 Statistika" and is_admin(user.id):
        return await adm_statistics(update, ctx)
    elif text == "⚙️ Start xabarini o'zgartirish" and is_admin(user.id):
        return await adm_start_msg(update, ctx)
    elif text == "🏠 Asosiy menyu":
        await update.message.reply_text("Asosiy menyu:", reply_markup=main_menu())
        return
    
    # Kino kodi
    not_joined = await check_subscription(ctx.bot, user.id)
    if not_joined:
        btns = [[InlineKeyboardButton(f"📢 {ch[3]}", url=ch[2])] for ch in not_joined]
        btns.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
        await update.message.reply_text("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=InlineKeyboardMarkup(btns))
        return
    
    # Movie code check
    parts = get_movie_parts(text)
    movie = get_movie(text)
    
    if not parts and not movie:
        await update.message.reply_text("❌ Bunday kod topilmadi. Iltimos, to'g'ri kod kiriting.")
        return
    
    all_parts = parts if parts else []
    
    if not all_parts:
        await update.message.reply_text("❌ Bu kinoning video qismlari topilmadi.")
        return
    
    # Check if free (price=0)
    total_price = sum(p[4] for p in all_parts)
    
    if total_price == 0:
        # Free movie - send directly
        movie_title = movie[2] if movie else text
        await update.message.reply_text(f"🎬 <b>{movie_title}</b>", parse_mode=ParseMode.HTML)
        for part in all_parts:
            part_num = part[2]
            file_id = part[3]
            info = part[4] if isinstance(part[4], str) else ""
            caption = f"📽 {part_num}-qism"
            if isinstance(part[4], str) and part[4]:
                caption += f"\n{part[4]}"
            await ctx.bot.send_video(chat_id=user.id, video=file_id, caption=caption)
        return
    
    # Paid movie
    balance = get_balance(user.id)
    movie_title = movie[2] if movie else text
    
    parts_info = ""
    for p in all_parts:
        price = p[4] if not isinstance(p[4], str) else 0
        # parts schema: id, code, part_number, file_id, info, price
        info_text = p[4] if isinstance(p[4], str) else ""
        pr = p[5] if len(p) > 5 else 0
        parts_info += f"\n  📽 {p[2]}-qism - {pr:,.0f} so'm"
    
    total = sum(p[5] for p in all_parts if len(p) > 5)
    
    text_msg = (
        f"🎬 <b>{movie_title}</b>\n"
        f"🔑 Kod: <code>{text}</code>\n"
        f"{parts_info}\n\n"
        f"💰 Jami narx: <b>{total:,.0f} so'm</b>\n"
        f"💳 Sizning balansingiz: <b>{balance:,.0f} so'm</b>"
    )
    
    btns = []
    if balance >= total:
        btns.append([InlineKeyboardButton(f"✅ Hisobdan to'lash ({total:,.0f} so'm)", callback_data=f"pay_balance_{text}")])
    else:
        btns.append([InlineKeyboardButton("💳 Hisobni to'ldirish", callback_data="topup")])
    btns.append([InlineKeyboardButton("💴 Karta orqali to'lash", callback_data=f"pay_card_{text}")])
    
    await update.message.reply_text(text_msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)

async def pay_balance_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    code = query.data.replace("pay_balance_", "")
    
    parts = get_movie_parts(code)
    movie = get_movie(code)
    
    if not parts:
        await query.message.reply_text("❌ Kino topilmadi.")
        return
    
    total = sum(p[5] for p in parts if len(p) > 5)
    balance = get_balance(user.id)
    
    if balance < total:
        await query.message.reply_text("❌ Balansingiz yetarli emas!")
        return
    
    deduct_balance(user.id, total)
    
    conn = db()
    c = conn.cursor()
    now = now_tashkent()
    c.execute("INSERT INTO transactions (tg_id, amount, type, movie_code, status, created_at) VALUES (?,?,?,?,?,?)",
              (user.id, total, "purchase", code, "approved", now))
    conn.commit()
    conn.close()
    
    movie_title = movie[2] if movie else code
    await query.message.reply_text(f"✅ To'lov amalga oshirildi!\n🎬 <b>{movie_title}</b>", parse_mode=ParseMode.HTML)
    
    for part in parts:
        caption = f"📽 {part[2]}-qism"
        if len(part) > 4 and isinstance(part[4], str) and part[4]:
            caption += f"\n{part[4]}"
        await ctx.bot.send_video(chat_id=user.id, video=part[3], caption=caption)

async def pay_card_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    code = query.data.replace("pay_card_", "")
    
    parts = get_movie_parts(code)
    if not parts:
        await query.message.reply_text("❌ Kino topilmadi.")
        return
    
    total = sum(p[5] for p in parts if len(p) > 5)
    card = get_setting("topup_card", "Karta raqam kiritilmagan")
    
    ctx.user_data["pay_card_code"] = code
    ctx.user_data["pay_card_amount"] = total
    
    await query.message.reply_text(
        f"💳 Karta: <b>{card}</b>\n"
        f"💰 Miqdor: <b>{total:,.0f} so'm</b>\n\n"
        f"To'lovni amalga oshiring va chekni yuboring.",
        parse_mode=ParseMode.HTML
    )
    return WAIT_CHECK

async def receive_movie_payment_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    code = ctx.user_data.get("pay_card_code")
    amount = ctx.user_data.get("pay_card_amount", 0)
    
    if not code:
        return ConversationHandler.END
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Chek (rasm) yuboring!")
        return WAIT_CHECK
    
    parts = get_movie_parts(code)
    movie = get_movie(code)
    movie_title = movie[2] if movie else code
    
    conn = db()
    c = conn.cursor()
    now = now_tashkent()
    c.execute("INSERT INTO transactions (tg_id, amount, type, movie_code, status, check_file_id, created_at) VALUES (?,?,?,?,?,?,?)",
              (user.id, amount, "purchase", code, "pending", file_id, now))
    tx_id = c.lastrowid
    conn.commit()
    conn.close()
    
    for admin_id in ADMIN_IDS:
        try:
            btns = [
                [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_movie_{tx_id}_{user.id}_{code}"),
                 InlineKeyboardButton("❌ Bekor qilish", callback_data=f"reject_movie_{tx_id}_{user.id}")]
            ]
            caption = (
                f"🎬 <b>Kino to'lovi</b>\n\n"
                f"👤 Ism: {user.full_name}\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"📱 Username: @{user.username or 'yo\'q'}\n"
                f"🎬 Kino: {movie_title} (kod: {code})\n"
                f"💵 Miqdor: <b>{amount:,.0f} so'm</b>\n"
                f"🕐 Vaqt: {now}"
            )
            await ctx.bot.send_photo(chat_id=admin_id, photo=file_id, caption=caption,
                                     reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.HTML)
        except:
            pass
    
    await update.message.reply_text("✅ Chekingiz adminga yuborildi!", reply_markup=main_menu())
    return ConversationHandler.END

async def approve_movie_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    
    parts_data = query.data.split("_")
    tx_id = int(parts_data[2])
    user_tg_id = int(parts_data[3])
    code = parts_data[4]
    
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE transactions SET status='approved' WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()
    
    parts = get_movie_parts(code)
    movie = get_movie(code)
    movie_title = movie[2] if movie else code
    
    try:
        await ctx.bot.send_message(
            chat_id=user_tg_id,
            text=f"✅ To'lovingiz tasdiqlandi!\n🎬 <b>{movie_title}</b>",
            parse_mode=ParseMode.HTML
        )
        for part in parts:
            caption = f"📽 {part[2]}-qism"
            if len(part) > 4 and isinstance(part[4], str) and part[4]:
                caption += f"\n{part[4]}"
            await ctx.bot.send_video(chat_id=user_tg_id, video=part[3], caption=caption)
    except Exception as e:
        logging.error(f"Error sending movie: {e}")
    
    await query.edit_message_caption(caption=query.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode=ParseMode.HTML)

async def reject_movie_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    
    parts_data = query.data.split("_")
    tx_id = int(parts_data[2])
    user_tg_id = int(parts_data[3])
    
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE transactions SET status='rejected' WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()
    
    try:
        await ctx.bot.send_message(chat_id=user_tg_id, text="❌ To'lovingiz rad etildi.")
    except:
        pass
    
    await query.edit_message_caption(caption=query.message.caption + "\n\n❌ <b>RAD ETILDI</b>", parse_mode=ParseMode.HTML)

# ===================== YORDAM =====================
async def support_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 <b>Yordam</b>\n\nAdminga xabaringizni yuboring (matn, rasm yoki ovozli xabar):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return WAIT_SUPPORT_MSG

async def receive_support_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=main_menu())
        return ConversationHandler.END
    
    for admin_id in ADMIN_IDS:
        try:
            header = (
                f"📩 <b>Foydalanuvchi xabari</b>\n"
                f"👤 {user.full_name} | 🆔 <code>{user.id}</code> | @{user.username or 'yo\'q'}"
            )
            # Forward message with context
            sent = await ctx.bot.send_message(chat_id=admin_id, text=header, parse_mode=ParseMode.HTML)
            
            if update.message.text:
                fwd = await ctx.bot.send_message(chat_id=admin_id, text=update.message.text)
            elif update.message.photo:
                fwd = await ctx.bot.send_photo(chat_id=admin_id, photo=update.message.photo[-1].file_id,
                                               caption=update.message.caption or "")
            elif update.message.voice:
                fwd = await ctx.bot.send_voice(chat_id=admin_id, voice=update.message.voice.file_id)
            elif update.message.video:
                fwd = await ctx.bot.send_video(chat_id=admin_id, video=update.message.video.file_id)
            elif update.message.document:
                fwd = await ctx.bot.send_document(chat_id=admin_id, document=update.message.document.file_id)
            else:
                fwd = await ctx.bot.send_message(chat_id=admin_id, text="[Noma'lum xabar turi]")
            
            # Add reply button
            reply_btn = [[InlineKeyboardButton("✍️ Javob yozish", callback_data=f"reply_user_{user.id}")]]
            await ctx.bot.send_message(
                chat_id=admin_id,
                text="Javob berish uchun tugmani bosing:",
                reply_markup=InlineKeyboardMarkup(reply_btn)
            )
        except Exception as e:
            logging.error(f"Support error: {e}")
    
    await update.message.reply_text("✅ Xabaringiz adminga yuborildi!", reply_markup=main_menu())
    return ConversationHandler.END

async def admin_reply_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    
    target_id = int(query.data.replace("reply_user_", ""))
    ctx.user_data["reply_target"] = target_id
    
    await query.message.reply_text(
        f"✍️ Foydalanuvchi (ID: {target_id})ga javob yozing:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return WAIT_ADMIN_REPLY

async def send_admin_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    target_id = ctx.user_data.get("reply_target")
    if not target_id:
        return ConversationHandler.END
    
    try:
        if update.message.text:
            await ctx.bot.send_message(chat_id=target_id, text=f"📨 Admin javobi:\n\n{update.message.text}")
        elif update.message.photo:
            await ctx.bot.send_photo(chat_id=target_id, photo=update.message.photo[-1].file_id,
                                     caption=f"📨 Admin javobi:\n{update.message.caption or ''}")
        elif update.message.voice:
            await ctx.bot.send_voice(chat_id=target_id, voice=update.message.voice.file_id)
        elif update.message.video:
            await ctx.bot.send_video(chat_id=target_id, video=update.message.video.file_id,
                                     caption=f"📨 Admin javobi:\n{update.message.caption or ''}")
        await update.message.reply_text("✅ Javob yuborildi!", reply_markup=admin_menu())
    except:
        await update.message.reply_text("❌ Xabar yuborishda xatolik.", reply_markup=admin_menu())
    
    return ConversationHandler.END

# ===================== ADMIN: KINO QO'SHISH =====================
async def adm_add_movie_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ctx.user_data.clear()
    ctx.user_data["movie_parts"] = []
    await update.message.reply_text(
        "🎬 Yangi kino qo'shish\n\n1-qism videosini yuboring:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_VIDEO1

async def adm_recv_video1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.video:
        await update.message.reply_text("❌ Video yuboring!")
        return ADM_VIDEO1
    
    ctx.user_data["video1"] = update.message.video.file_id
    
    btns = [["➕ 2-qism qo'shish", "⏭ Tugatish"]]
    await update.message.reply_text(
        "✅ 1-qism qabul qilindi!\n\n2-qism qo'shish yoki tugatish:",
        reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True)
    )
    return ADM_VIDEO2

async def adm_recv_video2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⏭ Tugatish" or update.message.text == "❌ Bekor qilish":
        if update.message.text == "❌ Bekor qilish":
            await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
            return ConversationHandler.END
        # Save with 1 part only, go to info
        ctx.user_data["video2"] = None
        await update.message.reply_text(
            "📝 1-qism uchun kino haqida ma'lumot kiriting:",
            reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
        )
        return ADM_INFO1
    
    if not update.message.video:
        await update.message.reply_text("❌ Video yuboring yoki 'Tugatish' tugmasini bosing!")
        return ADM_VIDEO2
    
    ctx.user_data["video2"] = update.message.video.file_id
    await update.message.reply_text(
        "✅ 2-qism qabul qilindi!\n\n📝 1-qism uchun kino haqida ma'lumot kiriting:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_INFO1

async def adm_recv_info1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    ctx.user_data["info1"] = update.message.text
    
    if ctx.user_data.get("video2"):
        await update.message.reply_text("📝 2-qism uchun ma'lumot kiriting:")
        return ADM_INFO2
    else:
        await update.message.reply_text("💰 1-qism narxini kiriting (bepul bo'lsa 0):")
        return ADM_PRICE1

async def adm_recv_info2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    ctx.user_data["info2"] = update.message.text
    await update.message.reply_text("💰 1-qism narxini kiriting (bepul bo'lsa 0):")
    return ADM_PRICE1

async def adm_recv_price1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Raqam kiriting!")
        return ADM_PRICE1
    
    ctx.user_data["price1"] = int(update.message.text)
    
    if ctx.user_data.get("video2"):
        await update.message.reply_text("💰 2-qism narxini kiriting (bepul bo'lsa 0):")
        return ADM_PRICE2
    else:
        await update.message.reply_text("🔑 Kino uchun kod kiriting:")
        return ADM_MOVIE_CODE

async def adm_recv_price2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Raqam kiriting!")
        return ADM_PRICE2
    
    ctx.user_data["price2"] = int(update.message.text)
    await update.message.reply_text("🔑 Kino uchun kod kiriting:")
    return ADM_MOVIE_CODE

async def adm_recv_movie_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    code = update.message.text.strip()
    
    existing = get_movie(code)
    if existing:
        await update.message.reply_text("❌ Bu kod allaqachon mavjud! Boshqa kod kiriting:")
        return ADM_MOVIE_CODE
    
    conn = db()
    c = conn.cursor()
    now = now_tashkent()
    
    # Save movie
    title = ctx.user_data.get("info1", code)
    c.execute("INSERT OR REPLACE INTO movies (code, title, info1, info2, file_id1, file_id2, price1, price2, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
              (code, title, ctx.user_data.get("info1", ""), ctx.user_data.get("info2", ""),
               ctx.user_data.get("video1"), ctx.user_data.get("video2"),
               ctx.user_data.get("price1", 0), ctx.user_data.get("price2", 0), now))
    
    # Save parts
    c.execute("INSERT INTO movie_parts (code, part_number, file_id, info, price) VALUES (?,?,?,?,?)",
              (code, 1, ctx.user_data.get("video1"), ctx.user_data.get("info1", ""), ctx.user_data.get("price1", 0)))
    
    if ctx.user_data.get("video2"):
        c.execute("INSERT INTO movie_parts (code, part_number, file_id, info, price) VALUES (?,?,?,?,?)",
                  (code, 2, ctx.user_data.get("video2"), ctx.user_data.get("info2", ""), ctx.user_data.get("price2", 0)))
    
    conn.commit()
    conn.close()
    
    parts_count = 2 if ctx.user_data.get("video2") else 1
    await update.message.reply_text(
        f"✅ Kino saqlandi!\n🔑 Kod: <code>{code}</code>\n📽 Qismlar: {parts_count}",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_menu()
    )
    return ConversationHandler.END

# ===================== ADMIN: KINO DAVOMINI QO'SHISH =====================
async def adm_continuation_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "➕ Kino davomini qo'shish\n\nKino kodini kiriting:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_CONTINUATION_CODE

async def adm_cont_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    code = update.message.text.strip()
    parts = get_movie_parts(code)
    
    if not parts:
        await update.message.reply_text("❌ Bu kodli kino topilmadi!")
        return ADM_CONTINUATION_CODE
    
    next_part = max(p[2] for p in parts) + 1
    ctx.user_data["cont_code"] = code
    ctx.user_data["cont_part"] = next_part
    
    await update.message.reply_text(f"✅ Topildi! Joriy qismlar: {len(parts)}\n\n{next_part}-qism videosini yuboring:")
    return ADM_CONT_VIDEO

async def adm_cont_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.video:
        await update.message.reply_text("❌ Video yuboring!")
        return ADM_CONT_VIDEO
    
    ctx.user_data["cont_video"] = update.message.video.file_id
    part = ctx.user_data["cont_part"]
    await update.message.reply_text(f"📝 {part}-qism uchun ma'lumot kiriting:")
    return ADM_CONT_INFO

async def adm_cont_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    ctx.user_data["cont_info"] = update.message.text
    part = ctx.user_data["cont_part"]
    await update.message.reply_text(f"💰 {part}-qism narxini kiriting (bepul bo'lsa 0):")
    return ADM_CONT_PRICE

async def adm_cont_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Raqam kiriting!")
        return ADM_CONT_PRICE
    
    code = ctx.user_data["cont_code"]
    part = ctx.user_data["cont_part"]
    video = ctx.user_data["cont_video"]
    info = ctx.user_data["cont_info"]
    price = int(update.message.text)
    
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO movie_parts (code, part_number, file_id, info, price) VALUES (?,?,?,?,?)",
              (code, part, video, info, price))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ {part}-qism saqlandi!\n🔑 Kod: <code>{code}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_menu()
    )
    return ConversationHandler.END

# ===================== ADMIN: START XABARI =====================
async def adm_start_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "⚙️ Start xabarini o'zgartirish\n\nAvval rasm yuboring (yo'q bo'lsa 'O'tkazib yuborish' bosing):",
        reply_markup=ReplyKeyboardMarkup([["⏭ O'tkazib yuborish", "❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_START_PHOTO

async def adm_start_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if update.message.text == "⏭ O'tkazib yuborish":
        ctx.user_data["start_photo"] = None
    elif update.message.photo:
        ctx.user_data["start_photo"] = update.message.photo[-1].file_id
    else:
        await update.message.reply_text("❌ Rasm yuboring yoki o'tkazib yuboring!")
        return ADM_START_PHOTO
    
    await update.message.reply_text("📝 Start xabari matnini kiriting:")
    return ADM_START_MSG

async def adm_start_msg_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    text = update.message.text
    photo = ctx.user_data.get("start_photo")
    
    set_setting("start_text", text)
    if photo:
        set_setting("start_photo", photo)
    elif ctx.user_data.get("start_photo") is None:
        set_setting("start_photo", "")
    
    await update.message.reply_text("✅ Start xabari saqlandi!", reply_markup=admin_menu())
    return ConversationHandler.END

# ===================== ADMIN: KANAL QO'SHISH =====================
async def adm_add_channel_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    channels = get_channels()
    ch_list = "\n".join([f"  • {c[3]} ({c[1]})" for c in channels]) if channels else "  Hali kanal yo'q"
    
    await update.message.reply_text(
        f"📢 Majburiy kanallar:\n{ch_list}\n\nYangi kanal ID sini kiriting (masalan: @channel yoki -1001234567890):",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_CHANNEL_ID

async def adm_channel_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    ctx.user_data["new_ch_id"] = update.message.text.strip()
    await update.message.reply_text("🔗 Kanal havolasini kiriting (masalan: https://t.me/channel):")
    return ADM_CHANNEL_LINK

async def adm_channel_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    ctx.user_data["new_ch_link"] = update.message.text.strip()
    await update.message.reply_text("📛 Kanal nomini kiriting:")
    return ADM_CHANNEL_NAME

async def adm_channel_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    name = update.message.text.strip()
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO channels (channel_id, channel_link, channel_name) VALUES (?,?,?)",
              (ctx.user_data["new_ch_id"], ctx.user_data["new_ch_link"], name))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Kanal qo'shildi: {name}", reply_markup=admin_menu())
    return ConversationHandler.END

# ===================== ADMIN: LINK QO'SHISH =====================
async def adm_add_link_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    links = get_links()
    link_list = "\n".join([f"  • {l[1]}: {l[2]}" for l in links]) if links else "  Hali link yo'q"
    await update.message.reply_text(
        f"🔗 Saqlangan linklar:\n{link_list}\n\nYangi link sarlavhasini kiriting:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_LINK_TITLE

async def adm_link_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    ctx.user_data["new_link_title"] = update.message.text.strip()
    await update.message.reply_text("🔗 Link URL sini kiriting:")
    return ADM_LINK_URL

async def adm_link_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    url = update.message.text.strip()
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO links (title, url) VALUES (?,?)", (ctx.user_data["new_link_title"], url))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Link qo'shildi!", reply_markup=admin_menu())
    return ConversationHandler.END

# ===================== ADMIN: BROADCAST =====================
async def adm_broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "📨 Barcha foydalanuvchilarga xabar yuborish\n\nXabarni yuboring (matn, rasm, video - qanday yuborsa shunday boradi):",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_BROADCAST_MSG

async def adm_broadcast_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    users = get_all_users()
    sent = 0
    failed = 0
    
    status_msg = await update.message.reply_text(f"📤 Yuborilmoqda... (0/{len(users)})")
    
    for i, user in enumerate(users):
        try:
            if update.message.text:
                await ctx.bot.send_message(chat_id=user[1], text=update.message.text)
            elif update.message.photo:
                await ctx.bot.send_photo(chat_id=user[1], photo=update.message.photo[-1].file_id,
                                         caption=update.message.caption or "")
            elif update.message.video:
                await ctx.bot.send_video(chat_id=user[1], video=update.message.video.file_id,
                                         caption=update.message.caption or "")
            elif update.message.voice:
                await ctx.bot.send_voice(chat_id=user[1], voice=update.message.voice.file_id)
            elif update.message.document:
                await ctx.bot.send_document(chat_id=user[1], document=update.message.document.file_id,
                                            caption=update.message.caption or "")
            sent += 1
        except:
            failed += 1
        
        if (i + 1) % 10 == 0:
            try:
                await status_msg.edit_text(f"📤 Yuborilmoqda... ({i+1}/{len(users)})")
            except:
                pass
        
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(f"✅ Xabar yuborildi!\n✅ Muvaffaqiyatli: {sent}\n❌ Xatolik: {failed}")
    await update.message.reply_text("Tayyor!", reply_markup=admin_menu())
    return ConversationHandler.END

# ===================== ADMIN: ID ORQALI XABAR =====================
async def adm_send_user_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "📩 ID orqali xabar yuborish\n\nFoydalanuvchi ID sini kiriting:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_SEND_USER_ID

async def adm_send_user_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Faqat raqam kiriting!")
        return ADM_SEND_USER_ID
    
    ctx.user_data["send_target_id"] = int(update.message.text)
    await update.message.reply_text("✍️ Xabarni yuboring:")
    return ADM_SEND_USER_MSG

async def adm_send_user_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    target = ctx.user_data.get("send_target_id")
    try:
        if update.message.text:
            await ctx.bot.send_message(chat_id=target, text=update.message.text)
        elif update.message.photo:
            await ctx.bot.send_photo(chat_id=target, photo=update.message.photo[-1].file_id,
                                     caption=update.message.caption or "")
        elif update.message.video:
            await ctx.bot.send_video(chat_id=target, video=update.message.video.file_id,
                                     caption=update.message.caption or "")
        elif update.message.voice:
            await ctx.bot.send_voice(chat_id=target, voice=update.message.voice.file_id)
        await update.message.reply_text("✅ Xabar yuborildi!", reply_markup=admin_menu())
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}", reply_markup=admin_menu())
    
    return ConversationHandler.END

# ===================== ADMIN: BAL QO'SHISH =====================
async def adm_add_balance_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "💵 ID orqali pul qo'shish\n\nFoydalanuvchi ID sini kiriting:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_ADD_BALANCE_ID

async def adm_add_balance_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Faqat raqam!")
        return ADM_ADD_BALANCE_ID
    
    user_id = int(update.message.text)
    u = get_user(user_id)
    if not u:
        await update.message.reply_text("❌ Foydalanuvchi topilmadi!")
        return ADM_ADD_BALANCE_ID
    
    ctx.user_data["bal_user_id"] = user_id
    await update.message.reply_text(f"👤 {u[3]} (ID: {u[1]})\n💰 Balans: {u[4]:,.0f} so'm\n\nQancha pul qo'shish?")
    return ADM_ADD_BALANCE_AMOUNT

async def adm_add_balance_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Faqat raqam!")
        return ADM_ADD_BALANCE_AMOUNT
    
    amount = int(update.message.text)
    user_id = ctx.user_data["bal_user_id"]
    add_balance(user_id, amount)
    
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO transactions (tg_id, amount, type, status, created_at) VALUES (?,?,?,?,?)",
              (user_id, amount, "topup", "approved", now_tashkent()))
    conn.commit()
    conn.close()
    
    try:
        await ctx.bot.send_message(
            chat_id=user_id,
            text=f"✅ Hisobingizga <b>{amount:,.0f} so'm</b> qo'shildi!\n💰 Balans: {get_balance(user_id):,.0f} so'm",
            parse_mode=ParseMode.HTML
        )
    except:
        pass
    
    await update.message.reply_text(f"✅ {amount:,.0f} so'm qo'shildi!", reply_markup=admin_menu())
    return ConversationHandler.END

async def adm_add_all_balance_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    users = get_all_users()
    await update.message.reply_text(
        f"💰 Barcha {len(users)} foydalanuvchi hisobiga pul qo'shish\n\nMiqdor kiriting:",
        reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)
    )
    return ADM_ADD_ALL_BALANCE

async def adm_add_all_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=admin_menu())
        return ConversationHandler.END
    
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Faqat raqam!")
        return ADM_ADD_ALL_BALANCE
    
    amount = int(update.message.text)
    users = get_all_users()
    
    conn = db()
    c = conn.cursor()
    for u in users:
        c.execute("UPDATE users SET balance = balance + ? WHERE tg_id=?", (amount, u[1]))
        c.execute("INSERT INTO transactions (tg_id, amount, type, status, created_at) VALUES (?,?,?,?,?)",
                  (u[1], amount, "topup", "approved", now_tashkent()))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ {len(users)} ta foydalanuvchi hisobiga {amount:,.0f} so'mdan qo'shildi!",
        reply_markup=admin_menu()
    )
    return ConversationHandler.END

# ===================== ADMIN: STATISTIKA =====================
async def adm_statistics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    conn = db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE joined_at >= date('now', '-1 day')")
    today_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE joined_at >= date('now', '-7 days')")
    week_users = c.fetchone()[0]
    
    c.execute("SELECT SUM(amount) FROM transactions WHERE type='topup' AND status='approved'")
    total_topup = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(amount) FROM transactions WHERE type='purchase' AND status='approved'")
    total_sales = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM movies")
    total_movies = c.fetchone()[0]
    
    # Top 5 users by balance
    c.execute("SELECT tg_id, full_name, balance FROM users ORDER BY balance DESC LIMIT 5")
    top_users = c.fetchall()
    
    # Recent users
    c.execute("SELECT tg_id, full_name, username, joined_at FROM users ORDER BY joined_at DESC LIMIT 10")
    recent = c.fetchall()
    
    # Top purchased movies
    c.execute("""SELECT movie_code, COUNT(*) as cnt FROM transactions 
                 WHERE type='purchase' AND status='approved' AND movie_code IS NOT NULL
                 GROUP BY movie_code ORDER BY cnt DESC LIMIT 5""")
    top_movies = c.fetchall()
    
    conn.close()
    
    top_u_text = ""
    for u in top_users:
        top_u_text += f"\n  👤 {u[1]} (<code>{u[0]}</code>) — {u[2]:,.0f} so'm"
    
    recent_text = ""
    for u in recent:
        recent_text += f"\n  • {u[1]} | @{u[2] or '-'} | {u[3]}"
    
    top_m_text = ""
    for m in top_movies:
        top_m_text += f"\n  🎬 Kod: {m[0]} — {m[1]} marta"
    
    now_time = datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M:%S")
    
    text = (
        f"📊 <b>Statistika</b>\n"
        f"🕐 {now_time} (Toshkent)\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users}</b>\n"
        f"📅 Bugun qo'shilganlar: <b>{today_users}</b>\n"
        f"📅 Hafta ichida: <b>{week_users}</b>\n\n"
        f"🎬 Jami kinolar: <b>{total_movies}</b>\n\n"
        f"💰 Jami to'ldirilgan: <b>{total_topup:,.0f} so'm</b>\n"
        f"🛒 Jami sotuvlar: <b>{total_sales:,.0f} so'm</b>\n\n"
        f"🏆 <b>Eng ko'p balansi bor:</b>{top_u_text}\n\n"
        f"🎬 <b>Eng ko'p ko'rilgan kinolar:</b>{top_m_text}\n\n"
        f"🆕 <b>Oxirgi qo'shilganlar:</b>{recent_text}"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=admin_menu())

# ===================== ADMIN PANEL =====================
async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    await update.message.reply_text("👨‍💼 Admin paneliga xush kelibsiz!", reply_markup=admin_menu())

# ===================== TOPUP CARD SETTING =====================
async def set_topup_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    card = get_setting("topup_card", "Kiritilmagan")
    await update.message.reply_text(
        f"💳 Joriy karta raqami: <b>{card}</b>\n\nYangi karta raqamini kiriting:",
        parse_mode=ParseMode.HTML
    )
    return ADM_TOPUP_CARD

async def save_topup_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    set_setting("topup_card", update.message.text.strip())
    await update.message.reply_text("✅ Karta raqami saqlandi!", reply_markup=admin_menu())
    return ConversationHandler.END

# ===================== MAIN =====================
def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handlers
    conv_topup = ConversationHandler(
        entry_points=[CallbackQueryHandler(topup_callback, pattern="^topup$")],
        states={
            WAIT_TOPUP_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, topup_amount)],
            WAIT_CHECK: [MessageHandler(filters.PHOTO | filters.Document.ALL, receive_check)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    
    conv_movie_pay = ConversationHandler(
        entry_points=[CallbackQueryHandler(pay_card_callback, pattern="^pay_card_")],
        states={
            WAIT_CHECK: [MessageHandler(filters.PHOTO | filters.Document.ALL, receive_movie_payment_check)],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    
    conv_support = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🆘 Yordam$"), support_start)],
        states={
            WAIT_SUPPORT_MSG: [MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VOICE | filters.VIDEO | filters.Document.ALL,
                receive_support_msg
            )],
        },
        fallbacks=[]
    )
    
    conv_admin_reply = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_reply_callback, pattern="^reply_user_")],
        states={
            WAIT_ADMIN_REPLY: [MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VOICE | filters.VIDEO,
                send_admin_reply
            )],
        },
        fallbacks=[]
    )
    
    conv_add_movie = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎬 Kino qo'shish$"), adm_add_movie_start)],
        states={
            ADM_VIDEO1: [MessageHandler(filters.VIDEO | filters.TEXT, adm_recv_video1)],
            ADM_VIDEO2: [MessageHandler(filters.VIDEO | filters.TEXT, adm_recv_video2)],
            ADM_INFO1: [MessageHandler(filters.TEXT, adm_recv_info1)],
            ADM_INFO2: [MessageHandler(filters.TEXT, adm_recv_info2)],
            ADM_PRICE1: [MessageHandler(filters.TEXT, adm_recv_price1)],
            ADM_PRICE2: [MessageHandler(filters.TEXT, adm_recv_price2)],
            ADM_MOVIE_CODE: [MessageHandler(filters.TEXT, adm_recv_movie_code)],
        },
        fallbacks=[]
    )
    
    conv_continuation = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Kino davomini qo'shish$"), adm_continuation_start)],
        states={
            ADM_CONTINUATION_CODE: [MessageHandler(filters.TEXT, adm_cont_code)],
            ADM_CONT_VIDEO: [MessageHandler(filters.VIDEO | filters.TEXT, adm_cont_video)],
            ADM_CONT_INFO: [MessageHandler(filters.TEXT, adm_cont_info)],
            ADM_CONT_PRICE: [MessageHandler(filters.TEXT, adm_cont_price)],
        },
        fallbacks=[]
    )
    
    conv_start_msg = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⚙️ Start xabarini o'zgartirish$"), adm_start_msg)],
        states={
            ADM_START_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, adm_start_photo)],
            ADM_START_MSG: [MessageHandler(filters.TEXT, adm_start_msg_text)],
        },
        fallbacks=[]
    )
    
    conv_channel = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📢 Kanal qo'shish$"), adm_add_channel_start)],
        states={
            ADM_CHANNEL_ID: [MessageHandler(filters.TEXT, adm_channel_id)],
            ADM_CHANNEL_LINK: [MessageHandler(filters.TEXT, adm_channel_link)],
            ADM_CHANNEL_NAME: [MessageHandler(filters.TEXT, adm_channel_name)],
        },
        fallbacks=[]
    )
    
    conv_link = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔗 Link qo'shish$"), adm_add_link_start)],
        states={
            ADM_LINK_TITLE: [MessageHandler(filters.TEXT, adm_link_title)],
            ADM_LINK_URL: [MessageHandler(filters.TEXT, adm_link_url)],
        },
        fallbacks=[]
    )
    
    conv_broadcast = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📨 Barcha foydalanuvchilarga xabar$"), adm_broadcast_start)],
        states={
            ADM_BROADCAST_MSG: [MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VOICE | filters.Document.ALL,
                adm_broadcast_send
            )],
        },
        fallbacks=[]
    )
    
    conv_send_user = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📩 ID orqali xabar$"), adm_send_user_start)],
        states={
            ADM_SEND_USER_ID: [MessageHandler(filters.TEXT, adm_send_user_id)],
            ADM_SEND_USER_MSG: [MessageHandler(
                filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VOICE,
                adm_send_user_msg
            )],
        },
        fallbacks=[]
    )
    
    conv_add_balance = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💵 ID orqali pul qo'shish$"), adm_add_balance_start)],
        states={
            ADM_ADD_BALANCE_ID: [MessageHandler(filters.TEXT, adm_add_balance_id)],
            ADM_ADD_BALANCE_AMOUNT: [MessageHandler(filters.TEXT, adm_add_balance_amount)],
        },
        fallbacks=[]
    )
    
    conv_add_all_balance = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Barcha hisobiga pul qo'shish$"), adm_add_all_balance_start)],
        states={
            ADM_ADD_ALL_BALANCE: [MessageHandler(filters.TEXT, adm_add_all_balance)],
        },
        fallbacks=[]
    )
    
    conv_topup_card = ConversationHandler(
        entry_points=[CommandHandler("setcard", set_topup_card)],
        states={
            ADM_TOPUP_CARD: [MessageHandler(filters.TEXT, save_topup_card)],
        },
        fallbacks=[]
    )
    
    # Add all handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(conv_topup)
    app.add_handler(conv_movie_pay)
    app.add_handler(conv_support)
    app.add_handler(conv_admin_reply)
    app.add_handler(conv_add_movie)
    app.add_handler(conv_continuation)
    app.add_handler(conv_start_msg)
    app.add_handler(conv_channel)
    app.add_handler(conv_link)
    app.add_handler(conv_broadcast)
    app.add_handler(conv_send_user)
    app.add_handler(conv_add_balance)
    app.add_handler(conv_add_all_balance)
    app.add_handler(conv_topup_card)
    
    # Callback handlers
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(approve_topup, pattern="^approve_topup_"))
    app.add_handler(CallbackQueryHandler(reject_topup, pattern="^reject_topup_"))
    app.add_handler(CallbackQueryHandler(approve_movie_payment, pattern="^approve_movie_"))
    app.add_handler(CallbackQueryHandler(reject_movie_payment, pattern="^reject_movie_"))
    app.add_handler(CallbackQueryHandler(pay_balance_callback, pattern="^pay_balance_"))
    
    # Statistics handler
    app.add_handler(MessageHandler(filters.Regex("^📊 Statistika$"), adm_statistics))
    
    # Text handler (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("✅ Bot ishga tushdi!")
    app.run_polling()

if __name__ == "__main__":
    main()
