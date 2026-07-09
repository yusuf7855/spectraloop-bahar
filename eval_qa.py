#!/usr/bin/env python3
"""
Spectraloop — QA Eval
----------------------
Her Q&A girişinin tüm variant'larını route_debug()'dan geçirir.

Keyword girişleri: variant metni sorgu içinde geçmeli (match_type="keyword").
Semantic girişleri: doğru id'ye eşleşmeli ve skor >= eşik olmalı.

Gürültülü STT testi: Kasıtlı yazım hataları içeren variant'lar yine doğru
id'ye eşleşmeli ve karar "answer" olmalı.

Gate testi: MockSegment nesneleriyle STTGate'in düşük kaliteli sesi
doğru reddettiği kontrol edilir. Ollama gerekmez.

Kullanım:
    python3 eval_qa.py
    python3 eval_qa.py --threshold 0.75
    python3 eval_qa.py --verbose
    python3 eval_qa.py --skip-semantic     # sadece keyword testleri (Ollama gerekmez)
    python3 eval_qa.py --gate-only         # yalnızca gate testleri
"""

import argparse
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from qa_router import QARouter, QA_CONFIG, _QA_PATH, _norm_kw
from stt_gate  import STTGate
import spectra_config as cfg

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
    parser.add_argument(
        "--gate-only", action="store_true",
        help="Yalnızca STT gate testlerini çalıştır (Ollama gerekmez)",
    )
    args = parser.parse_args()

    # ── Gate-only kısa yol (Ollama gerekmez) ─────────────────────────────────
    if args.gate_only:
        print(f"\n{_col('STT Gate Eval', _BOLD)}")
        _run_gate_tests()
        sys.exit(0)

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
        print(f"  {_col('Mod: yalnızca keyword testleri', _YELLOW)}")
    print()

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
                answer, score, mid, rtype, decision = router.route_debug(variant)
                correct = (answer is not None) and (mid == eid) and (rtype == "keyword")
                if correct:
                    passed_kw += 1
                score_disp = "—"
            else:
                total_sem += 1
                answer, score, mid, rtype, decision = router.route_debug(variant)
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

    # ── Gürültülü STT Testleri ────────────────────────────────────────────────
    if not args.skip_semantic and not args.gate_only:
        _run_noisy_tests(router, args.threshold)

    # ── STT Gate Testleri ─────────────────────────────────────────────────────
    _run_gate_tests()

    sys.exit(0 if passed == total else 1)


# ── Gürültülü STT Test Vektörü ───────────────────────────────────────────────
# Her tuple: (expected_id, sorgu_metni)  — STT karakteristik yazım hataları
_NOISY_VARIANTS: list = [
    ("dslim_motor",      "dslaim motor nasıl calısıor"),        # OCR-tipi hata
    ("dslim_motor",      "motor sistemi nasi calişiyor"),       # ş→s, ı→i
    ("sogutma_termal",   "soğutma sistmei nasıl"),              # transposition
    ("agirlik_boyut",    "araç kac kilogram agirlık"),          # ğ→g, ı→i
    ("fren_mesafe",      "fren mesafsi ne kadr"),               # dropped chars
    ("takim_roller",     "takımda kim neler yapıo"),            # informal STT
    ("gerilim_seviye",   "batarya gerilmi kac volt"),           # transposition
    ("maliyet",          "aracın maliyti ne kadar"),            # dropped 'e'
    ("test_sureci",      "test süreci nasıl ilerlio"),          # informal STT
    ("otonom_mu",        "arac otonom mu yoksa elle mi"),       # ğ dropped
]


def _run_noisy_tests(router: QARouter, threshold: float) -> None:
    print(f"\n{_col('Gürültülü STT Testleri', _BOLD)}")
    print(f"  Beklenti: karar='answer', skor >= {cfg.T_MED}")
    print("─" * 80)

    total_n  = 0
    passed_n = 0
    for eid, query in _NOISY_VARIANTS:
        total_n += 1
        answer, score, mid, rtype, decision = router.route_debug(query)
        correct = (decision == "answer") and (mid == eid) and (score >= cfg.T_MED)
        if correct:
            passed_n += 1
        status = _col("OK  ", _GREEN) if correct else _col("FAIL", _RED)
        q_disp = query[:42] + ".." if len(query) > 44 else query
        print(f"{status}  {eid:<22}  {q_disp:<44}  {score:.3f}  {mid or '—'}")

    pct_n = 100 * passed_n / total_n if total_n else 0
    sc_n  = _GREEN if pct_n == 100 else (_YELLOW if pct_n >= 70 else _RED)
    print(f"\nGürültülü: {_col(f'{passed_n}/{total_n}', sc_n)} ({_col(f'{pct_n:.0f}%', sc_n)})")


# ── STT Gate Test Altyapısı ──────────────────────────────────────────────────
@dataclass
class _MockSegment:
    text:             str
    start:            float
    end:              float
    avg_logprob:      float
    no_speech_prob:   float
    compression_ratio: float


_GATE_CASES: list = [
    # (açıklama, segments, beklenen_passed, beklenen_reason)
    (
        "iyi ses — geçmeli",
        [_MockSegment("İtki sistemi nasıl çalışıyor?", 0.0, 2.5,
                      avg_logprob=-0.3, no_speech_prob=0.05, compression_ratio=1.1)],
        True, "ok",
    ),
    (
        "düşük logprob — reddedilmeli",
        [_MockSegment("mmm", 0.0, 1.0,
                      avg_logprob=-1.5, no_speech_prob=0.10, compression_ratio=1.0)],
        False, "low_logprob",
    ),
    (
        "yüksek no_speech — reddedilmeli",
        [_MockSegment("evet", 0.0, 0.5,
                      avg_logprob=-0.4, no_speech_prob=0.85, compression_ratio=1.0)],
        False, "no_speech",
    ),
    (
        "yüksek compression — reddedilmeli",
        [_MockSegment("tekrar tekrar tekrar", 0.0, 1.5,
                      avg_logprob=-0.5, no_speech_prob=0.10, compression_ratio=3.0)],
        False, "high_compression",
    ),
    (
        "token sayısı az — reddedilmeli",
        [_MockSegment("mm", 0.0, 0.3,
                      avg_logprob=-0.4, no_speech_prob=0.10, compression_ratio=1.0)],
        False, "too_short",
    ),
    (
        "halüsinasyon — reddedilmeli",
        [_MockSegment("Teşekkür ederim.", 0.0, 1.0,
                      avg_logprob=-0.3, no_speech_prob=0.05, compression_ratio=1.0)],
        False, "hallucination",
    ),
    (
        "tekrar kalıbı — reddedilmeli",
        [_MockSegment("itki sistemi nasil calisiyor itki sistemi nasil calisiyor", 0.0, 4.0,
                      avg_logprob=-0.4, no_speech_prob=0.05, compression_ratio=2.0)],
        False, "repetition",
    ),
    (
        "boş segment listesi — reddedilmeli",
        [],
        False, "no_segments",
    ),
]


def _run_gate_tests() -> None:
    gate = STTGate()
    print(f"\n{_col('STT Gate Testleri', _BOLD)}")
    print("─" * 60)

    total_g  = len(_GATE_CASES)
    passed_g = 0
    for desc, segs, exp_passed, exp_reason in _GATE_CASES:
        passed, reason, meta = gate.check(segs)
        correct = (passed == exp_passed) and (reason == exp_reason)
        if correct:
            passed_g += 1
        status  = _col("OK  ", _GREEN) if correct else _col("FAIL", _RED)
        r_disp  = reason if reason == exp_reason else f"{reason} (beklenen: {exp_reason})"
        print(f"{status}  {desc:<35}  {r_disp}")

    pct_g = 100 * passed_g / total_g if total_g else 0
    sc_g  = _GREEN if pct_g == 100 else (_YELLOW if pct_g >= 80 else _RED)
    print(f"\nGate: {_col(f'{passed_g}/{total_g}', sc_g)} ({_col(f'{pct_g:.0f}%', sc_g)})")


if __name__ == "__main__":
    main()
