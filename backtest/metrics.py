"""
Расчет метрик эффективности торговых стратегий.

Содержит функции для расчета ключевых метрик производительности
торговых стратегий, таких как Sharpe Ratio, Max Drawdown, и т.д.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class PerformanceMetrics:
    """
    Класс для расчета метрик эффективности торговых стратегий.
    
    Содержит методы для расчета:
    - Доходности
    - Просадки
    - Коэффициентов Шарпа, Сортино, Калмара
    - Статистики сделок
    - И других метрик производительности
    """
    
    @staticmethod
    def calculate_returns(equity_curve: List[Dict[str, Any]]) -> pd.Series:
        """
        Расчет доходности на основе кривой капитала
        
        Args:
            equity_curve: Список словарей с данными о капитале по дням
            
        Returns:
            Series: Временной ряд доходностей
        """
        if not equity_curve:
            return pd.Series()
        
        # Создаем DataFrame из кривой капитала
        df = pd.DataFrame(equity_curve)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Рассчитываем доходность
        returns = df['equity'].pct_change()
        
        return returns
    
    @staticmethod
    def calculate_statistics(returns: pd.Series, risk_free_rate: float = 0.0) -> Dict[str, float]:
        """
        Расчет статистических показателей доходности
        
        Args:
            returns: Временной ряд доходностей
            risk_free_rate: Безрисковая ставка доходности (годовая)
            
        Returns:
            dict: Статистические показатели
        """
        # Исключаем NaN значения
        returns = returns.dropna()
        
        if len(returns) == 0:
            return {
                'total_return': 0.0,
                'annual_return': 0.0,
                'volatility': 0.0,
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'max_drawdown': 0.0,
                'calmar_ratio': 0.0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'avg_return': 0.0
            }
        
        # Преобразуем годовую безрисковую ставку в дневную
        daily_risk_free = (1 + risk_free_rate) ** (1/252) - 1
        
        # Рассчитываем базовые статистики
        total_return = (1 + returns).prod() - 1
        annual_return = (1 + total_return) ** (252 / len(returns)) - 1
        volatility = returns.std() * np.sqrt(252)  # Годовая волатильность
        
        # Коэффициент Шарпа
        excess_returns = returns - daily_risk_free
        sharpe_ratio = excess_returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
        
        # Коэффициент Сортино
        downside_returns = returns[returns < 0]
        downside_deviation = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        sortino_ratio = (returns.mean() - daily_risk_free) * np.sqrt(252) / downside_deviation if downside_deviation > 0 else 0
        
        # Максимальная просадка
        cumulative_returns = (1 + returns).cumprod()
        max_drawdown = PerformanceMetrics.calculate_max_drawdown(cumulative_returns)
        
        # Коэффициент Калмара
        calmar_ratio = annual_return / max_drawdown if max_drawdown > 0 else 0
        
        # Статистика по сделкам
        win_rate = len(returns[returns > 0]) / len(returns)
        positive_returns = returns[returns > 0].sum()
        negative_returns = abs(returns[returns < 0].sum())
        profit_factor = positive_returns / negative_returns if negative_returns > 0 else float('inf')
        
        avg_win = returns[returns > 0].mean() if len(returns[returns > 0]) > 0 else 0
        avg_loss = returns[returns < 0].mean() if len(returns[returns < 0]) > 0 else 0
        avg_return = returns.mean()
        
        return {
            'total_return': total_return * 100,  # В процентах
            'annual_return': annual_return * 100,  # В процентах
            'volatility': volatility * 100,  # В процентах
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown * 100,  # В процентах
            'calmar_ratio': calmar_ratio,
            'win_rate': win_rate * 100,  # В процентах
            'profit_factor': profit_factor,
            'avg_win': avg_win * 100,  # В процентах
            'avg_loss': avg_loss * 100,  # В процентах
            'avg_return': avg_return * 100  # В процентах
        }
    
    @staticmethod
    def calculate_max_drawdown(equity_curve: Union[pd.Series, List[float]]) -> float:
        """
        Расчет максимальной просадки
        
        Args:
            equity_curve: Кривая капитала
            
        Returns:
            float: Максимальная просадка (в долях)
        """
        if isinstance(equity_curve, list):
            equity_curve = pd.Series(equity_curve)
        
        # Максимум до текущей точки
        running_max = equity_curve.expanding().max()
        
        # Просадка в каждой точке
        drawdown = (equity_curve / running_max - 1)
        
        # Максимальная просадка
        max_drawdown = abs(drawdown.min())
        
        return max_drawdown
    
    @staticmethod
    def analyze_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Анализ сделок
        
        Args:
            trades: Список сделок
            
        Returns:
            dict: Статистика по сделкам
        """
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'avg_holding_days': 0.0,
                'best_trade': None,
                'worst_trade': None
            }
        
        # Фильтруем сделки (оставляем только закрытые позиции)
        closed_trades = [trade for trade in trades if 'exit_date' in trade and 'profit' in trade]
        
        if not closed_trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'avg_holding_days': 0.0,
                'best_trade': None,
                'worst_trade': None
            }
        
        # Разделяем на выигрышные и проигрышные сделки
        winning_trades = [trade for trade in closed_trades if trade['profit'] > 0]
        losing_trades = [trade for trade in closed_trades if trade['profit'] <= 0]
        
        # Статистика по сделкам
        total_trades = len(closed_trades)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        # Средняя прибыль и убыток
        avg_profit = np.mean([trade['profit'] for trade in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([abs(trade['profit']) for trade in losing_trades]) if losing_trades else 0
        
        # Профит-фактор
        total_profit = sum(trade['profit'] for trade in winning_trades)
        total_loss = abs(sum(trade['profit'] for trade in losing_trades))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        # Среднее время удержания
        avg_holding_days = np.mean([trade['holding_days'] for trade in closed_trades])
        
        # Лучшая и худшая сделки
        best_trade = max(closed_trades, key=lambda x: x['profit']) if closed_trades else None
        worst_trade = min(closed_trades, key=lambda x: x['profit']) if closed_trades else None
        
        # Группировка сделок по причинам закрытия
        close_reasons = {}
        for trade in closed_trades:
            reason = trade.get('reason', 'unknown')
            if reason not in close_reasons:
                close_reasons[reason] = 0
            close_reasons[reason] += 1
        
        # Группировка сделок по символам
        symbols = {}
        for trade in closed_trades:
            symbol = trade.get('symbol', 'unknown')
            if symbol not in symbols:
                symbols[symbol] = {
                    'count': 0,
                    'wins': 0,
                    'losses': 0,
                    'profit': 0
                }
            
            symbols[symbol]['count'] += 1
            
            if trade['profit'] > 0:
                symbols[symbol]['wins'] += 1
            else:
                symbols[symbol]['losses'] += 1
            
            symbols[symbol]['profit'] += trade['profit']
        
        # Статистика по месяцам
        monthly_stats = {}
        for trade in closed_trades:
            exit_date = pd.to_datetime(trade['exit_date'])
            month_key = f"{exit_date.year}-{exit_date.month:02d}"
            
            if month_key not in monthly_stats:
                monthly_stats[month_key] = {
                    'count': 0,
                    'wins': 0,
                    'losses': 0,
                    'profit': 0
                }
            
            monthly_stats[month_key]['count'] += 1
            
            if trade['profit'] > 0:
                monthly_stats[month_key]['wins'] += 1
            else:
                monthly_stats[month_key]['losses'] += 1
            
            monthly_stats[month_key]['profit'] += trade['profit']
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate * 100,  # В процентах
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_holding_days': avg_holding_days,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'close_reasons': close_reasons,
            'symbols': symbols,
            'monthly_stats': monthly_stats
        }
    
    @staticmethod
    def calculate_drawdowns(equity_curve: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Расчет всех просадок
        
        Args:
            equity_curve: Кривая капитала
            
        Returns:
            list: Список всех просадок
        """
        if not equity_curve:
            return []
        
        # Создаем DataFrame из кривой капитала
        df = pd.DataFrame(equity_curve)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Максимум до текущей точки
        running_max = df['equity'].expanding().max()
        
        # Просадка в каждой точке
        drawdown = (df['equity'] / running_max - 1) * 100  # В процентах
        
        # Находим все просадки
        drawdowns = []
        in_drawdown = False
        start_date = None
        peak_value = 0
        
        for date, value in drawdown.items():
            if value < 0 and not in_drawdown:
                # Начало просадки
                in_drawdown = True
                start_date = date
                peak_value = running_max.loc[date]
            elif value == 0 and in_drawdown:
                # Конец просадки
                in_drawdown = False
                end_date = date
                
                # Находим максимальную глубину просадки
                section = drawdown[start_date:end_date]
                max_depth = section.min()
                max_depth_date = section.idxmin()
                
                # Добавляем информацию о просадке
                drawdowns.append({
                    'start_date': start_date,
                    'end_date': end_date,
                    'max_depth_date': max_depth_date,
                    'max_depth': max_depth,
                    'duration': (end_date - start_date).days,
                    'peak_value': peak_value,
                    'trough_value': peak_value * (1 + max_depth / 100)
                })
        
        # Если последняя просадка не закончилась
        if in_drawdown:
            end_date = drawdown.index[-1]
            
            # Находим максимальную глубину просадки
            section = drawdown[start_date:end_date]
            max_depth = section.min()
            max_depth_date = section.idxmin()
            
            # Добавляем информацию о просадке
            drawdowns.append({
                'start_date': start_date,
                'end_date': end_date,
                'max_depth_date': max_depth_date,
                'max_depth': max_depth,
                'duration': (end_date - start_date).days,
                'peak_value': peak_value,
                'trough_value': peak_value * (1 + max_depth / 100),
                'ongoing': True
            })
        
        # Сортируем просадки по глубине
        drawdowns.sort(key=lambda x: x['max_depth'])
        
        return drawdowns
    
    @staticmethod
    def calculate_monthly_returns(equity_curve: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Расчет доходности по месяцам
        
        Args:
            equity_curve: Кривая капитала
            
        Returns:
            dict: Доходность по месяцам
        """
        if not equity_curve:
            return {}
        
        # Создаем DataFrame из кривой капитала
        df = pd.DataFrame(equity_curve)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Создаем таблицу с месячной доходностью
        monthly_returns = {}
        
        # Группируем по месяцам
        df['month'] = df.index.to_period('M')
        grouped = df.groupby('month')
        
        for month, group in grouped:
            # Начальное и конечное значение для месяца
            start_value = group['equity'].iloc[0]
            end_value = group['equity'].iloc[-1]
            
            # Расчет доходности
            return_value = (end_value / start_value - 1) * 100  # В процентах
            
            # Добавляем в результат
            monthly_returns[str(month)] = return_value
        
        return monthly_returns
    
    @staticmethod
    def calculate_rolling_statistics(returns: pd.Series, window: int = 20) -> Dict[str, pd.Series]:
        """
        Расчет скользящих статистик
        
        Args:
            returns: Ряд доходностей
            window: Размер окна
            
        Returns:
            dict: Словарь со скользящими статистиками
        """
        # Исключаем NaN значения
        returns = returns.dropna()
        
        if len(returns) < window:
            return {
                'rolling_return': pd.Series(),
                'rolling_volatility': pd.Series(),
                'rolling_sharpe': pd.Series(),
                'rolling_drawdown': pd.Series()
            }
        
        # Скользящая доходность
        rolling_return = returns.rolling(window=window).apply(
            lambda x: (1 + x).prod() - 1, raw=False
        ) * 100  # В процентах
        
        # Скользящая волатильность
        rolling_volatility = returns.rolling(window=window).std() * np.sqrt(window) * 100  # В процентах
        
        # Скользящий коэффициент Шарпа
        rolling_sharpe = (returns.rolling(window=window).mean() / returns.rolling(window=window).std()) * np.sqrt(252)
        
        # Скользящая просадка
        rolling_drawdown = pd.Series(index=returns.index)
        
        for i in range(window, len(returns) + 1):
            section = returns.iloc[i-window:i]
            cumulative = (1 + section).cumprod()
            drawdown = PerformanceMetrics.calculate_max_drawdown(cumulative)
            rolling_drawdown.iloc[i-1] = drawdown * 100  # В процентах
        
        return {
            'rolling_return': rolling_return,
            'rolling_volatility': rolling_volatility,
            'rolling_sharpe': rolling_sharpe,
            'rolling_drawdown': rolling_drawdown
        }
    
    @staticmethod
    def calculate_var(returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Расчет Value at Risk (VaR)
        
        Args:
            returns: Ряд доходностей
            confidence: Уровень достоверности
            
        Returns:
            float: Значение VaR
        """
        # Исключаем NaN значения
        returns = returns.dropna()
        
        if len(returns) == 0:
            return 0.0
        
        # Рассчитываем квантиль
        var = np.percentile(returns, 100 * (1 - confidence))
        
        return abs(var) * 100  # В процентах
    
    @staticmethod
    def calculate_cvar(returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Расчет Conditional Value at Risk (CVaR)
        
        Args:
            returns: Ряд доходностей
            confidence: Уровень достоверности
            
        Returns:
            float: Значение CVaR
        """
        # Исключаем NaN значения
        returns = returns.dropna()
        
        if len(returns) == 0:
            return 0.0
        
        # Рассчитываем VaR
        var = np.percentile(returns, 100 * (1 - confidence))
        
        # Фильтруем доходности, которые меньше VaR
        cvar_returns = returns[returns <= var]
        
        # Рассчитываем CVaR
        cvar = cvar_returns.mean() if len(cvar_returns) > 0 else var
        
        return abs(cvar) * 100  # В процентах
    
    @staticmethod
    def generate_performance_report(equity_curve: List[Dict[str, Any]], trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Генерация полного отчета о производительности
        
        Args:
            equity_curve: Кривая капитала
            trades: Список сделок
            
        Returns:
            dict: Полный отчет о производительности
        """
        # Рассчитываем доходность
        returns = PerformanceMetrics.calculate_returns(equity_curve)
        
        # Рассчитываем статистики
        statistics = PerformanceMetrics.calculate_statistics(returns)
        
        # Анализируем сделки
        trade_analysis = PerformanceMetrics.analyze_trades(trades)
        
        # Рассчитываем просадки
        drawdowns = PerformanceMetrics.calculate_drawdowns(equity_curve)
        
        # Рассчитываем доходность по месяцам
        monthly_returns = PerformanceMetrics.calculate_monthly_returns(equity_curve)
        
        # Рассчитываем скользящие статистики
        rolling_stats = PerformanceMetrics.calculate_rolling_statistics(returns)
        
        # Рассчитываем VaR и CVaR
        var_95 = PerformanceMetrics.calculate_var(returns, 0.95)
        var_99 = PerformanceMetrics.calculate_var(returns, 0.99)
        cvar_95 = PerformanceMetrics.calculate_cvar(returns, 0.95)
        cvar_99 = PerformanceMetrics.calculate_cvar(returns, 0.99)
        
        # Формируем полный отчет
        report = {
            'statistics': statistics,
            'trade_analysis': trade_analysis,
            'drawdowns': drawdowns,
            'monthly_returns': monthly_returns,
            'risk_metrics': {
                'var_95': var_95,
                'var_99': var_99,
                'cvar_95': cvar_95,
                'cvar_99': cvar_99
            },
            'rolling_statistics': {
                key: values.dropna().to_dict() for key, values in rolling_stats.items()
            }
        }
        
        return report