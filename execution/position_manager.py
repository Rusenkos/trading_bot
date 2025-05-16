### execution/position_manager.py ###
from typing import Dict, List, Optional, Tuple, Any
import logging
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)

class PositionManager:
    """
    Управляет открытыми позициями и их состоянием.
    
    Отвечает за:
    - Отслеживание открытых позиций
    - Обновление статуса позиций
    - Сохранение и загрузку состояния позиций
    - Расчет метрик по портфелю
    """
    
    def __init__(self, config=None):
        """
        Инициализация менеджера позиций
        
        Args:
            config: Объект конфигурации
        """
        self.config = config
        self.positions = {}  # Текущие открытые позиции (symbol -> position_info)
        self.closed_positions = []  # История закрытых позиций
        self.state_file = "positions_state.json"  # Файл для сохранения состояния
    
    def add_position(self, symbol: str, position_info: Dict[str, Any]) -> None:
        """
        Добавление новой позиции
        
        Args:
            symbol: Тикер символа
            position_info: Информация о позиции
        """
        # Проверяем наличие обязательных полей
        required_fields = ['entry_price', 'quantity', 'entry_time']
        for field in required_fields:
            if field not in position_info:
                if field == 'entry_time':
                    position_info['entry_time'] = datetime.now().isoformat()
                else:
                    logger.warning(f"Отсутствует обязательное поле {field} в информации о позиции")
        
        # Рассчитываем значение позиции
        if 'value' not in position_info and 'entry_price' in position_info and 'quantity' in position_info:
            position_info['value'] = position_info['entry_price'] * position_info['quantity']
        
        # Устанавливаем направление позиции
        if 'direction' not in position_info:
            position_info['direction'] = 'buy'  # По умолчанию длинная позиция
        
        # Добавляем идентификатор позиции
        if 'id' not in position_info:
            position_info['id'] = f"{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Сохраняем позицию
        self.positions[symbol] = position_info
        logger.info(f"Добавлена новая позиция {symbol}: цена={position_info.get('entry_price', 0)}, "
                  f"кол-во={position_info.get('quantity', 0)}, "
                  f"стоп={position_info.get('stop_loss', 0)}")
        
        # Сохраняем состояние
        self.save_state()
    
    def update_position(self, symbol: str, updates: Dict[str, Any]) -> None:
        """
        Обновление информации о существующей позиции
        
        Args:
            symbol: Тикер символа
            updates: Обновляемые параметры позиции
        """
        if symbol not in self.positions:
            logger.warning(f"Попытка обновить несуществующую позицию {symbol}")
            return
        
        # Обновляем информацию
        for key, value in updates.items():
            self.positions[symbol][key] = value
        
        logger.info(f"Обновлена позиция {symbol}: {', '.join([f'{k}={v}' for k, v in updates.items()])}")
        
        # Сохраняем состояние
        self.save_state()
    
    def close_position(self, symbol: str, close_info: Dict[str, Any]) -> None:
        """
        Закрытие позиции
        
        Args:
            symbol: Тикер символа
            close_info: Информация о закрытии (цена, время, причина)
        """
        if symbol not in self.positions:
            logger.warning(f"Попытка закрыть несуществующую позицию {symbol}")
            return
        
        # Получаем информацию о позиции
        position = self.positions[symbol].copy()
        
        # Добавляем информацию о закрытии
        position.update(close_info)
        
        # Если не указано время закрытия, ставим текущее
        if 'close_time' not in position:
            position['close_time'] = datetime.now().isoformat()
        
        # Рассчитываем P&L
        if 'close_price' in position and 'entry_price' in position:
            entry_price = position['entry_price']
            close_price = position['close_price']
            
            if position.get('direction', 'buy') == 'buy':
                # Для длинной позиции
                pnl_percent = (close_price / entry_price - 1) * 100
            else:
                # Для короткой позиции (на будущее)
                pnl_percent = (entry_price / close_price - 1) * 100
            
            position['pnl_percent'] = pnl_percent
            
            # Абсолютный P&L
            if 'quantity' in position:
                position['pnl_absolute'] = (close_price - entry_price) * position['quantity']
        
        # Рассчитываем время удержания
        if 'entry_time' in position and 'close_time' in position:
            try:
                entry_time = datetime.fromisoformat(position['entry_time']) if isinstance(position['entry_time'], str) else position['entry_time']
                close_time = datetime.fromisoformat(position['close_time']) if isinstance(position['close_time'], str) else position['close_time']
                
                # Если время задано pandas.Timestamp, преобразуем в datetime
                if hasattr(entry_time, 'to_pydatetime'):
                    entry_time = entry_time.to_pydatetime()
                if hasattr(close_time, 'to_pydatetime'):
                    close_time = close_time.to_pydatetime()
                
                holding_time = close_time - entry_time
                position['holding_days'] = holding_time.days
                position['holding_hours'] = holding_time.total_seconds() / 3600
            except Exception as e:
                logger.error(f"Ошибка при расчете времени удержания: {e}")
        
        # Добавляем в историю закрытых позиций
        self.closed_positions.append(position)
        
        # Логируем информацию о закрытии
        pnl_info = f", P&L: {position.get('pnl_percent', 0):.2f}%" if 'pnl_percent' in position else ""
        logger.info(f"Закрыта позиция {symbol}: цена={position.get('close_price', 0)}, "
                  f"причина={position.get('close_reason', 'not specified')}{pnl_info}")
        
        # Удаляем из активных позиций
        del self.positions[symbol]
        
        # Сохраняем состояние
        self.save_state()
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Получение информации о позиции
        
        Args:
            symbol: Тикер символа
            
        Returns:
            dict: Информация о позиции или None, если позиция не найдена
        """
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Получение всех открытых позиций
        
        Returns:
            dict: Словарь всех открытых позиций
        """
        return self.positions
    
    def has_position(self, symbol: str) -> bool:
        """
        Проверка наличия открытой позиции по символу
        
        Args:
            symbol: Тикер символа
            
        Returns:
            bool: True, если позиция открыта
        """
        return symbol in self.positions
    
    def get_position_count(self) -> int:
        """
        Получение количества открытых позиций
        
        Returns:
            int: Количество открытых позиций
        """
        return len(self.positions)
    
    def calculate_portfolio_metrics(self) -> Dict[str, Any]:
        """
        Расчет метрик по портфелю
        
        Returns:
            dict: Метрики портфеля
        """
        if not self.positions and not self.closed_positions:
            return {
                'total_positions': 0,
                'open_positions': 0,
                'closed_positions': 0,
                'total_pnl_percent': 0,
                'total_pnl_absolute': 0,
                'win_rate': 0,
                'average_win': 0,
                'average_loss': 0,
                'profit_factor': 0,
                'average_holding_days': 0
            }
        
        # Метрики по открытым позициям
        open_positions_count = len(self.positions)
        open_positions_value = sum(pos.get('value', 0) for pos in self.positions.values())
        
        # Метрики по закрытым позициям
        closed_positions_count = len(self.closed_positions)
        
        # Расчет прибыли/убытков
        if closed_positions_count > 0:
            # Общий P&L
            total_pnl_absolute = sum(pos.get('pnl_absolute', 0) for pos in self.closed_positions)
            
            # Среднее значение P&L%
            total_pnl_percent = sum(pos.get('pnl_percent', 0) for pos in self.closed_positions) / closed_positions_count
            
            # Расчет винрейта
            winning_trades = [pos for pos in self.closed_positions if pos.get('pnl_percent', 0) > 0]
            losing_trades = [pos for pos in self.closed_positions if pos.get('pnl_percent', 0) <= 0]
            
            win_count = len(winning_trades)
            loss_count = len(losing_trades)
            
            win_rate = win_count / closed_positions_count if closed_positions_count > 0 else 0
            
            # Среднее значение выигрышных и проигрышных сделок
            average_win = sum(pos.get('pnl_percent', 0) for pos in winning_trades) / win_count if win_count > 0 else 0
            average_loss = sum(abs(pos.get('pnl_percent', 0)) for pos in losing_trades) / loss_count if loss_count > 0 else 0
            
            # Расчет Profit Factor
            total_wins = sum(pos.get('pnl_absolute', 0) for pos in winning_trades)
            total_losses = sum(abs(pos.get('pnl_absolute', 0)) for pos in losing_trades)
            
            profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
            
            # Среднее время удержания позиции
            average_holding_days = sum(pos.get('holding_days', 0) for pos in self.closed_positions) / closed_positions_count
        else:
            total_pnl_absolute = 0
            total_pnl_percent = 0
            win_rate = 0
            average_win = 0
            average_loss = 0
            profit_factor = 0
            average_holding_days = 0
        
        return {
            'total_positions': open_positions_count + closed_positions_count,
            'open_positions': open_positions_count,
            'closed_positions': closed_positions_count,
            'open_positions_value': open_positions_value,
            'total_pnl_percent': total_pnl_percent,
            'total_pnl_absolute': total_pnl_absolute,
            'win_rate': win_rate * 100,  # в процентах
            'average_win': average_win,
            'average_loss': average_loss,
            'profit_factor': profit_factor,
            'average_holding_days': average_holding_days
        }
    
    def save_state(self) -> None:
        """
        Сохранение состояния позиций в файл
        """
        try:
            # Подготавливаем данные для сохранения (преобразуем datetime в строки)
            positions_to_save = {}
            for symbol, position in self.positions.items():
                position_copy = position.copy()
                for key, value in position_copy.items():
                    if isinstance(value, datetime):
                        position_copy[key] = value.isoformat()
                positions_to_save[symbol] = position_copy
            
            closed_to_save = []
            for position in self.closed_positions:
                position_copy = position.copy()
                for key, value in position_copy.items():
                    if isinstance(value, datetime):
                        position_copy[key] = value.isoformat()
                closed_to_save.append(position_copy)
            
            # Создаем структуру для сохранения
            state = {
                'positions': positions_to_save,
                'closed_positions': closed_to_save,
                'last_update': datetime.now().isoformat()
            }
            
            # Сохраняем в файл
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=4)
            
            logger.debug(f"Состояние позиций сохранено в {self.state_file}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении состояния позиций: {e}")
    
    def load_state(self) -> None:
        """
        Загрузка состояния позиций из файла
        """
        if not os.path.exists(self.state_file):
            logger.info(f"Файл состояния {self.state_file} не найден, используется пустое состояние")
            return
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            # Загружаем открытые позиции
            self.positions = state.get('positions', {})
            
            # Загружаем историю закрытых позиций
            self.closed_positions = state.get('closed_positions', [])
            
            logger.info(f"Состояние позиций загружено из {self.state_file}: "
                      f"{len(self.positions)} открытых, {len(self.closed_positions)} закрытых")
        except Exception as e:
            logger.error(f"Ошибка при загрузке состояния позиций: {e}")
    
    def clear_state(self) -> None:
        """
        Очистка состояния позиций
        """
        self.positions = {}
        self.closed_positions = []
        
        # Удаляем файл состояния, если он существует
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
                logger.info(f"Файл состояния {self.state_file} удален")
            except Exception as e:
                logger.error(f"Ошибка при удалении файла состояния: {e}")
        
        logger.info("Состояние позиций очищено")
    
    def export_trading_history(self, filename: str = "trading_history.csv") -> None:
        """
        Экспорт истории сделок в CSV файл
        
        Args:
            filename: Имя файла для экспорта
        """
        if not self.closed_positions:
            logger.info("Нет закрытых позиций для экспорта")
            return
        
        try:
            import pandas as pd
            
            # Создаем DataFrame из истории сделок
            df = pd.DataFrame(self.closed_positions)
            
            # Сохраняем в CSV
            df.to_csv(filename, index=False)
            
            logger.info(f"История сделок экспортирована в {filename}")
        except Exception as e:
            logger.error(f"Ошибка при экспорте истории сделок: {e}")
    
    def generate_performance_report(self) -> str:
        """
        Генерация отчета о результатах торговли
        
        Returns:
            str: Текстовый отчет о результатах
        """
        metrics = self.calculate_portfolio_metrics()
        
        if metrics['total_positions'] == 0:
            return "Нет данных о сделках для формирования отчета"
        
        # Форматируем отчет
        report = []
        report.append("===== ОТЧЕТ О РЕЗУЛЬТАТАХ ТОРГОВЛИ =====")
        report.append(f"Всего сделок: {metrics['total_positions']}")
        report.append(f"Открытых позиций: {metrics['open_positions']}")
        report.append(f"Закрытых сделок: {metrics['closed_positions']}")
        report.append(f"Общая прибыль: {metrics['total_pnl_percent']:.2f}%")
        report.append(f"Абсолютная прибыль: {metrics['total_pnl_absolute']:.2f} руб.")
        report.append(f"Процент успешных сделок: {metrics['win_rate']:.2f}%")
        report.append(f"Средняя прибыль по успешным сделкам: {metrics['average_win']:.2f}%")
        report.append(f"Средний убыток по убыточным сделкам: {metrics['average_loss']:.2f}%")
        report.append(f"Profit Factor: {metrics['profit_factor']:.2f}")
        report.append(f"Среднее время удержания позиции: {metrics['average_holding_days']:.1f} дней")
        report.append("=====================================")
        
        return "\n".join(report)