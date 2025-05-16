### utils/state.py ###
import json
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class StateManager:
    """
    Управление состоянием бота.
    
    Отвечает за:
    - Сохранение и загрузку состояния бота
    - Восстановление работы после перезапуска
    """
    
    def __init__(self, state_file: str = "bot_state.json"):
        """
        Инициализация менеджера состояния
        
        Args:
            state_file: Путь к файлу состояния
        """
        self.state_file = state_file
        self.state = {
            'version': '1.0',
            'last_update': datetime.now().isoformat(),
            'running': False,
            'positions': {},
            'portfolio': {},
            'settings': {},
            'statistics': {}
        }
    
    def save_state(self, state_data: Dict[str, Any]) -> bool:
        """
        Сохранение состояния в файл
        
        Args:
            state_data: Данные состояния для сохранения
            
        Returns:
            bool: True, если состояние успешно сохранено
        """
        try:
            # Обновляем текущее состояние
            self.state.update(state_data)
            
            # Обновляем время последнего обновления
            self.state['last_update'] = datetime.now().isoformat()
            
            # Записываем в файл
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=4, ensure_ascii=False)
            
            logger.debug(f"Состояние бота сохранено в {self.state_file}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении состояния: {e}")
            return False
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """
        Загрузка состояния из файла
        
        Returns:
            dict: Загруженное состояние или None при ошибке
        """
        if not os.path.exists(self.state_file):
            logger.info(f"Файл состояния {self.state_file} не найден, используется пустое состояние")
            return self.state
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                loaded_state = json.load(f)
            
            # Обновляем текущее состояние
            self.state = loaded_state
            
            logger.info(f"Состояние бота загружено из {self.state_file}")
            return self.state
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке состояния: {e}")
            return None
    
    def update_state(self, key: str, value: Any) -> bool:
        """
        Обновление части состояния
        
        Args:
            key: Ключ для обновления
            value: Новое значение
            
        Returns:
            bool: True, если состояние успешно обновлено
        """
        try:
            # Обновляем состояние
            self.state[key] = value
            
            # Обновляем время последнего обновления
            self.state['last_update'] = datetime.now().isoformat()
            
            # Сохраняем в файл
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=4, ensure_ascii=False)
            
            logger.debug(f"Состояние бота обновлено (ключ: {key})")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении состояния: {e}")
            return False
    
    def get_state_value(self, key: str, default: Any = None) -> Any:
        """
        Получение значения из состояния
        
        Args:
            key: Ключ для получения
            default: Значение по умолчанию
            
        Returns:
            Any: Значение из состояния или default
        """
        return self.state.get(key, default)
    
    def clear_state(self) -> bool:
        """
        Очистка состояния
        
        Returns:
            bool: True, если состояние успешно очищено
        """
        try:
            # Сбрасываем состояние к начальному
            self.state = {
                'version': '1.0',
                'last_update': datetime.now().isoformat(),
                'running': False,
                'positions': {},
                'portfolio': {},
                'settings': {},
                'statistics': {}
            }
            
            # Удаляем файл состояния, если он существует
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
                logger.info(f"Файл состояния {self.state_file} удален")
            
            logger.info("Состояние бота очищено")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при очистке состояния: {e}")
            return False
    
    def is_running(self) -> bool:
        """
        Проверка, запущен ли бот
        
        Returns:
            bool: True, если бот запущен
        """
        return self.state.get('running', False)
    
    def set_running(self, running: bool) -> bool:
        """
        Установка флага запуска бота
        
        Args:
            running: Флаг запуска
            
        Returns:
            bool: True, если флаг успешно установлен
        """
        return self.update_state('running', running)