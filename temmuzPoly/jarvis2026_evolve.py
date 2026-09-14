"""JARVIS2026 evrim turu — 2 saatte bir (:30).

Tüm sanal defterleri tarar, kendi son işlemlerini bakarak Claude'a
coin başına motor seçtirir, `jarvis2026_policy.json` günceller.
Poly yapay-zeka-analiz sayfasına / Telegram'a yazmaz.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import analyst_common as ac  # noqa: E402
import jarvis2026_signal as j  # noqa: E402

_FEED_FILE = os.path.join(_DIR, "jarvis2026_feed.jsonl")
_FEED_MAX = 200
_WINDOW_H = 48.0
_MIN_TRADES = 4

SYSTEM = """Sen JARVIS2026 sanal Polymarket defterinin evrim motorusun.
Görevin defter kopyalamak değil: kendi hatalarından DERS çıkarıp
çalıştırılabilir FİKİR yazmak. Open o fikirleri uygular.

Her fikir bir kuraldır. Serbest 'BTC UP hissi' yasak.

dir_mode yalnız şunlar:
- follow — book o saatte açtıysa aynı yön
- fade — book açtıysa ters yön
- path_reversion — saat açılışına (ref) göre: altında UP, üstünde DOWN
- path_trend — ref'e göre: altında DOWN, üstünde UP

Kapılar (hepsi opsiyonel, sayı uydurma):
- ask_max / ask_min  (Polymarket best ask, 0-1). ask_max ASLA 0.50'nin altına inme.
- path_bps_min / path_bps_max  (şimdi vs 1h ref, bps)
- path_abs_bps  (düz saat eşiği, varsayılan 6; ASLA 6'nın üstüne çıkma)
- entry_min / entry_max  (saatin hangi dakikaları; :02/:05/:07 zorunlu değil)
- book  (follow/fade için zorunlu; aday listesinden)

Open her dakika bakar, kural uyunca girer. Slot'a kilitli değil.

Kurallar:
- Kendi kayıplarından ders yaz. Aynı hatayı tekrarlama (pahalı ask, yanlış motor).
- idea_scorecard eksi olan id'yi değiştir. Kapıyı 0.50 / 6 bps tabanından daha sıkma — az işlem sorunu.
- Türev defter (b1_01/02/04/05, combo, combo2, jarvis2026, ref01, ref02) book olamaz.
- Coin başına 1 fikir. Toplam 3. Sayı uydurma.
- Veri zayıfsa yeni id ver; ask_max'ı 0.36'ya çekme.

Yanıt YALNIZCA JSON:
{
  "ideas": [
    {
      "id": "btc_ask",
      "symbol": "BTCUSDT",
      "dir_mode": "follow",
      "book": "a2_14",
      "ask_max": 0.50,
      "path_abs_bps": 6,
      "path_bps_min": null,
      "path_bps_max": null,
      "why": "kısa",
      "lesson": "hangi hatadan"
    }
  ],
  "note": "tek cümle evrim notu"
}
"""


def _slim_scan(hours: float) -> list[dict]:
    rows = []
    for key in j.follow_keys():
        near = j.book_coin_stats(key, hours=hours)
        all_ = j.book_coin_stats(key)
        if not any((near[c]["n"] or 0) > 0 or (all_[c]["n"] or 0) >= _MIN_TRADES for c in j.COINS):
            continue
        rows.append({
            "book": key,
            "label": j.book_label(key),
            "h48": near,
            "since_reset": all_,
        })
    rows.sort(key=lambda r: -sum(float((r["h48"][c] or {}).get("pnl") or 0) for c in j.COINS))
    slim = []
    for r in rows[:16]:
        slim.append({
            "book": r["book"],
            "h48": {c: r["h48"][c] for c in j.COINS if (r["h48"][c].get("n") or 0) > 0},
            "all": {c: r["since_reset"][c] for c in j.COINS if (r["since_reset"][c].get("n") or 0) >= _MIN_TRADES},
        })
    return slim


def _own_recent(limit: int = 24) -> list[dict]:
    hist = j._reset_cut("jarvis2026", j.load_history("jarvis2026"))
    out = []
    for t in hist[-limit:]:
        out.append({
            "symbol": t.get("symbol"),
            "dir": t.get("predicted_dir"),
            "win": t.get("win"),
            "pnl": t.get("pnl"),
            "ask": t.get("pm_entry_price"),
            "idea": t.get("jarvis_idea"),
            "mode": t.get("jarvis_mode"),
            "path_bps": t.get("jarvis_path_bps"),
            "book": t.get("jarvis_book") or t.get("j2026_book"),
            "exit": (t.get("exit_time_tr") or "")[:16],
        })
    return out


def _parse_ideas(raw: dict) -> list[dict]:
    blob = raw.get("ideas")
    if not isinstance(blob, list):
        blob = []
        # eski format: coin anahtarı
        for i, sym in enumerate(j.SYMBOLS):
            row = raw.get(sym) or {}
            if isinstance(row, dict) and row.get("book"):
                blob.append({
                    "id": f"legacy_{sym[:3].lower()}",
                    "symbol": sym,
                    "dir_mode": "follow",
                    "book": row.get("book"),
                    "why": row.get("why"),
                    "lesson": raw.get("note") or "",
                })
    out = []
    seen_sym: set[str] = set()
    for i, row in enumerate(blob):
        idea = j.normalize_idea(row, i)
        if not idea or idea["symbol"] in seen_sym:
            continue
        seen_sym.add(idea["symbol"])
        out.append(idea)
        if len(out) >= 3:
            break
    return out


def _ideas_to_sources(ideas: list[dict]) -> dict[str, dict]:
    out = {}
    for idea in ideas:
        out[idea["symbol"]] = {
            "book": idea.get("book") or idea.get("dir_mode"),
            "why": idea.get("why") or idea.get("lesson") or idea["dir_mode"],
            "idea": idea["id"],
            "dir_mode": idea["dir_mode"],
        }
    return out


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(s[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _valid_sources(raw: dict) -> dict[str, dict]:
    allowed = set(j.follow_keys())
    out = {}
    for sym in j.SYMBOLS:
        row = raw.get(sym) or raw.get(sym.replace("USDT", "")) or {}
        if not isinstance(row, dict):
            continue
        book = j.book_key(row.get("book") or "")
        if book not in allowed:
            continue
        out[sym] = {
            "book": book,
            "why": str(row.get("why") or "")[:160],
        }
    return out


_CLAUDE_MODELS = (
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
)


def _claude_models() -> list[str]:
    env = (os.environ.get("ANTHROPIC_MODEL") or "").strip()
    out: list[str] = []
    for m in (*_CLAUDE_MODELS, env, ac.CLAUDE_MODEL):
        if m and m not in out:
            out.append(m)
    return out


def _persist_workspace(ws: str) -> None:
    if not ws or not str(ws).startswith("wrkspc_"):
        return
    env_path = os.path.abspath(os.path.join(_DIR, "..", ".env"))
    try:
        lines = open(env_path, encoding="utf-8").read().splitlines()
    except Exception:
        return
    key = "ANTHROPIC_WORKSPACE_ID="
    wrote = False
    out = []
    for line in lines:
        if line.startswith(key):
            out.append(f"{key}{ws}")
            wrote = True
        else:
            out.append(line)
    if not wrote:
        out.append(f"{key}{ws}")
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
    except Exception:
        pass


def _workspace_ids() -> list[str]:
    env = (os.environ.get("ANTHROPIC_WORKSPACE_ID") or "").strip()
    extra = (os.environ.get("ANTHROPIC_WORKSPACE_IDS") or "").replace(",", " ").split()
    out: list[str] = []
    for wid in (env, *extra):
        if wid and wid.startswith("wrkspc_") and wid not in out:
            out.append(wid)
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/organizations/workspaces",
            headers={
                "x-api-key": ac.ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        for row in data.get("data") or []:
            wid = str((row or {}).get("id") or "").strip()
            if wid and wid not in out:
                out.append(wid)
    except Exception:
        pass
    if not any(x.startswith("wrkspc_") for x in out) and "default" not in out:
        out.append("default")
    return out


def _call_claude_once(model: str, system_prompt: str, user_prompt: str) -> str:
    body = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }).encode("utf-8")
    last_err = None
    for ws in _workspace_ids() or [None]:
        headers = {
            "x-api-key": ac.ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        if ws:
            headers["anthropic-workspace-id"] = ws
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            last_err = RuntimeError(f"{model} HTTP {e.code} {detail}")
            if ws and ("workspace" in detail.lower() or e.code in (400, 404)):
                continue
            raise last_err from e
        text = "".join(
            b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"
        ).strip()
        if text and ws:
            os.environ["ANTHROPIC_WORKSPACE_ID"] = ws
            _persist_workspace(ws)
        return text
    if last_err:
        raise last_err
    raise RuntimeError(f"{model} boş yanıt")


def _call_claude(system_prompt: str, user_prompt: str) -> str:
    """Eski snapshot ID 400 veriyor; güncel sonnet/haiku sırasıyla dener."""
    errors: list[str] = []
    for model in _claude_models():
        try:
            text = _call_claude_once(model, system_prompt, user_prompt)
            if text:
                print(f"[JARVIS2026 evolve] Claude model {model}")
                return text
            errors.append(f"{model} boş yanıt")
        except Exception as e:
            errors.append(str(e)[:220])
            continue
    raise RuntimeError(" | ".join(errors)[:400])


def _append_feed(entry: dict) -> None:
    lines: list[str] = []
    if os.path.exists(_FEED_FILE):
        try:
            with open(_FEED_FILE, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            lines = []
    lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
    if len(lines) > _FEED_MAX:
        lines = lines[-_FEED_MAX:]
    with open(_FEED_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def evolve(*, force_fallback: bool = False) -> dict:
    prev = j.load_policy()
    scan = _slim_scan(_WINDOW_H)
    own = _own_recent()
    fallback = j.fallback_mapping(min_trades=_MIN_TRADES)
    if not fallback:
        fallback = j.fallback_mapping(min_trades=3)

    ideas: list[dict] = []
    sources = {}
    note = ""
    src_tag = "fallback_wr"
    own_hist = j._reset_cut("jarvis2026", j.load_history("jarvis2026"))
    if not force_fallback and ac.ANTHROPIC_KEY:
        payload = {
            "now_tr": j.now_tr().isoformat(),
            "prev_ideas": prev.get("ideas") or [],
            "prev_sources": prev.get("sources"),
            "prev_note": prev.get("note"),
            "own_recent": own,
            "idea_scorecard": j.idea_scorecard(own_hist),
            "path_hours": j.path_hour_summaries(10),
            "fallback_wr": fallback,
            "candidates": scan,
        }
        user = (
            "Ders + aday + yol JSON:\n"
            + json.dumps(payload, ensure_ascii=False)
            + "\n\n3 fikir yaz. Yalnız JSON."
        )
        try:
            text = _call_claude(SYSTEM, user)
            parsed = _extract_json(text)
            if parsed:
                ideas = _parse_ideas(parsed)
                note = str(parsed.get("note") or "")[:240]
                if ideas:
                    src_tag = "claude"
                    sources = _ideas_to_sources(ideas)
                    extra = _valid_sources(parsed)
                    for sym, row in extra.items():
                        sources.setdefault(sym, row)
                else:
                    print("[JARVIS2026 evolve] Claude JSON fikir üretemedi")
            else:
                print("[JARVIS2026 evolve] Claude yanıtı JSON değil")
        except Exception as e:
            print(f"[JARVIS2026 evolve] Claude: {e}")
            err = str(e)
            if "credit balance is too low" in err.lower():
                note = "Anthropic API bakiyesi yetersiz — console.anthropic.com Plans & Billing"
            elif "workspace-id" in err.lower() or "workspace" in err.lower():
                note = "Claude workspace ID gerekli — Console → Settings → Workspaces"
            else:
                note = "Claude hata — WR yedeği"

    if not ideas:
        prev_ideas = [x for x in (j.policy_ideas(prev) or [])]
        if prev_ideas:
            ideas = prev_ideas
            sources = _ideas_to_sources(ideas)
            src_tag = prev.get("source") or "prev_ideas"
            if not note:
                note = "Claude yok — önceki fikirler duruyor"
        else:
            sources = dict(fallback or prev.get("sources") or {})
            src_tag = "fallback_wr"
            if not note:
                note = "Claude yok/bozuk — WR yedeği"
            for i, (sym, row) in enumerate(sources.items()):
                if isinstance(row, dict) and row.get("book"):
                    idea = j.normalize_idea({
                        "id": f"wr_{sym[:3].lower()}",
                        "symbol": sym,
                        "dir_mode": "follow",
                        "book": row["book"],
                        "ask_max": 0.50,
                        "why": row.get("why"),
                        "lesson": "ilk fikir — pahalı bileti kes",
                    }, i)
                    if idea:
                        ideas.append(idea)

    for src in (fallback, prev.get("sources") or {}):
        for sym, row in src.items():
            if isinstance(row, dict) and row.get("book"):
                sources.setdefault(sym, row)
    if not ideas and not sources:
        print("[JARVIS2026 evolve] politika boş — önceki dosya korunuyor")
        return prev

    policy = {
        "updated_at_tr": j.now_tr().isoformat(),
        "generation": int(prev.get("generation") or 0) + 1,
        "source": src_tag,
        "note": note,
        "ideas": ideas,
        "sources": sources,
        "scan_books": len(scan),
    }
    j.save_policy(policy)
    _append_feed({
        "ts": policy["updated_at_tr"],
        "kind": "evolve",
        "title": f"JARVIS2026 evrim #{policy['generation']}",
        "body": note or src_tag,
        "tags": [x.get("id") for x in ideas if x.get("id")],
        "ideas": ideas,
        "sources": sources,
    })
    print(
        f"[JARVIS2026 evolve] #{policy['generation']} {src_tag} · "
        + " · ".join(
            f"{sym.replace('USDT','')}→{j.book_label(row.get('book') or '')}"
            for sym, row in sources.items()
        )
        + (f" · {note}" if note else "")
    )
    return policy


def main() -> int:
    force = "--fallback" in sys.argv
    evolve(force_fallback=force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
