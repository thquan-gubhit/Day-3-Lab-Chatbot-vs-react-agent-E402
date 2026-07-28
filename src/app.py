"""
🚀 CORE APP — TRỢ LÝ SO SÁNH PHÒNG TRỌ  (Role 4: Core Developer / Integrator)

Ghép nối: tools.py (Role 2) + prompts.py (Role 3) + test_cases.json (Role 1)
         + providers.py (multi-provider) + memory.py/planner.py (bonus Cấp 4)

Ba chế độ chạy, dùng chung một bộ test case để so sánh công bằng:
    CẤP 2  run_baseline_chatbot()  — 1 LLM call, 0 tool
    CẤP 3  run_react_agent()       — vòng lặp Thought -> Action -> Observation
    CẤP 4  run_autonomous_agent()  — Planning + Memory (phần bonus)

Chạy:
    python src/app.py                 # demo so sánh Chatbot vs Agent
    python src/app.py --chat          # chế độ hội thoại
    python src/app.py --case 4        # chạy đúng 1 test case
    python src/app.py --auto          # demo Cấp 4 (Planning + Memory)
"""

import json
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

import agent_core
import tools as tools_mod
from agent_core import (INJECTION_BANNER, Trace, cut_hallucinated_observation,
                        detect_injection, parse_action, parse_final_answer,
                        parse_thought, run_tool_safely)
from prompts import (CHATBOT_BASELINE_PROMPT, GUARDRAIL_LOOP_MESSAGE,
                     GUARDRAIL_MAX_ITER_MESSAGE, MAX_ITERATIONS,
                     MAX_REPEATED_ACTION, MAX_TOOL_OUTPUT_CHARS,
                     PARSE_ERROR_HINT, REACT_SYSTEM_PROMPT, TIMEOUT_SECONDS,
                     UNKNOWN_TOOL_HINT)
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_test_cases():
    """Đọc bộ test cases của Role 1."""
    p = os.path.join(BASE_DIR, "config", "test_cases.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════
# CẤP 2 — CHATBOT BASELINE (1 LLM call, KHÔNG tool)
# ═══════════════════════════════════════════════════════════════════════
def run_baseline_chatbot(user_query: str, provider, on_event=None) -> Trace:
    """
    Đường cơ sở để so sánh: đúng một lần gọi LLM, không công cụ, không vòng lặp.

    Giữ baseline "trần trụi" là cố ý. Nếu ta vá guardrail hay nhét sẵn dữ liệu
    phòng vào prompt baseline thì phép so sánh mất ý nghĩa — sẽ không phân biệt
    được đâu là công của TOOL, đâu là công của PROMPT.
    """
    tr = Trace(user_query, mode="chatbot")
    if on_event:
        on_event("start", {"mode": "chatbot", "query": user_query})

    t0 = time.time()
    answer = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    tr.llm_calls = 1
    tr.tool_calls = 0
    tr.final_answer = (answer or "").strip()
    tr.stop_reason = "single_llm_call"
    tr.add_step(thought=None, action=None, observation=None,
                raw=tr.final_answer, elapsed=round(time.time() - t0, 2))

    if on_event:
        on_event("final", {"answer": tr.final_answer, "trace": tr.to_dict()})
    return tr


# ═══════════════════════════════════════════════════════════════════════
# CẤP 3 — REACT AGENT LOOP
# ═══════════════════════════════════════════════════════════════════════
def run_react_agent(user_query: str, provider, on_event=None,
                    max_iterations: int = MAX_ITERATIONS,
                    memory_block: str = "") -> Trace:
    """
    Vòng lặp ReAct: Thought -> Action -> Observation -> ... -> Final Answer.

    Bốn nguyên tắc bất biến (CODELAB mục 4) được cài đặt ở đâu:
      1. Không lặp vô hạn      -> max_iterations + phát hiện lặp cùng action
      2. Mỗi Action đúng 1 Obs -> cut_hallucinated_observation() cắt phần LLM tự bịa
      3. Observation quay lại prompt -> `transcript` được nối vào mỗi lượt
      4. Không kết luận khi thiếu bằng chứng -> luật cứng trong REACT_SYSTEM_PROMPT
                                                + tool trả "LỖI:" thay vì đoán
    """
    tr = Trace(user_query, mode="agent")
    if on_event:
        on_event("start", {"mode": "agent", "query": user_query,
                           "max_iterations": max_iterations})

    tool_names = ", ".join(AVAILABLE_TOOLS.keys())
    transcript = ""
    action_counts = {}

    for step in range(1, max_iterations + 1):
        prompt = (
            f"{memory_block}"
            f"Question: {user_query}\n\n"
            f"{transcript}"
            f"(Bạn đang ở bước {step}/{max_iterations}. "
            f"Xuất ra Thought rồi Action, HOẶC Thought rồi Final Answer.)\n"
        )

        t0 = time.time()
        raw = provider.generate(prompt, system_prompt=REACT_SYSTEM_PROMPT)
        tr.llm_calls += 1
        llm_sec = round(time.time() - t0, 2)

        if isinstance(raw, str) and raw.startswith("["):  # provider trả chuỗi lỗi
            tr.final_answer = f"Không gọi được mô hình: {raw}"
            tr.stop_reason = "provider_error"
            if on_event:
                on_event("error", {"message": raw})
            return tr

        # ── Chặn LLM tự bịa Observation ───────────────────────────────
        raw_full = raw or ""
        raw = cut_hallucinated_observation(raw_full)
        faked = len(raw_full) > len(raw)

        thought = parse_thought(raw)
        if on_event and thought:
            on_event("thought", {"step": step, "text": thought})

        # ── Có Final Answer -> kết thúc ───────────────────────────────
        final = parse_final_answer(raw)
        if final:
            tr.add_step(thought=thought, action=None, observation=None,
                        final=final, llm_sec=llm_sec, hallucinated_obs=faked)
            tr.final_answer = final
            tr.stop_reason = "final_answer"
            if on_event:
                on_event("final", {"answer": final, "trace": tr.to_dict()})
            return tr

        # ── Không có Final Answer -> phải có Action ───────────────────
        parsed = parse_action(raw)
        if not parsed:
            hint = PARSE_ERROR_HINT.format(tools=tool_names)
            tr.add_step(thought=thought, action=None, observation=hint,
                        error="parse_error", llm_sec=llm_sec)
            if on_event:
                on_event("observation", {"step": step, "text": hint, "error": True})
            transcript += f"Thought: {thought or ''}\nObservation: {hint}\n\n"
            continue

        name, args, raw_args = parsed
        if on_event:
            on_event("action", {"step": step, "tool": name, "args": args})

        # ── PHANH 1: lặp lại y hệt một hành động ──────────────────────
        sig = f"{name}|{raw_args}"
        action_counts[sig] = action_counts.get(sig, 0) + 1
        if action_counts[sig] > MAX_REPEATED_ACTION:
            msg = GUARDRAIL_LOOP_MESSAGE.format(action=f"{name}[{raw_args}]")
            tr.add_step(thought=thought, action=name, action_args_raw=raw_args,
                        observation=None, guardrail="repeated_action", llm_sec=llm_sec)
            tr.final_answer = msg
            tr.stop_reason = "guardrail_repeated_action"
            if on_event:
                on_event("guardrail", {"type": "repeated_action", "message": msg})
                on_event("final", {"answer": msg, "trace": tr.to_dict()})
            return tr

        # ── Tool không tồn tại -> trả gợi ý để agent tự sửa (V2) ──────
        if name not in AVAILABLE_TOOLS:
            hint = UNKNOWN_TOOL_HINT.format(name=name, tools=tool_names)
            tr.add_step(thought=thought, action=name, action_args_raw=raw_args,
                        observation=hint, error="unknown_tool", llm_sec=llm_sec)
            if on_event:
                on_event("observation", {"step": step, "text": hint, "error": True})
            transcript += (f"Thought: {thought or ''}\nAction: {name}[{raw_args}]\n"
                           f"Observation: {hint}\n\n")
            continue

        # ── Chạy tool thật ───────────────────────────────────────────
        t1 = time.time()
        obs = run_tool_safely(AVAILABLE_TOOLS[name], args, TIMEOUT_SECONDS)
        tool_sec = round(time.time() - t1, 2)
        tr.tool_calls += 1
        obs = str(obs)

        # ── PHÒNG THỦ: bài đăng có thể chứa câu ra lệnh cho AI ────────
        hits = detect_injection(obs)
        if hits:
            tr.injection_flags.append({"step": step, "tool": name, "patterns": hits})
            obs = INJECTION_BANNER + obs
            if on_event:
                on_event("injection", {"step": step, "patterns": hits})

        if len(obs) > MAX_TOOL_OUTPUT_CHARS:
            obs = obs[:MAX_TOOL_OUTPUT_CHARS] + "\n... (đã cắt bớt cho gọn)"

        tr.add_step(thought=thought, action=name, action_args_raw=raw_args,
                    observation=obs, llm_sec=llm_sec, tool_sec=tool_sec,
                    is_error=obs.lstrip().startswith("LỖI:"),
                    injection=bool(hits), hallucinated_obs=faked)
        if on_event:
            on_event("observation", {"step": step, "text": obs,
                                     "error": obs.lstrip().startswith("LỖI:")})

        transcript += (f"Thought: {thought or ''}\nAction: {name}[{raw_args}]\n"
                       f"Observation: {obs}\n\n")

    # ── PHANH 2: chạm trần số vòng lặp -> dừng LỊCH SỰ, không crash ───
    evidence = []
    for s in tr.steps:
        if s.get("observation") and not s.get("is_error"):
            first = s["observation"].strip().split("\n")[0]
            evidence.append(f"  · {s.get('action')}: {first[:110]}")
    msg = GUARDRAIL_MAX_ITER_MESSAGE.format(
        n=max_iterations,
        evidence="\n".join(evidence) if evidence else "  · (chưa xác minh được gì chắc chắn)")
    tr.final_answer = msg
    tr.stop_reason = "guardrail_max_iterations"
    if on_event:
        on_event("guardrail", {"type": "max_iterations", "message": msg})
        on_event("final", {"answer": msg, "trace": tr.to_dict()})
    return tr


# ═══════════════════════════════════════════════════════════════════════
# CẤP 4 — BONUS: AUTONOMOUS AGENT (Planning + Memory)
# ═══════════════════════════════════════════════════════════════════════
def run_autonomous_agent(user_query: str, provider, memory=None, on_event=None) -> dict:
    """
    Cấp 4: tự rã mục tiêu lớn thành các mục tiêu con, chạy ReAct cho từng
    mục tiêu, và nhớ ràng buộc của người dùng qua nhiều lượt hội thoại.
    """
    from memory import AgentMemory
    from planner import make_plan

    mem = memory or AgentMemory()
    mem.observe_user_message(user_query)

    goals = make_plan(user_query, provider)
    if on_event:
        on_event("plan", {"goals": goals})

    results = []
    for i, g in enumerate(goals, 1):
        if on_event:
            on_event("goal_start", {"index": i, "total": len(goals), "goal": g})
        tr = run_react_agent(g, provider, on_event=on_event,
                             memory_block=mem.as_prompt_block())
        mem.remember_result(g, tr.final_answer)
        results.append({"goal": g, "trace": tr})

    summary = "\n\n".join(f"▸ {r['goal']}\n{r['trace'].final_answer}" for r in results)
    if on_event:
        on_event("plan_done", {"summary": summary})
    return {"goals": goals, "results": results, "summary": summary, "memory": mem}


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════
def _hr(title=""):
    print("\n" + "═" * 74)
    if title:
        print(title)
        print("═" * 74)


def _print_event(kind, payload):
    if kind == "thought":
        print(f"  🧠 Thought {payload['step']}: {payload['text']}")
    elif kind == "action":
        args = ", ".join(f'"{a}"' for a in payload["args"])
        print(f"  🛠️  Action {payload['step']}: {payload['tool']}[{args}]")
    elif kind == "observation":
        txt = payload["text"]
        show = txt if len(txt) <= 700 else txt[:700] + f"\n     ... (+{len(txt)-700} ký tự)"
        icon = "❗" if payload.get("error") else "👁️"
        print(f"  {icon} Observation {payload['step']}:")
        for line in show.split("\n"):
            print(f"       {line}")
    elif kind == "injection":
        print(f"  🛡️  PHÁT HIỆN PROMPT INJECTION trong dữ liệu ở bước {payload['step']} "
              f"→ đã vô hiệu hoá, coi là văn bản thường")
    elif kind == "guardrail":
        print(f"  🛑 GUARDRAIL [{payload['type']}] kích hoạt")
    elif kind == "plan":
        print("  📋 KẾ HOẠCH:")
        for i, g in enumerate(payload["goals"], 1):
            print(f"     {i}. {g}")
    elif kind == "goal_start":
        print(f"\n  ── Mục tiêu {payload['index']}/{payload['total']}: {payload['goal']}")


def demo_compare(provider, case):
    print(f"\n📌 TEST CASE #{case['id']} — {case['category']}")
    print(f"❓ Câu hỏi: {case['question']}")
    print(f"🎯 Kỳ vọng: {case['expected_behavior']}")

    _hr("CẤP 2 — CHATBOT BASELINE (1 LLM call · 0 tool)")
    tr1 = run_baseline_chatbot(case["question"], provider)
    print(tr1.final_answer)
    print(f"\n  [llm_calls={tr1.llm_calls} · tool_calls={tr1.tool_calls} · {tr1.elapsed:.1f}s]")

    _hr("CẤP 3 — REACT AGENT (Thought → Action → Observation)")
    tr2 = run_react_agent(case["question"], provider, on_event=_print_event)
    print(f"\n  🏁 Final Answer:\n{tr2.final_answer}")
    print(f"\n  [llm_calls={tr2.llm_calls} · tool_calls={tr2.tool_calls} · "
          f"stop={tr2.stop_reason} · {tr2.elapsed:.1f}s]")
    return tr1, tr2


def chat_loop(provider):
    from memory import AgentMemory
    mem = AgentMemory()
    print("\n💬 Chế độ hội thoại. Gõ 'thoat' để dừng.\n")
    while True:
        try:
            q = input("Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("thoat", "thoát", "exit", "quit"):
            break
        mem.observe_user_message(q)
        tr = run_react_agent(q, provider, on_event=_print_event,
                             memory_block=mem.as_prompt_block())
        mem.remember_result(q, tr.final_answer)
        print(f"\n🤖 {tr.final_answer}\n")


def main():
    print("=" * 74)
    print("🏫 VINUNI LAB 3 — TRỢ LÝ SO SÁNH PHÒNG TRỌ (Chatbot vs ReAct Agent)")
    print("   Đề tài #10 · kế thừa Problem Statement v1 từ Lab Day 02")
    print("=" * 74)

    provider = get_llm_provider()
    tools_mod.set_provider(provider)
    model = getattr(provider, "model_name", "Offline Mock")
    print(f"🔌 Provider: {provider.__class__.__name__} (model: {model})")

    import listing_store as store
    print(f"🗂️  Kho dữ liệu: {len(store.all_listings())} bài đăng")

    tests = load_test_cases()
    print(f"✅ Đã tải {len(tests)} test cases")
    print(f"🛡️  Guardrails: MAX_ITERATIONS={MAX_ITERATIONS} · "
          f"MAX_REPEATED_ACTION={MAX_REPEATED_ACTION} · TIMEOUT={TIMEOUT_SECONDS}s")
    print(f"🧰 Tools: {', '.join(AVAILABLE_TOOLS.keys())}")

    args = sys.argv[1:]

    if "--chat" in args:
        chat_loop(provider)
        return

    if "--auto" in args:
        _hr("CẤP 4 — AUTONOMOUS AGENT (Planning + Memory)")
        q = ("Tôi có ngân sách 3.5 triệu, muốn ở gần ĐH Bách Khoa và phải được nấu ăn. "
             "Tìm giúp tôi vài phòng, tính tổng chi phí thực tế rồi soạn tin nhắn hỏi "
             "những khoản bài đăng chưa nói.")
        print(f"❓ {q}")
        run_autonomous_agent(q, provider, on_event=_print_event)
        return

    if "--case" in args:
        i = args.index("--case")
        cid = int(args[i + 1]) if i + 1 < len(args) else 3
        case = next((c for c in tests if c["id"] == cid), tests[0])
        demo_compare(provider, case)
        return

    # Mặc định: demo 1 câu cần tool + 1 câu bẫy, để thấy rõ khác biệt
    for cid in (3, 8):
        case = next((c for c in tests if c["id"] == cid), None)
        if case:
            demo_compare(provider, case)

    print("\n" + "─" * 74)
    print("Chạy thêm:  python src/app.py --chat        (hội thoại)")
    print("            python src/app.py --case 9     (một test case cụ thể)")
    print("            python src/app.py --auto       (bonus Cấp 4)")
    print("            python src/eval/run_eval.py    (chấm toàn bộ test case)")
    print("            python ui/server.py            (giao diện web)")


if __name__ == "__main__":
    main()
