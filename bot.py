### bot.py ###
import logging
import time
import sys
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pandas as pd

# Импорт для Tinkoff API v0.2.0b111
from tinkoff.invest import Client, CandleInterval

from config.config import Config
from data.market_data import MarketDataProvider
from data.indicators import TechnicalIndicators
from data.patterns import CandlePatterns
from execution.executor import TradingExecutor
from execution.risk_manager import RiskManager
from execution.position_manager import PositionManager
from strategies.combined import CombinedStrategy
from strategies.trend import TrendStrategy
from strategies.reversal import ReversalStrategy
from utils.notifications import TelegramNotifier
from utils.state import StateManager

logger = logging.getLogger(__name__)

class TradingBot:
    """
    Основной класс бота для алгоритмической торговли акциями MOEX через API Тинькофф.
    
    Отвечает за:
    - Координацию работы всех модулей
    - Управление циклом работы бота
    - Обработку событий и ошибок
    """
    
    def __init__(self, config_path=None):
        """
        Инициализация бота
        
        Args:
            config_path: Путь к файлу конфигурации
        """
        # Загружаем конфигурацию
        self.config = Config.load(config_path)
        
        # Настраиваем логирование
        self._setup_logging()
        
        # Инициализируем состояние
        self.state_manager = StateManager("bot_state.json")
        self.state_manager.load_state()
        
        # Флаг для управления работой бота
        self.running = False
        
        # Инициализируем клиент API
        self.client = None
        
        # Инициализируем провайдера данных
        self.market_data = None
        
        # Инициализируем исполнителя торговых операций
        self.executor = None
        
        # Инициализируем стратегии
        self.strategies = {}
        
        # Инициализируем уведомления
        if self.config.TELEGRAM_TOKEN and self.config.TELEGRAM_CHAT_ID:
            self.notifier = TelegramNotifier(self.config.TELEGRAM_TOKEN, self.config.TELEGRAM_CHAT_ID)
        else:
            self.notifier = None
        
        # Регистрируем обработчик сигналов для корректного завершения
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)
    
    def _setup_logging(self):
        """
        Настройка логирования
        """
        # Создаем директорию для логов, если её нет
        import os
        log_dir = os.path.dirname(self.config.LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Настройка логирования
        logging.basicConfig(
            level=getattr(logging, self.config.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logger.info("====== Запуск торгового бота ======")
        logger.info(f"Конфигурация загружена из {self.config}")
    
    def initialize(self):
        """
        Инициализация компонентов бота
        
        Returns:
            bool: True, если инициализация успешна
        """
        logger.info("Инициализация компонентов бота...")
        
        try:
            # Создаем клиент API
            self.client = Client(self.config.TINKOFF_TOKEN)
            
            # Инициализируем провайдера данных
            self.market_data = MarketDataProvider(self.config.TINKOFF_TOKEN, self.config)
            if not self.market_data.connect():
                logger.error("Не удалось подключиться к API для получения данных")
                return False
            
            # Инициализируем менеджер позиций
            self.position_manager = PositionManager(self.config)
            self.position_manager.load_state()
            
            # Инициализируем риск-менеджер
            self.risk_manager = RiskManager(self.config)
            
            # Инициализируем исполнителя торговых операций
            self.executor = TradingExecutor(self.client, self.config, self.risk_manager, self.position_manager)
            if not self.executor.update_account_info():
                logger.error("Не удалось получить информацию о счете")
                return False
            
            # Инициализируем стратегии
            self._init_strategies()
            
            # Загружаем начальные данные для всех инструментов
            self._load_initial_data()
            
            logger.info("Инициализация компонентов бота завершена успешно")
            
            # Отправляем уведомление о запуске
            if self.notifier:
                self.notifier.send_message("🚀 Торговый бот запущен")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации бота: {e}", exc_info=True)
            return False
    
    def _init_strategies(self):
        """
        Инициализация торговых стратегий
        """
        # Определяем, какие стратегии нужно активировать
        active_strategies = self.config.ACTIVE_STRATEGIES
        
        # Инициализируем каждую стратегию
        if "trend" in active_strategies:
            self.strategies["trend"] = TrendStrategy(self.config)
            logger.info("Трендовая стратегия инициализирована")
        
        if "reversal" in active_strategies:
            self.strategies["reversal"] = ReversalStrategy(self.config)
            logger.info("Контртрендовая стратегия инициализирована")
        
        # Если активированы обе стратегии, добавляем комбинированную
        if "trend" in active_strategies and "reversal" in active_strategies:
            self.strategies["combined"] = CombinedStrategy(self.config)
            logger.info("Комбинированная стратегия инициализирована")
        
        logger.info(f"Активировано стратегий: {len(self.strategies)}")
    
    def _load_initial_data(self):
        """
        Загрузка начальных данных для всех инструментов
        """
        logger.info("Загрузка исторических данных для инструментов...")
        
        # Загружаем данные для каждого символа
        for symbol in self.config.SYMBOLS:
            try:
                df = self.market_data.get_historical_data(
                    symbol, 
                    self.config.TIMEFRAME, 
                    days_back=60  # Загружаем данные за 60 дней для анализа
                )
                
                if df is not None and not df.empty:
                    logger.info(f"Загружено {len(df)} свечей для {symbol}")
                else:
                    logger.warning(f"Не удалось загрузить данные для {symbol}")
                    
            except Exception as e:
                logger.error(f"Ошибка при загрузке данных для {symbol}: {e}")
    
    def run(self):
        """
        Основной цикл работы бота
        """
        if not self.initialize():
            logger.error("Не удалось инициализировать бота. Завершение работы.")
            return
        
        self.running = True
        self.state_manager.set_running(True)
        
        logger.info("Бот запущен и готов к работе")
        
        # Счетчики для определения периодичности выполнения задач
        last_data_update = datetime.now()
        last_stop_loss_check = datetime.now()
        last_status_report = datetime.now()
        
        try:
            while self.running:
                current_time = datetime.now()
                
                # Проверяем, открыт ли рынок
                market_open = self.market_data.is_market_open()
                
                # Если рынок закрыт, проверяем реже
                if not market_open:
                    time.sleep(60)  # Засыпаем на минуту
                    continue
                
                # Проверка стоп-лоссов и трейлинг-стопов (каждые N секунд)
                if (current_time - last_stop_loss_check).total_seconds() >= self.config.CHECK_STOP_LOSS_INTERVAL:
                    self.executor.check_stop_loss_and_trailing()
                    last_stop_loss_check = current_time
                
                # Обновление данных и проверка сигналов (каждые N секунд)
                if (current_time - last_data_update).total_seconds() >= self.config.UPDATE_INTERVAL:
                    self._update_data_and_check_signals()
                    last_data_update = current_time
                
                # Отчет о статусе (каждый час)
                if (current_time - last_status_report).total_seconds() >= 3600:
                    self._send_status_report()
                    last_status_report = current_time
                
                # Засыпаем на короткое время
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Получен сигнал прерывания. Завершение работы.")
        except Exception as e:
            logger.error(f"Критическая ошибка в основном цикле бота: {e}", exc_info=True)
            if self.notifier:
                self.notifier.send_error_notification(f"Критическая ошибка: {e}")
        finally:
            self._shutdown()
    
    def _update_data_and_check_signals(self):
        """
        Обновление данных и проверка торговых сигналов
        """
        logger.info("Обновление данных и проверка сигналов")
        
        # Обновляем информацию о портфеле
        self.executor.update_account_info()
        
        # Проходим по всем инструментам
        for symbol in self.config.SYMBOLS:
            try:
                # Обновляем данные
                df = self.market_data.update_data(symbol, self.config.TIMEFRAME)
                
                if df is None or df.empty:
                    logger.warning(f"Нет данных для {symbol}, пропускаем")
                    continue
                
                # Рассчитываем индикаторы
                df = TechnicalIndicators.calculate_all_indicators(df, self.config)
                
                # Добавляем информацию о свечных паттернах
                df = CandlePatterns.identify_patterns(df)
                
                # Проверяем сигналы для открытия позиции
                self._check_buy_signals(symbol, df)
                
                # Если есть открытая позиция, проверяем сигналы на закрытие
                if self.position_manager.has_position(symbol):
                    position = self.position_manager.get_position(symbol)
                    self._check_sell_signals(symbol, df, position)
                
            except Exception as e:
                logger.error(f"Ошибка при обработке {symbol}: {e}", exc_info=True)
    
    def _check_buy_signals(self, symbol: str, data: pd.DataFrame):
        """
        Проверка сигналов на покупку для всех стратегий
        
        Args:
            symbol: Тикер инструмента
            data: DataFrame с данными и индикаторами
        """
        # Проверяем, если у нас уже есть позиция по этому инструменту
        if self.position_manager.has_position(symbol):
            return
        
        # Проходим по всем стратегиям и проверяем сигналы
        buy_signals = []
        
        for strategy_name, strategy in self.strategies.items():
            signal, details = strategy.check_buy_signals(data)
            
            if signal:
                buy_signals.append(details)
                logger.info(f"Получен сигнал на покупку {symbol} от стратегии {strategy_name}: {details}")
        
        if buy_signals:
            # Если получили несколько сигналов, выбираем сильнейший
            if len(buy_signals) > 1:
                buy_signals.sort(key=lambda x: x.get('strength', 0), reverse=True)
            
            # Выбираем лучший сигнал
            best_signal = buy_signals[0]
            
            # Отправляем уведомление о сигнале
            if self.notifier:
                self.notifier.send_signal_notification(symbol, best_signal)
            
            # Исполняем сигнал
            self.executor.execute_trade_signal(symbol, best_signal)
    
    def _check_sell_signals(self, symbol: str, data: pd.DataFrame, position: Dict[str, Any]):
        """
        Проверка сигналов на продажу для всех стратегий
        
        Args:
            symbol: Тикер инструмента
            data: DataFrame с данными и индикаторами
            position: Информация о текущей позиции
        """
        # Проходим по всем стратегиям и проверяем сигналы
        sell_signals = []
        
        for strategy_name, strategy in self.strategies.items():
            signal, details = strategy.check_sell_signals(data, position)
            
            if signal:
                sell_signals.append(details)
                logger.info(f"Получен сигнал на продажу {symbol} от стратегии {strategy_name}: {details}")
        
        if sell_signals:
            # Если получили несколько сигналов, выбираем сильнейший
            if len(sell_signals) > 1:
                sell_signals.sort(key=lambda x: x.get('strength', 0), reverse=True)
            
            # Выбираем лучший сигнал
            best_signal = sell_signals[0]
            
            # Отправляем уведомление о сигнале
            if self.notifier:
                self.notifier.send_signal_notification(symbol, best_signal)
            
            # Исполняем сигнал
            self.executor.execute_trade_signal(symbol, best_signal)
    
    def _send_status_report(self):
        """
        Отправка отчета о состоянии бота
        """
        # Получаем метрики портфеля
        portfolio_metrics = self.position_manager.calculate_portfolio_metrics()
        
        # Формируем отчет
        logger.info(f"Статус бота: Активен. Открытых позиций: {portfolio_metrics['open_positions']}")
        
        # Отправляем отчет через Telegram
        if self.notifier:
            self.notifier.send_portfolio_report(portfolio_metrics)
    
    def _handle_exit(self, signum, frame):
        """
        Обработчик сигналов завершения для корректного выхода
        """
        logger.info(f"Получен сигнал {signum}. Начинаем корректное завершение...")
        self.running = False
    
    def _shutdown(self):
        """
        Корректное завершение работы бота
        """
        logger.info("Завершение работы бота...")
        
        # Сохраняем состояние позиций
        self.position_manager.save_state()
        
        # Сохраняем общее состояние
        self.state_manager.set_running(False)
        self.state_manager.save_state({
            'last_shutdown': datetime.now().isoformat(),
            'portfolio': self.executor.portfolio if self.executor else {},
            'balance': self.executor.balance if self.executor else 0
        })
        
        # Закрываем соединения
        if self.market_data:
            self.market_data.disconnect()
        
        if self.client:
            self.client.close()
        
        # Отправляем уведомление о завершении
        if self.notifier:
            self.notifier.send_message("🛑 Торговый бот остановлен")
        
        logger.info("Бот остановлен")
    
    def stop(self):
        """
        Остановка бота извне
        """
        logger.info("Получена команда остановки бота")
        self.running = False


if __name__ == "__main__":
    # Запуск бота
    bot = TradingBot()
    bot.run()