### strategies/trend.py ###
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
import logging
from .base import StrategyInterface

logger = logging.getLogger(__name__)

class TrendStrategy(StrategyInterface):
    """
    Трендовая стратегия на основе EMA, MACD и объема.
    
    Стратегия следования тренду, использующая:
    - Пересечение скользящих средних (EMA)
    - Подтверждение через MACD
    - Подтверждение объемом выше среднего
    
    Условия входа:
    1. Быстрая EMA пересекает медленную EMA снизу вверх
    2. MACD линия выше сигнальной или пересекает ее снизу вверх
    3. Объем торгов выше среднего
    
    Условия выхода:
    1. Быстрая EMA пересекает медленную EMA сверху вниз
    2. MACD линия пересекает сигнальную сверху вниз
    3. Или срабатывает стоп-лосс/тейк-профит
    """
    
    def __init__(self, config=None):
        """
        Инициализация трендовой стратегии
        
        Args:
            config: Объект конфигурации
        """
        super().__init__(config)
        self.name = "TrendStrategy"
        
        # Параметры стратегии из конфигурации или по умолчанию
        self.ema_short = getattr(config, 'EMA_SHORT', 5)
        self.ema_long = getattr(config, 'EMA_LONG', 15)
        self.volume_ma_period = getattr(config, 'VOLUME_MA_PERIOD', 20)
        self.min_volume_factor = getattr(config, 'MIN_VOLUME_FACTOR', 1.5)
    
    def check_buy_signals(self, data: pd.DataFrame) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка сигналов на покупку для трендовой стратегии
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            
        Returns:
            tuple: (есть_сигнал, детали_сигнала)
        """
        if data is None or len(data) < self.ema_long + 2:
            logger.warning("Недостаточно данных для проверки сигналов трендовой стратегии")
            return False, None
        
        # Получаем последние две строки для проверки пересечения
        curr = data.iloc[-1]
        prev = data.iloc[-2]
        
        # 1. Проверяем пересечение EMA (быстрая пересекает медленную снизу вверх)
        ema_cross_up = (
            prev[f'EMA_{self.ema_short}'] <= prev[f'EMA_{self.ema_long}'] and 
            curr[f'EMA_{self.ema_short}'] > curr[f'EMA_{self.ema_long}']
        )
        
        # 2. Проверяем MACD (линия MACD выше сигнальной или пересекает ее снизу вверх)
        macd_positive = curr['MACD'] > curr['MACD_Signal']
        macd_cross_up = (
            prev['MACD'] <= prev['MACD_Signal'] and 
            curr['MACD'] > curr['MACD_Signal']
        )
        
        # 3. Проверяем объем (выше среднего)
        volume_above_average = curr['Volume_Ratio'] > self.min_volume_factor
        
        # Формируем сигнал
        # Основной сигнал: пересечение EMA
        # Дополнительные условия: MACD и объем
        signal = ema_cross_up and (macd_positive or macd_cross_up) and volume_above_average
        
        if signal:
            # Собираем детали сигнала
            signal_details = {
                'type': 'buy',
                'strategy': self.name,
                'price': curr['close'],
                'time': data.index[-1],
                'strength': self.evaluate_signal_strength({
                    'ema_diff_percent': (curr[f'EMA_{self.ema_short}'] / curr[f'EMA_{self.ema_long}'] - 1) * 100,
                    'macd_histogram': curr['MACD_Histogram'],
                    'volume_ratio': curr['Volume_Ratio']
                }),
                'reasons': []
            }
            
            # Добавляем причины сигнала
            if ema_cross_up:
                signal_details['reasons'].append(
                    f"EMA{self.ema_short} пересекла EMA{self.ema_long} снизу вверх"
                )
            if macd_cross_up:
                signal_details['reasons'].append("MACD пересек сигнальную линию снизу вверх")
            elif macd_positive:
                signal_details['reasons'].append("MACD выше сигнальной линии")
            if volume_above_average:
                signal_details['reasons'].append(
                    f"Объем в {curr['Volume_Ratio']:.2f} раз выше среднего"
                )
            
            # Добавляем текущие значения индикаторов
            signal_details['indicators'] = {
                f'EMA_{self.ema_short}': curr[f'EMA_{self.ema_short}'],
                f'EMA_{self.ema_long}': curr[f'EMA_{self.ema_long}'],
                'MACD': curr['MACD'],
                'MACD_Signal': curr['MACD_Signal'],
                'MACD_Histogram': curr['MACD_Histogram'],
                'Volume_Ratio': curr['Volume_Ratio']
            }
            
            logger.info(f"Трендовая стратегия: сигнал на покупку {', '.join(signal_details['reasons'])}")
            return True, signal_details
        
        return False, None
    
    def check_sell_signals(self, data: pd.DataFrame, position: Optional[Dict] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка сигналов на продажу для трендовой стратегии
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            position: Информация о текущей позиции
            
        Returns:
            tuple: (есть_сигнал, детали_сигнала)
        """
        if data is None or len(data) < self.ema_long + 2:
            logger.warning("Недостаточно данных для проверки сигналов трендовой стратегии")
            return False, None
        
        # Если нет открытой позиции, нечего продавать
        if position is None:
            return False, None
        
        # Получаем последние две строки для проверки пересечения
        curr = data.iloc[-1]
        prev = data.iloc[-2]
        
        # 1. Проверяем пересечение EMA (быстрая пересекает медленную сверху вниз)
        ema_cross_down = (
            prev[f'EMA_{self.ema_short}'] >= prev[f'EMA_{self.ema_long}'] and 
            curr[f'EMA_{self.ema_short}'] < curr[f'EMA_{self.ema_long}']
        )
        
        # 2. Проверяем MACD (линия MACD пересекает сигнальную сверху вниз)
        macd_cross_down = (
            prev['MACD'] >= prev['MACD_Signal'] and 
            curr['MACD'] < curr['MACD_Signal']
        )
        
        # 3. Проверяем падение объема как предупреждение об ослаблении тренда
        volume_decreasing = curr['Volume_Ratio'] < prev['Volume_Ratio'] * 0.8
        
        # Формируем сигнал
        signal = ema_cross_down or macd_cross_down
        
        if signal:
            # Собираем детали сигнала
            signal_details = {
                'type': 'sell',
                'strategy': self.name,
                'price': curr['close'],
                'time': data.index[-1],
                'strength': self.evaluate_signal_strength({
                    'ema_diff_percent': (curr[f'EMA_{self.ema_long}'] / curr[f'EMA_{self.ema_short}'] - 1) * 100,
                    'macd_histogram': -curr['MACD_Histogram'],
                    'volume_ratio': curr['Volume_Ratio']
                }),
                'reasons': []
            }
            
            # Добавляем причины сигнала
            if ema_cross_down:
                signal_details['reasons'].append(
                    f"EMA{self.ema_short} пересекла EMA{self.ema_long} сверху вниз"
                )
            if macd_cross_down:
                signal_details['reasons'].append("MACD пересек сигнальную линию сверху вниз")
            if volume_decreasing:
                signal_details['reasons'].append("Объем торгов снизился, ослабление тренда")
            
            # Добавляем текущие значения индикаторов
            signal_details['indicators'] = {
                f'EMA_{self.ema_short}': curr[f'EMA_{self.ema_short}'],
                f'EMA_{self.ema_long}': curr[f'EMA_{self.ema_long}'],
                'MACD': curr['MACD'],
                'MACD_Signal': curr['MACD_Signal'],
                'MACD_Histogram': curr['MACD_Histogram'],
                'Volume_Ratio': curr['Volume_Ratio']
            }
            
            # Рассчитываем прибыль/убыток для позиции
            entry_price = position.get('entry_price', 0)
            if entry_price > 0:
                profit_percent = (curr['close'] / entry_price - 1) * 100
                signal_details['profit_percent'] = profit_percent
                signal_details['reasons'].append(f"Прибыль: {profit_percent:.2f}%")
            
            logger.info(f"Трендовая стратегия: сигнал на продажу {', '.join(signal_details['reasons'])}")
            return True, signal_details
        
        return False, None
    
    def evaluate_signal_strength(self, signal_info: Dict[str, Any]) -> float:
        """
        Оценка силы сигнала для приоритизации сделок
        
        Args:
            signal_info: Информация о сигнале
            
        Returns:
            float: Оценка силы сигнала от 0.0 до 1.0
        """
        strength = 0.5  # Базовая сила сигнала
        
        # Оцениваем по разнице EMA
        ema_diff = signal_info.get('ema_diff_percent', 0)
        if abs(ema_diff) > 0.5:
            strength += 0.1  # Большая разница - сильный сигнал
        
        # Оцениваем по гистограмме MACD
        macd_hist = signal_info.get('macd_histogram', 0)
        if abs(macd_hist) > 0.2:
            strength += 0.1
        
        # Оцениваем по объему
        volume_ratio = signal_info.get('volume_ratio', 1.0)
        if volume_ratio > 2.0:
            strength += 0.2  # Очень высокий объем - сильный сигнал
        elif volume_ratio > 1.5:
            strength += 0.1
        
        # Ограничиваем в диапазоне [0, 1]
        return max(0.0, min(1.0, strength))