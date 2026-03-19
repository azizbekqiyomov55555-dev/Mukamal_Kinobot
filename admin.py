import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, BufferedInputFile

from config import ADMIN_IDS, PAYMENT_CARD
from database import db
from keyboards import (
    admin_panel, admin_channel_menu, admin_bot_menu,
    confirm_payment_keyboard, confirm_topup_keyboard,
    user_profile_keyboard, start_message_type_keyboard,
    reply_to_user_keyboard
)
from states import (
    AdminVideoStates, AdminChannelStates, AdminSocialStates,
    AdminBanStates, AdminBalanceStates, AdminStartStates, AdminReplyStates
)

router = Router()

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ===== ADMIN PANEL =====
@router.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Admin Panel</b>", reply_markup=admin_panel(), parse_mode="HTML")

@router.callback_query(F.data == "back_admin")
async def back_admin(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🛠 <b>Admin Panel</b>", reply_markup=admin_panel(), parse_mode="HTML")

@router.callback_query(F.data == "close")
async def close_cb(call: CallbackQuery):
    await call.message.delete()

# ===== VIDEO QO'SHISH =====
@router.callback_query(F.data == "admin_add_video")
async def admin_add_video(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("📹 <b>Video yuborish uchun tugmani bosing:</b>\n\nVideo yuboring 👇", parse_mode="HTML")
    await state.set_state(AdminVideoStates.waiting_video)

@router.message(AdminVideoStates.waiting_video, F.video)
async def recv_video_part(message: Message, state: FSMContext):
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
    part_num = len(parts)
    await message.answer(
        f"✅ {part_num}-qism ma'lumoti saqlandi.\n\n"
        f"Boshqa qismlar kiritasizmi?",
        reply_markup=__more_parts_kb()
    )
    await state.set_state(AdminVideoStates.waiting_more_parts)

def __more_parts_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ha, yana qism", callback_data="add_more_part")],
        [InlineKeyboardButton(text="✅ O'tkazvorish (tugatish)", callback_data="finish_parts")]
    ])

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
    await message.answer(
        "💰 Bu video <b>pullikmi?</b>",
        parse_mode="HTML",
        reply_markup=__paid_kb()
    )
    await state.set_state(AdminVideoStates.waiting_video_paid)

def __paid_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, pullik", callback_data="video_paid_yes")],
        [InlineKeyboardButton(text="🆓 Yo'q, bepul", callback_data="video_paid_no")]
    ])

@router.callback_query(F.data.in_(["video_paid_yes", "video_paid_no"]))
async def recv_paid_choice(call: CallbackQuery, state: FSMContext):
    if call.data == "video_paid_yes":
        await state.update_data(is_paid=1)
        await call.message.edit_text("💲 Video <b>narxini</b> kiriting (so'mda):", parse_mode="HTML")
        await state.set_state(AdminVideoStates.waiting_video_price)
    else:
        await state.update_data(is_paid=0, price=0)
        await __save_video(call.message, state)

@router.message(AdminVideoStates.waiting_video_price)
async def recv_video_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "").replace(" ", ""))
        await state.update_data(price=price)
        await __save_video(message, state)
    except ValueError:
        await message.answer("❌ Narxni to'g'ri kiriting (faqat raqam):")

async def __save_video(message_or_msg, state: FSMContext):
    data = await state.get_data()
    code = data["code"]
    title = data["title"]
    is_paid = data.get("is_paid", 0)
    price = data.get("price", 0)
    parts = data.get("parts", [])
    descs = data.get("descs", [])

    await db.add_video(code, title, is_paid, price, len(parts))
    for i, (file_id, desc) in enumerate(zip(parts, descs), 1):
        await db.add_video_part(code, i, file_id, desc)

    await state.clear()
    msg = f"✅ Video muvaffaqiyatli saqlandi!\n\n📌 Kod: <code>{code}</code>\n🎬 Sarlavha: {title}\n📦 Qismlar: {len(parts)}"
    if is_paid:
        msg += f"\n💰 Narxi: {price:,.0f} so'm"
    if hasattr(message_or_msg, 'edit_text'):
        await message_or_msg.edit_text(msg, parse_mode="HTML", reply_markup=admin_panel())
    else:
        await message_or_msg.answer(msg, parse_mode="HTML", reply_markup=admin_panel())

# ===== KANALLAR =====
@router.callback_query(F.data == "admin_channels")
async def admin_channels(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("📢 <b>Telegram kanallar boshqaruvi</b>", reply_markup=admin_channel_menu(), parse_mode="HTML")

@router.callback_query(F.data == "add_tg_channel")
async def add_tg_channel_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📢 Kanal ID kiriting (masalan: @kanalim yoki -1001234567890):")
    await state.set_state(AdminChannelStates.waiting_channel_id)
    await state.update_data(ch_type='telegram')

@router.message(AdminChannelStates.waiting_channel_id)
async def recv_channel_id(message: Message, state: FSMContext):
    await state.update_data(channel_id=message.text.strip())
    await message.answer("📝 Kanal nomini kiriting:")
    await state.set_state(AdminChannelStates.waiting_channel_name)

@router.message(AdminChannelStates.waiting_channel_name)
async def recv_channel_name(message: Message, state: FSMContext):
    await state.update_data(channel_name=message.text)
    await message.answer("🔗 Kanal linkini kiriting (https://t.me/...):")
    await state.set_state(AdminChannelStates.waiting_channel_link)

@router.message(AdminChannelStates.waiting_channel_link)
async def recv_channel_link(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.add_channel(data['channel_id'], data['channel_name'], message.text, data.get('ch_type', 'telegram'))
    await state.clear()
    await message.answer("✅ Kanal qo'shildi!", reply_markup=admin_channel_menu())

@router.callback_query(F.data == "list_tg_channel")
async def list_tg_channels(call: CallbackQuery):
    channels = await db.get_channels('telegram')
    if not channels:
        await call.answer("Kanallar yo'q!", show_alert=True)
        return
    text = "📢 <b>Telegram kanallar:</b>\n\n"
    for ch in channels:
        text += f"🆔 ID: {ch['id']} | {ch['channel_name']} | {ch['channel_link']}\n"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_channel_menu())

@router.callback_query(F.data == "del_tg_channel")
async def del_tg_channel_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🗑 O'chirish uchun kanal DB-ID sini kiriting:")
    await state.set_state(AdminChannelStates.waiting_channel_id)
    await state.update_data(ch_type='delete')

# ===== BOTLAR =====
@router.callback_query(F.data == "admin_bots")
async def admin_bots(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("🤖 <b>Botlar boshqaruvi</b>", reply_markup=admin_bot_menu(), parse_mode="HTML")

@router.callback_query(F.data == "add_bot")
async def add_bot_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🤖 Bot username kiriting (@botusername):")
    await state.set_state(AdminChannelStates.waiting_bot_username)

@router.message(AdminChannelStates.waiting_bot_username)
async def recv_bot_username(message: Message, state: FSMContext):
    await state.update_data(bot_username=message.text.strip())
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
    await db.add_channel(data['bot_username'], data['bot_name'], message.text, 'bot')
    await state.clear()
    await message.answer("✅ Bot qo'shildi!", reply_markup=admin_bot_menu())

@router.callback_query(F.data == "list_bots")
async def list_bots(call: CallbackQuery):
    bots = await db.get_channels('bot')
    if not bots:
        await call.answer("Botlar yo'q!", show_alert=True)
        return
    text = "🤖 <b>Botlar:</b>\n\n"
    for b in bots:
        text += f"🆔 {b['id']} | {b['channel_name']} | {b['channel_link']}\n"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_bot_menu())

# ===== INSTAGRAM =====
@router.callback_query(F.data == "admin_instagram")
async def admin_instagram(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("📸 Instagram kanal linkini kiriting:")
    await state.set_state(AdminSocialStates.waiting_instagram)

@router.message(AdminSocialStates.waiting_instagram)
async def recv_instagram(message: Message, state: FSMContext):
    await db.add_social_link('instagram', message.text)
    await state.clear()
    await message.answer("✅ Instagram linki saqlandi!", reply_markup=admin_panel())

# ===== YOUTUBE =====
@router.callback_query(F.data == "admin_youtube")
async def admin_youtube(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("▶️ YouTube kanal linkini kiriting:")
    await state.set_state(AdminSocialStates.waiting_youtube)

@router.message(AdminSocialStates.waiting_youtube)
async def recv_youtube(message: Message, state: FSMContext):
    await db.add_social_link('youtube', message.text)
    await state.clear()
    await message.answer("✅ YouTube linki saqlandi!", reply_markup=admin_panel())

# ===== STATISTIKA =====
@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    users = await db.get_all_users()
    total = len(users)

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    fig.patch.set_facecolor('#1a1a2e')

    # Foydalanuvchilar ro'yxati
    ax1 = axes[0]
    ax1.set_facecolor('#16213e')
    ax1.set_title(f"👥 Foydalanuvchilar ({total} ta)", color='white', fontsize=13, pad=10)

    names = []
    ids = []
    dates = []
    for u in users[:15]:
        names.append(u['full_name'][:15] if u['full_name'] else "Noma'lum")
        ids.append(str(u['telegram_id']))
        dates.append(u['joined_at'][:10] if u['joined_at'] else "-")

    y_pos = list(range(len(names)))
    bars = ax1.barh(y_pos, [1] * len(names), color='#0f3460', edgecolor='#e94560', linewidth=0.5)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels([f"{n} ({i})" for n, i in zip(names, ids)], color='white', fontsize=7)
    ax1.set_xticks([])
    ax1.invert_yaxis()

    for i, (bar, d) in enumerate(zip(bars, dates)):
        ax1.text(0.5, bar.get_y() + bar.get_height() / 2, d,
                 va='center', ha='center', color='#e94560', fontsize=7)

    # Statistika xulosa
    ax2 = axes[1]
    ax2.set_facecolor('#16213e')
    ax2.set_title("📊 Statistika xulosa", color='white', fontsize=13, pad=10)
    ax2.axis('off')

    banned = sum(1 for u in users if u['is_banned'])
    active = total - banned
    total_bal = sum(u['balance'] or 0 for u in users)
    total_paid = sum(u['total_paid'] or 0 for u in users)

    stats_text = (
        f"Jami foydalanuvchilar: {total}\n"
        f"Faol: {active}\n"
        f"Bloklangan: {banned}\n"
        f"Jami balans: {total_bal:,.0f} so'm\n"
        f"Jami to'lov: {total_paid:,.0f} so'm"
    )
    ax2.text(0.1, 0.5, stats_text, color='white', fontsize=12,
             va='center', transform=ax2.transAxes,
             bbox=dict(boxstyle='round', facecolor='#0f3460', alpha=0.8))

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    plt.close()

    photo = BufferedInputFile(buf.read(), filename="stats.png")
    await bot.send_photo(
        call.from_user.id,
        photo,
        caption=f"📊 <b>Statistika</b>\n\n👥 Jami: {total}\n✅ Faol: {active}\n🚫 Bloklangan: {banned}",
        parse_mode="HTML",
        reply_markup=__stats_users_kb(users[:10])
    )
    await call.answer()

def __stats_users_kb(users):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for u in users:
        name = u['full_name'] or "Noma'lum"
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name[:20]}",
            url=f"tg://user?id={u['telegram_id']}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== YANGI OBUNACHI XABARI (user handlerdan chaqiriladi) =====
async def notify_new_user(bot: Bot, user):
    for admin_id in ADMIN_IDS:
        try:
            text = (
                f"🆕 <b>Yangi obunachi!</b>\n\n"
                f"👤 Ism: {user.full_name}\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"📅 Sana: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Lichkaga o'tish", url=f"tg://user?id={user.id}")]
            ])
            await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

# ===== TO'LOV TASDIQLASH =====
@router.callback_query(F.data.startswith("confirm_payment_"))
async def confirm_payment(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    payment_id = int(call.data.split("_")[-1])
    payment = await db.get_payment(payment_id)
    if not payment:
        await call.answer("To'lov topilmadi!", show_alert=True)
        return
    await db.update_payment_status(payment_id, 'confirmed')
    await db.add_purchase(payment['user_id'], payment['video_code'])

    video = await db.get_video(payment['video_code'])
    parts = await db.get_video_parts(payment['video_code'])
    from keyboards import video_parts_keyboard
    await bot.send_message(
        payment['user_id'],
        f"✅ To'lovingiz tasdiqlandi!\n\n🎬 <b>{video['title']}</b>\n\nQaytni ko'rishni xohlaysiz?",
        parse_mode="HTML",
        reply_markup=video_parts_keyboard(len(parts), payment['video_code'])
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("✅ Tasdiqlandi va video yuborildi!")

@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    payment_id = int(call.data.split("_")[-1])
    payment = await db.get_payment(payment_id)
    if payment:
        await db.update_payment_status(payment_id, 'rejected')
        await bot.send_message(payment['user_id'], "❌ To'lovingiz rad etildi. Iltimos, qayta urinib ko'ring yoki admin bilan bog'laning.")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("❌ Rad etildi")

# ===== HISOBNI TO'LDIRISH TASDIQLASH =====
@router.callback_query(F.data.startswith("confirm_topup_"))
async def confirm_topup(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    payment_id = int(call.data.split("_")[-1])
    payment = await db.get_payment(payment_id)
    if not payment:
        await call.answer("To'lov topilmadi!", show_alert=True)
        return
    await db.update_payment_status(payment_id, 'confirmed')
    await db.add_balance(payment['user_id'], payment['amount'])
    await bot.send_message(
        payment['user_id'],
        f"✅ Hisobingiz to'ldirildi!\n\n💰 Miqdor: <b>{payment['amount']:,.0f} so'm</b>",
        parse_mode="HTML"
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("✅ Hisob to'ldirildi!")

@router.callback_query(F.data.startswith("reject_topup_"))
async def reject_topup(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    payment_id = int(call.data.split("_")[-1])
    payment = await db.get_payment(payment_id)
    if payment:
        await db.update_payment_status(payment_id, 'rejected')
        await bot.send_message(payment['user_id'], "❌ Hisobni to'ldirish so'rovi rad etildi.")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("❌ Rad etildi")

# ===== BAN/UNBAN =====
@router.callback_query(F.data == "admin_ban")
async def admin_ban_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        "🚫 Ban/Unban\n\nFoydalanuvchi Telegram ID sini kiriting:",
        reply_markup=None
    )
    await state.set_state(AdminBanStates.waiting_user_id)

@router.message(AdminBanStates.waiting_user_id)
async def recv_ban_user_id(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        user = await db.get_user_by_id(uid)
        if not user:
            await message.answer("❌ Foydalanuvchi topilmadi!")
            await state.clear()
            return
        await state.update_data(target_id=uid)
        status = "🚫 Bloklangan" if user['is_banned'] else "✅ Faol"
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Ban qilish", callback_data="do_ban"),
             InlineKeyboardButton(text="✅ Bandan chiqarish", callback_data="do_unban")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_admin")]
        ])
        await message.answer(
            f"👤 {user['full_name']}\n🆔 {uid}\nHolat: {status}",
            reply_markup=kb
        )
        await state.set_state(AdminBanStates.waiting_action)
    except ValueError:
        await message.answer("❌ ID raqam bo'lishi kerak!")
        await state.clear()

@router.callback_query(F.data.in_(["do_ban", "do_unban"]), AdminBanStates.waiting_action)
async def do_ban_action(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    uid = data['target_id']
    if call.data == "do_ban":
        await db.ban_user(uid, 1)
        await bot.send_message(uid, "🚫 Siz botdan bloklanding.")
        await call.answer("✅ Ban qilindi!")
    else:
        await db.ban_user(uid, 0)
        await bot.send_message(uid, "✅ Siz botdan banning olindi!")
        await call.answer("✅ Bandan chiqarildi!")
    await state.clear()
    await call.message.edit_reply_markup(reply_markup=None)

# ===== BALANS QO'SHISH (ID orqali) =====
@router.callback_query(F.data == "admin_add_balance_id")
async def admin_add_balance_id(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💳 Foydalanuvchi ID sini kiriting:")
    await state.set_state(AdminBalanceStates.waiting_user_id)

@router.message(AdminBalanceStates.waiting_user_id)
async def recv_balance_user_id(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        user = await db.get_user_by_id(uid)
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
async def recv_add_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        data = await state.get_data()
        uid = data['target_id']
        await db.add_balance(uid, amount)
        await state.clear()
        await message.answer(f"✅ {amount:,.0f} so'm qo'shildi!", reply_markup=admin_panel())
        await bot.send_message(uid, f"💰 Hisobingizga <b>{amount:,.0f} so'm</b> qo'shildi!", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Miqdorni to'g'ri kiriting!")

# ===== HAMMAGA BALANS =====
@router.callback_query(F.data == "admin_add_balance_all")
async def admin_add_balance_all(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("💰 Barcha foydalanuvchilarga qo'shish miqdorini kiriting (so'mda):")
    await state.set_state(AdminBalanceStates.waiting_amount_all)

@router.message(AdminBalanceStates.waiting_amount_all)
async def recv_add_amount_all(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "").replace(" ", ""))
        await db.add_balance_all(amount)
        count = await db.get_users_count()
        await state.clear()
        await message.answer(f"✅ {count} ta foydalanuvchiga {amount:,.0f} so'm qo'shildi!", reply_markup=admin_panel())
    except ValueError:
        await message.answer("❌ Miqdorni to'g'ri kiriting!")

# ===== START XABAR SOZLASH =====
@router.callback_query(F.data == "admin_set_start")
async def admin_set_start(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("✉️ <b>Start xabar turini tanlang:</b>", parse_mode="HTML",
                                  reply_markup=start_message_type_keyboard())

@router.callback_query(F.data == "start_type_text")
async def start_type_text(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 Start xabar matni kiriting:")
    await state.set_state(AdminStartStates.waiting_text)
    await state.update_data(start_type='text')

@router.callback_query(F.data == "start_type_photo")
async def start_type_photo(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🖼 Rasm yuboring:")
    await state.set_state(AdminStartStates.waiting_photo)
    await state.update_data(start_type='photo')

@router.callback_query(F.data == "start_type_quote")
async def start_type_quote(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("💬 Iqtibos xabar matni kiriting:")
    await state.set_state(AdminStartStates.waiting_text)
    await state.update_data(start_type='quote')

@router.callback_query(F.data == "start_type_link")
async def start_type_link(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🔗 Link xabar matni kiriting:")
    await state.set_state(AdminStartStates.waiting_text)
    await state.update_data(start_type='link')

@router.message(AdminStartStates.waiting_photo, F.photo)
async def recv_start_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("📝 Endi rasm uchun matn kiriting:")
    await state.set_state(AdminStartStates.waiting_text)

@router.message(AdminStartStates.waiting_text)
async def recv_start_text(message: Message, state: FSMContext):
    data = await state.get_data()
    start_type = data.get('start_type', 'text')
    photo_id = data.get('photo_id')
    is_quote = 1 if start_type == 'quote' else 0
    quote_link = message.text if start_type == 'link' else None

    if start_type == 'link':
        await db.set_start_message("", photo_id, is_quote, quote_link)
        await state.clear()
        await message.answer("✅ Start xabari (link) saqlandi!", reply_markup=admin_panel())
    elif start_type == 'quote':
        await db.set_start_message(message.text, photo_id, 1, None)
        await state.clear()
        await message.answer("✅ Start xabari (iqtibos) saqlandi!", reply_markup=admin_panel())
    else:
        await db.set_start_message(message.text, photo_id, 0, None)
        await state.clear()
        await message.answer("✅ Start xabari saqlandi!", reply_markup=admin_panel())

# ===== ADMINGA JAVOB YUBORISH =====
@router.callback_query(F.data.startswith("reply_user_"))
async def reply_to_user_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split("_")[-1])
    await state.update_data(reply_to=user_id)
    await call.message.answer(f"✉️ {user_id} ga javob yozing:")
    await state.set_state(AdminReplyStates.waiting_reply)

@router.message(AdminReplyStates.waiting_reply)
async def send_reply_to_user(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = data['reply_to']
    try:
        if message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or "")
        elif message.voice:
            await bot.send_voice(user_id, message.voice.file_id)
        elif message.sticker:
            await bot.send_sticker(user_id, message.sticker.file_id)
        elif message.document:
            await bot.send_document(user_id, message.document.file_id, caption=message.caption or "")
        else:
            await bot.send_message(user_id, f"📩 Admin javobi:\n\n{message.text}")
        await message.answer("✅ Javob yuborildi!")
    except Exception as e:
        await message.answer(f"❌ Yuborishda xato: {e}")
    await state.clear()
