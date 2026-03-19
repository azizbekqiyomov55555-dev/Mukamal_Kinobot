import asyncio
import logging
import io
import aiosqlite
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime

from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
#                        CONFIG
# ============================================================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"          # @BotFather dan oling
ADMIN_IDS = [123456789]                     # O'z Telegram ID ingiz
PAYMENT_CARD = "8600 0000 0000 0000"        # To'lov karta raqami
DB_PATH = "bot_database.db"


# ============================================================
#                        STATES
# ============================================================
class AdminVideoStates(StatesGroup):
    waiting_video = State()
    waiting_more_parts = State()
    waiting_part_description = State()
    waiting_video_code = State()
    waiting_video_title = State()
    waiting_video_price = State()
    waiting_video_paid = State()

class AdminChannelStates(StatesGroup):
    waiting_channel_id = State()
    waiting_channel_name = State()
    waiting_channel_link = State()
    waiting_bot_username = State()
    waiting_bot_name = State()
    waiting_bot_link = State()

class AdminSocialStates(StatesGroup):
    waiting_instagram = State()
    waiting_youtube = State()

class AdminBanStates(StatesGroup):
    waiting_user_id = State()
    waiting_action = State()

class AdminBalanceStates(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()
    waiting_amount_all = State()

class AdminStartStates(StatesGroup):
    waiting_text = State()
    waiting_photo = State()

class AdminReplyStates(StatesGroup):
    waiting_reply = State()

class UserStates(StatesGroup):
    waiting_code = State()
    waiting_check = State()
    waiting_topup_check = State()
    waiting_topup_amount = State()
    waiting_message_to_admin = State()


# ============================================================
#                        DATABASE
# ============================================================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                full_name TEXT,
                balance REAL DEFAULT 0,
                total_paid REAL DEFAULT 0,
                joined_at TEXT,
                is_banned INTEGER DEFAULT 0
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                title TEXT,
                is_paid INTEGER DEFAULT 0,
                price REAL DEFAULT 0,
                parts_count INTEGER DEFAULT 0,
                created_at TEXT
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS video_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_code TEXT,
                part_number INTEGER,
                file_id TEXT,
                description TEXT
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_name TEXT,
                channel_link TEXT,
                channel_type TEXT DEFAULT 'telegram'
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS social_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT UNIQUE,
                link TEXT
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_code TEXT,
                amount REAL,
                check_file_id TEXT,
                status TEXT DEFAULT 'pending',
                payment_type TEXT DEFAULT 'video',
                created_at TEXT
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS start_message (
                id INTEGER PRIMARY KEY,
                text TEXT,
                photo_id TEXT,
                is_quote INTEGER DEFAULT 0,
                quote_link TEXT
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                video_code TEXT,
                purchased_at TEXT,
                UNIQUE(user_id, video_code)
            )""")
        await db.commit()

# --- User ---
async def get_user(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as cur:
            return await cur.fetchone()

async def create_user(telegram_id, username, full_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id,username,full_name,joined_at) VALUES (?,?,?,?)",
            (telegram_id, username, full_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY joined_at DESC") as cur:
            return await cur.fetchall()

async def get_users_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0]

async def ban_user(telegram_id, status=1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE telegram_id=?", (status, telegram_id))
        await db.commit()

async def add_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (amount, telegram_id))
        await db.commit()

async def deduct_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance=balance-?, total_paid=total_paid+? WHERE telegram_id=?",
            (amount, amount, telegram_id)
        )
        await db.commit()

async def add_balance_all(amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+?", (amount,))
        await db.commit()

# --- Video ---
async def add_video(code, title, is_paid, price, parts_count):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO videos (code,title,is_paid,price,parts_count,created_at) VALUES (?,?,?,?,?,?)",
            (code, title, is_paid, price, parts_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()

async def get_video(code):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE code=?", (code,)) as cur:
            return await cur.fetchone()

async def add_video_part(video_code, part_number, file_id, description):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO video_parts (video_code,part_number,file_id,description) VALUES (?,?,?,?)",
            (video_code, part_number, file_id, description)
        )
        await db.commit()

async def get_video_parts(video_code):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM video_parts WHERE video_code=? ORDER BY part_number", (video_code,)
        ) as cur:
            return await cur.fetchall()

async def get_video_part(video_code, part_number):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM video_parts WHERE video_code=? AND part_number=?", (video_code, part_number)
        ) as cur:
            return await cur.fetchone()

# --- Channel ---
async def add_channel(channel_id, channel_name, channel_link, channel_type='telegram'):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO channels (channel_id,channel_name,channel_link,channel_type) VALUES (?,?,?,?)",
            (channel_id, channel_name, channel_link, channel_type)
        )
        await db.commit()

async def get_channels(channel_type='telegram'):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels WHERE channel_type=?", (channel_type,)) as cur:
            return await cur.fetchall()

async def delete_channel(db_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE id=?", (db_id,))
        await db.commit()

async def add_social_link(platform, link):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO social_links (platform,link) VALUES (?,?)", (platform, link)
        )
        await db.commit()

async def get_social_links():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM social_links") as cur:
            return await cur.fetchall()

# --- Payment ---
async def add_payment(user_id, video_code, amount, check_file_id, payment_type='video'):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO payments (user_id,video_code,amount,check_file_id,payment_type,created_at) VALUES (?,?,?,?,?,?)",
            (user_id, video_code, amount, check_file_id, payment_type,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()
        return cursor.lastrowid

async def get_payment(payment_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payments WHERE id=?", (payment_id,)) as cur:
            return await cur.fetchone()

async def update_payment_status(payment_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE payments SET status=? WHERE id=?", (status, payment_id))
        await db.commit()

async def has_purchased(user_id, video_code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM user_purchases WHERE user_id=? AND video_code=?", (user_id, video_code)
        ) as cur:
            return await cur.fetchone() is not None

async def add_purchase(user_id, video_code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_purchases (user_id,video_code,purchased_at) VALUES (?,?,?)",
            (user_id, video_code, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        await db.commit()

# --- Start message ---
async def set_start_message(text, photo_id=None, is_quote=0, quote_link=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM start_message")
        await db.execute(
            "INSERT INTO start_message (id,text,photo_id,is_quote,quote_link) VALUES (1,?,?,?,?)",
            (text, photo_id, is_quote, quote_link)
        )
        await db.commit()

async def get_start_message():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM start_message WHERE id=1") as cur:
            return await cur.fetchone()


# ============================================================
#                        KEYBOARDS
# ============================================================
def kb_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kod kiriting"), KeyboardButton(text="💰 Hisobim")],
            [KeyboardButton(text="📩 Adminga xabar"),  KeyboardButton(text="❓ Yordam")]
        ],
        resize_keyboard=True
    )

def kb_admin_panel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Video qo'shish",        callback_data="admin_add_video")],
        [InlineKeyboardButton(text="📢 Telegram kanallar",     callback_data="admin_channels"),
         InlineKeyboardButton(text="🤖 Botlar",                callback_data="admin_bots")],
        [InlineKeyboardButton(text="📸 Instagram",             callback_data="admin_instagram"),
         InlineKeyboardButton(text="▶️ YouTube",               callback_data="admin_youtube")],
        [InlineKeyboardButton(text="📊 Statistika",            callback_data="admin_stats")],
        [InlineKeyboardButton(text="💳 ID ga pul qo'shish",    callback_data="admin_add_balance_id")],
        [InlineKeyboardButton(text="💰 Hammaga pul qo'shish",  callback_data="admin_add_balance_all")],
        [InlineKeyboardButton(text="🚫 Ban / Unban",           callback_data="admin_ban")],
        [InlineKeyboardButton(text="✉️ Start xabar sozlash",   callback_data="admin_set_start")],
        [InlineKeyboardButton(text="❌ Yopish",                callback_data="close")]
    ])

def kb_channel_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish",  callback_data="add_tg_channel")],
        [InlineKeyboardButton(text="🗑 Kanal o'chirish", callback_data="del_tg_channel")],
        [InlineKeyboardButton(text="📋 Ro'yxat",         callback_data="list_tg_channel")],
        [InlineKeyboardButton(text="🔙 Orqaga",          callback_data="back_admin")]
    ])

def kb_bot_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Bot qo'shish",  callback_data="add_bot")],
        [InlineKeyboardButton(text="🗑 Bot o'chirish", callback_data="del_bot")],
        [InlineKeyboardButton(text="📋 Ro'yxat",       callback_data="list_bots")],
        [InlineKeyboardButton(text="🔙 Orqaga",        callback_data="back_admin")]
    ])

def kb_more_parts():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ha, yana qism qo'shish", callback_data="add_more_part")],
        [InlineKeyboardButton(text="✅ O'tkazvorish (tugatish)", callback_data="finish_parts")]
    ])

def kb_paid_choice():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, pullik", callback_data="video_paid_yes")],
        [InlineKeyboardButton(text="🆓 Yo'q, bepul", callback_data="video_paid_no")]
    ])

def kb_video_parts(parts_count, video_code):
    buttons = []
    row = []
    for i in range(1, parts_count + 1):
        row.append(InlineKeyboardButton(text=f"📺 {i}-qism", callback_data=f"part_{video_code}_{i}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Yopish", callback_data="close_video")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_video_actions(video_code, part_number):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Do'stlarga ulashish",
                              switch_inline_query=f"video_{video_code}")],
        [InlineKeyboardButton(text="❌ Videoni yopish", callback_data="close_video")]
    ])

def kb_payment(video_code, price):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 To'lov qilish ({price:,.0f} so'm)",
                              callback_data=f"pay_card_{video_code}")],
        [InlineKeyboardButton(text="💰 Balansdan to'lash",
                              callback_data=f"pay_balance_{video_code}")]
    ])

def kb_confirm_payment(payment_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash",    callback_data=f"confirm_pay_{payment_id}"),
         InlineKeyboardButton(text="❌ Bekor qilish",  callback_data=f"reject_pay_{payment_id}")]
    ])

def kb_confirm_topup(payment_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash",    callback_data=f"confirm_top_{payment_id}"),
         InlineKeyboardButton(text="❌ Bekor qilish",  callback_data=f"reject_top_{payment_id}")]
    ])

def kb_subscribe(channels):
    buttons = [[InlineKeyboardButton(text=f"📢 {ch['channel_name']}", url=ch['channel_link'])]
               for ch in channels]
    buttons.append([InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_balance_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Hisobni to'ldirish", callback_data="topup_balance")]
    ])

def kb_start_type():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Oddiy matn",      callback_data="stype_text")],
        [InlineKeyboardButton(text="🖼 Rasm + matn",     callback_data="stype_photo")],
        [InlineKeyboardButton(text="💬 Iqtibos xabar",   callback_data="stype_quote")],
        [InlineKeyboardButton(text="🔗 Link xabar",      callback_data="stype_link")],
        [InlineKeyboardButton(text="🔙 Orqaga",          callback_data="back_admin")]
    ])

def kb_reply_user(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Javob yuborish", callback_data=f"reply_{user_id}")]
    ])

def kb_ban_action():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Ban qilish",         callback_data="do_ban"),
         InlineKeyboardButton(text="✅ Bandan chiqarish",   callback_data="do_unban")],
        [InlineKeyboardButton(text="🔙 Orqaga",             callback_data="back_admin")]
    ])


# ============================================================
#                   HELPER FUNCTIONS
# ============================================================
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def check_subscription(bot: Bot, user_id: int) -> bool:
    channels = await get_channels('telegram')
    if not channels:
        return True
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch['channel_id'], user_id)
            if member.status in ('left', 'kicked'):
                return False
        except Exception:
            pass
    return True

async def notify_new_user(bot: Bot, user):
    for admin_id in ADMIN_IDS:
        try:
            text = (
                f"🆕 <b>Yangi obunachi!</b>\n\n"
                f"👤 Ism: {user.full_name}\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"📅 Sana: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Lichkaga o'tish", url=f"tg://user?id={user.id}")]
            ])
            await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


# ============================================================
#                        ROUTER
# ============================================================
router = Router()


# ============================================================
#                   ADMIN HANDLERS
# ============================================================
@router.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Admin Panel</b>", reply_markup=kb_admin_panel(), parse_mode="HTML")

@router.callback_query(F.data == "back_admin")
async def back_admin(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🛠 <b>Admin Panel</b>", reply_markup=kb_admin_panel(), parse_mode="HTML")

@router.callback_query(F.data == "close")
async def close_cb(call: CallbackQuery):
    await call.message.delete()

# ----- VIDEO QO'SHISH -----
@router.callback_query(F.data == "admin_add_video")
async def admin_add_video(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("📹 <b>Video yuboring:</b>", parse_mode="HTML")
    await state.set_state(AdminVideoStates.waiting_video)
    await state.update_data(parts=[], descs=[])

@router.message(AdminVideoStates.waiting_video, F.video)
async def recv_video(message: Message, state: FSMContext):
    data = await state.get_data()
    parts = data.get("parts", [])
    parts.append(message.video.file_id)
    await state.update_data(parts=parts)
    part_num = len(parts)
    await message.answer(f"✅ {part_num}-qism qabul qilindi.\n\n📝 Bu qism uchun ma'lumot matni kiriting:")
    await state.set_state(AdminVideoStates.waiting_part_description)

@router.message(AdminVideoStates.waiting_part_description)
async def recv_part_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    descs = data.get("descs", [])
    descs.append(message.text)
    await state.update_data(descs=descs)
    parts = data.get("parts", [])
    await message.answer(
        f"✅ {len(parts)}-qism ma'lumoti saqlandi.\n\nBoshqa qismlar kiritasizmi?",
        reply_markup=kb_more_parts()
    )
    await state.set_state(AdminVideoStates.waiting_more_parts)

@router.callback_query(F.data == "add_more_part")
async def add_more_part(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📹 Keyingi qism videosini yuboring:")
    await state.set_state(AdminVideoStates.waiting_video)

@router.callback_query(F.data == "finish_parts")
async def finish_parts(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 Video uchun <b>KOD</b> kiriting (masalan: FILM001):", parse_mode="HTML")
    await state.set_state(AdminVideoStates.waiting_video_code)

@router.message(AdminVideoStates.waiting_video_code)
async def recv_video_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip().upper())
    await message.answer("📋 Video <b>sarlavhasini</b> kiriting:", parse_mode="HTML")
    await state.set_state(AdminVideoStates.waiting_video_title)

@router.message(AdminVideoStates.waiting_video_title)
async def recv_video_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("💰 Bu video <b>pullikmi?</b>", parse_mode="HTML", reply_markup=kb_paid_choice())
    await state.set_state(AdminVideoStates.waiting_video_paid)

@router.callback_query(F.data.in_(["video_paid_yes", "video_paid_no"]))
async def recv_paid_choice(call: CallbackQuery, state: FSMContext):
    if call.data == "video_paid_yes":
        await state.update_data(is_paid=1)
        await call.message.edit_text("💲 Video <b>narxini</b> kiriting (so'mda):", parse_mode="HTML")
        await state.set_state(AdminVideoStates.waiting_video_price)
    else:
        await state.update_data(is_paid=0, price=0)
        await save_video_final(call.message, state)

@router.message(AdminVideoStates.waiting_video_price)
async def recv_video_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "").replace(" ", ""))
        await state.update_data(price=price)
        await save_video_final(message, state)
    except ValueError:
        await message.answer("❌ Narxni to'g'ri kiriting (faqat raqam):")

async def save_video_final(msg_or_call, state: FSMContext):
    data = await state.get_data()
    code = data["code"]
    title = data["title"]
    is_paid = data.get("is_paid", 0)
    price = data.get("price", 0)
    parts = data.get("parts", [])
    descs = data.get("descs", [])
    await add_video(code, title, is_paid, price, len(parts))
    for i, (fid, desc) in enumerate(zip(parts, descs), 1):
        await add_video_part(code, i, fid, desc)
    await state.clear()
    text = (
        f"✅ Video saqlandi!\n\n"
        f"📌 Kod: <code>{code}</code>\n"
        f"🎬 Sarlavha: {title}\n"
        f"📦 Qismlar: {len(parts)}\n"
    )
    if is_paid:
        text += f"💰 Narxi: {price:,.0f} so'm"
    if hasattr(msg_or_call, 'edit_text'):
        await msg_or_call.edit_text(text, parse_mode="HTML", reply_markup=kb_admin_panel())
    else:
        await msg_or_call.answer(text, parse_mode="HTML", reply_markup=kb_admin_panel())

# ----- KANALLAR -----
@router.callback_query(F.data == "admin_channels")
async def admin_channels(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("📢 <b>Telegram kanallar</b>", reply_markup=kb_channel_menu(), parse_mode="HTML")

@router.callback_query(F.data == "add_tg_channel")
async def add_tg_channel_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📢 Kanal ID kiriting (@kanal yoki -1001234567890):")
    await state.update_data(ch_type='telegram')
    await state.set_state(AdminChannelStates.waiting_channel_id)

@router.callback_query(F.data == "del_tg_channel")
async def del_tg_channel_start(call: CallbackQuery, state: FSMContext):
    channels = await get_channels('telegram')
    if not channels:
        await call.answer("Kanallar yo'q!", show_alert=True)
        return
    text = "🗑 O'chirish uchun kanal DB-ID sini kiriting:\n\n"
    for ch in channels:
        text += f"#{ch['id']} — {ch['channel_name']}\n"
    await call.message.edit_text(text)
    await state.update_data(ch_type='delete_tg')
    await state.set_state(AdminChannelStates.waiting_channel_id)

@router.callback_query(F.data == "list_tg_channel")
async def list_tg_channels(call: CallbackQuery):
    channels = await get_channels('telegram')
    if not channels:
        await call.answer("Kanallar yo'q!", show_alert=True)
        return
    text = "📢 <b>Kanallar:</b>\n\n"
    for ch in channels:
        text += f"#{ch['id']} | {ch['channel_name']} | {ch['channel_link']}\n"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_channel_menu())

@router.message(AdminChannelStates.waiting_channel_id)
async def recv_ch_id(message: Message, state: FSMContext):
    data = await state.get_data()
    ch_type = data.get('ch_type', 'telegram')
    if ch_type == 'delete_tg':
        try:
            await delete_channel(int(message.text.strip()))
            await state.clear()
            await message.answer("✅ Kanal o'chirildi!", reply_markup=kb_channel_menu())
        except Exception:
            await message.answer("❌ Xato ID!")
            await state.clear()
        return
    await state.update_data(channel_id=message.text.strip())
    await message.answer("📝 Kanal nomini kiriting:")
    await state.set_state(AdminChannelStates.waiting_channel_name)

@router.message(AdminChannelStates.waiting_channel_name)
async def recv_ch_name(message: Message, state: FSMContext):
    await state.update_data(channel_name=message.text)
    await message.answer("🔗 Kanal linkini kiriting (https://t.me/...):")
    await state.set_state(AdminChannelStates.waiting_channel_link)

@router.message(AdminChannelStates.waiting_channel_link)
async def recv_ch_link(message: Message, state: FSMContext):
    data = await state.get_data()
    await add_channel(data['channel_id'], data['channel_name'], message.text, data.get('ch_type', 'telegram'))
    await state.clear()
    await message.answer("✅ Kanal qo'shildi!", reply_markup=kb_channel_menu())

# ----- BOTLAR -----
@router.callback_query(F.data == "admin_bots")
async def admin_bots_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🤖 <b>Botlar</b>", reply_markup=kb_bot_menu(), parse_mode="HTML")

@router.callback_query(F.data == "add_bot")
async def add_bot_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🤖 Bot username kiriting (@botusername):")
    await state.set_state(AdminChannelStates.waiting_bot_username)

@router.callback_query(F.data == "del_bot")
async def del_bot_start(call: CallbackQuery, state: FSMContext):
    bots = await get_channels('bot')
    if not bots:
        await call.answer("Botlar yo'q!", show_alert=True)
        return
    text = "🗑 O'chirish uchun bot DB-ID sini kiriting:\n\n"
    for b in bots:
        text += f"#{b['id']} — {b['channel_name']}\n"
    await call.message.edit_text(text)
    await state.update_data(ch_type='delete_bot')
    await state.set_state(AdminChannelStates.waiting_bot_username)

@router.callback_query(F.data == "list_bots")
async def list_bots(call: CallbackQuery):
    bots = await get_channels('bot')
    if not bots:
        await call.answer("Botlar yo'q!", show_alert=True)
        return
    text = "🤖 <b>Botlar:</b>\n\n"
    for b in bots:
        text += f"#{b['id']} | {b['channel_name']} | {b['channel_link']}\n"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_bot_menu())

@router.message(AdminChannelStates.waiting_bot_username)
async def recv_bot_username(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get('ch_type') == 'delete_bot':
        try:
            await delete_channel(int(message.text.strip()))
            await state.clear()
            await message.answer("✅ Bot o'chirildi!", reply_markup=kb_bot_menu())
        except Exception:
            await message.answer("❌ Xato ID!")
            await state.clear()
        return
    await state.update_data(bot_username=message.text.strip(), ch_type='bot')
    await message.answer("📝 Bot nomini kiriting:")
    await state.set_state(AdminChannelStates.waiting_bot_name)

@router.message(AdminChannelStates.waiting_bot_name)
async def recv_bot_name(message: Message, state: FSMContext):
    await state.update_data(bot_name=message.text)
    await message.answer("🔗 Bot linkini kiriting (https://t.me/...):")
    await state.set_state(AdminChannelStates.waiting_bot_link)

@router.message(AdminChannelStates.waiting_bot_link)
async def recv_bot_link(message: Message, state: FSMContext):
    data = await state.get_data()
    await add_channel(data['bot_username'], data['bot_name'], message.text, 'bot')
    await state.clear()
    await message.answer("✅ Bot qo'shildi!", reply_markup=kb_bot_menu())

# ----- INSTAGRAM / YOUTUBE -----
@router.callback_query(F.data == "admin_instagram")
async def admin_instagram(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("📸 Instagram kanal linkini kiriting:")
    await state.set_state(AdminSocialStates.waiting_instagram)

@router.message(AdminSocialStates.waiting_instagram)
async def recv_instagram(message: Message, state: FSMContext):
    await add_social_link('instagram', message.text)
    await state.clear()
    await message.answer("✅ Instagram linki saqlandi!", reply_markup=kb_admin_panel())

@router.callback_query(F.data == "admin_youtube")
async def admin_youtube(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("▶️ YouTube kanal linkini kiriting:")
    await state.set_state(AdminSocialStates.waiting_youtube)

@router.message(AdminSocialStates.waiting_youtube)
async def recv_youtube(message: Message, state: FSMContext):
    await add_social_link('youtube', message.text)
    await state.clear()
    await message.answer("✅ YouTube linki saqlandi!", reply_markup=kb_admin_panel())

# ----- STATISTIKA -----
@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    users = await get_all_users()
    total = len(users)
    banned = sum(1 for u in users if u['is_banned'])
    active = total - banned
    total_bal = sum(u['balance'] or 0 for u in users)
    total_paid_sum = sum(u['total_paid'] or 0 for u in users)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    fig.patch.set_facecolor('#1a1a2e')

    # Chap: foydalanuvchilar jadvali
    ax1 = axes[0]
    ax1.set_facecolor('#16213e')
    ax1.set_title(f"👥 So'nggi foydalanuvchilar", color='white', fontsize=11, pad=8)
    show_users = list(users)[:12]
    names = [f"{u['full_name'] or 'Noma\'lum'}"[:14] for u in show_users]
    ids = [str(u['telegram_id']) for u in show_users]
    dates = [(u['joined_at'] or '-')[:10] for u in show_users]
    y = list(range(len(names)))
    ax1.barh(y, [1]*len(names), color='#0f3460', edgecolor='#e94560', linewidth=0.6)
    ax1.set_yticks(y)
    ax1.set_yticklabels([f"{n} | {i}" for n, i in zip(names, ids)], color='white', fontsize=7)
    ax1.set_xticks([])
    ax1.invert_yaxis()
    for i, (_, d) in enumerate(zip(names, dates)):
        ax1.text(0.5, i, d, va='center', ha='center', color='#e2e2e2', fontsize=6.5)

    # O'ng: umumiy statistika
    ax2 = axes[1]
    ax2.set_facecolor('#16213e')
    ax2.set_title("📊 Umumiy statistika", color='white', fontsize=11, pad=8)
    ax2.axis('off')
    stats = (
        f"Jami foydalanuvchilar:  {total}\n"
        f"Faol:                   {active}\n"
        f"Bloklangan:             {banned}\n\n"
        f"Jami balans:  {total_bal:,.0f} so'm\n"
        f"Jami to'lov:  {total_paid_sum:,.0f} so'm"
    )
    ax2.text(0.08, 0.55, stats, color='white', fontsize=11, va='center',
             transform=ax2.transAxes, family='monospace',
             bbox=dict(boxstyle='round,pad=0.6', facecolor='#0f3460', alpha=0.85))

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=110, bbox_inches='tight')
    buf.seek(0)
    plt.close()

    # Foydalanuvchilar tugmalari
    buttons = []
    for u in show_users:
        name = (u['full_name'] or 'Noma\'lum')[:22]
        jdate = (u['joined_at'] or '-')[:10]
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name} | {jdate}",
            url=f"tg://user?id={u['telegram_id']}"
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await bot.send_photo(
        call.from_user.id,
        BufferedInputFile(buf.read(), filename="stats.png"),
        caption=(
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Jami: {total}  |  ✅ Faol: {active}  |  🚫 Ban: {banned}\n"
            f"💰 Jami balans: {total_bal:,.0f} so'm"
        ),
        parse_mode="HTML",
        reply_markup=kb
    )
    await call.answer()

# ----- TO'LOV TASDIQLASH (Admin) -----
@router.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split("_")[-1])
    pay = await get_payment(pid)
    if not pay:
        await call.answer("Topilmadi!", show_alert=True)
        return
    await update_payment_status(pid, 'confirmed')
    await add_purchase(pay['user_id'], pay['video_code'])
    video = await get_video(pay['video_code'])
    parts = await get_video_parts(pay['video_code'])
    await bot.send_message(
        pay['user_id'],
        f"✅ To'lovingiz tasdiqlandi!\n🎬 <b>{video['title']}</b>\n\nQaysi qismni ko'rmoqchisiz?",
        parse_mode="HTML",
        reply_markup=kb_video_parts(len(parts), pay['video_code'])
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("✅ Tasdiqlandi!")

@router.callback_query(F.data.startswith("reject_pay_"))
async def reject_payment(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split("_")[-1])
    pay = await get_payment(pid)
    if pay:
        await update_payment_status(pid, 'rejected')
        await bot.send_message(pay['user_id'], "❌ To'lovingiz rad etildi. Admin bilan bog'laning.")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("❌ Rad etildi")

# ----- HISOB TO'LDIRISH TASDIQLASH (Admin) -----
@router.callback_query(F.data.startswith("confirm_top_"))
async def confirm_topup(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split("_")[-1])
    pay = await get_payment(pid)
    if not pay:
        await call.answer("Topilmadi!", show_alert=True)
        return
    await update_payment_status(pid, 'confirmed')
    await add_balance(pay['user_id'], pay['amount'])
    await bot.send_message(
        pay['user_id'],
        f"✅ Hisobingiz to'ldirildi!\n💰 <b>{pay['amount']:,.0f} so'm</b>",
        parse_mode="HTML"
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("✅ To'ldirildi!")

@router.callback_query(F.data.startswith("reject_top_"))
async def reject_topup(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    pid = int(call.data.split("_")[-1])
    pay = await get_payment(pid)
    if pay:
        await update_payment_status(pid, 'rejected')
        await bot.send_message(pay['user_id'], "❌ Hisob to'ldirish rad etildi.")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("❌ Rad etildi")

# ----- BAN / UNBAN -----
@router.callback_query(F.data == "admin_ban")
async def admin_ban_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🚫 Foydalanuvchi Telegram ID sini kiriting:")
    await state.set_state(AdminBanStates.waiting_user_id)

@router.message(AdminBanStates.waiting_user_id)
async def recv_ban_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        user = await get_user(uid)
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi!")
            await state.clear()
            return
        await state.update_data(target_id=uid)
        status_txt = "🚫 Bloklangan" if user['is_banned'] else "✅ Faol"
        await message.answer(
            f"👤 {user['full_name']}\n🆔 {uid}\nHolat: {status_txt}",
            reply_markup=kb_ban_action()
        )
        await state.set_state(AdminBanStates.waiting_action)
    except ValueError:
        await message.answer("❌ ID raqam bo'lishi kerak!")
        await state.clear()

@router.callback_query(F.data.in_(["do_ban", "do_unban"]), AdminBanStates.waiting_action)
async def do_ban(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data['target_id']
    if call.data == "do_ban":
        await ban_user(uid, 1)
        await bot.send_message(uid, "🚫 Siz botdan bloklanding.")
        await call.answer("✅ Ban qilindi!")
    else:
        await ban_user(uid, 0)
        await bot.send_message(uid, "✅ Bloklash bekor qilindi!")
        await call.answer("✅ Bandan chiqarildi!")
    await state.clear()
    await call.message.edit_reply_markup(reply_markup=None)

# ----- BALANS QO'SHISH (ID orqali) -----
@router.callback_query(F.data == "admin_add_balance_id")
async def admin_bal_id(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💳 Foydalanuvchi ID sini kiriting:")
    await state.set_state(AdminBalanceStates.waiting_user_id)

@router.message(AdminBalanceStates.waiting_user_id)
async def recv_bal_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        user = await get_user(uid)
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi!")
            await state.clear()
            return
        await state.update_data(target_id=uid)
        await message.answer(f"💰 {user['full_name']} ga qo'shish miqdorini kiriting (so'mda):")
        await state.set_state(AdminBalanceStates.waiting_amount)
    except ValueError:
        await message.answer("❌ ID raqam bo'lishi kerak!")
        await state.clear()

@router.message(AdminBalanceStates.waiting_amount)
async def recv_bal_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        data = await state.get_data()
        uid = data['target_id']
        await add_balance(uid, amount)
        await state.clear()
        await message.answer(f"✅ {amount:,.0f} so'm qo'shildi!", reply_markup=kb_admin_panel())
        await bot.send_message(uid, f"💰 Hisobingizga <b>{amount:,.0f} so'm</b> qo'shildi!", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Miqdorni to'g'ri kiriting!")

# ----- HAMMAGA BALANS -----
@router.callback_query(F.data == "admin_add_balance_all")
async def admin_bal_all(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💰 Barcha foydalanuvchilarga qo'shish miqdorini kiriting:")
    await state.set_state(AdminBalanceStates.waiting_amount_all)

@router.message(AdminBalanceStates.waiting_amount_all)
async def recv_bal_all(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        await add_balance_all(amount)
        count = await get_users_count()
        await state.clear()
        await message.answer(f"✅ {count} ta foydalanuvchiga {amount:,.0f} so'm qo'shildi!", reply_markup=kb_admin_panel())
    except ValueError:
        await message.answer("❌ Miqdorni to'g'ri kiriting!")

# ----- START XABAR -----
@router.callback_query(F.data == "admin_set_start")
async def admin_set_start(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("✉️ <b>Start xabar turini tanlang:</b>",
                                  parse_mode="HTML", reply_markup=kb_start_type())

@router.callback_query(F.data.in_(["stype_text", "stype_quote", "stype_link"]))
async def stype_text_based(call: CallbackQuery, state: FSMContext):
    mapping = {
        "stype_text":  ("📝 Start xabar matni kiriting:", "text"),
        "stype_quote": ("💬 Iqtibos matni kiriting:",      "quote"),
        "stype_link":  ("🔗 Link kiriting:",               "link"),
    }
    txt, stype = mapping[call.data]
    await call.message.edit_text(txt)
    await state.update_data(stype=stype, photo_id=None)
    await state.set_state(AdminStartStates.waiting_text)

@router.callback_query(F.data == "stype_photo")
async def stype_photo(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🖼 Rasm yuboring:")
    await state.update_data(stype='photo')
    await state.set_state(AdminStartStates.waiting_photo)

@router.message(AdminStartStates.waiting_photo, F.photo)
async def recv_start_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("📝 Endi rasm uchun matn kiriting:")
    await state.set_state(AdminStartStates.waiting_text)

@router.message(AdminStartStates.waiting_text)
async def recv_start_text(message: Message, state: FSMContext):
    data = await state.get_data()
    stype = data.get('stype', 'text')
    photo_id = data.get('photo_id')
    if stype == 'quote':
        await set_start_message(message.text, photo_id, is_quote=1)
    elif stype == 'link':
        await set_start_message("", None, is_quote=0, quote_link=message.text)
    else:
        await set_start_message(message.text, photo_id, is_quote=0)
    await state.clear()
    await message.answer("✅ Start xabari saqlandi!", reply_markup=kb_admin_panel())

# ----- ADMINGA JAVOB -----
@router.callback_query(F.data.startswith("reply_"))
async def reply_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data.split("_", 1)[1])
    await state.update_data(reply_to=uid)
    await call.message.answer(f"✉️ {uid} ga javob yozing (matn, rasm, ovoz, stiker):")
    await state.set_state(AdminReplyStates.waiting_reply)

@router.message(AdminReplyStates.waiting_reply)
async def send_admin_reply(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data['reply_to']
    try:
        if message.text:
            await bot.send_message(uid, f"📩 <b>Admin javobi:</b>\n\n{message.text}", parse_mode="HTML")
        elif message.photo:
            await bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption or "")
        elif message.voice:
            await bot.send_voice(uid, message.voice.file_id)
        elif message.sticker:
            await bot.send_sticker(uid, message.sticker.file_id)
        elif message.document:
            await bot.send_document(uid, message.document.file_id, caption=message.caption or "")
        await message.answer("✅ Javob yuborildi!")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    await state.clear()


# ============================================================
#                   USER HANDLERS
# ============================================================
@router.message(CommandStart())
async def start_cmd(message: Message, bot: Bot):
    user = await get_user(message.from_user.id)
    is_new = user is None
    await create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    if is_new:
        await notify_new_user(bot, message.from_user)

    user = await get_user(message.from_user.id)
    if user and user['is_banned']:
        await message.answer("🚫 Siz botdan bloklangansiz.")
        return

    subscribed = await check_subscription(bot, message.from_user.id)
    if not subscribed:
        channels = await get_channels('telegram')
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=kb_subscribe([dict(ch) for ch in channels])
        )
        return

    await send_start_msg(message, bot)

async def send_start_msg(message: Message, bot: Bot):
    sm = await get_start_message()
    if sm:
        if sm['is_quote']:
            await message.answer(
                f"<blockquote>{sm['text']}</blockquote>",
                parse_mode="HTML", reply_markup=kb_main_menu()
            )
        elif sm['quote_link']:
            await message.answer(f"🔗 {sm['quote_link']}", reply_markup=kb_main_menu())
        elif sm['photo_id']:
            await bot.send_photo(
                message.from_user.id, sm['photo_id'],
                caption=sm['text'], reply_markup=kb_main_menu()
            )
        else:
            await message.answer(sm['text'], reply_markup=kb_main_menu())
    else:
        await message.answer(
            f"👋 Xush kelibsiz, <b>{message.from_user.full_name}</b>!\n\n"
            "🎬 Video kodini kiriting.",
            parse_mode="HTML", reply_markup=kb_main_menu()
        )

@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot: Bot):
    subscribed = await check_subscription(bot, call.from_user.id)
    if not subscribed:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
        return
    await call.message.delete()
    await call.message.answer("✅ Obuna bo'ldingiz! Botdan foydalanishingiz mumkin.", reply_markup=kb_main_menu())

# ----- KOD KIRITING -----
@router.message(F.text == "🎬 Kod kiriting")
async def ask_code(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user and user['is_banned']:
        await message.answer("🚫 Siz botdan bloklangansiz.")
        return
    await message.answer("🔑 Video kodini kiriting:")
    await state.set_state(UserStates.waiting_code)

@router.message(UserStates.waiting_code)
async def recv_code(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    code = message.text.strip().upper()
    video = await get_video(code)
    if not video:
        await message.answer("❌ Bunday kod topilmadi. Qayta urinib ko'ring.")
        return
    parts = await get_video_parts(code)
    if video['is_paid']:
        already = await has_purchased(message.from_user.id, code)
        if already:
            await message.answer(
                f"🎬 <b>{video['title']}</b>\n\nQaysi qismni ko'rmoqchisiz?",
                parse_mode="HTML",
                reply_markup=kb_video_parts(len(parts), code)
            )
            return
        user = await get_user(message.from_user.id)
        await message.answer(
            f"🎬 <b>{video['title']}</b>\n\n💰 Narxi: <b>{video['price']:,.0f} so'm</b>\n\nTo'lov usulini tanlang:",
            parse_mode="HTML",
            reply_markup=kb_payment(code, video['price'])
        )
    else:
        await message.answer(
            f"🎬 <b>{video['title']}</b>\n\nQaysi qismni ko'rmoqchisiz?",
            parse_mode="HTML",
            reply_markup=kb_video_parts(len(parts), code)
        )

# ----- VIDEO KO'RISH -----
@router.callback_query(F.data.startswith("part_"))
async def watch_part(call: CallbackQuery, bot: Bot):
    _, video_code, part_str = call.data.split("_", 2)
    part_num = int(part_str)
    video = await get_video(video_code)
    part = await get_video_part(video_code, part_num)
    if not part:
        await call.answer("❌ Qism topilmadi!", show_alert=True)
        return
    caption = (
        f"🎬 <b>{video['title']}</b>\n"
        f"📺 {part_num}-qism\n\n"
        f"{part['description'] or ''}"
    )
    await bot.send_video(
        call.from_user.id, part['file_id'],
        caption=caption, parse_mode="HTML",
        reply_markup=kb_video_actions(video_code, part_num)
    )
    await call.answer()

@router.callback_query(F.data == "close_video")
async def close_video(call: CallbackQuery):
    await call.message.delete()

# ----- TO'LOV (karta) -----
@router.callback_query(F.data.startswith("pay_card_"))
async def pay_card(call: CallbackQuery, state: FSMContext):
    video_code = call.data.replace("pay_card_", "")
    video = await get_video(video_code)
    await state.update_data(pay_code=video_code)
    await call.message.edit_text(
        f"💳 Karta: <code>{PAYMENT_CARD}</code>\n\n"
        f"💰 Miqdor: <b>{video['price']:,.0f} so'm</b>\n\n"
        f"To'lovni o'tkazib, chek (rasm yoki fayl) yuboring:",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_check)

@router.message(UserStates.waiting_check, F.photo | F.document)
async def recv_check(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    video_code = data.get('pay_code')
    video = await get_video(video_code)
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    pid = await add_payment(message.from_user.id, video_code, video['price'], file_id, 'video')
    await state.clear()
    await message.answer("✅ Chek qabul qilindi! Admin tasdiqlashini kuting...")
    for admin_id in ADMIN_IDS:
        try:
            cap = (
                f"💳 <b>Yangi to'lov so'rovi</b>\n\n"
                f"👤 {message.from_user.full_name}\n"
                f"🆔 <code>{message.from_user.id}</code>\n"
                f"🎬 {video['title']} (<code>{video_code}</code>)\n"
                f"💰 {video['price']:,.0f} so'm"
            )
            if message.photo:
                await bot.send_photo(admin_id, file_id, caption=cap, parse_mode="HTML",
                                     reply_markup=kb_confirm_payment(pid))
            else:
                await bot.send_document(admin_id, file_id, caption=cap, parse_mode="HTML",
                                        reply_markup=kb_confirm_payment(pid))
        except Exception:
            pass

# ----- TO'LOV (balans) -----
@router.callback_query(F.data.startswith("pay_balance_"))
async def pay_balance(call: CallbackQuery, bot: Bot):
    video_code = call.data.replace("pay_balance_", "")
    video = await get_video(video_code)
    user = await get_user(call.from_user.id)
    if user['balance'] < video['price']:
        await call.answer(
            f"❌ Balansingiz yetarli emas!\nBalans: {user['balance']:,.0f} so'm",
            show_alert=True
        )
        return
    await deduct_balance(call.from_user.id, video['price'])
    await add_purchase(call.from_user.id, video_code)
    parts = await get_video_parts(video_code)
    await call.message.edit_text(
        f"✅ Balansdan to'landi! ({video['price']:,.0f} so'm)\n\nQaysi qismni ko'rmoqchisiz?",
        reply_markup=kb_video_parts(len(parts), video_code)
    )

# ----- HISOBIM -----
@router.message(F.text == "💰 Hisobim")
async def my_balance(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Topilmadi.")
        return
    await message.answer(
        f"💰 <b>Hisobim</b>\n\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"💵 Balans: <b>{user['balance']:,.0f} so'm</b>\n"
        f"📊 Jami to'lagan: <b>{user['total_paid']:,.0f} so'm</b>",
        parse_mode="HTML",
        reply_markup=kb_balance_menu()
    )

@router.callback_query(F.data == "topup_balance")
async def topup_balance(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        f"💳 Karta: <code>{PAYMENT_CARD}</code>\n\n"
        "Qancha miqdor kiritmoqchisiz? (so'mda):",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_topup_amount)

@router.message(UserStates.waiting_topup_amount)
async def recv_topup_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        await state.update_data(topup_amount=amount)
        await message.answer(
            f"💳 {PAYMENT_CARD} kartasiga <b>{amount:,.0f} so'm</b> o'tkazing.\n\n"
            "Chek (rasm yoki fayl) yuboring:",
            parse_mode="HTML"
        )
        await state.set_state(UserStates.waiting_topup_check)
    except ValueError:
        await message.answer("❌ To'g'ri miqdor kiriting!")

@router.message(UserStates.waiting_topup_check, F.photo | F.document)
async def recv_topup_check(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get('topup_amount', 0)
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    pid = await add_payment(message.from_user.id, 'topup', amount, file_id, 'topup')
    await state.clear()
    await message.answer("✅ Chek qabul qilindi! Admin tasdiqlashini kuting...")
    for admin_id in ADMIN_IDS:
        try:
            cap = (
                f"💰 <b>Hisob to'ldirish</b>\n\n"
                f"👤 {message.from_user.full_name}\n"
                f"🆔 <code>{message.from_user.id}</code>\n"
                f"💵 Miqdor: <b>{amount:,.0f} so'm</b>"
            )
            if message.photo:
                await bot.send_photo(admin_id, file_id, caption=cap, parse_mode="HTML",
                                     reply_markup=kb_confirm_topup(pid))
            else:
                await bot.send_document(admin_id, file_id, caption=cap, parse_mode="HTML",
                                        reply_markup=kb_confirm_topup(pid))
        except Exception:
            pass

# ----- ADMINGA XABAR -----
@router.message(F.text.in_(["📩 Adminga xabar", "❓ Yordam"]))
async def msg_to_admin(message: Message, state: FSMContext):
    await message.answer("✉️ Xabarni yuboring (matn, rasm, ovozli xabar, stiker):")
    await state.set_state(UserStates.waiting_message_to_admin)

@router.message(UserStates.waiting_message_to_admin)
async def forward_to_admin(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    sender = message.from_user
    header = (
        f"📩 <b>Foydalanuvchidan xabar</b>\n"
        f"👤 {sender.full_name}\n"
        f"🆔 <code>{sender.id}</code>\n\n"
    )
    kb = kb_reply_user(sender.id)
    for admin_id in ADMIN_IDS:
        try:
            if message.text:
                await bot.send_message(admin_id, header + message.text, parse_mode="HTML", reply_markup=kb)
            elif message.photo:
                await bot.send_photo(admin_id, message.photo[-1].file_id,
                                     caption=header + (message.caption or ""), parse_mode="HTML", reply_markup=kb)
            elif message.voice:
                await bot.send_voice(admin_id, message.voice.file_id, caption=header, parse_mode="HTML", reply_markup=kb)
            elif message.sticker:
                await bot.send_message(admin_id, header, parse_mode="HTML", reply_markup=kb)
                await bot.send_sticker(admin_id, message.sticker.file_id)
            elif message.document:
                await bot.send_document(admin_id, message.document.file_id,
                                        caption=header + (message.caption or ""), parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
    await message.answer("✅ Xabaringiz adminga yuborildi!")


# ============================================================
#                        MAIN
# ============================================================
async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logger.info("✅ Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
