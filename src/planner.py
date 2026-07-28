"""
📋 PLANNER — thành phần Cấp 4 (Autonomous Agent), phần BONUS +10%

Khác biệt so với Cấp 3:
    Cấp 3  người dùng đưa 1 câu -> agent tự chọn tool cho tới khi trả lời xong
    Cấp 4  người dùng đưa 1 MỤC TIÊU LỚN -> agent tự chia thành các mục tiêu
           con, chạy lần lượt, và mang kết quả bước trước sang bước sau

Vì sao dừng ở đây mà không làm sâu hơn: Day 02 đã kết luận bài toán này KHÔNG
cần mức Agent tự chủ hoàn toàn, vì mọi hành động ra ngoài (nhắn tin, đặt lịch,
đặt cọc) đều dính tiền thật và phải do người làm. Planner ở đây chỉ tự chủ
trong phạm vi ĐỌC và TÍNH — đúng ranh giới đã chốt.
"""

import json
import re

from prompts import PLANNER_PROMPT

# Kế hoạch dự phòng khi LLM lỗi hoặc trả JSON hỏng — hệ thống không được đứng im
FALLBACK_GOALS = [
    "Tìm danh sách phòng khớp ngân sách và khu vực người dùng nêu",
    "Trích 15 field và tính tổng chi phí thực tế cho các phòng tìm được",
    "Lập bảng so sánh các phòng theo tổng chi phí đã tính được",
    "Soạn tin nhắn hỏi chủ nhà những khoản bài đăng chưa nói",
]


def make_plan(user_query: str, provider, max_goals: int = 4):
    """
    Chia mục tiêu lớn thành các mục tiêu con.

    Returns:
        list[str]: danh sách mục tiêu con (luôn có ít nhất 1, không bao giờ rỗng).
    """
    try:
        raw = provider.generate(PLANNER_PROMPT.format(query=user_query), system_prompt="")
    except Exception:
        return FALLBACK_GOALS[:max_goals]

    if not isinstance(raw, str) or raw.startswith("["):
        return FALLBACK_GOALS[:max_goals]

    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return FALLBACK_GOALS[:max_goals]

    try:
        goals = json.loads(m.group(0)).get("goals", [])
    except json.JSONDecodeError:
        return FALLBACK_GOALS[:max_goals]

    goals = [str(g).strip() for g in goals if str(g).strip()]
    return goals[:max_goals] or FALLBACK_GOALS[:max_goals]
