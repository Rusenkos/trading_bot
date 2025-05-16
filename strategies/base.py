### strategies/base.py ###
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class StrategyInterface(ABC):
    """
    Абстрактный базовый класс для торговых стратегий.
    Определяет интерфейс для всех конкретных стратегий.
    """
    
    def __init__(self, config=None):
        """
        Инициализация стратегии
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        self.name = "BaseStrategy"
    
    @abstractmethod
    def check_buy_signals(self, data: pd.DataFrame) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка сигналов на покупку
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            
        Returns:
            tuple: (есть_сигнал, детали_сигнала)
        """
        pass
    
    @abstractmethod
    def check_sell_signals(self, data: pd.DataFrame, position: Optional[Dict] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка сигналов на продажу
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            position: Информация о текущей позиции (цена входа, время и т.д.)
            
        Returns:
            tuple: (есть_сигнал, детали_сигнала)
        """
        pass
    
    def calculate_target_price(self, entry_price: float, is_buy: bool) -> Dict[str, float]:
        """
        Расчет целевых уровней для позиции (стоп-лосс, тейк-профит)
        
        Args:
            entry_price: Цена входа в позицию
            is_buy: True для длинной позиции, False для короткой
            
        Returns:
            dict: Целевые уровни
        """
        # Получаем проценты стоп-лосса и тейк-профита из конфигурации
        stop_loss_percent = getattr(self.config, 'STOP_LOSS_PERCENT', 2.5) / 100
        take_profit_percent = getattr(self.config, 'TAKE_PROFIT_PERCENT', 5.0) / 100
        
        if is_buy:
            # Для длинной позиции
            stop_loss = entry_price * (1 - stop_loss_percent)
            take_profit = entry_price * (1 + take_profit_percent)
        else:
            # Для короткой позиции (на будущее, пока не используется)
            stop_loss = entry_price * (1 + stop_loss_percent)
            take_profit = entry_price * (1 - take_profit_percent)
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'entry_price': entry_price
        }
    
    def evaluate_signal_strength(self, signal_details: Dict[str, Any]) -> float:
        """
        Оценка силы сигнала для приоритизации сделок
        
        Args:
            signal_details: Детали сигнала
            
        Returns:
            float: Оценка силы сигнала от 0.0 до 1.0
        """
        # Метод должен быть переопределен в конкретных стратегиях
        return 0.5  # Значение по умолчанию
    
    def get_position_size(self, capital: float, entry_price: float) -> float:
        """
        Расчет размера позиции на основе капитала
        
        Args:
            capital: Доступный капитал
            entry_price: Цена входа
            
        Returns:
            float: Доля капитала для позиции (от 0.0 до 1.0)
        """
        # По умолчанию используем значение из конфигурации
        position_size = getattr(self.config, 'MAX_POSITION_SIZE', 0.9)
        return min(position_size, 1.0)  # Убедимся, что не превышает 100%
    
    def should_update_stops(self, data: pd.DataFrame, position: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """
        Проверяет, нужно ли обновить стоп-лоссы и тейк-профиты
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            position: Информация о текущей позиции
            
        Returns:
            dict: Обновленные уровни или None, если обновление не требуется
        """
        # Проверяем необходимость трейлинг-стопа
        trailing_stop_percent = getattr(self.config, 'TRAILING_STOP_PERCENT', 1.8) / 100
        
        # Если позиция длинная (покупка)
        if position.get('direction', 'buy') == 'buy':
            entry_price = position.get('entry_price', 0)
            stop_loss = position.get('stop_loss', 0)
            current_price = data['close'].iloc[-1]
            
            # Если цена выросла, проверяем необходимость обновления стопа
            if current_price > entry_price:
                # Новый стоп по трейлингу
                potential_new_stop = current_price * (1 - trailing_stop_percent)
                
                # Обновляем стоп, только если он выше текущего
                if potential_new_stop > stop_loss:
                    return {
                        'stop_loss': potential_new_stop,
                        'entry_price': entry_price,  # Сохраняем исходную цену входа
                        'max_price': current_price  # Записываем максимальную достигнутую цену
                    }
        
        return None
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """
        Получение информации о стратегии
        
        Returns:
            dict: Информация о стратегии
        """
        return {
            'name': self.name,
            'description': self.__doc__ or "Нет описания",
            'config': {
                param: getattr(self.config, param) 
                for param in dir(self.config) 
                if not param.startswith('__') and not callable(getattr(self.config, param))
            } if self.config else {}
        }
    
    def __str__(self) -> str:
        """
        Строковое представление стратегии
        
        Returns:
            str: Имя стратегии
        """
        return self.name