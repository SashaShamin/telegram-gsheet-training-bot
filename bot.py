import os
import telebot
import gspread
from datetime import datetime, date
from oauth2client.service_account import ServiceAccountCredentials

# 🔐 Переменные окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_SHEET_NAME = os.environ.get('GOOGLE_SHEET_NAME')
GOOGLE_CREDS = os.environ.get('GOOGLE_CREDS_JSON')  # Railway secret — JSON строка


bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Google Sheets авторизация
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
sheet = client.open_by_key(SHEET_ID).sheet1


user_state = {}
TEMP_DATA = {}

COLUMN_MAP = {
    'date': 4,
    'type': 5,
    'training': 6,
    'volume': 7,
    'goal': 8
}

def find_row_by_date(search_date):
    rows = sheet.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        try:
            row_date = datetime.strptime(row[3], "%d.%m.%Y").date()
            if row_date == search_date:
                return i, row
        except:
            continue
    return None, None

@bot.message_handler(commands=['start'])
def start_message(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Посмотреть тренировку", "Изменить тренировку")
    bot.send_message(message.chat.id, "Выберите дальнейшее действие:", reply_markup=markup)
    user_state[message.chat.id] = "choose_action"

@bot.message_handler(func=lambda msg: user_state.get(msg.chat.id) == "choose_action")
def choose_action(message):
    if message.text == "Посмотреть тренировку":
        bot.send_message(message.chat.id, "Введите дату тренировки (в формате ГГГГ-ММ-ДД):")
        user_state[message.chat.id] = "view_date"
    elif message.text == "Изменить тренировку":
        bot.send_message(message.chat.id, "Введите дату тренировки или нажмите 'Сегодня':")
        user_state[message.chat.id] = "edit_date"

@bot.message_handler(func=lambda msg: user_state.get(msg.chat.id) == "view_date")
def view_training(message):
    try:
        input_date = datetime.strptime(message.text, "%Y-%m-%d").date()
        row_num, row = find_row_by_date(input_date)
        if row:
            response = (
                f"Дата: {row[3]}\n"
                f"Тип нагрузки: {row[4]}\n"
                f"Тренировка: {row[5]}\n"
                f"Объем: {row[6]}\n"
                f"Цель: {row[7]}"
            
)
        else:
            response = "В данном периоде тренировок не предусмотрено."
        bot.send_message(message.chat.id, response)
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат даты. Введите в формате ГГГГ-ММ-ДД.")
    user_state[message.chat.id] = "choose_action"

@bot.message_handler(func=lambda msg: user_state.get(msg.chat.id) == "edit_date")
def edit_date(message):
    try:
        if message.text.lower() == "сегодня":
            input_date = date.today()
        else:
            input_date = datetime.strptime(message.text, "%Y-%m-%d").date()

        row_num, row = find_row_by_date(input_date)
        if not row:
            bot.send_message(message.chat.id, "Нет данных на эту дату. Создать новую строку пока нельзя.")
            return

        TEMP_DATA[message.chat.id] = {'row_num': row_num, 'date': input_date}
        user_state[message.chat.id] = "edit_training"
        bot.send_message(message.chat.id, f"Заполните поле 'Тренировка', текущее значение: {row[5]}")
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат даты. Введите в формате ГГГГ-ММ-ДД.")

@bot.message_handler(func=lambda msg: user_state.get(msg.chat.id) == "edit_training")
def edit_training(message):
    if message.text.lower() != "не менять":
        sheet.update_cell(TEMP_DATA[message.chat.id]['row_num'], COLUMN_MAP['training'], message.text)
    bot.send_message(message.chat.id, "Заполните поле 'Объем', текущее значение: (оставьте 'Не менять' если не хотите менять)")
    user_state[message.chat.id] = "edit_volume"

@bot.message_handler(func=lambda msg: user_state.get(msg.chat.id) == "edit_volume")
def edit_volume(message):
    if message.text.lower() != "не менять":
        sheet.update_cell(TEMP_DATA[message.chat.id]['row_num'], COLUMN_MAP['volume'], message.text)
    bot.send_message(message.chat.id, "Заполните поле 'Цель', текущее значение: (оставьте 'Не менять' если не хотите менять)")
    user_state[message.chat.id] = "edit_goal"

@bot.message_handler(func=lambda msg: user_state.get(msg.chat.id) == "edit_goal")
def edit_goal(message):
    if message.text.lower() != "не менять":
        sheet.update_cell(TEMP_DATA[message.chat.id]['row_num'], COLUMN_MAP['goal'], message.text)
    bot.send_message(message.chat.id, "✅ Данные обновлены.")
    user_state[message.chat.id] = "choose_action"

bot.polling()

