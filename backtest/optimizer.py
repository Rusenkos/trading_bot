"""
Оптимизатор параметров торговых стратегий.

Позволяет подбирать оптимальные параметры для торговых стратегий
путем перебора различных комбинаций параметров и оценки результатов.
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from itertools import product
import time
import concurrent.futures
from copy import deepcopy

from backtest.engine import BacktestEngine
from config.config import Config

logger = logging.getLogger(__name__)

class StrategyOptimizer:
    """
    Оптимизатор параметров торговых стратегий.
    
    Методы оптимизации:
    - Полный перебор (grid search)
    - Параллельный перебор
    - Генетический алгоритм (в будущем)
    """
    
    def __init__(self, config):
        """
        Инициализация оптимизатора
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        self.backtest_engine = BacktestEngine(config)
    
    def optimize(self, strategy_name: str, symbol: str, 
               parameter_ranges: Optional[Dict[str, List[Any]]] = None, 
               start_date: Optional[datetime] = None, 
               end_date: Optional[datetime] = None,
               metric: str = 'sharpe_ratio',
               parallel: bool = True,
               max_workers: int = 4) -> Dict[str, Any]:
        """
        Запуск оптимизации параметров стратегии
        
        Args:
            strategy_name: Название стратегии
            symbol: Символ для оптимизации
            parameter_ranges: Диапазоны параметров (если None, используются предустановленные)
            start_date: Дата начала (если None, используется 365 дней назад)
            end_date: Дата окончания (если None, используется текущая дата)
            metric: Метрика для оптимизации
            parallel: Флаг использования параллельного вычисления
            max_workers: Максимальное количество рабочих процессов
            
        Returns:
            dict: Результаты оптимизации
        """
        logger.info(f"Запуск оптимизации параметров для стратегии {strategy_name} на символе {symbol}")
        
        # Если диапазоны параметров не указаны, используем предустановленные
        if parameter_ranges is None:
            parameter_ranges = self._get_default_parameter_ranges(strategy_name)
        
        # Если даты не указаны, устанавливаем значения по умолчанию
        if start_date is None:
            start_date = datetime.now() - timedelta(days=365)
        
        if end_date is None:
            end_date = datetime.now()
        
        # Запускаем оптимизацию в зависимости от выбранного метода
        if parallel and max_workers > 1:
            results = self._parallel_grid_search(
                strategy_name, symbol, parameter_ranges, 
                start_date, end_date, metric, max_workers
            )
        else:
            results = self._grid_search(
                strategy_name, symbol, parameter_ranges, 
                start_date, end_date, metric
            )
        
        return results
    
    def _get_default_parameter_ranges(self, strategy_name: str) -> Dict[str, List[Any]]:
        """
        Получение предустановленных диапазонов параметров для стратегии
        
        Args:
            strategy_name: Название стратегии
            
        Returns:
            dict: Диапазоны параметров
        """
        # Параметры для трендовой стратегии
        if strategy_name.lower() == "trend":
            return {
                'EMA_SHORT': [3, 5, 8, 10, 12],
                'EMA_LONG': [15, 20, 25, 30],
                'MIN_VOLUME_FACTOR': [1.0, 1.5, 2.0, 2.5],
                'STOP_LOSS_PERCENT': [1.5, 2.0, 2.5, 3.0],
                'TAKE_PROFIT_PERCENT': [3.0, 4.0, 5.0, 6.0, 7.0]
            }
        
        # Параметры для контртрендовой стратегии
        elif strategy_name.lower() == "reversal":
            return {
                'RSI_PERIOD': [7, 10, 14, 21],
                'RSI_OVERSOLD': [20, 25, 30, 35],
                'RSI_OVERBOUGHT': [65, 70, 75, 80],
                'BOLLINGER_PERIOD': [15, 20, 25],
                'BOLLINGER_STD': [1.5, 2.0, 2.5],
                'STOP_LOSS_PERCENT': [1.5, 2.0, 2.5, 3.0],
                'TAKE_PROFIT_PERCENT': [3.0, 4.0, 5.0, 6.0]
            }
        
        # Параметры для комбинированной стратегии
        elif strategy_name.lower() == "combined":
            return {
                'EMA_SHORT': [5, 8, 10],
                'EMA_LONG': [15, 20, 25],
                'RSI_PERIOD': [10, 14, 21],
                'RSI_OVERSOLD': [25, 30, 35],
                'RSI_OVERBOUGHT': [65, 70, 75],
                'STOP_LOSS_PERCENT': [2.0, 2.5, 3.0],
                'TAKE_PROFIT_PERCENT': [4.0, 5.0, 6.0]
            }
        
        # Для неизвестной стратегии возвращаем базовые параметры
        else:
            return {
                'STOP_LOSS_PERCENT': [2.0, 2.5, 3.0],
                'TAKE_PROFIT_PERCENT': [4.0, 5.0, 6.0],
                'MAX_HOLDING_DAYS': [5, 7, 10]
            }
    
    def _grid_search(self, strategy_name: str, symbol: str, 
                   parameter_ranges: Dict[str, List[Any]], 
                   start_date: datetime, end_date: datetime,
                   metric: str) -> Dict[str, Any]:
        """
        Оптимизация методом полного перебора (grid search)
        
        Args:
            strategy_name: Название стратегии
            symbol: Символ для оптимизации
            parameter_ranges: Диапазоны параметров
            start_date: Дата начала
            end_date: Дата окончания
            metric: Метрика для оптимизации
            
        Returns:
            dict: Результаты оптимизации
        """
        # Формируем все комбинации параметров
        param_names = list(parameter_ranges.keys())
        param_values = list(parameter_ranges.values())
        
        # Считаем общее количество комбинаций
        total_combinations = 1
        for values in param_values:
            total_combinations *= len(values)
        
        logger.info(f"Запуск grid search с {total_combinations} комбинациями параметров")
        
        # Результаты всех комбинаций
        all_results = []
        
        # Лучший результат
        best_metric_value = float('-inf')
        best_result = None
        best_params = None
        
        # Время начала оптимизации
        start_time = time.time()
        
        # Перебираем все комбинации параметров
        for i, combo in enumerate(product(*param_values)):
            # Формируем словарь параметров
            params = dict(zip(param_names, combo))
            
            # Создаем копию конфигурации
            config_copy = deepcopy(self.config)
            
            # Обновляем параметры
            for param_name, param_value in params.items():
                setattr(config_copy, param_name, param_value)
            
            # Создаем новый экземпляр BacktestEngine с обновленной конфигурацией
            backtest_engine = BacktestEngine(config_copy)
            
            # Запускаем бэктест
            result = backtest_engine.run_backtest(
                strategy_name=strategy_name,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            # Добавляем параметры к результату
            result['parameters'] = params
            
            # Добавляем в список всех результатов
            all_results.append(result)
            
            # Проверяем, является ли текущий результат лучшим
            if metric in result and (result[metric] > best_metric_value or best_metric_value == float('-inf')):
                best_metric_value = result[metric]
                best_result = result
                best_params = params
            
            # Выводим прогресс
            if (i + 1) % 10 == 0 or (i + 1) == total_combinations:
                elapsed_time = time.time() - start_time
                progress = (i + 1) / total_combinations * 100
                remaining_time = elapsed_time / (i + 1) * (total_combinations - i - 1)
                
                logger.info(f"Прогресс: {i+1}/{total_combinations} ({progress:.1f}%), "
                          f"Прошло: {elapsed_time:.1f} сек, Осталось: {remaining_time:.1f} сек")
        
        # Формируем результат оптимизации
        optimization_result = {
            'best_params': best_params,
            'best_performance': best_result,
            'all_results': all_results,
            'total_combinations': total_combinations,
            'optimization_time': time.time() - start_time
        }
        
        logger.info(f"Оптимизация завершена за {optimization_result['optimization_time']:.1f} сек")
        logger.info(f"Лучшие параметры: {best_params}")
        logger.info(f"Лучшее значение метрики {metric}: {best_metric_value}")
        
        return optimization_result
    
    def _parallel_grid_search(self, strategy_name: str, symbol: str, 
                           parameter_ranges: Dict[str, List[Any]],
                           start_date: datetime, end_date: datetime,
                           metric: str, max_workers: int) -> Dict[str, Any]:
        """
        Параллельная оптимизация методом полного перебора
        
        Args:
            strategy_name: Название стратегии
            symbol: Символ для оптимизации
            parameter_ranges: Диапазоны параметров
            start_date: Дата начала
            end_date: Дата окончания
            metric: Метрика для оптимизации
            max_workers: Максимальное количество рабочих процессов
            
        Returns:
            dict: Результаты оптимизации
        """
        # Формируем все комбинации параметров
        param_names = list(parameter_ranges.keys())
        param_values = list(parameter_ranges.values())
        
        combinations = list(product(*param_values))
        total_combinations = len(combinations)
        
        logger.info(f"Запуск parallel grid search с {total_combinations} комбинациями параметров "
                  f"и {max_workers} рабочими процессами")
        
        # Время начала оптимизации
        start_time = time.time()
        
        # Функция для выполнения бэктеста с заданными параметрами
        def run_backtest_with_params(combo):
            # Формируем словарь параметров
            params = dict(zip(param_names, combo))
            
            # Создаем копию конфигурации
            config_copy = deepcopy(self.config)
            
            # Обновляем параметры
            for param_name, param_value in params.items():
                setattr(config_copy, param_name, param_value)
            
            # Создаем новый экземпляр BacktestEngine с обновленной конфигурацией
            backtest_engine = BacktestEngine(config_copy)
            
            # Запускаем бэктест
            result = backtest_engine.run_backtest(
                strategy_name=strategy_name,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            # Добавляем параметры к результату
            result['parameters'] = params
            
            return result
        
        # Запускаем параллельное выполнение
        all_results = []
        completed = 0
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(run_backtest_with_params, combo): combo for combo in combinations}
            
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                
                try:
                    result = future.result()
                    all_results.append(result)
                    
                    # Выводим прогресс
                    if completed % 10 == 0 or completed == total_combinations:
                        elapsed_time = time.time() - start_time
                        progress = completed / total_combinations * 100
                        remaining_time = elapsed_time / completed * (total_combinations - completed)
                        
                        logger.info(f"Прогресс: {completed}/{total_combinations} ({progress:.1f}%), "
                                  f"Прошло: {elapsed_time:.1f} сек, Осталось: {remaining_time:.1f} сек")
                
                except Exception as e:
                    logger.error(f"Ошибка при выполнении бэктеста: {e}")
        
        # Находим лучший результат
        best_metric_value = float('-inf')
        best_result = None
        best_params = None
        
        for result in all_results:
            if metric in result and (result[metric] > best_metric_value or best_metric_value == float('-inf')):
                best_metric_value = result[metric]
                best_result = result
                best_params = result['parameters']
        
        # Формируем результат оптимизации
        optimization_result = {
            'best_params': best_params,
            'best_performance': best_result,
            'all_results': all_results,
            'total_combinations': total_combinations,
            'optimization_time': time.time() - start_time
        }
        
        logger.info(f"Параллельная оптимизация завершена за {optimization_result['optimization_time']:.1f} сек")
        logger.info(f"Лучшие параметры: {best_params}")
        logger.info(f"Лучшее значение метрики {metric}: {best_metric_value}")
        
        return optimization_result
    
    def walk_forward_optimization(self, strategy_name: str, symbol: str,
                                parameter_ranges: Dict[str, List[Any]],
                                start_date: datetime, end_date: datetime,
                                window_size: int = 90, step_size: int = 30,
                                metric: str = 'sharpe_ratio') -> Dict[str, Any]:
        """
        Оптимизация методом Walk-Forward (скользящее окно)
        
        Args:
            strategy_name: Название стратегии
            symbol: Символ для оптимизации
            parameter_ranges: Диапазоны параметров
            start_date: Дата начала
            end_date: Дата окончания
            window_size: Размер окна оптимизации в днях
            step_size: Шаг смещения окна в днях
            metric: Метрика для оптимизации
            
        Returns:
            dict: Результаты оптимизации
        """
        logger.info(f"Запуск Walk-Forward оптимизации для стратегии {strategy_name} на символе {symbol}")
        
        # Результаты для каждого окна
        window_results = []
        
        # Текущая дата начала окна
        current_start = start_date
        
        # Пока текущее окно не достигнет конечной даты
        while current_start + timedelta(days=window_size) <= end_date:
            # Определяем даты окна оптимизации и проверки
            window_end = current_start + timedelta(days=window_size)
            validation_end = min(window_end + timedelta(days=step_size), end_date)
            
            logger.info(f"Оптимизация для окна {current_start.date()} - {window_end.date()}, "
                      f"проверка {window_end.date()} - {validation_end.date()}")
            
            # Запускаем оптимизацию для текущего окна
            optimization_result = self._grid_search(
                strategy_name=strategy_name,
                symbol=symbol,
                parameter_ranges=parameter_ranges,
                start_date=current_start,
                end_date=window_end,
                metric=metric
            )
            
            # Получаем лучшие параметры
            best_params = optimization_result['best_params']
            
            # Проверяем лучшие параметры на периоде проверки
            config_copy = deepcopy(self.config)
            
            # Обновляем параметры
            for param_name, param_value in best_params.items():
                setattr(config_copy, param_name, param_value)
            
            # Создаем новый экземпляр BacktestEngine с обновленной конфигурацией
            backtest_engine = BacktestEngine(config_copy)
            
            # Запускаем бэктест на периоде проверки
            validation_result = backtest_engine.run_backtest(
                strategy_name=strategy_name,
                symbol=symbol,
                start_date=window_end,
                end_date=validation_end
            )
            
            # Сохраняем результаты для текущего окна
            window_result = {
                'optimization_window': {
                    'start_date': current_start,
                    'end_date': window_end
                },
                'validation_window': {
                    'start_date': window_end,
                    'end_date': validation_end
                },
                'best_params': best_params,
                'optimization_performance': optimization_result['best_performance'],
                'validation_performance': validation_result
            }
            
            window_results.append(window_result)
            
            # Смещаем окно
            current_start += timedelta(days=step_size)
        
        # Анализируем результаты для всех окон
        validation_metrics = [window['validation_performance'].get(metric, float('-inf')) for window in window_results]
        
        # Находим окно с лучшими результатами на валидации
        best_window_index = np.argmax(validation_metrics)
        best_window = window_results[best_window_index]
        
        # Формируем общий результат
        wfo_result = {
            'window_results': window_results,
            'best_window': best_window,
            'best_params': best_window['best_params'],
            'optimization_time': sum(window['optimization_performance'].get('optimization_time', 0) for window in window_results),
            'stability_score': self._calculate_stability_score(window_results, metric)
        }
        
        logger.info(f"Walk-Forward оптимизация завершена")
        logger.info(f"Лучшие параметры из окна {best_window['optimization_window']['start_date'].date()} - "
                  f"{best_window['optimization_window']['end_date'].date()}: {best_window['best_params']}")
        
        return wfo_result
    
    def _calculate_stability_score(self, window_results: List[Dict[str, Any]], metric: str) -> float:
        """
        Расчет показателя стабильности параметров по окнам
        
        Args:
            window_results: Результаты оптимизации по окнам
            metric: Метрика для оценки
            
        Returns:
            float: Показатель стабильности (от 0 до 1)
        """
        # Если меньше 2 окон, стабильность не имеет смысла
        if len(window_results) < 2:
            return 1.0
        
        # Соберем все уникальные параметры
        all_params = set()
        for window in window_results:
            for param in window['best_params'].keys():
                all_params.add(param)
        
        # Для каждого параметра вычислим коэффициент вариации
        param_stability = {}
        
        for param in all_params:
            values = [window['best_params'].get(param, None) for window in window_results]
            
            # Удаляем None значения
            values = [v for v in values if v is not None]
            
            # Если меньше 2 значений, считаем параметр стабильным
            if len(values) < 2:
                param_stability[param] = 1.0
                continue
            
            # Вычисляем коэффициент вариации
            mean = np.mean(values)
            std = np.std(values)
            
            # Избегаем деления на ноль
            if mean == 0:
                cv = 0
            else:
                cv = std / mean
            
            # Преобразуем в показатель стабильности (от 0 до 1)
            # Чем меньше коэффициент вариации, тем стабильнее параметр
            param_stability[param] = max(0, 1 - min(cv, 1))
        
        # Общая стабильность - среднее значение стабильности всех параметров
        overall_stability = np.mean(list(param_stability.values()))
        
        return overall_stability