import re
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class ParsedSignal:
    is_valid: bool
    symbol: Optional[str] = None
    action: Optional[str] = None          # "BUY" or "SELL"
    order_type: str = "MARKET"            # "MARKET", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"
    entry_price: Optional[float] = None
    sl: Optional[float] = None
    tps: List[float] = None
    raw_text: str = ""

    def __post_init__(self):
        if self.tps is None:
            self.tps = []

    def to_dict(self) -> dict:
        return asdict(self)


# قاموس توحيد أسماء الأزواج والمعادن الشائعة في قنوات التوصيات
SYMBOL_ALIASES = {
    "GOLD": "XAUUSD",
    "XAU": "XAUUSD",
    "ذهب": "XAUUSD",
    "الذهب": "XAUUSD",
    "SILVER": "XAGUSD",
    "XAG": "XAGUSD",
    "فضة": "XAGUSD",
    "الفضة": "XAGUSD",
    "US30": "US30",
    "DOW": "US30",
    "داو": "US30",
    "NAS100": "NDX100",
    "NASDAQ": "NDX100",
    "ناسداك": "NDX100",
    "BTC": "BTCUSD",
    "BTCUSD": "BTCUSD",
    "بتكوين": "BTCUSD",
}


def _normalize_arabic_digits(text: str) -> str:
    """تحويل الأرقام العربية والفارسية إلى أرقام إنجليزية قياسية"""
    arabic_map = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹،", "01234567890123456789.")
    return text.translate(arabic_map)


def _extract_symbol(text: str) -> Optional[str]:
    upper_text = text.upper()

    # 1. البحث عن أسماء مستعارة عربية أو شائعة
    for alias, canonical in SYMBOL_ALIASES.items():
        if re.search(rf"(?<![A-Z0-9_]){re.escape(alias.upper())}(?![A-Z0-9_])", upper_text):
            return canonical

    # 2. البحث عن أزواج العملات الستة أحرف (مثل EURUSD, GBPJPY) مع أو بدون شرطة
    pair_match = re.search(
        r"\b([A-Z]{3})\s*[/\-]?\s*([A-Z]{3})\b",
        upper_text
    )
    if pair_match:
        base, quote = pair_match.group(1), pair_match.group(2)
        currencies = {
            "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "XAU", "XAG"
        }
        if base in currencies and quote in currencies:
            return f"{base}{quote}"

    # 3. رموز شائعة إضافية
    for extra in ["USOIL", "WTI", "UKOIL", "BRENT"]:
        if re.search(rf"\b{extra}\b", upper_text):
            return extra

    return None


def _resolve_default_symbol(default_symbol: Optional[str]) -> Optional[str]:
    """توحيد الرمز الافتراضي للقناة إذا تم تحديده"""
    if not default_symbol or not default_symbol.strip():
        return None
    normalized_default = _normalize_arabic_digits(default_symbol.strip())
    return _extract_symbol(normalized_default) or normalized_default.upper()


def _extract_action(text: str) -> Optional[str]:
    upper_text = text.upper()

    buy_patterns = [
        r"\bBUY\b", r"\bLONG\b",
        r"شراء", r"شراء\s*فوري", r"شراء\s*معلق", r"باي"
    ]
    sell_patterns = [
        r"\bSELL\b", r"\bSHORT\b",
        r"بيع", r"بيع\s*فوري", r"بيع\s*معلق", r"سيل"
    ]

    has_buy = any(re.search(p, upper_text) for p in buy_patterns)
    has_sell = any(re.search(p, upper_text) for p in sell_patterns)

    if has_buy and not has_sell:
        return "BUY"
    if has_sell and not has_buy:
        return "SELL"
    return None


def _extract_order_type(text: str, action: Optional[str]) -> str:
    if not action:
        return "MARKET"

    upper_text = text.upper()
    if "LIMIT" in upper_text or "معلق" in upper_text:
        return f"{action}_LIMIT"
    if "STOP" in upper_text:
        return f"{action}_STOP"
    return "MARKET"


def _extract_sl(text: str) -> Optional[float]:
    patterns = [
        r"(?:SL|S/L|STOP\s*LOSS|STOP|ستوب(?:\s*لوز)?|وقف(?:\s*الخسارة)?)\s*[:=\-]?\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _extract_tps(text: str) -> List[float]:
    tps: List[float] = []

    tp_section_matches = re.findall(
        r"(?:TP\s*\d*|T\d+|TARGET\s*\d*|TAKE\s*PROFIT\s*\d*|هدف(?:\s*\d+)?|اهداف|أهداف)\s*[:=\-]?\s*([^\n]+)",
        text,
        flags=re.IGNORECASE
    )

    for section in tp_section_matches:
        cleaned_section = re.split(r"\b(?:SL|S/L|STOP|ستوب|وقف)\b", section, flags=re.IGNORECASE)[0]
        nums = re.findall(r"\d+(?:\.\d+)?", cleaned_section)
        for n in nums:
            val = float(n)
            if val not in tps:
                tps.append(val)

    return tps


def _extract_entry_price(text: str, sl: Optional[float], tps: List[float]) -> Optional[float]:
    entry_patterns = [
        r"(?:ENTRY|PRICE|AT|@|دخول|سعر\s*الدخول|من)\s*[:=\-]?\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in entry_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            val = float(match.group(1))
            if val != sl and val not in tps:
                return val

    after_action = re.search(
        r"(?:\bBUY\b|\bSELL\b|شراء|بيع)\s+(?:NOW|الآن)?\s*[:=\-]?\s*(\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE
    )
    if after_action:
        val = float(after_action.group(1))
        if val != sl and val not in tps:
            return val

    return None


def parse_signal(raw_text: str, default_symbol: Optional[str] = None) -> ParsedSignal:
    """تحليل نص التوصية وإرجاع كائن ParsedSignal منظم مع دعم الرمز الافتراضي"""
    if not raw_text or not raw_text.strip():
        return ParsedSignal(is_valid=False, raw_text=raw_text or "")

    normalized = _normalize_arabic_digits(raw_text)

    symbol = _extract_symbol(normalized) or _resolve_default_symbol(default_symbol)
    action = _extract_action(normalized)
    order_type = _extract_order_type(normalized, action)
    sl = _extract_sl(normalized)
    tps = _extract_tps(normalized)
    entry_price = _extract_entry_price(normalized, sl, tps)

    is_valid = bool(symbol and action)

    return ParsedSignal(
        is_valid=is_valid,
        symbol=symbol,
        action=action,
        order_type=order_type,
        entry_price=entry_price,
        sl=sl,
        tps=tps,
        raw_text=raw_text.strip(),
    )


# --- تجربة سريعة للملف ---
if __name__ == "__main__":
    test_cases = [
        ("شراء من 2650 ستوب 2642 هدف 2665", "XAUUSD"),
        ("بيع من 2660 ستوب 2668 هدف 2648", "ذهب"),
        ("شراء من 2650 ستوب 2642 هدف 2665", None),  # بدون رمز افتراضي -> False
        ("EUR/USD BUY NOW SL 1.0800 TP 1.0860", None),
    ]

    for idx, (msg, default_sym) in enumerate(test_cases, 1):
        res = parse_signal(msg, default_symbol=default_sym)
        print(f"#{idx} | default={default_sym} | valid={res.is_valid} | data={res.to_dict()}")
