# Split StoreAdapter into StoreSession + LGSAdapter + MarketplaceAdapter

The original `StoreAdapter` Protocol declared 9 methods, but the four
adapters split cleanly into two flows: LGS (TGP, Atomic Empire) implement
per-item shopping (`search`, `add_to_cart`); marketplaces (TCGPlayer, Mana
Pool) implement bulk shopping (`bulk_submit_and_optimize`). The other half
of methods (auth, cart inspection, clear, handoff, name canonicalization)
are shared lifecycle.

We split into three Protocols — `StoreSession` (lifecycle base) +
`LGSAdapter` and `MarketplaceAdapter` (each extends StoreSession with its
flow-specific methods) — instead of keeping one Protocol or splitting only
by flow. The intrinsic-kind constraint (an Atomic Empire is permanently an
LGS, will never become a marketplace) makes the split clean. Cross-kind
iteration (cart-pollution sweep, login pre-flight, Phase 7 handoff,
grand-total reporting) all use only the StoreSession surface, so the
shared base earns its keep with real leverage rather than being a
boilerplate-only inheritance.

See `lgs-search/CONTEXT.md` for the LGS / Marketplace / StoreSession
domain language.
