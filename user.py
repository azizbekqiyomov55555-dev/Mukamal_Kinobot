from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS, PAYMENT_CARD
from database import db
from keyboards import (
    main_menu, video_parts_keyboard, video_share_close,
    payment_keyboard, subscribe_channels_keyboard, balance_menu,
    reply_to_user_keyboard
)
from states import UserStates

router = Router()


async def check_subscription(bot: Bot, user_id: int) -> bool:
    channels = await db.get_channels('telegram')
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


# ===== START =====
@router.message(CommandStart())
async def start_cmd(message: Message, bot: Bot):
    user = await db.get_user(message.from_user.id)
    is_new = user is None

    await db.create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )

    if is_new:
        from handlers.admin import notify_new_user
        await notify_new_user(bot, message.from_user)

    user_data = await db.get_user(message.from_user.id)
    if user_data and user_data['is_banned']:
        await message.answer("🚫 Siz botdan bloklangansiz.")
        return

    # Obuna tekshirish
    subscribed = await check_subscription(bot, message.from_user.id)
    if not subscribed:
        channels = await db.get_channels('telegram')
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            reply_markup=subscribe_channels_keyboard([dict(ch) for ch in channels])
        )
        return

    # Start xabari
    start_msg = await db.get_start_message()
    if start_msg:
        if start_msg['is_quote']:
            await message.answer(
                f"<blockquote>{start_msg['text']}</blockquote>",
                parse_mode="HTML",
                reply_markup=main_menu()
            )
        elif start_msg['quote_link']:
            await message.answer(
                f"🔗 {start_msg['quote_link']}",
                reply_markup=main_menu()
            )
        elif start_msg['photo_id']:
            await bot.send_photo(
                message.from_user.id,
                start_msg['photo_id'],
                caption=start_msg['text'],
                reply_markup=main_menu()
            )
        else:
            await message.answer(start_msg['text'], reply_markup=main_menu())
    else:
        await message.answer(
            f"👋 Xush kelibsiz, <b>{message.from_user.full_name}</b>!\n\n"
            "Videoni ko'rish uchun 🎬 <b>Kod kiriting</b> tugmasini bosing.",
            parse_mode="HTML",
            reply_markup=main_menu()
        )


# ===== OBUNA TEKSHIRISH =====
@router.callback_query(F.data == "check_subscribe")
async def check_subscribe(call: CallbackQuery, bot: Bot):
    subscribed = await check_subscription(bot, call.from_user.id)
    if not subscribed:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
        return
    await call.message.delete()
    await call.message.answer(
        "✅ Rahmat! Endi botdan foydalanishingiz mumkin.",
        reply_markup=main_menu()
    )


# ===== KOD KIRITING =====
@router.message(F.text == "🎬 Kod kiriting")
async def ask_code(message: Message, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if user and user['is_banned']:
        await message.answer("🚫 Siz botdan bloklangansiz.")
        return
    await message.answer("🔑 Video kodini kiriting:")
    await state.set_state(UserStates.waiting_code)


@router.message(UserStates.waiting_code)
async def recv_code(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    code = message.text.strip().upper()
    video = await db.get_video(code)

    if not video:
        await message.answer("❌ Bunday kod topilmadi. Qayta urinib ko'ring.")
        return

    parts = await db.get_video_parts(code)

    # Pullik video
    if video['is_paid']:
        # Sotib olganmi tekshir
        already = await db.has_purchased(message.from_user.id, code)
        if already:
            await message.answer(
                f"🎬 <b>{video['title']}</b>\n\nQaysi qismni ko'rishni xohlaysiz?",
                parse_mode="HTML",
                reply_markup=video_parts_keyboard(len(parts), code)
            )
            return

        user = await db.get_user(message.from_user.id)
        await message.answer(
            f"🎬 <b>{video['title']}</b>\n\n"
            f"💰 Bu video pullik: <b>{video['price']:,.0f} so'm</b>\n\n"
            f"To'lov usulini tanlang:",
            parse_mode="HTML",
            reply_markup=payment_keyboard(code, video['price'])
        )
    else:
        await message.answer(
            f"🎬 <b>{video['title']}</b>\n\nQaysi qismni ko'rishni xohlaysiz?",
            parse_mode="HTML",
            reply_markup=video_parts_keyboard(len(parts), code)
        )


# ===== VIDEO QISMLARINI KO'RISH =====
@router.callback_query(F.data.startswith("watch_part_"))
async def watch_part(call: CallbackQuery, bot: Bot):
    _, _, video_code, part_num = call.data.split("_", 3)
    part_num = int(part_num)

    video = await db.get_video(video_code)
    part = await db.get_video_part(video_code, part_num)
    parts = await db.get_video_parts(video_code)

    if not part:
        await call.answer("❌ Qism topilmadi!", show_alert=True)
        return

    caption = f"🎬 <b>{video['title']}</b>\n📺 {part_num}-qism\n\n{part['description'] or ''}"

    await bot.send_video(
        call.from_user.id,
        part['file_id'],
        caption=caption,
        parse_mode="HTML",
        reply_markup=video_share_close(video_code, part_num)
    )
    await call.answer()


@router.callback_query(F.data == "close_video")
async def close_video(call: CallbackQuery):
    await call.message.delete()


# ===== TO'LOV JARAYONI =====
@router.callback_query(F.data.startswith("pay_video_"))
async def pay_video(call: CallbackQuery, state: FSMContext):
    video_code = call.data.replace("pay_video_", "")
    video = await db.get_video(video_code)
    await state.update_data(pay_video_code=video_code, pay_type='card')
    await call.message.edit_text(
        f"💳 To'lov kartasi: <code>{PAYMENT_CARD}</code>\n\n"
        f"💰 Miqdor: <b>{video['price']:,.0f} so'm</b>\n\n"
        f"To'lovni amalga oshirib, chek (rasm yoki fayl) yuboring:",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_check)


@router.callback_query(F.data.startswith("pay_balance_"))
async def pay_balance(call: CallbackQuery, bot: Bot):
    video_code = call.data.replace("pay_balance_", "")
    video = await db.get_video(video_code)
    user = await db.get_user(call.from_user.id)

    if user['balance'] < video['price']:
        await call.answer(
            f"❌ Hisobingizda yetarli mablag' yo'q!\nBalans: {user['balance']:,.0f} so'm",
            show_alert=True
        )
        return

    await db.deduct_balance(call.from_user.id, video['price'])
    await db.add_purchase(call.from_user.id, video_code)

    parts = await db.get_video_parts(video_code)
    await call.message.edit_text(
        f"✅ Balansdan to'lov qilindi!\n💰 {video['price']:,.0f} so'm\n\nQaysi qismni ko'rishni xohlaysiz?",
        reply_markup=video_parts_keyboard(len(parts), video_code)
    )


@router.message(UserStates.waiting_check, F.photo | F.document)
async def recv_payment_check(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    video_code = data.get('pay_video_code')
    video = await db.get_video(video_code)

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id

    payment_id = await db.add_payment(
        message.from_user.id, video_code, video['price'], file_id, 'video'
    )

    await state.clear()
    await message.answer("✅ Chek qabul qilindi! Admin tasdiqlashini kuting...")

    for admin_id in ADMIN_IDS:
        try:
            caption = (
                f"💳 <b>Yangi to'lov so'rovi</b>\n\n"
                f"👤 Foydalanuvchi: {message.from_user.full_name}\n"
                f"🆔 ID: <code>{message.from_user.id}</code>\n"
                f"🎬 Video: {video['title']} (<code>{video_code}</code>)\n"
                f"💰 Narxi: {video['price']:,.0f} so'm"
            )
            if message.photo:
                await bot.send_photo(admin_id, file_id, caption=caption, parse_mode="HTML",
                                     reply_markup=__confirm_kb(payment_id, 'payment'))
            else:
                await bot.send_document(admin_id, file_id, caption=caption, parse_mode="HTML",
                                        reply_markup=__confirm_kb(payment_id, 'payment'))
        except Exception:
            pass


def __confirm_kb(payment_id, ptype):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    if ptype == 'payment':
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_payment_{payment_id}"),
             InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_payment_{payment_id}")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_topup_{payment_id}"),
             InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_topup_{payment_id}")]
        ])


# ===== HISOBIM =====
@router.message(F.text == "💰 Hisobim")
async def my_balance(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Foydalanuvchi topilmadi.")
        return
    await message.answer(
        f"💰 <b>Hisobim</b>\n\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"💵 Balans: <b>{user['balance']:,.0f} so'm</b>\n"
        f"📊 Jami to'lagan: <b>{user['total_paid']:,.0f} so'm</b>",
        parse_mode="HTML",
        reply_markup=balance_menu()
    )


# ===== HISOBNI TO'LDIRISH =====
@router.callback_query(F.data == "topup_balance")
async def topup_balance(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        f"💳 To'lov kartasi: <code>{PAYMENT_CARD}</code>\n\n"
        "Miqdorni o'tkazing va chek yuboring.\n"
        "Avval miqdorni kiriting (so'mda):",
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
            "So'ng chek (rasm yoki fayl) yuboring:",
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

    payment_id = await db.add_payment(
        message.from_user.id, 'topup', amount, file_id, 'topup'
    )
    await state.clear()
    await message.answer("✅ Chek qabul qilindi! Admin tasdiqlashini kuting...")

    for admin_id in ADMIN_IDS:
        try:
            caption = (
                f"💰 <b>Hisob to'ldirish so'rovi</b>\n\n"
                f"👤 {message.from_user.full_name}\n"
                f"🆔 <code>{message.from_user.id}</code>\n"
                f"💵 Miqdor: <b>{amount:,.0f} so'm</b>"
            )
            if message.photo:
                await bot.send_photo(admin_id, file_id, caption=caption, parse_mode="HTML",
                                     reply_markup=__confirm_kb(payment_id, 'topup'))
            else:
                await bot.send_document(admin_id, file_id, caption=caption, parse_mode="HTML",
                                        reply_markup=__confirm_kb(payment_id, 'topup'))
        except Exception:
            pass


# ===== ADMINGA XABAR =====
@router.message(F.text.in_(["📩 Adminga xabar", "❓ Yordam"]))
async def msg_to_admin(message: Message, state: FSMContext):
    await message.answer(
        "✉️ Xabarni yuboring (matn, rasm, stiker, ovozli xabar):"
    )
    await state.set_state(UserStates.waiting_message_to_admin)


@router.message(UserStates.waiting_message_to_admin)
async def forward_to_admin(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    sender = message.from_user

    for admin_id in ADMIN_IDS:
        try:
            header = (
                f"📩 <b>Foydalanuvchidan xabar</b>\n"
                f"👤 {sender.full_name}\n"
                f"🆔 <code>{sender.id}</code>\n\n"
            )
            kb = reply_to_user_keyboard(sender.id)

            if message.text:
                await bot.send_message(admin_id, header + message.text, parse_mode="HTML", reply_markup=kb)
            elif message.photo:
                await bot.send_photo(admin_id, message.photo[-1].file_id,
                                     caption=header + (message.caption or ""), parse_mode="HTML", reply_markup=kb)
            elif message.voice:
                await bot.send_voice(admin_id, message.voice.file_id,
                                     caption=header, parse_mode="HTML", reply_markup=kb)
            elif message.sticker:
                await bot.send_message(admin_id, header, parse_mode="HTML", reply_markup=kb)
                await bot.send_sticker(admin_id, message.sticker.file_id)
            elif message.document:
                await bot.send_document(admin_id, message.document.file_id,
                                        caption=header + (message.caption or ""), parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    await message.answer("✅ Xabaringiz adminga yuborildi!")
