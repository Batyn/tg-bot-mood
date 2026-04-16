import logging
import os
from datetime import date, timedelta

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db
import excel
from excel import _fmt_time_cell
from parser import parse_message

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Вспомогательные функции ────────────────────────────────────────────────

def _date_range_from_days(days: int) -> tuple[str, str]:
    today = date.today()
    return str(today - timedelta(days=days - 1)), str(today)


def _fmt_score(score: int) -> str:
    return f"+{score}" if score > 0 else str(score)


def _score_dot(score: int) -> str:
    if score > 0:
        return "🟢"
    if score < 0:
        return "🔴"
    return "🔵"


# ── Обработчики команд ────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    user_id = update.effective_user.id

    result = parse_message(text)
    if result is None:
        await update.message.reply_text(
            "Не нашла оценку. Напиши например: хороший день +6"
        )
        return

    score, description, custom_time = result
    row = db.insert_log(user_id, score, description, custom_time)

    created_at: str = row["created_at"]  # "2025-04-16 14:30:00"
    time_note = " (время из сообщения)" if custom_time is not None else ""
    await update.message.reply_text(
        f"Записала ✅  {created_at}{time_note}  {_score_dot(score)} {_fmt_score(score)}  {description}"
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /stats 7             — последние 7 дней
    /stats 2025-04-01 2025-04-16  — конкретный период
    """
    args = context.args or []
    user_id = update.effective_user.id

    try:
        if len(args) == 1:
            days = int(args[0])
            date_from, date_to = _date_range_from_days(days)
            period_label = f"последние {days} дн."
        elif len(args) == 2:
            date_from, date_to = args[0], args[1]
            # Быстрая валидация формата
            date.fromisoformat(date_from)
            date.fromisoformat(date_to)
            period_label = f"{date_from} — {date_to}"
        else:
            raise ValueError("wrong args")
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Использование:\n"
            "/stats 7\n"
            "/stats 2025-04-01 2025-04-16"
        )
        return

    stats = db.fetch_stats(user_id, date_from, date_to)
    cnt = stats["cnt"]
    total = stats["total"]
    avg = stats["avg_score"]

    if cnt == 0:
        await update.message.reply_text(f"За период «{period_label}» записей нет.")
        return

    rows = db.fetch_rows(user_id, date_from, date_to)
    avg_fmt = f"+{avg}" if avg and avg > 0 else str(avg)

    lines = [
        f"📊 Статистика за {period_label}",
        f"",
        f"Записей:        {cnt}",
        f"Сумма баллов:   {_fmt_score(total)}",
        f"Средняя оценка: {avg_fmt}",
        f"",
    ]
    for row in rows:
        date_part = row["created_at"].split(" ")[0]
        time_str = _fmt_time_cell(row["created_at"], row["description"])
        score_str = f'{_score_dot(row["score"])} "{_fmt_score(row["score"])}"'
        lines.append(f"* {date_part}, {time_str}, {row['description']} {score_str}")

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4090] + "\n…"

    await update.message.reply_text(text)


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /export 7            — Excel за последние 7 дней
    /export 2025-04-01 2025-04-16
    """
    args = context.args or []
    user_id = update.effective_user.id

    try:
        if len(args) == 1:
            days = int(args[0])
            date_from, date_to = _date_range_from_days(days)
            period_label = f"последние {days} дн."
            filename = f"mood_{days}d.xlsx"
        elif len(args) == 2:
            date_from, date_to = args[0], args[1]
            date.fromisoformat(date_from)
            date.fromisoformat(date_to)
            period_label = f"{date_from} — {date_to}"
            filename = f"mood_{date_from}_{date_to}.xlsx"
        else:
            raise ValueError("wrong args")
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Использование:\n"
            "/export 7\n"
            "/export 2025-04-01 2025-04-16"
        )
        return

    rows = db.fetch_rows(user_id, date_from, date_to)
    if not rows:
        await update.message.reply_text(f"За период «{period_label}» записей нет.")
        return

    stats = db.fetch_stats(user_id, date_from, date_to)

    # Текстовый список
    lines = []
    for row in rows:
        date_part = row["created_at"].split(" ")[0]
        time_str = _fmt_time_cell(row["created_at"], row["description"])
        score_str = f'{_score_dot(row["score"])} "{_fmt_score(row["score"])}"'
        lines.append(f"* {date_part}, {time_str}, {row['description']} {score_str}")

    total = stats["total"]
    lines.append(f"\nИтого: {_fmt_score(total)}")

    # Telegram ограничивает сообщение 4096 символами — режем если нужно
    text_list = "\n".join(lines)
    if len(text_list) > 4096:
        text_list = text_list[:4090] + "\n…"

    await update.message.reply_text(text_list)

    buf = excel.build_excel(rows, total)
    await update.message.reply_document(
        document=buf,
        filename=filename,
        caption=f"📎 Настроение за {period_label} ({len(rows)} записей, итого {_fmt_score(total)})",
    )


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Да, удалить всё", callback_data="delete_confirm"),
            InlineKeyboardButton("Отмена", callback_data="delete_cancel"),
        ]
    ])
    await update.message.reply_text(
        "⚠️ Удалить все твои записи? Это действие необратимо.",
        reply_markup=keyboard,
    )


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if query.data == "delete_confirm":
        count = db.delete_user_logs(user_id)
        await query.edit_message_text(f"Удалено записей: {count} 🗑")
    else:
        await query.edit_message_text("Отменено.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📝 Как записывать настроение:\n"
        "Просто напиши сообщение с оценкой (число со знаком + или -).\n"
        "Оценка может быть в любом месте текста.\n\n"
        "Примеры:\n"
        "  проснулась с мыслями о нём, +5\n"
        "  -8 ссора с мужем\n"
        "  хороший завтрак +3\n"
        "  +10 путешествие с мужем\n\n"
        "🕐 Можно указать время — тогда запись сохранится с ним:\n"
        "  11:00 завтракал с женой -3\n"
        "  в 5 вечера прогулка +7\n"
        "  11 утра хороший кофе +4\n"
        "  в 3 ночи не мог уснуть -5\n\n"
        "📊 Команды:\n"
        "  /stats 7 — статистика за последние 7 дней\n"
        "  /stats 2025-04-01 2025-04-16 — за период\n"
        "  /export 7 — скачать Excel за 7 дней\n"
        "  /export 2025-04-01 2025-04-16 — Excel за период\n"
        "  /delete — удалить все свои записи\n"
        "  /help — эта справка"
    )


# ── Запуск ────────────────────────────────────────────────────────────────

def main() -> None:
    db.init_db()
    logger.info("База данных инициализирована.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern="^delete_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
