"""
🧠 MEMORY — thành phần Cấp 4 (Autonomous Agent), phần BONUS +10%

Agent Cấp 3 quên sạch sau mỗi câu hỏi. Với bài toán tìm trọ thì đó là một
hạn chế thật, không phải hạn chế tưởng tượng: người dùng nói ngân sách ở
lượt 1, tới lượt 4 hỏi "phòng nào rẻ hơn" thì agent đã quên mất ngân sách.

Memory ở đây CỐ Ý chỉ nhớ ràng buộc do người dùng NÓI RA, tách làm hai loại:

    facts       điều người dùng tự khai (ngân sách, nơi cần ở gần, số người)
    findings    điều agent đã xác minh được qua tool

Không nhớ suy đoán. Đây vẫn là luật cứng của nhóm: bot không tự đặt giả định
thay người dùng, nên cũng không được "nhớ" một giả định mà người dùng chưa
từng nói.
"""

import re


class AgentMemory:
    def __init__(self):
        self.facts = {}      # {"ngân sách": "3.5 triệu", ...}
        self.findings = []   # [(goal, kết quả tóm tắt)]
        self.turns = 0

    # ── Rút ràng buộc từ câu người dùng ─────────────────────────────
    def observe_user_message(self, text: str):
        self.turns += 1
        t = (text or "").lower()

        m = re.search(r"(\d+[.,]?\d*)\s*(triệu|tr)\b", t)
        if m:
            self.facts["ngân sách tối đa"] = f"{m.group(1).replace(',', '.')} triệu/tháng"

        m = re.search(r"(gần|cạnh|quanh)\s+([^,.\n]{3,40})", t)
        if m:
            self.facts["cần ở gần"] = m.group(2).strip()

        m = re.search(r"(\d+)\s*người", t)
        if m:
            self.facts["số người ở"] = m.group(1)

        m = re.search(r"(\d+)\s*(số điện|kwh|kw)", t)
        if m:
            self.facts["số kWh/tháng (người dùng tự nhập)"] = m.group(1)

        if re.search(r"(nấu ăn|bếp)", t):
            self.facts["yêu cầu"] = "phải được nấu ăn"
        if re.search(r"(thú cưng|chó|mèo|pet)", t):
            self.facts["yêu cầu thêm"] = "nuôi được thú cưng"

    def remember_result(self, goal: str, answer: str):
        if not answer:
            return
        first = " ".join(answer.strip().split())[:220]
        self.findings.append((goal, first))
        self.findings = self.findings[-5:]  # chỉ giữ 5 kết quả gần nhất

    # ── Đưa memory vào prompt của lượt sau ──────────────────────────
    def as_prompt_block(self) -> str:
        if not self.facts and not self.findings:
            return ""
        out = ["=== BỘ NHỚ HỘI THOẠI (do NGƯỜI DÙNG nói, không phải bạn suy đoán) ==="]
        if self.facts:
            out.append("Ràng buộc người dùng đã nêu:")
            out += [f"  - {k}: {v}" for k, v in self.facts.items()]
        if self.findings:
            out.append("Việc đã làm ở các lượt trước:")
            out += [f"  - {g[:60]} → {a[:120]}" for g, a in self.findings]
        out.append("Hãy dùng các ràng buộc trên thay vì hỏi lại người dùng.")
        out.append("=" * 60)
        out.append("")
        return "\n".join(out)

    def summary(self) -> str:
        if not self.facts:
            return "(chưa ghi nhận ràng buộc nào)"
        return " · ".join(f"{k}: {v}" for k, v in self.facts.items())
