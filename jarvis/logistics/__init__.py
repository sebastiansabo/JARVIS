"""JARVIS Parc — logistics / yard-ops module.

Mirrors `jarvis/carpark/` (repositories/, routes/, services/). Own schema
(`jarvis/migrations/domains/schema_logistics.py`), own tables
(`logistics_*`), never writes another module's tables. See
docs/superpowers/specs/2026-11-27-jarvis-parc-design.md for the full design.

Task 1 (this task) ships schema + repositories only. The Flask blueprint
(`logistics_bp`, `/api/logistics/*`) is wired up by a later task once there
are routes to register.
"""
