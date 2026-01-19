import os
import logging
import asyncio
import nest_asyncio
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from keep_alive import keep_alive

# --- ЛЕЧИМ ОШИБКИ АСИНХРОННОСТИ ДЛЯ RENDER ---
nest_asyncio.apply()

# --- КОНФИГУРАЦИЯ ---
API_KEY = os.getenv("EXCHANGE_API_KEY")
API_SECRET = os.getenv("EXCHANGE_SECRET_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
IS_SANDBOX = os.getenv("IS_SANDBOX", "True").lower() == "true"

# Настройки торговли
SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
POS_SIZE = 0.001

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

is_running = False

# --- ФУНКЦИИ БИРЖИ ---
async def get_exchange():
    exchange = ccxt.binance({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    if IS_SANDBOX:
        exchange.set_sandbox_mode(True)
    return exchange

async def fetch_data(exchange):
    try:
        ohlcv = await exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=50)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Индикаторы
        df['sma_fast'] = ta.sma(df['close'], length=10)
        df['sma_slow'] = ta.sma(df['close'], length=20)
        return df
    except Exception as e:
        logger.error(f"Ошибка данных: {e}")
        return None

async def trade_loop(context: ContextTypes.DEFAULT_TYPE):
    global is_running
    chat_id = context.job.chat_id
    
    # Если бот остановлен, не тратим ресурсы
    if not is_running:
        return

    exchange = await get_exchange()
    try:
        df = await fetch_data(exchange)
        if df is None: return

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last['close']
        
        # Логика сигналов
        buy_signal = prev['sma_fast'] < prev['sma_slow'] and last['sma_fast'] > last['sma_slow']
        sell_signal = prev['sma_fast'] > prev['sma_slow'] and last['sma_fast'] < last['sma_slow']

        # Проверка позиции
        balance = await exchange.fetch_balance()
        positions = [p for p in balance['info']['positions'] if p['symbol'] == SYMBOL.replace('/', '')]
        pos_amt = float(positions[0]['positionAmt']) if positions else 0

        msg = ""
        # Покупка
        if buy_signal and pos_amt <= 0:
            try:
                await exchange.create_market_buy_order(SYMBOL, POS_SIZE)
                msg = f"🚀 <b>BUY SIGNAL</b>\nЦена: {price}"
            except Exception as e:
                msg = f"Ошибка ордера BUY: {e}"

        # Продажа
        elif sell_signal and pos_amt >= 0:
            try:
                await exchange.create_market_sell_order(SYMBOL, POS_SIZE)
                msg = f"🔻 <b>SELL SIGNAL</b>\nЦена: {price}"
            except Exception as e:
                msg = f"Ошибка ордера SELL: {e}"

        if msg:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Ошибка в цикле: {e}")
    finally:
        await exchange.close()

# --- КОМАНДЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running
    is_running = True
    chat_id = update.effective_message.chat_id
    
    # Удаляем старые задачи, если есть
    for job in context.job_queue.jobs():
        job.schedule_removal()

    # Запускаем цикл каждые 60 сек
    context.job_queue.run_repeating(trade_loop, interval=60, first=5, chat_id=chat_id)
    await update.message.reply_text("✅ Бот запущен! Жду сигналов...")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running
    is_running = False
    for job in context.job_queue.jobs():
        job.schedule_removal()
    await update.message.reply_text("🛑 Бот остановлен.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exchange = await get_exchange()
    try:
        balance = await exchange.fetch_balance()
        usdt = balance['USDT']['free']
        mode = "DEMO" if IS_SANDBOX else "REAL"
        await update.message.reply_text(f"Статус: <b>{mode}</b>\nБаланс USDT: {usdt:.2f}", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"Ошибка связи с биржей: {e}")
    finally:
        await exchange.close()

# --- ЗАПУСК ---
if __name__ == '__main__':
    # 1. Запуск веб-сервера
    keep_alive()
    
    # 2. Проверка токена
    if not TG_TOKEN:
        print("ОШИБКА: Нет TELEGRAM_TOKEN в настройках Render!")
        exit(1)

    print("Попытка запуска Telegram бота...")
    
    try:
        # 3. Инициализация
        app = ApplicationBuilder().token(TG_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stop", stop))
        app.add_handler(CommandHandler("status", status))
        
        print("Бот успешно инициализирован. Начинаю polling...")
        
        # 4. Запуск прослушивания (с очисткой старых сообщений)
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА ЗАПУСКА: {e}")
