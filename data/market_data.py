import pandas as pd
import numpy as np
import logging
import time
import random
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from tinkoff.invest import (
    Client, 
    CandleInterval,
    InstrumentIdType,
    Quotation,
    RequestError
)
from tinkoff.invest.utils import now, quotation_to_decimal
from dotenv import load_dotenv
load_dotenv()
from config.config import Config
logger = logging.getLogger(__name__)

class MarketDataProvider:
    """
    Провайдер рыночных данных для Tinkoff Invest API 0.2.x
    """

    def __init__(self, token=None, config=None):
        self.token = token or (config.TINKOFF_TOKEN if config else None)
        self.config = config
        self.cache_dir = config.CACHE_DIR if config else "data_cache"
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        self.instruments_cache = {}
        self.data_cache = {}

    def _get_cache_path(self, symbol, interval):
        interval_str = str(interval).split('.')[-1]
        return f"{self.cache_dir}/{symbol}_{interval_str}.csv"

    def _save_to_cache(self, symbol, interval, df):
        if df is not None and not df.empty:
            try:
                cache_path = self._get_cache_path(symbol, interval)
                df.to_csv(cache_path)
                logger.info(f"Данные для {symbol} сохранены в кэш: {cache_path}")
                return True
            except Exception as e:
                logger.error(f"Ошибка при сохранении данных в кэш: {e}")
        return False

    def _load_from_cache(self, symbol, interval):
        try:
            cache_path = self._get_cache_path(symbol, interval)
            if os.path.exists(cache_path):
                df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                logger.info(f"Данные для {symbol} загружены из кэша: {len(df)} записей")
                return df
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных из кэша: {e}")
        return None

    def generate_sample_data(self, symbol, days=60):
        logger.info(f"Генерация тестовых данных для {symbol} (демо-режим)")
        seed = sum(ord(c) for c in symbol)
        np.random.seed(seed)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        dates = []
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:
                dates.append(current_date)
            current_date += timedelta(days=1)
        n = len(dates)
        base_price = 100.0
        trend = np.linspace(0, 30, n)
        cycles = np.sin(np.linspace(0, 10*np.pi, n)) * 25
        noise = np.random.normal(0, 3, n)
        for i in range(5, n, 15):
            if i < n-5:
                cycles[i:i+5] += 15
                cycles[i+7:i+12] -= 15 if i+12 < n else 0
        prices = base_price + trend + cycles + noise
        prices = np.maximum(prices, 50)
        df = pd.DataFrame(index=dates)
        df.index.name = 'time'
        df['open'] = prices
        df['close'] = prices + np.random.normal(0, 1, n)
        df['high'] = np.maximum(df['open'], df['close']) + abs(np.random.normal(0, 2, n))
        df['low'] = np.minimum(df['open'], df['close']) - abs(np.random.normal(0, 2, n))
        df['volume'] = np.random.randint(1000, 10000, n)
        for i in range(1, n):
            price_change = abs(df['close'].iloc[i] - df['close'].iloc[i-1])
            if price_change > 5:
                df.loc[df.index[i], 'volume'] *= 2
        return df

    def get_instrument_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        # Поиск в кэше
        if symbol in self.instruments_cache:
            return self.instruments_cache[symbol]
        
        try:
            with Client(self.token) as client:
                instruments = client.instruments.find_instrument(query=symbol)
            
            if not instruments.instruments:
                logger.error(f"Инструмент {symbol} не найден")
                return None
                
            # Приоритет: российские акции с кодом TQBR
            share_instruments = []
            tqbr_shares = []
            
            for instr in instruments.instruments:
                if instr.ticker == symbol and getattr(instr.instrument_type, 'name', None) == 'INSTRUMENT_TYPE_SHARE':
                    share_instruments.append(instr)
                    if hasattr(instr, 'class_code') and instr.class_code == 'TQBR':
                        tqbr_shares.append(instr)
            
            # Выбираем в первую очередь акции TQBR
            if tqbr_shares:
                selected_instrument = tqbr_shares[0]
            elif share_instruments:
                selected_instrument = share_instruments[0]
            elif instruments.instruments:
                selected_instrument = instruments.instruments[0]
            else:
                return None
                
            # Создаем информацию об инструменте
            instrument_info = {
                'figi': selected_instrument.figi,
                'ticker': selected_instrument.ticker,
                'name': selected_instrument.name,
                'lot': selected_instrument.lot,
                'currency': selected_instrument.currency,
                'class_code': selected_instrument.class_code if hasattr(selected_instrument, 'class_code') else None
            }
            
            self.instruments_cache[symbol] = instrument_info
            return instrument_info
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации об инструменте {symbol}: {e}")
            return None

    def get_historical_data(self, symbol, interval, days_back=60):
        logger.info(f"Получение исторических данных для {symbol}")
        cache_key = f"{symbol}_{interval}_{days_back}"
        if cache_key in self.data_cache:
            return self.data_cache[cache_key]
        use_cache = True
        if hasattr(self.config, 'USE_CACHE'):
            use_cache = self.config.USE_CACHE
        if use_cache and not getattr(self.config, 'DEMO_MODE', False):
            cached_data = self._load_from_cache(symbol, interval)
            if cached_data is not None:
                min_data_points = getattr(self.config, 'MIN_DATA_POINTS', 20)
                if len(cached_data) >= min_data_points:
                    self.data_cache[cache_key] = cached_data
                    return cached_data
        if getattr(self.config, 'DEMO_MODE', False):
            df = self.generate_sample_data(symbol, days=days_back)
            if use_cache:
                self._save_to_cache(symbol, interval, df)
            self.data_cache[cache_key] = df
            return df

        instrument = self.get_instrument_info(symbol)
        if not instrument:
            return None
        figi = instrument['figi']
        max_days_per_request = 7
        if hasattr(self.config, 'MAX_DAYS_PER_REQUEST'):
            max_days_per_request = self.config.MAX_DAYS_PER_REQUEST.get(interval, 7)
        days_back = min(days_back, 365)
        end_time = now()
        all_candles = []
        requests_success = 0
        for i in range(0, days_back, max_days_per_request):
            current_days = min(max_days_per_request, days_back - i)
            start_time = end_time - timedelta(days=current_days)
            logger.info(f"Запрос данных для {symbol} с {start_time.date()} по {end_time.date()}")
            max_retries = 3
            for retry in range(max_retries):
                try:
                    with Client(self.token) as client:
                        candles_response = client.market_data.get_candles(
                            figi=figi,
                            from_=start_time,
                            to=end_time,
                            interval=interval
                        )
                    if candles_response.candles:
                        requests_success += 1
                        for candle in candles_response.candles:
                            all_candles.append({
                                'time': candle.time,
                                'open': float(quotation_to_decimal(candle.open)),
                                'high': float(quotation_to_decimal(candle.high)),
                                'low': float(quotation_to_decimal(candle.low)),
                                'close': float(quotation_to_decimal(candle.close)),
                                'volume': candle.volume
                            })
                    break
                except RequestError as e:
                    if retry < max_retries - 1:
                        sleep_time = (2 ** retry) + random.uniform(0, 1)
                        logger.warning(f"Ошибка при получении свечей: {e}. "
                                       f"Повторная попытка через {sleep_time:.2f} сек...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"Ошибка при получении свечей для {symbol} за период "
                                     f"{start_time.date()} - {end_time.date()}: {e}")
                except Exception as e:
                    if retry < max_retries - 1:
                        sleep_time = (2 ** retry) + random.uniform(0, 1)
                        logger.warning(f"Общая ошибка при получении свечей: {e}. "
                                       f"Повторная попытка через {sleep_time:.2f} сек...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"Общая ошибка при получении свечей для {symbol}: {e}")
            end_time = start_time
            min_data_points = getattr(self.config, 'MIN_DATA_POINTS', 20)
            if len(all_candles) > min_data_points and requests_success >= 2:
                logger.info(f"Собрано достаточно данных для {symbol}: {len(all_candles)} свечей")
                break
        if not all_candles:
            logger.warning(f"Нет данных для {symbol}. Генерируем демо-данные для тестирования.")
            df = self.generate_sample_data(symbol, days=days_back)
            if use_cache:
                self._save_to_cache(symbol, interval, df)
            self.data_cache[cache_key] = df
            return df
        df = pd.DataFrame(all_candles)
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        df.sort_index(inplace=True)
        logger.info(f"Получено {len(df)} свечей для {symbol} c {df.index.min()} по {df.index.max()}")
        missing_values = df.isnull().sum().sum()
        if missing_values > 0:
            logger.warning(f"Обнаружено {missing_values} пропущенных значений в данных для {symbol}")
            df = df.fillna(method='ffill')
        min_data_points = getattr(self.config, 'MIN_DATA_POINTS', 20)
        if len(df) < min_data_points:
            logger.warning(f"Недостаточно данных для анализа {symbol}: {len(df)} < {min_data_points}. "
                           f"Генерируем демо-данные.")
            df = self.generate_sample_data(symbol, days=days_back)
        if use_cache:
            self._save_to_cache(symbol, interval, df)
        self.data_cache[cache_key] = df
        return df

    def get_current_price(self, symbol_or_figi):
        if hasattr(self.config, 'DEMO_MODE') and self.config.DEMO_MODE:
            if symbol_or_figi.startswith('DEMO_'):
                symbol = symbol_or_figi.replace('DEMO_', '')
            else:
                symbol = symbol_or_figi
            data = self.get_historical_data(symbol, CandleInterval.CANDLE_INTERVAL_DAY, days_back=5)
            if data is not None and not data.empty:
                return data['close'].iloc[-1]
            return 100.0
        try:
            if symbol_or_figi.startswith('BBG') or symbol_or_figi.startswith('DEMO_'):
                figi = symbol_or_figi
            else:
                instrument = self.get_instrument_info(symbol_or_figi)
                if not instrument:
                    return None
                figi = instrument['figi']
            with Client(self.token) as client:
                last_prices = client.market_data.get_last_prices(figi=[figi])
                if last_prices and last_prices.last_prices:
                    return float(quotation_to_decimal(last_prices.last_prices[0].price))
                order_book = client.market_data.get_order_book(figi=figi, depth=1)
                if order_book.asks and order_book.bids:
                    best_ask = float(quotation_to_decimal(order_book.asks[0].price))
                    best_bid = float(quotation_to_decimal(order_book.bids[0].price))
                    return (best_ask + best_bid) / 2
                elif order_book.last_price:
                    return float(quotation_to_decimal(order_book.last_price))
                else:
                    logger.warning(f"Не удалось получить текущую цену для {symbol_or_figi}")
                    return None
        except Exception as e:
            logger.error(f"Ошибка при получении текущей цены для {symbol_or_figi}: {e}")
            return None

    def update_data(self, symbol, interval):
        logger.info(f"Обновление данных для {symbol}")
        if hasattr(self.config, 'DEMO_MODE') and self.config.DEMO_MODE:
            return self.get_historical_data(symbol, interval, days_back=30)
        cached_data = None
        if hasattr(self.config, 'USE_CACHE') and self.config.USE_CACHE:
            cached_data = self._load_from_cache(symbol, interval)
        if cached_data is None or cached_data.empty:
            return self.get_historical_data(symbol, interval)
        last_date = cached_data.index[-1]
        instrument = self.get_instrument_info(symbol)
        if not instrument:
            return cached_data
        figi = instrument['figi']
        try:
            start_time = last_date - timedelta(days=1)
            end_time = now()
            if (end_time - start_time).days < 1:
                logger.info(f"Данные для {symbol} актуальны, обновление не требуется")
                return cached_data
            logger.info(f"Запрос новых данных для {symbol} с {start_time.date()} по {end_time.date()}")
            with Client(self.token) as client:
                candles_response = client.market_data.get_candles(
                    figi=figi,
                    from_=start_time,
                    to=end_time,
                    interval=interval
                )
            if not candles_response.candles:
                logger.info(f"Нет новых данных для {symbol}")
                return cached_data
            new_candles = []
            for candle in candles_response.candles:
                new_candles.append({
                    'time': candle.time,
                    'open': float(quotation_to_decimal(candle.open)),
                    'high': float(quotation_to_decimal(candle.high)),
                    'low': float(quotation_to_decimal(candle.low)),
                    'close': float(quotation_to_decimal(candle.close)),
                    'volume': candle.volume
                })
            new_df = pd.DataFrame(new_candles)
            new_df['time'] = pd.to_datetime(new_df['time'])
            new_df.set_index('time', inplace=True)
            new_df.sort_index(inplace=True)
            cached_data = cached_data[cached_data.index < new_df.index[0]]
            updated_df = pd.concat([cached_data, new_df])
            logger.info(f"Данные для {symbol} обновлены, получено {len(new_df)} новых свечей")
            if hasattr(self.config, 'USE_CACHE') and self.config.USE_CACHE:
                self._save_to_cache(symbol, interval, updated_df)
            cache_key = f"{symbol}_{interval}_30"
            self.data_cache[cache_key] = updated_df
            return updated_df
        except Exception as e:
            logger.error(f"Ошибка при обновлении данных для {symbol}: {e}")
            return cached_data

    def is_market_open(self, figi=None):
        try:
            if figi and not figi.startswith('DEMO_'):
                try:
                    with Client(self.token) as client:
                        trading_status = client.market_data.get_trading_status(figi=figi)
                        return (trading_status.trading_status.name == 'TRADING_STATUS_NORMAL_TRADING' and 
                                trading_status.market_order_available_flag)
                except Exception as e:
                    logger.warning(f"Ошибка при проверке торгового статуса: {e}, проверяем по расписанию")
            import pytz
            from datetime import datetime
            moscow_tz = pytz.timezone('Europe/Moscow')
            now_moscow = datetime.now(moscow_tz)
            weekday = now_moscow.weekday()
            if weekday >= 5:
                logger.debug(f"Сегодня выходной (день недели: {weekday}), рынок закрыт")
                return False
            open_hour = getattr(self.config, 'MARKET_OPEN_HOUR', 10)
            close_hour = getattr(self.config, 'MARKET_CLOSE_HOUR', 19)
            if now_moscow.hour < open_hour or now_moscow.hour >= close_hour:
                logger.debug(f"Текущее время ({now_moscow.hour}:{now_moscow.minute}) вне торговой сессии "
                             f"({open_hour}:00-{close_hour}:00), рынок закрыт")
                return False
            return True
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса рынка: {e}")
            return False

    def __del__(self):
        pass  # больше не нужно self.disconnect()