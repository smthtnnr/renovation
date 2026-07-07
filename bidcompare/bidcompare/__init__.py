"""bidcompare — force GC renovation bids into your estimator's taxonomy.

Pipeline (see README):
  1. taxonomy   — your estimator's line items exported as the master schema (the spine)
  2. extract    — bid PDF -> structured JSON, every line carries a verbatim quote (Claude)
  3. map        — each bid line -> mapped / extra / missing / unallocatable (Claude)
  4. exclusions — every exclusion / allowance / by-owner / TBD, verbatim (Claude)
  5. variance   — line-by-line delta vs your estimate, sorted by dollar impact (Python)
  6. calibrate  — flag your estimator when independent GCs systematically diverge (Python)
"""

__version__ = "0.1.0"
