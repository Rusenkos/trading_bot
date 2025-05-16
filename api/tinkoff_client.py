import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from tinkoff.invest import (
    Client,
    RequestError,
    CandleInterval,
    OrderDirection,
    OrderType,
    InstrumentIdType,
    Quotation
)
from tinkoff.invest.utils import quotation_to_decimal, now

logger = logging.getLogger(__name__)

class TinkoffClient:
    def __init__(self, token: str, config=None):
        self.token = token
        self.config = config
        self.account_id = None
        self.account_type = None
        self.instruments_cache = {}

    def get_accounts(self) -> List[Dict[str, Any]]:
        try:
            with Client(self.token) as client:
                accounts = client.users.get_accounts().accounts
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
        acc_id = account_id or self.account_id
        if not acc_id:
            logger.error("ID счета не указан")
            return {}
        try:
            with Client(self.token) as client:
                portfolio = client.operations.get_portfolio(account_id=acc_id)
            result = {
                'total_amount_currencies': [],
                'positions': []
            }
            for money in portfolio.total_amount_currencies:
                result['total_amount_currencies'].append({
                    'currency': money.currency,
                    'amount': float(quotation_to_decimal(money.value))
                })
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
                ticker = self.get_ticker_by_figi(position.figi)
                if ticker:
                    pos['ticker'] = ticker
                result['positions'].append(pos)
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении портфеля: {e}")
            return {}

    def get_instrument_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        if symbol in self.instruments_cache:
            return self.instruments_cache[symbol]
        max_retries = 3
        for retry in range(max_retries):
            try:
                with Client(self.token) as client:
                    instruments = client.instruments.find_instrument(query=symbol)
                if not instruments.instruments:
                    logger.error(f"Инструмент {symbol} не найден")
                    return None
                found_instrument = None
                for instr in instruments.instruments:
                    if instr.ticker == symbol and getattr(instr.instrument_type, 'name', None) == 'INSTRUMENT_TYPE_SHARE':
                        if hasattr(instr, 'class_code') and instr.class_code == 'TQBR':
                            found_instrument = instr
                            break
                        if not found_instrument:
                            found_instrument = instr
                if not found_instrument and instruments.instruments:
                    found_instrument = instruments.instruments[0]
                if not found_instrument:
                    logger.error(f"Не удалось найти подходящий инструмент для {symbol}")
                    return None
                instrument_info = {
                    'figi': found_instrument.figi,
                    'ticker': found_instrument.ticker,
                    'name': found_instrument.name,
                    'lot': found_instrument.lot,
                    'currency': found_instrument.currency,
                    'class_code': found_instrument.class_code if hasattr(found_instrument, 'class_code') else None,
                    'exchange': getattr(found_instrument, 'exchange', None),
                    'uid': getattr(found_instrument, 'uid', None)
                }
                self.instruments_cache[symbol] = instrument_info
                logger.info(f"Получена информация об инструменте {symbol}: {instrument_info}")
                return instrument_info
            except Exception as e:
                if retry < max_retries - 1:
                    sleep_time = (2 ** retry) + 0.5
                    logger.warning(f"Ошибка при получении информации об инструменте {symbol}: {e}. Повторная попытка через {sleep_time:.2f} сек...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Ошибка при получении информации об инструменте {symbol}: {e}")
                    return None

    def get_figi_by_ticker(self, ticker: str) -> Optional[str]:
        instrument = self.get_instrument_info(ticker)
        if not instrument:
            return None
        return instrument.get('figi')

    def get_ticker_by_figi(self, figi: str) -> Optional[str]:
        for ticker, info in self.instruments_cache.items():
            if info.get('figi') == figi:
                return ticker
        try:
            with Client(self.token) as client:
                instrument = client.instruments.get_instrument_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
                    id=figi
                ).instrument
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
        figi = symbol_or_figi
        if not symbol_or_figi.startswith('BBG'):
            figi = self.get_figi_by_ticker(symbol_or_figi)
            if not figi:
                logger.error(f"Не удалось получить FIGI для {symbol_or_figi}")
                return []
        if to_date is None:
            to_date = now()
        max_retries = 3
        all_candles = []
        try:
            for retry in range(max_retries):
                try:
                    with Client(self.token) as client:
                        candles_response = client.market_data.get_candles(
                            figi=figi,
                            from_=from_date,
                            to=to_date,
                            interval=interval
                        )
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
                        sleep_time = (2 ** retry) + 0.5
                        logger.warning(f"Ошибка при получении свечей: {e}. Повторная попытка через {sleep_time:.2f} сек...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"Ошибка при получении свечей для {symbol_or_figi}: {e}")
                        return []
            return all_candles
        except Exception as e:
            logger.error(f"Ошибка при получении исторических свечей для {symbol_or_figi}: {e}")
            return []

    def get_current_price(self, symbol_or_figi: str) -> Optional[float]:
        figi = symbol_or_figi
        if not symbol_or_figi.startswith('BBG'):
            figi = self.get_figi_by_ticker(symbol_or_figi)
            if not figi:
                return None
        try:
            with Client(self.token) as client:
                response = client.market_data.get_last_prices(figi=[figi])
                if response and response.last_prices:
                    last_price = response.last_prices[0]
                    return float(quotation_to_decimal(last_price.price))
                order_book = client.market_data.get_order_book(figi=figi, depth=1)
                if order_book.last_price:
                    return float(quotation_to_decimal(order_book.last_price))
                elif order_book.asks and order_book.bids:
                    best_ask = float(quotation_to_decimal(order_book.asks[0].price))
                    best_bid = float(quotation_to_decimal(order_book.bids[0].price))
                    return (best_ask + best_bid) / 2
                elif order_book.close_price:
                    return float(quotation_to_decimal(order_book.close_price))
                else:
                    logger.warning(f"Не удалось получить текущую цену для {figi}")
                    return None
        except Exception as e:
            logger.error(f"Ошибка при получении текущей цены для {symbol_or_figi}: {e}")
            return None

    def place_order(self, symbol_or_figi: str, direction: str, quantity: int,
                   price: Optional[float] = None, order_type: str = "market") -> Optional[Dict[str, Any]]:
        if quantity <= 0:
            logger.warning(f"Некорректное количество лотов: {quantity}")
            return None
        if direction not in ['buy', 'sell']:
            logger.error(f"Некорректное направление: {direction}")
            return None
        figi = symbol_or_figi
        if not symbol_or_figi.startswith('BBG'):
            figi = self.get_figi_by_ticker(symbol_or_figi)
            if not figi:
                logger.error(f"Не удалось получить FIGI для {symbol_or_figi}")
                return None
        try:
            order_direction = OrderDirection.ORDER_DIRECTION_BUY if direction == 'buy' else OrderDirection.ORDER_DIRECTION_SELL
            order_type_enum = OrderType.ORDER_TYPE_MARKET if order_type == 'market' else OrderType.ORDER_TYPE_LIMIT
            now_str = datetime.now().strftime('%Y%m%d%H%M%S%f')
            order_id = f"{symbol_or_figi}_{direction}_{now_str}"
            price_obj = None
            if price is not None and order_type == 'limit':
                int_part = int(price)
                frac_part = int((price - int_part) * 1_000_000_000)
                price_obj = Quotation(units=int_part, nano=frac_part)
            with Client(self.token) as client:
                accounts = client.users.get_accounts().accounts
                account_id = accounts[0].id if accounts else None
                order_response = client.orders.post_order(
                    instrument_id=figi,
                    quantity=quantity,
                    price=price_obj,
                    direction=order_direction,
                    account_id=account_id,
                    order_type=order_type_enum,
                    order_id=order_id
                )
            result = {
                'order_id': order_id,
                'figi': figi,
                'direction': direction,
                'quantity': quantity,
                'status': order_response.execution_report_status.name,
                'requested_lots': order_response.lots_requested,
                'executed_lots': order_response.lots_executed
            }
            if order_response.executed_order_price:
                result['executed_price'] = float(quotation_to_decimal(order_response.executed_order_price))
            if order_response.executed_commission:
                result['commission'] = float(quotation_to_decimal(order_response.executed_commission))
            return result
        except Exception as e:
            logger.error(f"Ошибка при размещении ордера для {symbol_or_figi}: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        try:
            with Client(self.token) as client:
                accounts = client.users.get_accounts().accounts
                account_id = accounts[0].id if accounts else None
                client.orders.cancel_order(
                    account_id=account_id,
                    order_id=order_id
                )
            logger.info(f"Ордер {order_id} отменен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при отмене ордера {order_id}: {e}")
            return False

    def get_order_state(self, order_id: str) -> Optional[Dict[str, Any]]:
        try:
            with Client(self.token) as client:
                accounts = client.users.get_accounts().accounts
                account_id = accounts[0].id if accounts else None
                order_state = client.orders.get_order_state(
                    account_id=account_id,
                    order_id=order_id
                )
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

    def get_orders(self) -> List[Dict[str, Any]]:
        try:
            with Client(self.token) as client:
                accounts = client.users.get_accounts().accounts
                account_id = accounts[0].id if accounts else None
                orders = client.orders.get_orders(account_id=account_id).orders
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
                ticker = self.get_ticker_by_figi(order.figi)
                if ticker:
                    order_info['ticker'] = ticker
                result.append(order_info)
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении списка активных ордеров: {e}")
            return []

    def get_operations(self, from_date: datetime, to_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if to_date is None:
            to_date = now()
        try:
            with Client(self.token) as client:
                accounts = client.users.get_accounts().accounts
                account_id = accounts[0].id if accounts else None
                operations = client.operations.get_operations(
                    account_id=account_id,
                    from_=from_date,
                    to=to_date
                ).operations
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
                    'quantity': getattr(op, 'quantity', None),
                    'payment': float(quotation_to_decimal(op.payment)) if op.payment else None
                }
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
        figi = symbol_or_figi
        if not symbol_or_figi.startswith('BBG'):
            figi = self.get_figi_by_ticker(symbol_or_figi)
            if not figi:
                logger.error(f"Не удалось получить FIGI для {symbol_or_figi}")
                return {}
        try:
            with Client(self.token) as client:
                status = client.market_data.get_trading_status(figi=figi)
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
        test_ticker = 'SBER'
        try:
            status = self.get_trading_status(test_ticker)
            if status and status.get('trading_status') == 'TRADING_STATUS_NORMAL_TRADING':
                return True
            return False
        except Exception:
            try:
                import pytz
                from datetime import datetime
                moscow_tz = pytz.timezone('Europe/Moscow')
                now_moscow = datetime.now(moscow_tz)
                weekday = now_moscow.weekday()
                if weekday >= 5:
                    return False
                if now_moscow.hour < 10 or now_moscow.hour >= 19:
                    return False
                return True
            except Exception as e:
                logger.error(f"Ошибка при проверке статуса рынка: {e}")
                return False