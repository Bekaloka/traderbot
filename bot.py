import telebot
import ccxt
import pandas_ta as ta
import pandas as pd
import time
import os
import logging
from threading import Thread
from datetime import datetime
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Получаем настройки из переменных окружения
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SYMBOL = os.getenv('SYMBOL', 'BTC/USDT')
TIMEFRAME = os.getenv('TIMEFRAME', '15m')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '900'))

# Проверка обязательных переменных
if not TOKEN:
    logger.error("❌ TELEGRAM_TOKEN не установлен!")
    sys.exit(1)
    
if not CHAT_ID:
    logger.error("❌ TELEGRAM_CHAT_ID не установлен!")
    sys.exit(1)

logger.info(f"✅ Настройки загружены: {SYMBOL}, {TIMEFRAME}")

# Инициализация бота и биржи
try:
    bot = telebot.TeleBot(TOKEN, parse_mode='HTML')
    exchange = ccxt.binance({'enableRateLimit': True})
    logger.info("✅ Бот и биржа инициализированы")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации: {e}")
    sys.exit(1)

class TradingBot:
    def __init__(self):
        self.last_signal = None
        self.is_running = False
        self.error_count = 0
    
    def get_signal(self):
        """Получение торгового сигнала SuperTrend"""
        try:
            # Загружаем свечи с Binance
            bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)
            
            if not bars or len(bars) < 50:
                logger.warning("⚠️ Недостаточно данных")
                return None
            
            # Создаем DataFrame
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Рассчитываем SuperTrend
            supertrend = ta.supertrend(
                high=df['high'],
                low=df['low'],
                close=df['close'],
                length=10,
                multiplier=3.0
            )
            
            if supertrend is None or supertrend.empty:
                logger.warning("⚠️ Ошибка расчета SuperTrend")
                return None
            
            # Получаем сигнал
            last_direction = supertrend.iloc[-1]['SUPERTd_10_3.0']
            current_price = df.iloc[-1]['close']
            
            self.error_count = 0  # Сброс счетчика ошибок
            
            signal = {
                'direction': 'BUY 🟢' if last_direction == 1 else 'SELL 🔴',
                'price': current_price,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            logger.info(f"📊 Сигнал: {signal['direction']} по цене {current_price}")
            return signal
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения сигнала: {e}")
            self.error_count += 1
            
            if self.error_count >= 5:
                logger.error("⚠️ Слишком много ошибок, пауза 5 минут...")
                time.sleep(300)
                self.error_count = 0
            
            return None
    
    def format_message(self, signal_data):
        """Форматирование сообщения"""
        return (
            f"📊 <b>{SYMBOL}</b>\n"
            f"⚡️ Сигнал: <b>{signal_data['direction']}</b>\n"
            f"💰 Цена: <code>{signal_data['price']:.2f}</code> USDT\n"
            f"🕐 {signal_data['timestamp']}"
        )
    
    def send_message(self, text):
        """Безопасная отправка сообщения"""
        try:
            bot.send_message(CHAT_ID, text, parse_mode='HTML')
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False
    
    def auto_check(self):
        """Автоматическая проверка сигналов каждые 15 минут"""
        self.is_running = True
        logger.info("🚀 Автоматическая проверка запущена!")
        
        # Уведомление о запуске
        self.send_message(
            f"✅ <b>Бот запущен!</b>\n"
            f"📊 Пара: {SYMBOL}\n"
            f"⏱ Таймфрейм: {TIMEFRAME}\n"
            f"🔄 Проверка каждые {CHECK_INTERVAL//60} минут"
        )
        
        while self.is_running:
            try:
                signal = self.get_signal()
                
                if signal:
                    # Отправляем только если сигнал изменился
                    if (self.last_signal is None or 
                        signal['direction'] != self.last_signal['direction']):
                        
                        message = f"🔔 <b>НОВЫЙ СИГНАЛ!</b>\n\n{self.format_message(signal)}"
                        
                        if self.send_message(message):
                            self.last_signal = signal
                            logger.info(f"✉️ Отправлено: {signal['direction']}")
                
                # Ждем до следующей проверки
                time.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле: {e}")
                time.sleep(60)

# Создаем экземпляр бота
trading_bot = TradingBot()

# КОМАНДЫ TELEGRAM БОТА

@bot.message_handler(commands=['start', 'help'])
def start(message):
    """Команда /start"""
    text = (
        f"👋 <b>Добро пожаловать!</b>\n\n"
        f"📈 Пара: <code>{SYMBOL}</code>\n"
        f"⏱ Таймфрейм: <code>{TIMEFRAME}</code>\n"
        f"📊 Индикатор: SuperTrend (10, 3.0)\n\n"
        f"<b>Команды:</b>\n"
        f"/status - текущий сигнал\n"
        f"/info - информация о боте"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['status'])
def status(message):
    """Команда /status - показать текущий сигнал"""
    try:
        bot.send_message(message.chat.id, "⏳ Получаю данные...")
        signal = trading_bot.get_signal()
        
        if signal:
            bot.send_message(message.chat.id, trading_bot.format_message(signal))
        else:
            bot.send_message(message.chat.id, "⚠️ Не удалось получить данные. Попробуйте позже.")
    except Exception as e:
        logger.error(f"❌ Ошибка /status: {e}")
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['info'])
def info(message):
    """Команда /info - показать статистику"""
    status_emoji = '🟢 Работает' if trading_bot.is_running else '🔴 Остановлен'
    last_sig = trading_bot.last_signal['direction'] if trading_bot.last_signal else 'Нет данных'
    
    text = (
        f"ℹ️ <b>Информация о боте</b>\n\n"
        f"Статус: {status_emoji}\n"
        f"Символ: <code>{SYMBOL}</code>\n"
        f"Интервал проверки: {CHECK_INTERVAL//60} минут\n"
        f"Последний сигнал: {last_sig}\n"
        f"Ошибок подряд: {trading_bot.error_count}/5"
    )
    bot.reply_to(message, text)

# ГЛАВНАЯ ФУНКЦИЯ
def main():
    try:
        logger.info("=" * 50)
        logger.info("🚀 ЗАПУСК ТОРГОВОГО БОТА")
        logger.info("=" * 50)
        
        # Запускаем автопроверку в отдельном потоке
        auto_thread = Thread(target=trading_bot.auto_check, daemon=True)
        auto_thread.start()
        
        # Запускаем бота
        logger.info("🤖 Запуск Telegram polling...")
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            skip_pending=True
        )
        
    except KeyboardInterrupt:
        logger.info("⛔ Остановка по Ctrl+C")
        trading_bot.is_running = False
        trading_bot.send_message("🛑 Бот остановлен")
        
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
        trading_bot.send_message(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
