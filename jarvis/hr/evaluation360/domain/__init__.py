"""Pure domain logic for the 360 module — no DB, no Flask.

State machine, scoring/aggregation, and the anonymity engine live here so the
non-negotiable invariants (spec §2/§4/§8) are unit-testable in isolation.
"""
