### utils/notifications.py ###
import logging
import requests
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """
    Класс для отправки уведомлений в Telegram.
    """
    
    def __init__(self, token: str, chat_id: str):
        """
        Инициализация отправителя уведомлений
        
        Args:
            token: Токен бота Telegram
            chat_id: ID чата для отправки уведомлений
        """
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Отправка сообщения в Telegram
        
        Args:
            text: Текст сообщения
            parse_mode: Режим форматирования текста
            
        Returns:
            bool: True, если сообщение успешно отправлено
        """
        if not self.token or not self.chat_id:
            logger.warning("Не указан токен или ID чата Telegram, уведомление не отправлено")
            return False
        
        # Формируем параметры запроса
        params = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        
        try:
            # Отправляем запрос
            response = requests.post(self.base_url, params=params, timeout=10)
            
            # Проверяем успешность запроса
            if response.status_code == 200 and response.json().get('ok'):
                logger.info(f"Уведомление в Telegram отправлено успешно")
                return True
            else:
                logger.warning(f"Ошибка при отправке уведомления в Telegram: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления в Telegram: {e}")
            return False
    
    def send_trade_notification(self, trade_info: Dict[str, Any]) -> bool:
        """
        Отправка уведомления о сделке
        
        Args:
            trade_info: Информация о сделке
            
        Returns:
            bool: True, если уведомление успешно отправлено
        """
        # Определяем тип сделки
        trade_type = trade_info.get('type', '').upper()
        
        # Определяем эмодзи в зависимости от типа сделки
        if trade_type == 'BUY':
            emoji = "🟢"
            action = "ПОКУПКА"
        elif trade_type == 'SELL':
            emoji = "🔴"
            action = "ПРОДАЖА"
        elif trade_type == 'STOP_LOSS':
            emoji = "⚠️"
            action = "СТОП-ЛОСС"
        elif trade_type == 'TAKE_PROFIT':
            emoji = "✅"
            action = "ТЕЙК-ПРОФИТ"
        else:
            emoji = "ℹ️"
            action = trade_type
        
        # Формируем текст сообщения
        symbol = trade_info.get('symbol', 'Неизвестный символ')
        price = trade_info.get('price', 0)
        quantity = trade_info.get('quantity', 0)
        
        # Добавляем информацию о прибыли/убытке для SELL
        pnl_info = ""
        if trade_type in ['SELL', 'STOP_LOSS', 'TAKE_PROFIT'] and 'pnl_percent' in trade_info:
            pnl = trade_info['pnl_percent']
            pnl_emoji = "📈" if pnl > 0 else "📉"
            pnl_info = f"\n{pnl_emoji} P&L: <b>{pnl:.2f}%</b>"
        
        # Добавляем информацию о причине
        reason_info = ""
        if 'reason' in trade_info and trade_info['reason']:
            reason_info = f"\n📋 Причина: {trade_info['reason']}"
        
        # Собираем сообщение
        message = (
            f"{emoji} <b>{action}: {symbol}</b>\n"
            f"💰 Цена: <b>{price:.2f}</b>\n"
            f"🔢 Количество: <b>{quantity}</b>\n"
            f"💵 Сумма: <b>{price * quantity:.2f}</b>"
            f"{pnl_info}"
            f"{reason_info}"
        )
        
        return self.send_message(message)
    
    def send_signal_notification(self, symbol: str, signal_details: Dict[str, Any]) -> bool:
        """
        Отправка уведомления о торговом сигнале
        
        Args:
            symbol: Тикер инструмента
            signal_details: Детали сигнала
            
        Returns:
            bool: True, если уведомление успешно отправлено
        """
        # Определяем тип сигнала
        signal_type = signal_details.get('type', '').upper()
        
        # Определяем эмодзи в зависимости от типа сигнала
        if signal_type == 'BUY':
            emoji = "🔔"
            action = "СИГНАЛ НА ПОКУПКУ"
        elif signal_type == 'SELL':
            emoji = "🔔"
            action = "СИГНАЛ НА ПРОДАЖУ"
        else:
            emoji = "ℹ️"
            action = f"СИГНАЛ {signal_type}"
        
        # Формируем текст сообщения
        strategy = signal_details.get('strategy', 'Неизвестная стратегия')
        price = signal_details.get('price', 0)
        strength = signal_details.get('strength', 0) * 100  # в процентах
        
        # Получаем причины сигнала
        reasons = signal_details.get('reasons', [])
        reasons_text = "\n".join([f"• {reason}" for reason in reasons]) if reasons else "Не указаны"
        
        # Собираем сообщение
        message = (
            f"{emoji} <b>{action}: {symbol}</b>\n"
            f"📊 Стратегия: <b>{strategy}</b>\n"
            f"💰 Цена: <b>{price:.2f}</b>\n"
            f"💪 Сила сигнала: <b>{strength:.0f}%</b>\n"
            f"📋 Причины:\n{reasons_text}"
        )
        
        return self.send_message(message)
    
    def send_error_notification(self, error_message: str) -> bool:
        """
        Отправка уведомления об ошибке
        
        Args:
            error_message: Сообщение об ошибке
            
        Returns:
            bool: True, если уведомление успешно отправлено
        """
        message = f"❌ <b>ОШИБКА</b>\n\n{error_message}"
        return self.send_message(message)
    
    def send_portfolio_report(self, portfolio_metrics: Dict[str, Any]) -> bool:
        """
        Отправка отчета о портфеле
        
        Args:
            portfolio_metrics: Метрики портфеля
            
        Returns:
            bool: True, если отчет успешно отправлен
        """
        # Форматируем отчет
        if not portfolio_metrics:
            return self.send_message("📊 <b>ПОРТФЕЛЬ</b>\n\nНет данных о портфеле")
        
        # Базовые метрики
        open_positions = portfolio_metrics.get('open_positions', 0)
        closed_positions = portfolio_metrics.get('closed_positions', 0)
        total_pnl_percent = portfolio_metrics.get('total_pnl_percent', 0)
        total_pnl_absolute = portfolio_metrics.get('total_pnl_absolute', 0)
        
        # Формируем текст отчета
        pnl_emoji = "📈" if total_pnl_percent > 0 else "📉"
        
        message = (
            f"📊 <b>ОТЧЕТ О ПОРТФЕЛЕ</b>\n\n"
            f"🔢 Открытых позиций: <b>{open_positions}</b>\n"
            f"🔄 Закрытых сделок: <b>{closed_positions}</b>\n"
            f"{pnl_emoji} Общая прибыль: <b>{total_pnl_percent:.2f}%</b>\n"
            f"💰 Абсолютная прибыль: <b>{total_pnl_absolute:.2f}</b> руб.\n"
        )
        
        # Добавляем дополнительные метрики, если есть закрытые сделки
        if closed_positions > 0:
            win_rate = portfolio_metrics.get('win_rate', 0)
            average_win = portfolio_metrics.get('average_win', 0)
            average_loss = portfolio_metrics.get('average_loss', 0)
            profit_factor = portfolio_metrics.get('profit_factor', 0)
            
            message += (
                f"✅ Процент успешных: <b>{win_rate:.1f}%</b>\n"
                f"📊 Средняя прибыль: <b>{average_win:.2f}%</b>\n"
                f"📊 Средний убыток: <b>{average_loss:.2f}%</b>\n"
                f"📊 Profit Factor: <b>{profit_factor:.2f}</b>\n"
            )
        
        return self.send_message(message)