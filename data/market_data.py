"""
Модуль для получения и обработки рыночных данных через API Тинькофф.
"""
import pandas as pd
import numpy as np
import logging
import time
import random
import os
from datetime import datetime, timedelta

# Updated imports for version 0.2.0b111
from tinkoff.invest import (
    Client, 
    CandleInterval,
    InstrumentIdType,
    Quotation,
    RequestError
)
from tinkoff.invest.utils import now, quotation_to_decimal

logger = logging.getLogger(__name__)

class MarketDataProvider:
    """
    Провайдер рыночных данных.
    Отвечает за получение и кэширование данных с биржи.
    """
    def __init__(self, token=None, config=None):
        """
        Инициализация провайдера данных
        
        Args:
            token: Токен API Тинькофф (если не указан, берется из Config)
            config: Объект конфигурации
        """
        self.token = token
        self.config = config
        self.client = None
        self.cache_dir = config.CACHE_DIR if config else "data_cache"
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        
        self.instruments_cache = {}  # Кэш информации об инструментах
        self.data_cache = {}         # Кэш данных в памяти
    
    def connect(self):
        """
        Подключение к API
        
        Returns:
            bool: True если подключение успешно, иначе False
        """
        if hasattr(self.config, 'DEMO_MODE') and self.config.DEMO_MODE:
            logger.info("Инициализация в демо-режиме (без подключения к API)")
            return True
            
        try:
            self.client = Client(self.token or self.config.TINKOFF_TOKEN)
            logger.info("Подключение к API Тинькофф выполнено успешно")
            return True
        except Exception as e:
            logger.error(f"Ошибка при подключении к API Тинькофф: {e}")
            return False
    
    def disconnect(self):
        """
        Отключение от API
        """
        if self.client:
            try:
                self.client.close()
                logger.info("Отключение от API Тинькофф выполнено")
            except Exception as e:
                logger.warning(f"Ошибка при закрытии соединения с API: {e}")
            self.client = None
    
    def _get_cache_path(self, symbol, interval):
        """
        Получение пути к файлу кэша
        
        Args:
            symbol: Тикер инструмента
            interval: Интервал свечей
        
        Returns:
            str: Путь к файлу кэша
        """
        interval_str = str(interval).split('.')[-1]
        return f"{self.cache_dir}/{symbol}_{interval_str}.csv"
    
    def _save_to_cache(self, symbol, interval, df):
        """
        Сохранение данных в кэш
        
        Args:
            symbol: Тикер инструмента
            interval: Интервал свечей
            df: DataFrame с данными
        
        Returns:
            bool: True если данные успешно сохранены
        """
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
        """
        Загрузка данных из кэша
        
        Args:
            symbol: Тикер инструмента
            interval: Интервал свечей
        
        Returns:
            DataFrame: Данные из кэша или None при ошибке
        """
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
        """
        Генерация тестовых данных для отладки и демонстрации в демо-режиме
        
        Args:
            symbol: Тикер инструмента
            days: Количество дней для генерации
            
        Returns:
            DataFrame: Сгенерированные данные
        """
        logger.info(f"Генерация тестовых данных для {symbol} (демо-режим)")
        seed = sum(ord(c) for c in symbol)
        np.random.seed(seed)
        
        # Создаем тестовые данные на основе синусоиды с шумом
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Генерируем даты (только рабочие дни)
        dates = []
        current_date = start_date
        while current_date <= end_date:
            # Пропускаем выходные (5, 6 = суббота, воскресенье)
            if current_date.weekday() < 5:
                dates.append(current_date)
            current_date += timedelta(days=1)
        
        # Генерируем цены
        n = len(dates)
        base_price = 100.0  # Базовая цена
        trend = np.linspace(0, 30, n)  # Увеличенный восходящий тренд
        cycles = np.sin(np.linspace(0, 10*np.pi, n)) * 25  # Больше циклов и амплитуда
        noise = np.random.normal(0, 3, n)  # Меньше шума для четких сигналов
        
        # Добавляем несколько характерных паттернов для тестирования стратегий
        for i in range(5, n, 15):
            if i < n-5:
                cycles[i:i+5] += 15  # Резкие подъемы
                cycles[i+7:i+12] -= 15 if i+12 < n else 0  # Резкие падения
        
        prices = base_price + trend + cycles + noise
        prices = np.maximum(prices, 50)  # Цена не может быть ниже 50
        
        # Создаем DataFrame
        df = pd.DataFrame(index=dates)
        df.index.name = 'time'
        df['open'] = prices
        df['close'] = prices + np.random.normal(0, 1, n)
        df['high'] = np.maximum(df['open'], df['close']) + abs(np.random.normal(0, 2, n))
        df['low'] = np.minimum(df['open'], df['close']) - abs(np.random.normal(0, 2, n))
        
        # Генерируем объемы с корреляцией с движениями цены
        df['volume'] = np.random.randint(1000, 10000, n)
        for i in range(1, n):
            # Увеличиваем объем при сильных движениях цены
            price_change = abs(df['close'].iloc[i] - df['close'].iloc[i-1])
            if price_change > 5:  # Сильное движение
                df.loc[df.index[i], 'volume'] *= 2  # Удваиваем объем
        
        return df
    
    def get_instrument_info(self, symbol):
        """
        Получение информации об инструменте
        
        Args:
            symbol: Тикер инструмента
            
        Returns:
            dict: Информация об инструменте или None в случае ошибки
        """
        # Проверяем кэш
        if symbol in self.instruments_cache:
            return self.instruments_cache[symbol]
        
        # Проверяем наличие демо-режима
        if hasattr(self.config, 'DEMO_MODE') and self.config.DEMO_MODE:
            # Генерируем заглушку с базовой информацией
            instrument_info = {
                'figi': f"DEMO_{symbol}",
                'ticker': symbol,
                'name': f"{symbol} (Demo)",
                'lot': 1,
                'currency': 'rub',
                'class_code': 'TQBR'  # Добавляем class_code для демо-режима
            }
            self.instruments_cache[symbol] = instrument_info
            return instrument_info
        
        max_retries = 3
        
        for retry in range(max_retries):
            try:
                if not self.client:
                    self.connect()
                
                instruments = self.client.instruments.find_instrument(query=symbol)
                if not instruments.instruments:
                    logger.error(f"Инструмент {symbol} не найден")
                    return None
                
                # Создаем список всех найденных инструментов с типом 'share'
                share_instruments = []
                
                for instr in instruments.instruments:
                    logger.info(f"Найден инструмент: {instr.ticker} ({instr.figi}), тип: {instr.instrument_type}")
                    
                    # Собираем все акции с точным совпадением тикера
                    if instr.ticker == symbol and instr.instrument_type.name == 'INSTRUMENT_TYPE_SHARE':
                        # Для акций Мосбиржи
                        if hasattr(instr, 'class_code') and instr.class_code == 'TQBR':
                            share_instruments.append(instr)
                        # Если не нашли TQBR, используем первый подходящий
                        if not share_instruments:
                            share_instruments.append(instr)
                
                # Если нашли акции, выбираем лучшую по приоритету
                if share_instruments:
                    # Предпочитаем акции с class_code TQBR (основной рынок Мосбиржи)
                    tqbr_shares = [s for s in share_instruments if hasattr(s, 'class_code') and s.class_code == 'TQBR']
                    if tqbr_shares:
                        best_instrument = tqbr_shares[0]
                    else:
                        best_instrument = share_instruments[0]
                    
                    instrument_info = {
                        'figi': best_instrument.figi,
                        'ticker': best_instrument.ticker,
                        'name': best_instrument.name if hasattr(best_instrument, 'name') else symbol,
                        'lot': best_instrument.lot if hasattr(best_instrument, 'lot') else 1,
                        'currency': best_instrument.currency if hasattr(best_instrument, 'currency') else 'rub',
                        'class_code': best_instrument.class_code if hasattr(best_instrument, 'class_code') else None
                    }
                    
                    # Сохраняем в кэш
                    self.instruments_cache[symbol] = instrument_info
                    
                    logger.info(f"Выбран инструмент: {instrument_info['ticker']} ({instrument_info['figi']})")
                    return instrument_info
                
                # Если не нашли акций, берем первый инструмент
                if instruments.instruments:
                    first_instr = instruments.instruments[0]
                    instrument_info = {
                        'figi': first_instr.figi,
                        'ticker': first_instr.ticker,
                        'name': first_instr.name if hasattr(first_instr, 'name') else symbol,
                        'lot': first_instr.lot if hasattr(first_instr, 'lot') else 1,
                        'currency': first_instr.currency if hasattr(first_instr, 'currency') else 'rub',
                        'class_code': first_instr.class_code if hasattr(first_instr, 'class_code') else None
                    }
                    
                    # Сохраняем в кэш
                    self.instruments_cache[symbol] = instrument_info
                    
                    logger.info(f"Выбран первый доступный инструмент: {instrument_info['ticker']} ({instrument_info['figi']})")
                    return instrument_info
                
                logger.error(f"Не удалось найти подходящий инструмент для {symbol}")
                return None
                
            except Exception as e:
                if retry < max_retries - 1:
                    sleep_time = (2 ** retry) + random.uniform(0, 1)
                    logger.warning(f"Ошибка при получении информации об инструменте {symbol}: {e}. "
                                  f"Повторная попытка через {sleep_time:.2f} сек...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Не удалось получить информацию об инструменте {symbol} после {max_retries} попыток: {e}")
                    return None
    
    def get_historical_data(self, symbol, interval, days_back=60):
        """
        Получение исторических данных через API Тинькофф
        
        Args:
            symbol: Тикер инструмента
            interval: Интервал свечей
            days_back: Количество дней для анализа
            
        Returns:
            DataFrame: Исторические данные или None в случае ошибки
        """
        logger.info(f"Получение исторических данных для {symbol}")
        
        # Уникальный ключ для кэширования в памяти
        cache_key = f"{symbol}_{interval}_{days_back}"
        
        # Проверяем кэш в памяти
        if cache_key in self.data_cache:
            return self.data_cache[cache_key]
        
        # Проверяем использование кэширования
        use_cache = True
        if hasattr(self.config, 'USE_CACHE'):
            use_cache = self.config.USE_CACHE
        
        # Пробуем загрузить из файлового кэша
        if use_cache and not hasattr(self.config, 'DEMO_MODE') or not self.config.DEMO_MODE:
            cached_data = self._load_from_cache(symbol, interval)
            if cached_data is not None:
                min_data_points = self.config.MIN_DATA_POINTS if hasattr(self.config, 'MIN_DATA_POINTS') else 20
                if len(cached_data) >= min_data_points:
                    self.data_cache[cache_key] = cached_data
                    return cached_data
        
        # Проверяем наличие демо-режима
        if hasattr(self.config, 'DEMO_MODE') and self.config.DEMO_MODE:
            # Генерируем тестовые данные для демонстрации
            df = self.generate_sample_data(symbol, days=days_back)
            if use_cache:
                self._save_to_cache(symbol, interval, df)
            self.data_cache[cache_key] = df
            return df
        
        # Если в кэше недостаточно данных, запрашиваем через API
        instrument = self.get_instrument_info(symbol)
        if not instrument:
            return None
        
        figi = instrument['figi']
        
        # Максимальный период для запроса зависит от интервала
        max_days_per_request = 7  # По умолчанию
        
        if hasattr(self.config, 'MAX_DAYS_PER_REQUEST'):
            max_days_per_request = self.config.MAX_DAYS_PER_REQUEST.get(interval, 7)
        
        # Ограничиваем период запроса, чтобы избежать проблем с данными
        days_back = min(days_back, 365)  # Не более года для любого интервала
        
        end_time = now()
        all_candles = []
        requests_success = 0
        
        # Разбиваем запрос на несколько периодов
        for i in range(0, days_back, max_days_per_request):
            # Вычисляем период для текущего запроса
            current_days = min(max_days_per_request, days_back - i)
            start_time = end_time - timedelta(days=current_days)
            
            logger.info(f"Запрос данных для {symbol} с {start_time.date()} по {end_time.date()}")
            
            # Делаем запрос с повторными попытками
            max_retries = 3
            success = False
            
            for retry in range(max_retries):
                try:
                    if not self.client:
                        self.connect()
                    
                    # Получаем свечи за текущий период
                    candles_response = self.client.market_data.get_candles(
                        figi=figi,
                        from_=start_time,
                        to=end_time,
                        interval=interval
                    )
                    
                    # Проверяем, есть ли свечи в ответе
                    if candles_response.candles:
                        requests_success += 1
                        success = True
                        # Обрабатываем полученные свечи
                        for candle in candles_response.candles:
                            all_candles.append({
                                'time': candle.time,
                                'open': float(quotation_to_decimal(candle.open)),
                                'high': float(quotation_to_decimal(candle.high)),
                                'low': float(quotation_to_decimal(candle.low)),
                                'close': float(quotation_to_decimal(candle.close)),
                                'volume': candle.volume
                            })
                    # Выходим из цикла повторов если запрос успешный
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
            
            # Устанавливаем конец текущего периода как начало следующего
            end_time = start_time
            
            # Проверяем, достаточно ли данных у нас уже есть
            min_data_points = self.config.MIN_DATA_POINTS if hasattr(self.config, 'MIN_DATA_POINTS') else 20
            if len(all_candles) > min_data_points and requests_success >= 2:
                logger.info(f"Собрано достаточно данных для {symbol}: {len(all_candles)} свечей")
                break
        
        if not all_candles:
            logger.warning(f"Нет данных для {symbol}. Генерируем демо-данные для тестирования.")
            # Генерируем тестовые данные для демонстрации
            df = self.generate_sample_data(symbol, days=days_back)
            if use_cache:
                self._save_to_cache(symbol, interval, df)
            self.data_cache[cache_key] = df
            return df
        
        # Преобразуем в DataFrame
        df = pd.DataFrame(all_candles)
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
        
        # Сортировка по времени (от старых к новым)
        df.sort_index(inplace=True)
        
        logger.info(f"Получено {len(df)} свечей для {symbol} c {df.index.min()} по {df.index.max()}")
        
        # Проверяем качество данных
        missing_values = df.isnull().sum().sum()
        if missing_values > 0:
            logger.warning(f"Обнаружено {missing_values} пропущенных значений в данных для {symbol}")
            # Заполняем пропуски в данных методом forward fill
            df = df.fillna(method='ffill')
        
        # Проверка на достаточное количество данных для анализа
        min_data_points = self.config.MIN_DATA_POINTS if hasattr(self.config, 'MIN_DATA_POINTS') else 20
        if len(df) < min_data_points:
            logger.warning(f"Недостаточно данных для анализа {symbol}: {len(df)} < {min_data_points}. "
                          f"Генерируем демо-данные.")
            # Генерируем тестовые данные для демонстрации
            df = self.generate_sample_data(symbol, days=days_back)
        
        # Сохраняем данные в кэш для последующего использования
        if use_cache:
            self._save_to_cache(symbol, interval, df)
        
        # Сохраняем в памяти
        self.data_cache[cache_key] = df
        
        return df
    
    def get_current_price(self, symbol_or_figi):
        """
        Получение текущей цены инструмента
        
        Args:
            symbol_or_figi: Тикер или FIGI инструмента
            
        Returns:
            float: Текущая цена или None в случае ошибки
        """
        # Проверяем наличие демо-режима
        if hasattr(self.config, 'DEMO_MODE') and self.config.DEMO_MODE:
            # В демо-режиме возвращаем последнюю цену из исторических данных
            if symbol_or_figi.startswith('DEMO_'):
                symbol = symbol_or_figi.replace('DEMO_', '')
            else:
                symbol = symbol_or_figi
                
            data = self.get_historical_data(symbol, CandleInterval.CANDLE_INTERVAL_DAY, days_back=5)
            if data is not None and not data.empty:
                return data['close'].iloc[-1]
            return 100.0  # Заглушка для демо-режима
        
        try:
            if not self.client:
                self.connect()
            
            # Определяем FIGI по переданному параметру
            figi = symbol_or_figi
            if not symbol_or_figi.startswith('BBG') and not symbol_or_figi.startswith('DEMO_'):
                # Это тикер, получаем FIGI
                instrument = self.get_instrument_info(symbol_or_figi)
                if not instrument:
                    return None
                figi = instrument['figi']
            
            # Получаем последние цены инструмента
            last_prices = self.client.market_data.get_last_prices(figi=[figi])
            
            if last_prices and last_prices.last_prices:
                return float(quotation_to_decimal(last_prices.last_prices[0].price))
            
            # Если не получили последние цены, пробуем получить стакан
            order_book = self.client.market_data.get_order_book(figi=figi, depth=1)
            
            if order_book.asks and order_book.bids:
                # Усредненная цена между лучшим бидом и аском
                best_ask = float(quotation_to_decimal(order_book.asks[0].price))
                best_bid = float(quotation_to_decimal(order_book.bids[0].price))
                return (best_ask + best_bid) / 2
            elif order_book.last_price:
                # Если есть цена последней сделки
                return float(quotation_to_decimal(order_book.last_price))
            else:
                logger.warning(f"Не удалось получить текущую цену для {symbol_or_figi}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при получении текущей цены для {symbol_or_figi}: {e}")
            return None
    
    def update_data(self, symbol, interval):
        """
        Обновление данных после завершения торговой сессии
        
        Args:
            symbol: Тикер инструмента
            interval: Интервал свечей
            
        Returns:
            DataFrame: Обновленные данные или None в случае ошибки
        """
        logger.info(f"Обновление данных для {symbol}")
        
        # Проверяем наличие демо-режима
        if hasattr(self.config, 'DEMO_MODE') and self.config.DEMO_MODE:
            # В демо-режиме просто обновляем кэш
            return self.get_historical_data(symbol, interval, days_back=30)
        
        # Загружаем последние данные из кэша
        cached_data = None
        if hasattr(self.config, 'USE_CACHE') and self.config.USE_CACHE:
            cached_data = self._load_from_cache(symbol, interval)
        
        if cached_data is None or cached_data.empty:
            # Если кэш пуст, загружаем все данные
            return self.get_historical_data(symbol, interval)
        
        # Определяем последнюю дату в кэше
        last_date = cached_data.index[-1]
        
        # Получаем данные с последней даты до текущего момента
        instrument = self.get_instrument_info(symbol)
        if not instrument:
            return cached_data  # Возвращаем хотя бы кэшированные данные
        
        figi = instrument['figi']
        
        try:
            if not self.client:
                self.connect()
            
            # Добавляем небольшой запас для перекрытия
            start_time = last_date - timedelta(days=1)
            end_time = now()
            
            # Проверяем, нужно ли обновлять данные
            if (end_time - start_time).days < 1:
                logger.info(f"Данные для {symbol} актуальны, обновление не требуется")
                return cached_data
            
            logger.info(f"Запрос новых данных для {symbol} с {start_time.date()} по {end_time.date()}")
            
            # Получаем свечи за период
            candles_response = self.client.market_data.get_candles(
                figi=figi,
                from_=start_time,
                to=end_time,
                interval=interval
            )
            
            if not candles_response.candles:
                logger.info(f"Нет новых данных для {symbol}")
                return cached_data
            
            # Преобразуем новые свечи в DataFrame
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
            
            # Объединяем старые и новые данные
            # Удаляем дубликаты из кэшированных данных
            cached_data = cached_data[cached_data.index < new_df.index[0]]
            
            # Объединяем данные
            updated_df = pd.concat([cached_data, new_df])
            
            logger.info(f"Данные для {symbol} обновлены, получено {len(new_df)} новых свечей")
            
            # Сохраняем обновленные данные в кэш
            if hasattr(self.config, 'USE_CACHE') and self.config.USE_CACHE:
                self._save_to_cache(symbol, interval, updated_df)
            
            # Обновляем кэш в памяти
            cache_key = f"{symbol}_{interval}_30"  # Стандартный ключ для 30 дней
            self.data_cache[cache_key] = updated_df
            
            return updated_df
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении данных для {symbol}: {e}")
            return cached_data  # Возвращаем хотя бы кэшированные данные
    
    def is_market_open(self, figi=None):
        """
        Проверка, открыт ли рынок в данный момент
        
        Args:
            figi: FIGI инструмента (если None, проверяется по расписанию)
            
        Returns:
            bool: True если рынок открыт, иначе False
        """
        try:
            # Если задан FIGI, проверяем через API
            if figi and not figi.startswith('DEMO_') and self.client:
                try:
                    trading_status = self.client.market_data.get_trading_status(figi=figi)
                    return (trading_status.trading_status.name == 'TRADING_STATUS_NORMAL_TRADING' and 
                           trading_status.market_order_available_flag)
                except Exception as e:
                    logger.warning(f"Ошибка при проверке торгового статуса: {e}, "
                                  f"проверяем по расписанию")
            
            # Иначе проверяем по времени
            import pytz
            from datetime import datetime
            
            # Московское время
            moscow_tz = pytz.timezone('Europe/Moscow')
            now_moscow = datetime.now(moscow_tz)
            
            # Проверяем день недели
            weekday = now_moscow.weekday()  # 0-6, 0=понедельник
            if weekday >= 5:  # 5=суббота, 6=воскресенье
                logger.debug(f"Сегодня выходной (день недели: {weekday}), рынок закрыт")
                return False
            
            # Проверяем время
            open_hour = self.config.MARKET_OPEN_HOUR if hasattr(self.config, 'MARKET_OPEN_HOUR') else 10
            close_hour = self.config.MARKET_CLOSE_HOUR if hasattr(self.config, 'MARKET_CLOSE_HOUR') else 19
            
            if now_moscow.hour < open_hour or now_moscow.hour >= close_hour:
                logger.debug(f"Текущее время ({now_moscow.hour}:{now_moscow.minute}) "
                            f"вне торговой сессии ({open_hour}:00-{close_hour}:00), рынок закрыт")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса рынка: {e}")
            # В случае ошибки лучше считать, что рынок закрыт
            return False
    
    def __del__(self):
        """
        Деструктор класса
        """
        self.disconnect()