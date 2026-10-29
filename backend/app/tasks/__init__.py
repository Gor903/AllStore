"""What the worker does. One module per kind of work, discovered by `app.worker`.

A task is the narrowest possible thing: it takes values that survive JSON, it reads the
settings itself, and it decides nothing. What to say and to whom was decided by the request
that queued it — by the time the worker runs, that request is over and its session is closed.
"""
