"""Backfill initials avatars for users left on the default "/user.png".

Older accounts (created before server-side initials generation existed, e.g.
SSO/Keycloak users with no provider picture) have ``profile_image_url`` set to
``/user.png`` or left empty. The serving endpoint now generates an initials
avatar on the fly for those, but this one-off script persists a generated
``data:image/png;base64,...`` avatar directly into the database so the value is
stable and no per-request generation is needed.

Usage (from the ``backend`` directory, with the app's virtualenv active)::

    python -m open_webui.scripts.backfill_user_avatars --dry-run   # preview
    python -m open_webui.scripts.backfill_user_avatars             # apply

Safe to re-run: only users whose stored image is empty or "/user.png" are
touched; anyone with an http URL or an existing data-image avatar is skipped.
"""

import argparse
import logging

from open_webui.internal.db import get_db
from open_webui.models.users import User
from open_webui.utils.misc import generate_initials_image_data_url

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("backfill_user_avatars")

# Stored values that mean "no real avatar".
PLACEHOLDER_VALUES = (None, "", "/user.png")


def backfill(dry_run: bool = False) -> dict:
    updated = 0
    skipped = 0
    failed = 0

    with get_db() as db:
        users = (
            db.query(User)
            .filter(User.profile_image_url.in_([v for v in PLACEHOLDER_VALUES if v is not None]))
            .all()
        )
        # SQL IN can't match NULL; pick those up separately.
        users += db.query(User).filter(User.profile_image_url.is_(None)).all()

        total = len(users)
        log.info(f"Found {total} user(s) without a stored avatar.")

        for user in users:
            data_url = generate_initials_image_data_url(user.name)
            if not data_url.startswith("data:image"):
                # Generation fell back to "/user.png" — leave as-is.
                failed += 1
                log.warning(f"  ! could not generate avatar for {user.email} ({user.id})")
                continue

            if dry_run:
                log.info(f"  [dry-run] would update {user.email} ({user.name})")
                skipped += 1
                continue

            user.profile_image_url = data_url
            updated += 1
            log.info(f"  updated {user.email} ({user.name})")

        if dry_run:
            db.rollback()
        else:
            db.commit()

    result = {"total": total, "updated": updated, "skipped": skipped, "failed": failed}
    log.info(
        f"Done. updated={updated} skipped={skipped} failed={failed} "
        f"({'dry-run, no changes written' if dry_run else 'changes committed'})"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing to the database.",
    )
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
