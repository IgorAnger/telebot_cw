import json
import os
from dotenv import load_dotenv
import telebot
from telebot import types
import requests
import sqlite3

from available_curs import print_curs

load_dotenv()

B_TOKEN = os.getenv('BOT_TOKEN')
W_TOKEN = os.getenv('WEATHER_TOKEN')
C_TOKEN = os.getenv('ABSTRACTAPI_EX_RATES_TOKEN')

database = 'users.db'

bot = telebot.TeleBot(B_TOKEN)

#------------------------------Database commands-----------------------------

def post_sql_query(sql_query, commit=False):
    """ Process a SQL query """
    with sqlite3.connect(database) as connection:
        cursor = connection.cursor()
        cursor.execute(sql_query)
        if commit:
            connection.commit()
            return None
        else:
            result = cursor.fetchall()
            return result

def create_tables():
    """ Init db if absent """
    users_query = '''CREATE TABLE IF NOT EXISTS USERS 
                        (user_id INTEGER PRIMARY KEY NOT NULL,
                        username TEXT,
                        last_choice TEXT);'''
    post_sql_query(users_query)


def user_exists(user):
    """ Check user id is in db"""
    user_check_query = f'SELECT * FROM USERS WHERE user_id = {user};'
    return post_sql_query(user_check_query)

def register_user(user, username):
    """ Add new user to db"""
    user_check_data = user_exists(user)
    if not user_check_data:
        sql_query = f'INSERT INTO USERS (user_id, username) VALUES ({user}, "{username}");'
        post_sql_query(sql_query, commit=True)

def store_user_choice(user, location):
    """ Add or rewrite last location from get_weather"""
    user_check_data = user_exists(user)
    if user_check_data:
        with sqlite3.connect(database) as connection:
            cur = connection.cursor()
            location_data_query = f'SELECT last_choice FROM USERS WHERE user_id = {user};'
            current_db_loc = cur.execute(location_data_query).fetchall()[0][0]
            print(type(location), location, type(current_db_loc), current_db_loc)
            if location != current_db_loc:
                update_location = f'UPDATE USERS SET last_choice = ? WHERE user_id = ?'
                data = (location, user)
                cur.execute(update_location, data)
                connection.commit()
            else:
                pass

def location_exist(user):
    """Check existance of the stored location"""
    location_check_query = f'SELECT last_choice FROM USERS WHERE user_id = {user};'
    return post_sql_query(location_check_query)

def load_location(user):
    """Load previous user choice"""
    with sqlite3.connect(database) as connection:
        cur = connection.cursor()
        location_data_query = f'SELECT last_choice FROM USERS WHERE user_id = {user};'
        location = cur.execute(location_data_query).fetchall()
    return location

@bot.message_handler(commands = ['start'])
def start(message):
    chat_id = message.chat.id
    markup = types.InlineKeyboardMarkup(row_width = 2)
    but_weather = types.InlineKeyboardButton('Get Weather', callback_data='w')
    but_currencies = types.InlineKeyboardButton('Get Currencies', callback_data='c')
    markup.add(but_weather, but_currencies)
    if not user_exists(chat_id):
        register_user(message.from_user.id, message.from_user.username)
        bot.send_message(chat_id, 
        f'Hello, {message.from_user.first_name} {message.from_user.last_name}! Press one of the buttons below',
        reply_markup=markup)
    else:
        bot.send_message(chat_id, f'Welcome back', reply_markup=markup)

@bot.message_handler(content_types = ['text'])
def get_weather(message):
    chat_id = message.chat.id
    location_db = load_location(chat_id)
    location_db = location_db[0][0]
    markup = types.InlineKeyboardMarkup(row_width = 1)
    but_stored_loc = types.InlineKeyboardButton(f'{location_db}', callback_data='stored_loc')
    but_back = types.InlineKeyboardButton('Back', callback_data='go_start')
    markup.add(but_stored_loc, but_back)
    location = message.text.lower().strip()
    weather_r = requests.get(f'https://api.openweathermap.org/data/2.5/weather?q={location}&appid={W_TOKEN}&units=metric')
    if weather_r.status_code == 200:
        weather_data = json.loads(weather_r.text)
        bot.send_message(chat_id,
        f'{message.text.capitalize()}: \nCurrent temperature: {weather_data["main"]["temp"]} C \nFeels like: {weather_data["main"]["feels_like"]} C \nCurrent weather: {weather_data["weather"][0]["description"]} \nYou can try new location',
        reply_markup=markup)
        return store_user_choice(chat_id, message.text.capitalize())

    else:
        bot.send_message(chat_id, 'Something went wrong, try again', reply_markup=markup)

@bot.message_handler(content_types = ['text'])
def get_currencies(message):
    chat_id = message.chat.id
    markup = types.InlineKeyboardMarkup(row_width = 2)
    cur_choice_keyboard = [[types.InlineKeyboardButton('USD/EUR', callback_data='usd_eur'),
    types.InlineKeyboardButton('USD/GBP', callback_data='usd_gbp'),
    types.InlineKeyboardButton('USD/CHF', callback_data='usd_chf'),
    types.InlineKeyboardButton('USD/BTC', callback_data='usd_btc'),
    types.InlineKeyboardButton('USD/ETH', callback_data='usd_eth'),
    types.InlineKeyboardButton('Custom', callback_data='custom'),
    types.InlineKeyboardButton('Back to start', callback_data='go_start'),
    types.InlineKeyboardButton('Back to choice', callback_data='go_choice_cur')]]
    markup.add(cur_choice_keyboard)
    bot.send_message(chat_id, 'Choose pair', reply_markup=markup)

@bot.message_handler(content_types = ['text'])
def get_custom_curs(message):
    chat_id = message.chat.id
    markup = types.InlineKeyboardMarkup(row_width = 1)
    but_back_choice = types.InlineKeyboardButton('Back to choice', callback_data='c')
    markup.add(but_back_choice)
    user_curs = message.text.upper().split('/')
    cur1 = user_curs[0]
    cur2 = user_curs[1]
    currencies_r = requests.get(f'https://exchange-rates.abstractapi.com/v1/live/?api_key={C_TOKEN}&base={cur1}&target={cur2}')
    if currencies_r.status_code == 200:
        cur_data = json.loads(currencies_r.text)
        for cur_key, ex_value in cur_data["exchange_rates"].items():
            ex_rate = ex_value
        custom_cur_mes = bot.send_message(chat_id, 
        f'Current {cur1.upper()}/{cur2.upper()} rate: {ex_rate} \nYou can type new pair or go back to choice',
        reply_markup=markup)
        bot.register_next_step_handler(custom_cur_mes, get_custom_curs)
    else:
        custom_cur_mes_error = bot.send_message(chat_id, 'Something went wrong, try again', reply_markup=markup)
        bot.register_next_step_handler(custom_cur_mes_error, get_custom_curs)

@bot.callback_query_handler(func = lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    if call.data == 'w':
        markup = types.InlineKeyboardMarkup(row_width = 1)
        if location_exist(chat_id):
            location_db = load_location(chat_id)
            location_db = location_db[0][0]
            but_stored_loc = types.InlineKeyboardButton(f'{location_db}', callback_data='stored_loc')
            back_choice = types.InlineKeyboardButton('Back', callback_data = 'go_start')
            markup.add(but_stored_loc, back_choice)
            w_reply = bot.send_message(chat_id, 'Type name of the city and get current weather or try your last search:', reply_markup=markup)
            bot.register_next_step_handler(w_reply, get_weather)
        else:
            markup = types.InlineKeyboardMarkup(row_width = 1)
            back_choice = types.InlineKeyboardButton('Back', callback_data = 'go_start')
            markup.add(back_choice)
            w_reply = bot.send_message(chat_id, 'Type name of the city and get current weather:', reply_markup=markup)
            bot.register_next_step_handler(w_reply, get_weather)
    elif call.data == 'c':
        markup = types.InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(types.InlineKeyboardButton('USD/EUR', callback_data='usd_eur'),
        types.InlineKeyboardButton('USD/GBP', callback_data='usd_gbp'),
        types.InlineKeyboardButton('USD/CHF', callback_data='usd_chf'),
        types.InlineKeyboardButton('USD/BTC', callback_data='usd_btc'),
        types.InlineKeyboardButton('USD/BTC', callback_data='usd_btc'),
        types.InlineKeyboardButton('USD/ETH', callback_data='usd_eth'),
        types.InlineKeyboardButton('Custom', callback_data='custom'),
        types.InlineKeyboardButton('Back to start', callback_data='go_start'))
        c_reply = bot.send_message(chat_id, 'Choose one of the pairs or press custom', reply_markup=markup)
    elif call.data == 'go_start':
        markup = types.InlineKeyboardMarkup(row_width = 2)
        but_weather = types.InlineKeyboardButton('Get Weather', callback_data='w')
        but_currencies = types.InlineKeyboardButton('Get Currencies', callback_data='c')
        markup.add(but_weather, but_currencies)
        back_to_start_reply = bot.send_message(chat_id, 'Choose one of the buttons bellow', reply_markup=markup)
    elif call.data == 'stored_loc':
        location_db = load_location(chat_id)
        location_db = location_db[0][0]
        markup = types.InlineKeyboardMarkup(row_width = 1)
        back_choice = types.InlineKeyboardButton('Back', callback_data = 'go_start')
        but_stored_loc = types.InlineKeyboardButton(f'{location_db}', callback_data='stored_loc')
        markup.add(but_stored_loc, back_choice)
        weather_r = requests.get(f'https://api.openweathermap.org/data/2.5/weather?q={location_db}&appid={W_TOKEN}&units=metric')
        if weather_r.status_code == 200:
            weather_data = json.loads(weather_r.text)
            stored_loc_mes = bot.send_message(chat_id,
            f'{location_db}: \nCurrent temperature: {weather_data["main"]["temp"]} C \nFeels like: {weather_data["main"]["feels_like"]} C \nCurrent weather: {weather_data["weather"][0]["description"]} \nYou can try new location',
            reply_markup=markup)
            bot.register_next_step_handler(stored_loc_mes, get_weather)
        else:
            error_mes = bot.send_message(chat_id, 'Something went wrong, try again', reply_markup=markup)
            bot.register_next_step_handler(error_mes, get_weather)
    elif call.data == 'usd_eur':
        markup = types.InlineKeyboardMarkup(row_width = 1)
        but_back_choice = types.InlineKeyboardButton('Back to choice', callback_data='c')
        markup.add(but_back_choice)
        cur1 = 'USD'
        cur2 = 'EUR'
        currencies_r = requests.get(f'https://exchange-rates.abstractapi.com/v1/live/?api_key={C_TOKEN}&base={cur1}&target={cur2}')
        if currencies_r.status_code == 200:
            cur_data = json.loads(currencies_r.text)
            for cur_key, ex_value in cur_data["exchange_rates"].items():
                ex_rate = ex_value
            bot.send_message(chat_id, f'Current {cur1.upper()}/{cur2.upper()} rate: {ex_rate}', reply_markup=markup)
        else:
            bot.send_message(chat_id, 'Something went wrong, try again', reply_markup=markup)
    elif call.data == 'usd_gbp':
        markup = types.InlineKeyboardMarkup(row_width = 1)
        but_back_choice = types.InlineKeyboardButton('Back to choice', callback_data='c')
        markup.add(but_back_choice)
        cur1 = 'USD'
        cur2 = 'GBP'
        currencies_r = requests.get(f'https://exchange-rates.abstractapi.com/v1/live/?api_key={C_TOKEN}&base={cur1}&target={cur2}')
        if currencies_r.status_code == 200:
            cur_data = json.loads(currencies_r.text)
            for cur_key, ex_value in cur_data["exchange_rates"].items():
                ex_rate = ex_value
            bot.send_message(chat_id, f'Current {cur1.upper()}/{cur2.upper()} rate: {ex_rate}', reply_markup=markup)
        else:
            bot.send_message(chat_id, 'Something went wrong, try again', reply_markup=markup)
    elif call.data == 'usd_chf':
        markup = types.InlineKeyboardMarkup(row_width = 1)
        but_back_choice = types.InlineKeyboardButton('Back to choice', callback_data='c')
        markup.add(but_back_choice)
        cur1 = 'USD'
        cur2 = 'CHF'
        currencies_r = requests.get(f'https://exchange-rates.abstractapi.com/v1/live/?api_key={C_TOKEN}&base={cur1}&target={cur2}')
        if currencies_r.status_code == 200:
            cur_data = json.loads(currencies_r.text)
            for cur_key, ex_value in cur_data["exchange_rates"].items():
                ex_rate = ex_value
            bot.send_message(chat_id, f'Current {cur1.upper()}/{cur2.upper()} rate: {ex_rate}', reply_markup=markup)
        else:
            bot.send_message(chat_id, 'Something went wrong, try again', reply_markup=markup)
    elif call.data == 'usd_btc':
        markup = types.InlineKeyboardMarkup(row_width = 1)
        but_back_choice = types.InlineKeyboardButton('Back to choice', callback_data='c')
        markup.add(but_back_choice)
        cur1 = 'USD'
        cur2 = 'BTC'
        currencies_r = requests.get(f'https://exchange-rates.abstractapi.com/v1/live/?api_key={C_TOKEN}&base={cur1}&target={cur2}')
        if currencies_r.status_code == 200:
            cur_data = json.loads(currencies_r.text)
            for cur_key, ex_value in cur_data["exchange_rates"].items():
                ex_rate = ex_value
            bot.send_message(chat_id, f'Current {cur1.upper()}/{cur2.upper()} rate: {ex_rate}', reply_markup=markup)
        else:
            bot.send_message(chat_id, 'Something went wrong, try again', reply_markup=markup)
    elif call.data == 'usd_eth':
        markup = types.InlineKeyboardMarkup(row_width = 1)
        but_back_choice = types.InlineKeyboardButton('Back to choice', callback_data='c')
        markup.add(but_back_choice)
        cur1 = 'USD'
        cur2 = 'ETH'
        currencies_r = requests.get(f'https://exchange-rates.abstractapi.com/v1/live/?api_key={C_TOKEN}&base={cur1}&target={cur2}')
        if currencies_r.status_code == 200:
            cur_data = json.loads(currencies_r.text)
            for cur_key, ex_value in cur_data["exchange_rates"].items():
                ex_rate = ex_value
            bot.send_message(chat_id, f'Current {cur1.upper()}/{cur2.upper()} rate: {ex_rate}', reply_markup=markup)
        else:
            bot.send_message(chat_id, 'Something went wrong, try again', reply_markup=markup)
    elif call.data == 'custom':
        markup = types.InlineKeyboardMarkup(row_width = 1)
        but_back_choice = types.InlineKeyboardButton('Back to choice', callback_data='c')
        markup.add(but_back_choice)
        custom_cur_mes = bot.send_message(chat_id, f'{print_curs()} \nEnter interested pair from the list above in format <b> currency1/currency2 </b>', reply_markup=markup, parse_mode='html')
        bot.register_next_step_handler(custom_cur_mes, get_custom_curs)

if __name__ == '__main__':
    create_tables()
    bot.polling(non_stop = True)