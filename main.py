import os
import logging
import asyncio
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from keep_alive import keep_alive  # <--- ИМПОРТИРУЕМ НАШ "БУДИЛЬНИК"

# --- КОНФИГУРАЦИЯ ---
API_KEY = os.getenv("EXCHANGE_API_KEY")
API_SECRET = os.getenv("EXCHANGE_SECRET_KEY")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
IS_SANDBOX = os.getenv("IS_SANDBOX", "True").lower() == "true"

SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
POS_SIZE = 0.001

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

is_running = False

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
        ohlcv = await exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['sma_fast'] = ta.sma(df['close'], length=10)
        df['sma_slow'] = ta.sma(df['close'], length=20)
        return df
    except Exception as e:
        logger.error(f"Error data: {e}")
        return None

async def trade_loop(context: ContextTypes.DEFAULT_TYPE):
    global is_running
    chat_id = context.job.chat_id
    exchange = await get_exchange()
    
    try:
        if not is_running: return
        df = await fetch_data(exchange)
        if df is None: return

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last['close']
        
        # Cross logic
        buy_sig = prev['sma_fast'] < prev['sma_slow'] and last['sma_fast'] > last['sma_slow']
        sell_sig = prev['sma_fast'] > prev['sma_slow'] and last['sma_fast'] < last['sma_slow']

        balance = await exchange.fetch_balance()
        positions = [p for p in balance['info']['positions'] if p['symbol'] == SYMBOL.replace('/', '')]
        pos_amt = float(positions[0]['positionAmt']) if positions else 0

        msg = ""
        if buy_sig and pos_amt <= 0:
            await exchange.create_market_buy_order(SYMBOL, POS_SIZE)
            msg = f"🚀 <b>BUY</b> | Price: {price}"
        elif sell_sig and pos_amt >= 0:
            await exchange.create_market_sell_order(SYMBOL, POS_SIZE)
            msg = f"🔻 <b>SELL</b> | Price: {price}"

        if msg:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
            
    except Exception as e:
        logger.error(f"Loop error: {e}")
    finally:
        await exchange.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running
    is_running = True
    chat_id = update.effective_message.chat_id
    
    context.job_queue.run_repeating(trade_loop, interval=60, first=10, chat_id=chat_id, name='trade_job')
    await update.message.reply_text("Бот запущен (Free Mode)!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running
    is_running = False
    for job in context.job_queue.jobs(): job.schedule_removal()
    await update.message.reply_text("Бот остановлен.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Упрощенный статус для проверки
    await update.message.reply_text(f"Бот работает. Режим Sandbox: {IS_SANDBOX}")

if __name__ == '__main__':
    keep_alive()  # <--- ЗАПУСКАЕМ ВЕБ-СЕРВЕР ПЕРЕД БОТОМ
    
    if not TG_TOKEN:
        print("Нет токена")
        exit()
        
    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    
    print("Бот запущен...")
    app.run_polling()
