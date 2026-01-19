import os
import logging
import asyncio
import ccxt.async_support as ccxt  # Асинхронная версия
import pandas as pd
import pandas_ta as ta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- КОНФИГУРАЦИЯ ---
# Эти данные мы будем задавать в настройках Render.com, чтобы не светить ключи
API_KEY = os.getenv("EXCHANGE_API_KEY")
API_SECRET = os.getenv("EXCHANGE_SECRET_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
IS_SANDBOX = os.getenv("IS_SANDBOX", "True").lower() == "true" # True = Демо счет

# Настройки торговли
SYMBOL = 'BTC/USDT'  # Торговая пара
TIMEFRAME = '15m'    # Таймфрейм
POS_SIZE = 0.001     # Размер позиции в BTC (для теста)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальный флаг работы
is_running = False

async def get_exchange():
    """Создает подключение к бирже (Binance)"""
    exchange = ccxt.binance({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future', # Торгуем фьючерсами
        }
    })
    
    # ПЕРЕКЛЮЧЕНИЕ НА ДЕМО (SANDBOX)
    if IS_SANDBOX:
        exchange.set_sandbox_mode(True) 
    
    return exchange

async def fetch_data(exchange):
    """Получает свечи и считает индикаторы"""
    try:
        ohlcv = await exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Стратегия: SMA Crossover (Простая, для примера)
        # Если SMA 10 пересекает SMA 20 снизу вверх -> BUY
        df['sma_fast'] = ta.sma(df['close'], length=10)
        df['sma_slow'] = ta.sma(df['close'], length=20)
        
        return df
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return None

async def trade_loop(context: ContextTypes.DEFAULT_TYPE):
    """Главный цикл торговли"""
    global is_running
    chat_id = context.job.chat_id
    
    exchange = await get_exchange()
    
    try:
        # Если бот остановлен - выходим
        if not is_running:
            return

        df = await fetch_data(exchange)
        if df is None:
            return

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        price = last_row['close']
        
        # ЛОГИКА ВХОДА
        # Золотой крест (Fast пересекает Slow снизу вверх) -> BUY
        signal_buy = prev_row['sma_fast'] < prev_row['sma_slow'] and last_row['sma_fast'] > last_row['sma_slow']
        
        # Мертвый крест (Fast пересекает Slow сверху вниз) -> SELL
        signal_sell = prev_row['sma_fast'] > prev_row['sma_slow'] and last_row['sma_fast'] < last_row['sma_slow']

        # Проверка текущей позиции
        balance = await exchange.fetch_balance()
        positions = [p for p in balance['info']['positions'] if p['symbol'] == SYMBOL.replace('/', '')]
        current_pos = float(positions[0]['positionAmt']) if positions else 0

        msg = ""

        if signal_buy and current_pos <= 0:
            # Закрыть шорт если есть, открыть лонг
            order = await exchange.create_market_buy_order(SYMBOL, POS_SIZE)
            msg = f"🚀 <b>BUY SIGNAL</b>\nЦена: {price}\nОрдер исполнен!"
            
        elif signal_sell and current_pos >= 0:
            # Закрыть лонг если есть, открыть шорт
            order = await exchange.create_market_sell_order(SYMBOL, POS_SIZE)
            msg = f"🔻 <b>SELL SIGNAL</b>\nЦена: {price}\nОрдер исполнен!"

        if msg:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Ошибка в цикле: {e}")
    finally:
        await exchange.close()

# --- КОМАНДЫ TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running
    is_running = True
    
    # Запускаем проверку рынка каждые 60 секунд
    chat_id = update.effective_message.chat_id
    job_queue = context.job_queue
    
    # Удаляем старые задачи, чтобы не дублировать
    current_jobs = job_queue.get_jobs_by_name('trade_job')
    for job in current_jobs:
        job.schedule_removal()
        
    job_queue.run_repeating(trade_loop, interval=60, first=10, chat_id=chat_id, name='trade_job')
    
    mode = "DEMO (Testnet)" if IS_SANDBOX else "REAL MONEY"
    await update.message.reply_text(f"✅ Бот запущен!\nРежим: <b>{mode}</b>\nПара: {SYMBOL}", parse_mode='HTML')

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running
    is_running = False
    
    job_queue = context.job_queue
    current_jobs = job_queue.get_jobs_by_name('trade_job')
    for job in current_jobs:
        job.schedule_removal()
        
    await update.message.reply_text("🛑 Бот остановлен.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exchange = await get_exchange()
    try:
        ticker = await exchange.fetch_ticker(SYMBOL)
        price = ticker['last']
        
        # Баланс
        balance = await exchange.fetch_balance()
        usdt = balance['USDT']['free']
        
        mode = "🟢 DEMO" if IS_SANDBOX else "🔴 REAL"
        
        msg = (
            f"📊 <b>Статус:</b> {mode}\n"
            f"Пара: {SYMBOL}\n"
            f"Текущая цена: {price}\n"
            f"Свободно USDT: {usdt:.2f}"
        )
        await update.message.reply_text(msg, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"Ошибка получения статуса: {e}")
    finally:
        await exchange.close()

if __name__ == '__main__':
    if not TG_TOKEN:
        print("Ошибка: Токен Telegram не найден.")
        exit()
        
    app = ApplicationBuilder().token(TG_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    
    print("Бот запущен...")
    app.run_polling()
