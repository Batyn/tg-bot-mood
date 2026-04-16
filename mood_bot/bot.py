import logging
import os
from datetime import date, datetime, timedelta

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
from abc_handler import build_abc_handler
from excel import _fmt_time_cell, build_abc_excel
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


def _parse_date(s: str) -> str:
    return datetime.strptime(s, "%d.%m.%Y").strftime("%Y-%m-%d")


def _fmt_date(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def _fmt_score(score: int) -> str:
    return f"+{score}" if score > 0 else str(score)


def _score_dot(score: int) -> str:
    if score > 0:
        return "🟢"
    if score < 0:
        return "🔴"
    return "🔵"


def _parse_period(args: list[str]) -> tuple[str, str, str]:
    """Возвращает (date_from, date_to, period_label). Бросает ValueError при ошибке."""
    if len(args) == 0:
        today = str(date.today())
        return today, today, "сегодня"
    if len(args) == 1:
        days = int(args[0])
        date_from, date_to = _date_range_from_days(days)
        return date_from, date_to, f"последние {days} дн."
    if len(args) == 2:
        date_from = _parse_date(args[0])
        date_to = _parse_date(args[1])
        return date_from, date_to, f"{args[0]} — {args[1]}"
    raise ValueError("wrong args")


# ── /start и /mode ────────────────────────────────────────────────────────

_MODE_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("📊 Трекер настроения", callback_data="set_mode_mood"),
    InlineKeyboardButton("📋 КПТ ABC", callback_data="set_mode_abc"),
]])

_MODE_NAMES = {"mood": "📊 Трекер настроения", "abc": "📋 КПТ ABC"}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"Привет, {name}! 👋\n\n"
        "Я помогаю вести дневник — отслеживать настроение и анализировать мысли.\n\n"
        "Выбери режим работы:",
        reply_markup=_MODE_KEYBOARD,
    )


async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current = db.get_user_mode(user_id)
    await update.message.reply_text(
        f"Текущий режим: {_MODE_NAMES[current]}\n\nВыбери режим:",
        reply_markup=_MODE_KEYBOARD,
    )


async def mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if query.data == "set_mode_mood":
        db.set_user_mode(user_id, "mood")
        await query.edit_message_text(
            "Режим: 📊 Трекер настроения\n\n"
            "Просто пиши что происходит и ставь оценку от -10 до +10.\n\n"
            "Примеры:\n"
            "  хороший завтрак +3\n"
            "  -8 ссора с мужем\n"
            "  11-15 работал +3\n\n"
            "Команды:\n"
            "  /stats — статистика\n"
            "  /export — Excel\n"
            "  /mode — сменить режим\n"
            "  /help — справка"
        )
    elif query.data == "set_mode_abc":
        db.set_user_mode(user_id, "abc")
        await query.edit_message_text(
            "Режим: 📋 КПТ ABC\n\n"
            "Веди дневник по методу КПТ: ситуация → мысли → чувства.\n\n"
            "Команды:\n"
            "  /abc — новая запись\n"
            "  /stats — список записей\n"
            "  /export — Excel\n"
            "  /mode — сменить режим\n"
            "  /help — справка"
        )


# ── Трекер настроения — ввод сообщения ───────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    mode = db.get_user_mode(user_id)

    if mode == "abc":
        await update.message.reply_text(
            "Ты в режиме КПТ ABC.\n"
            "Напиши /abc чтобы создать новую запись, или /mode чтобы сменить режим."
        )
        return

    text = update.message.text or ""
    result = parse_message(text)
    if result is None:
        await update.message.reply_text(
            "Не нашла оценку. Напиши например: хороший день +6"
        )
        return

    score, description, start_time, end_time = result
    row = db.insert_log(user_id, score, description, start_time, end_time)

    created_at: str = row["created_at"]
    date_fmt = _fmt_date(created_at.split(" ")[0])
    time_display = _fmt_time_cell(created_at, row["end_time"])
    time_note = " (время из сообщения)" if start_time is not None else ""
    await update.message.reply_text(
        f"✅  {date_fmt} {time_display}{time_note}  {_score_dot(score)} {_fmt_score(score)}  {description}"
    )


# ── /stats ────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    mode = db.get_user_mode(user_id)

    try:
        date_from, date_to, period_label = _parse_period(context.args or [])
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Использование:\n/stats\n/stats 7\n/stats 01.04.2025 16.04.2025"
        )
        return

    if mode == "mood":
        await _stats_mood(update, user_id, date_from, date_to, period_label)
    else:
        await _stats_abc(update, user_id, date_from, date_to, period_label)


async def _stats_mood(update, user_id, date_from, date_to, period_label):
    stats = db.fetch_stats(user_id, date_from, date_to)
    cnt, total, avg = stats["cnt"], stats["total"], stats["avg_score"]

    if cnt == 0:
        await update.message.reply_text(f"За период «{period_label}» записей нет.")
        return

    rows = db.fetch_rows(user_id, date_from, date_to)
    avg_fmt = f"+{avg}" if avg and avg > 0 else str(avg)

    lines = [
        f"📊 Трекер настроения — {period_label}", "",
        f"Записей:        {cnt}",
        f"Сумма баллов:   {_fmt_score(total)}",
        f"Средняя оценка: {avg_fmt}", "",
    ]
    for row in rows:
        date_part = _fmt_date(row["created_at"].split(" ")[0])
        time_str = _fmt_time_cell(row["created_at"], row["end_time"])
        score_str = f'{_score_dot(row["score"])} "{_fmt_score(row["score"])}"'
        lines.append(f"* {date_part}, {time_str}, {row['description']} {score_str}")

    text = "\n".join(lines)
    await update.message.reply_text(text[:4090] + "\n…" if len(text) > 4096 else text)


async def _stats_abc(update, user_id, date_from, date_to, period_label):
    rows = db.fetch_abc_rows(user_id, date_from, date_to)

    if not rows:
        await update.message.reply_text(f"За период «{period_label}» записей нет.")
        return

    lines = [f"📋 КПТ ABC — {period_label} — {len(rows)} записей", ""]
    for row in rows:
        date_part = _fmt_date(row["created_at"].split(" ")[0])
        time_part = row["created_at"].split(" ")[1][:5]
        lines.append(f"📅 {date_part}, {time_part}")
        lines.append(f"  A: {row['situation']}")
        lines.append(f"  B: {row['thoughts']}")
        lines.append(f"  C: {row['feelings']}")
        if row["comment"]:
            lines.append(f"  💬 {row['comment']}")
        lines.append("")

    text = "\n".join(lines)
    await update.message.reply_text(text[:4090] + "\n…" if len(text) > 4096 else text)


# ── /export ───────────────────────────────────────────────────────────────

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    mode = db.get_user_mode(user_id)

    try:
        date_from, date_to, period_label = _parse_period(context.args or [])
    except (ValueError, IndexError):
        await update.message.reply_text(
            "Использование:\n/export\n/export 7\n/export 01.04.2025 16.04.2025"
        )
        return

    if mode == "mood":
        await _export_mood(update, user_id, date_from, date_to, period_label)
    else:
        await _export_abc(update, user_id, date_from, date_to, period_label)


async def _export_mood(update, user_id, date_from, date_to, period_label):
    rows = db.fetch_rows(user_id, date_from, date_to)
    if not rows:
        await update.message.reply_text(f"За период «{period_label}» записей нет.")
        return

    stats = db.fetch_stats(user_id, date_from, date_to)
    total = stats["total"]

    lines = []
    for row in rows:
        date_part = _fmt_date(row["created_at"].split(" ")[0])
        time_str = _fmt_time_cell(row["created_at"], row["end_time"])
        score_str = f'{_score_dot(row["score"])} "{_fmt_score(row["score"])}"'
        lines.append(f"* {date_part}, {time_str}, {row['description']} {score_str}")
    lines.append(f"\nИтого: {_fmt_score(total)}")

    text_list = "\n".join(lines)
    await update.message.reply_text(text_list[:4090] + "\n…" if len(text_list) > 4096 else text_list)

    filename = f"mood_{date_from}_{date_to}.xlsx"
    buf = excel.build_excel(rows, total)
    await update.message.reply_document(
        document=buf, filename=filename,
        caption=f"📎 Трекер за {period_label} ({len(rows)} записей, итого {_fmt_score(total)})",
    )


async def _export_abc(update, user_id, date_from, date_to, period_label):
    rows = db.fetch_abc_rows(user_id, date_from, date_to)
    if not rows:
        await update.message.reply_text(f"За период «{period_label}» записей нет.")
        return

    filename = f"abc_{date_from}_{date_to}.xlsx"
    buf = build_abc_excel(rows)
    await update.message.reply_document(
        document=buf, filename=filename,
        caption=f"📎 КПТ ABC за {period_label} ({len(rows)} записей)",
    )


# ── /delete и /deleteall ──────────────────────────────────────────────────

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    mode = db.get_user_mode(user_id)

    if mode == "mood":
        row = db.get_last_log(user_id)
        if not row:
            await update.message.reply_text("Записей нет.")
            return
        created_at = row["created_at"]
        time_str = _fmt_time_cell(created_at, row["end_time"])
        score_str = f'{_score_dot(row["score"])} {_fmt_score(row["score"])}'
        preview = f"{_fmt_date(created_at.split(' ')[0])}, {time_str}, {row['description']} {score_str}"
        cb = "delete_last_mood"
    else:
        row = db.get_last_abc_log(user_id)
        if not row:
            await update.message.reply_text("Записей нет.")
            return
        date_part = _fmt_date(row["created_at"].split(" ")[0])
        preview = f"{date_part}\n  A: {row['situation']}\n  B: {row['thoughts']}\n  C: {row['feelings']}"
        cb = "delete_last_abc"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Да, удалить", callback_data=cb),
        InlineKeyboardButton("Отмена", callback_data="delete_cancel"),
    ]])
    await update.message.reply_text(f"⚠️ Удалить последнюю запись?\n{preview}", reply_markup=keyboard)


async def cmd_deleteall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    mode = db.get_user_mode(user_id)
    cb = "deleteall_mood" if mode == "mood" else "deleteall_abc"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Да, удалить всё", callback_data=cb),
        InlineKeyboardButton("Отмена", callback_data="delete_cancel"),
    ]])
    await update.message.reply_text("⚠️ Удалить все свои записи? Это действие необратимо.", reply_markup=keyboard)


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data == "delete_last_mood":
        row = db.delete_last_log(user_id)
        await query.edit_message_text("Последняя запись удалена 🗑" if row else "Записей нет.")
    elif data == "delete_last_abc":
        row = db.delete_last_abc_log(user_id)
        await query.edit_message_text("Последняя ABC-запись удалена 🗑" if row else "Записей нет.")
    elif data == "deleteall_mood":
        count = db.delete_user_logs(user_id)
        await query.edit_message_text(f"Удалено записей трекера: {count} 🗑")
    elif data == "deleteall_abc":
        count = db.delete_user_abc_logs(user_id)
        await query.edit_message_text(f"Удалено ABC-записей: {count} 🗑")
    else:
        await query.edit_message_text("Отменено.")


# ── /help ─────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    mode = db.get_user_mode(user_id)

    if mode == "mood":
        await update.message.reply_text(
            "📊 Режим: Трекер настроения\n\n"
            "Просто напиши сообщение с оценкой (число со знаком + или -).\n"
            "Шкала оценки от -10 до +10.\n"
            "Оценка может быть в любом месте текста.\n\n"
            "Примеры:\n"
            "  проснулась с мыслями о нём, +5\n"
            "  -8 ссора с мужем\n"
            "  хороший завтрак +3\n\n"
            "🕐 Можно указать время:\n"
            "  11:00 завтракал с женой +3\n"
            "  в 5 вечера прогулка +7\n"
            "  11 утра хороший кофе +4\n"
            "  в 3 ночи не мог уснуть -5\n\n"
            "  Можно добавлять промежутки:\n"
            "  11-15 работал +3\n"
            "  с 11 до 15 работал +3\n\n"
            "📊 Команды:\n"
            "  /stats — статистика за сегодня\n"
            "  /stats 7 — за последние 7 дней\n"
            "  /stats 01.04.2025 16.04.2025 — за период\n"
            "  /export — скачать Excel за сегодня\n"
            "  /export 7 — скачать Excel за 7 дней\n"
            "  /export 01.04.2025 16.04.2025 — Excel за период\n"
            "  /delete — удалить последнюю запись\n"
            "  /deleteall — удалить все свои записи\n"
            "  /mode — переключить режим\n"
            "  /help — эта справка"
        )
    else:
        await update.message.reply_text(
            "📋 Режим: КПТ ABC\n\n"
            "Метод КПТ помогает анализировать ситуации через три шага:\n"
            "  A — Ситуация (что произошло)\n"
            "  B — Мысли и убеждения\n"
            "  C — Чувства и эмоции\n\n"
            "Команды:\n"
            "  /abc — создать новую запись\n"
            "  /cancel — отменить текущую запись\n"
            "  /stats — список записей за сегодня\n"
            "  /stats 7 — за последние 7 дней\n"
            "  /stats 01.04.2025 16.04.2025 — за период\n"
            "  /export — скачать Excel за сегодня\n"
            "  /export 7 — скачать Excel за 7 дней\n"
            "  /export 01.04.2025 16.04.2025 — Excel за период\n"
            "  /delete — удалить последнюю запись\n"
            "  /deleteall — удалить все свои записи\n"
            "  /mode — переключить режим\n"
            "  /help — эта справка"
        )


# ── Запуск ────────────────────────────────────────────────────────────────

def main() -> None:
    db.init_db()
    logger.info("База данных инициализирована.")

    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler должен быть до общего MessageHandler
    app.add_handler(build_abc_handler())

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("deleteall", cmd_deleteall))
    app.add_handler(CallbackQueryHandler(mode_callback, pattern="^set_mode_"))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern="^delete"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
