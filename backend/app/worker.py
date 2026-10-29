"""The background worker: a second process that does what a request must not wait for.

Started as `celery -A app.worker worker`. It shares the codebase and the settings with the
API and nothing else — no routes, no database session per request, no HTTP server.

**Why there is a queue at all.** Letters used to ride on `BackgroundTasks`, which runs them in
the API process after the response. That has two faults and both are the kind that only show
up on a bad day: a send that fails is gone, with nobody to try again; and anything that is not
an endpoint — a dependency, a startup hook — has no `BackgroundTasks` to put work on, so the
letter simply cannot be sent from there. A queue answers both: the task survives the process
that created it, and putting something on it is an ordinary function call from anywhere.

**JSON, never pickle.** Celery can serialise tasks with pickle, and a broker that carries
pickled objects is a broker that executes whatever is written to it. Redis here is not
exposed, but "not exposed" is a property of today's network and not of this file.

**Acknowledged late.** A task is acknowledged when it finishes, not when it is picked up, so a
worker killed mid-letter gives the letter back to the queue instead of taking it to the grave.
The cost is that a letter may be sent twice if the worker dies after the send and before the
acknowledgement — duplicated transactional mail is a nuisance, a lost confirmation link is a
person who cannot use the platform.

**No result backend.** Nothing waits for an answer. Storing one would be a second Redis
keyspace to expire for information nobody reads.
"""

from typing import Any

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

settings = get_settings()
configure_logging(settings.log_level)

celery_app = Celery("allstore")

celery_app.conf.update(
    broker_url=settings.queue_url,
    # When there is no broker configured, every task runs inline in the caller — which is what
    # the test suite wants and what a stand without Redis gets. It is the honest fallback:
    # the work still happens, it just happens in the process that asked for it, exactly as it
    # did before this file existed.
    task_always_eager=settings.queue_url is None,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    # one at a time: a worker that reserved ten letters and then died would hold all ten
    worker_prefetch_multiplier=1,
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    # Named rather than auto-discovered. Celery registers a task because the module defining
    # it was imported, and the worker imports nothing by itself; autodiscovery would import
    # them from here, which is a cycle (a task module imports this one for the app). These
    # are imported when the worker boots, by which time this module is fully loaded. The API
    # process gets them the ordinary way — `services/notifications.py` imports what it sends.
    imports=("app.tasks.mail",),
)


@celery_app.task(name="allstore.ping")
def ping() -> str:
    """Proves the worker is alive and can be reached through the broker. Used by nothing in
    the application and by hand when a deploy looks wrong."""
    return "pong"


def enqueue(task: Any, *args: Any, **options: Any) -> bool:
    """Puts work on the queue, and says whether it got there.

    Wrapped because the caller is almost always a request that has already succeeded: the
    account was created, the password was changed, the commit happened. A broker that is down
    must not turn that into a failure the person sees — it must turn into a line in the log
    and a letter sent some other way.
    """
    try:
        task.apply_async(args=args, **options)
    except Exception:
        # Deliberately everything. kombu raises its own tree of connection, transport and
        # timeout errors, and naming them here would be a list that goes stale — while the
        # answer to every one of them is the same: there is no queue right now.
        logger.exception("could not queue %s", getattr(task, "name", task))
        return False
    return True
