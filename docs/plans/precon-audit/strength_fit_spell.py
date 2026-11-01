"""Fit and measure the spell theme-strength read (``card_quality.spell``'s
``THEME_WEIGHTS``): ``strength_fit_noncreature.py``'s method on the spell pairs.

    cd mtg-utils && uv run python ../docs/plans/precon-audit/strength_fit_spell.py \
        --fit A [--set existing|theme] [--features a,b,...]

The spell ``THEME_READ`` scores the module's own ``features`` (a refit, no new
features), so ``--set existing`` and ``--set theme`` fit the same features; the
shipped weights are the ``--fit A`` full fit, hand-rounded.

Output (2026-10-31 night, ``--fit A``)::

    source A: 945 pairs, 184 guide adds, 23 decks | play-rate 0.565  mana value 0.664
    source B: 813 pairs, 41 guide adds, 16 decks | play-rate 0.000  mana value 0.568
    feature        A:differs guide-higher | B:differs guide-higher
      abilities        0.33   0.53       |   0.26   0.68
      answer           0.46   0.31       |   0.43   0.34
      cost             0.85   0.31       |   0.79   0.53
      per_cast         0.56   0.52       |   0.57   0.67
      tutor            0.18   0.80       |   0.21   0.65
    LODO l2=1.0   fit A -> A 0.673 B 0.586 | fit B -> A 0.548 B 0.458 | fit A+B -> A 0.657 B 0.577
    LODO l2=3.0   fit A -> A 0.677 B 0.586 | fit B -> A 0.545 B 0.458 | fit A+B -> A 0.657 B 0.577
    LODO l2=10.0  fit A -> A 0.676 B 0.565 | fit B -> A 0.544 B 0.471 | fit A+B -> A 0.656 B 0.580
    LODO l2=30.0  fit A -> A 0.683 B 0.545 | fit B -> A 0.533 B 0.472 | fit A+B -> A 0.658 B 0.575
    A full fit (l2=3.0): weight (standardised = weight x sd)
      abilities      +0.33  (+0.19)
      answer         -0.60  (-0.29)
      cost           -0.29  (-0.56)
      per_cast       -0.10  (-0.07)
      tutor          +1.08  (+0.34)
    THEME_WEIGHTS in-sample on A: 0.701
    THEME_WEIGHTS in-sample on B: 0.564

B is too small to fit on (fitted alone it is below a coin flip on itself), and
every B guide add is also an A guide add, so the cross-source check shares the
preferred side. The read beats play-rate on both sources and mana value by 1-2
points: close to "cheaper, and a tutor".
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from strength_fit_noncreature import main  # noqa: E402

if __name__ == "__main__":
    main("spell", "A")
