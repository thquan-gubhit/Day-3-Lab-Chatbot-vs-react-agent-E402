"""
🛠️ TOOL REGISTRY & SCHEMAS
(Dành cho Role 2: Tool & Spec Engineer)

Nơi khai báo tất cả các Tool mà ReAct Agent có thể gọi.
"""


def search_listing(location: str, max_price: int) -> str:
    """
    Tìm danh sách nhà trọ/căn hộ theo khu vực và ngân sách.

    Args:
        location (str): Khu vực cần tìm.
        max_price (int): Giá tối đa (VNĐ).

    Returns:
        str: Danh sách các căn hộ phù hợp.
    """

    listings = {
        "cầu giấy": [
            {
                "id": "A101",
                "type": "1PN",
                "price": 7500000,
                "status": "Còn trống"
            },
            {
                "id": "A102",
                "type": "Studio",
                "price": 6800000,
                "status": "Còn trống"
            },
            {
                "id": "A103",
                "type": "2PN",
                "price": 8000000,
                "status": "Đã thuê"
            }
        ],
        "nam từ liêm": [
            {
                "id": "B201",
                "type": "Studio",
                "price": 5500000,
                "status": "Còn trống"
            },
            {
                "id": "B202",
                "type": "1PN",
                "price": 7000000,
                "status": "Còn trống"
            }
        ]
    }

    location = location.lower()

    if location not in listings:
        return f"Không tìm thấy căn hộ tại khu vực '{location}'."

    results = []

    for room in listings[location]:
        if room["price"] <= max_price:
            results.append(
                f"{room['id']} | {room['type']} | {room['price']:,} VNĐ | {room['status']}"
            )

    if not results:
        return "Không có căn hộ phù hợp với ngân sách."

    return "\n".join(results)


def get_listing_detail(listing_id: str) -> str:
    """
    Lấy thông tin chi tiết căn hộ.

    Args:
        listing_id (str): Mã căn hộ.

    Returns:
        str: Thông tin chi tiết.
    """

    database = {
        "A101": {
            "area": "45m²",
            "price": "7,500,000 VNĐ",
            "furniture": "Full nội thất",
            "utilities": "Ban công, Máy giặt, Điều hòa",
            "status": "Còn trống"
        },
        "A102": {
            "area": "35m²",
            "price": "6,800,000 VNĐ",
            "furniture": "Full nội thất",
            "utilities": "Điều hòa",
            "status": "Còn trống"
        },
        "A103": {
            "area": "55m²",
            "price": "8,000,000 VNĐ",
            "furniture": "Full nội thất",
            "utilities": "Ban công, Máy giặt",
            "status": "Đã thuê"
        },
        "B201": {
            "area": "30m²",
            "price": "5,500,000 VNĐ",
            "furniture": "Cơ bản",
            "utilities": "Máy giặt",
            "status": "Còn trống"
        },
        "B202": {
            "area": "40m²",
            "price": "7,000,000 VNĐ",
            "furniture": "Full nội thất",
            "utilities": "Điều hòa, Ban công",
            "status": "Còn trống"
        }
    }

    if listing_id not in database:
        return "LỖI: Không tìm thấy căn hộ."

    room = database[listing_id]

    return (
        f"Mã căn hộ: {listing_id}\n"
        f"Diện tích: {room['area']}\n"
        f"Giá: {room['price']}\n"
        f"Nội thất: {room['furniture']}\n"
        f"Tiện ích: {room['utilities']}\n"
        f"Trạng thái: {room['status']}"
    )


def booking_tool(listing_id: str, date: str, time: str) -> str:
    """
    Đặt lịch xem căn hộ.

    Args:
        listing_id (str): Mã căn hộ.
        date (str): Ngày xem.
        time (str): Giờ xem.

    Returns:
        str: Kết quả đặt lịch.
    """

    unavailable = ["A103"]

    if listing_id in unavailable:
        return (
            f"Không thể đặt lịch.\n"
            f"Căn hộ {listing_id} hiện đã được thuê."
        )

    booking_id = "BK001"

    return (
        "ĐẶT LỊCH THÀNH CÔNG\n"
        f"Booking ID: {booking_id}\n"
        f"Căn hộ: {listing_id}\n"
        f"Ngày xem: {date}\n"
        f"Giờ xem: {time}"
    )


def cancel_booking(booking_id: str) -> str:
    """
    Hủy lịch xem nhà.

    Args:
        booking_id (str): Mã booking.

    Returns:
        str: Kết quả hủy lịch.
    """

    bookings = {
        "BK001": "A101",
        "BK002": "A102",
        "BK003": "B201"
    }

    if booking_id not in bookings:
        return "LỖI: Không tìm thấy booking."

    return (
        "HỦY LỊCH THÀNH CÔNG\n"
        f"Booking ID: {booking_id}\n"
        f"Căn hộ: {bookings[booking_id]}\n"
        "Trạng thái: Cancelled"
    )


def similar_listing(listing_id: str) -> str:
    """
    Gợi ý các căn hộ tương tự.

    Args:
        listing_id (str): Mã căn hộ.

    Returns:
        str: Danh sách căn hộ tương tự.
    """

    similar = {
        "A101": [
            "B202 | 1PN | 7,000,000 VNĐ",
            "A102 | Studio | 6,800,000 VNĐ"
        ],
        "A102": [
            "A101 | 1PN | 7,500,000 VNĐ",
            "B201 | Studio | 5,500,000 VNĐ"
        ],
        "A103": [
            "A101 | 1PN | 7,500,000 VNĐ",
            "B202 | 1PN | 7,000,000 VNĐ"
        ]
    }

    if listing_id not in similar:
        return "Không tìm thấy căn hộ tương tự."

    return "Các căn hộ gợi ý:\n" + "\n".join(similar[listing_id])


# =====================================================
# TOOL REGISTRY
# =====================================================

AVAILABLE_TOOLS = {
    "search_listing": search_listing,
    "get_listing_detail": get_listing_detail,
    "booking_tool": booking_tool,
    "cancel_booking": cancel_booking,
    "similar_listing": similar_listing,
}