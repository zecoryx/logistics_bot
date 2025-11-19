import logging
import os
import sqlite3
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import requests
from datetime import datetime

# .env faylni yuklash
load_dotenv()

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Holatlar
(LANG_SELECT, PHONE, PASSWORD, MAIN_MENU, 
 CHANGE_PHONE, APPEAL_TITLE, APPEAL_DESC) = range(7)

# Sozlamalar .env dan
BACKEND_URL = os.getenv("BACKEND_URL")
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Database fayli
DB_FILE = "users.db"

# Database yaratish
def init_db():
    """Database va jadvalni yaratish"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            phone TEXT NOT NULL,
            full_name TEXT,
            role TEXT,
            balans TEXT,
            access_token TEXT,
            refresh_token TEXT,
            lang TEXT DEFAULT 'uz',
            logged_in BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

def get_user(user_id):
    """Foydalanuvchini olish"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'phone': user[1],
            'full_name': user[2],
            'role': user[3],
            'balans': user[4],
            'access_token': user[5],
            'refresh_token': user[6],
            'lang': user[7],
            'logged_in': bool(user[8])
        }
    return None

def save_user(user_data):
    """Foydalanuvchini saqlash/yangilash"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, phone, full_name, role, balans, access_token, refresh_token, lang, logged_in, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (
        user_data['user_id'],
        user_data['phone'],
        user_data['full_name'],
        user_data['role'],
        user_data['balans'],
        user_data['access_token'],
        user_data['refresh_token'],
        user_data['lang'],
        user_data['logged_in']
    ))
    
    conn.commit()
    conn.close()

def logout_user(user_id):
    """Foydalanuvchini logout qilish"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET logged_in = FALSE WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# Database ni ishga tushirish
init_db()

# Tarjimalar
TRANSLATIONS = {
    'uz': {
        'welcome': "👋 Xush kelibsiz!\n\nIltimos, tilni tanlang:",
        'send_phone': "📱 Ilovadan ro'yhatdan o'tgan telefon raqamingizni kiriting\n\n💡 Masalan: +99890XXXXXXX",
        'send_password': "🔐 Ilovadan ro'yhatdan o'tgan Parolingizni kiriting:",
        'login_success': "✅ Xush kelibsiz!\n\nSiz tizimga muvaffaqiyatli kirdingiz.",
        'login_failed': "❌ Xatolik!\n\nTelefon raqam yoki parol noto'g'ri.\n\nIltimos, qaytadan urinib ko'ring.",
        'connection_error': "⚠️ Serverga ulanishda xatolik!\n\nIltimos, keyinroq qayta urinib ko'ring.",
        'main_menu': "📋 Asosiy menyu\n\nKerakli bo'limni tanlang:",
        'profile': "👤 Profil",
        'change_phone': "📱 Raqamni o'zgartirish",
        'contact_admin': "📨 Adminga murojaat",
        'settings': "⚙️ Sozlamalar",
        'back': "🔙 Orqaga",
        'enter_new_phone': "📱 Yangi telefon raqamingizni kiriting:\n\n💡 Masalan: +99890XXXXXXX",
        'phone_updated': "✅ Raqam yangilandi!\n\nYangi raqamingiz muvaffaqiyatli saqlandi.",
        'enter_appeal_title': "📝 Murojaat sarlavhasini kiriting:\n\n💡 Qisqa va aniq yozing",
        'enter_appeal_desc': "📄 Murojaat matnini kiriting:\n\n💡 Batafsil yozing",
        'appeal_sent': "✅ Yuborildi!\n\nMurojaatingiz adminga yetkazildi.\nTez orada javob beramiz.",
        'cancel': "❌ Bekor qilish",
        'choose_lang': "🌐 Tilni tanlang",
        'logout': "🚪 Chiqish",
        'uz': "🇺🇿 O'zbekcha",
        'ru': "🇷🇺 Русский",
        'en': "🇬🇧 English",
        'user_info': "👤 Profil ma'lumotlari\n\n📱 Telefon: {}\n🌐 Til: {}\n📅 Sana: {}",
        'invalid_phone': "❌ Noto'g'ri format!\n\nIltimos, to'g'ri telefon raqam kiriting.\nMasalan: +99890XXXXXXX",
        'welcome_back': "👋 Xush kelibsiz, {}!\n\nSiz allaqachon tizimga kirgansiz.",
        'logout_success': "✅ Siz tizimdan muvaffaqiyatli chiqdingiz.\n\nQaytadan kirish uchun /start ni bosing.",
        'language_changed': "Til muvaffaqiyatli o'zgartirildi!"
    },
    'ru': {
        'welcome': "👋 Добро пожаловать!\n\nПожалуйста, выберите язык:",
        'send_phone': "📱 Введите ваш номер телефона\n\n💡 Например: +99890XXXXXXX",
        'send_password': "🔐 Введите ваш пароль:",
        'login_success': "✅ Добро пожаловать!\n\nВы успешно вошли в систему.",
        'login_failed': "❌ Ошибка!\n\nНеверный номер телефона или пароль.\n\nПожалуйста, попробуйте снова.",
        'connection_error': "⚠️ Ошибка подключения к серверу!\n\nПожалуйста, попробуйте позже.",
        'main_menu': "📋 Главное меню\n\nВыберите нужный раздел:",
        'profile': "👤 Профиль",
        'change_phone': "📱 Изменить номер",
        'contact_admin': "📨 Связаться с админом",
        'settings': "⚙️ Настройки",
        'back': "🔙 Назад",
        'enter_new_phone': "📱 Введите новый номер телефона:\n\n💡 Например: +99890XXXXXXX",
        'phone_updated': "✅ Номер обновлен!\n\nВаш новый номер успешно сохранен.",
        'enter_appeal_title': "📝 Введите заголовок обращения:\n\n💡 Кратко и ясно",
        'enter_appeal_desc': "📄 Введите текст обращения:\n\n💡 Подробно опишите вашу проблему",
        'appeal_sent': "✅ Отправлено!\n\nВаше обращение доставлено админу.\nМы ответим в ближайшее время.",
        'cancel': "❌ Отмена",
        'choose_lang': "🌐 Выберите язык",
        'logout': "🚪 Выйти",
        'uz': "🇺🇿 O'zbekcha",
        'ru': "🇷🇺 Русский",
        'en': "🇬🇧 English",
        'user_info': "👤 Информация профиля\n\n📱 Телефон: {}\n🌐 Язык: {}\n📅 Дата: {}",
        'invalid_phone': "❌ Неверный формат!\n\nПожалуйста, введите правильный номер.\nНапример: +99890XXXXXXX",
        'welcome_back': "👋 Добро пожаловать, {}!\n\nВы уже вошли в систему.",
        'logout_success': "✅ Вы успешно вышли из системы.\n\nНажмите /start чтобы войти снова.",
        'language_changed': "Язык успешно изменен!"
    },
    'en': {
        'welcome': "👋 Welcome!\n\nPlease choose your language:",
        'send_phone': "📱 Enter your phone number\n\n💡 Example: +99890XXXXXXX",
        'send_password': "🔐 Enter your password:",
        'login_success': "✅ Welcome!\n\nYou have successfully logged in.",
        'login_failed': "❌ Error!\n\nInvalid phone number or password.\n\nPlease try again.",
        'connection_error': "⚠️ Server connection error!\n\nPlease try again later.",
        'main_menu': "📋 Main Menu\n\nSelect a section:",
        'profile': "👤 Profile",
        'change_phone': "📱 Change phone",
        'contact_admin': "📨 Contact admin",
        'settings': "⚙️ Settings",
        'back': "🔙 Back",
        'enter_new_phone': "📱 Enter new phone number:\n\n💡 Example: +99890XXXXXXX",
        'phone_updated': "✅ Number updated!\n\nYour new number has been saved.",
        'enter_appeal_title': "📝 Enter appeal title:\n\n💡 Short and clear",
        'enter_appeal_desc': "📄 Enter appeal text:\n\n💡 Describe in detail",
        'appeal_sent': "✅ Sent!\n\nYour appeal has been delivered to admin.\nWe'll respond soon.",
        'cancel': "❌ Cancel",
        'choose_lang': "🌐 Choose language",
        'logout': "🚪 Logout",
        'uz': "🇺🇿 O'zbekcha",
        'ru': "🇷🇺 Русский",
        'en': "🇬🇧 English",
        'user_info': "👤 Profile Information\n\n📱 Phone: {}\n🌐 Language: {}\n📅 Date: {}",
        'invalid_phone': "❌ Invalid format!\n\nPlease enter correct phone number.\nExample: +99890XXXXXXX",
        'welcome_back': "👋 Welcome back, {}!\n\nYou're already logged in.",
        'logout_success': "✅ You have successfully logged out.\n\nPress /start to login again.",
        'language_changed': "Language successfully changed!"
    }
}

def get_text(lang, key):
    """Tarjima olish"""
    return TRANSLATIONS.get(lang, TRANSLATIONS['uz']).get(key, key)

def get_lang_keyboard():
    """Modern til tanlash klaviaturasi"""
    keyboard = [
        [KeyboardButton("🇺🇿 O'zbekcha")],
        [KeyboardButton("🇷🇺 Русский")],
        [KeyboardButton("🇬🇧 English")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_main_menu_keyboard(lang):
    """Modern asosiy menyu"""
    keyboard = [
        [KeyboardButton(get_text(lang, 'profile')), KeyboardButton(get_text(lang, 'contact_admin'))],
        [KeyboardButton(get_text(lang, 'change_phone'))],
        [KeyboardButton(get_text(lang, 'settings')), KeyboardButton(get_text(lang, 'logout'))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard(lang):
    """Orqaga tugmasi"""
    keyboard = [[KeyboardButton(get_text(lang, 'back'))]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def validate_phone(phone):
    """Telefon raqam formatini tekshirish"""
    phone = phone.strip()
    if phone.startswith('+998') and len(phone) == 13:
        return True
    if phone.startswith('998') and len(phone) == 12:
        return True
    if phone.startswith('8') and len(phone) == 11:
        return True
    return False

def get_profile_message(user_data, lang):
    """Profil xabarini tayyorlash"""
    full_name = user_data.get('full_name', 'User')
    phone = user_data.get('phone', 'N/A')
    balans = user_data.get('balans', '0')
    role = user_data.get('role', 'user')
    lang_name = get_text(lang, lang)
    date_now = datetime.now().strftime("%d.%m.%Y")
    
    profile_msg = f"""
👤 Profil ma'lumotlari

📝 Ism: {full_name}
📱 Telefon: {phone}
💰 Balans: {balans} so'm
👔 Rol: {role}
🌐 Til: {lang_name}
📅 Sana: {date_now}
🆔 User ID: {user_data.get('user_id', 'N/A')}
    """
    return profile_msg.strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komandasi - Database dan foydalanuvchi ma'lumotlarini tekshiradi"""
    user = update.effective_user
    logger.info(f"User {user.id} started bot")

    # Database dan foydalanuvchini tekshiramiz
    db_user = get_user(user.id)
    
    if db_user and db_user.get('logged_in'):
        # Foydalanuvchi allaqachon login qilgan
        lang = db_user.get('lang', 'uz')
        
        # Context user_data ni to'ldirish
        context.user_data.update(db_user)
        
        # Profil ma'lumotlarini tayyorlash
        profile_msg = get_profile_message(db_user, lang)
        
        welcome_msg = f"{get_text(lang, 'welcome_back').format(user.first_name)}\n\n{profile_msg}"
        
        await update.message.reply_text(
            welcome_msg,
            reply_markup=get_main_menu_keyboard(lang)
        )
        return MAIN_MENU

    # Yangi foydalanuvchi yoki logout qilgan
    context.user_data.clear()  # Eski ma'lumotlarni tozalash
    
    await update.message.reply_text(
        f"👋 Assalomu aleykum, {user.first_name}!\n\n" + TRANSLATIONS['uz']['welcome'],
        reply_markup=get_lang_keyboard()
    )
    return LANG_SELECT

async def lang_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Til tanlash (faqat yangi foydalanuvchilar uchun)"""
    text = update.message.text
    
    if "O'zbekcha" in text or "🇺🇿" in text:
        context.user_data['lang'] = 'uz'
    elif "Русский" in text or "🇷🇺" in text:
        context.user_data['lang'] = 'ru'
    elif "English" in text or "🇬🇧" in text:
        context.user_data['lang'] = 'en'
    else:
        context.user_data['lang'] = 'uz'
    
    lang = context.user_data['lang']
    logger.info(f"User {update.effective_user.id} selected language: {lang}")
    
    await update.message.reply_text(
        get_text(lang, 'send_phone'),
        reply_markup=ReplyKeyboardRemove()
    )
    return PHONE

async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telefon raqam qabul qilish va validatsiya"""
    phone = update.message.text.strip()
    lang = context.user_data.get('lang', 'uz')
    
    # Telefon raqam formatini tekshirish
    if not validate_phone(phone):
        await update.message.reply_text(get_text(lang, 'invalid_phone'))
        return PHONE
    
    # Telefon raqamni normalize qilish
    if not phone.startswith('+'):
        if phone.startswith('998'):
            phone = '+' + phone
        elif phone.startswith('8'):
            phone = '+998' + phone[1:]
        else:
            phone = '+998' + phone
    
    context.user_data['phone'] = phone
    logger.info(f"User {update.effective_user.id} entered phone: {phone}")
    
    await update.message.reply_text(get_text(lang, 'send_password'))
    return PASSWORD

async def password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parol tekshirish va backend bilan bog'lanish"""
    password = update.message.text
    phone = context.user_data.get('phone')
    lang = context.user_data.get('lang', 'uz')
    user_id = update.effective_user.id
    
    logger.info(f"User {user_id} attempting login with phone: {phone}")
    
    # Backend ga so'rov yuborish
    try:
        login_url = f"{BACKEND_URL}/auth/login"
        payload = {
            'phoneNumber': phone,
            'password': password
        }
        
        logger.info(f"Sending request to: {login_url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(
            login_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('success') and result.get('code') == 200:
                data = result.get('data', {})
                
                # User ma'lumotlarini saqlash
                user_data = {
                    'user_id': user_id,
                    'phone': data.get('phoneNumber', phone),
                    'full_name': data.get('fullName', 'User'),
                    'role': data.get('role', 'user'),
                    'balans': data.get('balans', '0'),
                    'access_token': data.get('accessToken'),
                    'refresh_token': data.get('refreshToken'),
                    'lang': lang,
                    'logged_in': True
                }
                
                # Database ga saqlash
                save_user(user_data)
                
                # Context user_data ni yangilash
                context.user_data.update(user_data)
                
                logger.info(f"User {user_id} logged in successfully as {data.get('fullName')}")
                
                # Profil ma'lumotlarini tayyorlash
                profile_msg = get_profile_message(user_data, lang)
                
                # Muvaffaqiyatli login xabari
                welcome_msg = f"✅ {get_text(lang, 'login_success')}\n\n{profile_msg}"
                
                await update.message.reply_text(
                    welcome_msg,
                    reply_markup=get_main_menu_keyboard(lang)
                )
                return MAIN_MENU
            else:
                logger.warning(f"Login failed for user {user_id}: {result.get('message')}")
                await update.message.reply_text(
                    get_text(lang, 'login_failed'),
                    reply_markup=get_lang_keyboard()
                )
                return LANG_SELECT
        else:
            logger.warning(f"Login failed for user {user_id}: HTTP {response.status_code}")
            await update.message.reply_text(
                get_text(lang, 'login_failed'),
                reply_markup=get_lang_keyboard()
            )
            return LANG_SELECT
            
    except Exception as e:
        logger.error(f"Login error for user {user_id}: {str(e)}")
        await update.message.reply_text(get_text(lang, 'connection_error'))
        return LANG_SELECT

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy menyu handler"""
    text = update.message.text
    user_id = update.effective_user.id
    lang = context.user_data.get('lang', 'uz')
    
    # Database dan yangi ma'lumotlarni olish
    db_user = get_user(user_id)
    if db_user:
        context.user_data.update(db_user)
        lang = db_user.get('lang', lang)  # Yangi tilni olish
    
    if get_text(lang, 'profile') in text or "👤" in text:
        profile_msg = get_profile_message(context.user_data, lang)
        
        await update.message.reply_text(
            profile_msg,
            reply_markup=get_main_menu_keyboard(lang)
        )
        return MAIN_MENU
    
    elif get_text(lang, 'change_phone') in text or "📱" in text:
        await update.message.reply_text(
            get_text(lang, 'enter_new_phone'),
            reply_markup=get_back_keyboard(lang)
        )
        return CHANGE_PHONE
    
    elif get_text(lang, 'contact_admin') in text or "📨" in text:
        await update.message.reply_text(
            get_text(lang, 'enter_appeal_title'),
            reply_markup=get_back_keyboard(lang)
        )
        return APPEAL_TITLE
    
    elif get_text(lang, 'settings') in text or "⚙️" in text:
        # SOZLAMALAR: Faqat til tanlash menyusini ko'rsatamiz
        await update.message.reply_text(
            get_text(lang, 'choose_lang'),
            reply_markup=get_lang_keyboard()
        )
        return MAIN_MENU  # ⚠️ MUHIM: MAIN_MENU ni saqlaymiz
    
    elif get_text(lang, 'logout') in text or "🚪" in text:
        # Logout qilish
        logout_user(user_id)
        context.user_data.clear()
        
        await update.message.reply_text(
            get_text(lang, 'logout_success'),
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    # Agar til tanlash tugmalaridan birini bossa (sozlamalar ichida)
    elif any(lang_text in text for lang_text in ["O'zbekcha", "Русский", "English", "🇺🇿", "🇷🇺", "🇬🇧"]):
        return await language_change_handler(update, context)
    
    return MAIN_MENU

async def language_change_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Til o'zgartirish (faqat login qilgan foydalanuvchilar uchun)"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Database dan foydalanuvchini tekshiramiz
    db_user = get_user(user_id)
    if not db_user or not db_user.get('logged_in'):
        # Agar login qilmagan bo'lsa, boshidan boshlaymiz
        await update.message.reply_text(
            TRANSLATIONS['uz']['welcome'],
            reply_markup=get_lang_keyboard()
        )
        return LANG_SELECT
    
    # Yangi tilni tanlash
    if "O'zbekcha" in text or "🇺🇿" in text:
        new_lang = 'uz'
    elif "Русский" in text or "🇷🇺" in text:
        new_lang = 'ru'
    elif "English" in text or "🇬🇧" in text:
        new_lang = 'en'
    else:
        new_lang = 'uz'
    
    # Database yangilash
    db_user['lang'] = new_lang
    save_user(db_user)
    context.user_data['lang'] = new_lang
    
    logger.info(f"User {user_id} changed language to: {new_lang}")
    
    # Asosiy menyuga qaytish
    await update.message.reply_text(
        f"✅ {get_text(new_lang, 'language_changed')}\n\n" +
        get_text(new_lang, 'main_menu'),
        reply_markup=get_main_menu_keyboard(new_lang)
    )
    return MAIN_MENU

async def change_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Raqamni o'zgartirish"""
    text = update.message.text
    user_id = update.effective_user.id
    lang = context.user_data.get('lang', 'uz')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'main_menu'),
            reply_markup=get_main_menu_keyboard(lang)
        )
        return MAIN_MENU
    
    # Yangi raqamni validatsiya qilish
    if not validate_phone(text):
        await update.message.reply_text(
            get_text(lang, 'invalid_phone'),
            reply_markup=get_back_keyboard(lang)
        )
        return CHANGE_PHONE
    
    # Normalize qilish
    phone = text.strip()
    if not phone.startswith('+'):
        if phone.startswith('998'):
            phone = '+' + phone
        elif phone.startswith('8'):
            phone = '+998' + phone[1:]
        else:
            phone = '+998' + phone
    
    # Database yangilash
    db_user = get_user(user_id)
    if db_user:
        db_user['phone'] = phone
        save_user(db_user)
        context.user_data['phone'] = phone
    
    logger.info(f"User {user_id} changed phone to: {phone}")
    
    await update.message.reply_text(
        get_text(lang, 'phone_updated'),
        reply_markup=get_main_menu_keyboard(lang)
    )
    return MAIN_MENU

async def appeal_title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Murojaat sarlavhasi"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'main_menu'),
            reply_markup=get_main_menu_keyboard(lang)
        )
        return MAIN_MENU
    
    context.user_data['appeal_title'] = text
    await update.message.reply_text(
        get_text(lang, 'enter_appeal_desc'),
        reply_markup=get_back_keyboard(lang)
    )
    return APPEAL_DESC

async def appeal_desc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Murojaat tavsifi va admin guruhga yuborish"""
    text = update.message.text
    user_id = update.effective_user.id
    lang = context.user_data.get('lang', 'uz')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'main_menu'),
            reply_markup=get_main_menu_keyboard(lang)
        )
        return MAIN_MENU
    
    # Database dan yangi ma'lumotlarni olish
    db_user = get_user(user_id)
    if db_user:
        context.user_data.update(db_user)
    
    title = context.user_data.get('appeal_title', 'N/A')
    phone = context.user_data.get('phone', 'N/A')
    full_name = context.user_data.get('full_name', 'User')
    user = update.effective_user
    date_now = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    # Admin guruhga xabar
    message = f"""
╔══════════════════════════╗
   🆕 YANGI MUROJAAT
╚══════════════════════════╝

👤 Ism: {full_name}
🆔 User ID: {user.id}
📱 Telefon: {phone}
🌐 Username: @{user.username if user.username else 'Yo\'q'}

━━━━━━━━━━━━━━━━━━━━━━━━

📝 Sarlavha:
{title}

📄 Tavsif:
{text}

━━━━━━━━━━━━━━━━━━━━━━━━
📅 Sana: {date_now}
    """
    
    try:
        group_id = int(ADMIN_GROUP_ID)
        await context.bot.send_message(chat_id=group_id, text=message, parse_mode='HTML')
        logger.info(f"✅ Appeal sent to admin group {group_id} from user {user.id}")
        
        await update.message.reply_text(
            get_text(lang, 'appeal_sent'),
            reply_markup=get_main_menu_keyboard(lang)
        )
    except Exception as e:
        logger.error(f"❌ Failed to send to admin group: {e}")
        await update.message.reply_text(
            f"⚠️ Xatolik: {str(e)}\n\nIltimos botni guruhga admin qiling!",
            reply_markup=get_main_menu_keyboard(lang)
        )
    
    return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bekor qilish"""
    lang = context.user_data.get('lang', 'uz')
    await update.message.reply_text(
        get_text(lang, 'cancel'),
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Logout komandasi"""
    user_id = update.effective_user.id
    logout_user(user_id)
    context.user_data.clear()
    
    await update.message.reply_text(
        "✅ Siz tizimdan muvaffaqiyatli chiqdingiz.\n\nQaytadan kirish uchun /start ni bosing.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

def main():
    """Botni ishga tushirish"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylni tekshiring!")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANG_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lang_select)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_handler)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
            CHANGE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_phone_handler)],
            APPEAL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, appeal_title_handler)],
            APPEAL_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, appeal_desc_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('logout', logout_command)],
    )
    
    application.add_handler(conv_handler)
    
    logger.info("✅ Bot muvaffaqiyatli ishga tushdi!")
    logger.info(f"📡 Backend URL: {BACKEND_URL}")
    logger.info(f"📨 Admin Group ID: {ADMIN_GROUP_ID}")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()