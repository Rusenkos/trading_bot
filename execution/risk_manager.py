### execution/risk_manager.py ###
from typing import Dict, List, Optional, Tuple, Any
import logging
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RiskManager:
    """
    Класс для управления рисками и контроля позиций.
    
    Отвечает за:
    - Проверку и срабатывание стоп-лоссов и тейк-профитов
    - Управление трейлинг-стопами
    - Контроль максимального времени удержания позиции
    - Ограничение размера позиции по капиталу
    """
    
    def __init__(self, config=None):
        """
        Инициализация менеджера рисков
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        
        # Параметры риск-менеджмента
        self.stop_loss_percent = getattr(config, 'STOP_LOSS_PERCENT', 2.5) / 100  # По умолчанию 2.5%
        self.trailing_stop_percent = getattr(config, 'TRAILING_STOP_PERCENT', 1.8) / 100  # По умолчанию 1.8%
        self.take_profit_percent = getattr(config, 'TAKE_PROFIT_PERCENT', 5.0) / 100  # По умолчанию 5%
        self.max_position_size = getattr(config, 'MAX_POSITION_SIZE', 0.9)  # По умолчанию 90% капитала
        self.max_positions = getattr(config, 'MAX_POSITIONS', 1)  # По умолчанию 1 позиция
        self.max_holding_days = getattr(config, 'MAX_HOLDING_DAYS', 7)  # По умолчанию 7 дней
    
    def check_position_limits(self, capital: float, positions: Dict[str, Dict[str, Any]]) -> bool:
        """
        Проверяет, можно ли открыть новую позицию с учетом лимитов
        
        Args:
            capital: Доступный капитал
            positions: Текущие открытые позиции
            
        Returns:
            bool: True, если лимиты позволяют открыть новую позицию
        """
        # Проверка по количеству позиций
        if len(positions) >= self.max_positions:
            logger.info(f"Достигнут лимит по количеству позиций ({self.max_positions})")
            return False
        
        # Проверка по размеру капитала
        used_capital = sum(position.get('value', 0) for position in positions.values())
        available_capital = capital - used_capital
        
        # Если свободного капитала менее 10% от общего, считаем, что нет возможности открыть новую позицию
        if available_capital < capital * 0.1:
            logger.info(f"Недостаточно свободного капитала для новой позиции: {available_capital:.2f}")
            return False
        
        return True
    
    def calculate_position_size(self, capital: float, price: float, 
                               positions: Dict[str, Dict[str, Any]]) -> Tuple[float, int]:
        """
        Рассчитывает размер позиции на основе доступного капитала и текущей цены
        
        Args:
            capital: Доступный капитал
            price: Цена инструмента
            positions: Текущие открытые позиции
            
        Returns:
            tuple: (сумма в деньгах, количество лотов)
        """
        # Расчет уже используемого капитала
        used_capital = sum(position.get('value', 0) for position in positions.values())
        
        # Расчет доступного капитала
        available_capital = capital - used_capital
        
        # Лимит на позицию
        max_position_value = capital * self.max_position_size
        
        # Итоговый размер позиции (не больше доступного капитала и не больше лимита)
        position_value = min(available_capital, max_position_value)
        
        # Расчет количества лотов (учитываем комиссию 0.3%)
        commission_factor = 1.003  # 0.3% комиссии
        quantity = int(position_value / (price * commission_factor))
        
        return position_value, quantity
    
    def check_stop_loss_take_profit(self, position: Dict[str, Any], current_price: float) -> Optional[str]:
        """
        Проверяет, сработал ли стоп-лосс или тейк-профит для позиции
        
        Args:
            position: Информация о позиции
            current_price: Текущая цена
            
        Returns:
            str: "stop_loss" или "take_profit", если сработал, иначе None
        """
        if 'direction' not in position or position['direction'] == 'buy':
            # Для длинной позиции
            stop_loss = position.get('stop_loss', 0)
            take_profit = position.get('take_profit', float('inf'))
            
            if stop_loss > 0 and current_price <= stop_loss:
                return "stop_loss"
            
            if take_profit < float('inf') and current_price >= take_profit:
                return "take_profit"
        
        return None
    
    def check_trailing_stop(self, position: Dict[str, Any], current_price: float) -> Tuple[bool, float]:
        """
        Проверяет и обновляет трейлинг-стоп для позиции
        
        Args:
            position: Информация о позиции
            current_price: Текущая цена
            
        Returns:
            tuple: (сработал_стоп, новый_уровень_стопа)
        """
        if 'direction' not in position or position['direction'] == 'buy':
            # Для длинной позиции
            entry_price = position.get('entry_price', 0)
            stop_loss = position.get('stop_loss', 0)
            max_price = position.get('max_price', entry_price)
            
            # Обновляем максимальную цену, если текущая выше
            if current_price > max_price:
                max_price = current_price
                # Рассчитываем новый уровень трейлинг-стопа
                new_stop = max_price * (1 - self.trailing_stop_percent)
                
                # Обновляем стоп только если он выше текущего
                if new_stop > stop_loss:
                    return False, new_stop
            
            # Если цена упала ниже уровня трейлинг-стопа
            if stop_loss > 0 and max_price > entry_price and current_price <= stop_loss:
                return True, stop_loss
        
        return False, position.get('stop_loss', 0)
    
    def check_holding_time(self, position: Dict[str, Any]) -> bool:
        """
        Проверяет, превышено ли максимальное время удержания позиции
        
        Args:
            position: Информация о позиции
            
        Returns:
            bool: True, если пора закрывать позицию по времени
        """
        entry_time = position.get('entry_time')
        if entry_time is None:
            return False
        
        # Если время задано строкой, преобразуем в datetime
        if isinstance(entry_time, str):
            try:
                entry_time = datetime.fromisoformat(entry_time)
            except ValueError:
                logger.error(f"Некорректный формат времени входа: {entry_time}")
                return False
        
        # Если время задано pandas.Timestamp, преобразуем в datetime
        if hasattr(entry_time, 'to_pydatetime'):
            entry_time = entry_time.to_pydatetime()
        
        current_time = datetime.now()
        holding_days = (current_time - entry_time).days
        
        if holding_days >= self.max_holding_days:
            logger.info(f"Достигнут максимальный срок удержания позиции: {holding_days} дней")
            return True
        
        return False
    
    def update_position_levels(self, position: Dict[str, Any], 
                              current_price: float) -> Dict[str, Any]:
        """
        Обновляет уровни стоп-лосса и тейк-профита для позиции
        
        Args:
            position: Информация о позиции
            current_price: Текущая цена
            
        Returns:
            dict: Обновленная информация о позиции
        """
        # Создаем копию позиции для обновления
        updated_position = position.copy()
        
        # Для длинной позиции
        if position.get('direction', 'buy') == 'buy':
            entry_price = position.get('entry_price', current_price)
            max_price = position.get('max_price', entry_price)
            
            # Обновляем максимальную цену
            if current_price > max_price:
                updated_position['max_price'] = current_price
                
                # Рассчитываем новый уровень трейлинг-стопа
                new_stop = current_price * (1 - self.trailing_stop_percent)
                
                # Обновляем стоп только если он выше текущего
                current_stop = position.get('stop_loss', 0)
                if new_stop > current_stop:
                    updated_position['stop_loss'] = new_stop
                    updated_position['stop_type'] = 'trailing'
                    logger.info(f"Обновлен трейлинг-стоп: {new_stop:.2f} "
                              f"(цена: {current_price:.2f}, макс.цена: {current_price:.2f})")
        
        return updated_position
    
    def validate_stop_levels(self, position: Dict[str, Any]) -> Dict[str, Any]:
        """
        Проверяет и исправляет уровни стоп-лосса и тейк-профита
        
        Args:
            position: Информация о позиции
            
        Returns:
            dict: Проверенная и исправленная информация о позиции
        """
        validated = position.copy()
        entry_price = position.get('entry_price', 0)
        
        # Проверяем направление
        direction = position.get('direction', 'buy')
        
        if direction == 'buy':
            # Для длинной позиции стоп-лосс должен быть ниже цены входа
            stop_loss = position.get('stop_loss', entry_price * (1 - self.stop_loss_percent))
            if stop_loss >= entry_price:
                validated['stop_loss'] = entry_price * (1 - self.stop_loss_percent)
                logger.warning(f"Исправлен некорректный стоп-лосс: {stop_loss:.2f} -> {validated['stop_loss']:.2f}")
            
            # Тейк-профит должен быть выше цены входа
            take_profit = position.get('take_profit', entry_price * (1 + self.take_profit_percent))
            if take_profit <= entry_price:
                validated['take_profit'] = entry_price * (1 + self.take_profit_percent)
                logger.warning(f"Исправлен некорректный тейк-профит: {take_profit:.2f} -> {validated['take_profit']:.2f}")
        
        # Проверяем, что в позиции указано время входа
        if 'entry_time' not in validated:
            validated['entry_time'] = datetime.now()
        
        return validated
    
    def calculate_trade_risk(self, price: float, 
                           stop_loss: float, 
                           position_size: float) -> Dict[str, float]:
        """
        Рассчитывает риск для сделки
        
        Args:
            price: Цена входа
            stop_loss: Уровень стоп-лосса
            position_size: Размер позиции в деньгах
            
        Returns:
            dict: Информация о риске сделки
        """
        # Риск в процентах и деньгах
        risk_percent = abs(price - stop_loss) / price * 100
        risk_money = position_size * risk_percent / 100
        
        return {
            'risk_percent': risk_percent,
            'risk_money': risk_money,
            'price': price,
            'stop_loss': stop_loss,
            'position_size': position_size
        }
    
    def get_risk_report(self, positions: Dict[str, Dict[str, Any]], capital: float) -> Dict[str, Any]:
        """
        Генерирует отчет о рисках по открытым позициям
        
        Args:
            positions: Информация об открытых позициях
            capital: Общий капитал
            
        Returns:
            dict: Отчет о рисках
        """
        if not positions:
            return {
                'total_positions': 0,
                'total_exposure': 0,
                'total_risk': 0,
                'exposure_percent': 0,
                'risk_percent': 0,
                'positions_risk': []
            }
        
        # Расчет общей экспозиции (используемый капитал)
        total_exposure = sum(position.get('value', 0) for position in positions.values())
        
        # Расчет рисков по позициям
        positions_risk = []
        total_risk = 0
        
        for symbol, position in positions.items():
            entry_price = position.get('entry_price', 0)
            stop_loss = position.get('stop_loss', 0)
            value = position.get('value', 0)
            
            if entry_price == 0 or stop_loss == 0:
                continue
            
            # Риск для конкретной позиции
            risk_percent = abs(entry_price - stop_loss) / entry_price * 100
            risk_money = value * risk_percent / 100
            total_risk += risk_money
            
            positions_risk.append({
                'symbol': symbol,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'value': value,
                'risk_percent': risk_percent,
                'risk_money': risk_money
            })
        
        # Расчет процентов от общего капитала
        exposure_percent = total_exposure / capital * 100 if capital > 0 else 0
        risk_percent = total_risk / capital * 100 if capital > 0 else 0
        
        return {
            'total_positions': len(positions),
            'total_exposure': total_exposure,
            'total_risk': total_risk,
            'exposure_percent': exposure_percent,
            'risk_percent': risk_percent,
            'positions_risk': positions_risk
        }