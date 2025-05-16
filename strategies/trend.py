from typing import Dict, Any, Optional, Tuple
import pandas as pd
import logging
from .base import StrategyInterface

logger = logging.getLogger(__name__)

class TrendStrategy(StrategyInterface):
    """
    Трендовая стратегия на основе EMA, MACD и объема.
    """

    def __init__(self, config=None):
        super().__init__(config)
        self.name = "TrendStrategy"
        self.ema_short = getattr(config, 'EMA_SHORT', 8)
        self.ema_long = getattr(config, 'EMA_LONG', 21)
        self.volume_ma_period = getattr(config, 'VOLUME_MA_PERIOD', 20)
        self.min_volume_factor = getattr(config, 'MIN_VOLUME_FACTOR', 1.2)

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
        
        # 1. Более гибкие условия для генерации сигналов пересечения EMA
        ema_cross_up = (
            # Классическое пересечение
            (prev[f'EMA_{self.ema_short}'] <= prev[f'EMA_{self.ema_long}'] and 
            curr[f'EMA_{self.ema_short}'] > curr[f'EMA_{self.ema_long}']) or
            # Близкое пересечение
            (prev[f'EMA_{self.ema_short}'] <= prev[f'EMA_{self.ema_long}'] * 1.02 and 
            curr[f'EMA_{self.ema_short}'] >= curr[f'EMA_{self.ema_long}'] * 0.98) or
            # Рост короткой EMA при близости к пересечению
            (curr[f'EMA_{self.ema_short}'] > prev[f'EMA_{self.ema_short}'] and 
            curr[f'EMA_{self.ema_short}'] / curr[f'EMA_{self.ema_long}'] > 0.95 and
            curr[f'EMA_{self.ema_short}'] > curr[f'EMA_{self.ema_short}'] * 1.005)
        )
        
        # 2. Более гибкие условия для MACD
        macd_condition = (
            # Стандартное условие - MACD выше сигнальной
            curr['MACD'] > curr['MACD_Signal'] or
            # Почти пересечение снизу вверх
            (prev['MACD'] <= prev['MACD_Signal'] and 
            curr['MACD'] >= curr['MACD_Signal'] * 0.95) or
            # Рост MACD и положительная гистограмма
            (curr['MACD'] > prev['MACD'] * 1.05 and curr['MACD_Histogram'] > 0) or
            # Пересечение нулевой линии
            (prev['MACD'] < 0 and curr['MACD'] > 0)
        )
        
        # 3. Менее строгие условия для объема
        volume_condition = curr['Volume_Ratio'] > self.min_volume_factor * 0.7
        
        # 4. Формируем сигнал с более гибкими условиями
        signal = (ema_cross_up and (macd_condition or volume_condition)) or \
                (macd_condition and volume_condition and curr[f'EMA_{self.ema_short}'] > prev[f'EMA_{self.ema_short}'])
        
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
            if prev[f'EMA_{self.ema_short}'] <= prev[f'EMA_{self.ema_long}'] and curr[f'EMA_{self.ema_short}'] > curr[f'EMA_{self.ema_long}']:
                signal_details['reasons'].append(
                    f"EMA{self.ema_short} пересекла EMA{self.ema_long} снизу вверх"
                )
            elif prev[f'EMA_{self.ema_short}'] <= prev[f'EMA_{self.ema_long}'] * 1.02 and curr[f'EMA_{self.ema_short}'] >= curr[f'EMA_{self.ema_long}'] * 0.98:
                signal_details['reasons'].append(
                    f"EMA{self.ema_short} очень близка к пересечению EMA{self.ema_long} снизу вверх"
                )
            elif curr[f'EMA_{self.ema_short}'] > prev[f'EMA_{self.ema_short}'] and curr[f'EMA_{self.ema_short}'] / curr[f'EMA_{self.ema_long}'] > 0.95:
                signal_details['reasons'].append(
                    f"EMA{self.ema_short} растет и приближается к EMA{self.ema_long}"
                )
            
            if curr['MACD'] > curr['MACD_Signal']:
                signal_details['reasons'].append("MACD выше сигнальной линии")
            elif prev['MACD'] <= prev['MACD_Signal'] and curr['MACD'] >= curr['MACD_Signal'] * 0.95:
                signal_details['reasons'].append("MACD приближается к пересечению сигнальной линии снизу вверх")
            elif curr['MACD'] > prev['MACD'] * 1.05:
                signal_details['reasons'].append("MACD быстро растет")
            elif prev['MACD'] < 0 and curr['MACD'] > 0:
                signal_details['reasons'].append("MACD пересек нулевую линию снизу вверх")
            
            if volume_condition:
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
        if data is None or len(data) < self.ema_long + 2:
            logger.warning("Недостаточно данных для проверки сигналов трендовой стратегии")
            return False, None

        if position is None:
            return False, None

        curr = data.iloc[-1]
        prev = data.iloc[-2]

        # EMA пересечение вниз
        ema_short_prev = prev.get(f'EMA_{self.ema_short}', None)
        ema_long_prev = prev.get(f'EMA_{self.ema_long}', None)
        ema_short_curr = curr.get(f'EMA_{self.ema_short}', None)
        ema_long_curr = curr.get(f'EMA_{self.ema_long}', None)
        ema_cross_down = (ema_short_prev is not None and ema_long_prev is not None and 
                          ema_short_curr is not None and ema_long_curr is not None and
                          ema_short_prev > ema_long_prev and ema_short_curr < ema_long_curr)

        # MACD пересечение вниз
        macd_prev = prev.get('MACD', None)
        macd_signal_prev = prev.get('MACD_Signal', None)
        macd_curr = curr.get('MACD', None)
        macd_signal_curr = curr.get('MACD_Signal', None)
        macd_cross_down = (macd_prev is not None and macd_signal_prev is not None and 
                           macd_curr is not None and macd_signal_curr is not None and
                           macd_prev > macd_signal_prev and macd_curr < macd_signal_curr)

        # Объем падает
        volume_decreasing = curr.get('Volume_Ratio', 1.0) < prev.get('Volume_Ratio', 1.0) * 0.8

        signal = ema_cross_down or macd_cross_down

        if signal:
            signal_details = {
                'type': 'sell',
                'strategy': self.name,
                'price': curr['close'],
                'time': data.index[-1],
                'strength': self.evaluate_signal_strength({
                    'ema_diff_percent': ((ema_long_curr / ema_short_curr - 1) * 100) if (ema_short_curr and ema_long_curr) else 0,
                    'macd_histogram': -curr.get('MACD_Histogram', 0),
                    'volume_ratio': curr.get('Volume_Ratio', 1.0)
                }),
                'reasons': [],
                'indicators': {
                    f'EMA_{self.ema_short}': ema_short_curr,
                    f'EMA_{self.ema_long}': ema_long_curr,
                    'MACD': macd_curr,
                    'MACD_Signal': macd_signal_curr,
                    'MACD_Histogram': curr.get('MACD_Histogram', 0),
                    'Volume_Ratio': curr.get('Volume_Ratio', 1.0)
                }
            }
            if ema_cross_down:
                signal_details['reasons'].append(
                    f"EMA{self.ema_short} пересекла EMA{self.ema_long} сверху вниз"
                )
            if macd_cross_down:
                signal_details['reasons'].append("MACD пересек сигнальную линию сверху вниз")
            if volume_decreasing:
                signal_details['reasons'].append("Объем торгов снизился, ослабление тренда")
            entry_price = position.get('entry_price', 0)
            if entry_price > 0:
                profit_percent = (curr['close'] / entry_price - 1) * 100
                signal_details['profit_percent'] = profit_percent
                signal_details['reasons'].append(f"Прибыль: {profit_percent:.2f}%")
            logger.info(f"Трендовая стратегия: сигнал на продажу {', '.join(signal_details['reasons'])}")
            return True, signal_details

        return False, None

    def evaluate_signal_strength(self, signal_info: Dict[str, Any]) -> float:
        strength = 0.5  # Базовая сила сигнала

        # Оцениваем по разнице EMA
        ema_diff = signal_info.get('ema_diff_percent', 0)
        if abs(ema_diff) > 0.5:
            strength += 0.1

        # Оцениваем по гистограмме MACD
        macd_hist = signal_info.get('macd_histogram', 0)
        if abs(macd_hist) > 0.2:
            strength += 0.1

        # Оцениваем по объему
        volume_ratio = signal_info.get('volume_ratio', 1.0)
        if volume_ratio > 2.0:
            strength += 0.2
        elif volume_ratio > 1.5:
            strength += 0.1

        return max(0.0, min(1.0, strength))