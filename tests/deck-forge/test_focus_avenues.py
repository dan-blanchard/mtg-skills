"""Focused avenues (#2): a pin toggle marks the lanes the human is actually building
toward, and the candidate synergy score (✦) then counts ONLY those focused avenues
instead of every signal/avenue the deck happens to contain. Toggling lives at
POST /api/avenues/{id}/focus; the snapshot marks each avenue ``focused``."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _state():
    return ForgeState(
        by_name={}, search_fn=lambda **_: [], session=DeckSession("commander")
    )


def _agent_avenue(state, label="Sacrifice", oracle="sacrifice"):
    """Add an agent avenue (stable id, independent of signal detection) and return it."""
    av = {
        "id": f"agent:{len(state.agent_avenues) + 1}",
        "label": label,
        "description": "",
        "scope": "",
        "source": "agent",
        "search": {"oracle": oracle},
    }
    state.agent_avenues.append(av)
    return av


# ── endpoint: toggle + snapshot flag ────────────────────────────────────────


def test_focus_toggle_marks_then_unmarks_the_avenue():
    state = _state()
    av = _agent_avenue(state)
    client = TestClient(build_app(state))

    def focused_of(snap, aid):
        return next(a["focused"] for a in snap["avenues"] if a["id"] == aid)

    # default: present but not focused
    assert focused_of(client.get("/api/snapshot").json(), av["id"]) is False

    snap = client.post(f"/api/avenues/{av['id']}/focus").json()
    assert focused_of(snap, av["id"]) is True
    assert av["id"] in state.focused_avenue_ids

    snap = client.post(f"/api/avenues/{av['id']}/focus").json()  # toggle off
    assert focused_of(snap, av["id"]) is False
    assert av["id"] not in state.focused_avenue_ids


# ── scoring_basis: focus scopes the ✦ basis ─────────────────────────────────


def test_scoring_basis_defaults_to_signals_plus_context():
    state = _state()
    av = _agent_avenue(state)
    sigs = ["sig-a", "sig-b"]
    context = [av]
    # nothing focused → today's behavior: the deck signals AND the context avenues count
    assert engine.scoring_basis(state, [], sigs, context) == (sigs, context)


def test_scoring_basis_scopes_to_focused_only():
    state = _state()
    kept = _agent_avenue(state, label="Sacrifice", oracle="sacrifice")
    _agent_avenue(state, label="Tokens", oracle="create.*token")
    state.focused_avenue_ids = {kept["id"]}
    sigs = ["sig-a", "sig-b"]
    context = state.agent_avenues  # both avenues are "in context"

    active, avs = engine.scoring_basis(state, [], sigs, context)
    # signals dropped (the noise focus removes); only the focused lane credits a card
    assert active == []
    assert [a["id"] for a in avs] == [kept["id"]]
