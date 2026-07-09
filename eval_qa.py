#!/usr/bin/env python3
"""
Spectraloop — QA Eval
----------------------
Her Q&A girişinin tüm variant'larını route_debug()'dan geçirir.

Keyword girişleri: variant metni sorgu içinde geçmeli (match_type="keyword").
Semantic girişleri: doğru id'ye eşleşmeli ve skor >= eşik olmalı.

Kullanım:
    python3 eval_qa.py
    python3 eval_qa.py --threshold 0.75
    python3 eval_qa.py --verbose
    python3 eval_qa.py --skip-semantic     # sadece keyword testleri (Ollama gerekmez)
"""

import argparse
import json
import sys
import threading
from pathlib import Path

from qa_router import QARouter, QA_CONFIG, _QA_PATH, _norm_kw

# ── ANSI ─────────────────────────────────────────────────────────────────────
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_CYAN   = "\033[96m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"


def _col(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}"


def main() -> None:
    parser = argparse.ArgumentParser(description="QA Router Eval")
    parser.add_argument(
        "--threshold", type=float, default=QA_CONFIG["threshold"],
        help=f"Semantic cosine eşiği (varsayılan: {QA_CONFIG['threshold']})",
    )
    parser.add_argument("--verbose", action="store_true", help="Başarılı sonuçları da göster")
    parser.add_argument(
        "--skip-semantic", action="store_true",
        help="Semantic testleri atla (Ollama başlatmadan keyword testi)",
    )
    args = parser.parse_args()

    # ── Router hazırla ───────────────────────────────────────────────────────
    router = QARouter.__new__(QARouter)
    router._entries   = []
    router._ready     = False
    router._threshold = args.threshold
    router._top_k     = QA_CONFIG["top_k"]
    router._model     = QA_CONFIG["embed_model"]
    router._lock      = threading.Lock()

    print(f"\n{_col('QA Eval', _BOLD)} — {_QA_PATH.name}")
    print(f"  Eşik       : {args.threshold}")
    print(f"  Model      : {router._model}")
    if args.skip_semantic:
        print(f"  {_col('Mod: yalnızca keyword testleri', _YELLOW)}\n")

    try:
        router.load()
    except Exception as e:
        print(f"\n{_col('HATA', _RED)}: QA yüklenemedi — {e}")
        if not args.skip_semantic:
            print("Ollama çalışıyor mu? `ollama serve` && `ollama pull nomic-embed-text`")
        sys.exit(1)

    # ── Referans veri ────────────────────────────────────────────────────────
    with open(_QA_PATH, encoding="utf-8") as f:
        qa_data: list[dict] = json.load(f)
    for e in qa_data:
        e.setdefault("match_type", "semantic")

    # ── Test döngüsü ─────────────────────────────────────────────────────────
    total_kw  = total_sem  = 0
    passed_kw = passed_sem = 0
    failed_rows: list[dict] = []

    col_w = [6, 8, 22, 44, 7, 22]

    def _header() -> None:
        h = (
            f"{'Sonuç':<{col_w[0]}}  "
            f"{'Tür':<{col_w[1]}}  "
            f"{'Giriş ID':<{col_w[2]}}  "
            f"{'Variant':<{col_w[3]}}  "
            f"{'Skor':>{col_w[4]}}  "
            f"{'Eşleşen ID':<{col_w[5]}}"
        )
        print(_col(h, _BOLD))
        print("─" * (sum(col_w) + 12))

    _header()

    for entry in qa_data:
        eid   = entry["id"]
        mtype = entry["match_type"]

        if mtype == "semantic" and args.skip_semantic:
            continue

        for variant in entry.get("variants", []):
            # Placeholder girişi atla
            if "__" in variant:
                continue

            if mtype == "keyword":
                total_kw += 1
                # Keyword testi: variant normalize hali sorgu normalizinde geçmeli
                q_norm = _norm_kw(variant)
                v_norm = _norm_kw(variant)
                correct = v_norm in q_norm   # variant tam olarak kendini içerir (tautoloji)
                # Gerçek test: router'ı çağır
                answer, score, mid, rtype = router.route_debug(variant)
                correct = (answer is not None) and (mid == eid) and (rtype == "keyword")
                if correct:
                    passed_kw += 1
                score_disp = "—"
            else:
                total_sem += 1
                answer, score, mid, rtype = router.route_debug(variant)
                correct = (answer is not None) and (mid == eid)
                if correct:
                    passed_sem += 1
                score_disp = f"{score:.3f}"

            show = args.verbose or not correct
            if show:
                status = _col("OK  ", _GREEN) if correct else _col("FAIL", _RED)
                mtype_col = _col("kw", _CYAN) if mtype == "keyword" else _col("sem", _DIM)
                v_disp = variant[:42] + ".." if len(variant) > 44 else variant
                m_disp = mid or "—"
                print(
                    f"{status}  "
                    f"{mtype_col:<{col_w[1]+9}}  "
                    f"{eid:<{col_w[2]}}  "
                    f"{v_disp:<{col_w[3]}}  "
                    f"{score_disp:>{col_w[4]}}  "
                    f"{m_disp:<{col_w[5]}}"
                )

            if not correct:
                failed_rows.append({
                    "expected_id": eid,
                    "matched_id":  mid,
                    "match_type":  mtype,
                    "variant":     variant,
                    "score":       score if mtype == "semantic" else None,
                })

    # ── Özet ─────────────────────────────────────────────────────────────────
    print("\n" + "═" * (sum(col_w) + 12))

    total  = total_kw + total_sem
    passed = passed_kw + passed_sem
    pct    = 100 * passed / total if total else 0
    sc     = _GREEN if pct == 100 else (_YELLOW if pct >= 80 else _RED)

    print(f"Toplam  : {_col(f'{passed}/{total}', sc)} ({_col(f'{pct:.1f}%', sc)})")
    if total_kw:
        pct_kw = 100 * passed_kw / total_kw
        print(f"Keyword : {passed_kw}/{total_kw} ({pct_kw:.0f}%)")
    if total_sem:
        pct_sem = 100 * passed_sem / total_sem
        print(f"Semantic: {passed_sem}/{total_sem} ({pct_sem:.0f}%)")

    if failed_rows:
        label = "Başarısız variant'lar:"
        print(f"\n{_col(label, _YELLOW)}")
        print(f"  {'Tür':<8}  {'Beklenen':<22}  {'Eşleşen':<22}  {'Skor':>6}  Variant")
        print("  " + "─" * 85)
        for r in failed_rows:
            score_s = f"{r['score']:.3f}" if r["score"] is not None else "  —  "
            print(
                f"  {r['match_type']:<8}  {r['expected_id']:<22}  "
                f"{r['matched_id'] or '—':<22}  {score_s:>6}  {r['variant'][:45]}"
            )
        hint = "İpucu: Semantic için variants listesine benzer ifade ekleyin; keyword için normalize metni kontrol edin."
        print(f"\n{_col(hint, _CYAN)}")
    else:
        ok_msg = "Tüm variant'lar doğru eşleşti."
        print(f"\n{_col(ok_msg, _GREEN)}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
