"""
Bu bot guruh ID sini aniqlash uchun
Botni guruhga qo'shing va /id yuboring
"""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    chat_title = update.effective_chat.title or "Private Chat"
    
    message = f"""
🤖 Chat Ma'lumotlari:

📝 Nom: {chat_title}
🆔 Chat ID: `{chat_id}`
📂 Turi: {chat_type}

💡 Agar bu guruh bo'lsa, yuqoridagi ID ni .env fayliga qo'ying:
ADMIN_GROUP_ID={chat_id}
    """
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get chat ID"""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    chat_title = update.effective_chat.title or "Private Chat"
    user = update.effective_user
    
    message = f"""
✅ Ma'lumotlar:

👤 Sizning ID: `{user.id}`
👤 Sizning username: @{user.username or 'Yo\'q'}

📱 Chat ID: `{chat_id}`
📝 Chat nomi: {chat_title}
📂 Chat turi: {chat_type}

{'✅ Bu guruh - ID ni .env ga qo\'ying!' if chat_type in ['group', 'supergroup'] else '⚠️ Bu guruh emas!'}
    """
    
    await update.message.reply_text(message, parse_mode='Markdown')

def main():
    """Bot ishga tushirish"""
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN topilmadi!")
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_id))
    
    print("✅ Bot ishga tushdi! Guruhga qo'shing va /id yuboring")
    app.run_polling()

if __name__ == '__main__':
    main()