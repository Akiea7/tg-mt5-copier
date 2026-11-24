import asyncio
from typing import Callable, Dict, Optional
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from signal_parser import ParsedSignal, parse_signal


class TelegramChannelConfig:
    """إعدادات قناة واحدة مراقبة"""

    def __init__(self, chat_id: int, default_symbol: Optional[str] = None, enabled: bool = True):
        self.chat_id = chat_id
        self.default_symbol = default_symbol
        self.enabled = enabled


class TelegramSignalListener:
    """مراقب قنوات تيليجرام واستخراج التوصيات الجديدة"""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_string: str = "",
        channels: Optional[Dict[int, TelegramChannelConfig]] = None,
        on_signal_parsed: Optional[Callable[[int, ParsedSignal], None]] = None,
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.client = TelegramClient(StringSession(session_string), api_id, api_hash)
        self.channels: Dict[int, TelegramChannelConfig] = channels or {}
        self.on_signal_parsed = on_signal_parsed

    def update_channels(self, channels: Dict[int, TelegramChannelConfig]) -> None:
        """تحديث قائمة القنوات وإعداداتها (مثل الرمز الافتراضي أو التفعيل)"""
        self.channels = channels

    async def start(self) -> None:
        """تشغيل العميل والبدء بالاستماع للرسائل الجديدة"""
        @self.client.on(events.NewMessage())
        async def handle_new_message(event: events.NewMessage.Event) -> None:
            chat_id = event.chat_id
            if chat_id is None or chat_id not in self.channels:
                return

            ch_cfg = self.channels[chat_id]
            if not ch_cfg.enabled:
                return

            text = event.raw_text or ""
            parsed = parse_signal(text, default_symbol=ch_cfg.default_symbol)

            if self.on_signal_parsed:
                self.on_signal_parsed(chat_id, parsed)

        await self.client.start()
        print("TelegramSignalListener is running and watching configured channels...")
        await self.client.run_until_disconnected()

    def get_session_string(self) -> str:
        """إرجاع نص الجلسة لحفظه بشكل آمن عند الحاجة"""
        return self.client.session.save()


# --- تجربة سريعة للملف (تُعدّل القيم محلياً للاختبار فقط) ---
if __name__ == "__main__":
    API_ID = 1234567          # استبدله بـ API_ID الخاص بك من my.telegram.org
    API_HASH = "your_api_hash"

    # مثال: قناة ذهب بدون ذكر الرمز داخل الرسالة -> default_symbol="XAUUSD"
    sample_channels = {
        -1001234567890: TelegramChannelConfig(
            chat_id=-1001234567890,
            default_symbol="XAUUSD",
            enabled=True,
        )
    }

    def on_signal(chat_id: int, signal: ParsedSignal) -> None:
        print(f"[Chat {chat_id}] Valid={signal.is_valid} | {signal.to_dict()}")

    listener = TelegramSignalListener(
        api_id=API_ID,
        api_hash=API_HASH,
        channels=sample_channels,
        on_signal_parsed=on_signal,
    )

    try:
        asyncio.run(listener.start())
    except KeyboardInterrupt:
        print("Stopped.")
