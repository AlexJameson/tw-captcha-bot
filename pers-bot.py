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

# First captcha question
FIRST_QUESTION = "[1/2]Почему вы хотите присоединиться? Выбирайте внимательно!"
FIRST_OPTIONS = [
    "Я человек",
    "Нет",
    "Интересуюсь технической документацией",
    "Я не робот"
]
FIRST_CORRECT_ANSWER = "Интересуюсь технической документацией"

# Second question (with emojis)
CORRECT_EMOJI = "🔥"
SECOND_QUESTION = f"[2/2]Выберите такой же эмодзи: {CORRECT_EMOJI}"
SECOND_OPTIONS = ["🟢", "⭐", "🔵", "🔥"]
SECOND_CORRECT_ANSWER = "🔥"

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
        'not_requested_join': False,
        'is_dismissed': False
    }, User.user_id == user.id)

    # Initialize question number
    context.user_data[f'question_{user.id}'] = 1
    
    # Randomize first question options
    shuffled_options = FIRST_OPTIONS.copy()
    random.shuffle(shuffled_options)
    
    # Find the index of correct answer in shuffled options
    correct_option = shuffled_options.index(FIRST_CORRECT_ANSWER)
    
    # Store correct option index in user_data
    context.user_data[f'correct_option_{user.id}'] = correct_option
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"verify_1_{i}")]
        for i, option in enumerate(shuffled_options)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=f"Здравствуйте! Пройдите верификацию, чтобы вступить:\n\n{FIRST_QUESTION}",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Could not send message to user {user.id}: {e}")
        await join_request.decline()

async def show_second_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Show the second question with emoji options."""
    # Randomize emoji options
    shuffled_options = SECOND_OPTIONS.copy()
    random.shuffle(shuffled_options)
    
    # Find the index of correct answer in shuffled options
    correct_option = shuffled_options.index(SECOND_CORRECT_ANSWER)
    
    # Store correct option index in user_data
    context.user_data[f'correct_option_{user_id}'] = correct_option
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"verify_2_{i}")]
        for i, option in enumerate(shuffled_options)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text=SECOND_QUESTION,
        reply_markup=reply_markup
    )

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    admin = query.from_user
    admin_name = get_user_display_name(admin)
    
    # Verify admin rights
    chat_member = await context.bot.get_chat_member(MAIN_GROUP_ID, admin.id)
    if chat_member.status not in ['administrator', 'creator']:
        await query.answer("You're not an admin!")
        return

    action, user_id = query.data.split('_')
    user_id = int(user_id)
    
    # Get original message text
    original_text = query.message.text
    
    if action == "dismiss":
        try:
            await context.bot.decline_chat_join_request(
                chat_id=MAIN_GROUP_ID,
                user_id=user_id
            )
            
            # Danger! Dismiss user forever
            db.update({'is_dismissed': True}, User.user_id == user_id)
            
            # Update admin message
            new_text = f"{original_text}\n\n❌ Заявка отклонена {admin_name}"
            await query.edit_message_text(new_text)
            await query.edit_message_reply_markup(None)
            
            # Notify user about dismissal
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Ваша заявка была отклонена администрацией."
                )
            except Exception as e:
                logger.error(f"Couldn't notify user {user_id} about dismissal: {e}")
                
        except Exception as e:
            logger.error(f"Error dismissing user {user_id}: {e}")
            # await query.answer(f"Error: {str(e)}", show_alert=True)
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
        
        # Update database
        db.update({'pending_review': False, 'not_requested_join': True}, User.user_id == user_id)

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
    
    _, question_num, selected = query.data.split('_')
    question_num = int(question_num)
    selected = int(selected)
    
    correct_option = context.user_data.get(f'correct_option_{user_id}')
    
    if correct_option is None:
        await query.edit_message_text(
            "Истекло время сессии."
        )
        return
    
    try:
        if selected == correct_option:
            if question_num == 1:
                # First question correct, show second question
                context.user_data[f'question_{user_id}'] = 2
                await show_second_question(update, context, user_id)
            else:
                # Second question correct, approve join request
                try:
                    await context.bot.approve_chat_join_request(
                        chat_id=MAIN_GROUP_ID,
                        user_id=user_id
                    )

                    await query.edit_message_text(f"✅ Добро пожаловать в чат технических писателей!\n\nhttps://t.me/{MAIN_GROUP_USERNAME}\n\n1. Прочтите наши простые правила: (ссылка)\n2. Если вы хотите разместить у нас вакансию — прочтите это: (ссылка).\nМы удаляем вакансии, нарушающие наши правила публикации.")
                    
                    db.update({'not_requested_join': True}, User.user_id == user_id)
                    
                except Exception as e:
                    logger.error(f"Error adding user to group: {e}")
                    raise
        else:
            await query.edit_message_text("❌ Неправильный ответ. Напишите пару предложений о себе, добавив хештег #join, чтобы ваша заявка отправилась к администраторам.\n\nПример: «#join Здравствуйте! Я хочу стать техническим писателем. Вступаю, чтобы получить совет от участников сообщества.»")
            
    except Exception as e:
        logger.error(f"Error processing verification: {e}")
        await query.edit_message_text(
            "An error occurred. Please contact an administrator."
        )
    finally:
        # Clean up user_data if finished or failed
        if question_num == 2 or selected != correct_option:
            if f'correct_option_{user_id}' in context.user_data:
                del context.user_data[f'correct_option_{user_id}']
            if f'question_{user_id}' in context.user_data:
                del context.user_data[f'question_{user_id}']

async def handle_hashtag_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages with #join hashtag."""
    if update.effective_chat.type != 'private':
        return
    message = update.message
    message_text = message.text.strip()
    user = message.from_user

    user_record = db.get(User.user_id == user.id)
    # Check if a user is dismissed:
    if user_record and user_record.get('is_dismissed'):
        await message.reply_text(
            "Вход запрещён."
        )
        return

    # Check if user already has a pending request
    if user_record and user_record.get('pending_review'):
        await message.reply_text(
            "Ваша заявка уже рассматривается."
        )
        return

    # Check if user already has a pending request
    if not user_record or user_record.get('not_requested_join'):
        await update.message.reply_text(
            "Сначала нажмите «Подать заявку на вступление» в чате."
        )
        return

    if message_text == '#join' or '#join' not in message_text:
        await update.message.reply_text(
            "Сообщение должно содержать хештег и пару предложений о себе."
        )
        return 

    # Store/Update user's request
    db.upsert({
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'pending_review': True,
    }, User.user_id == user.id)
    
    # Create admin notification message with buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"dismiss_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    user_display_name = get_user_display_name(user)
    
    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=f"<b>Заявка от </b><a href='tg://user?id={user.id}'>{user_display_name}</a>:\n\n{update.message.text}",
        reply_markup=reply_markup,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    await update.message.reply_text(
        "Сообщение отправлено администрации."
    )

def main():
    app = Application.builder().token(TOKEN).build()
    
    #app.add_handler(CommandHandler("horoscope", get_horoscope))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(CallbackQueryHandler(handle_verification, pattern="^verify_"))
    app.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^(approve|dismiss)_"))
    app.add_handler(MessageHandler(filters.TEXT, handle_hashtag_message))

    print("Bot started...")
    app.run_polling()

if __name__ == '__main__':
    main()