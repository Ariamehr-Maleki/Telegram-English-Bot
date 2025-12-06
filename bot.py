import os
import re
import sqlite3
from openai import OpenAI
from telegram import (
    ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove, Update
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, CallbackQueryHandler, ContextTypes
)
from telegram.error import TimedOut, BadRequest, NetworkError, RetryAfter
import asyncio
import logging

# تنظیم لاگ‌گیری
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === تنظیمات ===
TELEGRAM_TOKEN = "8334408510:AAGQIHCBIuX5_wJMtb_Juh_dmaqwGQsbeso"
OPENAI_API_KEY = "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"

client = OpenAI(api_key=OPENAI_API_KEY)

# === دیتابیس ===
DB_NAME = "quiz.db"
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS responses 
             (user_id INTEGER, section TEXT, q_num INTEGER, answer TEXT, score REAL)''')
c.execute('''CREATE TABLE IF NOT EXISTS contact_requests
             (user_id INTEGER, full_name TEXT, phone TEXT, score REAL)''')
conn.commit()

# === سوالات MCQ (10 تا) ===
MCQ_QUESTIONS = [
    {"q": "📌 کدام جمله صحیح است؟",
     "opts": ["A) She don't like coffee.", "B) She doesn't likes coffee.", "C) She doesn't like coffee.", "D) She not likes coffee."], 
     "key": "C"},

    {"q": "🤝 کدام کلمه جای خالی را درست کامل می‌کند؟\n\nI agree _____ your idea.",  
     "opts": ["A) in", "B) with", "C) on", "D) at"], 
     "key": "B"},

    {"q": "⏳ کدام جمله از زمان گذشته کامل (Past Perfect) استفاده می‌کند؟",
     "opts": ["A) By the time we arrived, the film had already started.", 
              "B) When we arrived, the film started.", 
              "C) We arrived and the film starts.", 
              "D) The film has started when we arrived."], 
     "key": "A"},
 
    {"q": "📚 شکل درست مقایسه‌ای کدام است؟", 
         "opts": ["A) More better", "B) Better", "C) Best", "D) The best"], 
     "key": "B"},

    {"q": "👩🏼‍🦱 آنا آخر هفته‌ها چه کاری انجام می‌دهد؟\n\n\"Anna moved to the city last year. She works at a bookstore and studies part-time. On weekends she volunteers at an animal shelter.\"",      "opts": ["A) She studies.", "B) She works at a bookstore.", "C) She volunteers at an animal shelter.", "D) She moved to the city."], 
     "key": "C"},

    {"q": "🪑 کدام حرف اضافه درست است؟\nThey were sitting _____ the table.", 
         "opts": ["A) in", "B) on", "C) at", "D) by"], 
     "key": "C"},

    {"q": "📅 کدام جمله برای بیان قرار ملاقات در آینده صحیح است؟",      "opts": ["A) I will meeting him tomorrow.", "B) I am meeting him tomorrow.", 
              "C) I meet him tomorrow.", "D) I met him tomorrow."], 
     "key": "B"},

    {"q": "🚗 Conditionals: If I _____ enough money, I would buy a new car.", 
     "opts": ["A) have", "B) had", "C) will have", "D) has"], 
     "key": "B"},

    {"q": "🍽️ Which sentence is passive voice?",   
       "opts": ["A) The chef cooked dinner.", "B) Dinner was cooked by the chef.", 
              "C) The chef is cooking dinner.", "D) The chef will cook dinner."], 
     "key": "B"},

    {"q": "🎓 Fill the blank: By next year she _____ (graduate) from university.",  
        "opts": ["A) graduates", "B) will graduate", "C) will have graduated", "D) had graduated"], 
     "key": "C"}
]

# اضافه کردن گزینه "جواب رو نمی‌دونم" به همه‌ی سوالات
for q in MCQ_QUESTIONS:
    q["opts"].append("E) جواب رو نمی‌دونم")


# === Short Answer ===
SHORT_QUESTIONS = [
    "🌟🔁 Provide a synonym for \"important\".",
    "🤔📝 Fill the blank: \"If I _____ you, I would apologize.\" (use one word)",
    "💫💬 Answer briefly: What do you usually do when you have free time? (2 or 3 short sentences)"
]

# === Translation ===
TRANSLATE_PERSIAN = [
    "🏋️‍♂️⏰ من معمولا هفته ای دوبار به باشگاه می روم",
    "🌤️🧺 من تا حالا به دبی نرفته ام"
]

# === Speaking ===
SPEAKING_PROMPTS = [
    "🗣️🎙️ Introduce yourself. Say your name, where you are from, what you do and how many siblings you have.",
    "🌅🌃 (1 minute) describe the things you did yesterday from morning to night."
]
SPEAK_SKIP_TEXT = "نمیتونم پاسخ بدم"

# === Listening ===
LISTENING_FILE_ID = "CQACAgQAAxkBAAIFqmkiLS4ZtKXWwXAHwmZlg-rYHyLeAAIuGAAC2_3IU_nGzsA8g7lZNgQ"

LISTENING_QUESTIONS = [
    {
        "q": "🛒🛍️ Why did she go to the market?", 
        "type": "mcq", 
        "opts": ["A) 🌸 To buy flowers", 
                 "B) 🥦 To get fresh vegetables for a dinner party", 
                 "C) 📚 To sell books", 
                 "D) 🤝 To meet Marco"], 
        "key": "B"
    },
    {
        "q": "🚫🧺 Which of these did she NOT buy?", 
        "type": "mcq", 
        "opts": ["A) 🍅 Tomatoes", 
                 "B) 🍯 Honey", 
                 "C) 🍞 Bread", 
                 "D) 🌿 Spinach"], 
        "key": "C"
    },
    {
        "q": "✔️❌ True or False: Susan signed up to volunteer for an elderly care program starting next month.", 
        "type": "tf", 
        "key": ["false"]
    }
]

# === سطح‌بندی ===
def get_level(total):
    if total <= 2: return "استارتر"
    elif total <= 5: return "مبتدی"
    elif total <= 9: return "پایین تر از متوسط"
    elif total <= 14: return "متوسط"
    elif total <= 18: return "بالاتر از متوسط"
    else: return "پیشرفته"

# === تابع کمکی برای ارسال با تلاش مجدد ===
async def send_with_retry(func, *args, max_retries=3, **kwargs):
    """تابع کمکی برای ارسال پیام با تلاش مجدد در صورت خطای timeout"""
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except (TimedOut, NetworkError) as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to send after {max_retries} attempts: {e}")
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
            logger.warning(f"Retry attempt {attempt + 1}/{max_retries}")
        except RetryAfter as e:
            wait_time = e.retry_after
            logger.warning(f"Rate limited, waiting {wait_time} seconds")
            await asyncio.sleep(wait_time)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

# === Error Handler ===
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handler برای مدیریت خطاها"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    if isinstance(context.error, TimedOut):
        try:
            if update and hasattr(update, 'message') and update.message:
                await update.message.reply_text(
                    "⚠️ اتصال به سرور کند است. لطفاً دوباره تلاش کنید."
                )
        except:
            pass
    elif isinstance(context.error, BadRequest):
        if "file identifier" in str(context.error).lower():
            logger.error("Invalid file ID - the audio file may have expired")
            try:
                if update and hasattr(update, 'message') and update.message:
                    await update.message.reply_text(
                        "⚠️ فایل صوتی در دسترس نیست. لطفاً از /start استفاده کنید."
                    )
            except:
                pass

# === استیت‌ها ===
INITIAL_CONTACT, MCQ, SHORT, TRANS, SPEAK, LISTEN = range(6)

# === استارت ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    # Clear old responses from previous quiz sessions
    c.execute("DELETE FROM responses WHERE user_id = ?", (user_id,))
    conn.commit()
    context.user_data.clear()
    context.user_data['index'] = 0
    
    await send_with_retry(
        update.message.reply_text,
        "سلام\n\nخوش آمدید\n\nلطفا نام و نام خانوادگی و شماره تلفن خود را ارسال کنید تا آزمون را شروع کنید"
    )
    return INITIAL_CONTACT

# === Initial Contact Collection ===
async def handle_initial_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    # Check if user clicked "شروع آزمون" button
    if text == "شروع آزمون":
        # Check if contact info was already collected
        if 'user_phone' in context.user_data and context.user_data['user_phone']:
            await send_with_retry(
                update.message.reply_text,
                "آزمون تعیین سطح زبان انگلیسی شروع شد!\n\nبخش اول: ۱۰ سوال چهارگزینه‌ای",
                reply_markup=ReplyKeyboardRemove()
            )
            return await send_mcq(update, context)
        else:
            await send_with_retry(
                update.message.reply_text,
                "لطفا ابتدا نام و شماره تلفن خود را ارسال کنید"
            )
            return INITIAL_CONTACT
    
    # Extract phone number - check for 09123456789 or +989123456789 format
    # Pattern matches: 09xxxxxxxxx (11 digits) or +989xxxxxxxxx (13 chars) or 989xxxxxxxxx (12 digits)
    phone_pattern = r'(\+?98)?9\d{9}|09\d{9}'
    phone_match = re.search(phone_pattern, text)
    
    if not phone_match:
        await send_with_retry(
            update.message.reply_text,
            "لطفا یک شماره موبایل معتبر وارد کنید"
        )
        return INITIAL_CONTACT
    
    # Extract and normalize phone number
    raw_phone = phone_match.group()
    # Remove all non-digits first
    phone_digits = re.sub(r'\D', '', raw_phone)
    
    # Normalize to 09123456789 format
    if phone_digits.startswith('989'):
        # +989123456789 or 989123456789 -> 09123456789
        phone = '0' + phone_digits[2:]
    elif phone_digits.startswith('09') and len(phone_digits) == 11:
        # Already in correct format
        phone = phone_digits
    elif phone_digits.startswith('9') and len(phone_digits) == 10:
        # 9123456789 -> 09123456789
        phone = '0' + phone_digits
    else:
        await send_with_retry(
            update.message.reply_text,
            "لطفا یک شماره موبایل معتبر وارد کنید"
        )
        return INITIAL_CONTACT
    
    # Final validation: should be exactly 11 digits starting with 09
    if len(phone) != 11 or not phone.startswith('09'):
        await send_with_retry(
            update.message.reply_text,
            "لطفا یک شماره موبایل معتبر وارد کنید"
        )
        return INITIAL_CONTACT
    
    # Extract name (everything except the phone number)
    name_part = text[:phone_match.start()] + text[phone_match.end():]
    name_part = name_part.strip(" ،,-:")
    
    if not name_part:
        name_part = update.message.from_user.full_name or "نامشخص"
    
    # Store contact info in user_data (will be saved to DB at the end)
    context.user_data['user_name'] = name_part
    context.user_data['user_phone'] = phone
    
    await send_with_retry(
        update.message.reply_text,
        "نام و شماره شما با موفقیت ثبت شد"
    )
    
    # Ask if ready to start with button
    keyboard = ReplyKeyboardMarkup([["شروع آزمون"]], one_time_keyboard=True, resize_keyboard=True)
    await send_with_retry(
        update.message.reply_text,
        "آماده شروع آزمون هستی؟",
        reply_markup=keyboard
    )
    return INITIAL_CONTACT

# === MCQ ===
async def send_mcq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['index']
    if idx >= len(MCQ_QUESTIONS):
        context.user_data['index'] = 0
        await send_with_retry(
            update.message.reply_text,
            "بخش جواب کوتاه شروع شد.",
            reply_markup=ReplyKeyboardRemove()
        )
        return await send_short(update, context)
    q = MCQ_QUESTIONS[idx]
    keyboard = ReplyKeyboardMarkup([[opt] for opt in q['opts']], one_time_keyboard=True, resize_keyboard=True)
    await send_with_retry(
        update.message.reply_text,
        f"سوال {idx+1}/10:\n\n{q['q']}",
        reply_markup=keyboard
    )
    return MCQ

async def handle_mcq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    idx = context.user_data['index']
    ans = update.message.text.strip()[0].upper()
    key = MCQ_QUESTIONS[idx]['key']
    score = 1 if ans == key else 0
    c.execute("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", (user_id, 'mcq', idx+1, ans, score))
    conn.commit()
    context.user_data['index'] += 1
    return await send_mcq(update, context)

# === Short Answer ===
async def send_short(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['index']
    if idx >= len(SHORT_QUESTIONS):
        context.user_data['index'] = 0
        await send_with_retry(update.message.reply_text, "بخش ترجمه شروع شد.")
        return await send_translate(update, context)
    await send_with_retry(
        update.message.reply_text,
        f"سوال {idx+1}/3 (جواب کوتاه):\n\n{SHORT_QUESTIONS[idx]}"
    )
    return SHORT

async def handle_short(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    idx = context.user_data['index']
    ans = update.message.text.strip().lower()

    prompt = f"Question: {SHORT_QUESTIONS[idx]}\nUser answer: {ans}\nIs it correct and natural? Score 0 or 1.\nReturn only: SCORE: 0 or 1"
    
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        score = 1 if "1" in resp.choices[0].message.content else 0
    except:
        score = 0

    c.execute("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", (user_id, 'short', idx+1, ans, score))
    conn.commit()
    context.user_data['index'] += 1
    return await send_short(update, context)

# === Translation ===
async def send_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['index']
    if idx >= len(TRANSLATE_PERSIAN):
        context.user_data['index'] = 0
        await send_with_retry(update.message.reply_text, "بخش اسپیکینگ شروع شد. لطفاً ویس بفرستید.")
        return await send_speaking(update, context)
    await send_with_retry(
        update.message.reply_text,
        f"سوال {idx+1}/2 (ترجمه به انگلیسی):\n\n{TRANSLATE_PERSIAN[idx]}"
    )
    return TRANS

async def handle_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    idx = context.user_data['index']
    ans = update.message.text.strip()

    prompt = f"Original: {TRANSLATE_PERSIAN[idx]}\nTranslation: {ans}\nIs it natural and accurate? Score 0 or 1.\nReturn only: SCORE: 0 or 1"
    
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        score = 1 if "1" in resp.choices[0].message.content else 0
    except:
        score = 0

    c.execute("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", (user_id, 'trans', idx+1, ans, score))
    conn.commit()
    context.user_data['index'] += 1
    return await send_translate(update, context)

# === Speaking ===
async def send_speaking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['index']
    if idx >= len(SPEAKING_PROMPTS):
        context.user_data['index'] = 0
        await send_with_retry(update.message.reply_text, "بخش لیسنینگ شروع شد. صوت را گوش کنید.")
        return await send_listening(update, context)
    keyboard = ReplyKeyboardMarkup([[SPEAK_SKIP_TEXT]], resize_keyboard=True)
    await send_with_retry(
        update.message.reply_text,
        f"سوال {idx+1} (ویس بفرستید یا \"{SPEAK_SKIP_TEXT}\" را بزنید):\n\n{SPEAKING_PROMPTS[idx]}",
        reply_markup=keyboard
    )
    return SPEAK

async def handle_speaking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    idx = context.user_data['index']
    if not update.message.voice:
        await send_with_retry(update.message.reply_text, "لطفاً ویس بفرستید.")
        return SPEAK

    voice = update.message.voice
    file = await voice.get_file()
    await file.download_to_drive("temp.ogg")

    try:
        with open("temp.ogg", "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            ).text
    except Exception as e:
        logger.error(f"Error in voice transcription: {e}")
        await send_with_retry(
            update.message.reply_text,
            f"خطا در تبدیل صدا: {e}\nلطفاً دوباره ویس بفرستید."
        )
        if os.path.exists("temp.ogg"):
            os.remove("temp.ogg")
        return SPEAK

    prompt = f"""
    Prompt: {SPEAKING_PROMPTS[idx]}
    Transcript: {transcript}
    Score 0-1 based on:
    - Time (appropriate length)
    - Topic (on-topic)
    - Grammar
    - Vocabulary
    - Clarity
    Return only: SCORE: 0 or 1
    """
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        score = 1 if "1" in resp.choices[0].message.content else 0
    except:
        score = 0

    c.execute("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", (user_id, 'speak', idx+1, transcript, score))
    conn.commit()
    os.remove("temp.ogg")
    context.user_data['index'] += 1
    return await send_speaking(update, context)

async def handle_speaking_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    idx = context.user_data['index']

    if update.message.text.strip() != SPEAK_SKIP_TEXT:
        await send_with_retry(
            update.message.reply_text,
            f"برای این بخش ویس بفرستید یا دکمه \"{SPEAK_SKIP_TEXT}\" را فشار دهید."
        )
        return SPEAK

    c.execute(
        "INSERT INTO responses VALUES (?, ?, ?, ?, ?)",
        (user_id, 'speak', idx+1, 'skipped', 0)
    )
    conn.commit()
    context.user_data['index'] += 1
    return await send_speaking(update, context)

# === Listening ===
async def send_listening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['index']
    if idx == 0:
        try:
            await send_with_retry(
                update.message.reply_audio,
                audio=LISTENING_FILE_ID,
                caption="صوت را گوش کنید، سپس به سوالات جواب دهید."
            )
        except BadRequest as e:
            logger.error(f"Invalid audio file ID: {e}")
            await send_with_retry(
                update.message.reply_text,
                "⚠️ فایل صوتی در دسترس نیست. لطفاً به سوالات پاسخ دهید.\n\n"
                "برای گوش دادن به صوت، باید فایل صوتی معتبری ارسال شود."
            )
    
    if idx >= len(LISTENING_QUESTIONS):
        return await end_quiz(update, context)

    q = LISTENING_QUESTIONS[idx]
    if q['type'] == 'mcq':
        keyboard = ReplyKeyboardMarkup([[opt] for opt in q['opts']], one_time_keyboard=True, resize_keyboard=True)
        await send_with_retry(
            update.message.reply_text,
            f"سوال {idx+1}/3:\n\n{q['q']}",
            reply_markup=keyboard
        )
    elif q['type'] == 'tf':
        keyboard = ReplyKeyboardMarkup([["True✅"], ["False❌"]], one_time_keyboard=True, resize_keyboard=True)
        await send_with_retry(
            update.message.reply_text,
            f"سوال {idx+1}/3:\n\n{q['q']}",
            reply_markup=keyboard
        )
    else:
        await send_with_retry(
            update.message.reply_text,
            f"سوال {idx+1}/3:\n\n{q['q']}",
            reply_markup=ReplyKeyboardRemove()
        )
    return LISTEN


async def handle_listening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    idx = context.user_data['index']
    ans = update.message.text.strip().lower()
    q = LISTENING_QUESTIONS[idx]
    score = 0

    if q['type'] == 'mcq':
        ans = ans[0].upper()
        score = 1 if ans == q['key'] else 0
    elif q['type'] in ['short', 'tf']:
        if isinstance(q['key'], list):
            score = 1 if any(k in ans for k in q['key']) else 0
        else:
            score = 1 if q['key'] in ans else 0

    c.execute("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", (user_id, 'listen', idx+1, ans, score))
    conn.commit()
    context.user_data['index'] += 1
    return await send_listening(update, context)


# === پایان ===
async def end_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    c.execute("SELECT SUM(score) FROM responses WHERE user_id = ?", (user_id,))
    total = c.fetchone()[0] or 0
    level = get_level(total)
    context.user_data['final_score'] = total
    context.user_data['level_label'] = level

    await send_with_retry(
        update.message.reply_text,
        f"نمره کل: {total}/20\nسطح شما: {level}"
    )

    # Save contact info to database
    user_name = context.user_data.get('user_name', 'نامشخص')
    user_phone = context.user_data.get('user_phone', '')
    
    if user_phone:
        c.execute(
            "INSERT OR REPLACE INTO contact_requests VALUES (?, ?, ?, ?)",
            (user_id, user_name, user_phone, total)
        )
        conn.commit()

    await send_with_retry(
        update.message.reply_text,
        "آزمون شما با موفقیت ثبت شد"
    )

    await send_with_retry(
        update.message.reply_text,
        "به زودی کارشناسان خوش زبان با شما تماس خواهند گرفت."
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# === دکمه‌ها ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == 'courses':
        c.execute("SELECT AVG(score) FROM responses WHERE user_id=? AND section=?", (user_id, 'speak'))
        speak_score = c.fetchone()[0] or 0
        c.execute("SELECT SUM(score) FROM responses WHERE user_id=?", (user_id,))
        total = c.fetchone()[0] or 0
        if speak_score < 0.5:
            text = "دوره پیشنهادی: مکالمه فشرده (Speaking Focus)"
        elif total < 15:
            text = "دوره پیشنهادی: گرامر و واژگان A2-B1"
        else:
            text = "دوره پیشنهادی: پیشرفته C1 (Writing & Fluency)"
        try:
            await query.edit_message_text(text)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            try:
                await query.message.reply_text(text)
            except Exception as e2:
                logger.error(f"Error sending message: {e2}")
    elif query.data == 'consult':
        try:
            await query.edit_message_text("لطفاً نام، شماره تماس و بهترین زمان را بفرستید.")
        except Exception as e:
            logger.error(f"Error editing message: {e}")

# === اجرا ===
app = Application.builder().token(TELEGRAM_TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        INITIAL_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_initial_contact)],
        MCQ: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mcq)],
        SHORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_short)],
        TRANS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_translate)],
        SPEAK: [
            MessageHandler(filters.VOICE, handle_speaking),
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_speaking_skip)
        ],
        LISTEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_listening)],
    },
    fallbacks=[],
    per_user=True
)

app.add_handler(conv)
app.add_handler(CallbackQueryHandler(button_handler))
app.add_error_handler(error_handler)

if __name__ == '__main__':
    print("The Bot is running... :)")
    app.run_polling()
