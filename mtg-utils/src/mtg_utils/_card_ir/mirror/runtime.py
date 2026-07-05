"""Stable runtime base for the generated typed mirror (ADR-0035, Stage 2).

The generated module (``generated_types.py``) imports :class:`TypedMirrorNode`,
:class:`MirrorVariant` and :data:`MISSING` from here, and both it and the strict
loader build instances of these. Kept separate from the (regenerated) generated
module so the base contract is stable across regenerations, and so there is no
import cycle (``runtime`` <- ``generated_types`` <- ``loader``).

Losslessness is independent of the generated *field types*: the loader dispatches
on the data-visible value-kind, not on a declared annotation, so a single
:meth:`TypedMirrorNode.to_dict` that walks the concrete subclass's dataclass
fields reconstructs the source JSON dict byte-for-byte. The one subtlety is the
absent-vs-null distinction: an optional field that was *absent* holds
:data:`MISSING` and is omitted from ``to_dict``; a field present with JSON
``null`` holds ``None`` and is emitted as ``None``.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, ClassVar


class _MissingType:
    """The absent-optional-field sentinel, as a pickle-stable singleton.

    A bare ``object()`` gets a fresh identity on unpickle, which silently breaks
    every ``x is MISSING`` check on a reloaded node — so a pickled/unpickled
    concept tree measures as all-fields-absent (``has_structural_*`` reads return
    empty). ``__reduce__`` resolves back to the module :data:`MISSING`, so
    ``x is MISSING`` stays true across a pickle/deepcopy boundary (corpus
    caching). Otherwise identical to ``object()``: opaque, truthy, hashable.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"

    def __reduce__(self) -> tuple[Any, tuple[()]]:
        return (_load_missing, ())


def _load_missing() -> _MissingType:
    """Resolve to the one module-level :data:`MISSING` on unpickle/deepcopy."""
    return MISSING


# Sentinel default for an absent optional field. Typed ``Any`` so the generated
# code can use it as the default of any precisely-typed field without a type
# error, while ``to_dict`` filters it out by identity.
MISSING: Any = _MissingType()


@dataclass(frozen=True)
class TypedMirrorNode:
    """Base for every generated tagged / struct mirror node.

    ``_tag`` carries the discriminator tag for a tagged-enum node (``None`` for a
    plain struct). One ``to_dict`` serves every subclass by walking its dataclass
    fields; a field whose JSON key is a Python keyword carries the real key in
    ``field(metadata={"json": ...})``.
    """

    _tag: ClassVar[str | None] = None

    def to_dict(self) -> dict:
        out: dict[str, object] = {}
        if self._tag is not None:
            out["type"] = self._tag
        for f in dataclasses.fields(self):
            val = getattr(self, f.name)
            if val is MISSING:
                continue
            json_name = f.metadata.get("json", f.name)
            out[json_name] = to_plain(val)
        return out


@dataclass(frozen=True)
class MirrorVariant:
    """A loaded untagged single-key enum node, e.g. ``{"UntilNextTurnOf": …}``.

    The inner value is itself a built typed instance / scalar / list; this thin
    wrapper preserves the discriminator key for a lossless round-trip.
    """

    key: str
    ckey: str | None
    inner: object

    def to_dict(self) -> dict:
        return {self.key: to_plain(self.inner)}


def to_plain(v: object) -> object:
    """Recursively convert built mirror instances back to plain JSON values."""
    if isinstance(v, (TypedMirrorNode, MirrorVariant)):
        return v.to_dict()
    if isinstance(v, list):
        return [to_plain(x) for x in v]
    return v
