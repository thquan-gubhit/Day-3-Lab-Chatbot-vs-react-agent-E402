"""
🔥 NẠP SẴN CACHE TRÍCH XUẤT CHO CẢ 70 BÀI ĐĂNG

Vì sao cần: tool search_listings phải đọc giá của mọi bài mới lọc được theo
ngân sách. Nếu mỗi lần chạy đều gọi LLM 70 lần thì Agent chạy rất chậm và
tốn token vô ích. Trích một lần, cache xuống đĩa, dùng lại mãi.

Chạy:  python src/data_gen/warm_cache.py
       python src/data_gen/warm_cache.py --force   (bỏ cache cũ, trích lại)
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import extractor
import listing_store as store
from providers import get_llm_provider


def main():
    force = "--force" in sys.argv
    if force and os.path.isdir(extractor.CACHE_DIR):
        for f in os.listdir(extractor.CACHE_DIR):
            os.remove(os.path.join(extractor.CACHE_DIR, f))
        print("🗑️  Đã xoá cache cũ.")

    provider = get_llm_provider()
    print(f"🔌 Provider: {provider.__class__.__name__} "
          f"(model: {getattr(provider, 'model_name', 'n/a')})")

    listings = store.all_listings()
    t0 = time.time()
    done = {"n": 0, "err": 0}

    def work(lst):
        r = extractor.extract_listing(lst["id"], provider=provider)
        done["n"] += 1
        if "_error" in r:
            done["err"] += 1
            print(f"   ⚠️  {lst['id']}: {r['_error'][:90]}")
        if done["n"] % 10 == 0:
            print(f"   ... {done['n']}/{len(listings)} bài ({time.time() - t0:.0f}s)")

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, listings))

    print(f"\n✅ Xong {done['n']} bài trong {time.time() - t0:.0f}s, {done['err']} lỗi.")
    print(f"⛔ Vi phạm luật cứng (trích dẫn không có trong bài gốc): "
          f"{len(extractor.QUOTE_VIOLATIONS)} ô")
    for v in extractor.QUOTE_VIOLATIONS[:10]:
        print(f"   {v['listing_id']}.{v['field']}: {v.get('llm_value')} "
              f"<- trích bịa {v.get('llm_quote')!r}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
