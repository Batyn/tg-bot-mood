import io
import sqlite3
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter


def build_excel(rows: list[sqlite3.Row], total: int) -> io.BytesIO:
    """
    Принимает строки из БД (created_at, score, description) и итоговую сумму.
    Возвращает BytesIO с .xlsx-файлом.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Настроение"

    # ── Заголовки ──────────────────────────────────────────────
    headers = ["Дата", "Время", "Описание", "Оценка"]
    header_fill = PatternFill("solid", fgColor="4F81BD")
    header_font = Font(bold=True, color="FFFFFF")

    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # ── Данные ─────────────────────────────────────────────────
    for row_idx, row in enumerate(rows, start=2):
        created_at: str = row["created_at"]   # "2025-04-16 14:30:00"
        date_part, time_part = created_at.split(" ")

        ws.cell(row=row_idx, column=1, value=date_part)
        ws.cell(row=row_idx, column=2, value=time_part)
        ws.cell(row=row_idx, column=3, value=row["description"])
        score_cell = ws.cell(row=row_idx, column=4, value=row["score"])
        score_cell.alignment = Alignment(horizontal="center")

        # Цветовая индикация оценки
        if row["score"] > 0:
            score_cell.font = Font(color="375623")
        elif row["score"] < 0:
            score_cell.font = Font(color="9C0006")

    # ── Итоговая строка ────────────────────────────────────────
    total_row = len(rows) + 2
    ws.cell(row=total_row, column=3, value="ИТОГО").font = Font(bold=True)
    total_cell = ws.cell(row=total_row, column=4, value=total)
    total_cell.font = Font(bold=True)
    total_cell.alignment = Alignment(horizontal="center")

    # ── Ширина колонок ─────────────────────────────────────────
    widths = [12, 10, 40, 8]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
