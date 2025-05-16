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
        if data is None or len(data) < self.ema_long + 2:
            return False, None

        curr = data.iloc[-1]
        prev = data.iloc[-2]

        # EMA пересечение вверх
        ema_short_prev = prev.get(f'EMA_{self.ema_short}', None)
        ema_long_prev = prev.get(f'EMA_{self.ema_long}', None)
        ema_short_curr = curr.get(f'EMA_{self.ema_short}', None)
        ema_long_curr = curr.get(f'EMA_{self.ema_long}', None)
        ema_cross_up = (ema_short_prev is not None and ema_long_prev is not None and 
                        ema_short_curr is not None and ema_long_curr is not None and 
                        ema_short_prev < ema_long_prev and ema_short_curr > ema_long_curr)

        # MACD пересечение вверх
        macd_prev = prev.get('MACD', None)
        macd_signal_prev = prev.get('MACD_Signal', None)
        macd_curr = curr.get('MACD', None)
        macd_signal_curr = curr.get('MACD_Signal', None)
        macd_cross_up = (macd_prev is not None and macd_signal_prev is not None and 
                         macd_curr is not None and macd_signal_curr is not None and
                         macd_prev < macd_signal_prev and macd_curr > macd_signal_curr)
        macd_positive = (macd_curr is not None and macd_signal_curr is not None and macd_curr > macd_signal_curr)

        # Объем выше среднего
        volume_ratio = curr.get('Volume_Ratio', 1.0)
        volume_above_average = volume_ratio > self.min_volume_factor

        # Основной сигнал
        signal = ema_cross_up and (macd_cross_up or macd_positive) and volume_above_average

        if signal:
            signal_details = {
                'type': 'buy',
                'strategy': self.name,
                'price': curr['close'],
                'time': data.index[-1],
                'strength': self.evaluate_signal_strength({
                    'ema_diff_percent': ((ema_short_curr / ema_long_curr - 1) * 100) if (ema_short_curr and ema_long_curr) else 0,
                    'macd_histogram': curr.get('MACD_Histogram', 0),
                    'volume_ratio': volume_ratio
                }),
                'reasons': [],
                'indicators': {
                    f'EMA_{self.ema_short}': ema_short_curr,
                    f'EMA_{self.ema_long}': ema_long_curr,
                    'MACD': macd_curr,
                    'MACD_Signal': macd_signal_curr,
                    'MACD_Histogram': curr.get('MACD_Histogram', 0),
                    'Volume_Ratio': volume_ratio
                }
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
                    f"Объем в {volume_ratio:.2f} раз выше среднего"
                )
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