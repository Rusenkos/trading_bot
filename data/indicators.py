### data/indicators.py ###
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """
    Класс для расчета технических индикаторов.
    Предоставляет методы для расчета различных индикаторов на основе DataFrame с ценовыми данными.
    """
    
    @staticmethod
    def calculate_ema(data, period, column='close'):
        """
        Расчет экспоненциальной скользящей средней (EMA)
        
        Args:
            data: DataFrame с ценовыми данными
            period: Период для расчета EMA
            column: Колонка для расчета (обычно 'close')
            
        Returns:
            pandas.Series: Значения EMA
        """
        return data[column].ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_sma(data, period, column='close'):
        """
        Расчет простой скользящей средней (SMA)
        
        Args:
            data: DataFrame с ценовыми данными
            period: Период для расчета SMA
            column: Колонка для расчета (обычно 'close')
            
        Returns:
            pandas.Series: Значения SMA
        """
        return data[column].rolling(window=period).mean()
    
    @staticmethod
    def calculate_rsi(data, period=14, column='close'):
        """
        Расчет индикатора относительной силы (RSI)
        
        Args:
            data: DataFrame с ценовыми данными
            period: Период для расчета RSI (обычно 14)
            column: Колонка для расчета (обычно 'close')
            
        Returns:
            pandas.Series: Значения RSI
        """
        delta = data[column].diff()
        
        # Отделяем прирост и падение
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Рассчитываем среднее значение прироста и падения
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # Избегаем деления на ноль
        avg_loss = avg_loss.replace(0, np.nan)
        
        # Рассчитываем относительную силу
        rs = avg_gain / avg_loss
        rs = rs.replace(np.nan, 0)
        
        # Расчет RSI
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_macd(data, fast_period=12, slow_period=26, signal_period=9, column='close'):
        """
        Расчет индикатора MACD и сигнальной линии
        
        Args:
            data: DataFrame с ценовыми данными
            fast_period: Период быстрой EMA (обычно 12)
            slow_period: Период медленной EMA (обычно 26)
            signal_period: Период сигнальной линии (обычно 9)
            column: Колонка для расчета (обычно 'close')
            
        Returns:
            tuple: (MACD линия, сигнальная линия, гистограмма)
        """
        # Расчет быстрой и медленной EMA
        ema_fast = TechnicalIndicators.calculate_ema(data, fast_period, column)
        ema_slow = TechnicalIndicators.calculate_ema(data, slow_period, column)
        
        # Расчет линии MACD
        macd_line = ema_fast - ema_slow
        
        # Расчет сигнальной линии
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        
        # Расчет гистограммы
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def calculate_bollinger_bands(data, period=20, std_dev=2, column='close'):
        """
        Расчет полос Боллинджера
        
        Args:
            data: DataFrame с ценовыми данными
            period: Период для расчета (обычно 20)
            std_dev: Количество стандартных отклонений (обычно 2)
            column: Колонка для расчета (обычно 'close')
            
        Returns:
            tuple: (средняя линия, верхняя полоса, нижняя полоса)
        """
        # Расчет SMA
        middle_band = TechnicalIndicators.calculate_sma(data, period, column)
        
        # Расчет стандартного отклонения
        std = data[column].rolling(window=period).std()
        
        # Расчет верхней и нижней полос
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        
        return middle_band, upper_band, lower_band
    
    @staticmethod
    def calculate_volume_ma(data, period=20, column='volume'):
        """
        Расчет скользящей средней объема
        
        Args:
            data: DataFrame с ценовыми данными
            period: Период для расчета (обычно 20)
            column: Колонка для расчета (обычно 'volume')
            
        Returns:
            pandas.Series: Значения скользящей средней объема
        """
        return data[column].rolling(window=period).mean()
    
    @staticmethod
    def calculate_atr(data, period=14):
        """
        Расчет индикатора Average True Range (ATR)
        
        Args:
            data: DataFrame с ценовыми данными (должен содержать 'high', 'low', 'close')
            period: Период для расчета (обычно 14)
            
        Returns:
            pandas.Series: Значения ATR
        """
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Расчет True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        
        # Расчет ATR
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def calculate_stochastic(data, k_period=14, d_period=3):
        """
        Расчет Стохастического осциллятора
        
        Args:
            data: DataFrame с ценовыми данными (должен содержать 'high', 'low', 'close')
            k_period: Период для %K (обычно 14)
            d_period: Период для %D (обычно 3)
            
        Returns:
            tuple: (%K, %D)
        """
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Расчет минимума и максимума за период
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        # Расчет %K
        stoch_k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        
        # Расчет %D (скользящая средняя от %K)
        stoch_d = stoch_k.rolling(window=d_period).mean()
        
        return stoch_k, stoch_d
    
    @staticmethod
    def calculate_adx(data, period=14):
        """
        Расчет Average Directional Index (ADX)
        
        Args:
            data: DataFrame с ценовыми данными (должен содержать 'high', 'low', 'close')
            period: Период для расчета (обычно 14)
            
        Returns:
            tuple: (ADX, +DI, -DI)
        """
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Расчет True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        
        # Расчет Plus Directional Movement (+DM) и Minus Directional Movement (-DM)
        plus_dm = high.diff()
        minus_dm = low.diff() * -1
        
        # Условия для +DM и -DM
        plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm), 0)
        minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm), 0)
        
        # Расчет сглаженных значений
        smoothed_tr = tr.rolling(window=period).sum()
        smoothed_plus_dm = plus_dm.rolling(window=period).sum()
        smoothed_minus_dm = minus_dm.rolling(window=period).sum()
        
        # Расчет Plus Directional Indicator (+DI) и Minus Directional Indicator (-DI)
        plus_di = 100 * (smoothed_plus_dm / smoothed_tr)
        minus_di = 100 * (smoothed_minus_dm / smoothed_tr)
        
        # Расчет Directional Movement Index (DX)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        
        # Расчет Average Directional Index (ADX)
        adx = dx.rolling(window=period).mean()
        
        return adx, plus_di, minus_di
    
    @staticmethod
    def calculate_divergence(data, indicator, price_column='close'):
        """
        Определение дивергенций между ценой и индикатором
        
        Args:
            data: DataFrame с ценовыми данными
            indicator: Series с значениями индикатора
            price_column: Колонка с ценой (обычно 'close')
            
        Returns:
            pandas.Series: Серия с отметками дивергенций (1: бычья, -1: медвежья, 0: нет)
        """
        # Создаем пустую серию для дивергенций
        divergence = pd.Series(0, index=data.index)
        
        # Проверяем, что у нас достаточно данных
        if len(data) < 10:
            return divergence
        
        # Находим локальные максимумы и минимумы
        # Это простая реализация, для реальной стратегии может потребоваться более сложный алгоритм
        local_max_price = []
        local_min_price = []
        local_max_indicator = []
        local_min_indicator = []
        
        for i in range(5, len(data) - 5):
            # Локальный максимум цены (простое определение)
            if (data[price_column].iloc[i] > data[price_column].iloc[i-1] and 
                data[price_column].iloc[i] > data[price_column].iloc[i-2] and
                data[price_column].iloc[i] > data[price_column].iloc[i+1] and
                data[price_column].iloc[i] > data[price_column].iloc[i+2]):
                local_max_price.append(i)
                
            # Локальный минимум цены
            if (data[price_column].iloc[i] < data[price_column].iloc[i-1] and 
                data[price_column].iloc[i] < data[price_column].iloc[i-2] and
                data[price_column].iloc[i] < data[price_column].iloc[i+1] and
                data[price_column].iloc[i] < data[price_column].iloc[i+2]):
                local_min_price.append(i)
                
            # Локальный максимум индикатора
            if (indicator.iloc[i] > indicator.iloc[i-1] and 
                indicator.iloc[i] > indicator.iloc[i-2] and
                indicator.iloc[i] > indicator.iloc[i+1] and
                indicator.iloc[i] > indicator.iloc[i+2]):
                local_max_indicator.append(i)
                
            # Локальный минимум индикатора
            if (indicator.iloc[i] < indicator.iloc[i-1] and 
                indicator.iloc[i] < indicator.iloc[i-2] and
                indicator.iloc[i] < indicator.iloc[i+1] and
                indicator.iloc[i] < indicator.iloc[i+2]):
                local_min_indicator.append(i)
        
        # Проверяем бычью дивергенцию (цена делает новый минимум, индикатор нет)
        for i in local_min_price:
            if i > 0 and i < len(data) - 1:
                # Ищем предыдущий локальный минимум цены
                prev_min = None
                for j in local_min_price:
                    if j < i and (prev_min is None or j > prev_min):
                        prev_min = j
                
                if prev_min is not None:
                    # Если цена сделала новый минимум
                    if data[price_column].iloc[i] < data[price_column].iloc[prev_min]:
                        # Ищем соответствующие минимумы индикатора
                        indicator_min_1 = None
                        indicator_min_2 = None
                        
                        for j in local_min_indicator:
                            if j <= i and (indicator_min_1 is None or j > indicator_min_1):
                                indicator_min_1 = j
                        
                        for j in local_min_indicator:
                            if j <= prev_min and (indicator_min_2 is None or j > indicator_min_2):
                                indicator_min_2 = j
                        
                        # Проверяем дивергенцию
                        if (indicator_min_1 is not None and indicator_min_2 is not None and
                            indicator.iloc[indicator_min_1] > indicator.iloc[indicator_min_2]):
                            # Бычья дивергенция
                            divergence.iloc[i] = 1
        
        # Проверяем медвежью дивергенцию (цена делает новый максимум, индикатор нет)
        for i in local_max_price:
            if i > 0 and i < len(data) - 1:
                # Ищем предыдущий локальный максимум цены
                prev_max = None
                for j in local_max_price:
                    if j < i and (prev_max is None or j > prev_max):
                        prev_max = j
                
                if prev_max is not None:
                    # Если цена сделала новый максимум
                    if data[price_column].iloc[i] > data[price_column].iloc[prev_max]:
                        # Ищем соответствующие максимумы индикатора
                        indicator_max_1 = None
                        indicator_max_2 = None
                        
                        for j in local_max_indicator:
                            if j <= i and (indicator_max_1 is None or j > indicator_max_1):
                                indicator_max_1 = j
                        
                        for j in local_max_indicator:
                            if j <= prev_max and (indicator_max_2 is None or j > indicator_max_2):
                                indicator_max_2 = j
                        
                        # Проверяем дивергенцию
                        if (indicator_max_1 is not None and indicator_max_2 is not None and
                            indicator.iloc[indicator_max_1] < indicator.iloc[indicator_max_2]):
                            # Медвежья дивергенция
                            divergence.iloc[i] = -1
        
        return divergence
    
    @staticmethod
    def calculate_all_indicators(data, config=None):
        """
        Расчет всех основных индикаторов
        
        Args:
            data: DataFrame с ценовыми данными
            config: Объект конфигурации с параметрами индикаторов
            
        Returns:
            DataFrame: Исходные данные с добавленными индикаторами
        """
        if data is None or data.empty:
            logger.warning("Пустой DataFrame передан для расчета индикаторов")
            return None
        
        # Копируем данные, чтобы не изменять оригинал
        df = data.copy()
        
        # Используем параметры из конфигурации или значения по умолчанию
        if config:
            ema_short = getattr(config, 'EMA_SHORT', 5)
            ema_long = getattr(config, 'EMA_LONG', 20)
            rsi_period = getattr(config, 'RSI_PERIOD', 14)
            macd_fast = getattr(config, 'MACD_FAST', 12)
            macd_slow = getattr(config, 'MACD_SLOW', 26)
            macd_signal = getattr(config, 'MACD_SIGNAL', 9)
            bb_period = getattr(config, 'BOLLINGER_PERIOD', 20)
            bb_std = getattr(config, 'BOLLINGER_STD', 2)
            volume_period = getattr(config, 'VOLUME_MA_PERIOD', 20)
        else:
            ema_short = 5
            ema_long = 20
            rsi_period = 14
            macd_fast = 12
            macd_slow = 26
            macd_signal = 9
            bb_period = 20
            bb_std = 2
            volume_period = 20
        
        # Расчет EMA
        df[f'EMA_{ema_short}'] = TechnicalIndicators.calculate_ema(df, ema_short)
        df[f'EMA_{ema_long}'] = TechnicalIndicators.calculate_ema(df, ema_long)
        
        # Расчет RSI
        df['RSI'] = TechnicalIndicators.calculate_rsi(df, rsi_period)
        
        # Расчет MACD
        macd_line, signal_line, histogram = TechnicalIndicators.calculate_macd(
            df, macd_fast, macd_slow, macd_signal)
        df['MACD'] = macd_line
        df['MACD_Signal'] = signal_line
        df['MACD_Histogram'] = histogram
        
        # Расчет полос Боллинджера
        middle, upper, lower = TechnicalIndicators.calculate_bollinger_bands(
            df, bb_period, bb_std)
        df['BB_Middle'] = middle
        df['Upper_Band'] = upper
        df['Lower_Band'] = lower
        
        # Расчет скользящей средней объема
        df['Volume_MA'] = TechnicalIndicators.calculate_volume_ma(df, volume_period)
        
        # Расчет соотношения объема к среднему
        df['Volume_Ratio'] = df['volume'] / df['Volume_MA']
        
        # Расчет ATR
        df['ATR'] = TechnicalIndicators.calculate_atr(df, 14)
        
        # Расчет Стохастика
        stoch_k, stoch_d = TechnicalIndicators.calculate_stochastic(df)
        df['Stoch_K'] = stoch_k
        df['Stoch_D'] = stoch_d
        
        # Дивергенции RSI
        df['RSI_Divergence'] = TechnicalIndicators.calculate_divergence(df, df['RSI'])
        
        # Заполняем пропуски в индикаторах
        df = df.bfill()
        
        return df