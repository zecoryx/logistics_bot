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
(LANG_SELECT, MAIN_CHOICE, GET_CODE_MENU, CODE_PHONE, CODE_VERIFY, MAIN_MENU, 
 CHANGE_PHONE, APPEAL_TITLE, APPEAL_DESC,
 FORGOT_PASSWORD_CODE, FORGOT_PASSWORD_NEW_PASSWORD,
 REGISTER_DATA, LOGIN_PASSWORD) = range(13)

# Sozlamalar .env dan
BACKEND_URL = os.getenv("BACKEND_URL")
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Helper funksiya: Response'ni xavfsiz parse qilish
def safe_json_parse(response):
    """Response'ni xavfsiz JSON formatiga o'tkazish"""
    try:
        if response.text:
            # Agar HTML yoki boshqa format bo'lsa
            if response.text.strip().startswith('<'):
                return None
            return response.json()
    except Exception as e:
        logger.error(f"JSON parse error: {e}, Response: {response.text[:200]}")
        return None
    return None

# BACKEND_URL ni to'g'ri formatlash
def get_backend_url(endpoint):
    """Backend URL ni to'g'ri formatlash"""
    if not BACKEND_URL:
        return None
    
    # BACKEND_URL ni tozalash
    base_url = BACKEND_URL.strip().rstrip('/')
    
    # URL formatini tekshirish va tuzatish
    # Agar https:/ yoki http:/ bo'lsa (bir /), tuzatish
    if base_url.startswith('https:/') and not base_url.startswith('https://'):
        base_url = base_url.replace('https:/', 'https://', 1)
    elif base_url.startswith('http:/') and not base_url.startswith('http://'):
        base_url = base_url.replace('http:/', 'http://', 1)
    elif not base_url.startswith('http://') and not base_url.startswith('https://'):
        # Agar protocol yo'q bo'lsa, http:// qo'shamiz
        base_url = 'http://' + base_url
    
    # Agar endpoint allaqachon / bilan boshlansa, olib tashlash
    if endpoint.startswith('/'):
        endpoint = endpoint[1:]
    
    # Agar base_url da /api bo'lsa, qo'shmaslik
    if base_url.endswith('/api'):
        return f"{base_url}/{endpoint}"
    elif '/api/' in base_url:
        return f"{base_url}/{endpoint}"
    else:
        # Agar /api yo'q bo'lsa, qo'shamiz
        if endpoint.startswith('api/'):
            return f"{base_url}/{endpoint}"
        else:
            return f"{base_url}/api/{endpoint}"

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
        'send_phone': "📱 Telefon raqamingizni yuboring:",
        'send_password': "🔐 Parolingizni kiriting:",
        'login_success': "✅ Xush kelibsiz!\n\nSiz tizimga muvaffaqiyatli kirdingiz.",
        'login_failed': "❌ Xatolik!\n\nTelefon raqam yoki parol noto'g'ri.\n\nIltimos, qaytadan urinib ko'ring.",
        'connection_error': "⚠️ Serverga ulanishda xatolik!\n\nIltimos, keyinroq qayta urinib ko'ring.",
        'main_menu': "📋 Asosiy menyu\n\nKerakli bo'limni tanlang:",
        'profile': "👤 Profil",
        'change_phone': "📱 Raqamni o'zgartirish",
        'contact_admin': "📨 Adminga murojaat",
        'settings': "⚙️ Sozlamalar",
        'back': "🔙 Orqaga",
        'enter_new_phone': "📱 Yangi telefon raqamingizni kiriting:",
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
        'invalid_phone': "❌ Noto'g'ri format!\n\nIltimos, to'g'ri telefon raqam kiriting.",
        'welcome_back': "👋 Xush kelibsiz, {}!\n\nSiz allaqachon tizimga kirgansiz.",
        'logout_success': "✅ Siz tizimdan muvaffaqiyatli chiqdingiz.\n\nQaytadan kirish uchun /start ni bosing.",
        'language_changed': "Til muvaffaqiyatli o'zgartirildi!",
        'forgot_password': "🔑 Parolni tiklash",
        'forgot_password_phone': "📱 Parolni tiklash uchun telefon raqamingizni kiriting:",
        'forgot_password_code_sent': "✅ Kod yuborildi!\n\n🔐 Tasdiqlash kodingiz: <b>{}</b>\n\nKodni kiriting:",
        'forgot_password_enter_code': "🔐 Tasdiqlash kodini kiriting:",
        'forgot_password_code_verified': "✅ Kod tasdiqlandi!\n\nYangi parolingizni kiriting (kamida 6 ta belgi):",
        'forgot_password_enter_new': "🔑 Yangi parolingizni kiriting (kamida 6 ta belgi):",
        'forgot_password_success': "✅ Parol muvaffaqiyatli o'zgartirildi!\n\nEndi yangi parolingiz bilan kirishingiz mumkin.",
        'forgot_password_error': "❌ Xatolik: {}",
        'invalid_code': "❌ Noto'g'ri kod!\n\nIltimos, qaytadan urinib ko'ring.",
        'password_too_short': "❌ Parol kamida 6 ta belgidan iborat bo'lishi kerak!",
        'send_phone_contact': "📱 Telefon raqamni yuborish",
        'forgot_password_welcome': "🔑 Parolni tiklash\n\nParolni tiklash uchun telefon raqamingizni yuboring:",
        'login_or_reset': "🔐 Kirish yoki parolni tiklash\n\nKerakli bo'limni tanlang:",
        'login': "🔐 Kirish",
        'register': "📝 Ro'yxatdan o'tish",
        'reset_password': "🔑 Parolni tiklash",
        'main_choice': "🔐 Kerakli bo'limni tanlang:",
        'get_code': "📱 Kodni olish",
        'get_code_menu': "📱 Kodni olish\n\nKerakli bo'limni tanlang:",
        'get_code_login': "🔐 Kirish uchun kod",
        'get_code_register': "📝 Ro'yxatdan o'tish uchun kod",
        'get_code_forgot': "🔑 Parolni tiklash uchun kod",
        'register_phone': "📝 Ro'yxatdan o'tish uchun telefon raqamingizni yuboring:",
        'register_code_sent': "✅ Kod yuborildi!\n\n🔐 Tasdiqlash kodingiz: <b>{}</b>\n\nKodni kiriting:",
        'register_enter_code': "🔐 Tasdiqlash kodini kiriting:",
        'register_enter_data': "📝 Ro'yxatdan o'tish ma'lumotlari\n\nQuyidagi formatda kiriting:\n\n<b>Ism|Parol|Role</b>\n\nMasalan:\n<b>John Doe|password123|user</b>",
        'register_success': "✅ Muvaffaqiyatli ro'yxatdan o'tdingiz!",
        'login_code_sent': "✅ Kod yuborildi!\n\n🔐 Tasdiqlash kodingiz: <b>{}</b>\n\nKodni kiriting:",
        'login_enter_code': "🔐 Tasdiqlash kodini kiriting:",
        'admin_login_success': "✅ Admin sifatida muvaffaqiyatli kirildingiz!"
    },
    'ru': {
        'welcome': "👋 Добро пожаловать!\n\nПожалуйста, выберите язык:",
        'send_phone': "📱 Отправьте ваш номер телефона:",
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
        'enter_new_phone': "📱 Введите новый номер телефона:",
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
        'invalid_phone': "❌ Неверный формат!\n\nПожалуйста, введите правильный номер.",
        'welcome_back': "👋 Добро пожаловать, {}!\n\nВы уже вошли в систему.",
        'logout_success': "✅ Вы успешно вышли из системы.\n\nНажмите /start чтобы войти снова.",
        'language_changed': "Язык успешно изменен!",
        'forgot_password': "🔑 Восстановить пароль",
        'forgot_password_phone': "📱 Введите ваш номер телефона для восстановления пароля:",
        'forgot_password_code_sent': "✅ Код отправлен!\n\n🔐 Ваш код подтверждения: <b>{}</b>\n\nВведите код:",
        'forgot_password_enter_code': "🔐 Введите код подтверждения:",
        'forgot_password_code_verified': "✅ Код подтвержден!\n\nВведите новый пароль (минимум 6 символов):",
        'forgot_password_enter_new': "🔑 Введите новый пароль (минимум 6 символов):",
        'forgot_password_success': "✅ Пароль успешно изменен!\n\nТеперь вы можете войти с новым паролем.",
        'forgot_password_error': "❌ Ошибка: {}",
        'invalid_code': "❌ Неверный код!\n\nПожалуйста, попробуйте снова.",
        'password_too_short': "❌ Пароль должен содержать минимум 6 символов!",
        'send_phone_contact': "📱 Отправить номер телефона",
        'forgot_password_welcome': "🔑 Восстановление пароля\n\nОтправьте ваш номер телефона для восстановления пароля:",
        'main_choice': "🔐 Выберите нужный раздел:",
        'login': "🔐 Вход",
        'get_code': "📱 Получить код",
        'get_code_menu': "📱 Получить код\n\nВыберите нужный раздел:",
        'get_code_login': "🔐 Код для входа",
        'get_code_register': "📝 Код для регистрации",
        'get_code_forgot': "🔑 Код для восстановления пароля",
        'register_phone': "📝 Отправьте ваш номер телефона для регистрации:",
        'register_code_sent': "✅ Код отправлен!\n\n🔐 Ваш код подтверждения: <b>{}</b>\n\nВведите код:",
        'register_enter_code': "🔐 Введите код подтверждения:",
        'register_enter_data': "📝 Данные для регистрации\n\nВведите в следующем формате:\n\n<b>Имя|Пароль|Роль</b>\n\nНапример:\n<b>Иван Иванов|password123|user</b>",
        'register_success': "✅ Вы успешно зарегистрировались!",
        'login_code_sent': "✅ Код отправлен!\n\n🔐 Ваш код подтверждения: <b>{}</b>\n\nВведите код:",
        'login_enter_code': "🔐 Введите код подтверждения:",
        'admin_login_success': "✅ Вы успешно вошли как администратор!"
    },
    'en': {
        'welcome': "👋 Welcome!\n\nPlease choose your language:",
        'send_phone': "📱 Send your phone number:",
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
        'enter_new_phone': "📱 Enter new phone number:",
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
        'invalid_phone': "❌ Invalid format!\n\nPlease enter correct phone number.",
        'welcome_back': "👋 Welcome back, {}!\n\nYou're already logged in.",
        'logout_success': "✅ You have successfully logged out.\n\nPress /start to login again.",
        'language_changed': "Language successfully changed!",
        'forgot_password': "🔑 Reset password",
        'forgot_password_phone': "📱 Enter your phone number to reset password:",
        'forgot_password_code_sent': "✅ Code sent!\n\n🔐 Your verification code: <b>{}</b>\n\nEnter the code:",
        'forgot_password_enter_code': "🔐 Enter verification code:",
        'forgot_password_code_verified': "✅ Code verified!\n\nEnter your new password (minimum 6 characters):",
        'forgot_password_enter_new': "🔑 Enter new password (minimum 6 characters):",
        'forgot_password_success': "✅ Password successfully changed!\n\nYou can now login with your new password.",
        'forgot_password_error': "❌ Error: {}",
        'invalid_code': "❌ Invalid code!\n\nPlease try again.",
        'password_too_short': "❌ Password must be at least 6 characters!",
        'send_phone_contact': "📱 Send phone number",
        'forgot_password_welcome': "🔑 Reset password\n\nSend your phone number to reset password:",
        'main_choice': "🔐 Select a section:",
        'login': "🔐 Login",
        'get_code': "📱 Get code",
        'get_code_menu': "📱 Get code\n\nSelect a section:",
        'get_code_login': "🔐 Code for login",
        'get_code_register': "📝 Code for register",
        'get_code_forgot': "🔑 Code for reset password",
        'register_phone': "📝 Send your phone number for registration:",
        'register_code_sent': "✅ Code sent!\n\n🔐 Your verification code: <b>{}</b>\n\nEnter the code:",
        'register_enter_code': "🔐 Enter verification code:",
        'register_enter_data': "📝 Registration data\n\nEnter in the following format:\n\n<b>Name|Password|Role</b>\n\nExample:\n<b>John Doe|password123|user</b>",
        'register_success': "✅ You have successfully registered!",
        'login_code_sent': "✅ Code sent!\n\n🔐 Your verification code: <b>{}</b>\n\nEnter the code:",
        'login_enter_code': "🔐 Enter verification code:",
        'admin_login_success': "✅ You have successfully logged in as admin!"
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
        [KeyboardButton(get_text(lang, 'change_phone')), KeyboardButton(get_text(lang, 'forgot_password'))],
        [KeyboardButton(get_text(lang, 'settings')), KeyboardButton(get_text(lang, 'logout'))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard(lang):
    """Orqaga tugmasi"""
    keyboard = [[KeyboardButton(get_text(lang, 'back'))]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_phone_contact_keyboard(lang):
    """Telefon raqamni yuborish tugmasi"""
    keyboard = [
        [KeyboardButton(get_text(lang, 'send_phone_contact'), request_contact=True)],
        [KeyboardButton(get_text(lang, 'back'))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_main_choice_keyboard(lang):
    """Asosiy tanlov tugmalari"""
    keyboard = [
        [KeyboardButton(get_text(lang, 'login'))],
        [KeyboardButton(get_text(lang, 'get_code'))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_code_menu_keyboard(lang):
    """Kod olish menyusi tugmalari"""
    keyboard = [
        [KeyboardButton(get_text(lang, 'get_code_login'))],
        [KeyboardButton(get_text(lang, 'get_code_register'))],
        [KeyboardButton(get_text(lang, 'get_code_forgot'))],
        [KeyboardButton(get_text(lang, 'back'))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

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
        get_text(lang, 'main_choice'),
        reply_markup=get_main_choice_keyboard(lang)
    )
    return MAIN_CHOICE

async def main_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy tanlov handler"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    
    if get_text(lang, 'login') in text or "🔐" in text:
        # Kirish - Parol so'rash
        await update.message.reply_text(
            get_text(lang, 'send_phone'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return CODE_PHONE  # Telefon raqam olish uchun
    elif get_text(lang, 'get_code') in text or "📱" in text:
        # Kodni olish menyusi
        await update.message.reply_text(
            get_text(lang, 'get_code_menu'),
            reply_markup=get_code_menu_keyboard(lang)
        )
        return GET_CODE_MENU
    else:
        await update.message.reply_text(
            get_text(lang, 'main_choice'),
            reply_markup=get_main_choice_keyboard(lang)
        )
        return MAIN_CHOICE

async def get_code_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kod olish menyusi handler"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'main_choice'),
            reply_markup=get_main_choice_keyboard(lang)
        )
        return MAIN_CHOICE
    elif get_text(lang, 'get_code_login') in text or ("🔐" in text and "Kirish" in text):
        # Login uchun kod
        context.user_data['code_action'] = 'login'
        await update.message.reply_text(
            get_text(lang, 'send_phone'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return CODE_PHONE
    elif get_text(lang, 'get_code_register') in text or ("📝" in text and "Ro'yxatdan" in text):
        # Register uchun kod
        context.user_data['code_action'] = 'register'
        await update.message.reply_text(
            get_text(lang, 'send_phone'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return CODE_PHONE
    elif get_text(lang, 'get_code_forgot') in text or ("🔑" in text and "Parolni" in text):
        # Forgot password uchun kod
        context.user_data['code_action'] = 'forgot'
        await update.message.reply_text(
            get_text(lang, 'send_phone'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return CODE_PHONE
    else:
        await update.message.reply_text(
            get_text(lang, 'get_code_menu'),
            reply_markup=get_code_menu_keyboard(lang)
        )
        return GET_CODE_MENU

async def code_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kod olish yoki login uchun telefon raqam qabul qilish"""
    lang = context.user_data.get('lang', 'uz')
    user_id = update.effective_user.id
    
    # Faqat contact qabul qilish
    if not update.message.contact:
        text = update.message.text
        
        if get_text(lang, 'back') in text or "🔙" in text:
            code_action = context.user_data.get('code_action')
            if code_action:
                await update.message.reply_text(
                    get_text(lang, 'get_code_menu'),
                    reply_markup=get_code_menu_keyboard(lang)
                )
                return GET_CODE_MENU
            else:
                await update.message.reply_text(
                    get_text(lang, 'main_choice'),
                    reply_markup=get_main_choice_keyboard(lang)
                )
                return MAIN_CHOICE
        
        await update.message.reply_text(
            "📱 Iltimos, telefon raqamingizni tugma orqali yuboring:",
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return CODE_PHONE
    
    # Contact yuborilgan
    phone = update.message.contact.phone_number
    logger.info(f"User {user_id} sent contact: {phone}")
    
    # Telefon raqamni normalize qilish
    if not phone.startswith('+'):
        if phone.startswith('998'):
            phone = '+' + phone
        elif phone.startswith('8'):
            phone = '+998' + phone[1:]
        else:
            phone = '+998' + phone
    
    context.user_data['phone'] = phone
    
    # Agar "Kirish" tugmasi bosilgan bo'lsa (code_action yo'q), parol so'rash
    code_action = context.user_data.get('code_action')
    if not code_action:
        # "Kirish" tugmasi - parol so'rash
        await update.message.reply_text(
            get_text(lang, 'send_password'),
            reply_markup=ReplyKeyboardRemove()
        )
        return LOGIN_PASSWORD
    
    # "Kodni olish" tugmasi - backend'ga kod so'rash
    try:
        if code_action == 'forgot':
            # Forgot password uchun kod
            send_code_url = get_backend_url("auth/forgot-password")
            payload = {
                'phoneNumber': phone,
                'source': 'bot'
            }
        else:
            # Login yoki Register uchun kod
            send_code_url = get_backend_url("auth/send-code")
            payload = {
                'phoneNumber': phone,
                'action': code_action  # 'login' yoki 'register'
            }
        
        logger.info(f"Sending request to: {send_code_url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(
            send_code_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text[:500]}")
        
        if response.status_code == 200:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_phone_contact_keyboard(lang)
                )
                return CODE_PHONE
            
            if result.get('success'):
                code = result.get('data', {}).get('code')
                if code:
                    context.user_data['code'] = code
                    
                    await update.message.reply_text(
                        get_text(lang, 'login_code_sent').format(code),
                        parse_mode='HTML',
                        reply_markup=get_back_keyboard(lang)
                    )
                    return CODE_VERIFY
                else:
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_error').format("Kod olinmadi"),
                        reply_markup=get_phone_contact_keyboard(lang)
                    )
                    return CODE_PHONE
            else:
                error_msg = result.get('message', 'Noma\'lum xatolik')
                await update.message.reply_text(
                    get_text(lang, 'forgot_password_error').format(error_msg),
                    reply_markup=get_phone_contact_keyboard(lang)
                )
                return CODE_PHONE
        else:
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Kod olishda xatolik')
            else:
                error_msg = f"Xatolik ({response.status_code})"
            
            await update.message.reply_text(
                get_text(lang, 'forgot_password_error').format(error_msg),
                reply_markup=get_phone_contact_keyboard(lang)
            )
            return CODE_PHONE
            
    except Exception as e:
        logger.error(f"Get code error: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return CODE_PHONE

async def login_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Login uchun parol qabul qilish va to'g'ridan-to'g'ri login"""
    password = update.message.text
    phone = context.user_data.get('phone')
    lang = context.user_data.get('lang', 'uz')
    user_id = update.effective_user.id
    
    context.user_data['password'] = password
    logger.info(f"User {user_id} attempting login with phone: {phone}")
    
    # Backend'ga to'g'ridan-to'g'ri login qilish (parol bilan)
    try:
        login_url = get_backend_url("auth/login")
        payload = {
            'phoneNumber': phone,
            'password': password
        }
        
        logger.info(f"Sending request to: {login_url}")
        logger.info(f"Payload: {{'phoneNumber': '{phone}', 'password': '***'}}")
        
        response = requests.post(
            login_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text[:500]}")
        
        if response.status_code == 200:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_main_choice_keyboard(lang)
                )
                return MAIN_CHOICE
            
            if result.get('success'):
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
                error_msg = result.get('message', 'Login xatolik')
                logger.warning(f"Login failed for user {user_id}: {error_msg}")
                await update.message.reply_text(
                    get_text(lang, 'login_failed'),
                    reply_markup=get_main_choice_keyboard(lang)
                )
                return MAIN_CHOICE
        else:
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Login xatolik')
            else:
                error_msg = f"Xatolik ({response.status_code})"
            
            logger.warning(f"Login failed for user {user_id}: {error_msg}")
            await update.message.reply_text(
                get_text(lang, 'login_failed'),
                reply_markup=get_main_choice_keyboard(lang)
            )
            return MAIN_CHOICE
            
    except Exception as e:
        logger.error(f"Login error for user {user_id}: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_main_choice_keyboard(lang)
        )
        return MAIN_CHOICE

async def code_verify_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kodni tekshirish handler"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    phone = context.user_data.get('phone')
    code_action = context.user_data.get('code_action')
    user_id = update.effective_user.id
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'get_code_menu'),
            reply_markup=get_code_menu_keyboard(lang)
        )
        return GET_CODE_MENU
    
    code = text.strip()
    logger.info(f"User {user_id} verifying code: {code} for action: {code_action}")
    
    try:
        if code_action == 'forgot':
            # Forgot password - kodni tekshirish
            verify_url = get_backend_url("auth/verify-code")
            payload = {
                'phoneNumber': phone,
                'code': code
            }
        elif code_action == 'register':
            # Register - kodni tekshirish va keyin ma'lumotlarni so'rash
            verify_url = get_backend_url("auth/verify-code")
            payload = {
                'phoneNumber': phone,
                'code': code
            }
        else:
            # Login - kodni tekshirish va login qilish
            verify_url = get_backend_url("auth/verify-code-auth")
            payload = {
                'phoneNumber': phone,
                'code': code
            }
        
        logger.info(f"Sending request to: {verify_url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(
            verify_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text[:500]}")
        
        if response.status_code == 200:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_back_keyboard(lang)
                )
                return CODE_VERIFY
            
            if result.get('success'):
                if code_action == 'forgot':
                    # Forgot password - reset_token ni saqlash va yangi parol so'rash
                    reset_token = result.get('data', {}).get('resetToken')
                    if reset_token:
                        context.user_data['reset_token'] = reset_token
                    
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_new_password'),
                        reply_markup=get_back_keyboard(lang)
                    )
                    return FORGOT_PASSWORD_NEW_PASSWORD
                elif code_action == 'register':
                    # Register - ma'lumotlarni so'rash
                    await update.message.reply_text(
                        get_text(lang, 'register_enter_data'),
                        parse_mode='HTML',
                        reply_markup=get_back_keyboard(lang)
                    )
                    context.user_data['verified_code'] = code
                    return REGISTER_DATA
                else:
                    # Login - to'g'ridan-to'g'ri login qilish
                    # verify-code-auth dan keyin login qilish
                    login_url = get_backend_url("auth/login")
                    login_payload = {
                        'phoneNumber': phone,
                        'code': code
                    }
                    
                    login_response = requests.post(
                        login_url,
                        json=login_payload,
                        headers={'Content-Type': 'application/json'},
                        timeout=10
                    )
                    
                    if login_response.status_code == 200:
                        login_result = safe_json_parse(login_response)
                        if login_result and login_result.get('success'):
                            data = login_result.get('data', {})
                            
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
                            
                            save_user(user_data)
                            context.user_data.update(user_data)
                            
                            profile_msg = get_profile_message(user_data, lang)
                            welcome_msg = f"✅ {get_text(lang, 'login_success')}\n\n{profile_msg}"
                            
                            await update.message.reply_text(
                                welcome_msg,
                                reply_markup=get_main_menu_keyboard(lang)
                            )
                            return MAIN_MENU
                    
                    await update.message.reply_text(
                        get_text(lang, 'login_failed'),
                        reply_markup=get_back_keyboard(lang)
                    )
                    return CODE_VERIFY
            else:
                error_msg = result.get('message', 'Kod noto\'g\'ri')
                await update.message.reply_text(
                    get_text(lang, 'invalid_code'),
                    reply_markup=get_back_keyboard(lang)
                )
                return CODE_VERIFY
        else:
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Kod tekshirishda xatolik')
            else:
                error_msg = f"Xatolik ({response.status_code})"
            
            await update.message.reply_text(
                get_text(lang, 'forgot_password_error').format(error_msg),
                reply_markup=get_back_keyboard(lang)
            )
            return CODE_VERIFY
            
    except Exception as e:
        logger.error(f"Code verify error for user {user_id}: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_back_keyboard(lang)
        )
        return CODE_VERIFY

async def register_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register - telefon raqam qabul qilish"""
    lang = context.user_data.get('lang', 'uz')
    
    # Faqat contact qabul qilish
    if not update.message.contact:
        text = update.message.text
        
        if get_text(lang, 'back') in text or "🔙" in text:
            await update.message.reply_text(
                get_text(lang, 'login_or_reset'),
                reply_markup=get_login_or_reset_keyboard(lang)
            )
            return LOGIN_OR_RESET
        
        await update.message.reply_text(
            "📱 Iltimos, telefon raqamingizni tugma orqali yuboring:",
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return REGISTER_PHONE
    
    # Contact yuborilgan
    phone = update.message.contact.phone_number
    logger.info(f"User {update.effective_user.id} sent contact for register: {phone}")
    
    # Telefon raqamni normalize qilish
    if not phone.startswith('+'):
        if phone.startswith('998'):
            phone = '+' + phone
        elif phone.startswith('8'):
            phone = '+998' + phone[1:]
        else:
            phone = '+998' + phone
    
    context.user_data['register_phone'] = phone
    
    # Backend'ga kod so'rash
    try:
        send_code_url = get_backend_url("auth/send-register-code")
        payload = {
            'phoneNumber': phone,
            'source': 'register'
        }
        
        logger.info(f"Sending request to: {send_code_url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(
            send_code_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text[:500]}")
        
        if response.status_code == 200:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_phone_contact_keyboard(lang)
                )
                return REGISTER_PHONE
            
            if result.get('success'):
                code = result.get('data', {}).get('code')
                if code:
                    await update.message.reply_text(
                        get_text(lang, 'register_code_sent').format(code),
                        parse_mode='HTML',
                        reply_markup=get_back_keyboard(lang)
                    )
                    context.user_data['register_code'] = code
                    return REGISTER_CODE
                else:
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_error').format("Kod olinmadi"),
                        reply_markup=get_phone_contact_keyboard(lang)
                    )
                    return REGISTER_PHONE
            else:
                error_msg = result.get('message', 'Noma\'lum xatolik')
                await update.message.reply_text(
                    get_text(lang, 'forgot_password_error').format(error_msg),
                    reply_markup=get_phone_contact_keyboard(lang)
                )
                return REGISTER_PHONE
        else:
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Kod olishda xatolik')
            else:
                error_msg = f"Xatolik ({response.status_code})"
            
            await update.message.reply_text(
                get_text(lang, 'forgot_password_error').format(error_msg),
                reply_markup=get_phone_contact_keyboard(lang)
            )
            return REGISTER_PHONE
            
    except Exception as e:
        logger.error(f"Register code error: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return REGISTER_PHONE

async def register_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register - kodni qabul qilish"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'register_phone'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return REGISTER_PHONE
    
    code = text.strip()
    context.user_data['register_code'] = code
    
    await update.message.reply_text(
        get_text(lang, 'register_enter_data'),
        parse_mode='HTML',
        reply_markup=get_back_keyboard(lang)
    )
    return REGISTER_DATA

async def register_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register - ism, parol, rol qabul qilish"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    user_id = update.effective_user.id
    phone = context.user_data.get('phone')
    code = context.user_data.get('verified_code')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'register_enter_code'),
            reply_markup=get_back_keyboard(lang)
        )
        return REGISTER_CODE
    
    # Format: Ism|Parol|Role
    parts = text.split('|')
    if len(parts) != 3:
        await update.message.reply_text(
            get_text(lang, 'register_enter_data'),
            parse_mode='HTML',
            reply_markup=get_back_keyboard(lang)
        )
        return REGISTER_DATA
    
    full_name = parts[0].strip()
    password = parts[1].strip()
    role = parts[2].strip().lower()
    
    if not full_name or not password or not role:
        await update.message.reply_text(
            get_text(lang, 'register_enter_data'),
            parse_mode='HTML',
            reply_markup=get_back_keyboard(lang)
        )
        return REGISTER_DATA
    
    # Backend'ga register qilish
    try:
        register_url = get_backend_url("auth/register")
        payload = {
            'fullName': full_name,
            'phoneNumber': phone,
            'password': password,
            'role': role,
            'code': code
        }
        
        logger.info(f"Sending request to: {register_url}")
        logger.info(f"Payload: {{'fullName': '{full_name}', 'phoneNumber': '{phone}', 'role': '{role}', 'code': '{code}'}}")
        
        response = requests.post(
            register_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text[:500]}")
        
        if response.status_code == 200 or response.status_code == 201:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_back_keyboard(lang)
                )
                return REGISTER_DATA
            
            if result.get('success'):
                data = result.get('data', {})
                
                # User ma'lumotlarini saqlash
                user_data = {
                    'user_id': user_id,
                    'phone': data.get('phoneNumber', phone),
                    'full_name': data.get('fullName', full_name),
                    'role': data.get('role', role),
                    'balans': data.get('balans', '0'),
                    'access_token': data.get('accessToken'),
                    'refresh_token': data.get('refreshToken'),
                    'lang': lang,
                    'logged_in': True
                }
                
                # Database ga saqlash
                save_user(user_data)
                context.user_data.update(user_data)
                
                logger.info(f"User {user_id} registered successfully as {full_name}")
                
                # Profil ma'lumotlarini tayyorlash
                profile_msg = get_profile_message(user_data, lang)
                
                # Muvaffaqiyatli register xabari
                welcome_msg = f"✅ {get_text(lang, 'register_success')}\n\n{profile_msg}"
                
                await update.message.reply_text(
                    welcome_msg,
                    reply_markup=get_main_menu_keyboard(lang)
                )
                return MAIN_MENU
            else:
                error_msg = result.get('message', 'Register xatolik')
                await update.message.reply_text(
                    get_text(lang, 'forgot_password_error').format(error_msg),
                    reply_markup=get_back_keyboard(lang)
                )
                return REGISTER_DATA
        else:
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Register xatolik')
            else:
                error_msg = f"Xatolik ({response.status_code})"
            
            await update.message.reply_text(
                get_text(lang, 'forgot_password_error').format(error_msg),
                reply_markup=get_back_keyboard(lang)
            )
            return REGISTER_DATA
            
    except Exception as e:
        logger.error(f"Register error: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_back_keyboard(lang)
        )
        return REGISTER_DATA

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
    
    elif get_text(lang, 'forgot_password') in text or "🔑" in text:
        # Parolni tiklash - Faqat contact orqali telefon raqam olish
        await update.message.reply_text(
            get_text(lang, 'forgot_password_welcome'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return FORGOT_PASSWORD_CONTACT
    
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
            get_text(lang, 'login_or_reset'),
            reply_markup=get_login_or_reset_keyboard(lang)
        )
        return LOGIN_OR_RESET
    
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
            get_text(lang, 'login_or_reset'),
            reply_markup=get_login_or_reset_keyboard(lang)
        )
        return LOGIN_OR_RESET
    
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
            get_text(lang, 'login_or_reset'),
            reply_markup=get_login_or_reset_keyboard(lang)
        )
        return LOGIN_OR_RESET
    
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

async def forgot_password_contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parolni tiklash - telefon raqamni contact orqali qabul qilish - Faqat contact"""
    lang = context.user_data.get('lang', 'uz')
    
    # Faqat contact qabul qilish
    if not update.message.contact:
        # Agar contact emas, text bo'lsa
        text = update.message.text
        
        if get_text(lang, 'back') in text or "🔙" in text:
            await update.message.reply_text(
                get_text(lang, 'main_menu'),
                reply_markup=get_main_menu_keyboard(lang)
            )
            return MAIN_MENU
        
        # Agar contact emas, qayta so'rash
        await update.message.reply_text(
            "📱 Iltimos, telefon raqamingizni tugma orqali yuboring:",
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return FORGOT_PASSWORD_CONTACT
    
    # Contact yuborilgan
    phone = update.message.contact.phone_number
    logger.info(f"User {update.effective_user.id} sent contact: {phone}")
    
    # Telefon raqamni normalize qilish
    if not phone.startswith('+'):
        if phone.startswith('998'):
            phone = '+' + phone
        elif phone.startswith('8'):
            phone = '+998' + phone[1:]
        else:
            phone = '+998' + phone
    
    context.user_data['forgot_password_phone'] = phone
    logger.info(f"User {update.effective_user.id} requested password reset for phone: {phone}")
    
    # Backend'dan kod olish
    try:
        # Backend URL ni tekshirish
        if not BACKEND_URL:
            logger.error("BACKEND_URL topilmadi! .env faylni tekshiring!")
            await update.message.reply_text(
                get_text(lang, 'connection_error'),
                reply_markup=get_phone_contact_keyboard(lang)
            )
            return FORGOT_PASSWORD_CONTACT
        
        forgot_password_url = get_backend_url("auth/forgot-password")
        payload = {
            'phoneNumber': phone,
            'source': 'bot'  # Bot'dan kelgan so'rov
        }
        
        logger.info(f"Sending request to: {forgot_password_url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(
            forgot_password_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        if response.status_code == 200:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_back_keyboard(lang)
                )
                return FORGOT_PASSWORD_CODE
            
            if result.get('success'):
                code = result.get('data', {}).get('code')
                
                if code:
                    # Foydalanuvchiga kodni yuborish
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_code_sent').format(code),
                        parse_mode='HTML',
                        reply_markup=get_back_keyboard(lang)
                    )
                    context.user_data['forgot_password_code'] = code
                    return FORGOT_PASSWORD_CODE
                else:
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_error').format("Kod olinmadi"),
                        reply_markup=get_phone_contact_keyboard(lang)
                    )
                    return FORGOT_PASSWORD_CONTACT
            else:
                error_msg = result.get('message', 'Noma\'lum xatolik')
                await update.message.reply_text(
                    get_text(lang, 'forgot_password_error').format(error_msg),
                    reply_markup=get_phone_contact_keyboard(lang)
                )
                return FORGOT_PASSWORD_CONTACT
        else:
            # 502 Bad Gateway yoki boshqa server xatolari
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Kod olishda xatolik')
            else:
                # HTML response yoki boshqa format
                if response.status_code == 502:
                    error_msg = "Server vaqtincha ishlamayapti (502 Bad Gateway)"
                elif response.status_code >= 500:
                    error_msg = f"Server xatosi ({response.status_code})"
                else:
                    error_msg = f"Xatolik ({response.status_code})"
            
            await update.message.reply_text(
                get_text(lang, 'forgot_password_error').format(error_msg),
                reply_markup=get_phone_contact_keyboard(lang)
            )
            return FORGOT_PASSWORD_CONTACT
            
    except Exception as e:
        logger.error(f"Forgot password error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_phone_contact_keyboard(lang)
        )
        return FORGOT_PASSWORD_CONTACT

async def forgot_password_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parolni tiklash - telefon raqam qabul qilish (asosiy menyudan)"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'login_or_reset'),
            reply_markup=get_login_or_reset_keyboard(lang)
        )
        return LOGIN_OR_RESET
    
    # Telefon raqam formatini tekshirish
    phone = text.strip()
    if not validate_phone(phone):
        await update.message.reply_text(
            get_text(lang, 'invalid_phone'),
            reply_markup=get_back_keyboard(lang)
        )
        return FORGOT_PASSWORD_PHONE
    
    # Telefon raqamni normalize qilish
    if not phone.startswith('+'):
        if phone.startswith('998'):
            phone = '+' + phone
        elif phone.startswith('8'):
            phone = '+998' + phone[1:]
        else:
            phone = '+998' + phone
    
    context.user_data['forgot_password_phone'] = phone
    logger.info(f"User {update.effective_user.id} requested password reset for phone: {phone}")
    
    # Backend'dan kod olish
    try:
        forgot_password_url = get_backend_url("auth/forgot-password")
        payload = {
            'phoneNumber': phone,
            'source': 'bot'  # Bot'dan kelgan so'rov
        }
        
        logger.info(f"Sending request to: {forgot_password_url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(
            forgot_password_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        if response.status_code == 200:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_back_keyboard(lang)
                )
                return FORGOT_PASSWORD_CODE
            
            if result.get('success'):
                code = result.get('data', {}).get('code')
                
                if code:
                    # Foydalanuvchiga kodni yuborish
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_code_sent').format(code),
                        parse_mode='HTML',
                        reply_markup=get_back_keyboard(lang)
                    )
                    context.user_data['forgot_password_code'] = code
                    return FORGOT_PASSWORD_CODE
                else:
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_error').format("Kod olinmadi"),
                        reply_markup=get_back_keyboard(lang)
                    )
                    return FORGOT_PASSWORD_PHONE
            else:
                error_msg = result.get('message', 'Noma\'lum xatolik')
                await update.message.reply_text(
                    get_text(lang, 'forgot_password_error').format(error_msg),
                    reply_markup=get_back_keyboard(lang)
                )
                return FORGOT_PASSWORD_PHONE
        else:
            # 502 Bad Gateway yoki boshqa server xatolari
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Kod olishda xatolik')
            else:
                # HTML response yoki boshqa format
                if response.status_code == 502:
                    error_msg = "Server vaqtincha ishlamayapti (502 Bad Gateway)"
                elif response.status_code >= 500:
                    error_msg = f"Server xatosi ({response.status_code})"
                else:
                    error_msg = f"Xatolik ({response.status_code})"
            
            await update.message.reply_text(
                get_text(lang, 'forgot_password_error').format(error_msg),
                reply_markup=get_back_keyboard(lang)
            )
            return FORGOT_PASSWORD_PHONE
            
    except Exception as e:
        logger.error(f"Forgot password error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_back_keyboard(lang)
        )
        return FORGOT_PASSWORD_PHONE

async def forgot_password_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parolni tiklash - kodni tekshirish"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    phone = context.user_data.get('forgot_password_phone')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'login_or_reset'),
            reply_markup=get_login_or_reset_keyboard(lang)
        )
        return LOGIN_OR_RESET
    
    code = text.strip()
    logger.info(f"User {update.effective_user.id} verifying code: {code} for phone: {phone}")
    
    # Backend'da kodni tekshirish
    try:
        verify_code_url = get_backend_url("auth/verify-code")
        payload = {
            'phoneNumber': phone,
            'code': code
        }
        
        logger.info(f"Sending request to: {verify_code_url}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(
            verify_code_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        if response.status_code == 200:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_back_keyboard(lang)
                )
                return FORGOT_PASSWORD_CODE
            
            if result.get('success'):
                reset_token = result.get('data', {}).get('resetToken')
                
                if reset_token:
                    context.user_data['reset_token'] = reset_token
                    
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_code_verified'),
                        reply_markup=get_back_keyboard(lang)
                    )
                    return FORGOT_PASSWORD_NEW_PASSWORD
                else:
                    await update.message.reply_text(
                        get_text(lang, 'forgot_password_error').format("Token olinmadi"),
                        reply_markup=get_back_keyboard(lang)
                    )
                    return FORGOT_PASSWORD_CODE
            else:
                await update.message.reply_text(
                    get_text(lang, 'invalid_code'),
                    reply_markup=get_back_keyboard(lang)
                )
                return FORGOT_PASSWORD_CODE
        else:
            # 502 Bad Gateway yoki boshqa server xatolari
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Kod tekshirishda xatolik')
            else:
                # HTML response yoki boshqa format
                if response.status_code == 502:
                    error_msg = "Server vaqtincha ishlamayapti (502 Bad Gateway)"
                elif response.status_code >= 500:
                    error_msg = f"Server xatosi ({response.status_code})"
                else:
                    error_msg = f"Xatolik ({response.status_code})"
            await update.message.reply_text(
                get_text(lang, 'forgot_password_error').format(error_msg),
                reply_markup=get_back_keyboard(lang)
            )
            return FORGOT_PASSWORD_CODE
            
    except Exception as e:
        logger.error(f"Verify code error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_back_keyboard(lang)
        )
        return FORGOT_PASSWORD_CODE

async def forgot_password_new_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parolni tiklash - yangi parol qabul qilish"""
    text = update.message.text
    lang = context.user_data.get('lang', 'uz')
    phone = context.user_data.get('phone')
    code = context.user_data.get('code')
    reset_token = context.user_data.get('reset_token')
    
    if get_text(lang, 'back') in text or "🔙" in text:
        await update.message.reply_text(
            get_text(lang, 'get_code_menu'),
            reply_markup=get_code_menu_keyboard(lang)
        )
        return GET_CODE_MENU
    
    new_password = text.strip()
    
    # Parol uzunligini tekshirish
    if len(new_password) < 6:
        await update.message.reply_text(
            get_text(lang, 'password_too_short'),
            reply_markup=get_back_keyboard(lang)
        )
        return FORGOT_PASSWORD_NEW_PASSWORD
    
    logger.info(f"User {update.effective_user.id} resetting password")
    
    # Backend'da parolni tiklash
    try:
        reset_password_url = get_backend_url("auth/reset-password")
        payload = {
            'resetToken': reset_token,
            'newPassword': new_password
        }
        
        logger.info(f"Sending request to: {reset_password_url}")
        logger.info(f"Payload: {{'resetToken': '***', 'newPassword': '***'}}")
        
        response = requests.post(
            reset_password_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        if response.status_code == 200:
            result = safe_json_parse(response)
            if not result:
                await update.message.reply_text(
                    get_text(lang, 'connection_error'),
                    reply_markup=get_back_keyboard(lang)
                )
                return FORGOT_PASSWORD_CODE
            
            if result.get('success'):
                # Foydalanuvchi ma'lumotlarini tozalash
                context.user_data.pop('phone', None)
                context.user_data.pop('code', None)
                context.user_data.pop('reset_token', None)
                context.user_data.pop('code_action', None)
                
                await update.message.reply_text(
                    get_text(lang, 'forgot_password_success'),
                    reply_markup=get_main_menu_keyboard(lang)
                )
                return MAIN_MENU
            else:
                error_msg = result.get('message', 'Parol tiklashda xatolik')
                await update.message.reply_text(
                    get_text(lang, 'forgot_password_error').format(error_msg),
                    reply_markup=get_back_keyboard(lang)
                )
                return FORGOT_PASSWORD_NEW_PASSWORD
        else:
            # 502 Bad Gateway yoki boshqa server xatolari
            error_data = safe_json_parse(response)
            if error_data:
                error_msg = error_data.get('message', 'Parol tiklashda xatolik')
            else:
                # HTML response yoki boshqa format
                if response.status_code == 502:
                    error_msg = "Server vaqtincha ishlamayapti (502 Bad Gateway)"
                elif response.status_code >= 500:
                    error_msg = f"Server xatosi ({response.status_code})"
                else:
                    error_msg = f"Xatolik ({response.status_code})"
            await update.message.reply_text(
                get_text(lang, 'forgot_password_error').format(error_msg),
                reply_markup=get_back_keyboard(lang)
            )
            return FORGOT_PASSWORD_NEW_PASSWORD
            
    except Exception as e:
        logger.error(f"Reset password error for user {update.effective_user.id}: {str(e)}")
        await update.message.reply_text(
            get_text(lang, 'connection_error'),
            reply_markup=get_back_keyboard(lang)
        )
        return FORGOT_PASSWORD_NEW_PASSWORD

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
            MAIN_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_choice_handler)],
            GET_CODE_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_code_menu_handler)],
            CODE_PHONE: [MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), code_phone_handler)],
            CODE_VERIFY: [MessageHandler(filters.TEXT & ~filters.COMMAND, code_verify_handler)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password_handler)],
            REGISTER_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_data_handler)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
            CHANGE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_phone_handler)],
            APPEAL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, appeal_title_handler)],
            APPEAL_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, appeal_desc_handler)],
            FORGOT_PASSWORD_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, forgot_password_code_handler)],
            FORGOT_PASSWORD_NEW_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, forgot_password_new_password_handler)],
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