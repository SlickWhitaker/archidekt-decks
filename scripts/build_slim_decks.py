#!/usr/bin/env python3
"""Build compact, searchable Archidekt sources for Commander analysis.

Full Archidekt exports remain untouched in decks/. For each deck this creates:
  * <id>.meta.json   - commander, color identity, counts
  * <id>.names.txt   - every card name, one per line
  * <id>.cards.jsonl - one complete card object per line
  * <id>.json        - legacy pretty JSON for compatibility

The names and JSONL files are deliberately line-oriented so analysis never
has to depend on a giant connector response containing an entire deck.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SOURCE = Path("decks")
DEST = Path("decks-slim")


def board_for(categories: list[str], companion: bool = False) -> str:
    cats = {str(c).strip().lower() for c in categories}
    if "maybeboard" in cats:
        return "maybeboard"
    if "sideboard" in cats:
        return "sideboard"
    if "commander" in cats or companion:
        return "commander"
    return "main"


def compact_text(oracle: dict) -> str:
    text = oracle.get("text", "") or ""
    faces = oracle.get("faces") or []
    if not faces or text:
        return text
    parts = []
    for face in faces:
        face_name = face.get("name", "")
        face_text = face.get("text", "") or ""
        if face_name and face_text:
            parts.append(f"{face_name}: {face_text}")
        elif face_text:
            parts.append(face_text)
    return " | ".join(parts)


def slim_card(entry: dict) -> dict:
    card = entry.get("card") or {}
    oracle = card.get("oracleCard") or {}
    categories = entry.get("categories") or []
    return {
        "name": oracle.get("name") or card.get("name") or "",
        "quantity": entry.get("quantity", 1),
        "board": board_for(categories, bool(entry.get("companion", False))),
        "colors": oracle.get("colors", []),
        "colorIdentity": oracle.get("colorIdentity", []),
        "manaValue": oracle.get("cmc"),
        "type": " ".join([
            *oracle.get("superTypes", []),
            *oracle.get("types", []),
            *(["—"] if oracle.get("subTypes") else []),
            *oracle.get("subTypes", []),
        ]),
        "text": compact_text(oracle),
    }


def build(source_path: Path) -> tuple[dict, list[dict]]:
    with source_path.open("r", encoding="utf-8") as fh:
        deck = json.load(fh)
    entries = deck.get("cards") or []
    cards = [slim_card(entry) for entry in entries]
    commanders = [c for c in cards if c["board"] == "commander"]
    main_cards = [c for c in cards if c["board"] == "main"]
    maybeboard = [c for c in cards if c["board"] == "maybeboard"]
    sideboard = [c for c in cards if c["board"] == "sideboard"]
    color_identity = sorted({color for c in commanders for color in c["colorIdentity"]})
    counts = {
        "main": sum(c["quantity"] for c in main_cards),
        "commander": sum(c["quantity"] for c in commanders),
        "maybeboard": sum(c["quantity"] for c in maybeboard),
        "sideboard": sum(c["quantity"] for c in sideboard),
        "total": sum(c["quantity"] for c in cards),
    }
    meta = {
        "id": deck.get("id"),
        "name": deck.get("name", ""),
        "format": deck.get("deckFormat"),
        "commander": [c["name"] for c in commanders],
        "colorIdentity": color_identity,
        "counts": counts,
    }
    return meta, cards


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    # Remove generated files only; never touch the full decks/ exports.
    for pattern in ("*.json", "*.jsonl", "*.txt"):
        for old_file in DEST.glob(pattern):
            old_file.unlink()

    generated = 0
    errors = 0
    manifest = []

    for source_path in sorted(SOURCE.glob("*.json")):
        if source_path.name.startswith("."):
            continue
        try:
            meta, cards = build(source_path)
            deck_id = meta["id"]
            stem = str(deck_id)

            # Human-readable compatibility JSON.
            legacy = {**meta, "cards": cards}
            with (DEST / f"{stem}.json").open("w", encoding="utf-8") as fh:
                json.dump(legacy, fh, ensure_ascii=False, indent=2)
                fh.write("\n")

            # Complete name index: ideal for fast "is this already in the deck?" checks.
            names = [c["name"] for c in cards if c["board"] in {"main", "commander"}]
            with (DEST / f"{stem}.names.txt").open("w", encoding="utf-8") as fh:
                fh.write("\n".join(names) + "\n")

            # One complete card object per line: each card can be retrieved independently.
            with (DEST / f"{stem}.cards.jsonl").open("w", encoding="utf-8") as fh:
                for card in cards:
                    fh.write(json.dumps(card, ensure_ascii=False, separators=(",", ":")) + "\n")

            full_size = source_path.stat().st_size
            slim_size = (DEST / f"{stem}.cards.jsonl").stat().st_size + (DEST / f"{stem}.names.txt").stat().st_size + (DEST / f"{stem}.meta.json").stat().st_size if (DEST / f"{stem}.meta.json").exists() else 0
            with (DEST / f"{stem}.meta.json").open("w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            slim_size = sum((DEST / name).stat().st_size for name in (f"{stem}.cards.jsonl", f"{stem}.names.txt", f"{stem}.meta.json"))
            reduction = (1 - slim_size / full_size) * 100 if full_size else 0
            manifest.append({**meta, "namesFile": f"{stem}.names.txt", "cardsFile": f"{stem}.cards.jsonl", "metaFile": f"{stem}.meta.json", "fullBytes": full_size, "analysisBytes": slim_size, "reductionPercent": round(reduction, 1)})
            print(f"{source_path.name}: {len(cards)} entries, analysis source {slim_size:,} bytes ({reduction:.1f}% smaller)")
            generated += 1
        except Exception as exc:
            print(f"ERROR: {source_path}: {exc}", file=sys.stderr)
            errors += 1

    with (DEST / "index.json").open("w", encoding="utf-8") as fh:
        json.dump({"decks": manifest}, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"Generated {generated} deck analysis bundles in {DEST}/")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
