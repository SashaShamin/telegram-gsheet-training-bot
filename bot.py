import os
import telebot
from telebot import types
import gspread
from datetime import datetime, date
from oauth2client.service_account import ServiceAccountCredentials
import json

# 🔐 Переменные окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_SHEET_NAME = os.environ.get('GOOGLE_SHEET_NAME')
GOOGLE_CREDS = os.environ.get('GOOGLE_CREDS_JSON')  # Railway secret — JSON строка

# 📌 Авторизация в Google Sheets
creds_dict = json.loads(GOOGLE_CREDS)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
sheet = client.open_by_key(SHEET_ID).sheet1

# 🤖 Запуск Telegram бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)

user_states = {}

@bot.message_handler(commands=['start'])
def handle_start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Посмотреть тренировку", "Изменить тренировку")
    bot.send_message(message.chat.id, "Выберите дальнейшее действие:", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if text == "Посмотреть тренировку":
        bot.send_message(chat_id, "Введите дату тренировки (в формате ГГГГ-ММ-ДД):")
        user_states[chat_id] = {"action": "view"}
        return

    if text == "Изменить тренировку":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Сегодня")
        bot.send_message(chat_id, "Введите дату тренировки или нажмите 'Сегодня':", reply_markup=markup)
        user_states[chat_id] = {"action": "edit"}
        return

    if chat_id in user_states and "action" in user_states[chat_id]:
        state = user_states[chat_id]
        action = state["action"]

        if text == "Сегодня":
            input_date = date.today()
        else:
            try:
                input_date = datetime.strptime(text, '%Y-%m-%d').date()
            except ValueError:
                bot.send_message(chat_id, "Неверный формат даты. Введите в формате ГГГГ-ММ-ДД.")
                return

        rows = sheet.get_all_values()
        found_row = None

        for row in rows[1:]:
            try:
                row_date = datetime.strptime(row[3], '%d.%m.%Y').date()
                if row_date == input_date:
                    found_row = row
                    break
            except:
                continue

        if not found_row:
            bot.send_message(chat_id, "В данном периоде тренировок не предусмотрено.")
            return

        if action == "view":
            msg = f"{row[3]} {row[4]} тренировка.\nПодобранная нагрузка: {row[5]},\nОбъем и содержание: {row[6]},\nЦель: {row[7]}."
            bot.send_message(chat_id, msg)
            user_states.pop(chat_id)
            return

        elif action == "edit":
            state["edit_row"] = found_row
            state["date_obj"] = input_date
            ask_next_field(chat_id, 0)
            return

edit_fields = ["Тренировка", "Объем / Содержание", "Цель"]

def ask_next_field(chat_id, index):
    if index >= len(edit_fields):
        bot.send_message(chat_id, "Данные по тренировке обновлены.")
        user_states.pop(chat_id)
        return

    field_name = edit_fields[index]
    user_states[chat_id]["edit_index"] = index
    col_index = get_column_index(field_name)
    row = user_states[chat_id]["edit_row"]
    current = row[col_index] if col_index < len(row) else "Не заполнено"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Не менять", "Добавить")
    bot.send_message(chat_id, f"Заполните поле '{field_name}', текущее значение: {current}", reply_markup=markup)

@bot.message_handler(func=lambda message: message.chat.id in user_states and "edit_index" in user_states[message.chat.id])
def handle_editing(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = user_states[chat_id]
    index = state["edit_index"]
    field_name = edit_fields[index]
    col_index = get_column_index(field_name)

    row_number = get_row_number_by_date(state["date_obj"])
    if not row_number:
        bot.send_message(chat_id, "Ошибка: не удалось найти строку по дате.")
        user_states.pop(chat_id)
        return

    if text == "Не менять":
        ask_next_field(chat_id, index + 1)
        return

    elif text == "Добавить":
        bot.send_message(chat_id, "Введите дополнительную информацию:")
        user_states[chat_id]["awaiting_append"] = True
        return

    else:
        sheet.update_cell(row_number, col_index + 1, text)
        ask_next_field(chat_id, index + 1)

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id].get("awaiting_append"))
def handle_append(message):
    chat_id = message.chat.id
    text = message.text.strip()
    state = user_states[chat_id]
    index = state["edit_index"]
    field_name = edit_fields[index]
    col_index = get_column_index(field_name)

    row_number = get_row_number_by_date(state["date_obj"])
    old_value = sheet.cell(row_number, col_index + 1).value or ""
    new_value = old_value + " " + text

    sheet.update_cell(row_number, col_index + 1, new_value.strip())
    state.pop("awaiting_append")
    ask_next_field(chat_id, index + 1)

def get_row_number_by_date(target_date):
    rows = sheet.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        try:
            row_date = datetime.strptime(row[3], "%d.%m.%Y").date()
            if row_date == target_date:
                return i
        except:
            continue
    return None

def get_column_index(column_name):
    headers = sheet.row_values(1)
    mapping = {
        "Тренировка": 5,
        "Объем / Содержание": 6,
        "Цель": 7
    }
    return mapping.get(column_name, -1)

# ✅ Запуск бота
bot.polling(none_stop=True)
