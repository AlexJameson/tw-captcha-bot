from tinydb import TinyDB, Query
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ChatJoinRequestHandler, ContextTypes,MessageHandler, filters
import os
import logging
import datetime
import random
from dotenv import load_dotenv
from horoscope import get_horoscope

logging.basicConfig(level=logging.WARNING, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
                    filename="bot.log",
                    filemode="a")
logger = logging.getLogger(__name__)

db_users_file = "./pending_users.json"
if not os.path.exists(db_users_file):
    with open(db_users_file, "w") as file:
        file.write("{}")
db = TinyDB(db_users_file)
User = Query()

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
MAIN_GROUP_ID = os.getenv('MAIN_GROUP_ID')
MAIN_GROUP_USERNAME = os.getenv('MAIN_GROUP_USERNAME')
ADMIN_GROUP_ID = os.getenv('ADMIN_GROUP_ID')

# Single captcha question
CAPTCHA_QUESTION = "Why do you want to join?"
CAPTCHA_OPTIONS = [
    "Yes",
    "No",
    "Because I am interested in technical documentation",
    "I'm not a robot"
]
CORRECT_ANSWER = "Because I am interested in technical documentation"

def get_user_display_name(user) -> str:
    """Helper function to format user's display name"""
    parts = []
    if user.first_name:
        parts.append(user.first_name)
    if user.last_name:
        parts.append(user.last_name)
    full_name = " ".join(parts)
    
    if user.username:
        return f"{full_name} (@{user.username})"
    return full_name

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming chat join requests."""
    join_request = update.chat_join_request
    user = join_request.from_user
    
    # Store the join request in TinyDB
    db.upsert({
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'timestamp': datetime.datetime.now().isoformat()
    }, User.user_id == user.id)
    
    # Randomize options order
    shuffled_options = CAPTCHA_OPTIONS.copy()
    random.shuffle(shuffled_options)
    
    # Find the index of correct answer in shuffled options
    correct_option = shuffled_options.index(CORRECT_ANSWER)
    
    # Store correct option index in user_data
    context.user_data[f'correct_option_{user.id}'] = correct_option
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"verify_{i}")]
        for i, option in enumerate(shuffled_options)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"Здравствуйте! Пройдите верификацию чтобы вступить:\n\n{CAPTCHA_QUESTION}",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Could not send message to user {user.id}: {e}")
        await join_request.decline()

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle manual admin approval or dismissal."""
    query = update.callback_query
    admin_id = query.from_user.id
    admin = query.from_user
    admin_name = get_user_display_name(admin)

    action, user_id = query.data.split('_')
    user_id = int(user_id)
    
    original_text = query.message.text
    
    if action == "dismiss":
        try:
            await context.bot.decline_chat_join_request(
                chat_id=MAIN_GROUP_ID,
                user_id=user_id
            )
            
            # Notify user about dismissal
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Your join request has been reviewed and declined by administrators."
                )
            except Exception as e:
                logger.error(f"Couldn't notify user {user_id} about dismissal: {e}")
            
            # Update message and remove keyboard
            new_text = f"{original_text}\n\n❌ Request dismissed by {admin_name}"
            await query.edit_message_text(new_text)
            await query.edit_message_reply_markup(None)
                
        except Exception as e:
            logger.error(f"Error dismissing user {user_id}: {e}")
            await query.edit_message_text(f"{original_text}\n\n⚠️ Error dismissing user: {str(e)}")
            await query.edit_message_reply_markup(None)
        return

    try:
        # Try to add user to group
        await context.bot.approve_chat_join_request(
            chat_id=MAIN_GROUP_ID,
            user_id=user_id
        )

        # Notify user about approval
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Добро пожаловать в чат технических писателей!\n\nhttps://t.me/{MAIN_GROUP_USERNAME}\n\n1. Прочтите наши простые правила: (ссылка)\n2. Если вы хотите разместить у нас вакансию — прочтите это: (ссылка).\nМы удаляем вакансии, нарушающие наши правила публикации."
            )
        except Exception as e:
            logger.error(f"Couldn't notify user {user_id} about approval: {e}")
        
        # Update message and remove keyboard
        new_text = f"{original_text}\n\n✅ Request approved by {admin_name}"
        await query.edit_message_text(new_text)
        await query.edit_message_reply_markup(None)
        
    
    except Exception as e:
        logger.error(f"Error approving user {user_id}: {e}")

async def handle_verification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the verification response."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    _, selected = query.data.split('_')
    selected = int(selected)
    
    correct_option = context.user_data.get(f'correct_option_{user_id}')
	     
    if correct_option is None:
        await query.edit_message_text(
            "Session expired. Please use the group invite link again."
        )
        return
    
    try:
        if selected == correct_option:
            try:
                await context.bot.approve_chat_join_request(
                    chat_id=MAIN_GROUP_ID,
                    user_id=user_id
                )
                await query.edit_message_text(f"✅ Добро пожаловать в чат технических писателей!\n\nhttps://t.me/{MAIN_GROUP_USERNAME}\n\n1. Прочтите наши простые правила: (ссылка)\n2. Если вы хотите разместить у нас вакансию — прочтите это: (ссылка).\nМы удаляем вакансии, нарушающие наши правила публикации.")
            except Exception as e:
                logger.error(f"Error adding user to group: {e}")
                raise
        else:
            await query.edit_message_text("❌ Неправильный ответ. Напишите пару предложений о себе, добавив хештег #join, чтобы ваша заявка была обработана администраторами вручную.\n\nПример: '#join Здравствуйте! Меня зовут имярек, я хочу присоединиться к сообществу'.")
            
    except Exception as e:
        logger.error(f"Error processing verification: {e}")
        await query.edit_message_text(
            "An error occurred. Please contact an administrator."
        )
    finally:
        # Clean up user_data
        if f'correct_option_{user_id}' in context.user_data:
            del context.user_data[f'correct_option_{user_id}']

async def handle_hashtag_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages with #join hashtag."""
    if '#join' not in update.message.text:
        return
    
    user = update.message.from_user
    
    # Create approval/dismiss keyboard
    keyboard = [
        [
            InlineKeyboardButton("Approve", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("Dismiss", callback_data=f"dismiss_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    user_display_name = get_user_display_name(user)
    
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=f"<b>Join request from</b> <a href='tg://user?id={user.id}'>{user_display_name}</a>:\n\n{update.message.text}",
        reply_markup=reply_markup,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    await update.message.reply_text(
        "Your request has been forwarded to administrators."
    )

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("horoscope", get_horoscope))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(CallbackQueryHandler(handle_verification, pattern="^verify_"))
    app.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^(approve|dismiss)_"))
    app.add_handler(MessageHandler(filters.TEXT, handle_hashtag_message))

    print("Bot started...")
    app.run_polling()

if __name__ == '__main__':
    main()