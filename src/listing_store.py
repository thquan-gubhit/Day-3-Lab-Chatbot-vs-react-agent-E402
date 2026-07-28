"""
🗄️ LỚP TRUY CẬP DỮ LIỆU BÀI ĐĂNG

Tách riêng khỏi tools.py để Role 2 chỉ phải lo phần "hợp đồng công cụ",
không phải lo chuyện đọc file.
"""

import json
import math
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")

FIELDS = [
    "gia_thue", "dien", "nuoc", "gui_xe", "wifi", "rac_dichvu",
    "coc", "phi_moi_gioi",
    "dien_tich", "tang_thang_may", "gac_lung",
    "nau_an", "gio_khoa_cua", "thu_cung",
    "dia_chi",
]

FIELD_LABELS = {
    "gia_thue": "Giá thuê", "dien": "Tiền điện", "nuoc": "Tiền nước",
    "gui_xe": "Gửi xe", "wifi": "Wifi", "rac_dichvu": "Rác / dịch vụ",
    "coc": "Cọc", "phi_moi_gioi": "Phí môi giới", "dien_tich": "Diện tích",
    "tang_thang_may": "Tầng / thang máy", "gac_lung": "Gác lửng",
    "nau_an": "Nấu ăn", "gio_khoa_cua": "Giờ khoá cửa",
    "thu_cung": "Thú cưng", "dia_chi": "Địa chỉ",
}

# 6 khoản tạo nên TỔNG CHI PHÍ HẰNG THÁNG
MONTHLY_FIELDS = ["gia_thue", "dien", "nuoc", "gui_xe", "wifi", "rac_dichvu"]

ST_VALUE = "stated_value"
ST_AMBIGUOUS = "stated_ambiguous"
ST_MISSING = "not_mentioned"

LANDMARKS = {
    "ĐH Bách Khoa TP.HCM": (10.7724, 106.6578),
    "ĐH Kinh tế TP.HCM": (10.7830, 106.6957),
    "ĐH Sư phạm TP.HCM": (10.7620, 106.6820),
    "ĐH Y Dược TP.HCM": (10.7556, 106.6620),
    "ĐH Khoa học Tự nhiên": (10.7620, 106.6822),
    "ĐH Ngoại thương CS2": (10.7960, 106.7130),
    "Chợ Bến Thành": (10.7725, 106.6980),
    "Landmark 81": (10.7950, 106.7218),
}

_listings = None
_by_id = None
_gold = None


def _load():
    global _listings, _by_id, _gold
    if _listings is None:
        with open(os.path.join(CONFIG_DIR, "listings.json"), encoding="utf-8") as f:
            _listings = json.load(f)
        _by_id = {l["id"]: l for l in _listings}
        with open(os.path.join(CONFIG_DIR, "gold_labels.json"), encoding="utf-8") as f:
            _gold = json.load(f)
    return _listings, _by_id, _gold


def all_listings():
    return _load()[0]


def get(listing_id):
    return _load()[1].get((listing_id or "").strip().upper())


def gold(listing_id=None):
    g = _load()[2]
    return g if listing_id is None else g.get((listing_id or "").strip().upper())


def haversine_km(a, b):
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def resolve_landmark(name):
    """Khớp tên địa điểm người dùng nhập với danh sách mốc đã biết."""
    if not name:
        return None, None
    q = name.lower().strip()
    for k, v in LANDMARKS.items():
        if q in k.lower() or k.lower() in q:
            return k, v
    # khớp lỏng theo từ khoá
    alias = {
        "bách khoa": "ĐH Bách Khoa TP.HCM", "bk": "ĐH Bách Khoa TP.HCM",
        "kinh tế": "ĐH Kinh tế TP.HCM", "ueh": "ĐH Kinh tế TP.HCM",
        "sư phạm": "ĐH Sư phạm TP.HCM", "y dược": "ĐH Y Dược TP.HCM",
        "tự nhiên": "ĐH Khoa học Tự nhiên", "ngoại thương": "ĐH Ngoại thương CS2",
        "bến thành": "Chợ Bến Thành", "landmark": "Landmark 81",
    }
    for a, k in alias.items():
        if a in q:
            return k, LANDMARKS[k]
    return None, None


def money(v):
    """850000 -> '850.000đ'"""
    try:
        return f"{int(round(v)):,}đ".replace(",", ".")
    except Exception:
        return str(v)
