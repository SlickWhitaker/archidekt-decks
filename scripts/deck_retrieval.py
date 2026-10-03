#!/usr/bin/env python3
"""Current Commander deck retrieval helpers.

The synchronized repository is the source of truth.

Deck discovery is intentionally based on decks-slim/index.json, not
GitHub code search and not individual Archidekt URLs. The index is a
stable, known path that the ChatGPT GitHub connector can fetch even when
GitHub's code-search index is unavailable.

Public entry points:
    discover_current_decks()
    get_current_deck_by_id(deck_id)
    find_current_deck(query)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

GITHUB_OWNER = "SlickWhitaker"
GITHUB_REPO = "archidekt-decks"
GITHUB_BRANCH = "main"
DECKS_PATH = "decks-slim"
REQUEST_TIMEOUT = 20


def github_api_url(path: str) -> str:
    return (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{path}?ref={GITHUB_BRANCH}"
    )


def _http_get(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Magic-the-Gathering-Analyzer/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError(f"GitHub retrieval failed for {url}: {exc}") from exc


def github_get_file(path: str) -> str:
    payload = json.loads(_http_get(github_api_url(path)))
    if not isinstance(payload, dict) or "content" not in payload:
        raise RuntimeError(f"GitHub did not return file content for {path}.")
    import base64
    return base64.b64decode(payload["content"].replace("\n", "")).decode("utf-8")


def discover_current_decks() -> list[dict[str, Any]]:
    """Return every current deck advertised by the synchronized index."""
    raw = github_get_file(f"{DECKS_PATH}/index.json")
    data = json.loads(raw)
    decks = data.get("decks")
    if not isinstance(decks, list):
        raise RuntimeError("decks-slim/index.json has no valid 'decks' list.")

    valid: list[dict[str, Any]] = []
    for deck in decks:
        if not isinstance(deck, dict) or deck.get("id") is None:
            continue
        valid.append(deck)

    if not valid:
        raise RuntimeError("Deck discovery returned zero current decks.")

    return valid


def get_current_deck_by_id(deck_id: int | str) -> dict[str, Any]:
    """Retrieve the complete compact deck for one discovered deck ID."""
    deck_id = str(deck_id)
    meta = json.loads(github_get_file(f"{DECKS_PATH}/{deck_id}.meta.json"))
    lines = github_get_file(f"{DECKS_PATH}/{deck_id}.cards.jsonl").splitlines()

    cards: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            card = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Invalid card JSON in deck {deck_id}, line {line_number}."
            ) from exc
        if not isinstance(card, dict) or not card.get("name"):
            raise RuntimeError(
                f"Invalid card record in deck {deck_id}, line {line_number}."
            )
        cards.append(card)

    if not cards:
        raise RuntimeError(f"Deck {deck_id} returned zero cards.")

    expected = (meta.get("counts") or {}).get("total")
    actual = sum(int(card.get("quantity", 1)) for card in cards)
    if expected is not None and int(expected) != actual:
        raise RuntimeError(
            f"Deck {deck_id} failed count validation: expected {expected}, got {actual}."
        )

    commanders = [c for c in cards if c.get("board") == "commander"]
    if not commanders:
        raise RuntimeError(f"Deck {deck_id} has no commander record.")

    return {
        "id": deck_id,
        "name": meta.get("name", f"Archidekt Deck {deck_id}"),
        "format": meta.get("format"),
        "commander": commanders,
        "cards": cards,
        "counts": meta.get("counts", {}),
        "colorIdentity": meta.get("colorIdentity", []),
        "metadata": meta,
    }


def find_current_deck(query: str) -> dict[str, Any]:
    """Find one current deck by ID, deck name, or commander name."""
    needle = query.strip().casefold()
    matches = []

    for entry in discover_current_decks():
        values = {
            str(entry.get("id", "")).casefold(),
            str(entry.get("name", "")).casefold(),
            *[str(c).casefold() for c in (entry.get("commander") or [])],
        }
        if needle in values:
            matches.append(entry)

    if not matches:
        raise LookupError(f"No current deck matched '{query}'.")
    if len(matches) > 1:
        names = ", ".join(str(m.get("name")) for m in matches)
        raise LookupError(f"Multiple current decks matched '{query}': {names}")

    return get_current_deck_by_id(matches[0]["id"])


if __name__ == "__main__":
    for deck in discover_current_decks():
        print(
            f"{deck['id']}: {deck.get('name', '')} — "
            f"{', '.join(deck.get('commander') or [])}"
        )
