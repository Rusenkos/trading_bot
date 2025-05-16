### data/patterns.py ###
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class CandlePatterns:
    """
    Класс для распознавания свечных паттернов.
    """
    
    @staticmethod
    def is_hammer(candle, shadow_body_ratio=2.0):
        """
        Проверка на паттерн "Молот"
        
        Args:
            candle: dict или Series с данными свечи (open, high, low, close)
            shadow_body_ratio: отношение нижней тени к телу свечи для признания паттерна
            
        Returns:
            bool: True если паттерн обнаружен
        """
        open_price = candle['open']
        close_price = candle['close']
        high_price = candle['high']
        low_price = candle['low']
        
        # Вычисляем размер тела свечи
        body_size = abs(close_price - open_price)
        
        # Если тело свечи очень маленькое, это не молот
        if body_size < (high_price - low_price) * 0.05:
            return False
        
        # Вычисляем размер верхней и нижней тени
        if close_price > open_price:  # Бычья свеча
            upper_shadow = high_price - close_price
            lower_shadow = open_price - low_price
        else:  # Медвежья свеча
            upper_shadow = high_price - open_price
            lower_shadow = close_price - low_price
        
        # Проверяем условия паттерна "Молот":
        # 1. Нижняя тень должна быть не менее X раз длиннее тела
        # 2. Верхняя тень должна быть маленькой или отсутствовать
        if (lower_shadow >= body_size * shadow_body_ratio and
            upper_shadow <= body_size * 0.1):
            return True
        
        return False
    
    @staticmethod
    def is_hanging_man(candle, shadow_body_ratio=2.0):
        """
        Проверка на паттерн "Повешенный" (Hanging Man)
        Похож на молот, но появляется на вершине восходящего тренда
        
        Args:
            candle: dict или Series с данными свечи (open, high, low, close)
            shadow_body_ratio: отношение нижней тени к телу свечи для признания паттерна
            
        Returns:
            bool: True если паттерн обнаружен
        """
        # Технически, hanging man имеет ту же структуру, что и молот
        return CandlePatterns.is_hammer(candle, shadow_body_ratio)
    
    @staticmethod
    def is_shooting_star(candle, shadow_body_ratio=2.0):
        """
        Проверка на паттерн "Падающая звезда" (Shooting Star)
        
        Args:
            candle: dict или Series с данными свечи (open, high, low, close)
            shadow_body_ratio: отношение верхней тени к телу свечи для признания паттерна
            
        Returns:
            bool: True если паттерн обнаружен
        """
        open_price = candle['open']
        close_price = candle['close']
        high_price = candle['high']
        low_price = candle['low']
        
        # Вычисляем размер тела свечи
        body_size = abs(close_price - open_price)
        
        # Если тело свечи очень маленькое, это не звезда
        if body_size < (high_price - low_price) * 0.05:
            return False
        
        # Вычисляем размер верхней и нижней тени
        if close_price > open_price:  # Бычья свеча
            upper_shadow = high_price - close_price
            lower_shadow = open_price - low_price
        else:  # Медвежья свеча
            upper_shadow = high_price - open_price
            lower_shadow = close_price - low_price
        
        # Проверяем условия паттерна "Падающая звезда":
        # 1. Верхняя тень должна быть не менее X раз длиннее тела
        # 2. Нижняя тень должна быть маленькой или отсутствовать
        if (upper_shadow >= body_size * shadow_body_ratio and
            lower_shadow <= body_size * 0.1):
            return True
        
        return False
    
    @staticmethod
    def is_doji(candle, body_range_ratio=0.1):
        """
        Проверка на паттерн "Доджи" (очень маленькое тело свечи)
        
        Args:
            candle: dict или Series с данными свечи (open, high, low, close)
            body_range_ratio: максимальное отношение тела к диапазону свечи для признания доджи
            
        Returns:
            bool: True если паттерн обнаружен
        """
        open_price = candle['open']
        close_price = candle['close']
        high_price = candle['high']
        low_price = candle['low']
        
        # Вычисляем размер тела и полный диапазон свечи
        body_size = abs(close_price - open_price)
        candle_range = high_price - low_price
        
        # Избегаем деления на ноль
        if candle_range == 0:
            return False
        
        # Доджи имеет очень маленькое тело по сравнению с общим диапазоном
        if (body_size / candle_range) <= body_range_ratio:
            return True
        
        return False
    
    @staticmethod
    def is_bullish_engulfing(candles):
        """
        Проверка на паттерн "Бычье поглощение" (Bullish Engulfing)
        
        Args:
            candles: DataFrame или list с данными двух последовательных свечей
            
        Returns:
            bool: True если паттерн обнаружен
        """
        if len(candles) < 2:
            return False
        
        prev_candle = candles.iloc[-2] if isinstance(candles, pd.DataFrame) else candles[-2]
        curr_candle = candles.iloc[-1] if isinstance(candles, pd.DataFrame) else candles[-1]
        
        prev_open = prev_candle['open']
        prev_close = prev_candle['close']
        curr_open = curr_candle['open']
        curr_close = curr_candle['close']
        
        # Предыдущая свеча должна быть медвежьей (закрытие ниже открытия)
        is_prev_bearish = prev_close < prev_open
        
        # Текущая свеча должна быть бычьей (закрытие выше открытия)
        is_curr_bullish = curr_close > curr_open
        
        # Текущая свеча должна полностью поглощать тело предыдущей
        is_engulfing = (curr_open < prev_close and curr_close > prev_open)
        
        return is_prev_bearish and is_curr_bullish and is_engulfing
    
    @staticmethod
    def is_bearish_engulfing(candles):
        """
        Проверка на паттерн "Медвежье поглощение" (Bearish Engulfing)
        
        Args:
            candles: DataFrame или list с данными двух последовательных свечей
            
        Returns:
            bool: True если паттерн обнаружен
        """
        if len(candles) < 2:
            return False
        
        prev_candle = candles.iloc[-2] if isinstance(candles, pd.DataFrame) else candles[-2]
        curr_candle = candles.iloc[-1] if isinstance(candles, pd.DataFrame) else candles[-1]
        
        prev_open = prev_candle['open']
        prev_close = prev_candle['close']
        curr_open = curr_candle['open']
        curr_close = curr_candle['close']
        
        # Предыдущая свеча должна быть бычьей (закрытие выше открытия)
        is_prev_bullish = prev_close > prev_open
        
        # Текущая свеча должна быть медвежьей (закрытие ниже открытия)
        is_curr_bearish = curr_close < curr_open
        
        # Текущая свеча должна полностью поглощать тело предыдущей
        is_engulfing = (curr_open > prev_close and curr_close < prev_open)
        
        return is_prev_bullish and is_curr_bearish and is_engulfing
    
    @staticmethod
    def is_morning_star(candles):
        """
        Проверка на паттерн "Утренняя звезда" (Morning Star)
        
        Args:
            candles: DataFrame или list с данными трех последовательных свечей
            
        Returns:
            bool: True если паттерн обнаружен
        """
        if len(candles) < 3:
            return False
        
        first_candle = candles.iloc[-3] if isinstance(candles, pd.DataFrame) else candles[-3]
        middle_candle = candles.iloc[-2] if isinstance(candles, pd.DataFrame) else candles[-2]
        last_candle = candles.iloc[-1] if isinstance(candles, pd.DataFrame) else candles[-1]
        
        # Первая свеча должна быть медвежьей с большим телом
        is_first_bearish = first_candle['close'] < first_candle['open']
        first_body_size = abs(first_candle['close'] - first_candle['open'])
        first_candle_range = first_candle['high'] - first_candle['low']
        is_first_large = first_body_size > first_candle_range * 0.6
        
        # Средняя свеча должна быть маленькой (доджи или с маленьким телом)
        middle_body_size = abs(middle_candle['close'] - middle_candle['open'])
        middle_candle_range = middle_candle['high'] - middle_candle['low']
        is_middle_small = middle_body_size < middle_candle_range * 0.3
        
        # Третья свеча должна быть бычьей с телом, перекрывающим большую часть первой свечи
        is_last_bullish = last_candle['close'] > last_candle['open']
        last_body_size = abs(last_candle['close'] - last_candle['open'])
        is_closing_gap = last_candle['close'] > (first_candle['open'] + first_candle['close']) / 2
        
        # Проверяем разрыв между первой и второй свечами
        is_gap_down = middle_candle['high'] < first_candle['close']
        
        return (is_first_bearish and is_first_large and is_middle_small and 
                is_last_bullish and is_closing_gap)
    
    @staticmethod
    def is_evening_star(candles):
        """
        Проверка на паттерн "Вечерняя звезда" (Evening Star)
        
        Args:
            candles: DataFrame или list с данными трех последовательных свечей
            
        Returns:
            bool: True если паттерн обнаружен
        """
        if len(candles) < 3:
            return False
        
        first_candle = candles.iloc[-3] if isinstance(candles, pd.DataFrame) else candles[-3]
        middle_candle = candles.iloc[-2] if isinstance(candles, pd.DataFrame) else candles[-2]
        last_candle = candles.iloc[-1] if isinstance(candles, pd.DataFrame) else candles[-1]
        
        # Первая свеча должна быть бычьей с большим телом
        is_first_bullish = first_candle['close'] > first_candle['open']
        first_body_size = abs(first_candle['close'] - first_candle['open'])
        first_candle_range = first_candle['high'] - first_candle['low']
        is_first_large = first_body_size > first_candle_range * 0.6
        
        # Средняя свеча должна быть маленькой (доджи или с маленьким телом)
        middle_body_size = abs(middle_candle['close'] - middle_candle['open'])
        middle_candle_range = middle_candle['high'] - middle_candle['low']
        is_middle_small = middle_body_size < middle_candle_range * 0.3
        
        # Третья свеча должна быть медвежьей с телом, перекрывающим большую часть первой свечи
        is_last_bearish = last_candle['close'] < last_candle['open']
        last_body_size = abs(last_candle['close'] - last_candle['open'])
        is_closing_gap = last_candle['close'] < (first_candle['open'] + first_candle['close']) / 2
        
        # Проверяем разрыв между первой и второй свечами
        is_gap_up = middle_candle['low'] > first_candle['close']
        
        return (is_first_bullish and is_first_large and is_middle_small and 
                is_last_bearish and is_closing_gap)
    
    @staticmethod
    def is_three_white_soldiers(candles, body_ratio_threshold=0.8):
        """
        Проверка на паттерн "Три белых солдата" (Three White Soldiers)
        
        Args:
            candles: DataFrame или list с данными трех последовательных свечей
            body_ratio_threshold: минимальное отношение тела к диапазону для признания сильной свечи
            
        Returns:
            bool: True если паттерн обнаружен
        """
        if len(candles) < 3:
            return False
        
        # Получаем три последние свечи
        if isinstance(candles, pd.DataFrame):
            candle1 = candles.iloc[-3]
            candle2 = candles.iloc[-2]
            candle3 = candles.iloc[-1]
        else:
            candle1 = candles[-3]
            candle2 = candles[-2]
            candle3 = candles[-1]
        
        # Проверяем, что все свечи бычьи (закрытие выше открытия)
        if not (candle1['close'] > candle1['open'] and 
                candle2['close'] > candle2['open'] and 
                candle3['close'] > candle3['open']):
            return False
        
        # Проверяем, что каждая следующая свеча открывается внутри тела предыдущей
        # и закрывается выше предыдущей
        if not (candle2['open'] >= candle1['open'] and candle2['close'] > candle1['close'] and
                candle3['open'] >= candle2['open'] and candle3['close'] > candle2['close']):
            return False
        
        # Проверяем, что все свечи имеют сильные тела (мало теней)
        for candle in [candle1, candle2, candle3]:
            body_size = abs(candle['close'] - candle['open'])
            candle_range = candle['high'] - candle['low']
            if body_size / candle_range < body_ratio_threshold:
                return False
        
        return True
    
    @staticmethod
    def is_three_black_crows(candles, body_ratio_threshold=0.8):
        """
        Проверка на паттерн "Три черные вороны" (Three Black Crows)
        
        Args:
            candles: DataFrame или list с данными трех последовательных свечей
            body_ratio_threshold: минимальное отношение тела к диапазону для признания сильной свечи
            
        Returns:
            bool: True если паттерн обнаружен
        """
        if len(candles) < 3:
            return False
        
        # Получаем три последние свечи
        if isinstance(candles, pd.DataFrame):
            candle1 = candles.iloc[-3]
            candle2 = candles.iloc[-2]
            candle3 = candles.iloc[-1]
        else:
            candle1 = candles[-3]
            candle2 = candles[-2]
            candle3 = candles[-1]
        
        # Проверяем, что все свечи медвежьи (закрытие ниже открытия)
        if not (candle1['close'] < candle1['open'] and 
                candle2['close'] < candle2['open'] and 
                candle3['close'] < candle3['open']):
            return False
        
        # Проверяем, что каждая следующая свеча открывается внутри тела предыдущей
        # и закрывается ниже предыдущей
        if not (candle2['open'] <= candle1['open'] and candle2['close'] < candle1['close'] and
                candle3['open'] <= candle2['open'] and candle3['close'] < candle2['close']):
            return False
        
        # Проверяем, что все свечи имеют сильные тела (мало теней)
        for candle in [candle1, candle2, candle3]:
            body_size = abs(candle['close'] - candle['open'])
            candle_range = candle['high'] - candle['low']
            if body_size / candle_range < body_ratio_threshold:
                return False
        
        return True
    
    @staticmethod
    def is_piercing_line(candles):
        """
        Проверка на паттерн "Просвет в облаках" (Piercing Line)
        
        Args:
            candles: DataFrame или list с данными двух последовательных свечей
            
        Returns:
            bool: True если паттерн обнаружен
        """
        if len(candles) < 2:
            return False
        
        prev_candle = candles.iloc[-2] if isinstance(candles, pd.DataFrame) else candles[-2]
        curr_candle = candles.iloc[-1] if isinstance(candles, pd.DataFrame) else candles[-1]
        
        # Предыдущая свеча должна быть медвежьей
        is_prev_bearish = prev_candle['close'] < prev_candle['open']
        
        # Текущая свеча должна быть бычьей
        is_curr_bullish = curr_candle['close'] > curr_candle['open']
        
        # Текущая свеча должна открыться ниже предыдущего закрытия
        is_gap_down = curr_candle['open'] < prev_candle['close']
        
        # Текущая свеча должна закрыться выше середины тела предыдущей
        prev_midpoint = (prev_candle['open'] + prev_candle['close']) / 2
        is_piercing = curr_candle['close'] > prev_midpoint and curr_candle['close'] < prev_candle['open']
        
        return is_prev_bearish and is_curr_bullish and is_gap_down and is_piercing
    
    @staticmethod
    def is_dark_cloud_cover(candles):
        """
        Проверка на паттерн "Завеса из темных облаков" (Dark Cloud Cover)
        
        Args:
            candles: DataFrame или list с данными двух последовательных свечей
            
        Returns:
            bool: True если паттерн обнаружен
        """
        if len(candles) < 2:
            return False
        
        prev_candle = candles.iloc[-2] if isinstance(candles, pd.DataFrame) else candles[-2]
        curr_candle = candles.iloc[-1] if isinstance(candles, pd.DataFrame) else candles[-1]
        
        # Предыдущая свеча должна быть бычьей
        is_prev_bullish = prev_candle['close'] > prev_candle['open']
        
        # Текущая свеча должна быть медвежьей
        is_curr_bearish = curr_candle['close'] < curr_candle['open']
        
        # Текущая свеча должна открыться выше предыдущего закрытия
        is_gap_up = curr_candle['open'] > prev_candle['close']
        
        # Текущая свеча должна закрыться ниже середины тела предыдущей
        prev_midpoint = (prev_candle['open'] + prev_candle['close']) / 2
        is_piercing = curr_candle['close'] < prev_midpoint and curr_candle['close'] > prev_candle['open']
        
        return is_prev_bullish and is_curr_bearish and is_gap_up and is_piercing
    
    @staticmethod
    def identify_patterns(df):
        """
        Идентификация всех свечных паттернов в DataFrame
        
        Args:
            df: DataFrame с данными OHLC
            
        Returns:
            DataFrame: Исходные данные с добавленными столбцами паттернов
        """
        if df is None or len(df) < 3:
            logger.warning("Недостаточно данных для анализа паттернов")
            return df
        
        # Создаем копию DataFrame
        result = df.copy()
        
        # Добавляем столбцы для паттернов
        result['Hammer'] = False
        result['Hanging_Man'] = False
        result['Shooting_Star'] = False
        result['Doji'] = False
        result['Bullish_Engulfing'] = False
        result['Bearish_Engulfing'] = False
        result['Morning_Star'] = False
        result['Evening_Star'] = False
        result['Three_White_Soldiers'] = False
        result['Three_Black_Crows'] = False
        result['Piercing_Line'] = False
        result['Dark_Cloud_Cover'] = False
        
        # Проверяем одиночные свечные паттерны
        for i in range(len(result)):
            # Пропускаем первые свечи, так как для некоторых паттернов нужны предыдущие
            if i < 2:
                continue
            
            # Получаем данные текущей свечи
            candle = result.iloc[i]
            
            # Проверяем паттерны одиночных свечей
            result.loc[result.index[i], 'Hammer'] = CandlePatterns.is_hammer(candle)
            result.loc[result.index[i], 'Shooting_Star'] = CandlePatterns.is_shooting_star(candle)
            result.loc[result.index[i], 'Doji'] = CandlePatterns.is_doji(candle)
            
            # Определяем контекст для hanging man (появляется на вершине восходящего тренда)
            if CandlePatterns.is_hammer(candle):
                # Простая проверка: если предыдущие 5 свечей в основном растущие, считаем hanging man
                if i >= 5:
                    prev_5_candles = result.iloc[i-5:i]
                    if (prev_5_candles['close'] > prev_5_candles['open']).sum() >= 3:
                        result.loc[result.index[i], 'Hanging_Man'] = True
            
            # Проверяем паттерны из 2 свечей
            if i >= 1:
                two_candles = result.iloc[i-1:i+1]
                result.loc[result.index[i], 'Bullish_Engulfing'] = CandlePatterns.is_bullish_engulfing(two_candles)
                result.loc[result.index[i], 'Bearish_Engulfing'] = CandlePatterns.is_bearish_engulfing(two_candles)
                result.loc[result.index[i], 'Piercing_Line'] = CandlePatterns.is_piercing_line(two_candles)
                result.loc[result.index[i], 'Dark_Cloud_Cover'] = CandlePatterns.is_dark_cloud_cover(two_candles)
            
            # Проверяем паттерны из 3 свечей
            if i >= 2:
                three_candles = result.iloc[i-2:i+1]
                result.loc[result.index[i], 'Morning_Star'] = CandlePatterns.is_morning_star(three_candles)
                result.loc[result.index[i], 'Evening_Star'] = CandlePatterns.is_evening_star(three_candles)
                result.loc[result.index[i], 'Three_White_Soldiers'] = CandlePatterns.is_three_white_soldiers(three_candles)
                result.loc[result.index[i], 'Three_Black_Crows'] = CandlePatterns.is_three_black_crows(three_candles)
        
        # Добавляем обобщенные сигналы паттернов
        result['Bullish_Pattern'] = (
            result['Hammer'] | 
            result['Bullish_Engulfing'] | 
            result['Morning_Star'] | 
            result['Three_White_Soldiers'] | 
            result['Piercing_Line']
        )
        
        result['Bearish_Pattern'] = (
            result['Hanging_Man'] | 
            result['Shooting_Star'] | 
            result['Bearish_Engulfing'] | 
            result['Evening_Star'] | 
            result['Three_Black_Crows'] | 
            result['Dark_Cloud_Cover']
        )
        
        # Добавляем признак неопределенности
        result['Uncertain_Pattern'] = result['Doji']
        
        return result
    
    @staticmethod
    def get_last_pattern(df):
        """
        Получает информацию о последнем обнаруженном паттерне
        
        Args:
            df: DataFrame с данными паттернов
            
        Returns:
            dict: Информация о последнем паттерне {тип: bool} или None если нет паттернов
        """
        if df is None or df.empty:
            return None
        
        # Получаем последнюю строку
        last_row = df.iloc[-1]
        
        # Проверяем, есть ли в ней паттерны
        pattern_info = {}
        pattern_found = False
        
        # Проверяем паттерны по одному
        if last_row['Hammer']:
            pattern_info['hammer'] = True
            pattern_found = True
            
        if last_row['Hanging_Man']:
            pattern_info['hanging_man'] = True
            pattern_found = True
            
        if last_row['Shooting_Star']:
            pattern_info['shooting_star'] = True
            pattern_found = True
            
        if last_row['Doji']:
            pattern_info['doji'] = True
            pattern_found = True
            
        if last_row['Bullish_Engulfing']:
            pattern_info['bullish_engulfing'] = True
            pattern_found = True
            
        if last_row['Bearish_Engulfing']:
            pattern_info['bearish_engulfing'] = True
            pattern_found = True
            
        if last_row['Morning_Star']:
            pattern_info['morning_star'] = True
            pattern_found = True
            
        if last_row['Evening_Star']:
            pattern_info['evening_star'] = True
            pattern_found = True
            
        if last_row['Three_White_Soldiers']:
            pattern_info['three_white_soldiers'] = True
            pattern_found = True
            
        if last_row['Three_Black_Crows']:
            pattern_info['three_black_crows'] = True
            pattern_found = True
            
        if last_row['Piercing_Line']:
            pattern_info['piercing_line'] = True
            pattern_found = True
            
        if last_row['Dark_Cloud_Cover']:
            pattern_info['dark_cloud_cover'] = True
            pattern_found = True
        
        # Добавляем общий тип паттерна
        if last_row['Bullish_Pattern']:
            pattern_info['type'] = 'bullish'
        elif last_row['Bearish_Pattern']:
            pattern_info['type'] = 'bearish'
        elif last_row['Uncertain_Pattern']:
            pattern_info['type'] = 'uncertain'
        else:
            pattern_info['type'] = 'none'
        
        if not pattern_found:
            return None
        
        return pattern_info
    
    @staticmethod
    def describe_pattern(pattern_info):
        """
        Генерирует текстовое описание паттерна
        
        Args:
            pattern_info: dict с информацией о паттерне
            
        Returns:
            str: Описание паттерна
        """
        if pattern_info is None or 'type' not in pattern_info or pattern_info['type'] == 'none':
            return "Нет обнаруженных паттернов"
        
        descriptions = []
        
        # Добавляем описания обнаруженных паттернов
        if pattern_info.get('hammer'):
            descriptions.append("Молот (бычий разворотный паттерн, показывающий возможное окончание нисходящего тренда)")
            
        if pattern_info.get('hanging_man'):
            descriptions.append("Повешенный (медвежий разворотный паттерн, появляющийся на вершине восходящего тренда)")
            
        if pattern_info.get('shooting_star'):
            descriptions.append("Падающая звезда (медвежий разворотный паттерн, сигнализирующий о возможном окончании восходящего тренда)")
            
        if pattern_info.get('doji'):
            descriptions.append("Доджи (паттерн неопределенности, показывающий равновесие покупателей и продавцов)")
            
        if pattern_info.get('bullish_engulfing'):
            descriptions.append("Бычье поглощение (сильный бычий разворотный паттерн, показывающий смену настроения рынка)")
            
        if pattern_info.get('bearish_engulfing'):
            descriptions.append("Медвежье поглощение (сильный медвежий разворотный паттерн, показывающий смену настроения рынка)")
            
        if pattern_info.get('morning_star'):
            descriptions.append("Утренняя звезда (сильный бычий разворотный паттерн из трех свечей, сигнализирующий о дне рынка)")
            
        if pattern_info.get('evening_star'):
            descriptions.append("Вечерняя звезда (сильный медвежий разворотный паттерн из трех свечей, сигнализирующий о вершине рынка)")
            
        if pattern_info.get('three_white_soldiers'):
            descriptions.append("Три белых солдата (сильный бычий тренд, показывающий устойчивый рост)")
            
        if pattern_info.get('three_black_crows'):
            descriptions.append("Три черные вороны (сильный медвежий тренд, показывающий устойчивое падение)")
            
        if pattern_info.get('piercing_line'):
            descriptions.append("Просвет в облаках (бычий разворотный паттерн, показывающий ослабление медвежьего давления)")
            
        if pattern_info.get('dark_cloud_cover'):
            descriptions.append("Завеса из темных облаков (медвежий разворотный паттерн, показывающий ослабление бычьего давления)")
        
        # Возвращаем все описания
        if descriptions:
            return " | ".join(descriptions)
        else:
            return f"Неизвестный паттерн типа: {pattern_info['type']}"