### strategies/combined.py ###
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
import logging
from .base import StrategyInterface
from .trend import TrendStrategy
from .reversal import ReversalStrategy

logger = logging.getLogger(__name__)

class CombinedStrategy(StrategyInterface):
    """
    Комбинированная стратегия, объединяющая трендовую и контртрендовую стратегии.
    
    Стратегия использует:
    - Сигналы трендовой стратегии (EMA, MACD, объем)
    - Сигналы контртрендовой стратегии (RSI, Bollinger Bands, свечные паттерны)
    - Приоритизирует сигналы на основе дополнительных критериев
    
    Комбинированная стратегия позволяет:
    1. Выбирать сигналы с наибольшей силой из обеих стратегий
    2. Использовать более консервативные условия: требовать подтверждения обеими стратегиями
    3. Адаптироваться к различным рыночным условиям
    """
    
    def __init__(self, config=None):
        """
        Инициализация комбинированной стратегии
        
        Args:
            config: Объект конфигурации
        """
        super().__init__(config)
        self.name = "CombinedStrategy"
        
        # Создаем экземпляры базовых стратегий
        self.trend_strategy = TrendStrategy(config)
        self.reversal_strategy = ReversalStrategy(config)
        
        # Режим комбинирования: 'any' - любая стратегия, 'all' - все стратегии
        self.combine_mode = getattr(config, 'STRATEGY_MODE', 'any')
    
    def check_buy_signals(self, data: pd.DataFrame) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка сигналов на покупку для комбинированной стратегии
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            
        Returns:
            tuple: (есть_сигнал, детали_сигнала)
        """
        # Проверяем сигналы от базовых стратегий
        trend_signal, trend_details = self.trend_strategy.check_buy_signals(data)
        reversal_signal, reversal_details = self.reversal_strategy.check_buy_signals(data)
        
        # Логика комбинирования сигналов в зависимости от режима
        if self.combine_mode == 'all':
            # Требуем сигналы от всех стратегий
            if trend_signal and reversal_signal:
                # Объединяем детали сигналов
                combined_details = self._combine_signal_details(trend_details, reversal_details)
                combined_details['strategy'] = self.name
                combined_details['type'] = 'buy'
                
                # Используем максимальную силу сигнала
                combined_details['strength'] = max(trend_details.get('strength', 0.5), 
                                                 reversal_details.get('strength', 0.5))
                
                # Логируем сигнал
                logger.info(f"Комбинированная стратегия (режим 'all'): сигнал на покупку, "
                           f"причины: {', '.join(combined_details['reasons'])}")
                
                return True, combined_details
            return False, None
        
        else:  # Режим 'any' - достаточно сигнала от любой стратегии
            if trend_signal and reversal_signal:
                # Если есть сигналы от обеих стратегий, выбираем сильнейший
                trend_strength = trend_details.get('strength', 0.5)
                reversal_strength = reversal_details.get('strength', 0.5)
                
                if trend_strength >= reversal_strength:
                    selected_details = trend_details.copy()
                    selected_details['strategy'] = f"{self.name} (trend)"
                    selected_details['combined'] = True
                    selected_details['reasons'].append("Подтверждено контртрендовой стратегией")
                    # Увеличиваем силу сигнала из-за двойного подтверждения
                    selected_details['strength'] = min(1.0, trend_strength + 0.2)
                else:
                    selected_details = reversal_details.copy()
                    selected_details['strategy'] = f"{self.name} (reversal)"
                    selected_details['combined'] = True
                    selected_details['reasons'].append("Подтверждено трендовой стратегией")
                    # Увеличиваем силу сигнала из-за двойного подтверждения
                    selected_details['strength'] = min(1.0, reversal_strength + 0.2)
                
                logger.info(f"Комбинированная стратегия (режим 'any'): сигнал на покупку, "
                           f"выбрана стратегия {selected_details['strategy']}, "
                           f"причины: {', '.join(selected_details['reasons'])}")
                
                return True, selected_details
            
            elif trend_signal:
                # Только сигнал трендовой стратегии
                trend_details['strategy'] = f"{self.name} (trend)"
                logger.info(f"Комбинированная стратегия (режим 'any'): сигнал на покупку от трендовой стратегии, "
                           f"причины: {', '.join(trend_details['reasons'])}")
                return True, trend_details
            
            elif reversal_signal:
                # Только сигнал контртрендовой стратегии
                reversal_details['strategy'] = f"{self.name} (reversal)"
                logger.info(f"Комбинированная стратегия (режим 'any'): сигнал на покупку от контртрендовой стратегии, "
                           f"причины: {', '.join(reversal_details['reasons'])}")
                return True, reversal_details
            
            return False, None
    
    def check_sell_signals(self, data: pd.DataFrame, position: Optional[Dict] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка сигналов на продажу для комбинированной стратегии
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            position: Информация о текущей позиции
            
        Returns:
            tuple: (есть_сигнал, детали_сигнала)
        """
        # Если нет открытой позиции, нечего продавать
        if position is None:
            return False, None
        
        # Проверяем сигналы от базовых стратегий
        trend_signal, trend_details = self.trend_strategy.check_sell_signals(data, position)
        reversal_signal, reversal_details = self.reversal_strategy.check_sell_signals(data, position)
        
        # Для продажи мы более осторожны и используем режим 'any' независимо от настроек,
        # т.к. фиксация прибыли и ограничение убытков важнее
        
        if trend_signal and reversal_signal:
            # Если есть сигналы от обеих стратегий, выбираем сильнейший
            trend_strength = trend_details.get('strength', 0.5)
            reversal_strength = reversal_details.get('strength', 0.5)
            
            if trend_strength >= reversal_strength:
                selected_details = trend_details.copy()
                selected_details['strategy'] = f"{self.name} (trend)"
                selected_details['combined'] = True
                selected_details['reasons'].append("Подтверждено контртрендовой стратегией")
                # Увеличиваем силу сигнала из-за двойного подтверждения
                selected_details['strength'] = min(1.0, trend_strength + 0.2)
            else:
                selected_details = reversal_details.copy()
                selected_details['strategy'] = f"{self.name} (reversal)"
                selected_details['combined'] = True
                selected_details['reasons'].append("Подтверждено трендовой стратегией")
                # Увеличиваем силу сигнала из-за двойного подтверждения
                selected_details['strength'] = min(1.0, reversal_strength + 0.2)
            
            logger.info(f"Комбинированная стратегия: сигнал на продажу, "
                       f"выбрана стратегия {selected_details['strategy']}, "
                       f"причины: {', '.join(selected_details['reasons'])}")
            
            return True, selected_details
        
        elif trend_signal:
            # Только сигнал трендовой стратегии
            trend_details['strategy'] = f"{self.name} (trend)"
            logger.info(f"Комбинированная стратегия: сигнал на продажу от трендовой стратегии, "
                       f"причины: {', '.join(trend_details['reasons'])}")
            return True, trend_details
        
        elif reversal_signal:
            # Только сигнал контртрендовой стратегии
            reversal_details['strategy'] = f"{self.name} (reversal)"
            logger.info(f"Комбинированная стратегия: сигнал на продажу от контртрендовой стратегии, "
                       f"причины: {', '.join(reversal_details['reasons'])}")
            return True, reversal_details
        
        return False, None
    
    def _combine_signal_details(self, details1: Dict[str, Any], details2: Dict[str, Any]) -> Dict[str, Any]:
        """
        Объединение деталей сигналов от разных стратегий
        
        Args:
            details1: Детали первого сигнала
            details2: Детали второго сигнала
            
        Returns:
            dict: Объединенные детали сигналов
        """
        # Создаем копию первого словаря
        combined = details1.copy()
        
        # Объединяем списки причин
        combined['reasons'] = details1.get('reasons', []) + details2.get('reasons', [])
        
        # Объединяем индикаторы
        combined_indicators = details1.get('indicators', {}).copy()
        combined_indicators.update(details2.get('indicators', {}))
        combined['indicators'] = combined_indicators
        
        # Помечаем как комбинированный сигнал
        combined['combined'] = True
        
        return combined
    
    def evaluate_signal_strength(self, signal_info: Dict[str, Any]) -> float:
        """
        Оценка силы сигнала комбинированной стратегии
        
        Args:
            signal_info: Информация о сигнале
            
        Returns:
            float: Оценка силы сигнала от 0.0 до 1.0
        """
        # Если уже оценено базовыми стратегиями, используем это значение
        if 'strength' in signal_info:
            return signal_info['strength']
        
        # Иначе делегируем соответствующей стратегии
        if 'strategy' in signal_info:
            if 'trend' in signal_info['strategy'].lower():
                return self.trend_strategy.evaluate_signal_strength(signal_info)
            elif 'reversal' in signal_info['strategy'].lower():
                return self.reversal_strategy.evaluate_signal_strength(signal_info)
        
        # Если не определена стратегия, используем базовую оценку
        return super().evaluate_signal_strength(signal_info)