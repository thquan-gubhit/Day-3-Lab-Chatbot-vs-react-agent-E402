"""
🛠️ TOOL REGISTRY — TRỢ LÝ SO SÁNH PHÒNG TRỌ  (Role 2: Tool & Spec Engineer)

Chủ đề nhóm: Đề tài #10 — Trợ Lý Tìm & So Sánh Phòng Trọ Cho Thuê
Kế thừa Problem Statement v1 đã chốt ở Lab Day 02.

NGUYÊN TẮC CHUNG CHO MỌI TOOL
─────────────────────────────────────────────────────────────────────────
1. Không bao giờ raise. Lỗi nghiệp vụ là DỮ LIỆU để Agent suy luận tiếp,
   nên mọi lỗi được trả về dạng chuỗi bắt đầu bằng "LỖI:".
2. Không tool nào có side effect ra thế giới thật (read-only toàn bộ).
3. Không tool nào được trả về số mà bài đăng không nói.

⛔ HAI TOOL CỐ Ý KHÔNG TỒN TẠI — VÀ ĐÓ LÀ MỘT QUYẾT ĐỊNH THIẾT KẾ
─────────────────────────────────────────────────────────────────────────
    send_message_to_landlord()   ❌ không có
    book_viewing_appointment()   ❌ không có

Day 02 mục 2.4 đã chốt: bot KHÔNG được tự nhắn môi giới và KHÔNG được tự
đặt lịch xem, vì đây là bước dính tiền thật (cọc 1-2 tháng, hợp đồng 12
tháng). Agent chỉ SOẠN SẴN tin nhắn (draft_question_message) để người dùng
tự đọc, tự sửa, tự gửi.

Việc thiếu hai tool này không phải làm chưa xong — nó là ranh giới người/máy
được cài đặt ở tầng năng lực, chứ không phải chỉ dặn dò trong prompt. Agent
không thể vượt ranh giới kể cả khi người dùng yêu cầu.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import listing_store as store
from listing_store import (FIELD_LABELS, MONTHLY_FIELDS, ST_AMBIGUOUS,
                           ST_MISSING, ST_VALUE, money)

_provider = None


def set_provider(p):
    """App gọi hàm này một lần lúc khởi động để tool dùng chung 1 provider."""
    global _provider
    _provider = p


def _extract(listing_id):
    import extractor
    return extractor.extract_listing(listing_id, provider=_provider)


# ═══════════════════════════════════════════════════════════════════════
# TOOL 1 — search_listings
# ═══════════════════════════════════════════════════════════════════════
def search_listings(max_price: str = "", khu_vuc: str = "", gan: str = "",
                    nau_an: str = "", limit: str = "8") -> str:
    """
    Tìm các bài đăng phòng trọ khớp tiêu chí. Dùng ĐẦU TIÊN khi người dùng
    muốn tìm phòng theo ngân sách / khu vực / gần một địa điểm.

    Args:
        max_price (str): Ngân sách tối đa mỗi tháng, VNĐ. VD: "3500000" hoặc "3.5tr".
                         Lọc theo GIÁ THUÊ ghi trong bài (chưa gồm điện nước).
        khu_vuc (str): Tên quận hoặc khu. VD: "Quận 10", "Bình Thạnh".
        gan (str): Tên địa điểm cần ở gần. VD: "ĐH Bách Khoa".
        nau_an (str): "true" nếu bắt buộc được nấu ăn.
        limit (str): Số kết quả tối đa, mặc định 8.

    Returns:
        str: Danh sách phòng khớp + MỤC RIÊNG "chưa đọc được giá".

    Error: Trả "LỖI: ..." nếu tham số sai định dạng.

    Side effect: Không (chỉ đọc).

    ⚠️ Tool này CỐ Ý trả về cả những phòng KHÔNG đọc được giá, ở một mục
    riêng. Luật cứng 3 của nhóm: phòng bot không đọc được vẫn phải hiện ra,
    không được im lặng loại bỏ — vì loại nhầm một phòng tốt là lỗi người
    dùng KHÔNG nhìn thấy được.
    """
    try:
        budget = _parse_money(max_price) if str(max_price).strip() else None
    except ValueError as e:
        return f"LỖI: {e}"

    try:
        n = int(str(limit).strip() or 8)
    except ValueError:
        n = 8
    n = max(1, min(n, 25))

    want_cook = str(nau_an).strip().lower() in ("true", "có", "co", "yes", "1")
    lm_name, lm_coord = store.resolve_landmark(gan) if str(gan).strip() else (None, None)
    if str(gan).strip() and not lm_coord:
        return (f"LỖI: Không nhận ra địa điểm '{gan}'. "
                f"Các địa điểm đã biết: {', '.join(store.LANDMARKS.keys())}")

    matched, unreadable = [], []

    for lst in store.all_listings():
        if lst["status"] == "rented":
            continue
        if str(khu_vuc).strip():
            q = khu_vuc.lower().strip()
            if q not in lst["quan"].lower() and q not in lst["khu_vuc"].lower():
                continue

        f = _extract(lst["id"])
        if "_error" in f and f.get("gia_thue", {}).get("status") != ST_VALUE:
            unreadable.append((lst, "lỗi trích xuất"))
            continue

        gia_cell = f.get("gia_thue", {"status": ST_MISSING})
        if gia_cell["status"] != ST_VALUE:
            # Không đọc được giá từ bài viết (thường vì giá nằm trong ảnh)
            unreadable.append((lst, "bài đăng không ghi giá bằng chữ"))
            continue

        gia = (gia_cell.get("value") or {}).get("amount")
        if not isinstance(gia, (int, float)):
            unreadable.append((lst, "giá không đọc được"))
            continue
        if budget is not None and gia > budget:
            continue

        if want_cook:
            c = f.get("nau_an", {})
            if not (c.get("status") == ST_VALUE and (c.get("value") or {}).get("allowed") is True):
                continue

        dist = None
        if lm_coord:
            addr = f.get("dia_chi", {})
            if addr.get("status") == ST_VALUE:
                dist = store.haversine_km(lst["coords"], lm_coord)
                if dist > 6.0:
                    continue
            else:
                continue

        matched.append((lst, gia, dist))

    matched.sort(key=lambda x: (x[2] if x[2] is not None else 0, x[1]))
    matched = matched[:n]

    if not matched and not unreadable:
        return "Không có phòng nào khớp tiêu chí. Thử nới ngân sách hoặc đổi khu vực."

    lines = [f"Tìm thấy {len(matched)} phòng khớp tiêu chí"
             + (f" (gần {lm_name})" if lm_name else "") + ":"]
    for lst, gia, dist in matched:
        d = f" · cách {dist:.1f}km" if dist is not None else ""
        dup = f" · TRÙNG với {lst['duplicate_of']}" if lst.get("duplicate_of") else ""
        lines.append(f"  {lst['id']} | {money(gia)}/tháng | {lst['khu_vuc']}, {lst['quan']}{d}{dup}")

    if unreadable:
        lines.append("")
        lines.append(f"⚠️ {len(unreadable)} phòng CHƯA ĐỌC ĐƯỢC GIÁ — không bị loại bỏ, "
                     f"cần người dùng tự mở xem:")
        for lst, why in unreadable[:6]:
            lines.append(f"  {lst['id']} | {lst['khu_vuc']}, {lst['quan']} | lý do: {why}")
        if len(unreadable) > 6:
            lines.append(f"  ... và {len(unreadable) - 6} phòng khác")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# TOOL 2 — get_listing_raw
# ═══════════════════════════════════════════════════════════════════════
def get_listing_raw(listing_id: str) -> str:
    """
    Lấy NGUYÊN VĂN bài đăng gốc. Dùng khi cần kiểm chứng lại một thông tin,
    hoặc khi người dùng hỏi "bài gốc viết gì".

    Args:
        listing_id (str): Mã phòng, VD "P012".

    Returns:
        str: Toàn văn bài đăng + metadata (nhóm, người đăng, ngày, trạng thái).

    Error: "LỖI: Không tìm thấy bài đăng ..."

    Side effect: Không.
    """
    lst = store.get(listing_id)
    if not lst:
        return f"LỖI: Không tìm thấy bài đăng '{listing_id}'. Mã hợp lệ có dạng P001..P070."

    head = (f"[{lst['id']}] Đăng bởi {lst['author']} · nhóm \"{lst['group']}\" · "
            f"ngày {lst['posted_at']} · trạng thái: "
            f"{'ĐÃ CHO THUÊ' if lst['status'] == 'rented' else 'đang cho thuê'}")
    body = lst["raw_text"]
    note = ""
    if lst.get("image_only_price"):
        note = ("\n\n[GHI CHÚ HỆ THỐNG] Bài này có ảnh đính kèm và giá dường như nằm "
                "TRONG ẢNH. Hệ thống không đọc được chữ trong ảnh, nên KHÔNG có giá "
                "từ bài đăng này. Không được suy đoán giá.")
    return f"{head}\n{'-' * 60}\n{body}{note}"


# ═══════════════════════════════════════════════════════════════════════
# TOOL 3 — extract_listing_fields
# ═══════════════════════════════════════════════════════════════════════
def extract_listing_fields(listing_id: str) -> str:
    """
    Trích 15 field chuẩn từ một bài đăng, mỗi ô kèm TRÍCH NGUYÊN VĂN.
    Đây là tool quan trọng nhất — dùng trước khi tính tiền hoặc so sánh.

    Args:
        listing_id (str): Mã phòng, VD "P012".

    Returns:
        str: Bảng 15 field. Mỗi ô là một trong ba trạng thái:
             - có số/rõ ràng  : kèm trích dẫn nguyên văn từ bài gốc
             - ⚠️ mơ hồ       : bài có nhắc nhưng không quy ra số được
             - ❓ bài không nói: KHÔNG được suy đoán, phải đi hỏi chủ nhà

    Error: "LỖI: ..." nếu không tìm thấy bài hoặc LLM lỗi.

    Side effect: Không (có cache trên đĩa để đỡ tốn token).
    """
    lst = store.get(listing_id)
    if not lst:
        return f"LỖI: Không tìm thấy bài đăng '{listing_id}'. Mã hợp lệ có dạng P001..P070."

    f = _extract(lst["id"])
    if "_error" in f and all(v.get("status") == ST_MISSING
                             for k, v in f.items() if not k.startswith("_")):
        return f"LỖI: Không trích được bài {lst['id']} — {f['_error']}"

    lines = [f"15 field của {lst['id']} ({lst['khu_vuc']}, {lst['quan']}):"]
    n_missing = 0
    for key in store.FIELDS:
        cell = f.get(key, {"status": ST_MISSING})
        label = FIELD_LABELS[key]
        if cell["status"] == ST_VALUE:
            lines.append(f"  {label:<18}: {_fmt_value(key, cell.get('value'))}"
                         f"   « {cell.get('quote')} »")
        elif cell["status"] == ST_AMBIGUOUS:
            lines.append(f"  {label:<18}: ⚠️ MƠ HỒ — không quy ra số được"
                         f"   « {cell.get('quote')} »")
        else:
            n_missing += 1
            lines.append(f"  {label:<18}: ❓ bài đăng KHÔNG nói")

    lines.append(f"\n➜ {n_missing}/15 ô bài đăng không nói. Các ô ❓ phải đi hỏi chủ nhà, "
                 f"TUYỆT ĐỐI không được điền số suy đoán.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# TOOL 4 — compute_total_cost
# ═══════════════════════════════════════════════════════════════════════
def compute_total_cost(listing_id: str, so_kwh: str = "", so_nguoi: str = "",
                       so_khoi_nuoc: str = "") -> str:
    """
    Cộng TỔNG CHI PHÍ THỰC TẾ mỗi tháng, tách làm ba cột riêng biệt.
    Dùng sau khi đã extract_listing_fields.

    Args:
        listing_id (str): Mã phòng.
        so_kwh (str): Số điện dự kiến dùng mỗi tháng (do NGƯỜI DÙNG nhập).
        so_nguoi (str): Số người ở (để tính nước tính theo đầu người).
        so_khoi_nuoc (str): Số khối nước dự kiến mỗi tháng.

    Returns:
        str: Ba cột — CHẮC CHẮN / ƯỚC LƯỢNG / CHƯA TÍNH ĐƯỢC.

    Error: "LỖI: ..." nếu không có bài hoặc không có cả giá thuê.

    Side effect: Không.

    ⚠️ Giả định tiêu thụ (số kWh, số người, số khối) do NGƯỜI DÙNG nhập.
    Tool KHÔNG tự đặt giả định thay người dùng — nếu thiếu, khoản đó rơi
    vào cột "chưa tính được" chứ không bị đoán bừa. Đây là luật cứng 2.
    """
    lst = store.get(listing_id)
    if not lst:
        return f"LỖI: Không tìm thấy bài đăng '{listing_id}'."

    f = _extract(lst["id"])
    gia_cell = f.get("gia_thue", {"status": ST_MISSING})
    if gia_cell.get("status") != ST_VALUE:
        return (f"LỖI: Bài {lst['id']} không ghi giá thuê bằng chữ nên KHÔNG tính được tổng. "
                f"Phòng này thuộc mục 'chưa đọc được', cần người dùng tự mở bài gốc xem.")

    kwh = _to_float(so_kwh)
    nguoi = _to_float(so_nguoi)
    khoi = _to_float(so_khoi_nuoc)

    chac_chan, uoc_luong, chua_tinh = [], [], []

    gia = (gia_cell.get("value") or {}).get("amount") or 0
    chac_chan.append(("Giá thuê", gia, gia_cell.get("quote")))

    def handle(key, label):
        cell = f.get(key, {"status": ST_MISSING})
        st = cell.get("status")
        val = cell.get("value") or {}
        quote = cell.get("quote")

        if st == ST_MISSING:
            chua_tinh.append((label, "❓ bài đăng không nói — phải đi hỏi chủ nhà"))
            return
        if st == ST_AMBIGUOUS:
            chua_tinh.append((label, f"⚠️ mơ hồ, không quy ra số được « {quote} »"))
            return

        mode = val.get("mode")
        if mode == "included":
            chac_chan.append((label + " (đã bao)", 0, quote))
        elif mode == "per_month":
            chac_chan.append((label, val.get("price") or 0, quote))
        elif mode == "per_kwh":
            price = val.get("price") or 0
            if kwh is None:
                chua_tinh.append((label, f"có đơn giá {money(price)}/kWh nhưng "
                                         f"CHƯA BIẾT số kWh/tháng — cần người dùng nhập"))
            else:
                uoc_luong.append((f"{label} ({money(price)}/kWh × {kwh:g} kWh)",
                                  price * kwh, quote))
        elif mode == "per_person":
            price = val.get("price") or 0
            if nguoi is None:
                chua_tinh.append((label, f"có đơn giá {money(price)}/người nhưng "
                                         f"CHƯA BIẾT số người ở — cần người dùng nhập"))
            else:
                uoc_luong.append((f"{label} ({money(price)}/người × {nguoi:g} người)",
                                  price * nguoi, quote))
        elif mode == "per_m3":
            price = val.get("price") or 0
            if khoi is None:
                chua_tinh.append((label, f"có đơn giá {money(price)}/khối nhưng "
                                         f"CHƯA BIẾT số khối/tháng — cần người dùng nhập"))
            else:
                uoc_luong.append((f"{label} ({money(price)}/khối × {khoi:g} khối)",
                                  price * khoi, quote))
        else:
            chua_tinh.append((label, f"không hiểu cách tính « {quote} »"))

    handle("dien", "Tiền điện")
    handle("nuoc", "Tiền nước")
    handle("gui_xe", "Gửi xe")
    handle("wifi", "Wifi")
    handle("rac_dichvu", "Rác / dịch vụ")

    t_chac = sum(v for _, v, _ in chac_chan)
    t_uoc = sum(v for _, v, _ in uoc_luong)

    out = [f"TỔNG CHI PHÍ HẰNG THÁNG — {lst['id']} ({lst['khu_vuc']}, {lst['quan']})", ""]
    out.append("✅ CHẮC CHẮN (bài đăng ghi rõ):")
    for label, v, q in chac_chan:
        out.append(f"     {label:<28} {money(v):>12}   « {q} »")
    out.append(f"     {'CỘNG CHẮC CHẮN':<28} {money(t_chac):>12}")

    out.append("")
    if uoc_luong:
        out.append("🔶 ƯỚC LƯỢNG (đơn giá × giả định NGƯỜI DÙNG nhập — KHÔNG trộn vào cột trên):")
        for label, v, q in uoc_luong:
            out.append(f"     {label:<28} {money(v):>12}   « {q} »")
        out.append(f"     {'CỘNG ƯỚC LƯỢNG':<28} {money(t_uoc):>12}")
    else:
        out.append("🔶 ƯỚC LƯỢNG: (không có — hoặc thiếu giả định tiêu thụ của người dùng)")

    out.append("")
    if chua_tinh:
        out.append("❓ CHƯA TÍNH ĐƯỢC — các khoản này KHÔNG có trong tổng:")
        for label, why in chua_tinh:
            out.append(f"     {label:<20} {why}")
    else:
        out.append("❓ CHƯA TÍNH ĐƯỢC: không có — bài đăng này đủ thông tin.")

    out.append("")
    out.append(f"➜ TỔNG (chắc chắn + ước lượng) = {money(t_chac + t_uoc)}/tháng")
    if chua_tinh:
        out.append(f"➜ ⚠️ Con số trên CHƯA đầy đủ: còn {len(chua_tinh)} khoản chưa tính được. "
                   f"Tổng thật sẽ CAO HƠN. Không được coi đây là tổng cuối cùng.")
    return "\n".join(out)


# ═══════════════════════════════════════════════════════════════════════
# TOOL 5 — estimate_commute
# ═══════════════════════════════════════════════════════════════════════
def estimate_commute(listing_id: str, den: str) -> str:
    """
    Ước tính quãng đường và thời gian đi xe máy từ phòng tới một địa điểm.
    (Mô phỏng API bản đồ — Day 02 đã kết luận bước này là API, KHÔNG cần AI.)

    Args:
        listing_id (str): Mã phòng.
        den (str): Địa điểm đích, VD "ĐH Bách Khoa".

    Returns:
        str: Khoảng cách km và thời gian phút (giờ thường / giờ cao điểm).

    Error: "LỖI: ..." nếu địa chỉ bài đăng quá mơ hồ để tra đường.

    Side effect: Không.
    """
    lst = store.get(listing_id)
    if not lst:
        return f"LỖI: Không tìm thấy bài đăng '{listing_id}'."

    lm_name, lm_coord = store.resolve_landmark(den)
    if not lm_coord:
        return (f"LỖI: Không nhận ra địa điểm '{den}'. "
                f"Các địa điểm đã biết: {', '.join(store.LANDMARKS.keys())}")

    f = _extract(lst["id"])
    addr = f.get("dia_chi", {"status": ST_MISSING})
    if addr.get("status") != ST_VALUE:
        q = addr.get("quote")
        return (f"LỖI: Bài {lst['id']} không có địa chỉ đủ cụ thể để tra đường đi"
                + (f" (bài chỉ ghi « {q} »)" if q else "")
                + ". Cần hỏi chủ nhà địa chỉ chính xác trước.")

    km = store.haversine_km(lst["coords"], lm_coord) * 1.35  # hệ số đường thực tế
    phut = km / 22 * 60
    return (f"{lst['id']} → {lm_name}: khoảng {km:.1f} km, "
            f"đi xe máy ~{phut:.0f} phút (giờ thường), "
            f"~{phut * 1.5:.0f} phút (giờ cao điểm).")


# ═══════════════════════════════════════════════════════════════════════
# TOOL 6 — compare_listings
# ═══════════════════════════════════════════════════════════════════════
def compare_listings(listing_ids: str, so_kwh: str = "", so_nguoi: str = "") -> str:
    """
    Lập bảng so sánh nhiều phòng cạnh nhau, sắp theo tổng chi phí đã tính được.

    Args:
        listing_ids (str): Danh sách mã ngăn cách bởi dấu phẩy. VD "P003,P012,P045".
        so_kwh (str): Giả định số kWh/tháng do người dùng nhập.
        so_nguoi (str): Số người ở.

    Returns:
        str: Bảng so sánh + cột "số ô còn thiếu" của từng phòng.

    Error: "LỖI: ..." nếu danh sách rỗng hoặc mã sai.

    Side effect: Không.

    ⚠️ Tool này CỐ Ý KHÔNG xếp hạng và KHÔNG chấm điểm phòng nào tốt nhất.
    Nó chỉ sắp theo con số tổng và luôn hiện kèm số ô còn thiếu, để người
    dùng tự đọc và tự quyết. Day 02 mục 4.3 đã bỏ hẳn tính năng xếp hạng
    sau khi đọc PAIR Explainability: bot xếp hạng thì người dùng ngừng kiểm.
    """
    ids = [i.strip().upper() for i in str(listing_ids).replace(";", ",").split(",") if i.strip()]
    if not ids:
        return "LỖI: Chưa truyền danh sách mã phòng. VD: compare_listings[\"P003,P012\"]"
    if len(ids) > 8:
        return f"LỖI: Chỉ so sánh tối đa 8 phòng một lần (bạn đưa {len(ids)})."

    kwh = _to_float(so_kwh)
    nguoi = _to_float(so_nguoi)

    rows, bad = [], []
    for pid in ids:
        lst = store.get(pid)
        if not lst:
            bad.append(pid)
            continue
        f = _extract(pid)
        gia_cell = f.get("gia_thue", {"status": ST_MISSING})
        if gia_cell.get("status") != ST_VALUE:
            rows.append({"id": pid, "readable": False, "khu": f"{lst['khu_vuc']}, {lst['quan']}"})
            continue

        gia = (gia_cell.get("value") or {}).get("amount") or 0
        tong, thieu = gia, 0
        for key in ["dien", "nuoc", "gui_xe", "wifi", "rac_dichvu"]:
            c = f.get(key, {"status": ST_MISSING})
            if c.get("status") != ST_VALUE:
                thieu += 1
                continue
            v = c.get("value") or {}
            m = v.get("mode")
            if m == "included":
                pass
            elif m == "per_month":
                tong += v.get("price") or 0
            elif m == "per_kwh" and kwh is not None:
                tong += (v.get("price") or 0) * kwh
            elif m == "per_person" and nguoi is not None:
                tong += (v.get("price") or 0) * nguoi
            else:
                thieu += 1
        rows.append({"id": pid, "readable": True, "gia": gia, "tong": tong, "thieu": thieu,
                     "khu": f"{lst['khu_vuc']}, {lst['quan']}",
                     "dup": lst.get("duplicate_of")})

    ok = [r for r in rows if r["readable"]]
    ok.sort(key=lambda r: r["tong"])
    out = ["BẢNG SO SÁNH (sắp theo tổng đã tính được — KHÔNG phải xếp hạng chất lượng)", ""]
    out.append(f"  {'Mã':<6}{'Giá thuê':>13}{'Tổng tính được':>17}{'Ô thiếu':>9}  Khu vực")
    for r in ok:
        dup = f"  [trùng {r['dup']}]" if r.get("dup") else ""
        out.append(f"  {r['id']:<6}{money(r['gia']):>13}{money(r['tong']):>17}"
                   f"{str(r['thieu']) + '/5':>9}  {r['khu']}{dup}")

    unread = [r for r in rows if not r["readable"]]
    if unread:
        out.append("")
        out.append("⚠️ CHƯA ĐỌC ĐƯỢC GIÁ (không bị loại khỏi bảng, cần người tự xem):")
        for r in unread:
            out.append(f"  {r['id']:<6} {r['khu']}")

    if bad:
        out.append("")
        out.append(f"LỖI một phần: không tìm thấy mã {', '.join(bad)}")

    if ok:
        max_thieu = max(r["thieu"] for r in ok)
        if max_thieu > 0:
            out.append("")
            out.append("➜ ⚠️ Cột 'Tổng tính được' KHÔNG so sánh được công bằng: các phòng "
                       "thiếu số ô khác nhau, phòng thiếu nhiều ô trông rẻ hơn thực tế. "
                       "Hãy dùng draft_question_message để hỏi bù các ô ❓ trước khi kết luận.")
    return "\n".join(out)


# ═══════════════════════════════════════════════════════════════════════
# TOOL 7 — draft_question_message
# ═══════════════════════════════════════════════════════════════════════
def draft_question_message(listing_id: str) -> str:
    """
    SOẠN SẴN tin nhắn hỏi chủ nhà về đúng những ô mà bài đăng không nói.
    Người dùng tự copy, tự sửa và tự gửi — bot KHÔNG gửi.

    Args:
        listing_id (str): Mã phòng.

    Returns:
        str: Nội dung tin nhắn gợi ý, kèm nhắc rằng người dùng phải tự gửi.

    Error: "LỖI: ..." nếu không tìm thấy bài.

    Side effect: KHÔNG — tool này chỉ sinh văn bản, không gửi đi đâu cả.
    """
    lst = store.get(listing_id)
    if not lst:
        return f"LỖI: Không tìm thấy bài đăng '{listing_id}'."

    f = _extract(lst["id"])
    hoi = []
    ask_map = {
        "gia_thue": "giá thuê một tháng",
        "dien": "tiền điện tính thế nào ạ (bao nhiêu một số)",
        "nuoc": "tiền nước tính thế nào ạ (theo người hay theo khối)",
        "gui_xe": "gửi xe máy có mất phí không, bao nhiêu một tháng",
        "wifi": "wifi có tính thêm tiền không ạ",
        "rac_dichvu": "phí rác/dịch vụ hàng tháng",
        "coc": "cọc mấy tháng ạ",
        "phi_moi_gioi": "có mất phí môi giới không ạ",
        "dien_tich": "phòng bao nhiêu m2",
        "tang_thang_may": "phòng ở tầng mấy, có thang máy không",
        "nau_an": "có được nấu ăn trong phòng không ạ",
        "gio_khoa_cua": "mấy giờ khoá cửa ạ",
        "thu_cung": "có được nuôi thú cưng không",
        "dia_chi": "địa chỉ cụ thể của phòng",
    }
    for key, text in ask_map.items():
        cell = f.get(key, {"status": ST_MISSING})
        if cell.get("status") == ST_MISSING:
            hoi.append(text)
        elif cell.get("status") == ST_AMBIGUOUS and key in ("dien", "nuoc", "dia_chi"):
            hoi.append(text + " (bài ghi chưa rõ)")

    if not hoi:
        return (f"Bài {lst['id']} đã đủ thông tin, không cần hỏi thêm khoản nào.")

    hoi = hoi[:7]
    body = ("Chào anh/chị, em thấy bài đăng phòng ở "
            f"{lst['khu_vuc']}, {lst['quan']} ạ. Em muốn hỏi thêm mấy ý:\n"
            + "\n".join(f"  {i}. Cho em hỏi {h} ạ?" for i, h in enumerate(hoi, 1))
            + "\nEm cảm ơn anh/chị nhiều ạ!")

    return (f"TIN NHẮN GỢI Ý cho {lst['id']} (hỏi {len(hoi)} ô còn thiếu):\n"
            f"{'-' * 60}\n{body}\n{'-' * 60}\n"
            f"⚠️ Bot KHÔNG gửi tin này. Bạn hãy tự đọc lại, sửa nếu cần và tự nhắn "
            f"cho chủ nhà — đây là ranh giới người/máy nhóm đã chốt từ Day 02.")


# ═══════════════════════════════════════════════════════════════════════
# TIỆN ÍCH NỘI BỘ
# ═══════════════════════════════════════════════════════════════════════
def _parse_money(s):
    """'3.5tr' / '3500000' / '3tr5' -> 3500000"""
    t = str(s).lower().strip().replace(" ", "").replace(",", ".")
    t = t.replace("vnđ", "").replace("vnd", "").replace("đ", "").replace("/tháng", "")
    if not t:
        raise ValueError("giá rỗng")
    if "tr" in t:
        a, _, b = t.partition("tr")
        try:
            v = float(a) * 1_000_000 if a else 0
        except ValueError:
            raise ValueError(f"không hiểu số tiền '{s}'")
        if b:
            b = b.strip(".")
            if b.isdigit():
                v += float(b) * (100_000 if len(b) == 1 else 10_000 if len(b) == 2 else 1)
        return v
    if t.endswith("k"):
        try:
            return float(t[:-1]) * 1000
        except ValueError:
            raise ValueError(f"không hiểu số tiền '{s}'")
    t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"không hiểu số tiền '{s}'. Dùng dạng '3500000' hoặc '3.5tr'.")


def _to_float(s):
    t = str(s).strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _fmt_value(key, v):
    if not isinstance(v, dict):
        return str(v)
    if key == "gia_thue":
        return f"{money(v.get('amount'))}/tháng"
    if key == "dien_tich":
        return f"{v.get('m2')}m²"
    if key == "tang_thang_may":
        return f"tầng {v.get('floor')}, {'có' if v.get('elevator') else 'không'} thang máy"
    if key == "gac_lung":
        return "có gác" if v.get("has") else "không gác"
    if key == "nau_an":
        return "được nấu ăn" if v.get("allowed") else "KHÔNG được nấu ăn"
    if key == "thu_cung":
        return "được nuôi thú cưng" if v.get("allowed") else "KHÔNG được nuôi thú cưng"
    if key == "gio_khoa_cua":
        return "tự do 24/24" if v.get("free") else f"khoá cửa {v.get('time')}"
    if key == "dia_chi":
        return v.get("text", "")
    mode = v.get("mode")
    if mode == "included":
        return "đã bao trong giá thuê (0đ)"
    if mode == "per_month":
        return f"{money(v.get('price'))}/tháng"
    if mode == "per_kwh":
        return f"{money(v.get('price'))}/kWh"
    if mode == "per_person":
        return f"{money(v.get('price'))}/người/tháng"
    if mode == "per_m3":
        return f"{money(v.get('price'))}/khối"
    if mode == "months":
        return f"{v.get('n')} tháng tiền thuê"
    if mode == "amount":
        return money(v.get("price"))
    if mode == "none":
        return "không mất phí"
    return str(v)


# ═══════════════════════════════════════════════════════════════════════
# ĐĂNG KÝ TOOL
# ═══════════════════════════════════════════════════════════════════════
AVAILABLE_TOOLS = {
    "search_listings": search_listings,
    "get_listing_raw": get_listing_raw,
    "extract_listing_fields": extract_listing_fields,
    "compute_total_cost": compute_total_cost,
    "estimate_commute": estimate_commute,
    "compare_listings": compare_listings,
    "draft_question_message": draft_question_message,
}

# Mô tả ngắn để nhúng vào REACT_SYSTEM_PROMPT (Role 3 dùng)
TOOL_SPECS = [
    ("search_listings",
     'search_listings[max_price, khu_vuc, gan, nau_an]',
     "Tìm phòng theo ngân sách/khu vực/gần địa điểm. Trả cả mục 'chưa đọc được giá'."),
    ("get_listing_raw",
     'get_listing_raw["P012"]',
     "Lấy nguyên văn bài đăng gốc để kiểm chứng."),
    ("extract_listing_fields",
     'extract_listing_fields["P012"]',
     "Trích 15 field kèm trích dẫn nguyên văn; ô nào bài không nói thì hiện ❓."),
    ("compute_total_cost",
     'compute_total_cost["P012", so_kwh, so_nguoi, so_khoi_nuoc]',
     "Cộng tổng/tháng, tách 3 cột: chắc chắn / ước lượng / chưa tính được."),
    ("estimate_commute",
     'estimate_commute["P012", "ĐH Bách Khoa"]',
     "Ước tính km và phút đi xe máy tới một địa điểm."),
    ("compare_listings",
     'compare_listings["P003,P012,P045", so_kwh, so_nguoi]',
     "Lập bảng so sánh nhiều phòng, kèm số ô còn thiếu của từng phòng."),
    ("draft_question_message",
     'draft_question_message["P012"]',
     "Soạn sẵn tin nhắn hỏi các ô còn thiếu. Bot KHÔNG gửi, người dùng tự gửi."),
]
