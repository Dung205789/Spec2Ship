"""Simple migration runner.

In production you typically:
- keep multiple Alembic revisions under version control
- run `alembic upgrade head` as part of deployment

This repo ships an initial revision so `docker compose up` can bootstrap the DB.
"""

import logging
import os

from alembic import command
from alembic.config import Config

log = logging.getLogger(__name__)


def main() -> None:
    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    log.info("DB migrated to head.")


if __name__ == "__main__":
    main()
