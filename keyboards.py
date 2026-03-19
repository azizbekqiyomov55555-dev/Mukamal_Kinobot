from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

# ===== FOYDALANUVCHI MENYUSI =====
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kod kiriting"), KeyboardButton(text="💰 Hisobim")],
            [KeyboardButton(text="📩 Adminga xabar"), KeyboardButton(text="❓ Yordam")]
        ],
        resize_keyboard=True
    )

# ===== ADMIN PANEL =====
def admin_panel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Video qo'shish", callback_data="admin_add_video")],
        [InlineKeyboardButton(text="📢 Telegram kanallar", callback_data="admin_channels"),
         InlineKeyboardButton(text="🤖 Botlar", callback_data="admin_bots")],
        [InlineKeyboardButton(text="📸 Instagram", callback_data="admin_instagram"),
         InlineKeyboardButton(text="▶️ YouTube", callback_data="admin_youtube")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💳 ID ga pul qo'shish", callback_data="admin_add_balance_id")],
        [InlineKeyboardButton(text="💰 Hammaga pul qo'shish", callback_data="admin_add_balance_all")],
        [InlineKeyboardButton(text="🚫 Ban / Unban", callback_data="admin_ban")],
        [InlineKeyboardButton(text="✉️ Start xabar sozlash", callback_data="admin_set_start")],
        [InlineKeyboardButton(text="🔙 Yopish", callback_data="close")]
    ])

def admin_channel_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_tg_channel")],
        [InlineKeyboardButton(text="🗑 Kanal o'chirish", callback_data="del_tg_channel")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="list_tg_channel")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_admin")]
    ])

def admin_bot_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Bot qo'shish", callback_data="add_bot")],
        [InlineKeyboardButton(text="🗑 Bot o'chirish", callback_data="del_bot")],
        [InlineKeyboardButton(text="📋 Botlar ro'yxati", callback_data="list_bots")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_admin")]
    ])

def video_parts_keyboard(parts_count, video_code):
    buttons = []
    row = []
    for i in range(1, parts_count + 1):
        row.append(InlineKeyboardButton(text=f"📺 {i}-qism", callback_data=f"watch_part_{video_code}_{i}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Yopish", callback_data="close_video")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def video_share_close(video_code, part_number):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Do'stlarga ulashish", switch_inline_query=f"video_{video_code}")],
        [InlineKeyboardButton(text="❌ Videoni yopish", callback_data="close_video")]
    ])

def payment_keyboard(video_code, price):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 To'lov qilish ({price} so'm)", callback_data=f"pay_video_{video_code}")],
        [InlineKeyboardButton(text="💰 Balansdan to'lash", callback_data=f"pay_balance_{video_code}")]
    ])

def check_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Chek yuborish", callback_data="send_check")]
    ])

def confirm_payment_keyboard(payment_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_payment_{payment_id}"),
         InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_payment_{payment_id}")]
    ])

def confirm_topup_keyboard(payment_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_topup_{payment_id}"),
         InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_topup_{payment_id}")]
    ])

def user_profile_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Xabar yuborish", url=f"tg://user?id={user_id}")]
    ])

def reply_to_user_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Javob yuborish", callback_data=f"reply_user_{user_id}")]
    ])

def subscribe_channels_keyboard(channels):
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(text=f"📢 {ch['channel_name']}", url=ch['channel_link'])])
    buttons.append([InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_subscribe")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def balance_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Hisobni to'ldirish", callback_data="topup_balance")]
    ])

def start_message_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Oddiy matn", callback_data="start_type_text")],
        [InlineKeyboardButton(text="🖼 Rasm + matn", callback_data="start_type_photo")],
        [InlineKeyboardButton(text="💬 Iqtibos xabar", callback_data="start_type_quote")],
        [InlineKeyboardButton(text="🔗 Link xabar", callback_data="start_type_link")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_admin")]
    ])
