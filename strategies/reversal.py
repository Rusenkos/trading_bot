### strategies/reversal.py ###
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
import logging
from .base import StrategyInterface

logger = logging.getLogger(__name__)

class ReversalStrategy(StrategyInterface):
    """
    Контртрендовая стратегия, основанная на перепроданности/перекупленности рынка.
    
    Стратегия использует:
    - RSI для определения перепроданности/перекупленности
    - Полосы Боллинджера
    - Свечные паттерны для подтверждения разворота
    - Уровни поддержки/сопротивления
    
    Условия входа:
    1. RSI ниже уровня перепроданности и начинает расти
    2. Цена ниже нижней полосы Боллинджера
    3. Появление бычьего свечного паттерна (молот, бычье поглощение и т.д.)
    4. Опционально: цена у уровня поддержки
    
    Условия выхода:
    1. RSI выше уровня перекупленности
    2. Цена выше верхней полосы Боллинджера
    3. Появление медвежьего свечного паттерна (падающая звезда, медвежье поглощение и т.д.)
    """
    
    def __init__(self, config=None):
        """
        Инициализация контртрендовой стратегии
        
        Args:
            config: Объект конфигурации
        """
        super().__init__(config)
        self.name = "ReversalStrategy"
        
        # Параметры стратегии
        self.rsi_period = getattr(config, 'RSI_PERIOD', 14)
        self.rsi_oversold = getattr(config, 'RSI_OVERSOLD', 30)
        self.rsi_overbought = getattr(config, 'RSI_OVERBOUGHT', 70)
        self.bollinger_period = getattr(config, 'BOLLINGER_PERIOD', 20)
        self.bollinger_std = getattr(config, 'BOLLINGER_STD', 2)
    
    def check_buy_signals(self, data: pd.DataFrame) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка сигналов на покупку для контртрендовой стратегии
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            
        Returns:
            tuple: (есть_сигнал, детали_сигнала)
        """
        if data is None or len(data) < max(self.rsi_period, self.bollinger_period) + 2:
            logger.warning("Недостаточно данных для проверки сигналов контртрендовой стратегии")
            return False, None
        
        # Получаем последние строки данных
        curr = data.iloc[-1]
        prev = data.iloc[-2]
        
        # Получаем текущие значения
        current_rsi = curr['RSI']
        current_price = curr['close']
        lower_band = curr['Lower_Band']
        
        # Проверяем наличие бычьих паттернов свечей
        bullish_pattern = curr.get('Bullish_Pattern', False)
        
        # 1. Проверяем условие RSI: был ниже уровня перепроданности и начал расти
        rsi_condition = (
            (prev['RSI'] < self.rsi_oversold and current_rsi > prev['RSI']) or
            (current_rsi < self.rsi_oversold)
        )
        
        # 2. Проверяем условие Боллинджера: цена около или ниже нижней полосы
        bb_condition = current_price <= lower_band * 1.01  # Допускаем 1% погрешность
        
        # 3. Проверяем на наличие дивергенции
        divergence = curr.get('RSI_Divergence', 0) == 1  # Бычья дивергенция = 1
        
        # 4. Проверяем, находится ли цена около уровня поддержки
        near_support = False
        if 'near_support' in curr:
            near_support = curr['near_support'] is not None
        
        # Формируем сигнал
        # Основное условие: RSI показывает перепроданность И (цена у нижней полосы Боллинджера ИЛИ бычий паттерн)
        signal = rsi_condition and (bb_condition or bullish_pattern or divergence or near_support)
        
        if signal:
            # Собираем детали сигнала
            signal_details = {
                'type': 'buy',
                'strategy': self.name,
                'price': current_price,
                'time': data.index[-1],
                'strength': self.evaluate_signal_strength({
                    'rsi': current_rsi,
                    'bb_distance': (current_price / lower_band - 1) * 100,
                    'bullish_pattern': bullish_pattern,
                    'divergence': divergence,
                    'near_support': near_support
                }),
                'reasons': []
            }
            
            # Добавляем причины сигнала
            if current_rsi < self.rsi_oversold:
                signal_details['reasons'].append(f"RSI ({current_rsi:.1f}) ниже уровня перепроданности ({self.rsi_oversold})")
            elif prev['RSI'] < self.rsi_oversold and current_rsi > prev['RSI']:
                signal_details['reasons'].append(f"RSI вырос с {prev['RSI']:.1f} до {current_rsi:.1f} после перепроданности")
            
            if bb_condition:
                signal_details['reasons'].append(f"Цена ({current_price:.2f}) около нижней полосы Боллинджера ({lower_band:.2f})")
            
            if bullish_pattern:
                # Определяем, какой именно паттерн
                patterns = []
                for pattern_column in ['Hammer', 'Bullish_Engulfing', 'Morning_Star', 'Piercing_Line', 'Three_White_Soldiers']:
                    if pattern_column in curr and curr[pattern_column]:
                        pattern_name = pattern_column.replace('_', ' ')
                        patterns.append(pattern_name)
                
                if patterns:
                    signal_details['reasons'].append(f"Бычий паттерн: {', '.join(patterns)}")
                else:
                    signal_details['reasons'].append("Бычий свечной паттерн")
            
            if divergence:
                signal_details['reasons'].append("Бычья дивергенция RSI и цены")
            
            if near_support:
                signal_details['reasons'].append(f"Цена у уровня поддержки ({curr.get('near_support', 0):.2f})")
            
            # Добавляем текущие значения индикаторов
            signal_details['indicators'] = {
                'RSI': current_rsi,
                'Lower_Band': lower_band,
                'BB_Middle': curr.get('BB_Middle', 0),
                'Upper_Band': curr.get('Upper_Band', 0),
                'Bullish_Pattern': bullish_pattern,
                'RSI_Divergence': divergence
            }
            
            logger.info(f"Контртрендовая стратегия: сигнал на покупку {', '.join(signal_details['reasons'])}")
            return True, signal_details
        
        return False, None
    
    def check_sell_signals(self, data: pd.DataFrame, position: Optional[Dict] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка сигналов на продажу для контртрендовой стратегии
        
        Args:
            data: DataFrame с ценовыми данными и индикаторами
            position: Информация о текущей позиции
            
        Returns:
            tuple: (есть_сигнал, детали_сигнала)
        """
        if data is None or len(data) < max(self.rsi_period, self.bollinger_period) + 2:
            logger.warning("Недостаточно данных для проверки сигналов контртрендовой стратегии")
            return False, None
        
        # Если нет открытой позиции, нечего продавать
        if position is None:
            return False, None
        
        # Получаем последние строки данных
        curr = data.iloc[-1]
        prev = data.iloc[-2]
        
        # Получаем текущие значения
        current_rsi = curr['RSI']
        current_price = curr['close']
        upper_band = curr['Upper_Band']
        
        # Проверяем наличие медвежьих паттернов свечей
        bearish_pattern = curr.get('Bearish_Pattern', False)
        
        # 1. Проверяем условие RSI: был выше уровня перекупленности или начал падать из зоны перекупленности
        rsi_condition = (
            (current_rsi > self.rsi_overbought) or
            (prev['RSI'] > self.rsi_overbought and current_rsi < prev['RSI'])
        )
        
        # 2. Проверяем условие Боллинджера: цена около или выше верхней полосы
        bb_condition = current_price >= upper_band * 0.99  # Допускаем 1% погрешность
        
        # 3. Проверяем на наличие дивергенции
        divergence = curr.get('RSI_Divergence', 0) == -1  # Медвежья дивергенция = -1
        
        # 4. Проверяем, находится ли цена около уровня сопротивления
        near_resistance = False
        if 'near_resistance' in curr:
            near_resistance = curr['near_resistance'] is not None
        
        # 5. Проверяем, достигла ли цена ключевого уровня цены (например, фибо)
        near_fib = False
        if 'near_fib' in curr:
            near_fib = curr['near_fib'] is not None
        
        # 6. Проверяем, достигла ли позиция целевого уровня прибыли
        entry_price = position.get('entry_price', 0)
        profit_target = 0.5  # 50% от исходной цели тейк-профита
        take_profit = position.get('take_profit', 0)
        
        target_reached = False
        if entry_price > 0 and take_profit > 0:
            # Если цена ушла более чем на half_target% от цены входа
            target_price = entry_price + (take_profit - entry_price) * profit_target
            target_reached = current_price >= target_price
        
        # Формируем сигнал
        # Основное условие: (RSI показывает перекупленность ИЛИ цена у верхней полосы Боллинджера ИЛИ медвежий паттерн)
        # И (достигли целевого уровня ИЛИ достигли уровня сопротивления)
        signal = (rsi_condition or bb_condition or bearish_pattern or divergence or near_resistance or near_fib) and (target_reached or near_resistance)
        
        if signal:
            # Собираем детали сигнала
            signal_details = {
                'type': 'sell',
                'strategy': self.name,
                'price': current_price,
                'time': data.index[-1],
                'strength': self.evaluate_signal_strength({
                    'rsi': current_rsi,
                    'bb_distance': (current_price / upper_band - 1) * 100,
                    'bearish_pattern': bearish_pattern,
                    'divergence': divergence,
                    'near_resistance': near_resistance,
                    'target_reached': target_reached
                }),
                'reasons': []
            }
            
            # Добавляем причины сигнала
            if current_rsi > self.rsi_overbought:
                signal_details['reasons'].append(f"RSI ({current_rsi:.1f}) выше уровня перекупленности ({self.rsi_overbought})")
            elif prev['RSI'] > self.rsi_overbought and current_rsi < prev['RSI']:
                signal_details['reasons'].append(f"RSI упал с {prev['RSI']:.1f} до {current_rsi:.1f} после перекупленности")
            
            if bb_condition:
                signal_details['reasons'].append(f"Цена ({current_price:.2f}) около верхней полосы Боллинджера ({upper_band:.2f})")
            
            if bearish_pattern:
                # Определяем, какой именно паттерн
                patterns = []
                for pattern_column in ['Shooting_Star', 'Bearish_Engulfing', 'Evening_Star', 'Dark_Cloud_Cover', 'Three_Black_Crows']:
                    if pattern_column in curr and curr[pattern_column]:
                        pattern_name = pattern_column.replace('_', ' ')
                        patterns.append(pattern_name)
                
                if patterns:
                    signal_details['reasons'].append(f"Медвежий паттерн: {', '.join(patterns)}")
                else:
                    signal_details['reasons'].append("Медвежий свечной паттерн")
            
            if divergence:
                signal_details['reasons'].append("Медвежья дивергенция RSI и цены")
            
            if near_resistance:
                signal_details['reasons'].append(f"Цена у уровня сопротивления ({curr.get('near_resistance', 0):.2f})")
            
            if near_fib:
                signal_details['reasons'].append(f"Цена у уровня Фибоначчи {curr.get('near_fib', '')}")
            
            if target_reached:
                signal_details['reasons'].append(f"Достигнута цель по прибыли {(current_price / entry_price - 1) * 100:.2f}%")
            
            # Рассчитываем прибыль/убыток для позиции
            if entry_price > 0:
                profit_percent = (current_price / entry_price - 1) * 100
                signal_details['profit_percent'] = profit_percent
            
            # Добавляем текущие значения индикаторов
            signal_details['indicators'] = {
                'RSI': current_rsi,
                'Lower_Band': curr.get('Lower_Band', 0),
                'BB_Middle': curr.get('BB_Middle', 0),
                'Upper_Band': upper_band,
                'Bearish_Pattern': bearish_pattern,
                'RSI_Divergence': divergence
            }
            
            logger.info(f"Контртрендовая стратегия: сигнал на продажу {', '.join(signal_details['reasons'])}")
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
        
        # Оцениваем по значению RSI
        rsi = signal_info.get('rsi', 50)
        if rsi <= 20 or rsi >= 80:
            strength += 0.15  # Экстремальный RSI - сильный сигнал
        elif rsi <= 30 or rsi >= 70:
            strength += 0.1
        
        # Оцениваем по расстоянию до полосы Боллинджера
        bb_distance = abs(signal_info.get('bb_distance', 0))
        if bb_distance > 2.0:
            strength += 0.1  # Значительное отклонение от полосы
        
        # Оцениваем по наличию паттерна
        if signal_info.get('bullish_pattern', False) or signal_info.get('bearish_pattern', False):
            strength += 0.15
        
        # Оцениваем по наличию дивергенции
        if signal_info.get('divergence', False):
            strength += 0.2  # Дивергенция - очень сильный сигнал
        
        # Оцениваем по близости к уровню поддержки/сопротивления
        if signal_info.get('near_support', False) or signal_info.get('near_resistance', False):
            strength += 0.1
        
        # Оцениваем по достижению целевого уровня
        if signal_info.get('target_reached', False):
            strength += 0.05
        
        # Ограничиваем в диапазоне [0, 1]
        return max(0.0, min(1.0, strength))