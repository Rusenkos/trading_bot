"""
Точка входа для запуска торгового бота.

Этот модуль предоставляет CLI-интерфейс для управления ботом.
"""
import os
import sys
import argparse
import logging
import time
from datetime import datetime
from dotenv import load_dotenv

from bot import TradingBot
from config.config import Config
from utils.logging import setup_logging


logger = logging.getLogger(__name__)

def parse_arguments():
    """
    Разбор аргументов командной строки
    
    Returns:
        argparse.Namespace: Объект с аргументами
    """
    parser = argparse.ArgumentParser(description='MOEX Trading Bot через API Тинькофф')
    
    # Общие аргументы
    parser.add_argument('--config', type=str, help='Путь к файлу конфигурации')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default='INFO', help='Уровень логирования')
    
    # Подкоманды
    subparsers = parser.add_subparsers(dest='command', help='Команды')
    
    # Команда start
    start_parser = subparsers.add_parser('start', help='Запуск бота')
    start_parser.add_argument('--daemon', action='store_true', help='Запуск в фоновом режиме')
    
    # Команда stop
    stop_parser = subparsers.add_parser('stop', help='Остановка бота')
    
    # Команда status
    status_parser = subparsers.add_parser('status', help='Проверка статуса бота')
    
    # Команда report
    report_parser = subparsers.add_parser('report', help='Создание отчета о портфеле')
    
    # Команда backtest
    backtest_parser = subparsers.add_parser('backtest', help='Запуск бэктестинга')
    backtest_parser.add_argument('--strategy', type=str, required=True, 
                              choices=['trend', 'reversal', 'combined'],
                              help='Стратегия для бэктеста')
    backtest_parser.add_argument('--symbol', type=str, required=True, 
                              help='Символ для бэктеста')
    backtest_parser.add_argument('--start-date', type=str, required=True, 
                              help='Дата начала бэктеста (YYYY-MM-DD)')
    backtest_parser.add_argument('--end-date', type=str, required=False, 
                              help='Дата окончания бэктеста (YYYY-MM-DD)')
    
    # Команда optimize
    optimize_parser = subparsers.add_parser('optimize', help='Оптимизация параметров стратегии')
    optimize_parser.add_argument('--strategy', type=str, required=True, 
                              choices=['trend', 'reversal', 'combined'],
                              help='Стратегия для оптимизации')
    optimize_parser.add_argument('--symbol', type=str, required=True, 
                               help='Символ для оптимизации')
    
    return parser.parse_args()

def main():
    """
    Основная функция запуска
    """
    # Загружаем переменные окружения из .env файла
    load_dotenv()
    
    # Разбираем аргументы командной строки
    args = parse_arguments()
    
    # Настраиваем логирование
    setup_logging(log_level=args.log_level)
    
    # Проверяем переменные окружения
    if not os.environ.get('TINKOFF_TOKEN'):
        logger.error("Не указан токен API Тинькофф. Укажите TINKOFF_TOKEN в .env файле")
        sys.exit(1)
    
    # Загружаем конфигурацию
    config = Config.load(args.config)
    
    # Обрабатываем команды
    if args.command == 'start':
        start_bot(config, args.daemon)
    elif args.command == 'stop':
        stop_bot()
    elif args.command == 'status':
        check_status()
    elif args.command == 'report':
        generate_report(config)
    elif args.command == 'backtest':
        run_backtest(config, args)
    elif args.command == 'optimize':
        run_optimization(config, args)
    else:
        # Если команда не указана, выводим справку
        logger.error("Не указана команда. Используйте --help для получения справки")
        sys.exit(1)

def start_bot(config, daemon=False):
    """
    Запуск бота
    
    Args:
        config: Объект конфигурации
        daemon: Флаг запуска в фоновом режиме
    """
    try:
        logger.info("Запуск торгового бота...")
        
        # Создаем экземпляр бота
        bot = TradingBot(config)
        
        if daemon:
            # Запуск в фоновом режиме
            logger.info("Запуск в фоновом режиме")
            
            # Можно использовать модуль daemon для полноценного демона,
            # но для простоты просто запускаем в отдельном потоке
            import threading
            bot_thread = threading.Thread(target=bot.start)
            bot_thread.daemon = True
            bot_thread.start()
            logger.info("Бот запущен в фоновом режиме")
            
            # Записываем PID в файл для возможности остановки
            with open('bot.pid', 'w') as f:
                f.write(str(os.getpid()))
            
            # Простой цикл для поддержания работы основного потока
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Получен сигнал остановки")
                bot.stop()
        else:
            # Обычный запуск в текущем процессе
            logger.info("Запуск в интерактивном режиме")
            
            # Записываем PID в файл для возможности остановки
            with open('bot.pid', 'w') as f:
                f.write(str(os.getpid()))
            
            # Запускаем бота
            bot.start()
    
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
        if 'bot' in locals():
            bot.stop()
    
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        sys.exit(1)

def stop_bot():
    """
    Остановка бота
    """
    try:
        # Читаем PID из файла
        if os.path.exists('bot.pid'):
            with open('bot.pid', 'r') as f:
                pid = int(f.read().strip())
            
            logger.info(f"Остановка бота (PID: {pid})...")
            
            # Отправляем сигнал SIGTERM для корректного завершения
            import signal
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info("Сигнал остановки отправлен")
                
                # Удаляем файл PID
                os.remove('bot.pid')
            except ProcessLookupError:
                logger.warning(f"Процесс с PID {pid} не найден")
                os.remove('bot.pid')
        else:
            logger.error("Файл PID не найден. Возможно, бот не запущен")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Ошибка при остановке бота: {e}")
        sys.exit(1)

def check_status():
    """
    Проверка статуса бота
    """
    try:
        # Проверяем наличие файла PID
        if os.path.exists('bot.pid'):
            with open('bot.pid', 'r') as f:
                pid = int(f.read().strip())
            
            # Проверяем, существует ли процесс
            try:
                os.kill(pid, 0)  # Сигнал 0 проверяет существование процесса
                print(f"Бот запущен (PID: {pid})")
                
                # Можно добавить дополнительную информацию из файла состояния
                from utils.state import StateManager
                state_manager = StateManager()
                state = state_manager.load_state()
                
                if state:
                    print(f"Последнее обновление: {state.get('last_update', 'N/A')}")
                    print(f"Статус: {'Работает' if state.get('running', False) else 'Остановлен'}")
                    
                    # Отображаем открытые позиции
                    positions = state.get('positions', {})
                    if positions:
                        print("\nОткрытые позиции:")
                        for symbol, position in positions.items():
                            print(f"  {symbol}: {position.get('quantity')} @ {position.get('entry_price')}")
                    else:
                        print("\nНет открытых позиций")
            
            except ProcessLookupError:
                print(f"Процесс с PID {pid} не найден. Бот не запущен или был завершен некорректно.")
                os.remove('bot.pid')
        else:
            print("Бот не запущен")
    
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса: {e}")
        sys.exit(1)

def generate_report(config):
    """
    Генерация отчета о портфеле
    
    Args:
        config: Объект конфигурации
    """
    try:
        # Создаем временный экземпляр бота для доступа к данным
        bot = TradingBot(config)
        
        # Подключаемся к API
        if not bot.connect():
            logger.error("Не удалось подключиться к API для получения отчета")
            sys.exit(1)
        
        # Получаем статус портфеля
        portfolio_status = bot.get_portfolio_status()
        
        # Выводим отчет
        print("\n============ ОТЧЕТ О ПОРТФЕЛЕ ============")
        print(f"Баланс: {portfolio_status['balance']:.2f} руб.")
        
        # Выводим открытые позиции
        positions = portfolio_status['positions']
        if positions:
            print("\nОткрытые позиции:")
            for symbol, position in positions.items():
                entry_price = position.get('entry_price', 0)
                quantity = position.get('quantity', 0)
                entry_time = position.get('entry_time', '')
                
                # Получаем текущую цену
                current_price = bot.executor.get_current_price(symbol) or 0
                
                # Рассчитываем P&L
                pnl_percent = ((current_price / entry_price) - 1) * 100 if entry_price > 0 else 0
                pnl_absolute = (current_price - entry_price) * quantity
                
                print(f"  {symbol}: {quantity} @ {entry_price:.2f} "
                     f"({entry_time}) | Текущая: {current_price:.2f} | "
                     f"P&L: {pnl_percent:.2f}% ({pnl_absolute:.2f} руб.)")
        else:
            print("\nНет открытых позиций")
        
        # Выводим метрики
        metrics = portfolio_status['metrics']
        print("\nМетрики:")
        print(f"  Всего сделок: {metrics.get('total_positions', 0)}")
        print(f"  Закрытых сделок: {metrics.get('closed_positions', 0)}")
        print(f"  Общая прибыль: {metrics.get('total_pnl_percent', 0):.2f}%")
        print(f"  Абсолютная прибыль: {metrics.get('total_pnl_absolute', 0):.2f} руб.")
        print(f"  Процент успешных: {metrics.get('win_rate', 0):.2f}%")
        print(f"  Средняя прибыль: {metrics.get('average_win', 0):.2f}%")
        print(f"  Средний убыток: {metrics.get('average_loss', 0):.2f}%")
        print(f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        
        print("==========================================\n")
        
        # Отключаемся от API
        bot.disconnect()
    
    except Exception as e:
        logger.error(f"Ошибка при генерации отчета: {e}")
        sys.exit(1)

def run_backtest(config, args):
    """
    Запуск бэктестинга
    
    Args:
        config: Объект конфигурации
        args: Аргументы командной строки
    """
    try:
        logger.info(f"Запуск бэктеста для стратегии {args.strategy} на символе {args.symbol}")
        
        # Импортируем движок бэктестинга
        try:
            from backtest.engine import BacktestEngine
        except ImportError:
            logger.error("Модуль бэктестинга не найден")
            print("Модуль бэктестинга еще не реализован. Пожалуйста, сначала реализуйте модуль backtest/engine.py")
            sys.exit(1)
        
        # Создаем экземпляр движка бэктестинга
        engine = BacktestEngine(config)
        
        # Запускаем бэктест
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else datetime.now()
        
        results = engine.run_backtest(
            strategy_name=args.strategy,
            symbol=args.symbol,
            start_date=start_date,
            end_date=end_date
        )
        
        # Выводим результаты
        print("\n============ РЕЗУЛЬТАТЫ БЭКТЕСТА ============")
        print(f"Стратегия: {args.strategy}")
        print(f"Символ: {args.symbol}")
        print(f"Период: {args.start_date} - {args.end_date or 'сейчас'}")
        print(f"Начальный капитал: {results['initial_capital']:.2f} руб.")
        print(f"Конечный капитал: {results['final_capital']:.2f} руб.")
        print(f"Доходность: {results['total_return']:.2f}%")
        print(f"Годовая доходность: {results['annual_return']:.2f}%")
        print(f"Максимальная просадка: {results['max_drawdown']:.2f}%")
        print(f"Коэффициент Шарпа: {results['sharpe_ratio']:.2f}")
        print(f"Всего сделок: {results['total_trades']}")
        print(f"Успешных сделок: {results['winning_trades']} ({results['win_rate']:.2f}%)")
        print("=============================================\n")
    
    except Exception as e:
        logger.error(f"Ошибка при запуске бэктеста: {e}")
        sys.exit(1)

def run_optimization(config, args):
    """
    Запуск оптимизации параметров стратегии
    
    Args:
        config: Объект конфигурации
        args: Аргументы командной строки
    """
    try:
        logger.info(f"Запуск оптимизации для стратегии {args.strategy} на символе {args.symbol}")
        
        # Импортируем оптимизатор
        try:
            from backtest.optimizer import StrategyOptimizer
        except ImportError:
            logger.error("Модуль оптимизации не найден")
            print("Модуль оптимизации еще не реализован. Пожалуйста, сначала реализуйте модуль backtest/optimizer.py")
            sys.exit(1)
        
        # Создаем экземпляр оптимизатора
        optimizer = StrategyOptimizer(config)
        
        # Запускаем оптимизацию
        results = optimizer.optimize(
            strategy_name=args.strategy,
            symbol=args.symbol
        )
        
        # Выводим результаты
        print("\n============ РЕЗУЛЬТАТЫ ОПТИМИЗАЦИИ ============")
        print(f"Стратегия: {args.strategy}")
        print(f"Символ: {args.symbol}")
        print("\nЛучшие параметры:")
        for param, value in results['best_params'].items():
            print(f"  {param}: {value}")
        
        print("\nПроизводительность с оптимальными параметрами:")
        print(f"  Доходность: {results['best_performance']['total_return']:.2f}%")
        print(f"  Максимальная просадка: {results['best_performance']['max_drawdown']:.2f}%")
        print(f"  Коэффициент Шарпа: {results['best_performance']['sharpe_ratio']:.2f}")
        print(f"  Успешных сделок: {results['best_performance']['win_rate']:.2f}%")
        print("==================================================\n")
    
    except Exception as e:
        logger.error(f"Ошибка при запуске оптимизации: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()