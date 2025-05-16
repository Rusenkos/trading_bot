"""
Модуль для определения уровней поддержки и сопротивления.

Реализует различные методы для выявления ключевых ценовых уровней,
на которых возможны развороты цены.
"""
import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional, Any, Union

logger = logging.getLogger(__name__)

class SupportResistanceLevels:
    """
    Класс для определения уровней поддержки и сопротивления.
    
    Реализует различные методы:
    - Поиск локальных минимумов и максимумов
    - Определение уровней по объему (Volume Profile)
    - Уровни Фибоначчи
    - Pivot Points
    """
    
    @staticmethod
    def find_local_extrema(data: pd.DataFrame, window: int = 5) -> pd.DataFrame:
        """
        Поиск локальных минимумов и максимумов
        
        Args:
            data: DataFrame с ценовыми данными
            window: Размер окна для поиска экстремумов
            
        Returns:
            DataFrame: Исходные данные с добавленными столбцами экстремумов
        """
        if data is None or len(data) < window * 2:
            logger.warning("Недостаточно данных для поиска локальных экстремумов")
            return data
        
        # Создаем копию DataFrame
        df = data.copy()
        
        # Инициализируем столбцы для экстремумов
        df['local_min'] = None
        df['local_max'] = None
        
        # Находим локальные минимумы
        for i in range(window, len(df) - window):
            # Получаем окно вокруг текущей точки
            window_data = df.iloc[i-window:i+window+1]
            
            # Если текущая точка - минимальная в окне
            if df.iloc[i]['low'] == window_data['low'].min():
                df.loc[df.index[i], 'local_min'] = df.iloc[i]['low']
            
            # Если текущая точка - максимальная в окне
            if df.iloc[i]['high'] == window_data['high'].max():
                df.loc[df.index[i], 'local_max'] = df.iloc[i]['high']
        
        return df
    
    @staticmethod
    def identify_support_resistance(data: pd.DataFrame, price_tolerance: float = 0.02, 
                                  min_touches: int = 2) -> Tuple[List[float], List[float]]:
        """
        Определение уровней поддержки и сопротивления на основе локальных экстремумов
        
        Args:
            data: DataFrame с ценовыми данными и экстремумами
            price_tolerance: Толерантность к цене для группировки уровней (в процентах)
            min_touches: Минимальное количество касаний для подтверждения уровня
            
        Returns:
            tuple: (уровни поддержки, уровни сопротивления)
        """
        # Проверяем наличие столбцов экстремумов
        if 'local_min' not in data.columns or 'local_max' not in data.columns:
            # Если экстремумы не найдены, находим их
            data = SupportResistanceLevels.find_local_extrema(data)
        
        # Собираем все локальные минимумы и максимумы
        local_mins = [x for x in data['local_min'].dropna().tolist()]
        local_maxs = [x for x in data['local_max'].dropna().tolist()]
        
        # Функция для группировки близких уровней
        def group_levels(levels: List[float], tolerance: float) -> List[float]:
            if not levels:
                return []
            
            # Сортируем уровни
            sorted_levels = sorted(levels)
            
            # Группируем близкие уровни
            grouped_levels = []
            current_group = [sorted_levels[0]]
            
            for i in range(1, len(sorted_levels)):
                # Если уровень близок к текущей группе, добавляем его в группу
                if sorted_levels[i] <= current_group[-1] * (1 + tolerance):
                    current_group.append(sorted_levels[i])
                else:
                    # Иначе вычисляем средний уровень текущей группы
                    grouped_levels.append(sum(current_group) / len(current_group))
                    # И начинаем новую группу
                    current_group = [sorted_levels[i]]
            
            # Добавляем последнюю группу
            if current_group:
                grouped_levels.append(sum(current_group) / len(current_group))
            
            return grouped_levels
        
        # Группируем экстремумы
        grouped_mins = group_levels(local_mins, price_tolerance)
        grouped_maxs = group_levels(local_maxs, price_tolerance)
        
        # Функция для подсчета касаний уровня
        def count_touches(level: float, data: pd.DataFrame, tolerance: float) -> int:
            # Считаем касание, если цена подходит к уровню в пределах tolerance
            lower_bound = level * (1 - tolerance)
            upper_bound = level * (1 + tolerance)
            
            # Проверяем, сколько раз цена касалась уровня
            touches = 0
            in_touch = False
            
            for i in range(len(data)):
                # Проверяем, находится ли текущая свеча в зоне касания
                if data.iloc[i]['low'] <= upper_bound and data.iloc[i]['high'] >= lower_bound:
                    if not in_touch:  # Новое касание
                        touches += 1
                        in_touch = True
                else:
                    in_touch = False
            
            return touches
        
        # Фильтруем уровни по количеству касаний
        support_levels = [level for level in grouped_mins if count_touches(level, data, price_tolerance) >= min_touches]
        resistance_levels = [level for level in grouped_maxs if count_touches(level, data, price_tolerance) >= min_touches]
        
        return support_levels, resistance_levels
    
    @staticmethod
    def fibonacci_levels(data: pd.DataFrame, is_uptrend: bool) -> Dict[str, float]:
        """
        Расчет уровней коррекции Фибоначчи
        
        Args:
            data: DataFrame с ценовыми данными
            is_uptrend: True для восходящего тренда, False для нисходящего
            
        Returns:
            dict: Уровни Фибоначчи
        """
        if data is None or len(data) < 2:
            logger.warning("Недостаточно данных для расчета уровней Фибоначчи")
            return {}
        
        # Находим максимум и минимум
        high = data['high'].max()
        low = data['low'].min()
        
        # Расчет уровней Фибоначчи
        if is_uptrend:
            # Для восходящего тренда: от минимума к максимуму
            diff = high - low
            
            levels = {
                '0.0': low,
                '0.236': low + 0.236 * diff,
                '0.382': low + 0.382 * diff,
                '0.5': low + 0.5 * diff,
                '0.618': low + 0.618 * diff,
                '0.786': low + 0.786 * diff,
                '1.0': high
            }
        else:
            # Для нисходящего тренда: от максимума к минимуму
            diff = high - low
            
            levels = {
                '0.0': high,
                '0.236': high - 0.236 * diff,
                '0.382': high - 0.382 * diff,
                '0.5': high - 0.5 * diff,
                '0.618': high - 0.618 * diff,
                '0.786': high - 0.786 * diff,
                '1.0': low
            }
        
        return levels
    
    @staticmethod
    def pivot_points(data: pd.DataFrame) -> Dict[str, float]:
        """
        Расчет точек разворота (Pivot Points)
        
        Args:
            data: DataFrame с ценовыми данными (должен содержать последний период)
            
        Returns:
            dict: Точки разворота
        """
        if data is None or len(data) < 1:
            logger.warning("Недостаточно данных для расчета точек разворота")
            return {}
        
        # Берем данные последнего периода (обычно день или неделя)
        last_period = data.iloc[-1]
        
        high = last_period['high']
        low = last_period['low']
        close = last_period['close']
        
        # Расчет основной точки разворота
        pivot = (high + low + close) / 3
        
        # Расчет уровней поддержки
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        s3 = low - 2 * (high - pivot)
        
        # Расчет уровней сопротивления
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)
        r3 = high + 2 * (pivot - low)
        
        # Формируем словарь с уровнями
        levels = {
            'pivot': pivot,
            'r1': r1,
            'r2': r2,
            'r3': r3,
            's1': s1,
            's2': s2,
            's3': s3
        }
        
        return levels
    
    @staticmethod
    def volume_profile(data: pd.DataFrame, bins: int = 10) -> Dict[str, Any]:
        """
        Построение профиля объема (Volume Profile)
        
        Args:
            data: DataFrame с ценовыми данными и объемами
            bins: Количество ценовых диапазонов
            
        Returns:
            dict: Профиль объема
        """
        if data is None or len(data) < 5 or 'volume' not in data.columns:
            logger.warning("Недостаточно данных для построения профиля объема")
            return {}
        
        # Находим максимум и минимум цены
        price_max = data['high'].max()
        price_min = data['low'].min()
        
        # Создаем ценовые диапазоны
        price_range = np.linspace(price_min, price_max, bins + 1)
        
        # Инициализируем массив для хранения объемов по ценовым диапазонам
        volume_by_price = [0] * bins
        
        # Распределяем объем по ценовым диапазонам
        for i in range(len(data)):
            row = data.iloc[i]
            
            # Находим, каким ценовым диапазонам принадлежит свеча
            # (свеча может затрагивать несколько диапазонов)
            candle_min = min(row['open'], row['close'])
            candle_max = max(row['open'], row['close'])
            
            # Находим индексы диапазонов, которые затрагивает свеча
            min_idx = np.searchsorted(price_range, candle_min) - 1
            max_idx = np.searchsorted(price_range, candle_max) - 1
            
            # Если свеча находится в одном диапазоне
            if min_idx == max_idx:
                if 0 <= min_idx < bins:
                    volume_by_price[min_idx] += row['volume']
            else:
                # Если свеча затрагивает несколько диапазонов,
                # пропорционально распределяем объем
                for idx in range(max(0, min_idx), min(bins, max_idx + 1)):
                    # Простое равномерное распределение
                    volume_by_price[idx] += row['volume'] / (max_idx - min_idx + 1)
        
        # Находим точку контроля (POC) - ценовой диапазон с наибольшим объемом
        poc_idx = np.argmax(volume_by_price)
        poc_price = (price_range[poc_idx] + price_range[poc_idx + 1]) / 2
        
        # Формируем результат
        result = {
            'price_range': price_range,
            'volume_by_price': volume_by_price,
            'poc': poc_price,
            'value_area_high': price_range[-1],  # Верхняя граница области стоимости
            'value_area_low': price_range[0]     # Нижняя граница области стоимости
        }
        
        # Рассчитываем границы области значимого объема (Value Area)
        # (обычно это 70% от общего объема)
        total_volume = sum(volume_by_price)
        target_volume = total_volume * 0.7
        
        current_volume = volume_by_price[poc_idx]
        va_high_idx = poc_idx
        va_low_idx = poc_idx
        
        # Расширяем область значимого объема, пока не достигнем целевого объема
        while current_volume < target_volume and (va_high_idx < bins - 1 or va_low_idx > 0):
            # Проверяем, какой диапазон добавить
            vol_above = volume_by_price[va_high_idx + 1] if va_high_idx < bins - 1 else 0
            vol_below = volume_by_price[va_low_idx - 1] if va_low_idx > 0 else 0
            
            if vol_above >= vol_below and va_high_idx < bins - 1:
                # Добавляем верхний диапазон
                va_high_idx += 1
                current_volume += vol_above
            elif va_low_idx > 0:
                # Добавляем нижний диапазон
                va_low_idx -= 1
                current_volume += vol_below
        
        # Обновляем границы области значимого объема
        result['value_area_high'] = price_range[va_high_idx + 1]
        result['value_area_low'] = price_range[va_low_idx]
        
        return result
    
    @staticmethod
    def add_support_resistance_to_data(data: pd.DataFrame, tolerance: float = 0.02) -> pd.DataFrame:
        """
        Добавление информации о близости к уровням поддержки/сопротивления
        
        Args:
            data: DataFrame с ценовыми данными
            tolerance: Толерантность к цене для определения близости к уровню
            
        Returns:
            DataFrame: Исходные данные с добавленными столбцами уровней
        """
        if data is None or len(data) < 10:
            logger.warning("Недостаточно данных для анализа уровней поддержки/сопротивления")
            return data
        
        # Создаем копию DataFrame
        df = data.copy()
        
        # Находим локальные экстремумы
        df = SupportResistanceLevels.find_local_extrema(df)
        
        # Определяем уровни поддержки и сопротивления
        support_levels, resistance_levels = SupportResistanceLevels.identify_support_resistance(df, tolerance)
        
        # Добавляем столбцы для близости к уровням
        df['near_support'] = None
        df['near_resistance'] = None
        
        # Рассчитываем точки разворота
        pivot_levels = SupportResistanceLevels.pivot_points(df)
        
        # Добавляем столбец для близости к точкам разворота
        df['near_pivot'] = None
        
        # Проверяем близость к уровням для каждой свечи
        for i in range(len(df)):
            current_price = df.iloc[i]['close']
            
            # Проверяем близость к уровням поддержки
            for level in support_levels:
                if abs(current_price - level) / level < tolerance:
                    df.loc[df.index[i], 'near_support'] = level
                    break
            
            # Проверяем близость к уровням сопротивления
            for level in resistance_levels:
                if abs(current_price - level) / level < tolerance:
                    df.loc[df.index[i], 'near_resistance'] = level
                    break
            
            # Проверяем близость к точкам разворота
            for key, level in pivot_levels.items():
                if abs(current_price - level) / level < tolerance:
                    df.loc[df.index[i], 'near_pivot'] = f"{key}:{level:.2f}"
                    break
        
        # Добавляем информацию об уровнях Фибоначчи
        # Сначала определяем направление тренда
        is_uptrend = df.iloc[-1]['close'] > df.iloc[0]['close']
        
        # Рассчитываем уровни Фибоначчи
        fib_levels = SupportResistanceLevels.fibonacci_levels(df, is_uptrend)
        
        # Добавляем столбец для близости к уровням Фибоначчи
        df['near_fib'] = None
        
        # Проверяем близость к уровням Фибоначчи
        for i in range(len(df)):
            current_price = df.iloc[i]['close']
            
            for key, level in fib_levels.items():
                if abs(current_price - level) / level < tolerance:
                    df.loc[df.index[i], 'near_fib'] = f"{key}:{level:.2f}"
                    break
        
        return df
    
    @staticmethod
    def daily_levels(data: pd.DataFrame) -> Dict[str, float]:
        """
        Расчет дневных уровней (high, low, open, close предыдущего дня)
        
        Args:
            data: DataFrame с дневными ценовыми данными
            
        Returns:
            dict: Дневные уровни
        """
        if data is None or len(data) < 2:
            logger.warning("Недостаточно данных для расчета дневных уровней")
            return {}
        
        # Берем данные предыдущего дня
        prev_day = data.iloc[-2]
        
        # Формируем словарь с уровнями
        levels = {
            'prev_high': prev_day['high'],
            'prev_low': prev_day['low'],
            'prev_open': prev_day['open'],
            'prev_close': prev_day['close']
        }
        
        return levels