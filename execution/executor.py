"""
Модуль для исполнения торговых операций через API Тинькофф.
"""
from typing import Dict, List, Optional, Tuple, Any, Union
import logging
import time
from datetime import datetime
# Updated imports for version 0.2.0b111
from tinkoff.invest import (
    Client, 
    OrderDirection, 
    OrderType, 
    Order,
    InstrumentIdType,
    Quotation
)
from tinkoff.invest.utils import quotation_to_decimal, now

from execution.risk_manager import RiskManager
from execution.position_manager import PositionManager

logger = logging.getLogger(__name__)

class TradingExecutor:
    """
    Исполнитель торговых операций.
    
    Отвечает за:
    - Размещение торговых ордеров через API
    - Проверку состояния ордеров
    - Обновление информации о счете
    - Контроль стоп-лоссов и тейк-профитов
    """
    
    def __init__(self, client, config=None, risk_manager=None, position_manager=None):
        """
        Инициализация исполнителя торговых операций
        
        Args:
            client: Клиент API Тинькофф
            config: Объект конфигурации
            risk_manager: Менеджер рисков
            position_manager: Менеджер позиций
        """
        self.client = client
        self.config = config
        
        # Создаем объекты менеджеров, если не переданы
        self.risk_manager = risk_manager or RiskManager(config)
        self.position_manager = position_manager or PositionManager(config)
        
        # Информация о счете
        self.account_id = None
        self.broker_account_type = None
        self.balance = 0
        self.portfolio = {}
        
        # Кэш инструментов
        self.instruments_cache = {}
    
    def update_account_info(self) -> bool:
        """
        Обновление информации о счете и портфеле
        
        Returns:
            bool: True, если информация успешно обновлена
        """
        try:
            # Получение списка счетов
            accounts = self.client.users.get_accounts().accounts
            if not accounts:
                logger.error("Не найдено активных счетов")
                return False
            
            # Используем первый счет (или можно выбрать конкретный)
            account = accounts[0]
            self.account_id = account.id
            self.broker_account_type = account.type.name
            
            logger.info(f"Выбран счет: {self.account_id} ({self.broker_account_type})")
            
            # Получение портфеля
            portfolio = self.client.operations.get_portfolio(account_id=self.account_id)
            
            # Обновление портфеля
            self.portfolio = {}
            for position in portfolio.positions:
                figi = position.figi
                instrument_type = position.instrument_type
                
                # Получаем тикер по FIGI
                ticker = self.get_ticker_by_figi(figi)
                
                # Преобразуем данные из API в читаемый формат
                quantity = float(quotation_to_decimal(position.quantity))
                average_price = float(quotation_to_decimal(position.average_position_price))
                
                # Сохраняем информацию о позиции
                if ticker:
                    self.portfolio[ticker] = {
                        'figi': figi,
                        'ticker': ticker,
                        'type': instrument_type,
                        'quantity': quantity,
                        'average_price': average_price,
                        'current_price': self.get_current_price(figi),
                        'position_uid': position.position_uid if hasattr(position, 'position_uid') else None
                    }
            
            # Получение баланса
            self.balance = 0
            for money in portfolio.total_amount_currencies:
                if money.currency == 'rub':
                    self.balance = float(quotation_to_decimal(money.value))
            
            logger.info(f"Баланс счета: {self.balance:.2f} RUB")
            logger.info(f"Текущие позиции в портфеле: {', '.join(self.portfolio.keys())}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении информации о счете: {e}")
            return False
    
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
        
        try:
            # Поиск инструмента по тикеру
            instruments = self.client.instruments.find_instrument(query=symbol)
            
            if not instruments.instruments:
                logger.error(f"Инструмент {symbol} не найден")
                return None
            
            # Находим соответствующий инструмент (предпочитаем акции MOEX)
            found_instrument = None
            for instr in instruments.instruments:
                if instr.ticker == symbol and instr.instrument_type.name == 'INSTRUMENT_TYPE_SHARE':
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
    
    def get_current_price(self, figi_or_ticker: str) -> Optional[float]:
        """
        Получение текущей цены инструмента
        
        Args:
            figi_or_ticker: FIGI или тикер инструмента
            
        Returns:
            float: Текущая цена или None при ошибке
        """
        # Определяем, это FIGI или тикер
        figi = figi_or_ticker
        if not figi_or_ticker.startswith('BBG'):
            # Это тикер, получаем FIGI
            figi = self.get_figi_by_ticker(figi_or_ticker)
            if not figi:
                return None
        
        try:
            # Получаем стакан глубиной 1 - это самый быстрый способ узнать актуальную цену
            order_book = self.client.market_data.get_order_book(figi=figi, depth=1)
            
            # Логика получения цены
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
            logger.error(f"Ошибка при получении текущей цены для {figi_or_ticker}: {e}")
            return None
    
    def calculate_quantity(self, symbol: str, price: float) -> Tuple[int, float]:
        """
        Расчет количества лотов и общей суммы для торговой операции
        
        Args:
            symbol: Тикер инструмента
            price: Текущая цена
            
        Returns:
            tuple: (количество лотов, общая сумма)
        """
        # Получаем информацию об инструменте
        instrument = self.get_instrument_info(symbol)
        if not instrument:
            logger.error(f"Не удалось получить информацию об инструменте {symbol}")
            return 0, 0
        
        # Размер лота
        lot_size = instrument.get('lot', 1)
        
        # Получаем текущие открытые позиции
        positions = self.position_manager.get_all_positions()
        
        # Рассчитываем размер позиции с учетом риск-менеджмента
        position_value, lots = self.risk_manager.calculate_position_size(
            self.balance, price, positions
        )
        
        # Корректируем с учетом размера лота
        max_lots = int(position_value / (price * lot_size))
        
        # Проверяем, что количество лотов положительное
        if max_lots <= 0:
            logger.warning(f"Недостаточно средств для покупки {symbol} по цене {price}")
            return 0, 0
        
        # Оценка общей суммы сделки
        total_value = max_lots * lot_size * price
        
        logger.info(f"Рассчитано количество лотов для {symbol}: {max_lots} лотов, "
                  f"примерная сумма: {total_value:.2f}")
        
        return max_lots, total_value
    
    def place_order(self, symbol: str, direction: str, quantity: int, order_type: str = "market") -> Optional[str]:
        """
        Размещение торгового ордера
        
        Args:
            symbol: Тикер инструмента
            direction: Направление ('buy' или 'sell')
            quantity: Количество лотов
            order_type: Тип ордера ('market' или 'limit')
            
        Returns:
            str: ID ордера или None при ошибке
        """
        # Проверяем параметры
        if quantity <= 0:
            logger.warning(f"Некорректное количество лотов: {quantity}")
            return None
        
        if direction not in ['buy', 'sell']:
            logger.error(f"Некорректное направление: {direction}")
            return None
        
        # Получаем FIGI инструмента
        figi = self.get_figi_by_ticker(symbol)
        if not figi:
            logger.error(f"Не удалось получить FIGI для {symbol}")
            return None
        
        try:
            # Преобразуем направление и тип ордера в формат API
            order_direction = OrderDirection.ORDER_DIRECTION_BUY if direction == 'buy' else OrderDirection.ORDER_DIRECTION_SELL
            order_type_enum = OrderType.ORDER_TYPE_MARKET if order_type == 'market' else OrderType.ORDER_TYPE_LIMIT
            
            # Формируем уникальный ID ордера
            now_str = datetime.now().strftime('%Y%m%d%H%M%S%f')
            order_id = f"{symbol}_{direction}_{now_str}"
            
            # Размещаем ордер
            order_response = self.client.orders.post_order(
                instrument_id=figi,
                quantity=quantity,
                price=None,  # Для рыночного ордера цена не указывается
                direction=order_direction,
                account_id=self.account_id,
                order_type=order_type_enum,
                order_id=order_id
            )
            
            # Получаем текущую цену для логирования
            current_price = self.get_current_price(figi)
            price_str = f" по примерной цене {current_price}" if current_price else ""
            
            logger.info(f"Размещен ордер {direction.upper()} для {symbol} на {quantity} лотов{price_str}, ID: {order_id}")
            
            # Проверяем статус ордера
            if order_response.execution_report_status.name == 'EXECUTION_REPORT_STATUS_FILL':
                # Ордер исполнен
                logger.info(f"Ордер {order_id} исполнен полностью")
                
                # Получаем фактическую цену исполнения
                executed_price = float(quotation_to_decimal(order_response.executed_order_price))
                executed_lots = order_response.lots_executed
                
                # Обновляем информацию о счете
                self.update_account_info()
                
                # Обрабатываем информацию о позиции
                if direction == 'buy':
                    # Создаем новую позицию
                    stop_loss, take_profit = self._calculate_stop_take_levels(executed_price, True)
                    
                    position_info = {
                        'entry_price': executed_price,
                        'quantity': executed_lots,
                        'entry_time': datetime.now().isoformat(),
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'direction': 'buy',
                        'value': executed_price * executed_lots,
                        'order_id': order_id
                    }
                    
                    # Добавляем позицию в менеджер позиций
                    self.position_manager.add_position(symbol, position_info)
                    
                    logger.info(f"Добавлена новая позиция {symbol}: цена={executed_price}, "
                              f"количество={executed_lots}, стоп={stop_loss}, тейк={take_profit}")
                
                elif direction == 'sell':
                    # Закрываем существующую позицию
                    position = self.position_manager.get_position(symbol)
                    
                    if position:
                        close_info = {
                            'close_price': executed_price,
                            'close_time': datetime.now().isoformat(),
                            'close_reason': 'sell_order'
                        }
                        
                        # Закрываем позицию в менеджере позиций
                        self.position_manager.close_position(symbol, close_info)
                        
                        logger.info(f"Закрыта позиция {symbol}: цена={executed_price}")
                    else:
                        logger.warning(f"Продажа {symbol}, но позиция не найдена в менеджере позиций")
            
            elif order_response.execution_report_status.name == 'EXECUTION_REPORT_STATUS_PARTIALLYFILL':
                # Ордер исполнен частично
                logger.info(f"Ордер {order_id} исполнен частично: {order_response.lots_executed} из {quantity} лотов")
                
                # Можно обработать частичное исполнение, но это сложнее
                # В данной реализации мы просто логируем это событие
            
            elif order_response.execution_report_status.name == 'EXECUTION_REPORT_STATUS_REJECTED':
                # Ордер отклонен
                logger.error(f"Ордер {order_id} отклонен: {order_response.rejection_reason}")
                return None
            
            return order_id
            
        except Exception as e:
            logger.error(f"Ошибка при размещении ордера для {symbol}: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Отмена ордера
        
        Args:
            order_id: ID ордера
            
        Returns:
            bool: True, если ордер успешно отменен
        """
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
        try:
            # Получаем состояние ордера
            order_state = self.client.orders.get_order_state(
                account_id=self.account_id,
                order_id=order_id
            )
            
            # Преобразуем информацию
            order_info = {
                'order_id': order_id,
                'figi': order_state.figi,
                'direction': 'buy' if order_state.direction.name == 'ORDER_DIRECTION_BUY' else 'sell',
                'status': order_state.execution_report_status.name,
                'requested_lots': order_state.lots_requested,
                'executed_lots': order_state.lots_executed,
                'initial_price': float(quotation_to_decimal(order_state.initial_security_price)) if order_state.initial_security_price else None,
                'executed_price': float(quotation_to_decimal(order_state.executed_order_price)) if order_state.executed_order_price else None
            }
            
            return order_info
            
        except Exception as e:
            logger.error(f"Ошибка при получении состояния ордера {order_id}: {e}")
            return None
    
    def check_stop_loss_and_trailing(self) -> None:
        """
        Проверка стоп-лоссов и трейлинг-стопов для всех открытых позиций
        """
        # Получаем все открытые позиции
        positions = self.position_manager.get_all_positions()
        
        if not positions:
            return
        
        for symbol, position in positions.items():
            # Получаем текущую цену
            current_price = self.get_current_price(symbol)
            if current_price is None:
                logger.warning(f"Не удалось получить текущую цену для {symbol}, пропускаем проверку стопов")
                continue
            
            # Проверяем срабатывание стоп-лосса или тейк-профита
            stop_result = self.risk_manager.check_stop_loss_take_profit(position, current_price)
            
            if stop_result == "stop_loss":
                # Сработал стоп-лосс
                logger.info(f"СТОП-ЛОСС для {symbol}: текущая цена {current_price} ниже стоп-лосса {position.get('stop_loss')}")
                
                # Отправляем рыночный ордер на продажу
                quantity = int(position.get('quantity', 0))
                order_id = self.place_order(symbol, 'sell', quantity)
                
                if order_id:
                    # Обновляем информацию о закрытии позиции
                    close_info = {
                        'close_price': current_price,
                        'close_time': datetime.now().isoformat(),
                        'close_reason': 'stop_loss'
                    }
                    
                    # Закрываем позицию в менеджере позиций
                    self.position_manager.close_position(symbol, close_info)
                
            elif stop_result == "take_profit":
                # Сработал тейк-профит
                logger.info(f"ТЕЙК-ПРОФИТ для {symbol}: текущая цена {current_price} выше тейк-профита {position.get('take_profit')}")
                
                # Отправляем рыночный ордер на продажу
                quantity = int(position.get('quantity', 0))
                order_id = self.place_order(symbol, 'sell', quantity)
                
                if order_id:
                    # Обновляем информацию о закрытии позиции
                    close_info = {
                        'close_price': current_price,
                        'close_time': datetime.now().isoformat(),
                        'close_reason': 'take_profit'
                    }
                    
                    # Закрываем позицию в менеджере позиций
                    self.position_manager.close_position(symbol, close_info)
            
            else:
                # Проверяем и обновляем трейлинг-стоп
                trailing_triggered, new_stop = self.risk_manager.check_trailing_stop(position, current_price)
                
                if trailing_triggered:
                    # Сработал трейлинг-стоп
                    logger.info(f"ТРЕЙЛИНГ-СТОП для {symbol}: текущая цена {current_price} ниже трейлинг-стопа {position.get('stop_loss')}")
                    
                    # Отправляем рыночный ордер на продажу
                    quantity = int(position.get('quantity', 0))
                    order_id = self.place_order(symbol, 'sell', quantity)
                    
                    if order_id:
                        # Обновляем информацию о закрытии позиции
                        close_info = {
                            'close_price': current_price,
                            'close_time': datetime.now().isoformat(),
                            'close_reason': 'trailing_stop'
                        }
                        
                        # Закрываем позицию в менеджере позиций
                        self.position_manager.close_position(symbol, close_info)
                
                elif new_stop > position.get('stop_loss', 0):
                    # Обновляем трейлинг-стоп
                    updates = {
                        'stop_loss': new_stop,
                        'max_price': current_price
                    }
                    self.position_manager.update_position(symbol, updates)
            
            # Проверяем максимальное время удержания позиции
            if self.risk_manager.check_holding_time(position):
                logger.info(f"Достигнуто максимальное время удержания позиции {symbol}")
                
                # Отправляем рыночный ордер на продажу
                quantity = int(position.get('quantity', 0))
                order_id = self.place_order(symbol, 'sell', quantity)
                
                if order_id:
                    # Обновляем информацию о закрытии позиции
                    close_info = {
                        'close_price': current_price,
                        'close_time': datetime.now().isoformat(),
                        'close_reason': 'max_holding_time'
                    }
                    
                    # Закрываем позицию в менеджере позиций
                    self.position_manager.close_position(symbol, close_info)
    
    def execute_trade_signal(self, symbol: str, signal_details: Dict[str, Any]) -> bool:
        """
        Исполнение торгового сигнала
        
        Args:
            symbol: Тикер инструмента
            signal_details: Детали сигнала
            
        Returns:
            bool: True, если сигнал успешно исполнен
        """
        signal_type = signal_details.get('type')
        
        if signal_type not in ['buy', 'sell']:
            logger.error(f"Неподдерживаемый тип сигнала: {signal_type}")
            return False
        
        # Проверяем наличие открытой позиции
        position_exists = self.position_manager.has_position(symbol)
        
        if signal_type == 'buy' and not position_exists:
            # Проверяем лимит на количество позиций
            if not self.risk_manager.check_position_limits(self.balance, self.position_manager.get_all_positions()):
                logger.warning(f"Не удалось открыть позицию {symbol}: превышен лимит позиций")
                return False
            
            # Получаем текущую цену
            current_price = signal_details.get('price') or self.get_current_price(symbol)
            if not current_price:
                logger.error(f"Не удалось получить цену для {symbol}")
                return False
            
            # Рассчитываем количество лотов
            lots, total_value = self.calculate_quantity(symbol, current_price)
            
            if lots <= 0:
                logger.warning(f"Не удалось рассчитать количество лотов для {symbol}")
                return False
            
            # Размещаем ордер на покупку
            order_id = self.place_order(symbol, 'buy', lots)
            
            return order_id is not None
        
        elif signal_type == 'sell' and position_exists:
            # Получаем информацию о позиции
            position = self.position_manager.get_position(symbol)
            
            # Получаем количество лотов
            quantity = int(position.get('quantity', 0))
            
            if quantity <= 0:
                logger.warning(f"Некорректное количество в позиции {symbol}: {quantity}")
                return False
            
            # Размещаем ордер на продажу
            order_id = self.place_order(symbol, 'sell', quantity)
            
            if order_id:
                # Причина закрытия
                close_reason = signal_details.get('reasons', ['sell_signal'])[0] if signal_details.get('reasons') else 'sell_signal'
                
                # Обновляем информацию о закрытии позиции
                close_info = {
                    'close_price': signal_details.get('price', self.get_current_price(symbol)),
                    'close_time': datetime.now().isoformat(),
                    'close_reason': close_reason
                }
                
                # Закрываем позицию в менеджере позиций
                self.position_manager.close_position(symbol, close_info)
            
            return order_id is not None
        
        else:
            # Несоответствие типа сигнала и состояния позиции
            logger.warning(f"Сигнал {signal_type} для {symbol} не может быть исполнен: "
                         f"позиция {'существует' if position_exists else 'не существует'}")
            return False
    
    def _calculate_stop_take_levels(self, price: float, is_buy: bool = True) -> Tuple[float, float]:
        """
        Рассчитывает уровни стоп-лосса и тейк-профита
        
        Args:
            price: Цена входа
            is_buy: True для длинной позиции
            
        Returns:
            tuple: (стоп-лосс, тейк-профит)
        """
        # Проценты из конфигурации или по умолчанию
        stop_loss_percent = getattr(self.config, 'STOP_LOSS_PERCENT', 2.5) / 100
        take_profit_percent = getattr(self.config, 'TAKE_PROFIT_PERCENT', 5.0) / 100
        
        if is_buy:
            # Для длинной позиции
            stop_loss = price * (1 - stop_loss_percent)
            take_profit = price * (1 + take_profit_percent)
        else:
            # Для короткой позиции (на будущее)
            stop_loss = price * (1 + stop_loss_percent)
            take_profit = price * (1 - take_profit_percent)
        
        return stop_loss, take_profit