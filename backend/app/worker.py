import logging
from redis import Redis
from rq import Worker, Queue, Connection

from app.core.config import settings

log = logging.getLogger(__name__)

listen = ["default"]


def main() -> None:
    redis_conn = Redis.from_url(settings.redis_url)
    with Connection(redis_conn):
        worker = Worker(map(Queue, listen))
        log.info("RQ worker starting...")
        worker.work()


if __name__ == "__main__":
    main()
