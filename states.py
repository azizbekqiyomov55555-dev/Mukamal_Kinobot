from aiogram.fsm.state import State, StatesGroup

class AdminVideoStates(StatesGroup):
    waiting_video = State()
    waiting_part_number = State()
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
    waiting_quote_link = State()

class UserStates(StatesGroup):
    waiting_code = State()
    waiting_check = State()
    waiting_topup_check = State()
    waiting_topup_amount = State()
    waiting_message_to_admin = State()
    waiting_reply_from_admin = State()

class AdminReplyStates(StatesGroup):
    waiting_reply = State()
