import os
import json
from io import StringIO
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Настройка Google Sheets ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Получение данных из переменных окружения
google_creds_json = os.environ.get("GOOGLE_CREDS_JSON")
creds_dict = json.load(StringIO(google_creds_json))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ID или URL таблицы
SHEET_URL = 'https://docs.google.com/spreadsheets/d/11aoCE_devUaQBGCIgdMWljfUibPfJu0PrWIaMtYIJpI/edit'
sheet = client.open_by_url(SHEET_URL).sheet1

# === Константы состояний для ConversationHandler ===
SELECT_ACTION, VIEW_DATE, EDIT_DATE, EDIT_FIELD_SELECT, EDIT_FIELD_INPUT = range(5)
current_edit_data = {}

# === Обработка команды /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Посмотреть тренировку", "Изменить тренировку"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите дальнейшее действие:", reply_markup=reply_markup)
    return SELECT_ACTION

# === Обработка выбора действия ===
async def select_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Посмотреть тренировку":
        await update.message.reply_text("Введите дату тренировки (в формате ГГГГ-ММ-ДД):")
        return VIEW_DATE
    elif text == "Изменить тренировку":
        keyboard = [[KeyboardButton("Сегодня")]]
        await update.message.reply_text("Введите дату тренировки или нажмите 'Сегодня':", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))
        return EDIT_DATE
    else:
        await update.message.reply_text("Пожалуйста, выберите действие с кнопок.")
        return SELECT_ACTION

# === Поиск строки по дате ===
def find_row_by_date(date_str):
    dates = sheet.col_values(1)
    for idx, date in enumerate(dates[1:], start=2):
        if date.strip() == date_str:
            return idx
    return None

# === Получить значение из ячейки, или "Не заполнено" ===
def get_or_placeholder(cell):
    return cell if cell.strip() else "Не заполнено"

# === Обработка просмотра тренировки ===
async def view_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_input = update.message.text.strip()
    row = find_row_by_date(date_input)
    if row:
        values = sheet.row_values(row)
        date = get_or_placeholder(values[0] if len(values) > 0 else "")
        type_ = get_or_placeholder(values[1] if len(values) > 1 else "")
        training = get_or_placeholder(values[2] if len(values) > 2 else "")
        content = get_or_placeholder(values[3] if len(values) > 3 else "")
        goal = get_or_placeholder(values[4] if len(values) > 4 else "")
        msg = f"{date} {type_} тренировка. Подобранная нагрузка {training}, её объем и содержание {content}, её цель {goal}."
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("В данном периоде тренировок не предусмотрено.")
    return ConversationHandler.END

# === Обработка даты редактирования ===
async def edit_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_input = update.message.text.strip()
    if date_input.lower() == "сегодня":
        date_input = datetime.now().strftime('%Y-%m-%d')
    row = find_row_by_date(date_input)
    if not row:
        await update.message.reply_text("В данном периоде тренировок не предусмотрено.")
        return ConversationHandler.END
    context.user_data["edit_row"] = row
    context.user_data["edit_field_index"] = 2  # Начинаем с поля [Тренировка]
    context.user_data["fields"] = ["Тренировка", "Объем / Содержание", "Цель"]
    context.user_data["field_col_map"] = {0: 2, 1: 3, 2: 4}
    context.user_data["current_field"] = 0
    return await prompt_edit_field(update, context)

# === Запрос на изменение конкретного поля ===
async def prompt_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = context.user_data["edit_row"]
    field_idx = context.user_data["current_field"]
    field_name = context.user_data["fields"][field_idx]
    col_idx = context.user_data["field_col_map"][field_idx]
    current_value = sheet.cell(row, col_idx).value or "Не заполнено"
    keyboard = [["Не менять", "Добавить"]]
    await update.message.reply_text(f"Заполните поле [{field_name}], текущие данные: {current_value}", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return EDIT_FIELD_SELECT

# === Обработка выбора действия с полем ===
async def edit_field_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice == "Не менять":
        return await next_edit_step(update, context)
    elif choice == "Добавить":
        context.user_data["mode"] = "append"
        await update.message.reply_text("Введите дополнительную информацию:")
        return EDIT_FIELD_INPUT
    else:
        context.user_data["mode"] = "replace"
        await update.message.reply_text("Введите новое значение:")
        return EDIT_FIELD_INPUT

# === Обработка ввода данных ===
async def edit_field_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text.strip()
    row = context.user_data["edit_row"]
    field_idx = context.user_data["current_field"]
    col_idx = context.user_data["field_col_map"][field_idx]
    current_value = sheet.cell(row, col_idx).value or ""
    if context.user_data.get("mode") == "append":
        new_value = current_value + " " + new_text if current_value else new_text
    else:
        new_value = new_text
    sheet.update_cell(row, col_idx, new_value)
    return await next_edit_step(update, context)

# === Переход к следующему полю ===
async def next_edit_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_field"] += 1
    if context.user_data["current_field"] >= len(context.user_data["fields"]):
        await update.message.reply_text("Данные по тренировке обновлены.")
        return ConversationHandler.END
    return await prompt_edit_field(update, context)

# === Запуск бота ===
if __name__ == "__main__":
    token = os.environ.get("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_action)],
            VIEW_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, view_date)],
            EDIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date)],
            EDIT_FIELD_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_select)],
            EDIT_FIELD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field_input)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.run_polling()
