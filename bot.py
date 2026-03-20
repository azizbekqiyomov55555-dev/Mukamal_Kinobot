# ╔══════════════════════════════════════════════════════════════╗
# ║           MUKAMMAL KINO BOT  –  by Claude                   ║
# ╚══════════════════════════════════════════════════════════════╝

import logging, sqlite3, asyncio
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

BOT_TOKEN = "8655776547:AAEKHHQfCjvdwIgn_y4PH7de-b3g2Jd5iYs"
ADMIN_IDS = [8537782289]
TZ        = pytz.timezone("Asia/Tashkent")
DB_FILE   = "kino.db"

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

def db(): return sqlite3.connect(DB_FILE)

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        tg_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        phone TEXT, balance REAL DEFAULT 0, joined_at TEXT);
    CREATE TABLE IF NOT EXISTS parts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT,
        part_no INTEGER, file_id TEXT, info TEXT, price REAL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS txs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER,
        amount REAL, kind TEXT, code TEXT, part_no INTEGER,
        status TEXT DEFAULT 'pending', file_id TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS channels(
        id INTEGER PRIMARY KEY AUTOINCREMENT, cid TEXT, link TEXT, name TEXT);
    CREATE TABLE IF NOT EXISTS links(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, url TEXT);
    """)
    c.commit(); c.close()

def now(): return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
def get(k, d=""): c=db(); r=c.execute("SELECT v FROM settings WHERE k=?",(k,)).fetchone(); c.close(); return r[0] if r else d
def put(k,v): c=db(); c.execute("INSERT OR REPLACE INTO settings(k,v) VALUES(?,?)",(k,v)); c.commit(); c.close()
def reg_user(uid,un,fn): c=db(); c.execute("INSERT OR IGNORE INTO users(tg_id,username,full_name,joined_at) VALUES(?,?,?,?)",(uid,un,fn,now())); c.commit(); c.close()
def get_user(uid): c=db(); r=c.execute("SELECT * FROM users WHERE tg_id=?",(uid,)).fetchone(); c.close(); return r
def get_all_users(): c=db(); r=c.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall(); c.close(); return r
def balance(uid): c=db(); r=c.execute("SELECT balance FROM users WHERE tg_id=?",(uid,)).fetchone(); c.close(); return r[0] if r else 0
def add_bal(uid,a): c=db(); c.execute("UPDATE users SET balance=balance+? WHERE tg_id=?",(a,uid)); c.commit(); c.close()
def sub_bal(uid,a): c=db(); c.execute("UPDATE users SET balance=balance-? WHERE tg_id=?",(a,uid)); c.commit(); c.close()
def get_parts(code): c=db(); r=c.execute("SELECT * FROM parts WHERE code=? ORDER BY part_no",(code,)).fetchall(); c.close(); return r
def get_part(code,pno): c=db(); r=c.execute("SELECT * FROM parts WHERE code=? AND part_no=?",(code,pno)).fetchone(); c.close(); return r
def channels(): c=db(); r=c.execute("SELECT * FROM channels").fetchall(); c.close(); return r
def is_admin(uid): return uid in ADMIN_IDS

def main_kb(): return ReplyKeyboardMarkup([["💰 Hisobim","🆘 Yordam"]], resize_keyboard=True)
def adm_kb(): return ReplyKeyboardMarkup([
    ["🎬 Kino qo'shish","➕ Davomini qo'shish"],
    ["📢 Kanal qo'shish","🔗 Link qo'shish"],
    ["📨 Barchaga xabar","📩 ID'ga xabar"],
    ["💵 ID'ga pul","💰 Barchaga pul"],
    ["📊 Statistika","⚙️ Start xabari"],
    ["💳 Karta o'rnat","🏠 Asosiy menyu"]], resize_keyboard=True)
def cancel_kb(): return ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True)

(S_TOPUP_AMT, S_TOPUP_CHECK, S_SUPPORT, S_ADM_REPLY,
 A_VID, A_MORE_VID, A_CODE, A_INFO, A_PRICE,
 C_CODE, C_VID, C_INFO, C_PRICE,
 ST_PHOTO, ST_TEXT,
 CH_ID, CH_LINK, CH_NAME,
 LN_TITLE, LN_URL,
 ADM_BC, ADM_SID, ADM_SMSG,
 ADM_BID, ADM_BAMT, ADM_ALLAMT, ADM_CARD) = range(27)

async def check_sub(bot, uid):
    nj=[]
    for ch in channels():
        try:
            m=await bot.get_chat_member(ch[1],uid)
            if m.status in ("left","kicked","banned","restricted"):
                nj.append(ch)
        except Exception as e:
            log.warning(f"check_sub error for {ch[1]}: {e}")
            # Only block if channel exists in DB - skip broken channels
            pass
    return nj

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; reg_user(u.id,u.username,u.full_name)
    nj=await check_sub(ctx.bot,u.id)
    if nj:
        btns=[[InlineKeyboardButton(f"📢 {c[3]}",url=c[2])] for c in nj]+[[InlineKeyboardButton("✅ Tekshirish",callback_data="sub_check")]]
        await update.message.reply_text("⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling:",reply_markup=InlineKeyboardMarkup(btns)); return
    photo=get("start_photo"); text=get("start_text","🎬 Kino botga xush kelibsiz!\n\nKino kodini yuboring.")
    if photo: await update.message.reply_photo(photo=photo,caption=text,reply_markup=main_kb())
    else: await update.message.reply_text(text,reply_markup=main_kb())

async def cb_sub_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    nj=await check_sub(ctx.bot,q.from_user.id)
    if nj:
        btns=[[InlineKeyboardButton(f"📢 {c[3]}",url=c[2])] for c in nj]+[[InlineKeyboardButton("✅ Tekshirish",callback_data="sub_check")]]
        await q.edit_message_text("⚠️ Hali obuna bo'lmagan kanallar bor:",reply_markup=InlineKeyboardMarkup(btns))
    else:
        await q.message.delete(); u=q.from_user; photo=get("start_photo"); text=get("start_text","🎬 Kino botga xush kelibsiz!\n\nKino kodini yuboring.")
        if photo: await ctx.bot.send_photo(chat_id=u.id,photo=photo,caption=text,reply_markup=main_kb())
        else: await ctx.bot.send_message(chat_id=u.id,text=text,reply_markup=main_kb())

async def my_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; bal=balance(u.id)
    c=db(); txs=c.execute("SELECT amount,kind,code,part_no,created_at FROM txs WHERE tg_id=? AND status='approved' ORDER BY created_at DESC LIMIT 7",(u.id,)).fetchall(); c.close()
    hist="".join(f"\n  {'➕' if t[1]=='topup' else '🎬'} {t[0]:,.0f} so'm{f'  ({t[2]}/{t[3]}-qism)' if t[2] else ''}  —  {t[4]}" for t in txs)
    txt=f"👤 <b>Hisobim</b>\n\n🆔 ID: <code>{u.id}</code>\n👤 Ism: {u.full_name}\n💰 Balans: <b>{bal:,.0f} so'm</b>"
    if hist: txt+=f"\n\n📋 <b>So'nggi amallar:</b>{hist}"
    await update.message.reply_text(txt,parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Hisobni to'ldirish",callback_data="topup_start")]]))

async def cb_topup_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.message.reply_text("💵 Qancha pul kiritmoqchisiz? (so'mda, masalan: 50000)",reply_markup=cancel_kb())
    return S_TOPUP_AMT

async def s_topup_amt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=main_kb()); return ConversationHandler.END
    t=update.message.text.strip()
    if not t.isdigit(): await update.message.reply_text("❌ Faqat raqam kiriting!"); return S_TOPUP_AMT
    ctx.user_data["topup_amt"]=int(t); card=get("card","❗ Karta hali kiritilmagan")
    await update.message.reply_text(f"💳 Karta raqami: <b>{card}</b>\n💰 Miqdor: <b>{int(t):,.0f} so'm</b>\n\nUshbu kartaga pul o'tkazing va <b>chek rasmini yuboring</b>.",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return S_TOPUP_CHECK

async def s_topup_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=main_kb()); return ConversationHandler.END
    if update.message.photo: fid=update.message.photo[-1].file_id
    elif update.message.document: fid=update.message.document.file_id
    else: await update.message.reply_text("❌ Chek rasmini yuboring!"); return S_TOPUP_CHECK
    user=update.effective_user; amount=ctx.user_data.get("topup_amt",0)
    c=db(); c.execute("INSERT INTO txs(tg_id,amount,kind,status,file_id,created_at) VALUES(?,?,?,?,?,?)",(user.id,amount,"topup","pending",fid,now())); tx_id=c.lastrowid; c.commit(); c.close()
    for aid in ADMIN_IDS:
        try:
            kb=[[InlineKeyboardButton("✅ Tasdiqlash",callback_data=f"at_{tx_id}_{user.id}_{amount}"),InlineKeyboardButton("❌ Rad etish",callback_data=f"rt_{tx_id}_{user.id}")]]
            cap=f"💰 <b>HISOBNI TO'LDIRISH</b>\n\n👤 {user.full_name}\n🆔 <code>{user.id}</code>\n📱 @{user.username or '–'}\n💵 <b>{amount:,.0f} so'm</b>\n🕐 {now()}"
            await ctx.bot.send_photo(chat_id=aid,photo=fid,caption=cap,reply_markup=InlineKeyboardMarkup(kb),parse_mode=ParseMode.HTML)
        except Exception as e: log.error(e)
    await update.message.reply_text("✅ Chekingiz adminga yuborildi. Tez orada hisobingiz to'ldiriladi!",reply_markup=main_kb())
    return ConversationHandler.END

async def cb_approve_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    _,tx_id,uid,amount=q.data.split("_"); uid=int(uid); amount=float(amount)
    add_bal(uid,amount); c=db(); c.execute("UPDATE txs SET status='approved' WHERE id=?",(tx_id,)); c.commit(); c.close()
    try: await ctx.bot.send_message(uid,f"✅ Hisobingizga <b>{amount:,.0f} so'm</b> qo'shildi!\n💰 Joriy balans: <b>{balance(uid):,.0f} so'm</b>",parse_mode=ParseMode.HTML)
    except: pass
    await q.edit_message_caption(caption=(q.message.caption or "")+"\n\n✅ <b>TASDIQLANDI</b>",parse_mode=ParseMode.HTML)

async def cb_reject_topup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    _,tx_id,uid=q.data.split("_"); c=db(); c.execute("UPDATE txs SET status='rejected' WHERE id=?",(tx_id,)); c.commit(); c.close()
    try: await ctx.bot.send_message(int(uid),"❌ To'lovingiz rad etildi. Admin bilan bog'laning.")
    except: pass
    await q.edit_message_caption(caption=(q.message.caption or "")+"\n\n❌ <b>RAD ETILDI</b>",parse_mode=ParseMode.HTML)

async def show_movie_parts(update: Update, ctx: ContextTypes.DEFAULT_TYPE, code: str):
    parts=get_parts(code)
    if not parts: await update.message.reply_text("❌ Bunday kod topilmadi. To'g'ri kod kiriting."); return
    btns=[]
    for p in parts:
        price_str = "🆓 Bepul" if p[5]==0 else f"{p[5]:,.0f} so'm"
        lbl = f"📽 {p[2]}-qism  —  {price_str}" 
        btns.append([InlineKeyboardButton(lbl,callback_data=f"p_{code}_{p[2]}")])
    await update.message.reply_text(f"🎬 <b>Kod: {code}</b>\n\nQayta ko'rmoqchi bo'lgan qismni tanlang:",parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup(btns))

async def cb_part(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    parts=q.data.split("_",2); code=parts[1]; pno=int(parts[2])
    part=get_part(code,pno)
    if not part: await q.message.reply_text("❌ Qism topilmadi."); return
    price=part[5]; info=part[4] or ""; uid=q.from_user.id
    if price==0:
        cap=f"📽 <b>{pno}-qism</b>"+( f"\n\n{info}" if info else "")
        await q.message.delete(); await ctx.bot.send_video(chat_id=uid,video=part[3],caption=cap,parse_mode=ParseMode.HTML); return
    bal=balance(uid)
    txt=f"🎬 <b>Kod: {code}  —  {pno}-qism</b>\n{info}\n\n💰 Narx: <b>{price:,.0f} so'm</b>\n💳 Sizning balansingiz: <b>{bal:,.0f} so'm</b>"
    kb=[]
    if bal>=price: kb.append([InlineKeyboardButton(f"✅ Hisobdan to'lash  ({price:,.0f} so'm)",callback_data=f"pb_{code}_{pno}_bal")])
    else: kb.append([InlineKeyboardButton("💳 Hisobni to'ldirish",callback_data="topup_start")])
    kb.append([InlineKeyboardButton("💴 Karta orqali to'lash",callback_data=f"pb_{code}_{pno}_card")])
    await q.edit_message_text(txt,parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup(kb))

async def cb_pay_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    parts=q.data.split("_",3); code=parts[1]; pno=int(parts[2]); method=parts[3]
    part=get_part(code,pno)
    if not part: await q.message.reply_text("❌ Qism topilmadi."); return
    price=part[5]; uid=q.from_user.id; user=q.from_user
    if method=="bal":
        if balance(uid)<price: await q.answer("❌ Balans yetarli emas!",show_alert=True); return
        sub_bal(uid,price); c=db(); c.execute("INSERT INTO txs(tg_id,amount,kind,code,part_no,status,created_at) VALUES(?,?,?,?,?,?,?)",(uid,price,"purchase",code,pno,"approved",now())); c.commit(); c.close()
        cap=f"📽 <b>{pno}-qism</b>"+( f"\n\n{part[4]}" if part[4] else "")
        await q.message.delete(); await ctx.bot.send_video(chat_id=uid,video=part[3],caption=cap,parse_mode=ParseMode.HTML)
    elif method=="card":
        ctx.user_data.update({"mv_code":code,"mv_pno":pno,"mv_price":price,"mv_uid":uid,"mv_fname":user.full_name,"mv_uname":user.username,"wait_mv_chk":True})
        card=get("card","❗ Karta kiritilmagan")
        await q.edit_message_text(f"💳 Karta raqami: <b>{card}</b>\n💰 Miqdor: <b>{price:,.0f} so'm</b>\n\nPul o'tkazing va <b>chek rasmini yuboring</b>.",parse_mode=ParseMode.HTML)

async def recv_movie_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["wait_mv_chk"]=False
    user=update.effective_user; code=ctx.user_data.get("mv_code"); pno=ctx.user_data.get("mv_pno"); price=ctx.user_data.get("mv_price",0)
    if update.message.photo: fid=update.message.photo[-1].file_id
    elif update.message.document: fid=update.message.document.file_id
    else: ctx.user_data["wait_mv_chk"]=True; await update.message.reply_text("❌ Chek rasmini yuboring!"); return
    c=db(); c.execute("INSERT INTO txs(tg_id,amount,kind,code,part_no,status,file_id,created_at) VALUES(?,?,?,?,?,?,?,?)",(user.id,price,"purchase",code,pno,"pending",fid,now())); tx_id=c.lastrowid; c.commit(); c.close()
    for aid in ADMIN_IDS:
        try:
            kb=[[InlineKeyboardButton("✅ Tasdiqlash",callback_data=f"am_{tx_id}_{user.id}_{code}_{pno}"),InlineKeyboardButton("❌ Rad etish",callback_data=f"rm_{tx_id}_{user.id}")]]
            cap=f"🎬 <b>KINO TO'LOVI</b>\n\n👤 {user.full_name}\n🆔 <code>{user.id}</code>\n📱 @{user.username or '–'}\n🎬 Kod: <b>{code}</b>  |  <b>{pno}-qism</b>\n💵 <b>{price:,.0f} so'm</b>\n🕐 {now()}"
            await ctx.bot.send_photo(chat_id=aid,photo=fid,caption=cap,reply_markup=InlineKeyboardMarkup(kb),parse_mode=ParseMode.HTML)
        except Exception as e: log.error(e)
    await update.message.reply_text("✅ Chekingiz adminga yuborildi!",reply_markup=main_kb())

async def cb_approve_movie(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    p=q.data.split("_"); tx_id=p[1]; uid=int(p[2]); code=p[3]; pno=int(p[4])
    c=db(); c.execute("UPDATE txs SET status='approved' WHERE id=?",(tx_id,)); c.commit(); c.close()
    part=get_part(code,pno)
    if part:
        try:
            cap=f"📽 <b>{pno}-qism</b>"+( f"\n\n{part[4]}" if part[4] else "")
            await ctx.bot.send_message(uid,"✅ To'lovingiz tasdiqlandi! Kino yuborilmoqda...")
            await ctx.bot.send_video(chat_id=uid,video=part[3],caption=cap,parse_mode=ParseMode.HTML)
        except Exception as e: log.error(e)
    await q.edit_message_caption(caption=(q.message.caption or "")+"\n\n✅ <b>TASDIQLANDI</b>",parse_mode=ParseMode.HTML)

async def cb_reject_movie(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    _,tx_id,uid=q.data.split("_"); c=db(); c.execute("UPDATE txs SET status='rejected' WHERE id=?",(tx_id,)); c.commit(); c.close()
    try: await ctx.bot.send_message(int(uid),"❌ To'lovingiz rad etildi.")
    except: pass
    await q.edit_message_caption(caption=(q.message.caption or "")+"\n\n❌ <b>RAD ETILDI</b>",parse_mode=ParseMode.HTML)

async def support_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🆘 Adminga xabar yuboring.\n(Matn, rasm, ovozli xabar — istalgan):",reply_markup=cancel_kb())
    return S_SUPPORT

async def s_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=main_kb()); return ConversationHandler.END
    user=update.effective_user; msg=update.message
    for aid in ADMIN_IDS:
        try:
            await ctx.bot.send_message(aid,f"📩 <b>Foydalanuvchi murojaat</b>\n👤 {user.full_name}  |  🆔 <code>{user.id}</code>  |  @{user.username or '–'}",parse_mode=ParseMode.HTML)
            if msg.text: await ctx.bot.send_message(aid,msg.text)
            elif msg.photo: await ctx.bot.send_photo(aid,msg.photo[-1].file_id,caption=msg.caption or "")
            elif msg.voice: await ctx.bot.send_voice(aid,msg.voice.file_id)
            elif msg.video: await ctx.bot.send_video(aid,msg.video.file_id,caption=msg.caption or "")
            elif msg.document: await ctx.bot.send_document(aid,msg.document.file_id,caption=msg.caption or "")
            else: await ctx.bot.send_message(aid,"[Noma'lum xabar]")
            await ctx.bot.send_message(aid,"Javob berish uchun:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Javob yozish",callback_data=f"reply_{user.id}")]]))
        except Exception as e: log.error(e)
    await update.message.reply_text("✅ Xabaringiz yuborildi!",reply_markup=main_kb())
    return ConversationHandler.END

async def cb_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    ctx.user_data["reply_to"]=int(q.data.split("_")[1])
    await q.message.reply_text("✍️ Javob xabaringizni yuboring:",reply_markup=cancel_kb())
    return S_ADM_REPLY

async def s_adm_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    tid=ctx.user_data.get("reply_to"); msg=update.message
    try:
        if msg.text: await ctx.bot.send_message(tid,f"📨 <b>Admin javobi:</b>\n\n{msg.text}",parse_mode=ParseMode.HTML)
        elif msg.photo: await ctx.bot.send_photo(tid,msg.photo[-1].file_id,caption=f"📨 Admin javobi:\n{msg.caption or ''}")
        elif msg.voice: await ctx.bot.send_voice(tid,msg.voice.file_id)
        elif msg.video: await ctx.bot.send_video(tid,msg.video.file_id,caption=f"📨 Admin javobi:\n{msg.caption or ''}")
        await update.message.reply_text("✅ Javob yuborildi!",reply_markup=adm_kb())
    except Exception as e: await update.message.reply_text(f"❌ Xatolik: {e}",reply_markup=adm_kb())
    return ConversationHandler.END

async def adm_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    ctx.user_data.clear(); ctx.user_data["vids"]=[]
    await update.message.reply_text("🎬 <b>Yangi kino qo'shish</b>\n\n1-qism videosini yuboring:",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return A_VID

async def a_vid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if not update.message.video: await update.message.reply_text("❌ Video yuboring!"); return A_VID
    ctx.user_data["vids"].append(update.message.video.file_id); n=len(ctx.user_data["vids"])
    await update.message.reply_text(f"✅ {n}-qism qabul qilindi!\n\nYana qism qo'shasizmi yoki tugatamizmi?",reply_markup=ReplyKeyboardMarkup([[f"➕ {n+1}-qism qo'shish","⏭ Tugatish"]],resize_keyboard=True))
    return A_MORE_VID

async def a_more_vid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if update.message.video:
        ctx.user_data["vids"].append(update.message.video.file_id); n=len(ctx.user_data["vids"])
        await update.message.reply_text(f"✅ {n}-qism qabul qilindi!\n\nYana qo'shasizmi?",reply_markup=ReplyKeyboardMarkup([[f"➕ {n+1}-qism qo'shish","⏭ Tugatish"]],resize_keyboard=True))
        return A_MORE_VID
    if update.message.text and "Tugatish" in update.message.text:
        ctx.user_data["infos"]=[]; ctx.user_data["prices"]=[]
        await update.message.reply_text(f"✅ Jami {len(ctx.user_data['vids'])} ta video!\n\n🔑 Kino uchun KOD kiriting (masalan: 001, BATMAN):",reply_markup=cancel_kb())
        return A_CODE
    await update.message.reply_text("❌ Video yuboring yoki «Tugatish»ni bosing!"); return A_MORE_VID

async def a_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    code=update.message.text.strip()
    if get_parts(code): await update.message.reply_text("❌ Bu kod allaqachon mavjud! Boshqa kod kiriting:"); return A_CODE
    ctx.user_data["code"]=code
    await update.message.reply_text("📝 1-qism uchun kino haqida ma'lumot kiriting:")
    return A_INFO

async def a_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    ctx.user_data["infos"].append(update.message.text); idx=len(ctx.user_data["infos"]); total=len(ctx.user_data["vids"])
    if idx<total: await update.message.reply_text(f"📝 {idx+1}-qism uchun ma'lumot kiriting:"); return A_INFO
    await update.message.reply_text("💰 1-qism uchun narx kiriting (bepul = 0):"); return A_PRICE

async def a_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if not update.message.text.isdigit(): await update.message.reply_text("❌ Faqat raqam!"); return A_PRICE
    ctx.user_data["prices"].append(int(update.message.text)); idx=len(ctx.user_data["prices"]); total=len(ctx.user_data["vids"])
    if idx<total: await update.message.reply_text(f"💰 {idx+1}-qism uchun narx kiriting (0=bepul):"); return A_PRICE
    code=ctx.user_data["code"]; c=db()
    for i,(vid,inf,pr) in enumerate(zip(ctx.user_data["vids"],ctx.user_data["infos"],ctx.user_data["prices"]),1):
        c.execute("INSERT INTO parts(code,part_no,file_id,info,price) VALUES(?,?,?,?,?)",(code,i,vid,inf,pr))
    c.commit(); c.close()
    await update.message.reply_text(f"✅ Kino saqlandi!\n🔑 Kod: <code>{code}</code>\n📽 Qismlar: {len(ctx.user_data['vids'])}",parse_mode=ParseMode.HTML,reply_markup=adm_kb())
    return ConversationHandler.END

async def adm_cont_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("➕ <b>Kino davomini qo'shish</b>\n\nKino kodini kiriting:",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return C_CODE

async def c_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    code=update.message.text.strip(); parts=get_parts(code)
    if not parts: await update.message.reply_text("❌ Bu kod topilmadi!"); return C_CODE
    nxt=max(p[2] for p in parts)+1; ctx.user_data["c_code"]=code; ctx.user_data["c_pno"]=nxt
    await update.message.reply_text(f"✅ Topildi! Mavjud qismlar: {len(parts)}\n\n{nxt}-qism videosini yuboring:")
    return C_VID

async def c_vid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if not update.message.video: await update.message.reply_text("❌ Video yuboring!"); return C_VID
    ctx.user_data["c_vid"]=update.message.video.file_id
    await update.message.reply_text(f"📝 {ctx.user_data['c_pno']}-qism uchun ma'lumot kiriting:")
    return C_INFO

async def c_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    ctx.user_data["c_info"]=update.message.text
    await update.message.reply_text(f"💰 {ctx.user_data['c_pno']}-qism uchun narx kiriting (0=bepul):")
    return C_PRICE

async def c_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if not update.message.text.isdigit(): await update.message.reply_text("❌ Raqam kiriting!"); return C_PRICE
    code=ctx.user_data["c_code"]; pno=ctx.user_data["c_pno"]
    c=db(); c.execute("INSERT INTO parts(code,part_no,file_id,info,price) VALUES(?,?,?,?,?)",(code,pno,ctx.user_data["c_vid"],ctx.user_data["c_info"],int(update.message.text))); c.commit(); c.close()
    await update.message.reply_text(f"✅ {pno}-qism saqlandi!\n🔑 Kod: <code>{code}</code>",parse_mode=ParseMode.HTML,reply_markup=adm_kb())
    return ConversationHandler.END

async def adm_start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("⚙️ Start xabari uchun <b>rasm</b> yuboring (yo'q bo'lsa «O'tkazib yuborish»):",parse_mode=ParseMode.HTML,reply_markup=ReplyKeyboardMarkup([["⏭ O'tkazib yuborish","❌ Bekor qilish"]],resize_keyboard=True))
    return ST_PHOTO

async def st_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if update.message.photo: ctx.user_data["st_ph"]=update.message.photo[-1].file_id
    elif update.message.text=="⏭ O'tkazib yuborish": ctx.user_data["st_ph"]=""
    else: await update.message.reply_text("❌ Rasm yuboring yoki o'tkazib yuboring!"); return ST_PHOTO
    await update.message.reply_text("📝 Start xabari <b>matnini</b> kiriting (qanday kiritsangiz shunday saqlanadi):",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return ST_TEXT

async def st_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    put("start_text",update.message.text); put("start_photo",ctx.user_data.get("st_ph",""))
    await update.message.reply_text("✅ Start xabari saqlandi!",reply_markup=adm_kb())
    return ConversationHandler.END

async def adm_ch_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    chs=channels(); lst="\n".join(f"  • {c[3]}  ({c[1]})" for c in chs) if chs else "  Hali yo'q"
    await update.message.reply_text(f"📢 <b>Mavjud kanallar:</b>\n{lst}\n\nYangi kanal ID sini kiriting (@kanaladi yoki -100...):",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return CH_ID

async def ch_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    ctx.user_data["ch_id"]=update.message.text.strip(); await update.message.reply_text("🔗 Kanal havolasini kiriting (https://t.me/...):")
    return CH_LINK

async def ch_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    ctx.user_data["ch_link"]=update.message.text.strip(); await update.message.reply_text("📛 Kanal nomini kiriting:")
    return CH_NAME

async def ch_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    c=db(); c.execute("INSERT INTO channels(cid,link,name) VALUES(?,?,?)",(ctx.user_data["ch_id"],ctx.user_data["ch_link"],update.message.text.strip())); c.commit(); c.close()
    await update.message.reply_text("✅ Kanal qo'shildi!",reply_markup=adm_kb())
    return ConversationHandler.END

async def adm_link_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    c=db(); lns=c.execute("SELECT * FROM links").fetchall(); c.close()
    lst="\n".join(f"  • {l[1]}: {l[2]}" for l in lns) if lns else "  Hali yo'q"
    await update.message.reply_text(f"🔗 <b>Saqlangan linklar:</b>\n{lst}\n\nYangi link sarlavhasini kiriting:",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return LN_TITLE

async def ln_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    ctx.user_data["ln_t"]=update.message.text.strip(); await update.message.reply_text("🔗 URL ni kiriting:")
    return LN_URL

async def ln_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    c=db(); c.execute("INSERT INTO links(title,url) VALUES(?,?)",(ctx.user_data["ln_t"],update.message.text.strip())); c.commit(); c.close()
    await update.message.reply_text("✅ Link saqlandi!",reply_markup=adm_kb())
    return ConversationHandler.END

async def adm_bc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text(f"📨 <b>Barchaga xabar</b>\nFoydalanuvchilar: {len(get_all_users())}\n\nXabarni yuboring (qanday kiritsangiz shunday boradi):",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return ADM_BC

async def adm_bc_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    users=get_all_users(); ok=err=0; sm=await update.message.reply_text(f"📤 Yuborilmoqda... 0/{len(users)}")
    for i,u in enumerate(users):
        try:
            msg=update.message
            if msg.text: await ctx.bot.send_message(u[0],msg.text)
            elif msg.photo: await ctx.bot.send_photo(u[0],msg.photo[-1].file_id,caption=msg.caption or "")
            elif msg.video: await ctx.bot.send_video(u[0],msg.video.file_id,caption=msg.caption or "")
            elif msg.voice: await ctx.bot.send_voice(u[0],msg.voice.file_id)
            elif msg.document: await ctx.bot.send_document(u[0],msg.document.file_id,caption=msg.caption or "")
            ok+=1
        except: err+=1
        if (i+1)%20==0:
            try: await sm.edit_text(f"📤 {i+1}/{len(users)}...")
            except: pass
        await asyncio.sleep(0.05)
    await sm.edit_text(f"✅ Tayyor!\n✅ Yuborildi: {ok}\n❌ Xatolik: {err}")
    await update.message.reply_text("Done.",reply_markup=adm_kb()); return ConversationHandler.END

async def adm_sid_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("📩 Foydalanuvchi ID sini kiriting:",reply_markup=cancel_kb()); return ADM_SID

async def adm_sid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if not update.message.text.isdigit(): await update.message.reply_text("❌ Faqat raqam!"); return ADM_SID
    ctx.user_data["sid_id"]=int(update.message.text); await update.message.reply_text("✍️ Xabarni yuboring:"); return ADM_SMSG

async def adm_smsg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    tid=ctx.user_data.get("sid_id"); msg=update.message
    try:
        if msg.text: await ctx.bot.send_message(tid,msg.text)
        elif msg.photo: await ctx.bot.send_photo(tid,msg.photo[-1].file_id,caption=msg.caption or "")
        elif msg.video: await ctx.bot.send_video(tid,msg.video.file_id,caption=msg.caption or "")
        elif msg.voice: await ctx.bot.send_voice(tid,msg.voice.file_id)
        await update.message.reply_text("✅ Xabar yuborildi!",reply_markup=adm_kb())
    except Exception as e: await update.message.reply_text(f"❌ Xatolik: {e}",reply_markup=adm_kb())
    return ConversationHandler.END

async def adm_bid_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("💵 Foydalanuvchi ID sini kiriting:",reply_markup=cancel_kb()); return ADM_BID

async def adm_bid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if not update.message.text.isdigit(): await update.message.reply_text("❌ Faqat raqam!"); return ADM_BID
    uid=int(update.message.text); u=get_user(uid)
    if not u: await update.message.reply_text("❌ Foydalanuvchi topilmadi!"); return ADM_BID
    ctx.user_data["bid_uid"]=uid
    await update.message.reply_text(f"👤 {u[2]}  |  🆔 {u[0]}\n💰 Joriy balans: {u[4]:,.0f} so'm\n\nQancha pul qo'shish?"); return ADM_BAMT

async def adm_bamt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if not update.message.text.isdigit(): await update.message.reply_text("❌ Faqat raqam!"); return ADM_BAMT
    amt=int(update.message.text); uid=ctx.user_data["bid_uid"]; add_bal(uid,amt)
    c=db(); c.execute("INSERT INTO txs(tg_id,amount,kind,status,created_at) VALUES(?,?,?,?,?)",(uid,amt,"topup","approved",now())); c.commit(); c.close()
    try: await ctx.bot.send_message(uid,f"✅ Hisobingizga <b>{amt:,.0f} so'm</b> qo'shildi!\n💰 Balans: <b>{balance(uid):,.0f} so'm</b>",parse_mode=ParseMode.HTML)
    except: pass
    await update.message.reply_text(f"✅ {amt:,.0f} so'm qo'shildi!",reply_markup=adm_kb()); return ConversationHandler.END

async def adm_allamt_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text(f"💰 Barcha <b>{len(get_all_users())}</b> ta foydalanuvchi hisobiga pul qo'shish.\nMiqdor kiriting:",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return ADM_ALLAMT

async def adm_allamt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    if not update.message.text.isdigit(): await update.message.reply_text("❌ Faqat raqam!"); return ADM_ALLAMT
    amt=int(update.message.text); users=get_all_users(); c=db()
    for u in users:
        c.execute("UPDATE users SET balance=balance+? WHERE tg_id=?",(amt,u[0]))
        c.execute("INSERT INTO txs(tg_id,amount,kind,status,created_at) VALUES(?,?,?,?,?)",(u[0],amt,"topup","approved",now()))
    c.commit(); c.close()
    await update.message.reply_text(f"✅ {len(users)} ta foydalanuvchiga {amt:,.0f} so'mdan qo'shildi!",reply_markup=adm_kb())
    return ConversationHandler.END

async def adm_card_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text(f"💳 Joriy karta: <b>{get('card','Kiritilmagan')}</b>\n\nYangi karta raqamini kiriting:",parse_mode=ParseMode.HTML,reply_markup=cancel_kb())
    return ADM_CARD

async def adm_card_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text=="❌ Bekor qilish": await update.message.reply_text("Bekor qilindi.",reply_markup=adm_kb()); return ConversationHandler.END
    put("card",update.message.text.strip()); await update.message.reply_text("✅ Karta saqlandi!",reply_markup=adm_kb())
    return ConversationHandler.END


def build_stats_image(total,today,week,t_top,t_sal,movies,rows,top_mv):
    from PIL import Image, ImageDraw, ImageFont
    W=900; ROW_H=38; HEADER_H=180
    TOP_H=(60+len(top_mv)*ROW_H) if top_mv else 20
    TABLE_H=50+len(rows)*(ROW_H+2)
    H=HEADER_H+TOP_H+TABLE_H+60
    img=Image.new("RGB",(W,H),(255,255,255)); d=ImageDraw.Draw(img)
    try:
        fb=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",20)
        fn=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",17)
        fs=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",15)
        fh=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",26)
    except:
        fb=fn=fs=fh=ImageFont.load_default()
    d.rectangle([(0,0),(W,HEADER_H)],fill=(30,30,50))
    d.text((W//2,30),"STATISTIKA",font=fh,fill=(255,220,50),anchor="mm")
    boxes=[("Jami",str(total),(60,210,140)),("Bugun",str(today),(60,140,210)),("Hafta",str(week),(180,100,220)),("Kinolar",str(movies),(220,120,60))]
    bw=W//len(boxes)
    for i,(lbl,val,col) in enumerate(boxes):
        x=i*bw; d.rectangle([(x+8,60),(x+bw-8,HEADER_H-10)],fill=col,outline=(255,255,255),width=2)
        d.text((x+bw//2,82),lbl,font=fs,fill=(255,255,255),anchor="mm"); d.text((x+bw//2,115),val,font=fh,fill=(255,255,255),anchor="mm")
    y=HEADER_H+10
    d.rectangle([(10,y),(W-10,y+45)],fill=(240,248,255),outline=(180,180,200))
    d.text((20,y+8),f"Jami kiritildi: {t_top:,.0f} so'm",font=fb,fill=(30,120,60))
    d.text((W//2+20,y+8),f"Jami sotuvlar: {t_sal:,.0f} so'm",font=fb,fill=(200,60,60)); y+=55
    if top_mv:
        d.text((20,y),"Eng ko'p ko'rilgan kinolar:",font=fb,fill=(60,60,120)); y+=30
        for m in top_mv:
            d.rectangle([(10,y),(W-10,y+ROW_H-2)],fill=(245,245,255),outline=(210,210,230))
            d.text((20,y+9),f"Kod: {m[0]}  -  {m[1]}-qism  |  {m[2]} marta",font=fn,fill=(40,40,80)); y+=ROW_H
        y+=10
    cols=[("ID",90),("Ism",200),("Username",150),("Balans (so'm)",130),("Kiritdi",130),("Qo'shilgan",180)]
    d.rectangle([(0,y),(W,y+36)],fill=(50,60,90)); x=5
    for lbl,cw in cols:
        d.text((x+cw//2,y+8),lbl,font=fb,fill=(255,255,255),anchor="mm"); x+=cw
    y+=36
    colors=[(100,60,180),(30,30,30),(60,100,160),(30,120,60),(180,80,30),(80,80,80)]
    for i,u in enumerate(rows):
        bg=(250,250,250) if i%2==0 else (238,242,250); d.rectangle([(0,y),(W,y+ROW_H-2)],fill=bg); x=5
        vals=[str(u[0]),(u[1] or "")[:22],f"@{u[2] or '-'}",f"{u[3]:,.0f}",f"{u[5]:,.0f}",str(u[4] or "")[:16]]
        for j,(val,cw) in enumerate(zip(vals,[c[1] for c in cols])):
            d.text((x+4,y+9),val,font=fs,fill=colors[j]); x+=cw
        d.line([(0,y+ROW_H-2),(W,y+ROW_H-2)],fill=(220,220,230),width=1); y+=ROW_H
    return img

async def adm_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    c=db()
    total=c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today=c.execute("SELECT COUNT(*) FROM users WHERE joined_at>=date('now','-1 day')").fetchone()[0]
    week=c.execute("SELECT COUNT(*) FROM users WHERE joined_at>=date('now','-7 days')").fetchone()[0]
    t_top=c.execute("SELECT COALESCE(SUM(amount),0) FROM txs WHERE kind='topup' AND status='approved'").fetchone()[0]
    t_sal=c.execute("SELECT COALESCE(SUM(amount),0) FROM txs WHERE kind='purchase' AND status='approved'").fetchone()[0]
    movies=c.execute("SELECT COUNT(DISTINCT code) FROM parts").fetchone()[0]
    rows=c.execute("SELECT u.tg_id,u.full_name,u.username,u.balance,u.joined_at,COALESCE(SUM(CASE WHEN t.kind='topup' AND t.status='approved' THEN t.amount ELSE 0 END),0) FROM users u LEFT JOIN txs t ON u.tg_id=t.tg_id GROUP BY u.tg_id ORDER BY u.joined_at DESC LIMIT 30").fetchall()
    top_mv=c.execute("SELECT code,part_no,COUNT(*) cnt FROM txs WHERE kind='purchase' AND status='approved' AND code IS NOT NULL GROUP BY code,part_no ORDER BY cnt DESC LIMIT 5").fetchall()
    c.close()
    # Build image
    img = build_stats_image(total,today,week,t_top,t_sal,movies,rows,top_mv)
    import io
    buf=io.BytesIO(); img.save(buf,format="PNG"); buf.seek(0)
    await update.message.reply_photo(photo=buf,caption=f"📊 Statistika  |  {now()}",reply_markup=adm_kb())

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Siz admin emassiz!"); return
    await update.message.reply_text("👨‍💼 <b>Admin paneli</b>",parse_mode=ParseMode.HTML,reply_markup=adm_kb())

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t=update.message.text.strip(); uid=update.effective_user.id
    if t=="💰 Hisobim": return await my_account(update,ctx)
    if t=="🆘 Yordam": return await support_start(update,ctx)
    if t=="🏠 Asosiy menyu": await update.message.reply_text("Asosiy menyu:",reply_markup=main_kb()); return
    if t=="📊 Statistika" and is_admin(uid): return await adm_stats(update,ctx)
    nj=await check_sub(ctx.bot,uid)
    if nj:
        btns=[[InlineKeyboardButton(f"📢 {c[3]}",url=c[2])] for c in nj]+[[InlineKeyboardButton("✅ Tekshirish",callback_data="sub_check")]]
        await update.message.reply_text("⚠️ Avval kanallarga obuna bo'ling:",reply_markup=InlineKeyboardMarkup(btns)); return
    await show_movie_parts(update,ctx,t)

async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("wait_mv_chk"): await recv_movie_check(update,ctx)

def main():
    init_db()
    app=Application.builder().token(BOT_TOKEN).build()
    def cv(*a,**k): return ConversationHandler(*a,per_message=False,**k)
    app.add_handler(cv(entry_points=[CallbackQueryHandler(cb_topup_start,pattern="^topup_start$")],states={S_TOPUP_AMT:[MessageHandler(filters.TEXT&~filters.COMMAND,s_topup_amt)],S_TOPUP_CHECK:[MessageHandler(filters.PHOTO|filters.Document.ALL,s_topup_check)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^🆘 Yordam$"),support_start)],states={S_SUPPORT:[MessageHandler(filters.TEXT|filters.PHOTO|filters.VOICE|filters.VIDEO|filters.Document.ALL,s_support)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[CallbackQueryHandler(cb_reply,pattern="^reply_")],states={S_ADM_REPLY:[MessageHandler(filters.TEXT|filters.PHOTO|filters.VOICE|filters.VIDEO,s_adm_reply)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^🎬 Kino qo'shish$"),adm_add_start)],states={A_VID:[MessageHandler(filters.VIDEO|filters.TEXT,a_vid)],A_MORE_VID:[MessageHandler(filters.VIDEO|filters.TEXT,a_more_vid)],A_CODE:[MessageHandler(filters.TEXT,a_code)],A_INFO:[MessageHandler(filters.TEXT,a_info)],A_PRICE:[MessageHandler(filters.TEXT,a_price)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^➕ Davomini qo'shish$"),adm_cont_start)],states={C_CODE:[MessageHandler(filters.TEXT,c_code)],C_VID:[MessageHandler(filters.VIDEO|filters.TEXT,c_vid)],C_INFO:[MessageHandler(filters.TEXT,c_info)],C_PRICE:[MessageHandler(filters.TEXT,c_price)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^⚙️ Start xabari$"),adm_start_cmd)],states={ST_PHOTO:[MessageHandler(filters.PHOTO|filters.TEXT,st_photo)],ST_TEXT:[MessageHandler(filters.TEXT,st_text)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^📢 Kanal qo'shish$"),adm_ch_start)],states={CH_ID:[MessageHandler(filters.TEXT,ch_id)],CH_LINK:[MessageHandler(filters.TEXT,ch_link)],CH_NAME:[MessageHandler(filters.TEXT,ch_name)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^🔗 Link qo'shish$"),adm_link_start)],states={LN_TITLE:[MessageHandler(filters.TEXT,ln_title)],LN_URL:[MessageHandler(filters.TEXT,ln_url)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^📨 Barchaga xabar$"),adm_bc_start)],states={ADM_BC:[MessageHandler(filters.TEXT|filters.PHOTO|filters.VIDEO|filters.VOICE|filters.Document.ALL,adm_bc_send)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^📩 ID'ga xabar$"),adm_sid_start)],states={ADM_SID:[MessageHandler(filters.TEXT,adm_sid)],ADM_SMSG:[MessageHandler(filters.TEXT|filters.PHOTO|filters.VIDEO|filters.VOICE,adm_smsg)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^💵 ID'ga pul$"),adm_bid_start)],states={ADM_BID:[MessageHandler(filters.TEXT,adm_bid)],ADM_BAMT:[MessageHandler(filters.TEXT,adm_bamt)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^💰 Barchaga pul$"),adm_allamt_start)],states={ADM_ALLAMT:[MessageHandler(filters.TEXT,adm_allamt)]},fallbacks=[]))
    app.add_handler(cv(entry_points=[MessageHandler(filters.Regex("^💳 Karta o'rnat$"),adm_card_start)],states={ADM_CARD:[MessageHandler(filters.TEXT,adm_card_save)]},fallbacks=[]))
    app.add_handler(CallbackQueryHandler(cb_sub_check,pattern="^sub_check$"))
    app.add_handler(CallbackQueryHandler(cb_part,pattern="^p_"))
    app.add_handler(CallbackQueryHandler(cb_pay_btn,pattern="^pb_"))
    app.add_handler(CallbackQueryHandler(cb_approve_topup,pattern="^at_"))
    app.add_handler(CallbackQueryHandler(cb_reject_topup,pattern="^rt_"))
    app.add_handler(CallbackQueryHandler(cb_approve_movie,pattern="^am_"))
    app.add_handler(CallbackQueryHandler(cb_reject_movie,pattern="^rm_"))
    app.add_handler(CommandHandler("start",cmd_start))
    app.add_handler(CommandHandler("admin",cmd_admin))
    app.add_handler(MessageHandler(filters.PHOTO|filters.Document.ALL,on_photo))
    app.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,on_text))
    log.info("✅ Bot ishga tushdi!")
    print("✅ Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
