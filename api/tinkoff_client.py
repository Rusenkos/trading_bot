"""
Модуль для работы с API Тинькофф Инвестиций версии 0.2.0b111.
Предоставляет унифицированный интерфейс для доступа к API.
"""
import logging
import time
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime, timedelta

# Updated imports for version 0.2.0b111
from tinkoff.invest import (
    Client, 
    RequestError, 
    CandleInterval,
    OrderDirection, 
    OrderType, 
    Order,
    InstrumentIdType,
    Quotation,
    PositionsResponse,
    PositionsSecurities
)
from tinkoff.invest.utils import quotation_to_decimal, now
from tinkoff.invest.exceptions import AioRequestError, StatusError

logger = logging.getLogger(__name__)

class TinkoffClient:
    """
    Обертка для Tinkoff API v0.2.0b111.
    Обеспечивает безопасное взаимодействие с API и обработку ошибок.
    """
    
    def __init__(self, token: str, config=None):
        """
        Инициализация клиента API
        
        Args:
            token: Токен API Тинькофф
            config: Объект конфигурации
        """
        self.token = token
        self.config = config
        self.client = None
        self.account_id = None
        self.account_type = None
        
        # Кэш для хранения информации об инструментах
        self.instruments_cache = {}
    
    def connect(self) -> bool:
        """
        Подключение к API
        
        Returns:
            bool: True если подключение успешно, иначе False
        """
        try:
            self.client = Client(self.token)
            logger.info("Подключение к API Тинькофф выполнено успешно")
            
            # Получаем и сохраняем ID счета
            accounts = self.client.users.get_accounts().accounts
            if not accounts:
                logger.error("Не найдено активных счетов")
                return False
            
            self.account_id = accounts[0].id
            self.account_type = accounts[0].type.name
            logger.info(f"Выбран счет: {self.account_id} ({self.account_type})")
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при подключении к API Тинькофф: {e}")
            return False
    
    def disconnect(self) -> None:
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
    
    def ensure_connection(self) -> bool:
        """
        Проверка и установка соединения при необходимости
        
        Returns:
            bool: True если соединение установлено, иначе False
        """
        if self.client is None:
            return self.connect()
        return True
    
    def get_accounts(self) -> List[Dict[str, Any]]:
        """
        Получение списка счетов
        
        Returns:
            list: Список счетов или пустой список при ошибке
        """
        if not self.ensure_connection():
            return []
        
        try:
            accounts = self.client.users.get_accounts().accounts
            
            # Преобразуем в список словарей для удобства
            result = []
            for acc in accounts:
                result.append({
                    'id': acc.id,
                    'type': acc.type.name,
                    'name': acc.name,
                    'status': acc.status.name,
                    'opened_date': acc.opened_date.strftime('%Y-%m-%d') if hasattr(acc, 'opened_date') and acc.opened_date else None
                })
            
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении списка счетов: {e}")
            return []
    
    def get_portfolio(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Получение портфеля
        
        Args:
            account_id: ID счета (если None, используется account_id из класса)
            
        Returns:
            dict: Информация о портфеле или пустой словарь при ошибке
        """
        if not self.ensure_connection():
            return {}
        
        acc_id = account_id or self.account_id
        if not acc_id:
            logger.error("ID счета не указан")
            return {}
        
        try:
            portfolio = self.client.operations.get_portfolio(account_id=acc_id)
            
            # Преобразуем в словарь
            result = {
                'total_amount_currencies': [],
                'total_amount_shares': 0,
                'total_amount_bonds': 0,
                'total_amount_etf': 0,
                'positions': []
            }
            
            # Обрабатываем валютные позиции
            for money in portfolio.total_amount_currencies:
                result['total_amount_currencies'].append({
                    'currency': money.currency,
                    'amount': float(quotation_to_decimal(money.value))
                })
            
            # Обрабатываем позиции
            for position in portfolio.positions:
                pos = {
                    'figi': position.figi,
                    'instrument_type': position.instrument_type,
                    'quantity': float(quotation_to_decimal(position.quantity)),
                    'average_price': float(quotation_to_decimal(position.average_position_price)),
                    'expected_yield': float(quotation_to_decimal(position.expected_yield)),
                    'current_price': float(quotation_to_decimal(position.current_price)),
                    'currency': position.average_position_price.currency
                }
                
                # Получаем тикер по FIGI
                ticker = self.get_ticker_by_figi(position.figi)
                if ticker:
                    pos['ticker'] = ticker
                
                result['positions'].append(pos)
            
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении портфеля: {e}")
            return {}
    
    def get_instrument_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Получение информации об инструменте
        
        Args:
            symbol: Тикер инструмента
            
        Returns:
            dict: Информация об инструменте или None при ошибке
        """
        # Проверяем кэш
        if symbol in self.instruments_cache:
            return self.instruments_cache[symbol]
        
        if not self.ensure_connection():
            return None
        
        max_retries = 3
        
        for retry in range(max_retries):
            try:
                # Поиск инструмента по тикеру
                instruments = self.client.instruments.find_instrument(query=symbol)
                
                if not instruments.instruments:
                    logger.error(f"Инструмент {symbol} не найден")
                    return None
                
                # Находим соответствующий инструмент (предпочитаем акции MOEX)
                found_instrument = None
                for instr in instruments.instruments:
                    if instr.ticker == symbol and instr.instrument_type == 'share':
                        # Для акций Мосбиржи
                        if hasattr(instr, 'class_code') and instr.class_code == 'TQBR':
                            found_instrument = instr
                            break
                        # Если не нашли TQBR, используем первый подходящий
                        if not found_instrument:
                            found_instrument = instr
                
                # Если не нашли акции, используем первый инструмент
                if not found_instrument and instruments.instruments:
                    found_instrument = instruments.instruments[0]
                
                if not found_instrument:
                    logger.error(f"Не удалось найти подходящий инструмент для {symbol}")
                    return None
                
                # Формируем информацию об инструменте
                instrument_info = {
                    'figi': found_instrument.figi,
                    'ticker': found_instrument.ticker,
                    'name': found_instrument.name,
                    'lot': found_instrument.lot,
                    'currency': found_instrument.currency,
                    'class_code': found_instrument.class_code if hasattr(found_instrument, 'class_code') else None,
                    'exchange': found_instrument.exchange if hasattr(found_instrument, 'exchange') else None,
                    'uid': found_instrument.uid if hasattr(found_instrument, 'uid') else None
                }
                
                # Сохраняем в кэш
                self.instruments_cache[symbol] = instrument_info
                
                logger.info(f"Получена информация об инструменте {symbol}: {instrument_info}")
                return instrument_info
                
            except Exception as e:
                if retry < max_retries - 1:
                    sleep_time = (2 ** retry) + 0.5
                    logger.warning(f"Ошибка при получении информации об инструменте {symbol}: {e}. "
                                  f"Повторная попытка через {sleep_time:.2f} сек...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Ошибка при получении информации об инструменте {symbol}: {e}")
                    return None
    
    def get_figi_by_ticker(self, ticker: str) -> Optional[str]:
        """
        Получение FIGI по тикеру
        
        Args:
            ticker: Тикер инструмента
            
        Returns:
            str: FIGI инструмента или None при ошибке
        """
        instrument = self.get_instrument_info(ticker)
        if not instrument:
            return None
        return instrument.get('figi')
    
    def get_ticker_by_figi(self, figi: str) -> Optional[str]:
        """
        Получение тикера по FIGI
        
        Args:
            figi: FIGI инструмента
            
        Returns:
            str: Тикер инструмента или None при ошибке
        """
        # Проверяем в кэше
        for ticker, info in self.instruments_cache.items():
            if info.get('figi') == figi:
                return ticker
        
        if not self.ensure_connection():
            return None
        
        try:
            # Получаем информацию об инструменте по FIGI
            instrument = self.client.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
                id=figi
            ).instrument
            
            # Добавляем в кэш
            self.instruments_cache[instrument.ticker] = {
                'figi': figi,
                'ticker': instrument.ticker,
                'name': instrument.name,
                'lot': instrument.lot,
                'currency': instrument.currency,
                'class_code': instrument.class_code if hasattr(instrument, 'class_code') else None
            }
            
            return instrument.ticker
            
        except Exception as e:
            logger.error(f"Ошибка при получении тикера по FIGI {figi}: {e}")
            return None
    
    def get_historical_candles(self, symbol_or_figi: str, interval: CandleInterval, 
                             from_date: datetime, to_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Получение исторических свечей
        
        Args:
            symbol_or_figi: Тикер или FIGI инструмента
            interval: Интервал свечей
            from_date: Начальная дата
            to_date: Конечная дата (если None, используется текущая дата)
            
        Returns:
            list: Список свечей или пустой список при ошибке
        """
        if not self.ensure_connection():
            return []
        
        # Определяем FIGI
        figi = symbol_or_figi
        if not symbol_or_figi.startswith('BBG'):
            figi = self.get_figi_by_ticker(symbol_or_figi)
            if not figi:
                logger.error(f"Не удалось получить FIGI для {symbol_or_figi}")
                return []
        
        # Если конечная дата не указана, используем текущую
        if to_date is None:
            to_date = now()
        
        max_retries = 3
        all_candles = []
        
        try:
            # Получаем свечи
            for retry in range(max_retries):
                try:
                    candles_response = self.client.market_data.get_candles(
                        figi=figi,
                        from_=from_date,
                        to=to_date,
                        interval=interval
                    )
                    
                    # Преобразуем свечи в список словарей
                    for candle in candles_response.candles:
                        all_candles.append({
                            'time': candle.time,
                            'open': float(quotation_to_decimal(candle.open)),
                            'high': float(quotation_to_decimal(candle.high)),
                            'low': float(quotation_to_decimal(candle.low)),
                            'close': float(quotation_to_decimal(candle.close)),
                            'volume': candle.volume
                        })
                    
                    break  # Если успешно получили свечи, выходим из цикла повторов
                    
                except RequestError as e:
                    if retry < max_retries - 1:
                        sleep_time = (2 ** retry) + 0.5
                        logger.warning(f"Ошибка при получении свечей: {e}. "
                                      f"Повторная попытка через {sleep_time:.2f} сек...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"Ошибка при получении свечей для {symbol_or_figi}: {e}")
                        return []
            
            return all_candles
            
        except Exception as e:
            logger.error(f"Ошибка при получении исторических свечей для {symbol_or_figi}: {e}")
            return []
    
    def get_current_price(self, symbol_or_figi: str) -> Optional[float]:
        """
        Получение текущей цены инструмента
        
        Args:
            symbol_or_figi: Тикер или FIGI инструмента
            
        Returns:
            float: Текущая цена или None при ошибке
        """
        if not self.ensure_connection():
            return None
        
        # Определяем FIGI
        figi = symbol_or_figi
        if not symbol_or_figi.startswith('BBG'):
            figi = self.get_figi_by_ticker(symbol_or_figi)
            if not figi:
                logger.error(f"Не удалось получить FIGI для {symbol_or_figi}")
                return None
        
        try:
            # Получаем последние цены для инструмента
            response = self.client.market_data.get_last_prices(figi=[figi])
            
            if response and response.last_prices:
                last_price = response.last_prices[0]
                return float(quotation_to_decimal(last_price.price))
            
            # Если нет последних цен, пробуем получить стакан
            order_book = self.client.market_data.get_order_book(figi=figi, depth=1)
            
            if order_book.last_price:
                # Если есть цена последней сделки, берем ее
                return float(quotation_to_decimal(order_book.last_price))
            elif order_book.asks and order_book.bids:
                # Если есть заявки, берем середину между лучшими
                best_ask = float(quotation_to_decimal(order_book.asks[0].price))
                best_bid = float(quotation_to_decimal(order_book.bids[0].price))
                return (best_ask + best_bid) / 2
            elif order_book.close_price:
                # Иначе берем цену закрытия предыдущей сессии
                return float(quotation_to_decimal(order_book.close_price))
            else:
                logger.warning(f"Не удалось получить текущую цену для {figi}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при получении текущей цены для {symbol_or_figi}: {e}")
            return None

    def place_order(self, symbol_or_figi: str, direction: str, quantity: int, 
                  price: Optional[float] = None, order_type: str = "market") -> Optional[Dict[str, Any]]:
        """
        Размещение торгового ордера
        
        Args:
            symbol_or_figi: Тикер или FIGI инструмента
            direction: Направление ('buy' или 'sell')
            quantity: Количество лотов
            price: Цена для лимитного ордера (None для рыночного)
            order_type: Тип ордера ('market' или 'limit')
            
        Returns:
            dict: Информация о размещенном ордере или None при ошибке
        """
        if not self.ensure_connection():
            return None
        
        # Проверяем параметры
        if quantity <= 0:
            logger.warning(f"Некорректное количество лотов: {quantity}")
            return None
        
        if direction not in ['buy', 'sell']:
            logger.error(f"Некорректное направление: {direction}")
            return None
        
        # Определяем FIGI
        figi = symbol_or_figi
        if not symbol_or_figi.startswith('BBG'):
            figi = self.get_figi_by_ticker(symbol_or_figi)
            if not figi:
                logger.error(f"Не удалось получить FIGI для {symbol_or_figi}")
                return None
        
        try:
            # Преобразуем направление и тип ордера в формат API
            order_direction = OrderDirection.ORDER_DIRECTION_BUY if direction == 'buy' else OrderDirection.ORDER_DIRECTION_SELL
            order_type_enum = OrderType.ORDER_TYPE_MARKET if order_type == 'market' else OrderType.ORDER_TYPE_LIMIT
            
            # Формируем уникальный ID ордера
            now_str = datetime.now().strftime('%Y%m%d%H%M%S%f')
            order_id = f"{symbol_or_figi}_{direction}_{now_str}"
            
            # Создаем объект цены для лимитного ордера
            price_obj = None
            if price is not None and order_type == 'limit':
                # Тут нужно преобразовать float -> Quotation
                # В новой версии API может быть другой способ
                int_part = int(price)
                frac_part = int((price - int_part) * 1_000_000_000)
                price_obj = Quotation(units=int_part, nano=frac_part)
            
            # Размещаем ордер
            order_response = self.client.orders.post_order(
                instrument_id=figi,
                quantity=quantity,
                price=price_obj,  # Для рыночного ордера может быть None
                direction=order_direction,
                account_id=self.account_id,
                order_type=order_type_enum,
                order_id=order_id
            )
            
            # Преобразуем ответ в словарь
            result = {
                'order_id': order_id,
                'figi': figi,
                'direction': direction,
                'quantity': quantity,
                'status': order_response.execution_report_status.name,
                'requested_lots': order_response.lots_requested,
                'executed_lots': order_response.lots_executed
            }
            
            # Если есть цена исполнения, добавляем ее
            if order_response.executed_order_price:
                result['executed_price'] = float(quotation_to_decimal(order_response.executed_order_price))
            
            # Если есть комиссия, добавляем ее
            if order_response.executed_commission:
                result['commission'] = float(quotation_to_decimal(order_response.executed_commission))
            
            logger.info(f"Размещен ордер {direction.upper()} для {symbol_or_figi} "
                      f"на {quantity} лотов, ID: {order_id}, статус: {result['status']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при размещении ордера для {symbol_or_figi}: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Отмена ордера
        
        Args:
            order_id: ID ордера
            
        Returns:
            bool: True, если ордер успешно отменен
        """
        if not self.ensure_connection():
            return False
        
        try:
            # Отменяем ордер
            self.client.orders.cancel_order(
                account_id=self.account_id,
                order_id=order_id
            )
            
            logger.info(f"Ордер {order_id} отменен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отмене ордера {order_id}: {e}")
            return False
    
    def get_order_state(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение состояния ордера
        
        Args:
            order_id: ID ордера
            
        Returns:
            dict: Информация о состоянии ордера или None при ошибке
        """
        if not self.ensure_connection():
            return None
        
        try:
            # Получаем состояние ордера
            order_state = self.client.orders.get_order_state(
                account_id=self.account_id,
                order_id=order_id
            )
            
            # Преобразуем информацию
            result = {
                'order_id': order_id,
                'figi': order_state.figi,
                'direction': 'buy' if order_state.direction.name == 'ORDER_DIRECTION_BUY' else 'sell',
                'status': order_state.execution_report_status.name,
                'requested_lots': order_state.lots_requested,
                'executed_lots': order_state.lots_executed
            }
            
            # Если есть цена исполнения, добавляем ее
            if order_state.executed_order_price:
                result['executed_price'] = float(quotation_to_decimal(order_state.executed_order_price))
            
            # Если есть комиссия, добавляем ее
            if order_state.executed_commission:
                result['commission'] = float(quotation_to_decimal(order_state.executed_commission))
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении состояния ордера {order_id}: {e}")
            return None
    
    def get_orders(self) -> List[Dict[str, Any]]:
        """
        Получение списка активных ордеров
        
        Returns:
            list: Список активных ордеров или пустой список при ошибке
        """
        if not self.ensure_connection():
            return []
        
        try:
            # Получаем активные ордера
            orders = self.client.orders.get_orders(account_id=self.account_id).orders
            
            # Преобразуем в список словарей
            result = []
            for order in orders:
                order_info = {
                    'order_id': order.order_id,
                    'figi': order.figi,
                    'direction': 'buy' if order.direction.name == 'ORDER_DIRECTION_BUY' else 'sell',
                    'status': order.execution_report_status.name,
                    'requested_lots': order.lots_requested,
                    'executed_lots': order.lots_executed,
                    'type': order.order_type.name,
                    'initial_security_price': float(quotation_to_decimal(order.initial_security_price)) if order.initial_security_price else None,
                    'create_date': order.order_date
                }
                
                # Получаем тикер по FIGI
                ticker = self.get_ticker_by_figi(order.figi)
                if ticker:
                    order_info['ticker'] = ticker
                
                result.append(order_info)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка активных ордеров: {e}")
            return []
    
    def get_operations(self, from_date: datetime, to_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Получение операций за период
        
        Args:
            from_date: Начальная дата
            to_date: Конечная дата (если None, используется текущая дата)
            
        Returns:
            list: Список операций или пустой список при ошибке
        """
        if not self.ensure_connection():
            return []
        
        # Если конечная дата не указана, используем текущую
        if to_date is None:
            to_date = now()
        
        try:
            # Получаем операции
            operations = self.client.operations.get_operations(
                account_id=self.account_id,
                from_=from_date,
                to=to_date
            ).operations
            
            # Преобразуем в список словарей
            result = []
            for op in operations:
                operation_info = {
                    'id': op.id,
                    'type': op.type.name,
                    'date': op.date,
                    'state': op.state.name,
                    'currency': op.currency,
                    'instrument_type': op.instrument_type.name if op.instrument_type else None,
                    'figi': op.figi,
                    'quantity': op.quantity if hasattr(op, 'quantity') else None,
                    'payment': float(quotation_to_decimal(op.payment)) if op.payment else None
                }
                
                # Получаем тикер по FIGI
                if op.figi:
                    ticker = self.get_ticker_by_figi(op.figi)
                    if ticker:
                        operation_info['ticker'] = ticker
                
                result.append(operation_info)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении операций: {e}")
            return []
    
    def get_trading_status(self, symbol_or_figi: str) -> Dict[str, Any]:
        """
        Получение торгового статуса инструмента
        
        Args:
            symbol_or_figi: Тикер или FIGI инструмента
            
        Returns:
            dict: Информация о торговом статусе или пустой словарь при ошибке
        """
        if not self.ensure_connection():
            return {}
        
        # Определяем FIGI
        figi = symbol_or_figi
        if not symbol_or_figi.startswith('BBG'):
            figi = self.get_figi_by_ticker(symbol_or_figi)
            if not figi:
                logger.error(f"Не удалось получить FIGI для {symbol_or_figi}")
                return {}
        
        try:
            # Получаем торговый статус
            status = self.client.market_data.get_trading_status(figi=figi)
            
            # Преобразуем в словарь
            result = {
                'figi': figi,
                'trading_status': status.trading_status.name,
                'market_order_available': status.market_order_available_flag,
                'limit_order_available': status.limit_order_available_flag,
                'api_trade_available': status.api_trade_available_flag
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении торгового статуса для {symbol_or_figi}: {e}")
            return {}
    
    def get_market_open_status(self) -> bool:
        """
        Проверка, открыт ли рынок в данный момент
        
        Returns:
            bool: True если рынок открыт, иначе False
        """
        # Можно проверить статус торгов для любого популярного инструмента
        test_ticker = 'SBER'
        
        try:
            status = self.get_trading_status(test_ticker)
            
            # Проверяем статус торгов
            if status and status.get('trading_status') == 'TRADING_STATUS_NORMAL_TRADING':
                return True
            
            return False
            
        except Exception:
            # В случае ошибки проверяем по расписанию
            try:
                import pytz
                from datetime import datetime
                
                # Московское время
                moscow_tz = pytz.timezone('Europe/Moscow')
                now_moscow = datetime.now(moscow_tz)
                
                # Проверяем день недели
                weekday = now_moscow.weekday()  # 0-6, 0=понедельник
                if weekday >= 5:  # 5=суббота, 6=воскресенье
                    return False
                
                # Проверяем время
                if now_moscow.hour < 10 or now_moscow.hour >= 19:
                    return False
                
                return True
                
            except Exception as e:
                logger.error(f"Ошибка при проверке статуса рынка: {e}")
                return False
    
    def __del__(self):
        """
        Деструктор класса
        """
        self.disconnect()