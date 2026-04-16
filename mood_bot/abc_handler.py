from datetime import date

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import db

SITUATION, THOUGHTS, FEELINGS, COMMENT = range(4)


async def cmd_abc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📋 Новая запись КПТ ABC\n\n"
        "A — Что произошло? Опиши ситуацию."
    )
    return SITUATION


async def got_situation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["abc_situation"] = update.message.text
    await update.message.reply_text("B — Какие мысли и убеждения возникли?")
    return THOUGHTS


async def got_thoughts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["abc_thoughts"] = update.message.text
    await update.message.reply_text("C — Какие чувства и эмоции ты испытал?")
    return FEELINGS


async def got_feelings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["abc_feelings"] = update.message.text
    await update.message.reply_text(
        "Добавить комментарий? Напиши текст или /skip чтобы пропустить."
    )
    return COMMENT


async def got_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["abc_comment"] = update.message.text
    return await _save(update, context)


async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["abc_comment"] = None
    return await _save(update, context)


async def _save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    db.insert_abc_log(
        user_id=user_id,
        situation=context.user_data.pop("abc_situation"),
        thoughts=context.user_data.pop("abc_thoughts"),
        feelings=context.user_data.pop("abc_feelings"),
        comment=context.user_data.pop("abc_comment", None),
    )
    today = date.today().strftime("%d.%m.%Y")
    await update.message.reply_text(f"✅  ABC-запись сохранена  {today}")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


def build_abc_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("abc", cmd_abc)],
        states={
            SITUATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_situation)],
            THOUGHTS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_thoughts)],
            FEELINGS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_feelings)],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_comment),
                CommandHandler("skip", skip_comment),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
