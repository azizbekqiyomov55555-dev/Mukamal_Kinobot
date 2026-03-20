"""
╔═══════════════════════════════════════════════════════╗
║  MUKAMMAL KINO BOT  –  Barcha xatolar tuzatilgan      ║
║  Token : 8655776547:AAEKHHQfCjvdwIgn_y4PH7de-b3g2Jd5iYs ║
║  Admin : 8537782289                                   ║
╚═══════════════════════════════════════════════════════╝
"""
import logging, sqlite3, asyncio, io
from datetime import datetime
import pytz
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode

# ─── SOZLAMALAR ───────────────────────────────────────
BOT_TOKEN = "8655776547:AAEKHHQfCjvdwIgn_y4PH7de-b3g2Jd5iYs"
ADMIN_IDS = [8537782289]
TZ        = pytz.timezone("Asia/Tashkent")
DB_FILE   = "kino.db"
# ──────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════
def db_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            tg_id INTEGER PRIMARY KEY,
            username TEXT, full_name TEXT,
            balance REAL DEFAULT 0,
            joined_at TEXT
        );
        CREATE TABLE IF NOT EXISTS parts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, part_no INTEGER,
            file_id TEXT, info TEXT,
            price REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS txs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER, amount REAL,
            kind TEXT, code TEXT, part_no INTEGER,
            status TEXT DEFAULT 'pending',
            file_id TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings(
            k TEXT PRIMARY KEY, v TEXT
        );
        CREATE TABLE IF NOT EXISTS channels(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cid TEXT, link TEXT, name TEXT
        );
        CREATE TABLE IF NOT EXISTS links(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, url TEXT
        );
        """)

def now():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def cfg_get(k, d=""):
    with db_conn() as c:
        r = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    return r["v"] if r else d

def cfg_set(k, v):
    with db_conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)", (k, v))

def reg_user(uid, un, fn):
    with db_conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO users(tg_id,username,full_name,joined_at) VALUES(?,?,?,?)",
            (uid, un, fn, now()))

def get_user(uid):
    with db_conn() as c:
        return c.execute("SELECT * FROM users WHERE tg_id=?", (uid,)).fetchone()

def get_all_users():
    with db_conn() as c:
        return c.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()

def get_balance(uid):
    with db_conn() as c:
        r = c.execute("SELECT balance FROM users WHERE tg_id=?", (uid,)).fetchone()
    return r["balance"] if r else 0.0

def add_balance(uid, amt):
    with db_conn() as c:
        c.execute("UPDATE users SET balance=balance+? WHERE tg_id=?", (amt, uid))

def sub_balance(uid, amt):
    with db_conn() as c:
        c.execute("UPDATE users SET balance=balance-? WHERE tg_id=?", (amt, uid))

def get_parts(code):
    with db_conn() as c:
        return c.execute(
            "SELECT * FROM parts WHERE code=? ORDER BY part_no", (code,)).fetchall()

def get_part(code, pno):
    with db_conn() as c:
        return c.execute(
            "SELECT * FROM parts WHERE code=? AND part_no=?", (code, pno)).fetchone()

def get_channels():
    with db_conn() as c:
        return c.execute("SELECT * FROM channels").fetchall()

def is_admin(uid):
    return uid in ADMIN_IDS

# ══════════════════════════════════════════════════════
#  KLAVIATURALAR
# ══════════════════════════════════════════════════════
def kb_main():
    return ReplyKeyboardMarkup(
        [["💰 Hisobim", "🆘 Yordam"]], resize_keyboard=True)

def kb_admin():
    return ReplyKeyboardMarkup([
        ["🎬 Kino qo'shish",   "➕ Davomini qo'shish"],
        ["📢 Kanal boshqaruv", "🔗 Link qo'shish"],
        ["📨 Barchaga xabar",  "📩 ID'ga xabar"],
        ["💵 ID'ga pul",       "💰 Barchaga pul"],
        ["📊 Statistika",      "⚙️ Start xabari"],
        ["💳 Karta o'rnat",    "🏠 Asosiy menyu"],
    ], resize_keyboard=True)

def kb_cancel():
    return ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)

# ══════════════════════════════════════════════════════
#  CONVERSATION STATES
# ══════════════════════════════════════════════════════
(
    # User flows
    U_TOPUP_AMT, U_TOPUP_CHECK,
    U_MOVIE_CHECK,
    U_SUPPORT, U_ADM_REPLY,
    # Admin: add movie
    A_VID, A_MORE_VID, A_CODE, A_INFO, A_PRICE,
    # Admin: continuation
    C_CODE, C_VID, C_INFO, C_PRICE,
    # Admin: settings
    ST_PHOTO, ST_TEXT,
    CH_ACTION, CH_DEL_ID, CH_ID, CH_LINK, CH_NAME,
    LN_TITLE, LN_URL,
    BC_MSG, SND_ID, SND_MSG,
    BAL_ID, BAL_AMT, ALLBAL_AMT,
    CARD_NUM,
    # Movie card pay conversation
    MV_CARD_CHECK,
) = range(30)

# ══════════════════════════════════════════════════════
#  SUBSCRIPTION CHECK
# ══════════════════════════════════════════════════════
async def check_sub(bot, uid):
    """Returns list of channels user is NOT subscribed to."""
    not_in = []
    for ch in get_channels():
        try:
            m = await bot.get_chat_member(ch["cid"], uid)
            if m.status in ("left", "kicked", "banned"):
                not_in.append(ch)
        except Exception as e:
            log.warning(f"check_sub [{ch['cid']}]: {e}")
    return not_in

def sub_buttons(not_joined):
    btns = [[InlineKeyboardButton(f"📢 {c['name']}", url=c["link"])] for c in not_joined]
    btns.append([InlineKeyboardButton("✅ Tekshirish", callback_data="sub_check")])
    return InlineKeyboardMarkup(btns)

# ══════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    reg_user(u.id, u.username, u.full_name)

    nj = await check_sub(ctx.bot, u.id)
    if nj:
        await update.message.reply_text(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=sub_buttons(nj))
        return

    await send_start_msg(ctx.bot, u.id)

async def send_start_msg(bot, uid):
    photo = cfg_get("start_photo")
    text  = cfg_get("start_text", "🎬 Kino botga xush kelibsiz!\n\nKino kodini yuboring.")
    kb    = kb_main()
    try:
        if photo:
            await bot.send_photo(chat_id=uid, photo=photo,
                                  caption=text, reply_markup=kb)
        else:
            await bot.send_message(chat_id=uid, text=text, reply_markup=kb)
    except Exception as e:
        log.error(f"send_start_msg error: {e}")
        try:
            await bot.send_message(chat_id=uid, text=text, reply_markup=kb)
        except:
            pass

async def cb_sub_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    nj = await check_sub(ctx.bot, q.from_user.id)
    if nj:
        try:
            await q.edit_message_text(
                "⚠️ Hali obuna bo'lmagan kanallar bor:",
                reply_markup=sub_buttons(nj))
        except:
            pass
    else:
        try:
            await q.message.delete()
        except:
            pass
        await send_start_msg(ctx.bot, q.from_user.id)

# ══════════════════════════════════════════════════════
#  HISOBIM
# ══════════════════════════════════════════════════════
async def cmd_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u   = update.effective_user
    bal = get_balance(u.id)
    with db_conn() as c:
        txs = c.execute(
            "SELECT amount,kind,code,part_no,created_at FROM txs "
            "WHERE tg_id=? AND status='approved' ORDER BY created_at DESC LIMIT 7",
            (u.id,)).fetchall()

    hist = ""
    for t in txs:
        ico = "➕" if t["kind"] == "topup" else "🎬"
        ex  = f" ({t['code']}/{t['part_no']}-qism)" if t["code"] else ""
        hist += f"\n  {ico} {t['amount']:,.0f} so'm{ex}  —  {t['created_at']}"

    txt = (
        f"👤 <b>Hisobim</b>\n\n"
        f"🆔 ID: <code>{u.id}</code>\n"
        f"👤 Ism: {u.full_name}\n"
        f"💰 Balans: <b>{bal:,.0f} so'm</b>"
    )
    if hist:
        txt += f"\n\n📋 <b>So'nggi amallar:</b>{hist}"

    kb = [[InlineKeyboardButton("💳 Hisobni to'ldirish", callback_data="topup_open")]]
    await update.message.reply_text(
        txt, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb))

# ══════════════════════════════════════════════════════
#  HISOBNI TO'LDIRISH  (ConversationHandler)
# ══════════════════════════════════════════════════════
async def topup_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        "💵 Qancha pul kiritmoqchisiz? (so'mda, masalan: 50000)",
        reply_markup=kb_cancel())
    return U_TOPUP_AMT

async def topup_get_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_main())
        return ConversationHandler.END

    t = update.message.text.strip().replace(" ", "").replace(",", "")
    if not t.isdigit():
        await update.message.reply_text("❌ Faqat raqam kiriting!")
        return U_TOPUP_AMT

    ctx.user_data["topup_amt"] = int(t)
    card = cfg_get("card", "❗ Karta raqami hali kiritilmagan")
    await update.message.reply_text(
        f"💳 Karta raqami: <b>{card}</b>\n"
        f"💰 Miqdor: <b>{int(t):,.0f} so'm</b>\n\n"
        f"Ushbu kartaga pul o'tkazing va <b>chek rasmini yuboring</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_cancel())
    return U_TOPUP_CHECK

async def topup_get_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_main())
        return ConversationHandler.END

    if update.message.photo:
        fid = update.message.photo[-1].file_id
    elif update.message.document:
        fid = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Chek rasmini (foto) yuboring!")
        return U_TOPUP_CHECK

    user   = update.effective_user
    amount = ctx.user_data.get("topup_amt", 0)

    with db_conn() as c:
        c.execute(
            "INSERT INTO txs(tg_id,amount,kind,status,file_id,created_at) VALUES(?,?,?,?,?,?)",
            (user.id, amount, "topup", "pending", fid, now()))
        tx_id = c.lastrowid

    for aid in ADMIN_IDS:
        try:
            kb = [[
                InlineKeyboardButton("✅ Tasdiqlash",
                    callback_data=f"atop|{tx_id}|{user.id}|{amount}"),
                InlineKeyboardButton("❌ Rad etish",
                    callback_data=f"rtop|{tx_id}|{user.id}"),
            ]]
            cap = (
                f"💰 <b>HISOBNI TO'LDIRISH SO'ROVI</b>\n\n"
                f"👤 {user.full_name}\n"
                f"🆔 <code>{user.id}</code>\n"
                f"📱 @{user.username or '–'}\n"
                f"💵 <b>{amount:,.0f} so'm</b>\n"
                f"🕐 {now()}"
            )
            await ctx.bot.send_photo(
                chat_id=aid, photo=fid, caption=cap,
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode=ParseMode.HTML)
        except Exception as e:
            log.error(f"topup notify admin: {e}")

    await update.message.reply_text(
        "✅ Chekingiz adminga yuborildi.\nTez orada hisobingiz to'ldiriladi!",
        reply_markup=kb_main())
    return ConversationHandler.END

async def cb_approve_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    _, tx_id, uid, amount = q.data.split("|")
    uid    = int(uid)
    amount = float(amount)
    add_balance(uid, amount)
    with db_conn() as c:
        c.execute("UPDATE txs SET status='approved' WHERE id=?", (tx_id,))
    try:
        await ctx.bot.send_message(
            uid,
            f"✅ Hisobingizga <b>{amount:,.0f} so'm</b> qo'shildi!\n"
            f"💰 Joriy balans: <b>{get_balance(uid):,.0f} so'm</b>",
            parse_mode=ParseMode.HTML)
    except:
        pass
    old = q.message.caption or ""
    try:
        await q.edit_message_caption(
            caption=old + "\n\n✅ <b>TASDIQLANDI</b>",
            parse_mode=ParseMode.HTML)
    except:
        pass

async def cb_reject_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    _, tx_id, uid = q.data.split("|")
    with db_conn() as c:
        c.execute("UPDATE txs SET status='rejected' WHERE id=?", (tx_id,))
    try:
        await ctx.bot.send_message(int(uid), "❌ To'lovingiz rad etildi.")
    except:
        pass
    old = q.message.caption or ""
    try:
        await q.edit_message_caption(
            caption=old + "\n\n❌ <b>RAD ETILDI</b>",
            parse_mode=ParseMode.HTML)
    except:
        pass

# ══════════════════════════════════════════════════════
#  KINO KODI → QISMLAR
# ══════════════════════════════════════════════════════
async def show_parts(update: Update, ctx: ContextTypes.DEFAULT_TYPE, code: str):
    parts = get_parts(code)
    if not parts:
        await update.message.reply_text(
            "❌ Bunday kod topilmadi. To'g'ri kod kiriting.")
        return

    btns = []
    for p in parts:
        price_str = "🆓 Bepul" if p["price"] == 0 else f"{p['price']:,.0f} so'm"
        lbl = f"📽 {p['part_no']}-qism  —  {price_str}"
        btns.append([InlineKeyboardButton(lbl, callback_data=f"qism|{code}|{p['part_no']}")])

    await update.message.reply_text(
        f"🎬 <b>Kod: {code}</b>\n\nQayta ko'rmoqchi bo'lgan qismni tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(btns))

async def cb_qism(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, code, pno = q.data.split("|")
    pno  = int(pno)
    part = get_part(code, pno)
    if not part:
        await q.message.reply_text("❌ Qism topilmadi.")
        return

    price = part["price"]
    info  = part["info"] or ""
    uid   = q.from_user.id

    if price == 0:
        # Bepul — darhol yuborish
        cap = f"📽 <b>{pno}-qism</b>"
        if info:
            cap += f"\n\n{info}"
        try:
            await q.message.delete()
        except:
            pass
        await ctx.bot.send_video(
            chat_id=uid, video=part["file_id"],
            caption=cap, parse_mode=ParseMode.HTML)
        return

    # Pullik
    bal = get_balance(uid)
    txt = (
        f"🎬 <b>Kod: {code}  —  {pno}-qism</b>\n"
        f"{info}\n\n"
        f"💰 Narx: <b>{price:,.0f} so'm</b>\n"
        f"💳 Sizning balansingiz: <b>{bal:,.0f} so'm</b>"
    )
    kb = []
    if bal >= price:
        kb.append([InlineKeyboardButton(
            f"✅ Hisobdan to'lash  ({price:,.0f} so'm)",
            callback_data=f"pay_bal|{code}|{pno}")])
    else:
        kb.append([InlineKeyboardButton(
            "💳 Hisobni to'ldirish",
            callback_data="topup_open")])
    kb.append([InlineKeyboardButton(
        "💴 Karta orqali to'lash",
        callback_data=f"pay_card|{code}|{pno}")])

    try:
        await q.edit_message_text(
            txt, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kb))
    except:
        await q.message.reply_text(
            txt, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(kb))

# ──── Hisobdan to'lash ────
async def cb_pay_bal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, code, pno = q.data.split("|")
    pno  = int(pno)
    part = get_part(code, pno)
    if not part:
        await q.answer("❌ Qism topilmadi!", show_alert=True)
        return

    price = part["price"]
    uid   = q.from_user.id

    if get_balance(uid) < price:
        await q.answer("❌ Balansingiz yetarli emas!", show_alert=True)
        return

    sub_balance(uid, price)
    with db_conn() as c:
        c.execute(
            "INSERT INTO txs(tg_id,amount,kind,code,part_no,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (uid, price, "purchase", code, pno, "approved", now()))

    cap = f"📽 <b>{pno}-qism</b>"
    if part["info"]:
        cap += f"\n\n{part['info']}"
    try:
        await q.message.delete()
    except:
        pass
    await ctx.bot.send_message(
        uid,
        f"✅ Hisobingizdan <b>{price:,.0f} so'm</b> yechildi!\n"
        f"💰 Qolgan balans: <b>{get_balance(uid):,.0f} so'm</b>",
        parse_mode=ParseMode.HTML)
    await ctx.bot.send_video(
        chat_id=uid, video=part["file_id"],
        caption=cap, parse_mode=ParseMode.HTML)

# ──── Karta orqali to'lash (ConversationHandler) ────
async def cb_pay_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, code, pno = q.data.split("|")
    pno  = int(pno)
    part = get_part(code, pno)
    if not part:
        await q.message.reply_text("❌ Qism topilmadi.")
        return

    ctx.user_data["mv_code"]  = code
    ctx.user_data["mv_pno"]   = pno
    ctx.user_data["mv_price"] = part["price"]

    card = cfg_get("card", "❗ Karta raqami kiritilmagan")
    msg_text = (
        f"💳 Karta raqami: <b>{card}</b>\n"
        f"💰 Miqdor: <b>{part['price']:,.0f} so'm</b>\n\n"
        f"Pul o'tkazing va <b>chek rasmini yuboring</b>."
    )
    try:
        await q.message.reply_text(
            msg_text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb_cancel())
    except Exception as e:
        log.error(f"cb_pay_card: {e}")
    # Return state for ConversationHandler — but this is callback, 
    # so we store state in user_data and handle in mv_card_check_conv
    return MV_CARD_CHECK

async def mv_card_check_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Karta orqali to'lov cheki — ConversationHandler ichida."""
    if update.message.text == "❌ Bekor qilish":
        ctx.user_data.pop("mv_code", None)
        ctx.user_data.pop("mv_pno", None)
        ctx.user_data.pop("mv_price", None)
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_main())
        return ConversationHandler.END

    if update.message.photo:
        fid = update.message.photo[-1].file_id
    elif update.message.document:
        fid = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Chek rasmini (foto) yuboring!")
        return MV_CARD_CHECK

    user  = update.effective_user
    code  = ctx.user_data.get("mv_code")
    pno   = ctx.user_data.get("mv_pno")
    price = ctx.user_data.get("mv_price", 0)

    with db_conn() as c:
        c.execute(
            "INSERT INTO txs(tg_id,amount,kind,code,part_no,status,file_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (user.id, price, "purchase", code, pno, "pending", fid, now()))
        tx_id = c.lastrowid

    for aid in ADMIN_IDS:
        try:
            kb = [[
                InlineKeyboardButton("✅ Tasdiqlash",
                    callback_data=f"amov|{tx_id}|{user.id}|{code}|{pno}"),
                InlineKeyboardButton("❌ Rad etish",
                    callback_data=f"rmov|{tx_id}|{user.id}"),
            ]]
            cap = (
                f"🎬 <b>KINO TO'LOVI</b>\n\n"
                f"👤 {user.full_name}\n"
                f"🆔 <code>{user.id}</code>\n"
                f"📱 @{user.username or '–'}\n"
                f"🎬 Kod: <b>{code}</b>  |  <b>{pno}-qism</b>\n"
                f"💵 <b>{price:,.0f} so'm</b>\n"
                f"🕐 {now()}"
            )
            await ctx.bot.send_photo(
                chat_id=aid, photo=fid, caption=cap,
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode=ParseMode.HTML)
        except Exception as e:
            log.error(f"movie check notify: {e}")

    await update.message.reply_text(
        "✅ Chekingiz adminga yuborildi!\nAdmin tasdiqlashini kuting.",
        reply_markup=kb_main())

    ctx.user_data.pop("mv_code", None)
    ctx.user_data.pop("mv_pno", None)
    ctx.user_data.pop("mv_price", None)
    return ConversationHandler.END

async def cb_approve_movie(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    parts = q.data.split("|")
    tx_id = parts[1]; uid = int(parts[2]); code = parts[3]; pno = int(parts[4])
    with db_conn() as c:
        c.execute("UPDATE txs SET status='approved' WHERE id=?", (tx_id,))
    part = get_part(code, pno)
    if part:
        try:
            cap = f"📽 <b>{pno}-qism</b>"
            if part["info"]:
                cap += f"\n\n{part['info']}"
            await ctx.bot.send_message(uid, "✅ To'lovingiz tasdiqlandi! Kino yuborilmoqda...")
            await ctx.bot.send_video(
                chat_id=uid, video=part["file_id"],
                caption=cap, parse_mode=ParseMode.HTML)
        except Exception as e:
            log.error(f"approve movie send: {e}")
    old = q.message.caption or ""
    try:
        await q.edit_message_caption(
            caption=old + "\n\n✅ <b>TASDIQLANDI</b>",
            parse_mode=ParseMode.HTML)
    except:
        pass

async def cb_reject_movie(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    _, tx_id, uid = q.data.split("|")
    with db_conn() as c:
        c.execute("UPDATE txs SET status='rejected' WHERE id=?", (tx_id,))
    try:
        await ctx.bot.send_message(int(uid), "❌ To'lovingiz rad etildi.")
    except:
        pass
    old = q.message.caption or ""
    try:
        await q.edit_message_caption(
            caption=old + "\n\n❌ <b>RAD ETILDI</b>",
            parse_mode=ParseMode.HTML)
    except:
        pass

# ══════════════════════════════════════════════════════
#  YORDAM
# ══════════════════════════════════════════════════════
async def support_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 Adminga xabar yuboring.\n"
        "(Matn, rasm, ovozli xabar — istalgan narsa):",
        reply_markup=kb_cancel())
    return U_SUPPORT

async def support_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_main())
        return ConversationHandler.END

    user = update.effective_user
    msg  = update.message
    for aid in ADMIN_IDS:
        try:
            hdr = (
                f"📩 <b>Foydalanuvchi murojaat</b>\n"
                f"👤 {user.full_name}  |  🆔 <code>{user.id}</code>  |  "
                f"@{user.username or '–'}"
            )
            await ctx.bot.send_message(aid, hdr, parse_mode=ParseMode.HTML)
            if msg.text:
                await ctx.bot.send_message(aid, msg.text)
            elif msg.photo:
                await ctx.bot.send_photo(aid, msg.photo[-1].file_id,
                                          caption=msg.caption or "")
            elif msg.voice:
                await ctx.bot.send_voice(aid, msg.voice.file_id)
            elif msg.video:
                await ctx.bot.send_video(aid, msg.video.file_id,
                                          caption=msg.caption or "")
            elif msg.document:
                await ctx.bot.send_document(aid, msg.document.file_id,
                                             caption=msg.caption or "")
            else:
                await ctx.bot.send_message(aid, "[Noma'lum xabar turi]")
            await ctx.bot.send_message(
                aid, "Javob berish uchun:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✍️ Javob yozish",
                                         callback_data=f"reply|{user.id}")
                ]]))
        except Exception as e:
            log.error(f"support notify: {e}")

    await update.message.reply_text("✅ Xabaringiz yuborildi!", reply_markup=kb_main())
    return ConversationHandler.END

async def cb_reply_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    ctx.user_data["reply_to"] = int(q.data.split("|")[1])
    await q.message.reply_text("✍️ Javob xabaringizni yuboring:", reply_markup=kb_cancel())
    return U_ADM_REPLY

async def adm_reply_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    tid = ctx.user_data.get("reply_to")
    msg = update.message
    try:
        if msg.text:
            await ctx.bot.send_message(
                tid, f"📨 <b>Admin javobi:</b>\n\n{msg.text}",
                parse_mode=ParseMode.HTML)
        elif msg.photo:
            await ctx.bot.send_photo(
                tid, msg.photo[-1].file_id,
                caption=f"📨 Admin javobi:\n{msg.caption or ''}")
        elif msg.voice:
            await ctx.bot.send_voice(tid, msg.voice.file_id)
        elif msg.video:
            await ctx.bot.send_video(
                tid, msg.video.file_id,
                caption=f"📨 Admin javobi:\n{msg.caption or ''}")
        await update.message.reply_text("✅ Javob yuborildi!", reply_markup=kb_admin())
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}", reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: KINO QO'SHISH (cheksiz qismlar)
# ══════════════════════════════════════════════════════
async def adm_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ctx.user_data.clear()
    ctx.user_data["vids"] = []
    await update.message.reply_text(
        "🎬 <b>Yangi kino qo'shish</b>\n\n1-qism videosini yuboring:",
        parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return A_VID

async def a_vid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    if not update.message.video:
        await update.message.reply_text("❌ Video yuboring!")
        return A_VID
    ctx.user_data["vids"].append(update.message.video.file_id)
    n = len(ctx.user_data["vids"])
    await update.message.reply_text(
        f"✅ {n}-qism qabul qilindi!\nYana qism qo'shasizmi yoki tugatamizmi?",
        reply_markup=ReplyKeyboardMarkup(
            [[f"➕ {n+1}-qism qo'shish", "⏭ Tugatish"]], resize_keyboard=True))
    return A_MORE_VID

async def a_more_vid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    if update.message.video:
        ctx.user_data["vids"].append(update.message.video.file_id)
        n = len(ctx.user_data["vids"])
        await update.message.reply_text(
            f"✅ {n}-qism qabul qilindi!\nYana qo'shasizmi?",
            reply_markup=ReplyKeyboardMarkup(
                [[f"➕ {n+1}-qism qo'shish", "⏭ Tugatish"]], resize_keyboard=True))
        return A_MORE_VID
    if update.message.text and "Tugatish" in update.message.text:
        ctx.user_data["infos"]  = []
        ctx.user_data["prices"] = []
        await update.message.reply_text(
            f"✅ Jami {len(ctx.user_data['vids'])} ta video!\n\n"
            f"🔑 Kino uchun KOD kiriting (masalan: 001, BATMAN):",
            reply_markup=kb_cancel())
        return A_CODE
    await update.message.reply_text("❌ Video yuboring yoki «Tugatish»ni bosing!")
    return A_MORE_VID

async def a_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    code = update.message.text.strip()
    if get_parts(code):
        await update.message.reply_text("❌ Bu kod allaqachon mavjud! Boshqa kod kiriting:")
        return A_CODE
    ctx.user_data["code"] = code
    await update.message.reply_text("📝 1-qism uchun kino haqida ma'lumot kiriting:")
    return A_INFO

async def a_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    ctx.user_data["infos"].append(update.message.text)
    idx   = len(ctx.user_data["infos"])
    total = len(ctx.user_data["vids"])
    if idx < total:
        await update.message.reply_text(f"📝 {idx+1}-qism uchun ma'lumot kiriting:")
        return A_INFO
    await update.message.reply_text("💰 1-qism uchun narx kiriting (bepul = 0):")
    return A_PRICE

async def a_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    t = update.message.text.strip().replace(" ", "").replace(",", "")
    if not t.isdigit():
        await update.message.reply_text("❌ Faqat raqam kiriting!")
        return A_PRICE
    ctx.user_data["prices"].append(int(t))
    idx   = len(ctx.user_data["prices"])
    total = len(ctx.user_data["vids"])
    if idx < total:
        await update.message.reply_text(f"💰 {idx+1}-qism uchun narx (0=bepul):")
        return A_PRICE
    # SAQLASH
    code = ctx.user_data["code"]
    with db_conn() as c:
        for i, (vid, inf, pr) in enumerate(
                zip(ctx.user_data["vids"],
                    ctx.user_data["infos"],
                    ctx.user_data["prices"]), 1):
            c.execute(
                "INSERT INTO parts(code,part_no,file_id,info,price) VALUES(?,?,?,?,?)",
                (code, i, vid, inf, pr))
    await update.message.reply_text(
        f"✅ Kino saqlandi!\n🔑 Kod: <code>{code}</code>\n"
        f"📽 Qismlar: {len(ctx.user_data['vids'])}",
        parse_mode=ParseMode.HTML, reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: KINO DAVOMINI QO'SHISH
# ══════════════════════════════════════════════════════
async def cont_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "➕ <b>Kino davomini qo'shish</b>\n\nKino kodini kiriting:",
        parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return C_CODE

async def cont_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    code  = update.message.text.strip()
    parts = get_parts(code)
    if not parts:
        await update.message.reply_text("❌ Bu kod topilmadi!")
        return C_CODE
    nxt = max(p["part_no"] for p in parts) + 1
    ctx.user_data["c_code"] = code
    ctx.user_data["c_pno"]  = nxt
    await update.message.reply_text(
        f"✅ Topildi! Mavjud qismlar: {len(parts)}\n\n{nxt}-qism videosini yuboring:",
        reply_markup=kb_cancel())
    return C_VID

async def cont_vid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    if not update.message.video:
        await update.message.reply_text("❌ Video yuboring!")
        return C_VID
    ctx.user_data["c_vid"] = update.message.video.file_id
    await update.message.reply_text(
        f"📝 {ctx.user_data['c_pno']}-qism uchun ma'lumot kiriting:",
        reply_markup=kb_cancel())
    return C_INFO

async def cont_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    ctx.user_data["c_info"] = update.message.text
    await update.message.reply_text(
        f"💰 {ctx.user_data['c_pno']}-qism uchun narx kiriting (0=bepul):",
        reply_markup=kb_cancel())
    return C_PRICE

async def cont_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    t = update.message.text.strip().replace(" ", "").replace(",", "")
    if not t.isdigit():
        await update.message.reply_text("❌ Raqam kiriting!")
        return C_PRICE
    code = ctx.user_data["c_code"]
    pno  = ctx.user_data["c_pno"]
    with db_conn() as c:
        c.execute(
            "INSERT INTO parts(code,part_no,file_id,info,price) VALUES(?,?,?,?,?)",
            (code, pno, ctx.user_data["c_vid"], ctx.user_data["c_info"], int(t)))
    await update.message.reply_text(
        f"✅ {pno}-qism saqlandi!\n🔑 Kod: <code>{code}</code>",
        parse_mode=ParseMode.HTML, reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: KANAL BOSHQARUV (qo'shish + o'chirish + ro'yxat)
# ══════════════════════════════════════════════════════
async def ch_manage_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    chs = get_channels()
    if chs:
        lst = "\n".join(f"  [{c['id']}] {c['name']}  ({c['cid']})" for c in chs)
    else:
        lst = "\n  Hali kanal yo'q"

    await update.message.reply_text(
        f"📢 <b>Majburiy obuna kanallar:</b>\n{lst}\n\n"
        f"Nima qilmoqchisiz?",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup([
            ["➕ Kanal qo'shish", "🗑 Kanal o'chirish"],
            ["📋 Kanallar ro'yxati", "❌ Bekor qilish"]
        ], resize_keyboard=True))
    return CH_ACTION

async def ch_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END

    if t == "📋 Kanallar ro'yxati":
        chs = get_channels()
        if not chs:
            await update.message.reply_text("📢 Hali hech qanday kanal qo'shilmagan.", reply_markup=kb_admin())
        else:
            lst = "\n".join(f"  [{c['id']}] {c['name']}\n      ID: {c['cid']}\n      Link: {c['link']}" for c in chs)
            await update.message.reply_text(
                f"📢 <b>Majburiy kanallar ro'yxati:</b>\n\n{lst}",
                parse_mode=ParseMode.HTML, reply_markup=kb_admin())
        return ConversationHandler.END

    if t == "➕ Kanal qo'shish":
        await update.message.reply_text(
            "Kanal ID sini kiriting (@username yoki -100...):",
            reply_markup=kb_cancel())
        return CH_ID

    if t == "🗑 Kanal o'chirish":
        chs = get_channels()
        if not chs:
            await update.message.reply_text("O'chirish uchun kanal yo'q.", reply_markup=kb_admin())
            return ConversationHandler.END
        lst = "\n".join(f"  [{c['id']}] {c['name']}  ({c['cid']})" for c in chs)
        await update.message.reply_text(
            f"Mavjud kanallar:\n{lst}\n\nO'chirish uchun <b>raqamini</b> kiriting:",
            parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
        return CH_DEL_ID

    return CH_ACTION

async def ch_del_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    t = update.message.text.strip()
    if not t.isdigit():
        await update.message.reply_text("❌ Raqam kiriting!")
        return CH_DEL_ID
    with db_conn() as c:
        r = c.execute("SELECT name FROM channels WHERE id=?", (int(t),)).fetchone()
        if not r:
            await update.message.reply_text("❌ Bunday raqamli kanal topilmadi!")
            return CH_DEL_ID
        c.execute("DELETE FROM channels WHERE id=?", (int(t),))
    await update.message.reply_text(
        f"✅ «{r['name']}» kanali o'chirildi!", reply_markup=kb_admin())
    return ConversationHandler.END

async def ch_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    ctx.user_data["ch_id"] = update.message.text.strip()
    await update.message.reply_text(
        "🔗 Kanal havolasini kiriting (https://t.me/...):",
        reply_markup=kb_cancel())
    return CH_LINK

async def ch_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    ctx.user_data["ch_link"] = update.message.text.strip()
    await update.message.reply_text("📛 Kanal nomini kiriting:", reply_markup=kb_cancel())
    return CH_NAME

async def ch_name_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    with db_conn() as c:
        c.execute("INSERT INTO channels(cid,link,name) VALUES(?,?,?)",
                  (ctx.user_data["ch_id"], ctx.user_data["ch_link"],
                   update.message.text.strip()))
    await update.message.reply_text("✅ Kanal qo'shildi!", reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: LINK
# ══════════════════════════════════════════════════════
async def link_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    with db_conn() as c:
        lns = c.execute("SELECT * FROM links").fetchall()
    lst = "\n".join(f"  • {l['title']}: {l['url']}" for l in lns) if lns else "  Hali yo'q"
    await update.message.reply_text(
        f"🔗 <b>Linklar:</b>\n{lst}\n\nYangi link sarlavhasini kiriting:",
        parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return LN_TITLE

async def ln_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    ctx.user_data["ln_t"] = update.message.text.strip()
    await update.message.reply_text("🔗 URL ni kiriting:", reply_markup=kb_cancel())
    return LN_URL

async def ln_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    with db_conn() as c:
        c.execute("INSERT INTO links(title,url) VALUES(?,?)",
                  (ctx.user_data["ln_t"], update.message.text.strip()))
    await update.message.reply_text("✅ Link saqlandi!", reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: START XABARI — TO'LIQ TUZATILGAN
# ══════════════════════════════════════════════════════
async def start_msg_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cur_text  = cfg_get("start_text", "Hali o'rnatilmagan")
    cur_photo = cfg_get("start_photo", "")
    await update.message.reply_text(
        f"⚙️ <b>Start xabari sozlamalari</b>\n\n"
        f"📝 Joriy matn:\n<code>{cur_text}</code>\n\n"
        "🖼 Rasm: " + ("✅ Bor" if cur_photo else "❌ Yo'q") + "\n\n"
        "Yangi rasm yuboring yoki «⏭ O'tkazib yuborish» ni bosing:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [["⏭ O'tkazib yuborish"], ["❌ Bekor qilish"]], resize_keyboard=True))
    return ST_PHOTO

async def st_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END

    if update.message.photo:
        fid = update.message.photo[-1].file_id
        cfg_set("start_photo", fid)
        ctx.user_data["st_ph"] = fid
        await update.message.reply_text("✅ Rasm saqlandi!")
    elif update.message.text == "⏭ O'tkazib yuborish":
        ctx.user_data["st_ph"] = cfg_get("start_photo", "")
    else:
        await update.message.reply_text(
            "❌ Rasm yuboring yoki «⏭ O'tkazib yuborish» ni bosing!")
        return ST_PHOTO

    await update.message.reply_text(
        "📝 Endi start xabari matnini kiriting\n"
        "(qanday kiritsangiz HUDDI SHUNDAY saqlanadi):\n\n"
        "Bekor qilish uchun «❌ Bekor qilish» ni bosing:",
        reply_markup=kb_cancel())
    return ST_TEXT

async def st_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END

    new_text = update.message.text
    cfg_set("start_text",  new_text)
    if ctx.user_data.get("st_ph") is not None:
        cfg_set("start_photo", ctx.user_data["st_ph"])

    await update.message.reply_text(
        f"✅ Start xabari muvaffaqiyatli saqlandi!\n\n"
        f"📝 Yangi matn:\n{new_text}",
        reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: BARCHAGA XABAR
# ══════════════════════════════════════════════════════
async def bc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    n = len(get_all_users())
    await update.message.reply_text(
        f"📨 <b>Barchaga xabar</b>  ({n} ta foydalanuvchi)\n\n"
        f"Xabarni yuboring (qanday kiritsangiz shunday boradi):",
        parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return BC_MSG

async def bc_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    users = get_all_users()
    ok = err = 0
    sm = await update.message.reply_text(f"📤 Yuborilmoqda... 0/{len(users)}")
    for i, u in enumerate(users):
        try:
            msg = update.message
            if msg.text:
                await ctx.bot.send_message(u["tg_id"], msg.text)
            elif msg.photo:
                await ctx.bot.send_photo(u["tg_id"], msg.photo[-1].file_id,
                                          caption=msg.caption or "")
            elif msg.video:
                await ctx.bot.send_video(u["tg_id"], msg.video.file_id,
                                          caption=msg.caption or "")
            elif msg.voice:
                await ctx.bot.send_voice(u["tg_id"], msg.voice.file_id)
            elif msg.document:
                await ctx.bot.send_document(u["tg_id"], msg.document.file_id,
                                             caption=msg.caption or "")
            ok += 1
        except:
            err += 1
        if (i + 1) % 20 == 0:
            try:
                await sm.edit_text(f"📤 Yuborilmoqda... {i+1}/{len(users)}")
            except:
                pass
        await asyncio.sleep(0.05)
    await sm.edit_text(
        f"✅ Xabar yuborildi!\n✅ Muvaffaqiyatli: {ok}\n❌ Xato: {err}")
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: ID GA XABAR
# ══════════════════════════════════════════════════════
async def snd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "📩 Xabar yuboriladigan foydalanuvchi ID sini kiriting:",
        reply_markup=kb_cancel())
    return SND_ID

async def snd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    t = update.message.text.strip()
    if not t.lstrip("-").isdigit():
        await update.message.reply_text("❌ To'g'ri ID kiriting!")
        return SND_ID
    ctx.user_data["snd_id"] = int(t)
    await update.message.reply_text("💬 Xabarni yuboring:", reply_markup=kb_cancel())
    return SND_MSG

async def snd_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    tid = ctx.user_data.get("snd_id")
    msg = update.message
    try:
        if msg.text:
            await ctx.bot.send_message(tid, msg.text)
        elif msg.photo:
            await ctx.bot.send_photo(tid, msg.photo[-1].file_id, caption=msg.caption or "")
        elif msg.video:
            await ctx.bot.send_video(tid, msg.video.file_id, caption=msg.caption or "")
        elif msg.voice:
            await ctx.bot.send_voice(tid, msg.voice.file_id)
        await update.message.reply_text(f"✅ Xabar {tid} ga yuborildi!", reply_markup=kb_admin())
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}", reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: ID GA PUL
# ══════════════════════════════════════════════════════
async def bal_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "💵 Pul qo'shiladigan foydalanuvchi ID sini kiriting:",
        reply_markup=kb_cancel())
    return BAL_ID

async def bal_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    t = update.message.text.strip()
    if not t.lstrip("-").isdigit():
        await update.message.reply_text("❌ To'g'ri ID kiriting!")
        return BAL_ID
    uid = int(t)
    u = get_user(uid)
    if not u:
        await update.message.reply_text("❌ Bu ID li foydalanuvchi topilmadi!")
        return BAL_ID
    ctx.user_data["bal_uid"] = uid
    await update.message.reply_text(
        f"👤 {u['full_name']}\n💰 Joriy balans: {get_balance(uid):,.0f} so'm\n\n"
        f"Qo'shiladigan miqdorni kiriting:",
        reply_markup=kb_cancel())
    return BAL_AMT

async def bal_amt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    t = update.message.text.strip().replace(" ", "").replace(",", "")
    if not t.lstrip("-").isdigit():
        await update.message.reply_text("❌ Faqat raqam kiriting!")
        return BAL_AMT
    uid = ctx.user_data["bal_uid"]
    amt = int(t)
    add_balance(uid, amt)
    with db_conn() as c:
        c.execute(
            "INSERT INTO txs(tg_id,amount,kind,status,created_at) VALUES(?,?,?,?,?)",
            (uid, amt, "topup", "approved", now()))
    try:
        await ctx.bot.send_message(
            uid,
            f"🎁 Admin tomonidan hisobingizga <b>{amt:,.0f} so'm</b> qo'shildi!\n"
            f"💰 Joriy balans: <b>{get_balance(uid):,.0f} so'm</b>",
            parse_mode=ParseMode.HTML)
    except:
        pass
    await update.message.reply_text(
        f"✅ {uid} ga {amt:,.0f} so'm qo'shildi!\nYangi balans: {get_balance(uid):,.0f} so'm",
        reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: BARCHAGA PUL
# ══════════════════════════════════════════════════════
async def allbal_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    n = len(get_all_users())
    await update.message.reply_text(
        f"💰 Barchaga pul qo'shish ({n} ta foydalanuvchi)\n\nMiqdorni kiriting:",
        reply_markup=kb_cancel())
    return ALLBAL_AMT

async def allbal_amt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    t = update.message.text.strip().replace(" ", "").replace(",", "")
    if not t.isdigit():
        await update.message.reply_text("❌ Faqat raqam kiriting!")
        return ALLBAL_AMT
    amt   = int(t)
    users = get_all_users()
    for u in users:
        add_balance(u["tg_id"], amt)
        with db_conn() as c:
            c.execute(
                "INSERT INTO txs(tg_id,amount,kind,status,created_at) VALUES(?,?,?,?,?)",
                (u["tg_id"], amt, "topup", "approved", now()))
    await update.message.reply_text(
        f"✅ {len(users)} ta foydalanuvchiga {amt:,.0f} so'mdan qo'shildi!",
        reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: KARTA O'RNAT
# ══════════════════════════════════════════════════════
async def card_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cur = cfg_get("card", "Hali o'rnatilmagan")
    await update.message.reply_text(
        f"💳 Joriy karta: <b>{cur}</b>\n\nYangi karta raqamini kiriting:",
        parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return CARD_NUM

async def card_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=kb_admin())
        return ConversationHandler.END
    card = update.message.text.strip().replace(" ", "")
    cfg_set("card", card)
    await update.message.reply_text(
        f"✅ Karta saqlandi!\n💳 <b>{card}</b>",
        parse_mode=ParseMode.HTML, reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════
#  ADMIN: STATISTIKA
# ══════════════════════════════════════════════════════
async def adm_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    with db_conn() as c:
        total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = c.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?",
            (datetime.now(TZ).strftime("%Y-%m-%d") + "%",)).fetchone()[0]
        week  = c.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at >= datetime('now','-7 days')").fetchone()[0]
        t_top = c.execute(
            "SELECT COALESCE(SUM(amount),0) FROM txs "
            "WHERE kind='topup' AND status='approved'").fetchone()[0]
        t_sal = c.execute(
            "SELECT COALESCE(SUM(amount),0) FROM txs "
            "WHERE kind='purchase' AND status='approved'").fetchone()[0]
        movies = c.execute("SELECT COUNT(DISTINCT code) FROM parts").fetchone()[0]
        rows  = c.execute(
            "SELECT u.tg_id, u.full_name, u.username, u.balance, u.joined_at, "
            "COALESCE(SUM(CASE WHEN t.kind='topup' AND t.status='approved' "
            "THEN t.amount ELSE 0 END),0) AS paid "
            "FROM users u LEFT JOIN txs t ON u.tg_id=t.tg_id "
            "GROUP BY u.tg_id ORDER BY u.joined_at DESC LIMIT 30").fetchall()

    u_txt = ""
    for u in rows[:15]:
        u_txt += f"\n👤 {u['full_name']}  🆔<code>{u['tg_id']}</code>  💰{u['balance']:,.0f} so'm"

    await update.message.reply_text(
        f"📊 <b>Statistika</b>  |  🕐 {now()}\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total}</b>\n"
        f"📅 Bugun qo'shildi: <b>{today}</b>\n"
        f"📆 Haftalik: <b>{week}</b>\n"
        f"🎬 Kinolar: <b>{movies}</b>\n\n"
        f"💰 Jami kiritilgan: <b>{t_top:,.0f} so'm</b>\n"
        f"🛒 Jami sotuvlar: <b>{t_sal:,.0f} so'm</b>\n\n"
        f"<b>So'nggi foydalanuvchilar:</b>{u_txt}",
        parse_mode=ParseMode.HTML, reply_markup=kb_admin())

# ══════════════════════════════════════════════════════
#  /admin
# ══════════════════════════════════════════════════════
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    await update.message.reply_text(
        "👨‍💼 <b>Admin paneli</b>",
        parse_mode=ParseMode.HTML, reply_markup=kb_admin())

# ══════════════════════════════════════════════════════
#  UNIVERSAL HANDLERS
# ══════════════════════════════════════════════════════
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t   = update.message.text.strip()
    uid = update.effective_user.id

    # Admin tugmalari
    if is_admin(uid):
        if t == "📊 Statistika":   return await adm_stats(update, ctx)
        if t == "🏠 Asosiy menyu":
            await update.message.reply_text("Asosiy menyu:", reply_markup=kb_main())
            return

    # Asosiy foydalanuvchi tugmalari
    if t == "💰 Hisobim":    return await cmd_account(update, ctx)
    if t == "🆘 Yordam":     return await support_start(update, ctx)

    # Obuna tekshir
    nj = await check_sub(ctx.bot, uid)
    if nj:
        await update.message.reply_text(
            "⚠️ Avval kanallarga obuna bo'ling:",
            reply_markup=sub_buttons(nj))
        return

    # Kino kodi
    await show_parts(update, ctx, t)

# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════
def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    def cv(entry, states, **kw):
        return ConversationHandler(
            entry_points=entry, states=states,
            fallbacks=[
                MessageHandler(filters.Regex("^❌ Bekor qilish$"), 
                               lambda u, c: (
                                   asyncio.ensure_future(
                                       u.message.reply_text("Bekor qilindi.", 
                                                            reply_markup=kb_admin() if is_admin(u.effective_user.id) else kb_main())
                                   ) or ConversationHandler.END
                               ))
            ],
            per_message=False, **kw)

    # ─── Hisobni to'ldirish ───
    app.add_handler(cv(
        [CallbackQueryHandler(topup_open, pattern="^topup_open$")],
        {U_TOPUP_AMT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, topup_get_amount)],
         U_TOPUP_CHECK: [MessageHandler(filters.PHOTO | filters.Document.ALL, topup_get_check),
                         MessageHandler(filters.TEXT & ~filters.COMMAND, topup_get_check)]}))

    # ─── Karta orqali kino to'lash ───
    app.add_handler(cv(
        [CallbackQueryHandler(cb_pay_card, pattern=r"^pay_card\|")],
        {MV_CARD_CHECK: [
            MessageHandler(filters.PHOTO | filters.Document.ALL, mv_card_check_recv),
            MessageHandler(filters.TEXT & ~filters.COMMAND, mv_card_check_recv)
        ]}))

    # ─── Yordam ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^🆘 Yordam$"), support_start)],
        {U_SUPPORT: [MessageHandler(
            filters.TEXT | filters.PHOTO | filters.VOICE |
            filters.VIDEO | filters.Document.ALL, support_recv)]}))

    # ─── Admin javob ───
    app.add_handler(cv(
        [CallbackQueryHandler(cb_reply_open, pattern=r"^reply\|")],
        {U_ADM_REPLY: [MessageHandler(
            filters.TEXT | filters.PHOTO | filters.VOICE | filters.VIDEO, adm_reply_send)]}))

    # ─── Kino qo'shish ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^🎬 Kino qo'shish$"), adm_add_start)],
        {A_VID:      [MessageHandler(filters.VIDEO | filters.TEXT, a_vid)],
         A_MORE_VID: [MessageHandler(filters.VIDEO | filters.TEXT, a_more_vid)],
         A_CODE:     [MessageHandler(filters.TEXT, a_code)],
         A_INFO:     [MessageHandler(filters.TEXT, a_info)],
         A_PRICE:    [MessageHandler(filters.TEXT, a_price)]}))

    # ─── Davom ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^➕ Davomini qo'shish$"), cont_start)],
        {C_CODE: [MessageHandler(filters.TEXT, cont_code)],
         C_VID:  [MessageHandler(filters.VIDEO | filters.TEXT, cont_vid)],
         C_INFO: [MessageHandler(filters.TEXT, cont_info)],
         C_PRICE:[MessageHandler(filters.TEXT, cont_price)]}))

    # ─── Start xabari ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^⚙️ Start xabari$"), start_msg_open)],
        {ST_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, st_photo)],
         ST_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, st_text)]}))

    # ─── Kanal boshqaruv ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^📢 Kanal boshqaruv$"), ch_manage_start)],
        {CH_ACTION: [MessageHandler(filters.TEXT, ch_action)],
         CH_DEL_ID: [MessageHandler(filters.TEXT, ch_del_id)],
         CH_ID:     [MessageHandler(filters.TEXT, ch_id)],
         CH_LINK:   [MessageHandler(filters.TEXT, ch_link)],
         CH_NAME:   [MessageHandler(filters.TEXT, ch_name_save)]}))

    # ─── Link ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^🔗 Link qo'shish$"), link_start)],
        {LN_TITLE: [MessageHandler(filters.TEXT, ln_title)],
         LN_URL:   [MessageHandler(filters.TEXT, ln_url)]}))

    # ─── Barchaga xabar ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^📨 Barchaga xabar$"), bc_start)],
        {BC_MSG: [MessageHandler(
            filters.TEXT | filters.PHOTO | filters.VIDEO |
            filters.VOICE | filters.Document.ALL, bc_send)]}))

    # ─── ID ga xabar ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^📩 ID'ga xabar$"), snd_start)],
        {SND_ID:  [MessageHandler(filters.TEXT, snd_id)],
         SND_MSG: [MessageHandler(
             filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VOICE, snd_msg)]}))

    # ─── ID ga pul ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^💵 ID'ga pul$"), bal_start)],
        {BAL_ID:  [MessageHandler(filters.TEXT, bal_id)],
         BAL_AMT: [MessageHandler(filters.TEXT, bal_amt)]}))

    # ─── Barchaga pul ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^💰 Barchaga pul$"), allbal_start)],
        {ALLBAL_AMT: [MessageHandler(filters.TEXT, allbal_amt)]}))

    # ─── Karta ───
    app.add_handler(cv(
        [MessageHandler(filters.Regex("^💳 Karta o'rnat$"), card_start)],
        {CARD_NUM: [MessageHandler(filters.TEXT, card_save)]}))

    # ─── Callback handlers ───
    app.add_handler(CallbackQueryHandler(cb_sub_check,     pattern="^sub_check$"))
    app.add_handler(CallbackQueryHandler(cb_approve_topup, pattern=r"^atop\|"))
    app.add_handler(CallbackQueryHandler(cb_reject_topup,  pattern=r"^rtop\|"))
    app.add_handler(CallbackQueryHandler(cb_approve_movie, pattern=r"^amov\|"))
    app.add_handler(CallbackQueryHandler(cb_reject_movie,  pattern=r"^rmov\|"))
    app.add_handler(CallbackQueryHandler(cb_qism,          pattern=r"^qism\|"))
    app.add_handler(CallbackQueryHandler(cb_pay_bal,       pattern=r"^pay_bal\|"))
    app.add_handler(CallbackQueryHandler(topup_open,       pattern="^topup_open$"))

    # ─── Command handlers ───
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))

    # ─── Message handlers ───
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, on_text))

    log.info("✅ Bot ishga tushdi!")
    print("✅ Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
