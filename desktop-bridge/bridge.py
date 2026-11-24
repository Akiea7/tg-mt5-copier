import asyncio
import os
from typing import Dict

from firebase_sync import FirebaseSyncClient
from mt5_executor import MT5Executor
from signal_parser import ParsedSignal
from telegram_listener import TelegramChannelConfig, TelegramSignalListener


class CopierBridgeApp:
    """المنسق الرئيسي لأداة اللابتوب التي تربط تيليجرام والسحابة وMT5"""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        database_url: str,
        user_id: str,
        session_string: str = "",
        poll_interval: int = 5,
    ):
        self.poll_interval = poll_interval
        self.sync = FirebaseSyncClient(database_url=database_url, user_id=user_id)
        self.executor = MT5Executor()
        self.listener = TelegramSignalListener(
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            on_signal_parsed=self._handle_parsed_signal,
        )

        self.copier_enabled: bool = True
        self.license_active: bool = True
        self.lot_size: float = 0.01

    def _apply_remote_config(self) -> None:
        """جلب الإعدادات والقنوات من Firebase وتحديث الحالة"""
        cfg = self.sync.get_user_config()
        settings = cfg.get("settings", {})
        raw_channels = cfg.get("channels", {})

        self.copier_enabled = bool(settings.get("enabled", True))
        self.license_active = bool(settings.get("license_active", True))
        try:
            self.lot_size = float(settings.get("lot_size", 0.01))
        except (TypeError, ValueError):
            self.lot_size = 0.01

        parsed_channels: Dict[int, TelegramChannelConfig] = {}
        if isinstance(raw_channels, dict):
            for key, ch_data in raw_channels.items():
                if not isinstance(ch_data, dict):
                    continue
                raw_chat_id = ch_data.get("chat_id", key)
                try:
                    chat_id_int = int(raw_chat_id)
                except (TypeError, ValueError):
                    continue

                parsed_channels[chat_id_int] = TelegramChannelConfig(
                    chat_id=chat_id_int,
                    default_symbol=ch_data.get("default_symbol"),
                    enabled=bool(ch_data.get("enabled", True)),
                )

        self.listener.update_channels(parsed_channels)

        mt5_ok = self.executor.connected or self.executor.connect()
        self.sync.update_bridge_status(online=True, mt5_connected=mt5_ok)

    def _handle_parsed_signal(self, chat_id: int, signal: ParsedSignal) -> None:
        """التعامل مع التوصية المحللة وتنفيذها إذا كانت الشروط متوفرة"""
        if not self.license_active:
            self.sync.log_execution({
                "success": False,
                "symbol": signal.symbol,
                "action": signal.action,
                "lot": self.lot_size,
                "message": "الاشتراك غير فعّال (License Inactive).",
                "chat_id": chat_id,
            })
            return

        if not self.copier_enabled:
            return

        if not signal.is_valid:
            return

        result = self.executor.execute_signal(signal=signal, lot_size=self.lot_size)
        self.sync.log_execution({
            "success": result.success,
            "ticket": result.ticket,
            "symbol": result.symbol or signal.symbol,
            "action": result.action or signal.action,
            "lot": result.lot or self.lot_size,
            "message": result.message,
            "chat_id": chat_id,
        })

    async def _sync_loop(self) -> None:
        """حلقة مزامنة دورية مع السحابة"""
        while True:
            self._apply_remote_config()
            await asyncio.sleep(self.poll_interval)

    async def run(self) -> None:
        """تشغيل مراقب تيليجرام وحلقة المزامنة معاً"""
        self._apply_remote_config()
        sync_task = asyncio.create_task(self._sync_loop())
        try:
            await self.listener.start()
        finally:
            sync_task.cancel()
            self.sync.update_bridge_status(online=False, mt5_connected=False)
            self.executor.disconnect()


if __name__ == "__main__":
    # يمكن تمرير هذه القيم عبر متغيرات البيئة أو ملف إعداد بسيط عند التغليف
    API_ID = int(os.getenv("TG_API_ID", "1234567"))
    API_HASH = os.getenv("TG_API_HASH", "your_api_hash")
    DATABASE_URL = os.getenv("FIREBASE_DB_URL", "https://your-project-default-rtdb.firebaseio.com")
    USER_ID = os.getenv("COPIER_USER_ID", "DEMO_USER_01")
    SESSION_STRING = os.getenv("TG_SESSION_STRING", "")

    app = CopierBridgeApp(
        api_id=API_ID,
        api_hash=API_HASH,
        database_url=DATABASE_URL,
        user_id=USER_ID,
        session_string=SESSION_STRING,
        poll_interval=5,
    )

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("Bridge stopped by user.")
