import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import json

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class FreqtradeAPI:
    """Класс для работы с API Freqtrade"""
    
    def __init__(self, api_url, username, password):
        self.api_url = api_url.rstrip('/')
        self.username = username
        self.password = password
        self.token = None
        self.authenticate()
    
    def authenticate(self):
        """Аутентификация в Freqtrade API"""
        try:
            response = requests.post(
                f"{self.api_url}/api/v1/token/login",
                json={"username": self.username, "password": self.password}
            )
            if response.status_code == 200:
                self.token = response.json().get('access_token')
                logger.info("Successfully authenticated with Freqtrade")
            else:
                logger.error(f"Authentication failed: {response.text}")
        except Exception as e:
            logger.error(f"Authentication error: {e}")
    
    def _make_request(self, method, endpoint, data=None):
        """Базовый метод для запросов к API"""
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        url = f"{self.api_url}/api/v1/{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data or {})
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Request failed: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
    
    def get_status(self):
        """Получить статус бота"""
        return self._make_request("GET", "status")
    
    def get_profit(self):
        """Получить информацию о прибыли"""
        return self._make_request("GET", "profit")
    
    def get_balance(self):
        """Получить баланс"""
        return self._make_request("GET", "balance")
    
    def get_trades(self):
        """Получить список сделок"""
        return self._make_request("GET", "trades")
    
    def get_performance(self):
        """Получить производительность по парам"""
        return self._make_request("GET", "performance")
    
    def start_bot(self):
        """Запустить бота"""
        return self._make_request("POST", "start")
    
    def stop_bot(self):
        """Остановить бота"""
        return self._make_request("POST", "stop")
    
    def reload_config(self):
        """Перезагрузить конфигурацию"""
        return self._make_request("POST", "reload_config")
    
    def get_daily_stats(self):
        """Получить ежедневную статистику"""
        return self._make_request("GET", "daily")
    
    def forcebuy(self, pair):
        """Принудительная покупка"""
        return self._make_request("POST", "forcebuy", {"pair": pair})
    
    def forcesell(self, tradeid):
        """Принудительная продажа"""
        return self._make_request("POST", "forcesell", {"tradeid": tradeid})
    
    def get_whitelist(self):
        """Получить белый список пар"""
        return self._make_request("GET", "whitelist")
    
    def get_blacklist(self):
        """Получить черный список пар"""
        return self._make_request("GET", "blacklist")

# Глобальная переменная для API
freqtrade_api = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("📊 Статус", callback_data='status'),
         InlineKeyboardButton("💰 Прибыль", callback_data='profit')],
        [InlineKeyboardButton("📈 Сделки", callback_data='trades'),
         InlineKeyboardButton("💵 Баланс", callback_data='balance')],
        [InlineKeyboardButton("🎯 Производительность", callback_data='performance'),
         InlineKeyboardButton("📅 Статистика", callback_data='daily')],
        [InlineKeyboardButton("▶️ Старт", callback_data='start_bot'),
         InlineKeyboardButton("⏸ Стоп", callback_data='stop_bot')],
        [InlineKeyboardButton("🔄 Перезагрузка", callback_data='reload'),
         InlineKeyboardButton("⚙️ Управление", callback_data='manage')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 *Freqtrade Control Panel*

Управляйте вашим торговым ботом через Telegram!

Выберите действие:
"""
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статус бота"""
    query = update.callback_query
    await query.answer()
    
    if not freqtrade_api:
        await query.edit_message_text("❌ Freqtrade API не настроен")
        return
    
    status = freqtrade_api.get_status()
    
    if not status:
        await query.edit_message_text("❌ Ошибка получения статуса")
        return
    
    if isinstance(status, list) and len(status) == 0:
        status_text = "🟢 *Бот работает*\n\n📭 Нет открытых сделок"
    else:
        trades = status if isinstance(status, list) else [status]
        status_text = f"🟢 *Бот работает*\n\n📊 Открытых сделок: {len(trades)}\n\n"
        
        for trade in trades[:5]:  # Показываем максимум 5 сделок
            pair = trade.get('pair', 'N/A')
            profit = trade.get('profit_pct', 0)
            profit_emoji = "📈" if profit > 0 else "📉"
            
            status_text += f"{profit_emoji} *{pair}*\n"
            status_text += f"   Прибыль: {profit:.2f}%\n"
            status_text += f"   Открыта: {trade.get('open_date', 'N/A')}\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать прибыль"""
    query = update.callback_query
    await query.answer()
    
    if not freqtrade_api:
        await query.edit_message_text("❌ Freqtrade API не настроен")
        return
    
    profit = freqtrade_api.get_profit()
    
    if not profit:
        await query.edit_message_text("❌ Ошибка получения данных о прибыли")
        return
    
    profit_text = f"""
💰 *Статистика прибыли*

📊 Всего сделок: {profit.get('trade_count', 0)}
✅ Прибыльных: {profit.get('winning_trades', 0)}
❌ Убыточных: {profit.get('losing_trades', 0)}

💵 Общая прибыль: {profit.get('profit_all_coin', 0):.8f} {profit.get('stake_currency', 'USDT')}
📈 Прибыль (%): {profit.get('profit_all_percent', 0):.2f}%
💎 В фиате: {profit.get('profit_all_fiat', 0):.2f} {profit.get('fiat_display_currency', 'USD')}

🎯 Средняя прибыль: {profit.get('avg_duration', 'N/A')}
⏱ Среднее время: {profit.get('avg_duration', 'N/A')}
"""
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(profit_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать баланс"""
    query = update.callback_query
    await query.answer()
    
    if not freqtrade_api:
        await query.edit_message_text("❌ Freqtrade API не настроен")
        return
    
    balance = freqtrade_api.get_balance()
    
    if not balance:
        await query.edit_message_text("❌ Ошибка получения баланса")
        return
    
    currencies = balance.get('currencies', [])
    total = balance.get('total', 0)
    stake = balance.get('stake', 'USDT')
    
    balance_text = f"💵 *Баланс кошелька*\n\n"
    balance_text += f"💰 Всего: {total:.2f} {stake}\n\n"
    
    for curr in currencies[:10]:  # Показываем топ-10
        balance_text += f"• {curr.get('currency')}: {curr.get('free', 0):.8f}\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(balance_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать сделки"""
    query = update.callback_query
    await query.answer()
    
    if not freqtrade_api:
        await query.edit_message_text("❌ Freqtrade API не настроен")
        return
    
    trades = freqtrade_api.get_trades()
    
    if not trades:
        await query.edit_message_text("❌ Ошибка получения сделок")
        return
    
    trades_list = trades.get('trades', [])
    
    if not trades_list:
        trades_text = "📭 *Нет сделок*"
    else:
        trades_text = f"📈 *Последние {min(5, len(trades_list))} сделок*\n\n"
        
        for trade in trades_list[-5:]:  # Последние 5
            pair = trade.get('pair', 'N/A')
            profit = trade.get('profit_pct', 0)
            profit_emoji = "✅" if profit > 0 else "❌"
            
            trades_text += f"{profit_emoji} *{pair}*\n"
            trades_text += f"   Прибыль: {profit:.2f}%\n"
            trades_text += f"   Закрыта: {trade.get('close_date', 'N/A')}\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(trades_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_performance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать производительность"""
    query = update.callback_query
    await query.answer()
    
    if not freqtrade_api:
        await query.edit_message_text("❌ Freqtrade API не настроен")
        return
    
    performance = freqtrade_api.get_performance()
    
    if not performance:
        await query.edit_message_text("❌ Ошибка получения производительности")
        return
    
    perf_text = "🎯 *Производительность по парам*\n\n"
    
    for pair_data in performance[:10]:  # Топ-10
        pair = pair_data.get('pair', 'N/A')
        profit = pair_data.get('profit', 0)
        count = pair_data.get('count', 0)
        
        perf_text += f"• *{pair}*: {profit:.2f}% ({count} сделок)\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(perf_text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать дневную статистику"""
    query = update.callback_query
    await query.answer()
    
    if not freqtrade_api:
        await query.edit_message_text("❌ Freqtrade API не настроен")
        return
    
    daily = freqtrade_api.get_daily_stats()
    
    if not daily:
        await query.edit_message_text("❌ Ошибка получения статистики")
        return
    
    daily_text = "📅 *Дневная статистика (последние 7 дней)*\n\n"
    
    data = daily.get('data', [])
    for day in data[-7:]:
        date = day.get('date', 'N/A')
        profit = day.get('abs_profit', 0)
        trades = day.get('trade_count', 0)
        
        daily_text += f"📆 {date}\n"
        daily_text += f"   Прибыль: {profit:.2f}\n"
        daily_text += f"   Сделок: {trades}\n\n"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(daily_text, reply_markup=reply_markup, parse_mode='Markdown')

async def manage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🛒 Купить пару", callback_data='forcebuy_menu')],
        [InlineKeyboardButton("💸 Продать сделку", callback_data='forcesell_menu')],
        [InlineKeyboardButton("📋 Белый список", callback_data='whitelist')],
        [InlineKeyboardButton("🚫 Черный список", callback_data='blacklist')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("⚙️ *Управление ботом*", reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back':
        await start(update, context)
    
    elif query.data == 'status':
        await show_status(update, context)
    
    elif query.data == 'profit':
        await show_profit(update, context)
    
    elif query.data == 'balance':
        await show_balance(update, context)
    
    elif query.data == 'trades':
        await show_trades(update, context)
    
    elif query.data == 'performance':
        await show_performance(update, context)
    
    elif query.data == 'daily':
        await show_daily(update, context)
    
    elif query.data == 'manage':
        await manage_menu(update, context)
    
    elif query.data == 'start_bot':
        if freqtrade_api:
            result = freqtrade_api.start_bot()
            await query.edit_message_text("✅ Бот запущен!" if result else "❌ Ошибка запуска")
    
    elif query.data == 'stop_bot':
        if freqtrade_api:
            result = freqtrade_api.stop_bot()
            await query.edit_message_text("⏸ Бот остановлен!" if result else "❌ Ошибка остановки")
    
    elif query.data == 'reload':
        if freqtrade_api:
            result = freqtrade_api.reload_config()
            await query.edit_message_text("🔄 Конфигурация перезагружена!" if result else "❌ Ошибка перезагрузки")
    
    elif query.data == 'whitelist':
        if freqtrade_api:
            whitelist = freqtrade_api.get_whitelist()
            if whitelist:
                pairs = ', '.join(whitelist.get('whitelist', []))
                await query.edit_message_text(f"📋 *Белый список:*\n\n{pairs}", parse_mode='Markdown')
    
    elif query.data == 'blacklist':
        if freqtrade_api:
            blacklist = freqtrade_api.get_blacklist()
            if blacklist:
                pairs = ', '.join(blacklist.get('blacklist', []))
                await query.edit_message_text(f"🚫 *Черный список:*\n\n{pairs}", parse_mode='Markdown')

def main():
    global freqtrade_api
    
    # Получение переменных окружения
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    FREQTRADE_URL = os.getenv('FREQTRADE_API_URL', 'http://localhost:8080')
    FREQTRADE_USER = os.getenv('FREQTRADE_API_USER', 'freqtrader')
    FREQTRADE_PASS = os.getenv('FREQTRADE_API_PASS', 'password')
    
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set!")
    
    # Инициализация Freqtrade API
    try:
        freqtrade_api = FreqtradeAPI(FREQTRADE_URL, FREQTRADE_USER, FREQTRADE_PASS)
        logger.info("Freqtrade API initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Freqtrade API: {e}")
    
    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запуск
    logger.info("Telegram bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
