# lgs-search Context

The bounded context for sourcing an MTG card list across local game
stores and online marketplaces, allocating to minimize total cost,
and handing off populated checkout carts to the user.

## Language

### Storefront kinds

**LGS**:
A single physical local game store with its own first-party
inventory; the user picks specific in-stock listings and adds them
one at a time.
_Avoid_: "store" (ambiguous with Marketplace), "shop", "physical store"
(LGSes can be online-only too).

**Marketplace**:
An online aggregator hosting many third-party sellers; the user
submits a want-list and the site's optimizer consolidates across
sellers to minimize shipping packages and total.
_Avoid_: "online store" (lumps marketplaces together with any
single-store online shop), "online" (used as a noun — too vague).

**Storefront**:
The umbrella term for the unit of authentication, cart state, and
checkout — exactly one per host. Every LGS is a Storefront; every
Marketplace is a Storefront. The kind is intrinsic to the
Storefront's identity and never changes (Atomic Empire is an LGS
and will not become a Marketplace).
_Avoid_: "store" alone (ambiguous), "site", "shop", "merchant".

### Workflow concepts

**Listing**:
A specific in-stock copy of a card at one Storefront — a tuple of
(card name, set, condition, foil, price, qty available, listing id).
Only LGSes return Listings directly; a Marketplace's optimizer
returns an aggregated cart total without per-line detail.
_Avoid_: "result", "match", "hit".

**Allocation**:
The per-card decision made by the spill check — "this card goes to
TGP," "this card spills to Marketplace." Each card lands in exactly
one Storefront (or splits across multiple Storefronts if no single
one can fill the requested quantity).
_Avoid_: "assignment", "routing".

**Spillover**:
Cards that the allocation sends to a Marketplace, either because no
LGS has them in stock or because the cheapest-printing online price
beats the cheapest LGS price by more than the spill threshold.
_Avoid_: "online cards", "remainder".

**Cart pollution**:
Pre-existing items in a target Storefront's cart that would corrupt
the next operation — for a Marketplace this poisons the optimizer
(its totals reflect the whole cart, including pollution); for an
LGS this just blocks `--clear-existing-carts` accounting. The
orchestrator pre-flights `get_existing_cart` before any add or
optimize and aborts that Storefront if the cart isn't empty.
_Avoid_: "leftover cart", "dirty state".

**Sidecar**:
JSON audit record of one orchestrator run, written to
`<output-dir>/lgs-cart-allocation.json` after Phase 3 completes.
Carries the allocation, the chosen Marketplace, unfindable cards, and
basic-lands-needed summary. Write-only — there is no resume path; if
a run fails mid-build, fix the underlying issue and re-run from
scratch.
_Avoid_: "checkpoint", "state file" (implies resume capability that
doesn't exist).

**Cheapest-printing proxy**:
The minimum non-foil non-digital USD across all printings of a card
in the Scryfall bulk dump, used as the "online price" in the spill
check. Not the default printing's USD — that misses cheap reprints.
_Avoid_: "Scryfall price" (which printing?), "market price".

### Adapter / Protocol concepts

**StoreSession**:
The Protocol shared by every Storefront — methods for auth state
(`is_logged_in`, `open_login`), cart inspection and clearing
(`get_existing_cart`, `clear_cart`), the headed checkout window
(`open_handoff`), and the canonical-name canonicalization
(`name_for_search`). Every iteration that crosses kinds (cart
pollution sweep, login pre-flight, Phase 7 handoff, grand-total
report) uses only StoreSession methods.
_Avoid_: "Adapter base", "common interface".

**LGS adapter**:
A StoreSession that also implements per-item shopping: `search`
returns Listings; `add_to_cart` adds one Listing at a time.
_Avoid_: "LGS store" (redundant — every LGS is a Storefront).

**Marketplace adapter**:
A StoreSession that also implements bulk shopping:
`bulk_submit_and_optimize` submits an entire want-list and runs the
site's seller-consolidation optimizer.
_Avoid_: "online adapter" (the misleading name we're moving away
from), "bulk store".

## Relationships

- A **Storefront** is exactly one of {**LGS**, **Marketplace**}; the
  kind is intrinsic and immutable.
- An **LGS adapter** is a **StoreSession** plus per-item shopping
  methods.
- A **Marketplace adapter** is a **StoreSession** plus the bulk
  optimizer method.
- The **Allocation** routes each requested card to exactly one
  **Storefront** (or splits across multiple if quantity demands).
- A **Spillover** card always lands in a **Marketplace**; an
  in-LGS-stock card stays at the **LGS** unless its
  **Cheapest-printing proxy** beats the LGS price by more than the
  spill threshold.
- **Cart pollution** is checked against every target **Storefront**
  via the **StoreSession** interface, regardless of kind.

## Example dialogue

> **Dev:** "If a card is at TGP for $5 and the cheapest printing on Mana Pool is $2, does it spill?"
> **Domain expert:** "Yes — the **Cheapest-printing proxy** is $2, the **LGS** price is $5, the spill thresholds are 20% and $2. Both fire, so the **Allocation** sends it to the **Marketplace**."

> **Dev:** "What about the same card at TGP for $0.60 — the proxy is $0.50?"
> **Domain expert:** "Stays at **LGS**. TGP has a $0.50 floor; the proxy is matched, not beaten, so neither threshold fires. Picking up locally beats paying shipping for $0.10."

> **Dev:** "Do we still need to log in to a **Marketplace** if we just want a **Spillover** total, not a checkout?"
> **Domain expert:** "Yes — the optimizer fills the marketplace cart as a side effect. Phase 4 is what populates the cart; you can't get the total without populating. So **Cart pollution** matters even on a no-checkout dry-run."

## Flagged ambiguities

- **"online"** was overloaded — sometimes meaning the *kind* of a
  Storefront (vs LGS), sometimes meaning "any internet-accessible
  shop." Resolved: prefer **Marketplace** for the kind; use "online"
  only as a casual adjective. The code's `kind: "online"` field is
  being renamed to `kind: "marketplace"` and `ONLINE_STORES` →
  `MARKETPLACE_STORES`.
- **"store"** alone is ambiguous between any **Storefront** and an
  **LGS** specifically. Use the precise term; reserve **Storefront**
  for genuinely-kind-agnostic contexts.
- **TCG** can mean "TCGPlayer" (the **Marketplace**) or "trading card
  game" generally. In this context, **TCG** = TCGPlayer.
