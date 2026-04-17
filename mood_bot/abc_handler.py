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
    situation = context.user_data.get("abc_situation")
    thoughts  = context.user_data.get("abc_thoughts")
    feelings  = context.user_data.get("abc_feelings")
    comment   = context.user_data.get("abc_comment")

    if not situation or not thoughts or not feelings:
        await update.message.reply_text(
            "Что-то пошло не так — данные потерялись. Начни заново с /abc."
        )
        context.user_data.clear()
        return ConversationHandler.END

    db.insert_abc_log(
        user_id=user_id,
        situation=situation,
        thoughts=thoughts,
        feelings=feelings,
        comment=comment,
    )
    for key in ("abc_situation", "abc_thoughts", "abc_feelings", "abc_comment"):
        context.user_data.pop(key, None)

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
        persistent=True,
        name="abc_conversation",
    )
