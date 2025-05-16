import logging
import time
import sys
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pandas as pd

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
    """

    def __init__(self, config_path=None):
        self.config = Config.load(config_path)
        self._setup_logging()
        self.state_manager = StateManager("bot_state.json")
        self.state_manager.load_state()
        self.running = False

        self.market_data = None
        self.executor = None
        self.position_manager = None
        self.risk_manager = None
        self.strategies = {}

        if self.config.TELEGRAM_TOKEN and self.config.TELEGRAM_CHAT_ID:
            self.notifier = TelegramNotifier(self.config.TELEGRAM_TOKEN, self.config.TELEGRAM_CHAT_ID)
        else:
            self.notifier = None

        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _setup_logging(self):
        import os
        log_dir = os.path.dirname(self.config.LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
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
        logger.info("Инициализация компонентов бота...")
        try:
            print(f"TINKOFF TOKEN = {repr(token)}")
            # Провайдер рыночных данных
            self.market_data = MarketDataProvider(self.config.TINKOFF_TOKEN, self.config)
            # Менеджер позиций
            self.position_manager = PositionManager(self.config)
            self.position_manager.load_state()
            # Риск-менеджер
            self.risk_manager = RiskManager(self.config)
            # Исполнитель торговых операций
            self.executor = TradingExecutor(self.config.TINKOFF_TOKEN, self.config, self.risk_manager, self.position_manager)
            if not self.executor.update_account_info():
                logger.error("Не удалось получить информацию о счете")
                return False
            # Стратегии
            self._init_strategies()
            # Загрузка исторических данных
            self._load_initial_data()
            logger.info("Инициализация компонентов бота завершена успешно")
            if self.notifier:
                self.notifier.send_message("🚀 Торговый бот запущен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при инициализации бота: {e}", exc_info=True)
            return False

    def _init_strategies(self):
        active_strategies = self.config.ACTIVE_STRATEGIES
        if "trend" in active_strategies:
            self.strategies["trend"] = TrendStrategy(self.config)
            logger.info("Трендовая стратегия инициализирована")
        if "reversal" in active_strategies:
            self.strategies["reversal"] = ReversalStrategy(self.config)
            logger.info("Контртрендовая стратегия инициализирована")
        if "trend" in active_strategies and "reversal" in active_strategies:
            self.strategies["combined"] = CombinedStrategy(self.config)
            logger.info("Комбинированная стратегия инициализирована")
        logger.info(f"Активировано стратегий: {len(self.strategies)}")

    def _load_initial_data(self):
        logger.info("Загрузка исторических данных для инструментов...")
        for symbol in self.config.SYMBOLS:
            try:
                df = self.market_data.get_historical_data(
                    symbol,
                    self.config.TIMEFRAME,
                    days_back=60
                )
                if df is not None and not df.empty:
                    logger.info(f"Загружено {len(df)} свечей для {symbol}")
                else:
                    logger.warning(f"Не удалось загрузить данные для {symbol}")
            except Exception as e:
                logger.error(f"Ошибка при загрузке данных для {symbol}: {e}")

    def run(self):
        if not self.initialize():
            logger.error("Не удалось инициализировать бота. Завершение работы.")
            return
        self.running = True
        self.state_manager.set_running(True)
        logger.info("Бот запущен и готов к работе")

        last_data_update = datetime.now()
        last_stop_loss_check = datetime.now()
        last_status_report = datetime.now()

        try:
            while self.running:
                current_time = datetime.now()
                # Проверяем открыт ли рынок
                market_open = self.market_data.is_market_open()
                if not market_open:
                    time.sleep(60)
                    continue
                # Проверка стоп-лоссов и трейлинг-стопов
                if (current_time - last_stop_loss_check).total_seconds() >= self.config.CHECK_STOP_LOSS_INTERVAL:
                    self.executor.check_stop_loss_and_trailing()
                    last_stop_loss_check = current_time
                # Обновление данных и проверка сигналов
                if (current_time - last_data_update).total_seconds() >= self.config.UPDATE_INTERVAL:
                    self._update_data_and_check_signals()
                    last_data_update = current_time
                # Отчет о статусе (раз в час)
                if (current_time - last_status_report).total_seconds() >= 3600:
                    self._send_status_report()
                    last_status_report = current_time
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
        logger.info("Обновление данных и проверка сигналов")
        self.executor.update_account_info()
        for symbol in self.config.SYMBOLS:
            try:
                df = self.market_data.update_data(symbol, self.config.TIMEFRAME)
                if df is None or df.empty:
                    logger.warning(f"Нет данных для {symbol}, пропускаем")
                    continue
                df = TechnicalIndicators.calculate_all_indicators(df, self.config)
                df = CandlePatterns.identify_patterns(df)
                self._check_buy_signals(symbol, df)
                if self.position_manager.has_position(symbol):
                    position = self.position_manager.get_position(symbol)
                    self._check_sell_signals(symbol, df, position)
            except Exception as e:
                logger.error(f"Ошибка при обработке {symbol}: {e}", exc_info=True)

    def _check_buy_signals(self, symbol: str, data: pd.DataFrame):
        if self.position_manager.has_position(symbol):
            return
        buy_signals = []
        for strategy_name, strategy in self.strategies.items():
            signal, details = strategy.check_buy_signals(data)
            if signal:
                buy_signals.append(details)
                logger.info(f"Получен сигнал на покупку {symbol} от стратегии {strategy_name}: {details}")
        if buy_signals:
            if len(buy_signals) > 1:
                buy_signals.sort(key=lambda x: x.get('strength', 0), reverse=True)
            best_signal = buy_signals[0]
            if self.notifier:
                self.notifier.send_signal_notification(symbol, best_signal)
            self.executor.execute_trade_signal(symbol, best_signal)

    def _check_sell_signals(self, symbol: str, data: pd.DataFrame, position: Dict[str, Any]):
        sell_signals = []
        for strategy_name, strategy in self.strategies.items():
            signal, details = strategy.check_sell_signals(data, position)
            if signal:
                sell_signals.append(details)
                logger.info(f"Получен сигнал на продажу {symbol} от стратегии {strategy_name}: {details}")
        if sell_signals:
            if len(sell_signals) > 1:
                sell_signals.sort(key=lambda x: x.get('strength', 0), reverse=True)
            best_signal = sell_signals[0]
            if self.notifier:
                self.notifier.send_signal_notification(symbol, best_signal)
            self.executor.execute_trade_signal(symbol, best_signal)

    def _send_status_report(self):
        portfolio_metrics = self.position_manager.calculate_portfolio_metrics()
        logger.info(f"Статус бота: Активен. Открытых позиций: {portfolio_metrics['open_positions']}")
        if self.notifier:
            self.notifier.send_portfolio_report(portfolio_metrics)

    def _handle_exit(self, signum, frame):
        logger.info(f"Получен сигнал {signum}. Начинаем корректное завершение...")
        self.running = False

    def _shutdown(self):
        logger.info("Завершение работы бота...")
        self.position_manager.save_state()
        self.state_manager.set_running(False)
        self.state_manager.save_state({
            'last_shutdown': datetime.now().isoformat(),
            'portfolio': self.executor.portfolio if self.executor else {},
            'balance': self.executor.balance if self.executor else 0
        })
        if self.notifier:
            self.notifier.send_message("🛑 Торговый бот остановлен")
        logger.info("Бот остановлен")

    def stop(self):
        logger.info("Получена команда остановки бота")
        self.running = False

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()