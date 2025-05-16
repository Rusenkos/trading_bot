import os
import yaml
import logging
from pathlib import Path
from datetime import datetime
from tinkoff.invest import CandleInterval
from dotenv import load_dotenv

# Грузим .env при старте модуля
load_dotenv()
logger = logging.getLogger(__name__)

def load_config(config_path=None):
    """
    Загружает конфигурацию из YAML файла.
    """
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'default_config.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config_data = yaml.safe_load(file)
            return config_data
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации: {e}")
        raise

class Config:
    """
    Класс конфигурации для трейдинг-бота с возможностью динамической загрузки.
    """
    # API Токены
    TINKOFF_TOKEN = os.environ.get('TINKOFF_TOKEN', '')
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    
    # Путь к файлу .env
    ENV_FILE = '.env'
    
    # Тикеры для торговли
    SYMBOLS = ['SBER', 'GAZP', 'LKOH', 'ROSN']
    
    # Режим демо-данных
    DEMO_MODE = False
    
    # Настройки таймфрейма
    TIMEFRAME = CandleInterval.CANDLE_INTERVAL_DAY
    
    # Настройки трендовой стратегии
    EMA_SHORT = 5
    EMA_LONG = 20
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    VOLUME_MA_PERIOD = 20
    MIN_VOLUME_FACTOR = 2.0  # Минимальный множитель объема для входа
    
    # Настройки контртрендовой стратегии
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    BOLLINGER_PERIOD = 20
    BOLLINGER_STD = 2
    
    # Управление рисками
    STOP_LOSS_PERCENT = 3.0
    TRAILING_STOP_PERCENT = 1.5
    MAX_POSITION_SIZE = 0.9
    MAX_POSITIONS = 1
    MAX_HOLDING_DAYS = 7
    TAKE_PROFIT_PERCENT = 3.0  # <-- добавлен обязательный параметр
    
    # Настройки комиссий и исполнения
    COMMISSION_RATE = 0.003  # 0.3% комиссия на сделку
    USE_MARKET_ORDERS = True
    
    # Настройки стратегий
    ACTIVE_STRATEGIES = ["trend", "reversal"]
    STRATEGY_MODE = "any"
    
    # Настройки логирования
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'logs/trading_bot.log'
    
    # Настройки цикла работы бота
    UPDATE_INTERVAL = 900
    CHECK_STOP_LOSS_INTERVAL = 300
    
    # Рабочее время рынка (Мосбиржа)
    MARKET_OPEN_HOUR = 10
    MARKET_CLOSE_HOUR = 19
    TRADING_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    
    # Настройки для чтения данных
    MAX_DAYS_PER_REQUEST = {
        CandleInterval.CANDLE_INTERVAL_1_MIN: 1,
        CandleInterval.CANDLE_INTERVAL_5_MIN: 1,
        CandleInterval.CANDLE_INTERVAL_15_MIN: 1,
        CandleInterval.CANDLE_INTERVAL_HOUR: 7,
        CandleInterval.CANDLE_INTERVAL_DAY: 365,
    }
    
    # Минимальное количество данных для анализа (в свечах)
    MIN_DATA_POINTS = 30
    
    # Настройки кэширования
    CACHE_DIR = "data_cache"
    USE_CACHE = True
    
    # Настройки бэктестинга
    INITIAL_CAPITAL = 50000
    
    @classmethod
    def from_dict(cls, config_dict):
        """
        Создает экземпляр Config на основе словаря
        """
        instance = cls()
        for section, params in config_dict.items():
            if isinstance(params, dict):
                for key, value in params.items():
                    attr_name = f"{section.upper()}_{key.upper()}"
                    setattr(instance, attr_name, value)
            else:
                attr_name = section.upper()
                setattr(instance, attr_name, params)
        return instance

    @classmethod
    def load(cls, config_path=None):
        """
        Загружает конфигурацию из файла
        """
        config_dict = load_config(config_path)
        return cls.from_dict(config_dict)
    
    @classmethod
    def reload_env(cls):
        """
        Перезагрузка переменных окружения из .env файла.
        """
        load_dotenv(dotenv_path=cls.ENV_FILE, override=True)
        cls.TINKOFF_TOKEN = os.environ.get('TINKOFF_TOKEN', '')
        cls.TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
        cls.TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

    @classmethod
    def is_token_valid(cls):
        """
        Проверка наличия и валидности формата токена Тинькофф
        """
        if not cls.TINKOFF_TOKEN:
            return False
        if not cls.TINKOFF_TOKEN.startswith('t.'):
            return False
        if len(cls.TINKOFF_TOKEN) < 20:
            return False
        return True

    def to_dict(self):
        """
        Преобразует конфигурацию в словарь
        """
        result = {}
        for attr in dir(self):
            if not attr.startswith('__') and not callable(getattr(self, attr)):
                result[attr] = getattr(self, attr)
        return result

    def save(self, config_path):
        """
        Сохраняет конфигурацию в файл
        """
        config_dict = self.to_dict()
        structured_config = {}
        for key, value in config_dict.items():
            if '_' in key:
                section, param = key.lower().split('_', 1)
                if section not in structured_config:
                    structured_config[section] = {}
                structured_config[section][param] = value
            else:
                structured_config[key.lower()] = value
        try:
            with open(config_path, 'w', encoding='utf-8') as file:
                yaml.dump(structured_config, file, default_flow_style=False, sort_keys=False)
            logger.info(f"Конфигурация сохранена в {config_path}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении конфигурации: {e}")
            raise