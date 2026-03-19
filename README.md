# 🤖 Telegram Bot - To'liq Qo'llanma

## 📁 Fayl tuzilmasi

```
bot/
├── main.py              # Asosiy ishga tushirish fayli
├── config.py            # Sozlamalar (TOKEN, ADMIN_ID, KARTA)
├── keyboards.py         # Barcha tugmalar
├── states.py            # FSM holatlari
├── requirements.txt     # Kutubxonalar
├── database/
│   ├── __init__.py
│   └── db.py            # SQLite ma'lumotlar bazasi
└── handlers/
    ├── __init__.py
    ├── admin.py          # Admin funksiyalari
    ├── user.py           # Foydalanuvchi funksiyalari
    └── payment.py        # To'lov (admin.py va user.py da)
```

---

## ⚙️ O'rnatish

### 1. Kutubxonalarni o'rnating:
```bash
pip install -r requirements.txt
```

### 2. `config.py` ni sozlang:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"   # @BotFather dan oling
ADMIN_IDS = [123456789]              # Telegram ID ingiz
PAYMENT_CARD = "8600 0000 0000 0000" # To'lov karta raqami
```

### 3. Botni ishga tushiring:
```bash
python main.py
```

---

## 👑 Admin buyruqlari

### `/admin` - Admin panel
Admin paneli quyidagi imkoniyatlarni beradi:

| Tugma | Funksiya |
|-------|----------|
| 📹 Video qo'shish | Yangi video yoki film qo'shish |
| 📢 Telegram kanallar | Obuna kanallari boshqaruvi |
| 🤖 Botlar | Bot qo'shish/o'chirish |
| 📸 Instagram | Instagram link sozlash |
| ▶️ YouTube | YouTube link sozlash |
| 📊 Statistika | Rasm ko'rinishida statistika |
| 💳 ID ga pul qo'shish | Aniq foydalanuvchiga balans qo'shish |
| 💰 Hammaga pul qo'shish | Barcha foydalanuvchilarga balans |
| 🚫 Ban / Unban | Foydalanuvchini ban qilish |
| ✉️ Start xabar | Start xabarni sozlash |

---

## 🎬 Video qo'shish jarayoni (Admin)

1. `/admin` → 📹 Video qo'shish
2. Video faylini yuboring
3. Qism raqami → Ma'lumot matni
4. "Yana qism" yoki "O'tkazvorish"
5. Video **KOD** kiriting (masalan: `FILM001`)
6. Sarlavha kiriting
7. Pullik/Bepul tanlang
8. Narx kiriting (pullik bo'lsa)
9. ✅ Saqlandi!

---

## 👤 Foydalanuvchi amallari

### 🎬 Kod kiriting
- Video kodini kiriting
- Bepul video → qismlar ko'rsatiladi
- Pullik video → to'lov sahifasi chiqadi

### 💳 To'lov jarayoni (Pullik video)
1. "💳 To'lov qilish" yoki "💰 Balansdan to'lash"
2. Karta raqamiga pul o'tkasing
3. Chek (rasm/fayl) yuboring
4. Admin tasdiqlaydi → Video avtomatik yuboriladi

### 💰 Hisobim
- Balans ko'rish
- To'ldirish → chek yuborish → admin tasdiqlash

### 📩 Adminga xabar
- Matn, rasm, stiker, ovozli xabar yuborish mumkin
- Admin javob yuborishi mumkin

---

## 📊 Statistika
- Rasm ko'rinishida chiqadi
- Har bir foydalanuvchi nomi, ID, qo'shilgan sana
- Jami, faol, bloklangan foydalanuvchilar
- Moliyaviy statistika

---

## 🔔 Yangi obunachi xabari
Har yangi foydalanuvchi qo'shilganda adminga:
- Ism
- ID
- Qo'shilgan sana/vaqt
- "Lichkaga o'tish" tugmasi

---

## 📝 Start xabar turlari
1. **Oddiy matn** - Faqat matn
2. **Rasm + matn** - Rasm va matn birgalikda
3. **Iqtibos xabar** - `<blockquote>` formatida
4. **Link xabar** - Havola ko'rinishida

---

## 🚫 Ban/Unban
- `/admin` → Ban/Unban
- Telegram ID kiriting
- Ban yoki Unban tanlang

---

## 💡 Muhim eslatmalar

- **BOT_TOKEN** va **ADMIN_IDS** ni albatta to'g'ri kiriting
- Kanalga obuna majburiy qilish uchun kanal ID ni kiriting
- Video kodlari KATTA HARFDA saqlanadi
- Ma'lumotlar bazasi `bot_database.db` faylida saqlanadi
