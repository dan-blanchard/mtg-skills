"""Token walk + dedup behavior.

Uses tiny in-memory fixtures so we never hit Scryfall.
"""

from __future__ import annotations

from mtg_utils.deck import discover_tokens


def _src(
    name: str,
    *,
    parts: list[dict] | None = None,
    type_line: str = "Creature",
) -> dict:
    return {
        "id": f"{name.lower().replace(' ', '-')}-id",
        "name": name,
        "type_line": type_line,
        "all_parts": parts or [],
    }


def _token(
    name: str,
    *,
    oid: str,
    type_line: str,
    colors: list[str] | None = None,
    power: int | None = None,
    toughness: int | None = None,
) -> dict:
    return {
        "id": f"{oid}-printing",
        "oracle_id": oid,
        "name": name,
        "type_line": type_line,
        "colors": colors or [],
        "power": str(power) if power is not None else None,
        "toughness": str(toughness) if toughness is not None else None,
        "layout": "token",
    }


def _all_part(token: dict) -> dict:
    return {
        "object": "related_card",
        "id": token["id"],
        "component": "token",
        "name": token["name"],
        "type_line": token["type_line"],
    }


def test_dedup_by_oracle_id() -> None:
    """Two source cards making the same oracle_id should collapse to one group."""
    treasure = _token(
        "Treasure",
        oid="treasure-oid",
        type_line="Token Artifact — Treasure",
    )
    deadly = _src("Deadly Dispute", parts=[_all_part(treasure)])
    mahadi = _src("Mahadi", parts=[_all_part(treasure)])

    by_name = {"deadly dispute": deadly, "mahadi": mahadi}
    by_id = {treasure["id"]: treasure}
    deck = {
        "cards": [
            {"name": "Deadly Dispute", "quantity": 1},
            {"name": "Mahadi", "quantity": 1},
        ]
    }

    warnings: list[str] = []
    groups = discover_tokens(deck, by_name, by_id, log_warn=warnings.append)

    assert len(groups) == 1
    assert groups[0]["token"]["oracle_id"] == "treasure-oid"
    assert sorted(groups[0]["sources"]) == ["Deadly Dispute", "Mahadi"]
    assert warnings == []


def test_distinct_tokens_are_separate() -> None:
    """Different oracle_ids stay separate."""
    saproling = _token(
        "Saproling",
        oid="sap-oid",
        type_line="Token Creature — Saproling",
        colors=["G"],
        power=1,
        toughness=1,
    )
    spider = _token(
        "Spider",
        oid="spider-oid",
        type_line="Token Creature — Spider",
        colors=["G"],
        power=1,
        toughness=2,
    )
    arachno = _src("Arachnogenesis", parts=[_all_part(spider)])
    mycoloth = _src("Mycoloth", parts=[_all_part(saproling)])

    by_name = {"arachnogenesis": arachno, "mycoloth": mycoloth}
    by_id = {saproling["id"]: saproling, spider["id"]: spider}
    deck = {
        "cards": [
            {"name": "Arachnogenesis", "quantity": 1},
            {"name": "Mycoloth", "quantity": 1},
        ]
    }

    warnings: list[str] = []
    groups = discover_tokens(deck, by_name, by_id, log_warn=warnings.append)

    assert len(groups) == 2
    assert {g["token"]["name"] for g in groups} == {"Saproling", "Spider"}


def test_missing_source_card_logs_warning() -> None:
    """Source card not in the bulk index → WARN, no token group."""
    deck = {"cards": [{"name": "Definitely Not A Real Card", "quantity": 1}]}
    warnings: list[str] = []
    groups = discover_tokens(deck, by_name={}, by_id={}, log_warn=warnings.append)
    assert groups == []
    assert any("missing from bulk" in w for w in warnings)


def test_card_with_no_tokens_emits_no_warning() -> None:
    """Cards with no all_parts produce no tokens but no warning either."""
    sol_ring = _src("Sol Ring", type_line="Artifact")  # no all_parts
    by_name = {"sol ring": sol_ring}
    deck = {"cards": [{"name": "Sol Ring", "quantity": 1}]}
    warnings: list[str] = []
    groups = discover_tokens(deck, by_name, by_id={}, log_warn=warnings.append)
    assert groups == []
    assert warnings == []


def test_sort_order_artifact_first_then_color() -> None:
    """Artifacts before colored creatures; color order WUBRG; alpha within."""
    treasure = _token("Treasure", oid="treasure", type_line="Token Artifact — Treasure")
    soldier = _token(
        "Soldier",
        oid="sold",
        type_line="Token Creature — Soldier",
        colors=["W"],
        power=1,
        toughness=1,
    )
    zombie = _token(
        "Zombie",
        oid="zomb",
        type_line="Token Creature — Zombie",
        colors=["B"],
        power=2,
        toughness=2,
    )
    beast = _token(
        "Beast",
        oid="beast",
        type_line="Token Creature — Beast",
        colors=["G"],
        power=3,
        toughness=3,
    )

    src1 = _src("X", parts=[_all_part(beast)])
    src2 = _src("Y", parts=[_all_part(zombie)])
    src3 = _src("Z", parts=[_all_part(soldier)])
    src4 = _src("W", parts=[_all_part(treasure)])

    by_name = {"x": src1, "y": src2, "z": src3, "w": src4}
    by_id = {t["id"]: t for t in (treasure, soldier, zombie, beast)}
    deck = {"cards": [{"name": n, "quantity": 1} for n in ("X", "Y", "Z", "W")]}

    groups = discover_tokens(deck, by_name, by_id, log_warn=lambda _m: None)
    names = [g["token"]["name"] for g in groups]
    assert names == ["Treasure", "Soldier", "Zombie", "Beast"]
