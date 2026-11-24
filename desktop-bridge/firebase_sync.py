from datetime import datetime, timezone
from typing import Any, Dict, Optional
import requests


class FirebaseSyncClient:
    """مزامنة الإعدادات، القنوات، الحالة، وسجل الصفقات مع Firebase Realtime Database"""

    def __init__(self, database_url: str, user_id: str, auth_token: Optional[str] = None):
        # مثال لـ database_url: https://your-project-default-rtdb.firebaseio.com
        self.database_url = database_url.rstrip("/")
        self.user_id = user_id
        self.auth_token = auth_token

    def _build_url(self, path: str) -> str:
        clean_path = path.strip("/")
        url = f"{self.database_url}/users/{self.user_id}/{clean_path}.json"
        if self.auth_token:
            url += f"?auth={self.auth_token}"
        return url

    def get_user_config(self) -> Dict[str, Any]:
        """جلب الإعدادات العامة وقائمة القنوات التي ضبطها المستخدم من الجوال"""
        default_data = {
            "settings": {"enabled": True, "lot_size": 0.01, "license_active": True},
            "channels": {},
        }
        try:
            resp = requests.get(self._build_url(""), timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return default_data
            return {
                "settings": {**default_data["settings"], **(data.get("settings") or {})},
                "channels": data.get("channels") or {},
            }
        except Exception as exc:
            print(f"[FirebaseSync] خطأ أثناء جلب الإعدادات: {exc}")
            return default_data

    def update_bridge_status(self, online: bool, mt5_connected: bool) -> None:
        """تحديث حالة أداة اللابتوب ليراها المستخدم من الجوال"""
        payload = {
            "online": online,
            "mt5_connected": mt5_connected,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }
        try:
            resp = requests.patch(self._build_url("bridge_status"), json=payload, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            print(f"[FirebaseSync] خطأ أثناء تحديث الحالة: {exc}")

    def log_execution(self, log_entry: Dict[str, Any]) -> None:
        """إرسال سجل تنفيذ الصفقة (نجاح أو فشل) ليظهر فوراً في تطبيق الجوال"""
        entry_with_time = {
            **log_entry,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            resp = requests.post(self._build_url("executions"), json=entry_with_time, timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            print(f"[FirebaseSync] خطأ أثناء تسجيل الصفقة: {exc}")
