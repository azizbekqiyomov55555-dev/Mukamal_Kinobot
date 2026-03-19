#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kino Bot - To'liq versiya
"""

import asyncio
import logging
import io
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone, timedelta

import aiosqlite

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    BufferedInputFile
)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# ═══════════════════════ SOZLAMALAR ═══════════════════════
BOT_TOKEN    = "8655776547:AAEKHHQfCjvdwIgn_y4PH7de-b3g2Jd5iYs"
ADMIN_IDS    = [8537782289]
PAYMENT_CARD = "8600 0000 0000 0000"   # o'z karta raqamingizni kiriting
DB_PATH      = "bot.db"

TASHKENT_TZ  = timezone(timedelta(hours=5))

def now_tz():
    return datetime.now(TASHKENT_TZ)

def fmt_dt(s: str) -> str:
    try:
        return datetime.fromisoformat(s).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return s or "-"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ═══════════════════════ FSM ═══════════════════════
# ─────────── Start xabar (yangi tizim) ───────────
# Turlar: text, photo, quote, link, text_link
# Bitta forma: rasm (ixtiyoriy), matn, extra (link URL yoki quote muallif yoki text_link url|nom)

class AS(StatesGroup):
    add_video    = State()
    more_parts   = State()
    part_desc    = State()
    part_price   = State()   # har bir qism uchun narx
    video_title  = State()
    video_code   = State()
    video_price  = State()   # umumiy narx (0 kiritsangiz qismlar narxi ishlatiladi)
    ch_id        = State()
    ch_name      = State()
    # Start xabar yangi FSM qismlari:
    sm_photo     = State()   # ixtiyoriy rasm
    sm_text      = State()   # asosiy matn
    sm_type      = State()   # tur tanlash (text/photo/quote/link/text_link)
    sm_extra     = State()   # qo'shimcha (url, muallif, text_link)
    broadcast    = State()
    reply_user   = State()
    bal_id       = State()
    bal_amount   = State()
    bal_all      = State()
    ban_id       = State()
    unban_id     = State()

class US(StatesGroup):
    code         = State()
    pay_check    = State()
    topup_amount = State()
    topup_check  = State()
    help_msg     = State()

# ═══════════════════════ DATABASE ═══════════════════════
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            language    TEXT DEFAULT 'uz',
            balance     REAL DEFAULT 0,
            total_spent REAL DEFAULT 0,
            is_banned   INTEGER DEFAULT 0,
            joined_at   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS channels (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ch_id    TEXT UNIQUE NOT NULL,
            ch_name  TEXT NOT NULL,
            ch_type  TEXT DEFAULT 'telegram',
            added_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS videos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            code        TEXT UNIQUE NOT NULL,
            price       REAL DEFAULT 0,
            total_parts INTEGER DEFAULT 1,
            added_at    TEXT NOT NULL,
            added_by    INTEGER
        );
        CREATE TABLE IF NOT EXISTS video_parts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id    INTEGER NOT NULL,
            part_number INTEGER NOT NULL,
            file_id     TEXT NOT NULL,
            description TEXT,
            price       REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS user_purchases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            video_id    INTEGER NOT NULL,
            paid_amount REAL DEFAULT 0,
            paid_at     TEXT NOT NULL,
            UNIQUE(user_id, video_id)
        );
        CREATE TABLE IF NOT EXISTS video_shares (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL,
            video_id  INTEGER NOT NULL,
            shared_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            video_id     INTEGER,
            pay_type     TEXT NOT NULL,
            amount       REAL NOT NULL,
            check_fid    TEXT,
            status       TEXT DEFAULT 'pending',
            created_at   TEXT NOT NULL,
            confirmed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS topups (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            amount       REAL NOT NULL,
            check_fid    TEXT,
            status       TEXT DEFAULT 'pending',
            created_at   TEXT NOT NULL,
            confirmed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS start_msg (
            id       INTEGER PRIMARY KEY DEFAULT 1,
            msg_type TEXT DEFAULT 'text',
            content  TEXT,
            photo_id TEXT,
            extra    TEXT
        );
        CREATE TABLE IF NOT EXISTS help_msgs (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL,
            content  TEXT,
            file_id  TEXT,
            msg_type TEXT,
            sent_at  TEXT NOT NULL
        );
        """)
        await db.commit()
    log.info("DB tayyor.")

# ═══════════════════════ HELPERS ═══════════════════════
async def get_user(uid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (uid,)) as c:
            return await c.fetchone()

async def ensure_user(msg: Message):
    uid = msg.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id,username,full_name,joined_at)"
            " VALUES (?,?,?,?)",
            (uid, msg.from_user.username, msg.from_user.full_name, now_tz().isoformat())
        )
        await db.execute(
            "UPDATE users SET username=?,full_name=? WHERE telegram_id=?",
            (msg.from_user.username, msg.from_user.full_name, uid)
        )
        await db.commit()

def lang(u) -> str:
    return (u['language'] if u else None) or 'uz'

async def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

async def is_banned(uid: int) -> bool:
    u = await get_user(uid)
    return bool(u and u['is_banned'])

async def unsub_channels(bot: Bot, uid: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels") as c:
            chs = await c.fetchall()
    result = []
    for ch in chs:
        if ch['ch_type'] == 'instagram':
            # Instagram kanallar har doim ko'rsatiladi, obuna tekshirilmaydi
            result.append(ch)
        else:
            try:
                m = await bot.get_chat_member(ch['ch_id'], uid)
                if m.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                    result.append(ch)
            except Exception:
                result.append(ch)
    return result

async def unsub_telegram_only(bot: Bot, uid: int) -> bool:
    """Faqat Telegram kanallarni tekshiradi (obuna bo'lish shart)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels WHERE ch_type='telegram'") as c:
            chs = await c.fetchall()
    for ch in chs:
        try:
            m = await bot.get_chat_member(ch['ch_id'], uid)
            if m.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                return True
        except Exception:
            return True
    return False

async def get_start_msg():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM start_msg WHERE id=1") as c:
            return await c.fetchone()

# ═══════════════════════ TRANSLATIONS ═══════════════════════
T = {
    'uz': {
        'choose_lang'    : "Tilni tanlang:",
        'welcome'        : "Xush kelibsiz!",
        'btn_videos'     : "Videolar",
        'btn_account'    : "Hisobim",
        'btn_help'       : "Yordam",
        'btn_admin'      : "Admin panel",
        'enter_code'     : "Video kodini kiriting:",
        'code_not_found' : "Bunday kod topilmadi.",
        'choose_part'    : "{title}\n\nQaysi qismni ko'rmoqchisiz?",
        'paid_video'     : "Bu video pullik: {price} so'm",
        'btn_pay_card'   : "Karta orqali to'lov",
        'btn_pay_balance': "Balansdan to'lov",
        'btn_share'      : "Ulashish",
        'btn_close'      : "Yopish",
        'send_check'     : "Chek yuboring.\nKarta: <code>{card}</code>\nSumma: {amount} so'm",
        'check_sent'     : "Chekingiz adminga yuborildi.",
        'bal_info'       : "<b>Hisobingiz</b>\n\nID: <code>{id}</code>\nBalans: <b>{bal}</b> so'm\nSarflangan: {spent} so'm",
        'btn_topup'      : "Hisobni to'ldirish",
        'enter_topup'    : "Summani kiriting (so'm):",
        'send_topup_chk' : "Chek yuboring.\nKarta: <code>{card}</code>\nSumma: {amount} so'm",
        'topup_sent'     : "So'rovingiz yuborildi.",
        'not_subbed'     : "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
        'help_send'      : "Xabar, rasm, stiker yoki ovozli xabar yuboring:",
        'help_sent'      : "Xabaringiz adminga yuborildi.",
        'bal_added'      : "Hisobingizga {amount} so'm qo'shildi.",
        'pay_ok'         : "To'lovingiz tasdiqlandi!",
        'pay_fail'       : "To'lovingiz rad etildi.",
        'banned'         : "Siz ban qilindingiz.",
        'insuf'          : "Balansingiz yetarli emas.",
        'already_bought' : "Siz bu videoni oldin sotib olgansi. Qismni tanlang:",
        'free_video'     : "Bu video bepul!",
    },
    'ru': {
        'choose_lang'    : "Выберите язык:",
        'welcome'        : "Добро пожаловать!",
        'btn_videos'     : "Видео",
        'btn_account'    : "Мой счёт",
        'btn_help'       : "Помощь",
        'btn_admin'      : "Админ панель",
        'enter_code'     : "Введите код видео:",
        'code_not_found' : "Такой код не найден.",
        'choose_part'    : "{title}\n\nКакую часть посмотреть?",
        'paid_video'     : "Это платное видео: {price} сум",
        'btn_pay_card'   : "Оплата картой",
        'btn_pay_balance': "Оплата с баланса",
        'btn_share'      : "Поделиться",
        'btn_close'      : "Закрыть",
        'send_check'     : "Отправьте чек.\nКарта: <code>{card}</code>\nСумма: {amount} сум",
        'check_sent'     : "Чек отправлен администратору.",
        'bal_info'       : "<b>Ваш счёт</b>\n\nID: <code>{id}</code>\nБаланс: <b>{bal}</b> сум\nПотрачено: {spent} сум",
        'btn_topup'      : "Пополнить счёт",
        'enter_topup'    : "Введите сумму (сум):",
        'send_topup_chk' : "Отправьте чек.\nКарта: <code>{card}</code>\nСумма: {amount} сум",
        'topup_sent'     : "Запрос отправлен.",
        'not_subbed'     : "Для использования бота подпишитесь на каналы:",
        'help_send'      : "Отправьте сообщение, фото, стикер или голосовое:",
        'help_sent'      : "Ваше сообщение отправлено администратору.",
        'bal_added'      : "На счёт добавлено {amount} сум.",
        'pay_ok'         : "Оплата подтверждена!",
        'pay_fail'       : "Платёж отклонён.",
        'banned'         : "Вы заблокированы.",
        'insuf'          : "Недостаточно средств.",
        'already_bought' : "Вы уже купили это видео. Выберите часть:",
        'free_video'     : "Это видео бесплатное!",
    }
}

def tr(lg: str, key: str, **kw) -> str:
    txt = T.get(lg, T['uz']).get(key, key)
    return txt.format(**kw) if kw else txt

# ═══════════════════════ KEYBOARDS ═══════════════════════
def kb_lang():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="O'zbek tili", callback_data="lang:uz"),
        InlineKeyboardButton(text="Русский язык", callback_data="lang:ru"),
    ]])

def kb_main(lg: str, adm: bool = False):
    rows = [
        [KeyboardButton(text=tr(lg, 'btn_account')),
         KeyboardButton(text=tr(lg, 'btn_help'))],
    ]
    if adm:
        rows.append([KeyboardButton(text=tr(lg, 'btn_admin'))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def kb_sub(chs):
    rows = []
    for ch in chs:
        cid = ch['ch_id']
        cnm = ch['ch_name']
        url = cid if cid.startswith("http") else f"https://t.me/{cid.lstrip('@')}"
        rows.append([InlineKeyboardButton(text=cnm, url=url)])
    rows.append([InlineKeyboardButton(text="Tekshirish / Проверить", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_parts(vid: int, total: int, lg: str):
    rows, row = [], []
    for i in range(1, total + 1):
        lbl = f"{i}-qism" if lg == 'uz' else f"Часть {i}"
        row.append(InlineKeyboardButton(text=lbl, callback_data=f"watch:{vid}:{i}"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text=tr(lg, 'btn_share'), callback_data=f"share:{vid}"),
        InlineKeyboardButton(text=tr(lg, 'btn_close'), callback_data="close_msg"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_payment(vid: int, lg: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr(lg, 'btn_pay_card'),    callback_data=f"paycard:{vid}")],
        [InlineKeyboardButton(text=tr(lg, 'btn_pay_balance'), callback_data=f"paybal:{vid}")],
        [InlineKeyboardButton(text=tr(lg, 'btn_close'),       callback_data="close_msg")],
    ])

def kb_cpay(pid: int, uid: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Tasdiqlash",   callback_data=f"cpay:ok:{pid}:{uid}"),
        InlineKeyboardButton(text="Bekor qilish", callback_data=f"cpay:no:{pid}:{uid}"),
    ]])

def kb_ctop(tid: int, uid: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Tasdiqlash",   callback_data=f"ctop:ok:{tid}:{uid}"),
        InlineKeyboardButton(text="Bekor qilish", callback_data=f"ctop:no:{tid}:{uid}"),
    ]])

def kb_reply(uid: int, hid: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Javob yuborish", callback_data=f"replyhelp:{uid}:{hid}"),
    ]])

def kb_admin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Video qo'shish",     callback_data="adm:add_video")],
        [InlineKeyboardButton(text="Majburiy obuna",     callback_data="adm:channels")],
        [InlineKeyboardButton(text="Statistika (matn)",  callback_data="adm:stats"),
         InlineKeyboardButton(text="Statistika (rasm)",  callback_data="adm:stats_img")],
        [InlineKeyboardButton(text="Obunchilar",         callback_data="adm:subs")],
        [InlineKeyboardButton(text="Xabar yuborish",     callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="ID ga pul qo'sh",    callback_data="adm:bal_id")],
        [InlineKeyboardButton(text="Barchaga pul qo'sh", callback_data="adm:bal_all")],
        [InlineKeyboardButton(text="Ban",                callback_data="adm:ban"),
         InlineKeyboardButton(text="Bandan chiqarish",   callback_data="adm:unban")],
        [InlineKeyboardButton(text="Start xabar",        callback_data="adm:start_msg")],
        [InlineKeyboardButton(text="Yopish",             callback_data="adm:close")],
    ])

def kb_channels_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telegram kanal qo'shish",  callback_data="ch:add_tg")],
        [InlineKeyboardButton(text="Instagram link qo'shish",  callback_data="ch:add_ig")],
        [InlineKeyboardButton(text="Kanallar ro'yxati",        callback_data="ch:list")],
        [InlineKeyboardButton(text="Orqaga",                   callback_data="ch:back")],
    ])

# ═══════════════════════ STATISTICS IMAGE ═══════════════════════
async def make_stats_image() -> bytes:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                u.telegram_id,
                u.full_name,
                u.balance,
                COALESCE(SUM(up.paid_amount), 0) AS spent,
                (SELECT v.code FROM user_purchases up2
                 JOIN videos v ON v.id=up2.video_id
                 WHERE up2.user_id=u.telegram_id
                 ORDER BY up2.paid_at DESC LIMIT 1) AS last_code,
                (SELECT COUNT(*) FROM video_shares vs WHERE vs.user_id=u.telegram_id) AS shares,
                u.joined_at
            FROM users u
            LEFT JOIN user_purchases up ON up.user_id=u.telegram_id
            GROUP BY u.telegram_id
            ORDER BY u.joined_at DESC
            LIMIT 40
        """) as c:
            rows = await c.fetchall()

    col_labels = ["Ism", "ID", "Balans", "Sarflagan", "Kod", "Ulashdi", "Sana"]
    table_data = []
    for r in rows:
        name = (r['full_name'] or "Noma'lum")[:16]
        table_data.append([
            name,
            str(r['telegram_id']),
            f"{r['balance']:,.0f}",
            f"{r['spent']:,.0f}",
            r['last_code'] or "-",
            str(r['shares']),
            fmt_dt(r['joined_at']),
        ])

    if not table_data:
        table_data = [["-"] * 7]

    n    = len(table_data)
    figh = max(4, 1.5 + n * 0.42)
    fig, ax = plt.subplots(figsize=(16, figh))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.axis('off')

    tbl = ax.table(
        cellText  = table_data,
        colLabels = col_labels,
        cellLoc   = 'center',
        loc       = 'center',
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.scale(1, 1.7)

    for j in range(len(col_labels)):
        cell = tbl[0, j]
        cell.set_facecolor('#1565C0')
        cell.set_text_props(color='white', fontweight='bold')

    for i in range(1, n + 1):
        bg = '#E3F2FD' if i % 2 == 0 else 'white'
        for j in range(len(col_labels)):
            tbl[i, j].set_facecolor(bg)
            tbl[i, j].set_edgecolor('#BBDEFB')

    ax.set_title(
        f"Foydalanuvchilar statistikasi  |  {now_tz().strftime('%d.%m.%Y %H:%M')} (Toshkent)",
        fontsize=11, fontweight='bold', color='#0D47A1', pad=12
    )

    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=130, bbox_inches='tight', facecolor='white')
    plt.close()
    buf.seek(0)
    return buf.read()

# ═══════════════════════ ROUTER ═══════════════════════
router = Router()

# ─────────── /start ───────────
@router.message(CommandStart())
async def cmd_start(msg: Message, bot: Bot, state: FSMContext):
    await state.clear()
    await ensure_user(msg)
    u = await get_user(msg.from_user.id)

    if await is_banned(msg.from_user.id):
        await msg.answer(tr(lang(u), 'banned'))
        return

    if not u or u['language'] not in ('uz', 'ru'):
        await msg.answer(tr('uz', 'choose_lang'), reply_markup=kb_lang())
        return

    not_sub = await unsub_channels(bot, msg.from_user.id)
    if not_sub:
        # Faqat Telegram kanallar obuna bo'lish uchun shart
        tg_unsub = await unsub_telegram_only(bot, msg.from_user.id)
        if tg_unsub:
            await msg.answer(tr(lang(u), 'not_subbed'), reply_markup=kb_sub(not_sub))
            return
        # Faqat Instagram bor — ko'rsatamiz lekin bloklamaymiz
        await msg.answer(tr(lang(u), 'not_subbed'), reply_markup=kb_sub(not_sub))

    await send_start(msg, bot, u)

async def send_start(msg: Message, bot: Bot, u):
    lg  = lang(u)
    adm = await is_admin(msg.from_user.id)
    sm  = await get_start_msg()
    kb  = kb_main(lg, adm)

    if sm:
        mtype   = sm['msg_type']
        content = sm['content'] or tr(lg, 'welcome')
        photo   = sm['photo_id']
        extra   = sm['extra']

        if mtype == 'photo' and photo:
            await msg.answer_photo(photo, caption=content,
                                   parse_mode=ParseMode.HTML, reply_markup=kb)
        elif mtype == 'quote':
            txt = f"<blockquote>{content}</blockquote>"
            if extra: txt += f"\n\n— <i>{extra}</i>"
            await msg.answer(txt, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif mtype == 'link':
            # extra = URL
            txt = f"{content}\n\n{extra}" if extra else content
            await msg.answer(txt, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif mtype == 'text_link':
            # extra format: "URL|Ko'rsatiladigan nom"
            if extra and '|' in extra:
                url, name = extra.split('|', 1)
                txt = f"{content}\n\n<a href='{url.strip()}'>{name.strip()}</a>"
            else:
                txt = f"{content}\n\n{extra}" if extra else content
            await msg.answer(txt, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await msg.answer(content, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await msg.answer(tr(lg, 'welcome'), reply_markup=kb)

# ─────────── Til tanlash ───────────
@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: CallbackQuery, bot: Bot, state: FSMContext):
    lg = call.data.split(":")[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET language=? WHERE telegram_id=?",
                         (lg, call.from_user.id))
        await db.commit()
    await call.message.delete()
    u = await get_user(call.from_user.id)
    not_sub = await unsub_channels(bot, call.from_user.id)
    if not_sub:
        tg_unsub = await unsub_telegram_only(bot, call.from_user.id)
        if tg_unsub:
            await call.message.answer(tr(lg, 'not_subbed'), reply_markup=kb_sub(not_sub))
            await call.answer()
            return
        await call.message.answer(tr(lg, 'not_subbed'), reply_markup=kb_sub(not_sub))
    await send_start(call.message, bot, u)
    await call.answer()

# ─────────── Obuna tekshirish ───────────
@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, bot: Bot):
    u       = await get_user(call.from_user.id)
    # Faqat Telegram kanallarni tekshir
    has_unsub = await unsub_telegram_only(bot, call.from_user.id)
    if has_unsub:
        await call.answer("Hali obuna bo'lmagan kanallar bor!", show_alert=True)
        return
    lg  = lang(u)
    adm = await is_admin(call.from_user.id)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(tr(lg, 'welcome'), reply_markup=kb_main(lg, adm))
    await send_start(call.message, bot, u)
    await call.answer()

# ─────────── Videolar ───────────
MENU_BUTTONS = {"Hisobim", "Мой счёт", "Yordam", "Помощь", "Admin panel", "Админ панель"}

@router.message(F.text.in_(["Videolar", "Видео"]))
async def btn_videos(msg: Message, state: FSMContext):
    u = await get_user(msg.from_user.id)
    await msg.answer(tr(lang(u), 'enter_code'))

async def _search_video(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    u    = await get_user(msg.from_user.id)
    lg   = lang(u)
    code = msg.text.strip()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE code=?", (code,)) as c:
            video = await c.fetchone()

    if not video:
        await msg.answer(tr(lg, 'code_not_found'),
                         reply_markup=kb_main(lg, await is_admin(msg.from_user.id)))
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_purchases WHERE user_id=? AND video_id=?",
            (msg.from_user.id, video['id'])
        ) as c:
            purchased = await c.fetchone()

    if video['price'] > 0 and not purchased:
        txt = tr(lg, 'paid_video', price=f"{video['price']:,.0f}")
        await msg.answer(f"<b>{video['title']}</b>\n\n{txt}",
                         parse_mode=ParseMode.HTML,
                         reply_markup=kb_payment(video['id'], lg))
    else:
        if purchased:
            await msg.answer(tr(lg, 'already_bought'))
        else:
            await msg.answer(tr(lg, 'free_video'))
        await msg.answer(tr(lg, 'choose_part', title=video['title']),
                         reply_markup=kb_parts(video['id'], video['total_parts'], lg))

@router.message(US.code)
async def process_code_state(msg: Message, state: FSMContext, bot: Bot):
    await _search_video(msg, state, bot)

@router.message(F.text & ~F.text.func(lambda t: t in MENU_BUTTONS))
async def process_code_any(msg: Message, state: FSMContext, bot: Bot):
    current_state = await state.get_state()
    if current_state is not None:
        return
    await _search_video(msg, state, bot)

# ─────────── Video qism ───────────
@router.callback_query(F.data.startswith("watch:"))
async def cb_watch(call: CallbackQuery):
    _, vid, pnum = call.data.split(":")
    vid, pnum = int(vid), int(pnum)
    u  = await get_user(call.from_user.id)
    lg = lang(u)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM video_parts WHERE video_id=? AND part_number=?", (vid, pnum)
        ) as c:
            part = await c.fetchone()
        async with db.execute("SELECT * FROM videos WHERE id=?", (vid,)) as c:
            video = await c.fetchone()

    if not part:
        await call.answer("Qism topilmadi.", show_alert=True)
        return

    part_lbl = f"{pnum}-qism" if lg == 'uz' else f"Часть {pnum}"
    caption  = f"<b>{video['title']}</b> — {part_lbl}"
    if part['description']:
        caption += f"\n\n{part['description']}"

    close_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tr(lg, 'btn_share'), callback_data=f"share:{vid}"),
        InlineKeyboardButton(text=tr(lg, 'btn_close'), callback_data="close_msg"),
    ]])
    await call.message.answer_video(part['file_id'], caption=caption,
                                    parse_mode=ParseMode.HTML, reply_markup=close_kb)
    await call.answer()

@router.callback_query(F.data == "close_msg")
async def cb_close(call: CallbackQuery):
    await call.message.delete()
    await call.answer()

@router.callback_query(F.data.startswith("share:"))
async def cb_share(call: CallbackQuery, bot: Bot):
    vid = int(call.data.split(":")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO video_shares (user_id,video_id,shared_at) VALUES (?,?,?)",
            (call.from_user.id, vid, now_tz().isoformat())
        )
        await db.commit()
    me = await bot.get_me()
    await call.message.answer(f"Havolani do'stlarga yuboring:\nhttps://t.me/{me.username}")
    await call.answer()

# ─────────── Karta to'lov ───────────
@router.callback_query(F.data.startswith("paycard:"))
async def cb_paycard(call: CallbackQuery, state: FSMContext):
    vid = int(call.data.split(":")[1])
    u   = await get_user(call.from_user.id)
    lg  = lang(u)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT price FROM videos WHERE id=?", (vid,)) as c:
            video = await c.fetchone()
    await state.set_data({"vid": vid, "amount": video['price']})
    await state.set_state(US.pay_check)
    await call.message.answer(
        tr(lg, 'send_check', card=PAYMENT_CARD, amount=f"{video['price']:,.0f}"),
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.message(US.pay_check, F.photo | F.document)
async def rx_pay_check(msg: Message, state: FSMContext, bot: Bot):
    data          = await state.get_data()
    await state.clear()
    vid, amount   = data['vid'], data['amount']
    u             = await get_user(msg.from_user.id)
    lg            = lang(u)
    fid           = msg.photo[-1].file_id if msg.photo else msg.document.file_id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT title FROM videos WHERE id=?", (vid,)) as c:
            v = await c.fetchone()
        cur = await db.execute(
            "INSERT INTO payments (user_id,video_id,pay_type,amount,check_fid,status,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (msg.from_user.id, vid, 'video', amount, fid, 'pending', now_tz().isoformat())
        )
        pid = cur.lastrowid
        await db.commit()

    adm_txt = (
        f"<b>To'lov so'rovi</b>\n\n"
        f"{msg.from_user.full_name} (<code>{msg.from_user.id}</code>)\n"
        f"Video: {v['title'] if v else '?'}\n"
        f"{amount:,.0f} so'm | {now_tz().strftime('%d.%m.%Y %H:%M')}"
    )
    for aid in ADMIN_IDS:
        try:
            if msg.photo:
                await bot.send_photo(aid, fid, caption=adm_txt,
                                     parse_mode=ParseMode.HTML,
                                     reply_markup=kb_cpay(pid, msg.from_user.id))
            else:
                await bot.send_document(aid, fid, caption=adm_txt,
                                        parse_mode=ParseMode.HTML,
                                        reply_markup=kb_cpay(pid, msg.from_user.id))
        except Exception:
            pass

    await msg.answer(tr(lg, 'check_sent'),
                     reply_markup=kb_main(lg, await is_admin(msg.from_user.id)))

# ─────────── Balansdan to'lov ───────────
@router.callback_query(F.data.startswith("paybal:"))
async def cb_paybal(call: CallbackQuery):
    vid = int(call.data.split(":")[1])
    u   = await get_user(call.from_user.id)
    lg  = lang(u)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE id=?", (vid,)) as c:
            video = await c.fetchone()

    if u['balance'] < video['price']:
        await call.answer(tr(lg, 'insuf'), show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance=balance-?,total_spent=total_spent+? WHERE telegram_id=?",
            (video['price'], video['price'], call.from_user.id)
        )
        await db.execute(
            "INSERT OR IGNORE INTO user_purchases (user_id,video_id,paid_amount,paid_at)"
            " VALUES (?,?,?,?)",
            (call.from_user.id, vid, video['price'], now_tz().isoformat())
        )
        await db.commit()

    await call.message.delete()
    await call.message.answer(tr(lg, 'pay_ok'))
    await call.message.answer(
        tr(lg, 'choose_part', title=video['title']),
        reply_markup=kb_parts(vid, video['total_parts'], lg)
    )
    await call.answer()

# ─────────── Admin: to'lov tasdiqlash ───────────
@router.callback_query(F.data.startswith("cpay:"))
async def cb_cpay_handler(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    _, action, pid, uid = call.data.split(":")
    pid, uid = int(pid), int(uid)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payments WHERE id=?", (pid,)) as c:
            pay = await c.fetchone()

    if not pay or pay['status'] != 'pending':
        await call.answer("Allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    u  = await get_user(uid)
    lg = lang(u)

    if action == 'ok':
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE payments SET status='confirmed',confirmed_at=? WHERE id=?",
                (now_tz().isoformat(), pid)
            )
            await db.execute(
                "INSERT OR IGNORE INTO user_purchases (user_id,video_id,paid_amount,paid_at)"
                " VALUES (?,?,?,?)",
                (uid, pay['video_id'], pay['amount'], now_tz().isoformat())
            )
            await db.commit()
        try:
            await bot.send_message(uid, tr(lg, 'pay_ok'))
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM videos WHERE id=?", (pay['video_id'],)) as c:
                    v = await c.fetchone()
            if v:
                await bot.send_message(uid, tr(lg, 'choose_part', title=v['title']),
                                       reply_markup=kb_parts(v['id'], v['total_parts'], lg))
        except Exception:
            pass
        label = "TASDIQLANDI"
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE payments SET status='rejected' WHERE id=?", (pid,))
            await db.commit()
        try:
            await bot.send_message(uid, tr(lg, 'pay_fail'))
        except Exception:
            pass
        label = "RAD ETILDI"

    try:
        old = call.message.caption or ""
        await call.message.edit_caption(old + f"\n\n<b>{label}</b>",
                                        parse_mode=ParseMode.HTML, reply_markup=None)
    except Exception:
        pass
    await call.answer(label)

# ─────────── Hisobim ───────────
@router.message(F.text.in_(["Hisobim", "Мой счёт"]))
async def btn_account(msg: Message):
    u  = await get_user(msg.from_user.id)
    lg = lang(u)
    txt = tr(lg, 'bal_info',
             id=msg.from_user.id,
             bal=f"{u['balance']:,.0f}",
             spent=f"{u['total_spent']:,.0f}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=tr(lg, 'btn_topup'), callback_data="topup")
    ]])
    await msg.answer(txt, parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data == "topup")
async def cb_topup(call: CallbackQuery, state: FSMContext):
    u = await get_user(call.from_user.id)
    await state.set_state(US.topup_amount)
    await call.message.answer(tr(lang(u), 'enter_topup'))
    await call.answer()

@router.message(US.topup_amount)
async def rx_topup_amount(msg: Message, state: FSMContext):
    u  = await get_user(msg.from_user.id)
    lg = lang(u)
    try:
        amount = float(msg.text.strip())
    except Exception:
        await msg.answer("Raqam kiriting!")
        return
    await state.set_data({"amount": amount})
    await state.set_state(US.topup_check)
    await msg.answer(tr(lg, 'send_topup_chk', card=PAYMENT_CARD, amount=f"{amount:,.0f}"),
                     parse_mode=ParseMode.HTML)

@router.message(US.topup_check, F.photo | F.document)
async def rx_topup_check(msg: Message, state: FSMContext, bot: Bot):
    data   = await state.get_data()
    await state.clear()
    amount = data['amount']
    u      = await get_user(msg.from_user.id)
    lg     = lang(u)
    fid    = msg.photo[-1].file_id if msg.photo else msg.document.file_id

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO topups (user_id,amount,check_fid,status,created_at) VALUES (?,?,?,?,?)",
            (msg.from_user.id, amount, fid, 'pending', now_tz().isoformat())
        )
        tid = cur.lastrowid
        await db.commit()

    adm_txt = (
        f"<b>Hisobni to'ldirish</b>\n\n"
        f"{msg.from_user.full_name} (<code>{msg.from_user.id}</code>)\n"
        f"{amount:,.0f} so'm | {now_tz().strftime('%d.%m.%Y %H:%M')}"
    )
    for aid in ADMIN_IDS:
        try:
            if msg.photo:
                await bot.send_photo(aid, fid, caption=adm_txt,
                                     parse_mode=ParseMode.HTML,
                                     reply_markup=kb_ctop(tid, msg.from_user.id))
            else:
                await bot.send_document(aid, fid, caption=adm_txt,
                                        parse_mode=ParseMode.HTML,
                                        reply_markup=kb_ctop(tid, msg.from_user.id))
        except Exception:
            pass
    await msg.answer(tr(lg, 'topup_sent'),
                     reply_markup=kb_main(lg, await is_admin(msg.from_user.id)))

@router.callback_query(F.data.startswith("ctop:"))
async def cb_ctop_handler(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    _, action, tid, uid = call.data.split(":")
    tid, uid = int(tid), int(uid)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM topups WHERE id=?", (tid,)) as c:
            top = await c.fetchone()

    if not top or top['status'] != 'pending':
        await call.answer("Allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    u  = await get_user(uid)
    lg = lang(u)

    if action == 'ok':
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE topups SET status='confirmed',confirmed_at=? WHERE id=?",
                (now_tz().isoformat(), tid)
            )
            await db.execute(
                "UPDATE users SET balance=balance+? WHERE telegram_id=?",
                (top['amount'], uid)
            )
            await db.commit()
        try:
            await bot.send_message(uid, tr(lg, 'bal_added', amount=f"{top['amount']:,.0f}"))
        except Exception:
            pass
        label = "TASDIQLANDI"
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE topups SET status='rejected' WHERE id=?", (tid,))
            await db.commit()
        try:
            await bot.send_message(uid, tr(lg, 'pay_fail'))
        except Exception:
            pass
        label = "RAD ETILDI"

    try:
        old = call.message.caption or ""
        await call.message.edit_caption(old + f"\n\n<b>{label}</b>",
                                        parse_mode=ParseMode.HTML, reply_markup=None)
    except Exception:
        pass
    await call.answer(label)

# ─────────── Yordam ───────────
@router.message(F.text.in_(["Yordam", "Помощь"]))
async def btn_help(msg: Message, state: FSMContext):
    u = await get_user(msg.from_user.id)
    await state.set_state(US.help_msg)
    await msg.answer(tr(lang(u), 'help_send'), reply_markup=ReplyKeyboardRemove())

@router.message(US.help_msg)
async def rx_help(msg: Message, state: FSMContext, bot: Bot):
    u  = await get_user(msg.from_user.id)
    lg = lang(u)
    await state.clear()

    fid, mtype = None, 'text'
    content = msg.text or msg.caption or ""
    if msg.photo:     fid, mtype = msg.photo[-1].file_id, 'photo'
    elif msg.document: fid, mtype = msg.document.file_id, 'document'
    elif msg.sticker:  fid, mtype = msg.sticker.file_id, 'sticker'
    elif msg.voice:    fid, mtype = msg.voice.file_id, 'voice'
    elif msg.video:    fid, mtype = msg.video.file_id, 'video'

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO help_msgs (user_id,content,file_id,msg_type,sent_at) VALUES (?,?,?,?,?)",
            (msg.from_user.id, content, fid, mtype, now_tz().isoformat())
        )
        hid = cur.lastrowid
        await db.commit()

    adm_txt = (
        f"<b>Yordam so'rovi</b>\n\n"
        f"{msg.from_user.full_name} (<code>{msg.from_user.id}</code>)\n"
        f"{now_tz().strftime('%d.%m.%Y %H:%M')}"
    )
    if content: adm_txt += f"\n\n{content}"
    rkb = kb_reply(msg.from_user.id, hid)

    for aid in ADMIN_IDS:
        try:
            if mtype == 'photo':
                await bot.send_photo(aid, fid, caption=adm_txt,
                                     parse_mode=ParseMode.HTML, reply_markup=rkb)
            elif mtype == 'document':
                await bot.send_document(aid, fid, caption=adm_txt,
                                        parse_mode=ParseMode.HTML, reply_markup=rkb)
            elif mtype == 'voice':
                await bot.send_voice(aid, fid, caption=adm_txt,
                                     parse_mode=ParseMode.HTML, reply_markup=rkb)
            elif mtype == 'video':
                await bot.send_video(aid, fid, caption=adm_txt,
                                     parse_mode=ParseMode.HTML, reply_markup=rkb)
            elif mtype == 'sticker':
                await bot.send_message(aid, adm_txt, parse_mode=ParseMode.HTML)
                await bot.send_sticker(aid, fid)
                await bot.send_message(aid, "^", reply_markup=rkb)
            else:
                await bot.send_message(aid, adm_txt, parse_mode=ParseMode.HTML, reply_markup=rkb)
        except Exception:
            pass

    await msg.answer(tr(lg, 'help_sent'),
                     reply_markup=kb_main(lg, await is_admin(msg.from_user.id)))

@router.callback_query(F.data.startswith("replyhelp:"))
async def cb_replyhelp(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    _, uid, hid = call.data.split(":")
    await state.set_data({"reply_uid": int(uid)})
    await state.set_state(AS.reply_user)
    await call.message.answer(f"Foydalanuvchi {uid} ga javob yuboring:")
    await call.answer()

@router.message(AS.reply_user)
async def rx_reply_user(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid  = data['reply_uid']
    await state.clear()
    try:
        if msg.photo:
            await bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
        elif msg.document:
            await bot.send_document(uid, msg.document.file_id, caption=msg.caption or "")
        elif msg.voice:
            await bot.send_voice(uid, msg.voice.file_id)
        elif msg.video:
            await bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
        elif msg.sticker:
            await bot.send_sticker(uid, msg.sticker.file_id)
        else:
            await bot.send_message(uid, msg.text or "")
        await msg.answer(f"Javob {uid} ga yuborildi.")
    except Exception as e:
        await msg.answer(f"Xato: {e}")

# ═══════════════════════ ADMIN PANEL ═══════════════════════
@router.message(F.text.in_(["Admin panel", "Админ панель"]))
async def btn_admin(msg: Message):
    if not await is_admin(msg.from_user.id):
        return
    await msg.answer("<b>Admin panel</b>", parse_mode=ParseMode.HTML,
                     reply_markup=kb_admin())

@router.callback_query(F.data == "adm:close")
async def adm_close(call: CallbackQuery):
    await call.message.delete()
    await call.answer()

# ─────────── Majburiy obuna kanallar ───────────
@router.callback_query(F.data == "adm:channels")
async def adm_channels(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    await call.message.answer("<b>Majburiy obuna kanallar</b>",
                              parse_mode=ParseMode.HTML,
                              reply_markup=kb_channels_menu())
    await call.answer()

@router.callback_query(F.data == "ch:back")
async def ch_back(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("<b>Admin panel</b>", parse_mode=ParseMode.HTML,
                              reply_markup=kb_admin())
    await call.answer()

@router.callback_query(F.data == "ch:add_tg")
async def ch_add_tg(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.update_data({"ch_type": "telegram"})
    await state.set_state(AS.ch_id)
    await call.message.answer(
        "Telegram kanal ID yoki @username kiriting:\n"
        "Misol: @mychanel yoki -1001234567890"
    )
    await call.answer()

@router.callback_query(F.data == "ch:add_ig")
async def ch_add_ig(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.update_data({"ch_type": "instagram"})
    await state.set_state(AS.ch_id)
    await call.message.answer(
        "Instagram sahifa havolasini kiriting:\n"
        "Misol: https://instagram.com/mypage"
    )
    await call.answer()

@router.message(AS.ch_id)
async def rx_ch_id(msg: Message, state: FSMContext):
    await state.update_data({"ch_id": msg.text.strip()})
    await state.set_state(AS.ch_name)
    await msg.answer("Kanal nomini kiriting:")

@router.message(AS.ch_name)
async def rx_ch_name(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT OR REPLACE INTO channels (ch_id,ch_name,ch_type,added_at)"
                " VALUES (?,?,?,?)",
                (data['ch_id'], msg.text.strip(),
                 data.get('ch_type', 'telegram'), now_tz().isoformat())
            )
            await db.commit()
            tp = "Telegram" if data.get('ch_type') == 'telegram' else "Instagram"
            await msg.answer(f"{tp} kanal qo'shildi: <b>{msg.text.strip()}</b>",
                             parse_mode=ParseMode.HTML)
        except Exception as e:
            await msg.answer(f"Xato: {e}")

@router.callback_query(F.data == "ch:list")
async def ch_list(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels") as c:
            chs = await c.fetchall()

    if not chs:
        await call.message.answer("Kanallar yo'q.")
        await call.answer()
        return

    rows, del_kb = [], []
    for ch in chs:
        tp = "TG" if ch['ch_type'] == 'telegram' else "IG"
        rows.append(f"[{tp}] <b>{ch['ch_name']}</b> — <code>{ch['ch_id']}</code>")
        del_kb.append([InlineKeyboardButton(
            text=f"O'chirish: {ch['ch_name']}",
            callback_data=f"ch:del:{ch['id']}"
        )])

    await call.message.answer(
        "<b>Kanallar:</b>\n\n" + "\n".join(rows),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=del_kb)
    )
    await call.answer()

@router.callback_query(F.data.startswith("ch:del:"))
async def ch_del(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    cid = int(call.data.split(":")[2])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE id=?", (cid,))
        await db.commit()
    await call.message.edit_text("Kanal o'chirildi.")
    await call.answer()

# ─────────── Video qo'shish ───────────
@router.callback_query(F.data == "adm:add_video")
async def adm_add_video(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_data({"parts": [], "descs": []})
    await state.set_state(AS.add_video)
    await call.message.answer("<b>1-qism</b> videoni yuboring:", parse_mode=ParseMode.HTML)
    await call.answer()

@router.message(AS.add_video, F.video)
async def rx_video_part(msg: Message, state: FSMContext):
    data  = await state.get_data()
    parts = data.get("parts", [])
    n     = len(parts) + 1
    parts.append({"num": n, "fid": msg.video.file_id})
    await state.update_data({"parts": parts})
    await state.set_state(AS.more_parts)
    await msg.answer(
        f"{n}-qism qabul qilindi. Yana qism bormi?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"{n+1}-qism qo'shish", callback_data="vp:more"),
            InlineKeyboardButton(text="Tugadi",               callback_data="vp:done"),
        ]])
    )

@router.callback_query(F.data == "vp:more")
async def vp_more(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    n    = len(data.get("parts", [])) + 1
    await state.set_state(AS.add_video)
    await call.message.answer(f"<b>{n}-qism</b> videoni yuboring:", parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data == "vp:done")
async def vp_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    n    = len(data.get("parts", []))
    await state.update_data({"descs": [], "prices": [], "desc_idx": 0})
    await state.set_state(AS.part_desc)
    await call.message.answer(
        f"{n} ta qism qabul qilindi.\n\n<b>1-qism</b> uchun tavsif kiriting (yoki - yozing):",
        parse_mode=ParseMode.HTML
    )
    await call.answer()

@router.message(AS.part_desc)
async def rx_part_desc(msg: Message, state: FSMContext):
    data  = await state.get_data()
    descs = data.get("descs", [])
    descs.append(msg.text.strip() if msg.text.strip() != '-' else "")
    await state.update_data({"descs": descs})
    # Narx so'raymiz
    await state.set_state(AS.part_price)
    await msg.answer(f"<b>{len(descs)}-qism</b> narxini kiriting (bepul = 0):",
                     parse_mode=ParseMode.HTML)

@router.message(AS.part_price)
async def rx_part_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.strip())
    except Exception:
        await msg.answer("Raqam kiriting! (bepul bo'lsa 0)"); return
    data   = await state.get_data()
    prices = data.get("prices", [])
    prices.append(price)
    parts  = data.get("parts", [])
    descs  = data.get("descs", [])
    await state.update_data({"prices": prices})
    if len(descs) < len(parts):
        await state.set_state(AS.part_desc)
        await msg.answer(f"<b>{len(descs)+1}-qism</b> uchun tavsif kiriting (yoki - yozing):",
                         parse_mode=ParseMode.HTML)
    else:
        await state.set_state(AS.video_title)
        await msg.answer("Video nomini kiriting:")

@router.message(AS.video_title)
async def rx_video_title(msg: Message, state: FSMContext):
    await state.update_data({"title": msg.text.strip()})
    await state.set_state(AS.video_code)
    await msg.answer("Video kodi kiriting (foydalanuvchilar shu kodni kiritadi):")

@router.message(AS.video_code)
async def rx_video_code(msg: Message, state: FSMContext):
    await state.update_data({"code": msg.text.strip()})
    await state.set_state(AS.video_price)
    await msg.answer("Narxini kiriting (bepul = 0):")

@router.message(AS.video_price)
async def rx_video_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.strip())
    except Exception:
        await msg.answer("Raqam kiriting!"); return
    data   = await state.get_data()
    await state.clear()
    parts  = data.get("parts", [])
    descs  = data.get("descs", [])
    prices = data.get("prices", [])

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute(
                "INSERT INTO videos (title,code,price,total_parts,added_at,added_by)"
                " VALUES (?,?,?,?,?,?)",
                (data['title'], data['code'], price,
                 len(parts), now_tz().isoformat(), msg.from_user.id)
            )
            vid = cur.lastrowid
            for i, p in enumerate(parts):
                desc       = descs[i] if i < len(descs) else ""
                part_price = prices[i] if i < len(prices) else 0
                await db.execute(
                    "INSERT INTO video_parts (video_id,part_number,file_id,description,price)"
                    " VALUES (?,?,?,?,?)",
                    (vid, p['num'], p['fid'], desc, part_price)
                )
            await db.commit()

            # Qismlar narxlari matni
            parts_info = ""
            for i in range(len(parts)):
                p_price = prices[i] if i < len(prices) else 0
                p_label = f"bepul" if p_price == 0 else f"{p_price:,.0f} so'm"
                parts_info += f"\n  {i+1}-qism: {p_label}"

            await msg.answer(
                f"<b>Video qo'shildi!</b>\n\n"
                f"Nom: {data['title']}\n"
                f"Kod: <code>{data['code']}</code>\n"
                f"Umumiy narx: {price:,.0f} so'm\n"
                f"Qismlar ({len(parts)}):{parts_info}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await msg.answer(f"Xato: {e}")

# ─────────── Statistika ───────────
@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned=0") as c:
            active = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM videos") as c:
            vids = (await c.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(paid_amount),0) FROM user_purchases") as c:
            rev = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM payments WHERE status='confirmed'") as c:
            pays = (await c.fetchone())[0]
    txt = (
        f"<b>Statistika</b>\n\n"
        f"Jami foydalanuvchilar: <b>{total}</b>\n"
        f"Faol: <b>{active}</b> | Banned: <b>{total-active}</b>\n"
        f"Videolar: <b>{vids}</b>\n"
        f"Jami daromad: <b>{rev:,.0f}</b> so'm\n"
        f"Tasdiqlangan to'lovlar: <b>{pays}</b>\n\n"
        f"{now_tz().strftime('%d.%m.%Y %H:%M')} (Toshkent)"
    )
    await call.message.answer(txt, parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data == "adm:stats_img")
async def adm_stats_img(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        return
    await call.answer("Rasm tayyorlanmoqda...")
    img = await make_stats_image()
    await bot.send_photo(
        call.from_user.id,
        BufferedInputFile(img, filename="stats.png"),
        caption=f"Statistika | {now_tz().strftime('%d.%m.%Y %H:%M')} (Toshkent)"
    )

# ─────────── Obunchilar ───────────
@router.callback_query(F.data == "adm:subs")
async def adm_subs(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY joined_at DESC LIMIT 25") as c:
            users = await c.fetchall()

    if not users:
        await call.message.answer("Foydalanuvchilar yo'q.")
        await call.answer()
        return

    for u in users:
        name  = u['full_name'] or "Noma'lum"
        uname = f"@{u['username']}" if u['username'] else "-"
        txt = (
            f"<b>{name}</b> ({uname})\n"
            f"ID: <code>{u['telegram_id']}</code>\n"
            f"Qo'shilgan: {fmt_dt(u['joined_at'])}\n"
            f"Balans: {u['balance']:,.0f} so'm"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Xabar yuborish",
                                 url=f"tg://user?id={u['telegram_id']}")
        ]])
        await call.message.answer(txt, parse_mode=ParseMode.HTML, reply_markup=kb)
    await call.answer()

# ─────────── Broadcast ───────────
@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_data({"reply_uid": None})
    await state.set_state(AS.broadcast)
    await call.message.answer("Barcha foydalanuvchilarga xabar yuboring:")
    await call.answer()

@router.message(AS.broadcast)
async def rx_broadcast(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT telegram_id FROM users WHERE is_banned=0") as c:
            uids = [r[0] for r in await c.fetchall()]

    ok = fail = 0
    for uid in uids:
        try:
            if msg.photo:
                await bot.send_photo(uid, msg.photo[-1].file_id,
                                     caption=msg.caption or "",
                                     parse_mode=ParseMode.HTML)
            elif msg.document:
                await bot.send_document(uid, msg.document.file_id,
                                        caption=msg.caption or "",
                                        parse_mode=ParseMode.HTML)
            elif msg.voice:
                await bot.send_voice(uid, msg.voice.file_id)
            elif msg.video:
                await bot.send_video(uid, msg.video.file_id,
                                     caption=msg.caption or "",
                                     parse_mode=ParseMode.HTML)
            elif msg.sticker:
                await bot.send_sticker(uid, msg.sticker.file_id)
            else:
                await bot.send_message(uid, msg.text or "",
                                       parse_mode=ParseMode.HTML)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)

    await msg.answer(f"Yuborildi: {ok} | Xato: {fail}")

# ─────────── Balans boshqaruvi ───────────
@router.callback_query(F.data == "adm:bal_id")
async def adm_bal_id(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AS.bal_id)
    await call.message.answer("Foydalanuvchi ID raqamini kiriting:")
    await call.answer()

@router.message(AS.bal_id)
async def rx_bal_id(msg: Message, state: FSMContext):
    try:
        await state.update_data({"uid": int(msg.text.strip())})
        await state.set_state(AS.bal_amount)
        await msg.answer("Qo'shiladigan summani kiriting (so'm):")
    except Exception:
        await msg.answer("Raqam kiriting!")

@router.message(AS.bal_amount)
async def rx_bal_amount(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    try:
        amount = float(msg.text.strip())
    except Exception:
        await msg.answer("Raqam kiriting!"); return
    uid = data['uid']
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?",
                         (amount, uid))
        await db.commit()
    u = await get_user(uid)
    try:
        await bot.send_message(uid, tr(lang(u), 'bal_added', amount=f"{amount:,.0f}"))
    except Exception:
        pass
    await msg.answer(f"{uid} ga {amount:,.0f} so'm qo'shildi.")

@router.callback_query(F.data == "adm:bal_all")
async def adm_bal_all(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AS.bal_all)
    await call.message.answer("Barchaga qo'shiladigan summani kiriting:")
    await call.answer()

@router.message(AS.bal_all)
async def rx_bal_all(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    try:
        amount = float(msg.text.strip())
    except Exception:
        await msg.answer("Raqam kiriting!"); return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE is_banned=0", (amount,))
        await db.commit()
        async with db.execute("SELECT telegram_id FROM users WHERE is_banned=0") as c:
            uids = [r[0] for r in await c.fetchall()]

    for uid in uids:
        try:
            u = await get_user(uid)
            await bot.send_message(uid, tr(lang(u), 'bal_added', amount=f"{amount:,.0f}"))
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await msg.answer(f"Barchaga {amount:,.0f} so'm qo'shildi.")

# ─────────── Ban / Unban ───────────
@router.callback_query(F.data == "adm:ban")
async def adm_ban(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AS.ban_id)
    await call.message.answer("Ban qilinadigan foydalanuvchi ID:")
    await call.answer()

@router.message(AS.ban_id)
async def rx_ban(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    try:
        uid = int(msg.text.strip())
    except Exception:
        await msg.answer("Raqam kiriting!"); return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=1 WHERE telegram_id=?", (uid,))
        await db.commit()
    try:
        await bot.send_message(uid, "Siz ban qilindingiz.")
    except Exception:
        pass
    await msg.answer(f"{uid} ban qilindi.")

@router.callback_query(F.data == "adm:unban")
async def adm_unban(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AS.unban_id)
    await call.message.answer("Bandan chiqariladigan foydalanuvchi ID:")
    await call.answer()

@router.message(AS.unban_id)
async def rx_unban(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    try:
        uid = int(msg.text.strip())
    except Exception:
        await msg.answer("Raqam kiriting!"); return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=0 WHERE telegram_id=?", (uid,))
        await db.commit()
    try:
        await bot.send_message(uid, "Bandan chiqarildingiz.")
    except Exception:
        pass
    await msg.answer(f"{uid} bandan chiqarildi.")

# ─────────── Start xabar (yangi bitta forma) ───────────
@router.callback_query(F.data == "adm:start_msg")
async def adm_start_msg(call: CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id):
        return
    await state.set_state(AS.sm_type)
    await call.message.answer(
        "📝 <b>Start xabar turini tanlang:</b>\n\n"
        "• <b>Matn</b> — oddiy matn\n"
        "• <b>Rasm + matn</b> — rasm va matn\n"
        "• <b>Iqtibos</b> — citata ko'rinishida\n"
        "• <b>Link</b> — matn + havola URL\n"
        "• <b>Matnli havola</b> — matn + <a href='...'>nom</a> ko'rinishida",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Matn",          callback_data="sm:text")],
            [InlineKeyboardButton(text="🖼 Rasm + matn",   callback_data="sm:photo")],
            [InlineKeyboardButton(text="💬 Iqtibos",       callback_data="sm:quote")],
            [InlineKeyboardButton(text="🔗 Link",          callback_data="sm:link")],
            [InlineKeyboardButton(text="🔤 Matnli havola", callback_data="sm:text_link")],
        ])
    )
    await call.answer()

@router.callback_query(F.data.startswith("sm:"))
async def cb_sm_type(call: CallbackQuery, state: FSMContext):
    mtype = call.data.split(":")[1]
    await state.update_data({"mtype": mtype})
    if mtype == 'photo':
        await state.set_state(AS.sm_photo)
        await call.message.answer("📷 Rasm yuboring (yoki /skip yozing o'tkazib yuborish uchun):")
    else:
        await state.set_state(AS.sm_text)
        await call.message.answer("✏️ Asosiy matni kiriting:")
    await call.answer()

@router.message(AS.sm_photo)
async def rx_sm_photo(msg: Message, state: FSMContext):
    if msg.photo:
        await state.update_data({"photo_id": msg.photo[-1].file_id})
    await state.set_state(AS.sm_text)
    await msg.answer("✏️ Rasm uchun matn kiriting:")

@router.message(AS.sm_text)
async def rx_sm_text(msg: Message, state: FSMContext):
    await state.update_data({"content": msg.text or msg.caption or ""})
    data  = await state.get_data()
    mtype = data.get("mtype", "text")

    if mtype == 'quote':
        await state.set_state(AS.sm_extra)
        await msg.answer("👤 Iqtibos muallifi kiriting (masalan: Alisher Navoiy):")
    elif mtype == 'link':
        await state.set_state(AS.sm_extra)
        await msg.answer("🔗 Havola URL kiriting (masalan: https://t.me/mychanel):")
    elif mtype == 'text_link':
        await state.set_state(AS.sm_extra)
        await msg.answer(
            "🔤 Havola va nomini kiriting quyidagi formatda:\n"
            "<code>https://t.me/mychanel|Kanalimiz</code>\n\n"
            "Yani: <code>URL|Ko'rsatiladigan nom</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await _save_start_msg(msg, state)

@router.message(AS.sm_extra)
async def rx_sm_extra(msg: Message, state: FSMContext):
    await state.update_data({"extra": msg.text or ""})
    await _save_start_msg(msg, state)

async def _save_start_msg(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM start_msg")
        await db.execute(
            "INSERT INTO start_msg (id,msg_type,content,photo_id,extra) VALUES (1,?,?,?,?)",
            (data.get("mtype", "text"), data.get("content", ""),
             data.get("photo_id"), data.get("extra"))
        )
        await db.commit()
    mtype_names = {
        'text': 'Matn', 'photo': 'Rasm + matn',
        'quote': 'Iqtibos', 'link': 'Link', 'text_link': 'Matnli havola'
    }
    await msg.answer(
        f"✅ <b>Start xabar saqlandi!</b>\n\nTur: {mtype_names.get(data.get('mtype','text'), '?')}",
        parse_mode=ParseMode.HTML
    )

# ═══════════════════════ MAIN ═══════════════════════
async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    log.info("Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
