from dataclasses import dataclass
from typing import Optional
import MetaTrader5 as mt5

from signal_parser import ParsedSignal


@dataclass
class ExecutionResult:
    success: bool
    message: str
    ticket: Optional[int] = None
    symbol: Optional[str] = None
    action: Optional[str] = None
    lot: Optional[float] = None


class MT5Executor:
    """منفذ الصفقات على منصة MetaTrader 5"""

    def __init__(self, magic_number: int = 202611, deviation: int = 20):
        self.magic_number = magic_number
        self.deviation = deviation
        self.connected = False

    def connect(self) -> bool:
        """تهيئة والاتصال بمنصة MT5 المفتوحة على الجهاز"""
        if mt5.initialize():
            self.connected = True
            return True
        self.connected = False
        return False

    def disconnect(self) -> None:
        """إغلاق الاتصال البرمجي بالمنصة"""
        mt5.shutdown()
        self.connected = False

    def _normalize_lot(self, symbol_info, requested_lot: float) -> float:
        """مطابقة حجم اللوت مع أقل وأعلى حجم وخطوة مسموحة للرمز"""
        step = symbol_info.volume_step or 0.01
        min_vol = symbol_info.volume_min or 0.01
        max_vol = symbol_info.volume_max or 100.0

        lot = max(min_vol, min(requested_lot, max_vol))
        steps = round(lot / step)
        normalized = round(steps * step, 8)
        return max(min_vol, min(normalized, max_vol))

    def _resolve_filling_mode(self, symbol_info) -> int:
        """اختيار نوع التنفيذ المدعوم من الوسيط"""
        filling = symbol_info.filling_mode
        if filling & mt5.SYMBOL_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        if filling & mt5.SYMBOL_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    def execute_signal(self, signal: ParsedSignal, lot_size: float = 0.01) -> ExecutionResult:
        """تنفيذ توصية محللة على MT5"""
        if not signal.is_valid or not signal.symbol or not signal.action:
            return ExecutionResult(success=False, message="التوصية غير صالحة للتنفيذ.")

        if not self.connected and not self.connect():
            return ExecutionResult(
                success=False,
                message=f"تعذر الاتصال بـ MT5: {mt5.last_error()}",
            )

        symbol = signal.symbol.upper()
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return ExecutionResult(
                success=False,
                message=f"الرمز {symbol} غير موجود في حساب MT5.",
                symbol=symbol,
            )

        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return ExecutionResult(
                    success=False,
                    message=f"تعذر إظهار الرمز {symbol} في Market Watch.",
                    symbol=symbol,
                )
            symbol_info = mt5.symbol_info(symbol)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return ExecutionResult(
                success=False,
                message=f"تعذر جلب سعر السوق للرمز {symbol}.",
                symbol=symbol,
            )

        lot = self._normalize_lot(symbol_info, lot_size)
        filling_mode = self._resolve_filling_mode(symbol_info)

        order_type_map = {
            "MARKET": {
                "BUY": (mt5.ORDER_TYPE_BUY, tick.ask),
                "SELL": (mt5.ORDER_TYPE_SELL, tick.bid),
            },
            "BUY_LIMIT": (mt5.ORDER_TYPE_BUY_LIMIT, signal.entry_price or tick.ask),
            "SELL_LIMIT": (mt5.ORDER_TYPE_SELL_LIMIT, signal.entry_price or tick.bid),
            "BUY_STOP": (mt5.ORDER_TYPE_BUY_STOP, signal.entry_price or tick.ask),
            "SELL_STOP": (mt5.ORDER_TYPE_SELL_STOP, signal.entry_price or tick.bid),
        }

        if signal.order_type == "MARKET":
            mt5_type, price = order_type_map["MARKET"][signal.action]
            action_mode = mt5.TRADE_ACTION_DEAL
        else:
            if signal.order_type not in order_type_map:
                return ExecutionResult(
                    success=False,
                    message=f"نوع الأمر غير مدعوم: {signal.order_type}",
                    symbol=symbol,
                )
            mt5_type, price = order_type_map[signal.order_type]
            action_mode = mt5.TRADE_ACTION_PENDING

        # الهدف الأول كهدف أساسي للأمر (ويمكن لاحقاً تقسيم العقود لأهداف متعددة)
        tp_price = signal.tps[0] if signal.tps else 0.0
        sl_price = signal.sl if signal.sl is not None else 0.0

        request = {
            "action": action_mode,
            "symbol": symbol,
            "volume": lot,
            "type": mt5_type,
            "price": float(price),
            "sl": float(sl_price),
            "tp": float(tp_price),
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": "TG-MT5 Copier",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        result = mt5.order_send(request)
        if result is None:
            return ExecutionResult(
                success=False,
                message=f"فشل إرسال الأمر: {mt5.last_error()}",
                symbol=symbol,
                action=signal.action,
                lot=lot,
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return ExecutionResult(
                success=False,
                message=f"رفض الوسيط تنفيذ الصفقة ({result.retcode}): {result.comment}",
                symbol=symbol,
                action=signal.action,
                lot=lot,
            )

        return ExecutionResult(
            success=True,
            message="تم تنفيذ الصفقة بنجاح.",
            ticket=result.order,
            symbol=symbol,
            action=signal.action,
            lot=lot,
        )
