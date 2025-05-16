"""
Движок бэктестинга для оценки эффективности торговых стратегий.

Позволяет тестировать стратегии на исторических данных с учетом
комиссий, проскальзывания и других реальных факторов.
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple
import matplotlib.pyplot as plt
from copy import deepcopy

from data.market_data import MarketDataProvider
from data.indicators import TechnicalIndicators
from data.patterns import CandlePatterns
from strategies.base import StrategyInterface
from strategies.trend import TrendStrategy
from strategies.reversal import ReversalStrategy
from strategies.combined import CombinedStrategy
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

class BacktestEngine:
    """
    Движок для проведения бэктестинга торговых стратегий.
    
    Позволяет:
    - Запускать тестирование стратегий на исторических данных
    - Симулировать исполнение сделок с учетом комиссий и проскальзывания
    - Рассчитывать метрики эффективности стратегии
    - Визуализировать результаты
    """
    
    def __init__(self, config):
        """
        Инициализация движка бэктестинга
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        self.data_provider = MarketDataProvider(config.TINKOFF_TOKEN, config)
        self.initial_capital = config.INITIAL_CAPITAL
        self.commission_rate = config.COMMISSION_RATE
        
        # Инициализация внутренних переменных
        self.trades = []
        self.equity_curve = []
        self.daily_returns = []
        self.positions = {}
        self.capital = self.initial_capital
        self.max_capital = self.initial_capital
    
    def run_backtest(self, strategy_name: str, symbol: str, 
                    start_date: datetime, end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Запуск бэктестинга для заданной стратегии и символа
        
        Args:
            strategy_name: Название стратегии
            symbol: Символ для бэктестинга
            start_date: Дата начала бэктеста
            end_date: Дата окончания бэктеста (если None, используется текущая дата)
            
        Returns:
            dict: Результаты бэктеста
        """
        logger.info(f"Запуск бэктеста для стратегии {strategy_name} на символе {symbol}")
        
        # Если конечная дата не указана, используем текущую
        if end_date is None:
            end_date = datetime.now()
        
        # Создаем стратегию
        strategy = self._create_strategy(strategy_name)
        if not strategy:
            logger.error(f"Стратегия {strategy_name} не найдена")
            return {"error": f"Стратегия {strategy_name} не найдена"}
        
        # Получаем исторические данные
        data = self._get_historical_data(symbol, start_date, end_date)
        if data is None or len(data) < 20:
            logger.error(f"Недостаточно данных для бэктеста {symbol}")
            return {"error": f"Недостаточно данных для бэктеста {symbol}"}
        
        # Рассчитываем индикаторы
        data = TechnicalIndicators.calculate_all_indicators(data, self.config)
        
        # Определяем свечные паттерны
        data = CandlePatterns.identify_patterns(data)
        
        # Сбрасываем внутренние переменные
        self.trades = []
        self.equity_curve = []
        self.daily_returns = []
        self.positions = {}
        self.capital = self.initial_capital
        self.max_capital = self.initial_capital
        
        # Запускаем симуляцию
        self._run_simulation(data, strategy, symbol)
        
        # Рассчитываем метрики
        results = self._calculate_metrics()
        
        logger.info(f"Бэктест завершен. Доходность: {results['total_return']:.2f}%, "
                  f"сделок: {results['total_trades']}")
        
        return results
    
    def _create_strategy(self, strategy_name: str) -> Optional[StrategyInterface]:
        """
        Создание стратегии по названию
        
        Args:
            strategy_name: Название стратегии
            
        Returns:
            StrategyInterface: Экземпляр стратегии или None
        """
        if strategy_name.lower() == "trend":
            return TrendStrategy(self.config)
        elif strategy_name.lower() == "reversal":
            return ReversalStrategy(self.config)
        elif strategy_name.lower() == "combined":
            return CombinedStrategy(self.config)
        else:
            return None
    
    def _get_historical_data(self, symbol: str, start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """
        Получение исторических данных для бэктеста
        """
        try:
            # days_diff = (end_date - start_date).days
            days_diff = (end_date - start_date).days
            # Получаем данные
            data = self.data_provider.get_historical_data(
                symbol, 
                self.config.TIMEFRAME,
                days_back=days_diff + 30  # Добавляем запас для расчета индикаторов
            )
            # Фильтруем данные по дате
            if data is not None:
                data = data[(data.index >= start_date) & (data.index <= end_date)]
            # Добавляем индикаторы
            data = TechnicalIndicators.calculate_all_indicators(data, self.config)
            return data
        except Exception as e:
            logger.error(f"Ошибка при получении исторических данных: {e}")
            return None
    
    def _run_simulation(self, data: pd.DataFrame, strategy: StrategyInterface, symbol: str) -> None:
        """
        Запуск симуляции торговли
        
        Args:
            data: DataFrame с историческими данными
            strategy: Стратегия для тестирования
            symbol: Тикер символа
        """
        # Минимальное количество свечей для работы индикаторов
        lookback = 30
        
        # Начальная запись для кривой капитала
        self.equity_curve.append({
            'date': data.index[lookback],
            'equity': self.capital,
            'position': 0
        })
        
        # Для каждой свечи после lookback
        for i in range(lookback, len(data)):
            # Получаем текущую дату
            current_date = data.index[i]
            
            # Обновляем кривую капитала
            if i > lookback:
                self.equity_curve.append({
                    'date': current_date,
                    'equity': self.capital,
                    'position': 1 if symbol in self.positions else 0
                })
            
            # Получаем срез данных для анализа
            data_slice = data.iloc[:i+1]
            
            # Текущая цена закрытия
            current_price = data.iloc[i]['close']
            
            # Если есть открытая позиция, проверяем сигналы на продажу
            if symbol in self.positions:
                position = self.positions[symbol]
                
                # Проверяем стоп-лосс
                if current_price <= position['stop_loss']:
                    # Закрываем позицию по стоп-лоссу
                    self._close_position(symbol, current_price, current_date, "stop_loss")
                    continue
                
                # Проверяем тейк-профит
                if current_price >= position['take_profit']:
                    # Закрываем позицию по тейк-профиту
                    self._close_position(symbol, current_price, current_date, "take_profit")
                    continue
                
                # Проверяем максимальное время удержания
                days_held = (current_date - position['entry_date']).days
                if days_held >= self.config.MAX_HOLDING_DAYS:
                    # Закрываем позицию по времени
                    self._close_position(symbol, current_price, current_date, "max_holding_time")
                    continue
                
                # Проверяем сигналы от стратегии
                sell_signal, sell_details = strategy.check_sell_signals(data_slice, position)
                
                if sell_signal:
                    # Закрываем позицию по сигналу
                    self._close_position(symbol, current_price, current_date, "strategy_signal")
            else:
                # Если нет открытой позиции, проверяем сигналы на покупку
                buy_signal, buy_details = strategy.check_buy_signals(data_slice)
                
                if buy_signal:
                    # Открываем новую позицию
                    self._open_position(symbol, current_price, current_date, buy_details)
        
        # Закрываем оставшиеся позиции по последней цене
        last_date = data.index[-1]
        last_price = data.iloc[-1]['close']
        
        for symbol in list(self.positions.keys()):
            self._close_position(symbol, last_price, last_date, "end_of_backtest")
    
    def _open_position(self, symbol: str, price: float, date: datetime, details: Dict[str, Any]) -> None:
        """
        Открытие новой позиции
        
        Args:
            symbol: Тикер символа
            price: Цена открытия
            date: Дата открытия
            details: Детали сигнала
        """
        # Проверяем, есть ли у нас уже открытая позиция
        if symbol in self.positions:
            logger.warning(f"Позиция для {symbol} уже открыта, пропускаем сигнал")
            return
        
        # Рассчитываем размер позиции (без учета комиссии)
        max_position_size = self.capital * self.config.MAX_POSITION_SIZE
        
        # Рассчитываем количество акций
        quantity = int(max_position_size / price)
        
        # Если количество акций ноль, значит недостаточно капитала
        if quantity <= 0:
            logger.warning(f"Недостаточно капитала для открытия позиции {symbol}")
            return
        
        # Рассчитываем полную стоимость позиции с учетом комиссии
        position_value = quantity * price
        commission = position_value * self.commission_rate
        total_cost = position_value + commission
        
        # Проверяем, достаточно ли капитала
        if total_cost > self.capital:
            # Корректируем количество
            quantity = int((self.capital / (price * (1 + self.commission_rate))))
            
            # Пересчитываем стоимость
            position_value = quantity * price
            commission = position_value * self.commission_rate
            total_cost = position_value + commission
        
        # Если все еще недостаточно капитала
        if quantity <= 0 or total_cost > self.capital:
            logger.warning(f"Недостаточно капитала для открытия позиции {symbol}")
            return
        
        # Рассчитываем уровни стоп-лосса и тейк-профита
        stop_loss_percent = self.config.STOP_LOSS_PERCENT / 100
        take_profit_percent = self.config.TAKE_PROFIT_PERCENT / 100
        
        stop_loss = price * (1 - stop_loss_percent)
        take_profit = price * (1 + take_profit_percent)
        
        # Создаем запись о позиции
        position = {
            'symbol': symbol,
            'entry_price': price,
            'quantity': quantity,
            'entry_date': date,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'value': position_value
        }
        
        # Сохраняем позицию
        self.positions[symbol] = position
        
        # Обновляем капитал
        self.capital -= total_cost
        
        # Сохраняем запись о сделке
        trade = {
            'symbol': symbol,
            'entry_date': date,
            'entry_price': price,
            'quantity': quantity,
            'type': 'buy',
            'commission': commission,
            'value': position_value,
            'reasons': details.get('reasons', [])
        }
        
        self.trades.append(trade)
        
        logger.debug(f"Открыта позиция {symbol}: {quantity} @ {price:.2f}, "
                   f"стоп: {stop_loss:.2f}, тейк: {take_profit:.2f}")
    
    def _close_position(self, symbol: str, price: float, date: datetime, reason: str) -> None:
        """
        Закрытие позиции
        
        Args:
            symbol: Тикер символа
            price: Цена закрытия
            date: Дата закрытия
            reason: Причина закрытия
        """
        # Проверяем, есть ли у нас открытая позиция
        if symbol not in self.positions:
            logger.warning(f"Нет открытой позиции для {symbol}, пропускаем сигнал")
            return
        
        position = self.positions[symbol]
        
        # Рассчитываем стоимость позиции при закрытии
        close_value = position['quantity'] * price
        commission = close_value * self.commission_rate
        
        # Обновляем капитал
        self.capital += close_value - commission
        
        # Обновляем максимальный капитал
        if self.capital > self.max_capital:
            self.max_capital = self.capital
        
        # Рассчитываем результаты сделки
        entry_value = position['quantity'] * position['entry_price']
        profit = close_value - entry_value
        profit_percent = (price / position['entry_price'] - 1) * 100
        
        # Сохраняем запись о закрытии сделки
        trade = {
            'symbol': symbol,
            'entry_date': position['entry_date'],
            'entry_price': position['entry_price'],
            'exit_date': date,
            'exit_price': price,
            'quantity': position['quantity'],
            'type': 'sell',
            'reason': reason,
            'commission': commission,
            'profit': profit,
            'profit_percent': profit_percent,
            'holding_days': (date - position['entry_date']).days
        }
        
        self.trades.append(trade)
        
        # Удаляем позицию
        del self.positions[symbol]
        
        logger.debug(f"Закрыта позиция {symbol}: {position['quantity']} @ {price:.2f}, "
                   f"прибыль: {profit:.2f} ({profit_percent:.2f}%), причина: {reason}")
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        """
        Расчет метрик эффективности стратегии
        
        Returns:
            dict: Метрики стратегии
        """
        # Создаем DataFrame из кривой капитала
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df.set_index('date', inplace=True)
        
        # Рассчитываем дневную доходность
        if len(equity_df) > 1:
            equity_df['daily_return'] = equity_df['equity'].pct_change()
        else:
            equity_df['daily_return'] = 0
        
        # Собираем всю информацию о сделках
        trades_info = []
        
        for i in range(0, len(self.trades), 2):
            if i + 1 < len(self.trades):
                buy = self.trades[i]
                sell = self.trades[i + 1]
                
                trade_info = {
                    'symbol': buy['symbol'],
                    'entry_date': buy['entry_date'],
                    'exit_date': sell['exit_date'],
                    'entry_price': buy['entry_price'],
                    'exit_price': sell['exit_price'],
                    'quantity': buy['quantity'],
                    'profit': sell['profit'],
                    'profit_percent': sell['profit_percent'],
                    'holding_days': sell['holding_days'],
                    'reason': sell.get('reason', 'unknown')
                }
                
                trades_info.append(trade_info)
        
        # Рассчитываем основные метрики
        total_trades = len(trades_info)
        winning_trades = sum(1 for trade in trades_info if trade['profit'] > 0)
        losing_trades = total_trades - winning_trades
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Средняя прибыль и убыток
        avg_profit = np.mean([trade['profit'] for trade in trades_info if trade['profit'] > 0]) if winning_trades > 0 else 0
        avg_loss = np.mean([abs(trade['profit']) for trade in trades_info if trade['profit'] <= 0]) if losing_trades > 0 else 0
        
        # Профит-фактор
        profit_factor = sum(trade['profit'] for trade in trades_info if trade['profit'] > 0) / abs(sum(trade['profit'] for trade in trades_info if trade['profit'] <= 0)) if losing_trades > 0 else float('inf')
        
        # Расчет доходности
        total_return = (self.capital / self.initial_capital - 1) * 100
        
        # Расчет годовой доходности
        if len(equity_df) > 1:
            start_date = equity_df.index[0]
            end_date = equity_df.index[-1]
            years = (end_date - start_date).days / 365
            annual_return = ((1 + total_return / 100) ** (1 / years) - 1) * 100 if years > 0 else 0
        else:
            annual_return = 0
        
        # Расчет максимальной просадки
        max_drawdown = 0
        peak = self.initial_capital
        
        for equity in equity_df['equity']:
            # Обновляем пик
            if equity > peak:
                peak = equity
            
            # Рассчитываем текущую просадку
            drawdown = (peak - equity) / peak * 100
            
            # Обновляем максимальную просадку
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Расчет коэффициента Шарпа
        risk_free_rate = 0.02  # 2% годовых
        daily_returns = equity_df['daily_return'].dropna()
        
        if len(daily_returns) > 0:
            daily_risk_free = (1 + risk_free_rate) ** (1/252) - 1
            excess_returns = daily_returns - daily_risk_free
            sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Формируем результаты
        results = {
            'initial_capital': self.initial_capital,
            'final_capital': self.capital,
            'total_return': total_return,
            'annual_return': annual_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate * 100,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'equity_curve': equity_df.reset_index().to_dict('records'),
            'trades': trades_info
        }
        
        return results
    
    def plot_results(self, results: Dict[str, Any], save_path: Optional[str] = None) -> None:
        """
        Построение графиков результатов бэктеста
        
        Args:
            results: Результаты бэктеста
            save_path: Путь для сохранения графика (если None, график отображается)
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            
            # Создаем фигуру с подграфиками
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 18), gridspec_kw={'height_ratios': [3, 1, 1]})
            
            # Подготавливаем данные
            equity_data = pd.DataFrame(results['equity_curve'])
            equity_data['date'] = pd.to_datetime(equity_data['date'])
            equity_data.set_index('date', inplace=True)
            
            # График кривой капитала
            ax1.plot(equity_data.index, equity_data['equity'], label='Equity')
            ax1.set_title('Equity Curve')
            ax1.set_ylabel('Capital')
            ax1.grid(True)
            ax1.legend()
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax1.xaxis.set_major_locator(mdates.MonthLocator())
            
            # График отметок сделок
            for trade in results['trades']:
                entry_date = pd.to_datetime(trade['entry_date'])
                exit_date = pd.to_datetime(trade['exit_date'])
                
                # Находим значения капитала на даты сделки
                entry_equity = equity_data.loc[entry_date:entry_date].iloc[0]['equity'] if not equity_data.loc[entry_date:entry_date].empty else None
                exit_equity = equity_data.loc[exit_date:exit_date].iloc[0]['equity'] if not equity_data.loc[exit_date:exit_date].empty else None
                
                if entry_equity is not None:
                    ax1.scatter(entry_date, entry_equity, c='g', marker='^', s=100)
                if exit_equity is not None:
                    ax1.scatter(exit_date, exit_equity, c='r', marker='v', s=100)
            
            # График просадок
            drawdowns = []
            rolling_max = equity_data['equity'].expanding().max()
            drawdown = (rolling_max - equity_data['equity']) / rolling_max * 100
            
            ax2.fill_between(drawdown.index, 0, drawdown, alpha=0.3, color='red')
            ax2.set_title('Drawdown (%)')
            ax2.set_ylabel('Drawdown %')
            ax2.grid(True)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax2.xaxis.set_major_locator(mdates.MonthLocator())
            ax2.set_ylim(bottom=0)
            
            # График прибыли по сделкам
            trades_df = pd.DataFrame(results['trades'])
            if not trades_df.empty:
                trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
                trades_df.set_index('entry_date', inplace=True)
                
                # Создаем столбец для цвета на основе прибыли
                trades_df['color'] = trades_df['profit'].apply(lambda x: 'g' if x > 0 else 'r')
                
                ax3.bar(trades_df.index, trades_df['profit_percent'], color=trades_df['color'])
                ax3.set_title('Trade Results (%)')
                ax3.set_ylabel('Profit %')
                ax3.grid(True)
                ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
                ax3.xaxis.set_major_locator(mdates.MonthLocator())
            
            # Добавляем подпись с метриками
            metrics_text = (
                f"Total Return: {results['total_return']:.2f}%\n"
                f"Annual Return: {results['annual_return']:.2f}%\n"
                f"Max Drawdown: {results['max_drawdown']:.2f}%\n"
                f"Sharpe Ratio: {results['sharpe_ratio']:.2f}\n"
                f"Win Rate: {results['win_rate']:.2f}%\n"
                f"Profit Factor: {results['profit_factor']:.2f}"
            )
            
            plt.figtext(0.01, 0.01, metrics_text, fontsize=12, bbox=dict(facecolor='white', alpha=0.8))
            
            # Настраиваем внешний вид
            plt.tight_layout()
            plt.subplots_adjust(bottom=0.1)
            
            # Сохраняем или отображаем
            if save_path:
                plt.savefig(save_path, dpi=100)
                plt.close()
            else:
                plt.show()
                
        except Exception as e:
            logger.error(f"Ошибка при построении графиков: {e}")
    
    def optimize_parameters(self, strategy_name: str, symbol: str, 
                          parameter_ranges: Dict[str, List[Any]], 
                          start_date: datetime, end_date: Optional[datetime] = None, 
                          metric: str = 'sharpe_ratio') -> Dict[str, Any]:
        """
        Оптимизация параметров стратегии
        
        Args:
            strategy_name: Название стратегии
            symbol: Символ для бэктеста
            parameter_ranges: Диапазоны параметров для оптимизации
            start_date: Дата начала бэктеста
            end_date: Дата окончания бэктеста
            metric: Метрика для оптимизации
            
        Returns:
            dict: Результаты оптимизации
        """
        logger.info(f"Запуск оптимизации параметров для стратегии {strategy_name} на символе {symbol}")
        
        # Если конечная дата не указана, используем текущую
        if end_date is None:
            end_date = datetime.now()
        
        # Получаем исторические данные для всего периода
        data = self._get_historical_data(symbol, start_date, end_date)
        if data is None or len(data) < 20:
            logger.error(f"Недостаточно данных для оптимизации {symbol}")
            return {"error": f"Недостаточно данных для оптимизации {symbol}"}
        
        # Создаем копию конфигурации для модификации
        from copy import deepcopy
        
        # Результаты всех прогонов
        all_results = []
        
        # Лучший результат
        best_result = None
        best_params = None
        best_metric_value = float('-inf')
        
        # Общее количество комбинаций
        total_combinations = 1
        for param_values in parameter_ranges.values():
            total_combinations *= len(param_values)
        
        logger.info(f"Запуск оптимизации с {total_combinations} комбинациями параметров")
        
        # Запускаем перебор параметров
        from itertools import product
        
        # Получаем имена параметров и их значения
        param_names = list(parameter_ranges.keys())
        param_values = list(parameter_ranges.values())
        
        # Для каждой комбинации параметров
        for i, combo in enumerate(product(*param_values)):
            # Создаем словарь параметров
            params = dict(zip(param_names, combo))
            
            # Создаем копию конфигурации
            config_copy = deepcopy(self.config)
            
            # Обновляем параметры в конфигурации
            for param_name, param_value in params.items():
                setattr(config_copy, param_name, param_value)
            
            # Создаем стратегию с новыми параметрами
            if strategy_name.lower() == "trend":
                strategy = TrendStrategy(config_copy)
            elif strategy_name.lower() == "reversal":
                strategy = ReversalStrategy(config_copy)
            elif strategy_name.lower() == "combined":
                strategy = CombinedStrategy(config_copy)
            else:
                continue
            
            # Сбрасываем внутренние переменные
            self.trades = []
            self.equity_curve = []
            self.daily_returns = []
            self.positions = {}
            self.capital = self.initial_capital
            self.max_capital = self.initial_capital
            
            # Запускаем симуляцию с новыми параметрами
            self._run_simulation(data.copy(), strategy, symbol)
            
            # Рассчитываем метрики
            results = self._calculate_metrics()
            
            # Добавляем параметры к результатам
            results['parameters'] = params
            
            # Добавляем в общий список
            all_results.append(results)
            
            # Проверяем, является ли текущий результат лучшим
            metric_value = results.get(metric, float('-inf'))
            
            if metric_value > best_metric_value:
                best_metric_value = metric_value
                best_result = results
                best_params = params
            
            # Выводим прогресс
            if i % 10 == 0 or i == total_combinations - 1:
                logger.info(f"Прогресс оптимизации: {i+1}/{total_combinations} ({(i+1)/total_combinations*100:.1f}%)")
        
        # Формируем результаты оптимизации
        optimization_results = {
            'best_params': best_params,
            'best_performance': best_result,
            'all_results': all_results
        }
        
        logger.info(f"Оптимизация завершена. Лучшие параметры: {best_params}")
        
        return optimization_results