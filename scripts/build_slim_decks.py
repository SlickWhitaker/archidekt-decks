#!/usr/bin/env python3
"""Build compact, analysis-friendly copies of the Archidekt deck JSON files.

The full Archidekt exports remain untouched in decks/. This script writes
small normalized files to decks-slim/ containing only the information needed
for Commander deck analysis.
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


def slim_face(face: dict) -> dict:
    return {
        "name": face.get("name", ""),
        "manaCost": face.get("manaCost", ""),
        "colors": face.get("colors", []),
        "subTypes": face.get("subTypes", []),
        "superTypes": face.get("superTypes", []),
        "types": face.get("types", []),
        "text": face.get("text", ""),
    }


def slim_card(entry: dict) -> dict:
    card = entry.get("card") or {}
    oracle = card.get("oracleCard") or {}
    categories = entry.get("categories") or []
    companion = bool(entry.get("companion", False))

    result = {
        "name": oracle.get("name") or card.get("name") or "",
        "quantity": entry.get("quantity", 1),
        "board": board_for(categories, companion),
        "categories": categories,
        "colors": oracle.get("colors", []),
        "colorIdentity": oracle.get("colorIdentity", []),
        "manaCost": oracle.get("manaCost", ""),
        "manaValue": oracle.get("cmc"),
        "types": oracle.get("types", []),
        "supertypes": oracle.get("superTypes", []),
        "subtypes": oracle.get("subTypes", []),
        "keywords": oracle.get("keywords", []),
        "text": oracle.get("text", ""),
    }

    faces = oracle.get("faces") or []
    if faces:
        result["faces"] = [slim_face(face) for face in faces]

    return result


def build(source_path: Path) -> tuple[dict, int]:
    with source_path.open("r", encoding="utf-8") as fh:
        deck = json.load(fh)

    entries = deck.get("cards") or []
    cards = [slim_card(entry) for entry in entries]
    commanders = [c for c in cards if c["board"] == "commander"]
    main_cards = [c for c in cards if c["board"] == "main"]
    maybeboard = [c for c in cards if c["board"] == "maybeboard"]
    sideboard = [c for c in cards if c["board"] == "sideboard"]

    color_identity = sorted({color for c in commanders for color in c["colorIdentity"]})

    slim = {
        "id": deck.get("id"),
        "name": deck.get("name", ""),
        "format": deck.get("deckFormat"),
        "commander": [c["name"] for c in commanders],
        "colorIdentity": color_identity,
        "counts": {
            "main": sum(c["quantity"] for c in main_cards),
            "commander": sum(c["quantity"] for c in commanders),
            "maybeboard": sum(c["quantity"] for c in maybeboard),
            "sideboard": sum(c["quantity"] for c in sideboard),
            "total": sum(c["quantity"] for c in cards),
        },
        "cards": cards,
    }
    return slim, len(cards)


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)

    # Remove old generated deck files so deleted/removed decks do not linger.
    for old_file in DEST.glob("*.json"):
        old_file.unlink()

    generated = 0
    errors = 0
    manifest = []

    for source_path in sorted(SOURCE.glob("*.json")):
        if source_path.name.startswith("."):
            continue
        try:
            slim, card_entries = build(source_path)
            output_path = DEST / source_path.name
            with output_path.open("w", encoding="utf-8") as fh:
                json.dump(slim, fh, ensure_ascii=False, separators=(",", ":"))
                fh.write("\n")

            full_size = source_path.stat().st_size
            slim_size = output_path.stat().st_size
            reduction = (1 - slim_size / full_size) * 100 if full_size else 0

            manifest.append({
                "id": slim["id"],
                "name": slim["name"],
                "file": output_path.name,
                "commander": slim["commander"],
                "colorIdentity": slim["colorIdentity"],
                "counts": slim["counts"],
                "fullBytes": full_size,
                "slimBytes": slim_size,
                "reductionPercent": round(reduction, 1),
            })

            print(
                f"{source_path.name}: {card_entries} entries, "
                f"{full_size:,} -> {slim_size:,} bytes ({reduction:.1f}% smaller)"
            )
            generated += 1
        except Exception as exc:
            print(f"ERROR: {source_path}: {exc}", file=sys.stderr)
            errors += 1

    with (DEST / "index.json").open("w", encoding="utf-8") as fh:
        json.dump({"decks": manifest}, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")

    print(f"Generated {generated} slim deck files in {DEST}/")
    print(f"Generated compact manifest: {DEST / 'index.json'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
