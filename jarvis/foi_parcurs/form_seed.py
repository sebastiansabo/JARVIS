"""Retire the legacy Forms-engine Test Drive form (now handled in-module)."""
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.foi_parcurs.form_seed')

TEST_DRIVE_FORM_SLUG = 'test-drive'


def retire_test_drive_form():
    """Retire the Forms-engine 'test-drive' form. Idempotent.

    Test drives are now recorded exclusively via the in-module custom form
    (POST /api/foi-parcurs/test-drive). Any previously-seeded row is soft-deleted
    and unpublished so it no longer appears in the Forms builder or on the hub.
    """
    base = BaseRepository()

    existing = base.query_one(
        "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL",
        (TEST_DRIVE_FORM_SLUG,)
    )
    if not existing:
        return None

    base.execute(
        "UPDATE forms SET published_to_hub = FALSE, status = 'draft', "
        "deleted_at = CURRENT_TIMESTAMP WHERE slug = %s AND deleted_at IS NULL",
        (TEST_DRIVE_FORM_SLUG,)
    )
    logger.info('Retired Forms-engine Test Drive form (id=%s)', existing['id'])
    return existing['id']
