### utils/logging.py ###
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_logging(config=None, log_to_console=True, log_level=None, log_file=None):
    """
    Настройка системы логирования
    
    Args:
        config: Объект конфигурации
        log_to_console: Флаг вывода логов в консоль
        log_level: Уровень логирования (перезаписывает значение из конфигурации)
        log_file: Путь к файлу лога (перезаписывает значение из конфигурации)
    """
    # Определяем уровень логирования
    if log_level:
        level = getattr(logging, log_level.upper())
    elif config and hasattr(config, 'LOG_LEVEL'):
        level = getattr(logging, config.LOG_LEVEL.upper())
    else:
        level = logging.INFO
    
    # Определяем путь к файлу лога
    log_file_path = log_file
    if not log_file_path and config and hasattr(config, 'LOG_FILE'):
        log_file_path = config.LOG_FILE
    
    # Создаем базовый форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Очищаем обработчики, если они были добавлены ранее
    root_logger.handlers = []
    
    # Добавляем обработчик для консоли
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)
    
    # Добавляем обработчик для файла
    if log_file_path:
        # Создаем директорию для логов, если её нет
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Создаем обработчик с ротацией файлов
        # Размер файла - до 5 МБ, хранение до 5 файлов
        file_handler = RotatingFileHandler(
            log_file_path, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    
    # Создание отдельного файла для важных событий (WARNING и выше)
    if log_file_path:
        # Формируем имя файла для важных событий
        base_path, ext = os.path.splitext(log_file_path)
        important_log_path = f"{base_path}_important{ext}"
        
        # Создаем обработчик с ротацией файлов для важных событий
        important_handler = RotatingFileHandler(
            important_log_path, maxBytes=2*1024*1024, backupCount=3, encoding='utf-8'
        )
        important_handler.setFormatter(formatter)
        important_handler.setLevel(logging.WARNING)
        root_logger.addHandler(important_handler)
    
    # Логируем начало сессии
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info(f"Начало сессии логирования: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Уровень логирования: {logging.getLevelName(level)}")
    if log_file_path:
        logger.info(f"Файл лога: {log_file_path}")
    logger.info("=" * 60)
    
    return root_logger
