"""Tuning issues — a diagnosis that carries its own remedy.

The scorecard's metrics say what is wrong; an :class:`Issue` also says what the swap
engine may DO about it: a :class:`Remedy` (where the add comes from, which cut pool
pays for it, how candidates are ranked) or ``None`` — nothing to source, the issue
is for the builder to read.

:class:`Sourcing` is the one place that decision is made. The swap engine has three
sourcing paths — the issue loop, the dead-weight drain, the under-sized-deck fill —
and each used to re-decide it (which search a kind gets, whether a Grant-covered role
sources anything); a rule added on one path was forgotten on another. Now all three
read the same answer: an issue's ``remedy``, or :meth:`Sourcing.role_spec` for the
fill pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._analysis.roles import is_ramp
from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils.card_classify import get_oracle_text

if TYPE_CHECKING:
    from collections.abc import Mapping

# The mana ability of these rocks is gated on board state a deck may not have (Mox Opal
# wants metalcraft, Mox Jasper a Dragon: "Activate only if you control …") — so they
# read as ramp but do nothing here. Match the gate phrase itself (not the "Activate[
# this ability]" prefix) so re-templating can't sneak one back in. Mox Amber has no such
# gate ("…among legendary creatures … you control"), so it's correctly still sourced.
_RAMP_CONDITIONAL = "only if you control"


def _reliable_ramp(card: dict) -> bool:
    """Ramp the tuner will SOURCE: a genuine producer (``roles.is_ramp`` — which already
    rejects mana an opponent receives, like An Offer You Can't Refuse's Treasures)
    whose ability isn't conditionally gated. The deck's existing conditional rocks still
    COUNT as ramp, but the tuner won't suggest one the deck can't reliably turn on."""
    return is_ramp(card) and _RAMP_CONDITIONAL not in get_oracle_text(card).lower()


ROLE_SEARCH: dict[str, dict] = {
    # Ramp is SOURCED by the same ``ramp`` preset ``roles.is_ramp`` COUNTS it by
    # (ADR-0051), so "fills the role" and "suggested for the role" cannot drift. The
    # "_filter" is a tuner-side precision pass (applied in the swap engine's ranked
    # pool): it drops a conditionally-gated rock — which still counts as ramp in the
    # deck, but the tuner won't suggest one.
    "ramp": {"preset_names": ("ramp",), "_filter": _reliable_ramp},
    "card_draw": {"preset_names": ("card-draw",)},
    "interaction": {
        "preset_names": ("removal", "creature-removal", "counterspell", "bounce")
    },
    "board_wipe": {"preset_names": ("board-wipe",)},
}
PROTECTION_SEARCH = {
    "preset_names": ("hexproof", "indestructible", "protection", "ward", "counterspell")
}
WINCON_SEARCH = {"oracle": r"wins the game|an additional combat phase|deals damage"}

# Efficiency curve issues → a CMC band to add into, scoped to the deck's main theme.
_EFFICIENCY_BANDS: dict[str, dict] = {
    "thin top-end": {"cmc_min": 6},
    "thin early game": {"cmc_max": 2},
    "top-heavy": {"cmc_max": 3},
}

# Cut pools a remedy may draw from (the swap engine routes ``cut_candidates`` in).
CUT_GENERIC = "generic"  # filler, then low-value, then stranded
CUT_FILLER = "filler"  # filler + low-value only — the dead-weight drain


def cut_over(role: str) -> str:
    """The cut pool holding ``role``'s over-band excess (a ``role_over`` trim cuts from
    THAT role, so it isn't derailed onto filler)."""
    return f"over:{role}"


@dataclass(frozen=True)
class Remedy:
    """What the swap engine does about an issue.

    ``spec`` is the candidate search for the add. ``cut_from`` names the cut pool that
    pays for it. ``spine`` marks a Spine fill: ranked efficiency-first (cheapest
    does-the-job) under the ADR-0040 role-fix guard, where every other add ranks
    synergy-first. ``drain`` marks the one multi-swap remedy — dead weight swaps until
    its pool or the swap budget runs out."""

    spec: dict
    cut_from: str = CUT_GENERIC
    spine: bool = False
    drain: bool = False


# An issue's optional wire fields, in the scorecard's key order.
_WIRE_FIELDS = (
    "role",
    "label",
    "subkind",
    "severity",
    "count",
    "advisory",
    "grant_covered",
)


@dataclass(frozen=True)
class Issue:
    """One ranked finding. ``remedy is None`` means the engine sources nothing for it.

    ``advisory`` is the scorecard's marker for a finding no swap can fix (a plan or a
    commander, not a slot) — a label for readers; the engine reads ``remedy``."""

    kind: str
    severity: int
    message: str
    remedy: Remedy | None = None
    role: str | None = None
    label: str | None = None
    subkind: str | None = None
    count: int | None = None
    advisory: bool | None = None
    grant_covered: bool | None = None

    def to_json(self) -> dict:
        """The scorecard's wire shape: the set fields, never the remedy."""
        out: dict = {"kind": self.kind}
        for key in _WIRE_FIELDS:
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        out["message"] = self.message
        return out


class Sourcing:
    """Where adds come from for THIS deck — the one owner of "is it actionable".

    Built from the focus result, the deck's signals and the slot budgets (whose short
    rows ``tune`` annotates with ``grant_covered``)."""

    def __init__(
        self, focus_result: Mapping, deck_signals: list, budgets: Mapping[str, dict]
    ) -> None:
        self._focus = focus_result
        self._signals = deck_signals
        self._budgets = budgets

    # ── Spine roles ─────────────────────────────────────────────────────────────

    def grant_cover(self, role: str) -> str | None:
        """The commander whose ability grant covers this short role (ADR-0040 §1 —
        deck-forge CONTEXT.md "Grant-covered role"), or None. ``""`` when covered by
        an unnamed grant."""
        band = self._budgets.get(role) or {}
        if not band.get("grant_covered"):
            return None
        return band.get("grant_covered_by", "")

    def role_spec(self, role: str) -> dict | None:
        """The search that fills a Spine role — None for a role nothing sources
        (``lands`` is the land tooling's) and for a Grant-covered one: the commander's
        own grant already covers it, so no path burns budget on a generic fill."""
        if self.grant_cover(role) is not None:
            return None
        return ROLE_SEARCH.get(role)

    def short_roles(self) -> list[str]:
        """Sourceable Spine roles below their floor, worst shortfall first."""
        short = [
            (band.get("deviation", 0), role)
            for role, band in self._budgets.items()
            if band.get("deviation", 0) < 0 and self.role_spec(role) is not None
        ]
        return [role for _, role in sorted(short, key=lambda pair: pair[0])]

    # ── Avenues ─────────────────────────────────────────────────────────────────

    def avenue(self, label: str) -> dict | None:
        """The serve spec of the deck signal behind an avenue label."""
        for sig in self._signals:
            spec = spec_for(sig)
            if spec is not None and spec.label == label:
                return dict(spec.search)
        return None

    def main_avenue(self) -> dict:
        """The deck's main-theme serve spec, or an empty (identity-only) spec."""
        viable = self._focus["viable_avenues"]
        if viable:
            return self.avenue(viable[0]["label"]) or {}
        return {}

    # ── Dead weight ─────────────────────────────────────────────────────────────

    def has_redeploy_target(self) -> bool:
        """Is there somewhere productive to redeploy a dead-weight slot — a viable
        theme to deepen, or a short role a grant doesn't already cover?"""
        return bool(self._focus.get("viable_avenues")) or any(
            band.get("deviation", 0) < 0 and self.grant_cover(role) is None
            for role, band in self._budgets.items()
        )

    def redeploy(self) -> dict | None:
        """Where a dead-weight slot goes: deepen the main theme if there is one, else
        fill the worst-short sourceable role. None when neither exists (nothing better
        to add than the filler being replaced, so don't churn)."""
        main = self.main_avenue()
        if main:
            return main
        short = self.short_roles()
        return self.role_spec(short[0]) if short else None

    # ── The decision ────────────────────────────────────────────────────────────

    def remedy_for(
        self,
        kind: str,
        *,
        role: str | None = None,
        label: str | None = None,
        subkind: str | None = None,
    ) -> Remedy | None:
        if kind == "role_short":
            spec = self.role_spec(role or "")
            return Remedy(spec, spine=True) if spec is not None else None
        if kind == "protection_short":
            return Remedy(PROTECTION_SEARCH, spine=True)
        if kind == "wincon_short":
            return Remedy(WINCON_SEARCH)
        if kind == "dead_weight":
            spec = self.redeploy()
            if spec is None:
                return None
            return Remedy(spec, cut_from=CUT_FILLER, drain=True)
        if kind == "spread_thin":
            viable = self._focus["viable_avenues"]
            spec = self.avenue(viable[0]["label"]) if viable else None
            return Remedy(spec) if spec is not None else None
        if kind == "under_supported_theme":
            # "Commit" to the emerging theme: add more cards that feed it.
            spec = self.avenue(label or "")
            return Remedy(spec) if spec is not None else None
        if kind == "role_over":
            # Trim the excess: the cut comes from the over role. The add deepens an
            # under-supported emerging theme if any (commit while trimming), else the
            # main theme. The engine's full-role filter keeps it from re-filling the
            # role being trimmed.
            emerging = self._focus.get("emerging", [])
            spec = self.avenue(emerging[0]["label"]) if emerging else None
            if spec is None:
                spec = self.main_avenue()
            return Remedy(spec, cut_from=cut_over(role or ""))
        if kind == "efficiency":
            # A curve problem is fixed by adding a synergistic card at the missing CMC
            # band (a thin top-end wants a 6+ MV finisher on the main theme, etc.).
            band = _EFFICIENCY_BANDS.get(subkind or "")
            if band is None:
                return None
            return Remedy({**self.main_avenue(), **band})
        # commander_misfit, voltron_no_commander_damage: no swap fixes a commander or
        # a plan.
        return None

    def issue(
        self,
        kind: str,
        *,
        severity: int,
        message: str,
        role: str | None = None,
        label: str | None = None,
        subkind: str | None = None,
        count: int | None = None,
        advisory: bool | None = None,
    ) -> Issue:
        """An :class:`Issue` of ``kind`` with its remedy decided."""
        covered = None
        if kind == "role_short":
            # A Grant-covered role keeps its literal shortfall but downgrades to
            # advisory — never suppressed (ADR-0040 §1).
            covered = self.grant_cover(role or "") is not None
            advisory = covered
        return Issue(
            kind=kind,
            severity=severity,
            message=message,
            remedy=self.remedy_for(kind, role=role, label=label, subkind=subkind),
            role=role,
            label=label,
            subkind=subkind,
            count=count,
            advisory=advisory,
            grant_covered=covered,
        )


def top_issues(
    *,
    efficiency_r: dict,
    focus_r: dict,
    template_r: dict,
    wincons_r: dict,
    protection_r: dict,
    commander_r: dict,
    sourcing: Sourcing,
) -> list[Issue]:
    """Rank the scorecard's findings by severity, each with its remedy decided."""
    issues: list[Issue] = []

    for role, b in template_r["short"].items():
        deficit = -b["deviation"]
        message = (
            f"{role.replace('_', ' ')} short by {deficit} "
            f"({b['current']}/{b['min']}-{b['max']})"
        )
        by = sourcing.grant_cover(role)
        if by is not None:
            message += f" — covered by {by}'s ability grant"
        issues.append(
            sourcing.issue("role_short", role=role, severity=deficit, message=message)
        )
    for role, b in template_r["over"].items():
        issues.append(
            sourcing.issue(
                "role_over",
                role=role,
                severity=b["deviation"],
                message=f"{role.replace('_', ' ')} over by {b['deviation']} "
                f"({b['current']}/{b['min']}-{b['max']})",
            )
        )

    # Dead weight: cards that serve no avenue AND fill no template role. Swapping a
    # do-nothing card for an on-theme / role card is almost always the highest-value
    # move, so it ranks above template trims — but only when there's somewhere
    # productive to redeploy (a viable theme to deepen or a short Spine role to fill);
    # with no target it's not an issue at all (the swap engine has nothing better to
    # add). A couple of off-theme good-stuff cards is normal, so a small tolerance
    # keeps this from churning a healthy deck.
    # Dead weight = do-nothing fillers PLUS barely-played fringe theme cards (the
    # upgrade targets the bucket test alone misses, e.g. a vanilla beater in a go-wide
    # deck). Both are replaced with stronger on-theme/role cards.
    dead = focus_r.get("filler", 0) + focus_r.get("low_value", 0)
    filler_tol = 2
    if dead > filler_tol and sourcing.has_redeploy_target():
        excess = dead - filler_tol
        issues.append(
            sourcing.issue(
                "dead_weight",
                # Ranks above theme-refocus (spread_thin) and template trims: replacing
                # a do-nothing card with an on-theme/role card is higher-value and only
                # ever cuts filler, so it should consume the swap budget before any pass
                # that risks churning a functional card.
                severity=7 + min(excess, 3),
                count=excess,
                message=f"{dead} cards are dead weight (no avenue/role, or barely "
                "played) — replace with stronger on-theme cards",
            )
        )

    for e in focus_r.get("emerging", []):
        issues.append(
            sourcing.issue(
                "under_supported_theme",
                label=e["label"],
                severity=2,
                message=f"{e['label']} ({e['depth']}) is an under-supported theme — "
                "commit more or cut it",
            )
        )

    if focus_r["verdict"] == "SPREAD-THIN":
        issues.append(
            sourcing.issue(
                "spread_thin",
                severity=4 + len(focus_r["stranded_avenues"]),
                message=f"spread thin — {len(focus_r['viable_avenues'])} viable "
                f"avenues, {focus_r['filler']} filler",
            )
        )

    if wincons_r["status"] == "low":
        issues.append(
            sourcing.issue(
                "wincon_short",
                severity=3 + (wincons_r["target"][0] - wincons_r["count"]),
                message=f"≈{wincons_r['count']} closers — "
                f"usually wants {wincons_r['target'][0]}-{wincons_r['target'][1]}",
            )
        )
    if wincons_r.get("voltron_needs_real_damage"):
        # The equip/aura density reads as voltron, but this game has no
        # 21-commander-damage rule (CR 903.10a is Commander's extra loss rule; Brawl
        # games don't use it, CR 903.12h), so the plan closes only by dealing the whole
        # starting life. Severity ranks how much the builder should change course — 2
        # here (read your closers differently) vs 5 for commander_misfit (you may have
        # the wrong commander).
        issues.append(
            sourcing.issue(
                "voltron_no_commander_damage",
                severity=2,
                advisory=True,
                message=f"voltron plan, but no commander-damage rule in this game — "
                f"it must deal the full {wincons_r.get('life')} life; count real "
                "evasion and reach as the closers",
            )
        )

    if protection_r["status"] == "low":
        issues.append(
            sourcing.issue(
                "protection_short",
                severity=2 + (protection_r["target"] - protection_r["count"]),
                message=f"{protection_r['count']} protection — "
                f"this Shape usually wants ~{protection_r['target']}",
            )
        )

    if efficiency_r["verdict"] != "ok":
        issues.append(
            sourcing.issue(
                "efficiency",
                subkind=efficiency_r["verdict"],
                severity=3,
                message=f"curve: {efficiency_r['verdict']}",
            )
        )

    if commander_r["misfit"]:
        # Severity 5 because it questions the whole build, where the voltron advisory
        # above (2) only re-reads the closers.
        issues.append(
            sourcing.issue(
                "commander_misfit",
                severity=5,
                advisory=True,
                message="commander serves "
                f"{len(commander_r['serves_viable'])}/{commander_r['viable_count']} "
                "viable avenues — the deck may be built for a different commander",
            )
        )

    issues.sort(key=lambda i: i.severity, reverse=True)
    return issues
