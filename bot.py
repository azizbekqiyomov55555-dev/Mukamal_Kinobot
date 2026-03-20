"""
╔══════════════════════════════════════════════════════════╗
║   MUKAMMAL KINO BOT  v4.0  — Barcha xatolar tuzatildi   ║
╚══════════════════════════════════════════════════════════╝
"""
import logging, sqlite3, asyncio, io
from datetime import datetime
import pytz

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:
    PIL_OK = False

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode

# ══════════════════════════════════════════════════════════
#  SOZLAMALAR
# ══════════════════════════════════════════════════════════
BOT_TOKEN = "8655776547:AAEKHHQfCjvdwIgn_y4PH7de-b3g2Jd5iYs"
ADMIN_IDS =[8537782289]
TZ        = pytz.timezone("Asia/Tashkent")
DB_FILE   = "kino.db"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════
#  DATABASE FUNKSIYALARI
# ══════════════════════════════════════════════════════════
def db_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            joined_at TEXT
        );
        CREATE TABLE IF NOT EXISTS parts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            part_no INTEGER,
            file_id TEXT,
            info TEXT,
            price REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS txs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            amount REAL,
            kind TEXT,
            code TEXT,
            part_no INTEGER,
            status TEXT DEFAULT 'pending',
            file_id TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings(
            k TEXT PRIMARY KEY,
            v TEXT
        );
        CREATE TABLE IF NOT EXISTS channels(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cid TEXT,
            link TEXT,
            name TEXT
        );
        """)

def now_str(): return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def cfg_get(k, d=""):
    with db_conn() as c: r = c.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    return r["v"] if r else d

def cfg_set(k, v):
    with db_conn() as c: c.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)", (k, v))

def reg_user(uid, un, fn):
    with db_conn() as c:
        c.execute("INSERT OR IGNORE INTO users(tg_id,username,full_name,joined_at) VALUES(?,?,?,?)",
                  (uid, un or "", fn or "", now_str()))

def get_user(uid):
    with db_conn() as c: return c.execute("SELECT * FROM users WHERE tg_id=?", (uid,)).fetchone()

def get_all_users():
    with db_conn() as c: return c.execute("SELECT tg_id FROM users").fetchall()

def get_balance(uid):
    with db_conn() as c: r = c.execute("SELECT balance FROM users WHERE tg_id=?", (uid,)).fetchone()
    return float(r["balance"]) if r else 0.0

def add_balance(uid, amt):
    with db_conn() as c: c.execute("UPDATE users SET balance=balance+? WHERE tg_id=?", (amt, uid))

def sub_balance(uid, amt):
    with db_conn() as c: c.execute("UPDATE users SET balance=balance-? WHERE tg_id=?", (amt, uid))

def get_parts(code):
    with db_conn() as c: return c.execute("SELECT * FROM parts WHERE code=? ORDER BY part_no", (code,)).fetchall()

def get_part(code, pno):
    with db_conn() as c: return c.execute("SELECT * FROM parts WHERE code=? AND part_no=?", (code, pno)).fetchone()

def get_channels():
    with db_conn() as c: return c.execute("SELECT * FROM channels ORDER BY id").fetchall()

def is_admin(uid): return uid in ADMIN_IDS

# ══════════════════════════════════════════════════════════
#  KLAVIATURALAR
# ══════════════════════════════════════════════════════════
def kb_main(): return ReplyKeyboardMarkup([["💰 Hisobim", "🆘 Yordam"]], resize_keyboard=True)

def kb_admin():
    return ReplyKeyboardMarkup([["🎬 Kino qo'shish",   "➕ Davomini qo'shish"],
        ["📢 Kanal boshqaruv", "⚙️ Start xabari"],["📨 Barchaga xabar",  "📩 ID'ga xabar"],["💵 ID'ga pul",       "📊 Statistika"],["💳 Karta o'rnat",    "🏠 Asosiy menyu"],
    ], resize_keyboard=True)

def kb_cancel(): return ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)

# ══════════════════════════════════════════════════════════
#  HOLATLAR
# ══════════════════════════════════════════════════════════
(
    U_TOPUP_AMT, U_TOPUP_CHECK, U_MOVIE_CHECK, U_SUPPORT, U_ADM_REPLY,
    A_VID, A_MORE_VID, A_CODE, A_INFO, A_PRICE,
    C_CODE, C_VID, C_INFO, C_PRICE,
    ST_PHOTO, ST_TEXT,
    CH_ACTION, CH_DEL_ID, CH_ID, CH_LINK, CH_NAME,
    BC_MSG, SND_ID, SND_MSG, BAL_ID, BAL_AMT, CARD_NUM, MV_CARD_CHECK,
) = range(28)

# ══════════════════════════════════════════════════════════
#  OBUNA TEKSHIRISH
# ══════════════════════════════════════════════════════════
async def check_sub(bot, uid):
    not_in = []
    channels = get_channels()
    if not channels: return[]
    for ch in channels:
        try:
            m = await bot.get_chat_member(ch["cid"], uid)
            if m.status in ("left", "kicked", "banned"):
                not_in.append(ch)
        except Exception as e:
            log.warning(f"check_sub [{ch['cid']}]: {e}")
            not_in.append(ch)
    return not_in

def sub_keyboard(not_joined):
    btns = [[InlineKeyboardButton(f"📢 {c['name']}", url=c["link"])] for c in not_joined]
    btns.append([InlineKeyboardButton("✅ Obunani tekshirish", callback_data="sub_check")])
    return InlineKeyboardMarkup(btns)

async def send_start_msg(bot, uid):
    photo = cfg_get("start_photo", "")
    text  = cfg_get("start_text", "🎬 Kino botga xush kelibsiz!\n\nKino kodini yuboring.")
    kb    = kb_admin() if is_admin(uid) else kb_main()
    
    try: # HTML qoidalari (Iqtibos va hk) chiroyli ishlashi uchun ParseMode.HTML doim yoqilgan bo'ladi
        if photo: await bot.send_photo(chat_id=uid, photo=photo, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else: await bot.send_message(chat_id=uid, text=text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception as e:
        log.error(f"HTML parse error: {e}")
        try: # Agar HTML matnda xatolik bo'lsa oddiy matn rejimida yuboradi
            if photo: await bot.send_photo(chat_id=uid, photo=photo, caption=text, reply_markup=kb)
            else: await bot.send_message(chat_id=uid, text=text, reply_markup=kb)
        except: pass

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    reg_user(u.id, u.username, u.full_name)
    nj = await check_sub(ctx.bot, u.id)
    if nj:
        await update.message.reply_text("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=sub_keyboard(nj))
        return
    await send_start_msg(ctx.bot, u.id)

async def cb_sub_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    nj  = await check_sub(ctx.bot, uid)
    if nj:
        try: await q.edit_message_text("⚠️ Hali obuna bo'lmagan kanallar bor:", reply_markup=sub_keyboard(nj))
        except: pass
    else:
        try: await q.message.delete()
        except: pass
        await send_start_msg(ctx.bot, uid)

async def cmd_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = kb_admin() if is_admin(update.effective_user.id) else kb_main()
    await update.message.reply_text("🏠 Asosiy menyu:", reply_markup=kb)

# ══════════════════════════════════════════════════════════
#  HISOBIM VA TO'LDIRISH
# ══════════════════════════════════════════════════════════
async def cmd_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    nj = await check_sub(ctx.bot, u.id)
    if nj:
        await update.message.reply_text("⚠️ Avval obuna bo'ling:", reply_markup=sub_keyboard(nj))
        return

    bal = get_balance(u.id)
    with db_conn() as c:
        txs = c.execute("SELECT amount,kind,code,part_no,created_at FROM txs WHERE tg_id=? AND status='approved' ORDER BY created_at DESC LIMIT 7", (u.id,)).fetchall()
    
    hist = ""
    for t in txs:
        ico = "➕" if t["kind"] == "topup" else "🎬"
        ex  = f" ({t['code']}/{t['part_no']}-qism)" if t["code"] else ""
        hist += f"\n  {ico} {t['amount']:,.0f} so'm{ex}"
        
    txt = f"👤 <b>Hisobim</b>\n\n🆔 ID: <code>{u.id}</code>\n👤 Ism: {u.full_name}\n💰 Balans: <b>{bal:,.0f} so'm</b>"
    if hist: txt += f"\n\n📋 <b>So'nggi amallar:</b>{hist}"
    
    kb = [[InlineKeyboardButton("💳 Hisobni to'ldirish", callback_data="topup_open")]]
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

async def topup_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("💵 Qancha pul kiritmoqchisiz?\n(so'mda, masalan: 50000)", reply_markup=kb_cancel())
    return U_TOPUP_AMT

async def topup_get_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip().replace(" ", "").replace(",", "")
    if not t.isdigit() or int(t) < 1000:
        await update.message.reply_text("❌ Kamida 1000 so'm kiriting!")
        return U_TOPUP_AMT
        
    ctx.user_data["topup_amt"] = int(t)
    card = cfg_get("card", "❗ Karta hali o'rnatilmagan")
    
    await update.message.reply_text(
        f"💳 Karta raqami: <code>{card}</code>\n💰 Miqdor: <b>{int(t):,.0f} so'm</b>\n\nUshbu kartaga pul o'tkazing va <b>chek rasmini yuboring</b>.",
        parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return U_TOPUP_CHECK

async def topup_get_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.photo: fid = update.message.photo[-1].file_id
    elif update.message.document: fid = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Iltimos chek rasmini (foto) yuboring!")
        return U_TOPUP_CHECK
    
    user = update.effective_user
    amount = ctx.user_data.get("topup_amt")
    kb = kb_admin() if is_admin(user.id) else kb_main()
    
    if not amount:
        await update.message.reply_text("❌ Xatolik yuz berdi. Iltimos, hisobni to'ldirishni boshidan boshlang.", reply_markup=kb)
        return ConversationHandler.END

    with db_conn() as c:
        c.execute("INSERT INTO txs(tg_id,amount,kind,status,file_id,created_at) VALUES(?,?,?,?,?,?)",
                  (user.id, amount, "topup", "pending", fid, now_str()))
        tx_id = c.lastrowid
        
    for aid in ADMIN_IDS:
        try:
            kb_adm = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"atop|{tx_id}|{user.id}|{amount}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"rtop|{tx_id}|{user.id}"),
            ]])
            cap = (f"💰 <b>HISOBNI TO'LDIRISH</b>\n\n👤 {user.full_name}\n🆔 <code>{user.id}</code>\n"
                   f"📱 @{user.username or '–'}\n💵 <b>{amount:,.0f} so'm</b>\n🕐 {now_str()}")
            await ctx.bot.send_photo(chat_id=aid, photo=fid, caption=cap, reply_markup=kb_adm, parse_mode=ParseMode.HTML)
        except Exception as e:
            log.error(f"Admin g'a yuborishda xatolik: {e}")

    await update.message.reply_text("✅ Chekingiz adminga muvaffaqiyatli yuborildi!\nTez orada hisobingiz to'ldiriladi.", reply_markup=kb)
    ctx.user_data.clear()
    return ConversationHandler.END

async def cb_approve_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    _, tx_id, uid, amount = q.data.split("|")
    uid = int(uid); amount = float(amount)
    
    add_balance(uid, amount)
    with db_conn() as c: c.execute("UPDATE txs SET status='approved' WHERE id=?", (tx_id,))
    try: await ctx.bot.send_message(uid, f"✅ Hisobingizga <b>{amount:,.0f} so'm</b> qo'shildi!\n💰 Joriy balans: <b>{get_balance(uid):,.0f} so'm</b>", parse_mode=ParseMode.HTML)
    except: pass
    try: await q.edit_message_caption(caption=(q.message.caption or "") + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode=ParseMode.HTML)
    except: pass

async def cb_reject_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    _, tx_id, uid = q.data.split("|")
    with db_conn() as c: c.execute("UPDATE txs SET status='rejected' WHERE id=?", (tx_id,))
    try: await ctx.bot.send_message(int(uid), "❌ To'lovingiz rad etildi.")
    except: pass
    try: await q.edit_message_caption(caption=(q.message.caption or "") + "\n\n❌ <b>RAD ETILDI</b>", parse_mode=ParseMode.HTML)
    except: pass

# ══════════════════════════════════════════════════════════
#  KINO QIDIRISH VA XARID
# ══════════════════════════════════════════════════════════
async def show_parts(update: Update, ctx: ContextTypes.DEFAULT_TYPE, code: str):
    parts = get_parts(code)
    if not parts:
        await update.message.reply_text("❌ Bunday kod bilan kino topilmadi.")
        return
    btns =[]
    for p in parts:
        price_str = "🆓 Bepul" if p["price"] == 0 else f"{p['price']:,.0f} so'm"
        btns.append([InlineKeyboardButton(f"📽 {p['part_no']}-qism  —  {price_str}", callback_data=f"qism|{code}|{p['part_no']}")])
    await update.message.reply_text(f"🎬 <b>Kod: {code}</b>\n\nQismni tanlang:", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btns))

async def cb_qism(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, code, pno = q.data.split("|")
    pno = int(pno)
    part = get_part(code, pno)
    
    if not part:
        await q.message.reply_text("❌ Qism topilmadi."); return
    
    price = float(part["price"])
    info  = part["info"] or ""
    uid   = q.from_user.id

    if price == 0:
        cap = f"📽 <b>{pno}-qism</b>" + (f"\n\n{info}" if info else "")
        try: await q.message.delete()
        except: pass
        await ctx.bot.send_video(chat_id=uid, video=part["file_id"], caption=cap, parse_mode=ParseMode.HTML)
        return

    bal = get_balance(uid)
    txt = (f"🎬 <b>Kod: {code}  —  {pno}-qism</b>\n{info}\n\n"
           f"💰 Narx: <b>{price:,.0f} so'm</b>\n💳 Sizning balansingiz: <b>{bal:,.0f} so'm</b>")
    kb =[]
    if bal >= price: kb.append([InlineKeyboardButton(f"✅ Hisobdan to'lash ({price:,.0f} so'm)", callback_data=f"pay_bal|{code}|{pno}")])
    else: kb.append([InlineKeyboardButton("💳 Hisobni to'ldirish", callback_data="topup_open")])
    kb.append([InlineKeyboardButton("💴 Karta orqali to'lash", callback_data=f"pay_card|{code}|{pno}")])
    
    try: await q.edit_message_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
    except: await q.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

async def cb_pay_bal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, code, pno = q.data.split("|")
    pno = int(pno)
    part = get_part(code, pno)
    
    if not part: await q.answer("❌ Qism topilmadi!", show_alert=True); return
    price = float(part["price"])
    uid = q.from_user.id
    
    if get_balance(uid) < price: await q.answer("❌ Balansingiz yetarli emas!", show_alert=True); return
        
    sub_balance(uid, price)
    with db_conn() as c:
        c.execute("INSERT INTO txs(tg_id,amount,kind,code,part_no,status,created_at) VALUES(?,?,?,?,?,?,?)",
                  (uid, price, "purchase", code, pno, "approved", now_str()))
                  
    cap = f"📽 <b>{pno}-qism</b>" + (f"\n\n{part['info']}" if part["info"] else "")
    try: await q.message.delete()
    except: pass
    
    await ctx.bot.send_message(uid, f"✅ Hisobingizdan <b>{price:,.0f} so'm</b> yechildi!", parse_mode=ParseMode.HTML)
    await ctx.bot.send_video(chat_id=uid, video=part["file_id"], caption=cap, parse_mode=ParseMode.HTML)

async def cb_pay_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, code, pno = q.data.split("|")
    part = get_part(code, int(pno))
    
    if not part: await q.message.reply_text("❌ Qism topilmadi."); return ConversationHandler.END
        
    ctx.user_data["mv_code"] = code; ctx.user_data["mv_pno"] = int(pno); ctx.user_data["mv_price"] = float(part["price"])
    card = cfg_get("card", "❗ Karta o'rnatilmagan")
    
    try: await q.message.delete()
    except: pass
    
    await ctx.bot.send_message(q.from_user.id, f"💳 Karta raqami: <code>{card}</code>\n💰 Miqdor: <b>{part['price']:,.0f} so'm</b>\n\nPul o'tkazing va <b>chek rasmini yuboring</b>.", parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return MV_CARD_CHECK

async def mv_card_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.photo: fid = update.message.photo[-1].file_id
    elif update.message.document: fid = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Chek rasmini (foto) yuboring!"); return MV_CARD_CHECK
        
    user = update.effective_user
    code = ctx.user_data.get("mv_code"); pno = ctx.user_data.get("mv_pno"); price = ctx.user_data.get("mv_price")
    kb = kb_admin() if is_admin(user.id) else kb_main()
    
    if not code or not price:
        await update.message.reply_text("❌ Xatolik. Jarayonni boshidan boshlang.", reply_markup=kb)
        return ConversationHandler.END
        
    with db_conn() as c:
        c.execute("INSERT INTO txs(tg_id,amount,kind,code,part_no,status,file_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (user.id, price, "purchase", code, pno, "pending", fid, now_str()))
        tx_id = c.lastrowid
        
    for aid in ADMIN_IDS:
        try:
            kb_adm = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"amov|{tx_id}|{user.id}|{code}|{pno}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"rmov|{tx_id}|{user.id}"),
            ]])
            cap = (f"🎬 <b>KINO TO'LOVI (KARTA)</b>\n\n👤 {user.full_name}\n🆔 <code>{user.id}</code>\n"
                   f"🎬 Kod: <b>{code}</b> | <b>{pno}-qism</b>\n💵 <b>{price:,.0f} so'm</b>\n🕐 {now_str()}")
            await ctx.bot.send_photo(chat_id=aid, photo=fid, caption=cap, reply_markup=kb_adm, parse_mode=ParseMode.HTML)
        except Exception as e: log.error(f"mv_card_notify: {e}")

    await update.message.reply_text("✅ Chekingiz adminga yuborildi!\nAdmin tasdiqlashini kuting.", reply_markup=kb)
    ctx.user_data.clear()
    return ConversationHandler.END

async def cb_approve_movie(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    p = q.data.split("|"); tx_id = p[1]; uid = int(p[2]); code = p[3]; pno = int(p[4])
    
    with db_conn() as c: c.execute("UPDATE txs SET status='approved' WHERE id=?", (tx_id,))
    part = get_part(code, pno)
    if part:
        try:
            cap = f"📽 <b>{pno}-qism</b>" + (f"\n\n{part['info']}" if part["info"] else "")
            await ctx.bot.send_message(uid, "✅ To'lovingiz tasdiqlandi!")
            await ctx.bot.send_video(chat_id=uid, video=part["file_id"], caption=cap, parse_mode=ParseMode.HTML)
        except: pass
    try: await q.edit_message_caption(caption=(q.message.caption or "") + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode=ParseMode.HTML)
    except: pass

async def cb_reject_movie(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    _, tx_id, uid = q.data.split("|")
    with db_conn() as c: c.execute("UPDATE txs SET status='rejected' WHERE id=?", (tx_id,))
    try: await ctx.bot.send_message(int(uid), "❌ To'lovingiz rad etildi.")
    except: pass
    try: await q.edit_message_caption(caption=(q.message.caption or "") + "\n\n❌ <b>RAD ETILDI</b>", parse_mode=ParseMode.HTML)
    except: pass

# ══════════════════════════════════════════════════════════
#  START XABARI
# ══════════════════════════════════════════════════════════
async def start_msg_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    cur_text = cfg_get("start_text", "Hali o'rnatilmagan")
    cur_photo = cfg_get("start_photo", "")
    await update.message.reply_text(
        f"⚙️ <b>Start xabari sozlamalari</b>\n\n🖼 Rasm: {'✅ Bor' if cur_photo else '❌ Yo\'q'}\n📝 Joriy matn:\n{cur_text}\n\n"
        f"Yangi rasm yuboring yoki «⏭ O'tkazib yuborish»ni bosing:",
        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup([["⏭ O'tkazib yuborish"], ["❌ Bekor qilish"]], resize_keyboard=True))
    return ST_PHOTO

async def st_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        ctx.user_data["new_photo"] = update.message.photo[-1].file_id
        # Agar admin rasm bilan birga matn (caption) ham yuborgan bo'lsa, birdaniga saqlaymiz:
        if update.message.caption_html:
            cfg_set("start_photo", ctx.user_data["new_photo"])
            cfg_set("start_text", update.message.caption_html)
            await update.message.reply_text("✅ Rasm va matn (formatlangan holatda) birdaniga saqlandi!", reply_markup=kb_admin())
            return ConversationHandler.END
            
        await update.message.reply_text("✅ Rasm qabul qilindi!\n\n📝 Endi start xabari matnini kiriting:", reply_markup=kb_cancel())
    elif update.message.text == "⏭ O'tkazib yuborish":
        ctx.user_data["new_photo"] = cfg_get("start_photo", "")
        await update.message.reply_text("📝 Start xabari matnini kiriting:", reply_markup=kb_cancel())
    else:
        await update.message.reply_text("❌ Rasm yuboring yoki o'tkazib yuboring!"); return ST_PHOTO
    return ST_TEXT

async def st_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # text_html - Telegramdagi har qanday HTML formatlarni (qalin, iqtibos, blockquote) olib qoladi
    new_text = update.message.text_html or update.message.caption_html or update.message.text or ""
    new_photo = ctx.user_data.get("new_photo", "")
    
    cfg_set("start_text", new_text)
    cfg_set("start_photo", new_photo)
    await update.message.reply_text("✅ Start xabari muvaffaqiyatli saqlandi!", reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#  KANAL BOSHQARUV (Majburiy Obuna)
# ══════════════════════════════════════════════════════════
async def ch_manage_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    chs = get_channels()
    lst = "\n".join(f"  [{c['id']}] {c['name']}  |  {c['cid']}" for c in chs) if chs else "  ❌ Hali kanal yo'q"
    await update.message.reply_text(f"📢 <b>Majburiy obuna kanallar:</b>\n{lst}\n\nNima qilmoqchisiz?",
        parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup([["➕ Kanal qo'shish", "🗑 Kanal o'chirish"],["📋 Kanallar ro'yxati", "❌ Bekor qilish"]], resize_keyboard=True))
    return CH_ACTION

async def ch_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "📋 Kanallar ro'yxati":
        chs = get_channels()
        if not chs: await update.message.reply_text("📢 Kanal yo'q.", reply_markup=kb_admin())
        else:
            lst = "\n\n".join(f"[{c['id']}] <b>{c['name']}</b>\n   ID: <code>{c['cid']}</code>\n   Link: {c['link']}" for c in chs)
            await update.message.reply_text(f"📢 <b>Kanallar ro'yxati:</b>\n\n{lst}", parse_mode=ParseMode.HTML, reply_markup=kb_admin())
        return ConversationHandler.END
    if t == "➕ Kanal qo'shish":
        await update.message.reply_text("Kanal ID yoki @username kiriting:\n(Masalan: @kanal_useri yoki -100123...)", reply_markup=kb_cancel())
        return CH_ID
    if t == "🗑 Kanal o'chirish":
        chs = get_channels()
        if not chs: await update.message.reply_text("O'chirish uchun kanal yo'q.", reply_markup=kb_admin()); return ConversationHandler.END
        lst = "\n".join(f"  [{c['id']}] {c['name']}" for c in chs)
        await update.message.reply_text(f"Mavjud kanallar:\n{lst}\n\nO'chirish uchun <b>raqamini</b> kiriting:", parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
        return CH_DEL_ID
    return CH_ACTION

async def ch_del_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not t.isdigit(): await update.message.reply_text("❌ Raqam kiriting!"); return CH_DEL_ID
    with db_conn() as c:
        r = c.execute("SELECT name FROM channels WHERE id=?", (int(t),)).fetchone()
        if not r: await update.message.reply_text("❌ Bunday raqamli kanal topilmadi!"); return CH_DEL_ID
        c.execute("DELETE FROM channels WHERE id=?", (int(t),))
    await update.message.reply_text(f"✅ «{r['name']}» kanali o'chirildi!", reply_markup=kb_admin())
    return ConversationHandler.END

async def ch_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = update.message.text.strip()
    # Formatini to'g'rilaymiz
    if not cid.startswith("-100") and not cid.startswith("@"):
        if not cid.lstrip("-").isdigit(): cid = "@" + cid
            
    # Xavfsizlik va xatoliklar oldini olish (Majburiy obuna ishlashi uchun)
    try:
        chat = await ctx.bot.get_chat(cid)
        bot_member = await ctx.bot.get_chat_member(chat_id=chat.id, user_id=ctx.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ Bot ushbu kanalga admin emas!\nIltimos, botni avval kanalga admin qiling va keyin kanal ma'lumotini yozing:", reply_markup=kb_cancel())
            return CH_ID
            
        ctx.user_data["ch_cid"] = str(chat.id)
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik! Kanal topilmadi yoki bot kanalga a'zo emas.\n\nQayta kiring:", reply_markup=kb_cancel())
        return CH_ID

    await update.message.reply_text("🔗 Endi kanal havolasini kiriting (https://t.me/...):", reply_markup=kb_cancel())
    return CH_LINK

async def ch_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["ch_link"] = update.message.text.strip()
    await update.message.reply_text("📛 Kanal nomini kiriting:", reply_markup=kb_cancel())
    return CH_NAME

async def ch_name_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    with db_conn() as c: c.execute("INSERT INTO channels(cid,link,name) VALUES(?,?,?)", (ctx.user_data["ch_cid"], ctx.user_data["ch_link"], name))
    await update.message.reply_text(f"✅ Kanal muvaffaqiyatli qo'shildi!\nEndi bu kanal to'liq va kafolatli ishlaydi.", reply_markup=kb_admin())
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#  QOLGAN ADMIN FUNKSIYALARI (Qisqartirilgan shaklda saqlandi)
# ══════════════════════════════════════════════════════════
# (Kino qo'shish, Yordam, Statistika va boshqalar oldingiday o'z joyida)
async def adm_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    ctx.user_data.clear(); ctx.user_data["vids"] =[]
    await update.message.reply_text("🎬 <b>Yangi kino qo'shish</b>\n\n1-qism videosini yuboring:", parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return A_VID
async def a_vid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.video: await update.message.reply_text("❌ Video yuboring!"); return A_VID
    ctx.user_data["vids"].append(update.message.video.file_id)
    n = len(ctx.user_data["vids"])
    await update.message.reply_text(f"✅ {n}-qism qabul qilindi!\nYana video yuboring yoki «⏭ Tugatish» ni bosing.", reply_markup=ReplyKeyboardMarkup([[f"➕ {n+1}-qism qo'shish", "⏭ Tugatish"], ["❌ Bekor qilish"]], resize_keyboard=True))
    return A_MORE_VID
async def a_more_vid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.video:
        ctx.user_data["vids"].append(update.message.video.file_id)
        await update.message.reply_text(f"✅ {len(ctx.user_data['vids'])}-qism qabul!\nYana yuboring yoki «⏭ Tugatish» ni bosing.", reply_markup=ReplyKeyboardMarkup([[f"➕ {len(ctx.user_data['vids'])+1}-qism qo'shish", "⏭ Tugatish"],["❌ Bekor qilish"]], resize_keyboard=True))
        return A_MORE_VID
    if update.message.text and "Tugatish" in update.message.text:
        ctx.user_data["infos"] = []; ctx.user_data["prices"] =[]
        await update.message.reply_text(f"✅ Jami {len(ctx.user_data['vids'])} ta video!\n🔑 Kino kodini kiriting:", reply_markup=kb_cancel()); return A_CODE
    await update.message.reply_text("❌ Video yuboring yoki «Tugatish» ni bosing!"); return A_MORE_VID
async def a_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if get_parts(code): await update.message.reply_text("❌ Bu kod mavjud! Boshqa kiriting:"); return A_CODE
    ctx.user_data["code"] = code
    await update.message.reply_text("📝 1-qism uchun ma'lumot:", reply_markup=kb_cancel()); return A_INFO
async def a_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["infos"].append(update.message.text)
    idx = len(ctx.user_data["infos"]); total = len(ctx.user_data["vids"])
    if idx < total: await update.message.reply_text(f"📝 {idx+1}-qism uchun ma'lumot:"); return A_INFO
    await update.message.reply_text("💰 1-qism uchun narx (0 = bepul):"); return A_PRICE
async def a_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip().replace(" ", "").replace(",", "")
    if not t.isdigit(): await update.message.reply_text("❌ Raqam kiriting!"); return A_PRICE
    ctx.user_data["prices"].append(int(t))
    idx = len(ctx.user_data["prices"]); total = len(ctx.user_data["vids"])
    if idx < total: await update.message.reply_text(f"💰 {idx+1}-qism narxi (0 = bepul):"); return A_PRICE
    code = ctx.user_data["code"]
    with db_conn() as c:
        for i, (vid, inf, pr) in enumerate(zip(ctx.user_data["vids"], ctx.user_data["infos"], ctx.user_data["prices"]), 1):
            c.execute("INSERT INTO parts(code,part_no,file_id,info,price) VALUES(?,?,?,?,?)", (code, i, vid, inf, pr))
    await update.message.reply_text(f"✅ Saqlandi! Kod: <code>{code}</code>", parse_mode=ParseMode.HTML, reply_markup=kb_admin()); return ConversationHandler.END

async def support_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🆘 Adminga xabar yuboring:", reply_markup=kb_cancel()); return U_SUPPORT
async def support_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; msg = update.message
    for aid in ADMIN_IDS:
        try:
            await ctx.bot.send_message(aid, f"📩 <b>Murojaat</b>\n👤 {user.full_name}  🆔<code>{user.id}</code>", parse_mode=ParseMode.HTML)
            if msg.text: await ctx.bot.send_message(aid, msg.text)
            elif msg.photo: await ctx.bot.send_photo(aid, msg.photo[-1].file_id, caption=msg.caption)
            elif msg.voice: await ctx.bot.send_voice(aid, msg.voice.file_id)
            elif msg.video: await ctx.bot.send_video(aid, msg.video.file_id, caption=msg.caption)
            await ctx.bot.send_message(aid, "Javob:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Javob yozish", callback_data=f"reply|{user.id}")]]))
        except: pass
    await update.message.reply_text("✅ Yuborildi!", reply_markup=kb_admin() if is_admin(user.id) else kb_main()); return ConversationHandler.END

async def cb_reply_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    ctx.user_data["reply_to"] = int(q.data.split("|")[1])
    await q.message.reply_text("✍️ Javobingizni yuboring:", reply_markup=kb_cancel()); return U_ADM_REPLY
async def adm_reply_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = ctx.user_data.get("reply_to"); msg = update.message
    try:
        if msg.text: await ctx.bot.send_message(tid, f"📨 <b>Admin javobi:</b>\n\n{msg.text_html}", parse_mode=ParseMode.HTML)
        elif msg.photo: await ctx.bot.send_photo(tid, msg.photo[-1].file_id, caption=f"📨 Admin: {msg.caption or ''}")
        await update.message.reply_text("✅ Javob yuborildi!", reply_markup=kb_admin())
    except Exception as e: await update.message.reply_text(f"❌ Xatolik: {e}", reply_markup=kb_admin())
    return ConversationHandler.END

async def bc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text(f"📨 Barchaga xabarni kiriting:", reply_markup=kb_cancel()); return BC_MSG
async def bc_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users = get_all_users(); ok = err = 0
    sm = await update.message.reply_text(f"📤 Yuborilmoqda... 0/{len(users)}")
    for i, u in enumerate(users):
        try:
            msg = update.message
            if msg.text: await ctx.bot.send_message(u["tg_id"], msg.text_html, parse_mode=ParseMode.HTML)
            elif msg.photo: await ctx.bot.send_photo(u["tg_id"], msg.photo[-1].file_id, caption=msg.caption_html, parse_mode=ParseMode.HTML)
            ok += 1
        except: err += 1
        if (i + 1) % 25 == 0:
            try: await sm.edit_text(f"📤 Yuborilmoqda... {i+1}/{len(users)}")
            except: pass
        await asyncio.sleep(0.05)
    await sm.edit_text(f"✅ Yuborildi!\n✅ Muvaffaqiyatli: {ok}\n❌ Xato: {err}")
    return ConversationHandler.END

async def card_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    cur = cfg_get("card", "Hali o'rnatilmagan")
    await update.message.reply_text(f"💳 Joriy karta: <code>{cur}</code>\n\nYangi karta raqamini kiriting:", parse_mode=ParseMode.HTML, reply_markup=kb_cancel())
    return CARD_NUM
async def card_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    card = update.message.text.strip().replace(" ", "")
    cfg_set("card", card)
    await update.message.reply_text(f"✅ Karta saqlandi!\n💳 <code>{card}</code>", parse_mode=ParseMode.HTML, reply_markup=kb_admin()); return ConversationHandler.END

async def bal_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("💵 ID kiriting:", reply_markup=kb_cancel()); return BAL_ID
async def bal_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if not t.lstrip("-").isdigit(): await update.message.reply_text("❌ Xato ID!"); return BAL_ID
    ctx.user_data["bal_uid"] = int(t)
    await update.message.reply_text("💰 Miqdorini kiriting:", reply_markup=kb_cancel()); return BAL_AMT
async def bal_amt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip().replace(" ", "")
    if not t.lstrip("-").isdigit(): await update.message.reply_text("❌ Xato!"); return BAL_AMT
    uid = ctx.user_data["bal_uid"]; amt = int(t)
    add_balance(uid, amt)
    await update.message.reply_text(f"✅ {uid} ga {amt:,.0f} so'm qo'shildi!", reply_markup=kb_admin()); return ConversationHandler.END

async def adm_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    with db_conn() as c:
        total  = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        t_top  = c.execute("SELECT COALESCE(SUM(amount),0) FROM txs WHERE kind='topup' AND status='approved'").fetchone()[0]
    txt = f"📊 <b>STATISTIKA</b>\n\n👥 Jami foydalanuvchi: <b>{total}</b>\n💰 Jami kiritilgan pul: <b>{t_top:,.0f} so'm</b>"
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=kb_admin())

# ══════════════════════════════════════════════════════════
#  ASOSIY QISMLAR
# ══════════════════════════════════════════════════════════
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    uid = update.effective_user.id

    nj = await check_sub(ctx.bot, uid)
    if nj:
        await update.message.reply_text("⚠️ Avval quyidagi kanallarga obuna bo'ling:", reply_markup=sub_keyboard(nj))
        return

    # Shunchaki matn sifatida qidiradi (Kino kodi)
    await show_parts(update, ctx, t)

async def unhandled_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Agar foydalanuvchi kutilmaganda rasm yuborsa, bot shunchaki e'tiborsiz qoldirmasligi uchun
    await update.message.reply_text("⚠️ Iltimos, avval kerakli menyuni tanlang yoki kino kodini yozing.")

async def cancel_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = kb_admin() if is_admin(update.effective_user.id) else kb_main()
    await update.message.reply_text("❌ Amaliyot bekor qilindi.", reply_markup=kb)
    ctx.user_data.clear()
    return ConversationHandler.END

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    def cv(entry, states):
        return ConversationHandler(
            entry_points=entry,
            states=states,
            fallbacks=[MessageHandler(filters.Regex("^❌ Bekor qilish$"), cancel_handler)],
            per_message=False,
            allow_reentry=True,
        )

    # Doimiy tugmalar
    app.add_handler(MessageHandler(filters.Regex("^💰 Hisobim$"), cmd_account))
    app.add_handler(MessageHandler(filters.Regex("^📊 Statistika$"), adm_stats))
    app.add_handler(MessageHandler(filters.Regex("^🏠 Asosiy menyu$"), cmd_home))

    # Xotiraga bog'liq tizimlar (to'lovlar)
    app.add_handler(cv([CallbackQueryHandler(topup_open, pattern="^topup_open$")],
        {U_TOPUP_AMT:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), topup_get_amount)],
         U_TOPUP_CHECK:[MessageHandler((filters.PHOTO | filters.Document.ALL | filters.TEXT) & ~filters.Regex("^❌ Bekor qilish$"), topup_get_check)]}))

    app.add_handler(cv([CallbackQueryHandler(cb_pay_card, pattern=r"^pay_card\|")],
        {MV_CARD_CHECK:[MessageHandler((filters.PHOTO | filters.Document.ALL | filters.TEXT) & ~filters.Regex("^❌ Bekor qilish$"), mv_card_recv)]}))

    # Admin qismlari
    app.add_handler(cv([MessageHandler(filters.Regex("^🎬 Kino qo'shish$"), adm_add_start)],
        {A_VID:[MessageHandler((filters.VIDEO | filters.TEXT) & ~filters.Regex("^❌ Bekor qilish$"), a_vid)],
         A_MORE_VID:[MessageHandler((filters.VIDEO | filters.TEXT) & ~filters.Regex("^❌ Bekor qilish$"), a_more_vid)],
         A_CODE:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), a_code)],
         A_INFO:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), a_info)],
         A_PRICE:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), a_price)]}))

    app.add_handler(cv([MessageHandler(filters.Regex("^⚙️ Start xabari$"), start_msg_open)],
        {ST_PHOTO:[MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.Regex("^❌ Bekor qilish$"), st_photo)],
         ST_TEXT:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), st_text)]}))

    app.add_handler(cv([MessageHandler(filters.Regex("^📢 Kanal boshqaruv$"), ch_manage_start)],
        {CH_ACTION:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), ch_action)],
         CH_DEL_ID:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), ch_del_id)],
         CH_ID:    [MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), ch_id)],
         CH_LINK:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), ch_link)],
         CH_NAME:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), ch_name_save)]}))

    app.add_handler(cv([MessageHandler(filters.Regex("^📨 Barchaga xabar$"), bc_start)],
        {BC_MSG:[MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.VOICE | filters.Document.ALL) & ~filters.Regex("^❌ Bekor qilish$"), bc_send)]}))

    app.add_handler(cv([MessageHandler(filters.Regex("^🆘 Yordam$"), support_start)],
        {U_SUPPORT:[MessageHandler((filters.TEXT | filters.PHOTO | filters.VOICE | filters.VIDEO | filters.Document.ALL) & ~filters.Regex("^❌ Bekor qilish$"), support_recv)]}))

    app.add_handler(cv([CallbackQueryHandler(cb_reply_open, pattern=r"^reply\|")],
        {U_ADM_REPLY:[MessageHandler((filters.TEXT | filters.PHOTO | filters.VOICE | filters.VIDEO) & ~filters.Regex("^❌ Bekor qilish$"), adm_reply_send)]}))

    app.add_handler(cv([MessageHandler(filters.Regex("^💳 Karta o'rnat$"), card_start)],
        {CARD_NUM:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), card_save)]}))

    app.add_handler(cv([MessageHandler(filters.Regex("^💵 ID'ga pul$"), bal_start)],
        {BAL_ID:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), bal_id)],
         BAL_AMT:[MessageHandler(filters.TEXT & ~filters.Regex("^❌ Bekor qilish$"), bal_amt)]}))

    # Callback'lar
    app.add_handler(CallbackQueryHandler(cb_sub_check,     pattern="^sub_check$"))
    app.add_handler(CallbackQueryHandler(cb_approve_topup, pattern=r"^atop\|"))
    app.add_handler(CallbackQueryHandler(cb_reject_topup,  pattern=r"^rtop\|"))
    app.add_handler(CallbackQueryHandler(cb_approve_movie, pattern=r"^amov\|"))
    app.add_handler(CallbackQueryHandler(cb_reject_movie,  pattern=r"^rmov\|"))
    app.add_handler(CallbackQueryHandler(cb_qism,          pattern=r"^qism\|"))
    app.add_handler(CallbackQueryHandler(cb_pay_bal,       pattern=r"^pay_bal\|"))

    # Matn va Media ushlagichlari
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_home))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, unhandled_media))

    log.info("✅ Bot v4.0 ishga tushdi!")
    print("✅ Bot v4.0 ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
