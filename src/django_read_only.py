import os
from contextlib import contextmanager

from django.apps import AppConfig
from django.db import connections
from django.db.backends.signals import connection_created

default_app_config = "django_read_only.DjangoReadOnlyAppConfig"

read_only = False


class DjangoReadOnlyAppConfig(AppConfig):
    name = "django_read_only"
    verbose_name = "django-read-only"

    def ready(self):
        global read_only
        read_only = bool(os.environ.get("DJANGO_READ_ONLY", ""))
        self.add_database_instrumentation()

    def add_database_instrumentation(self):
        for alias in connections:
            connection = connections[alias]
            install_hook(connection)
        connection_created.connect(install_hook)


def install_hook(connection, **kwargs):
    """
    Rather than use the documented API of the `execute_wrapper()` context
    manager, directly insert the hook. This is done because:
    1. Deleting the context manager closes it, so it's not possible to enter it
       here and not exit it, unless we store it forever in some variable.
    2. We want to be idempotent and only install the hook once.
    """
    if blocker not in connection.execute_wrappers:  # pragma: no branch
        connection.execute_wrappers.append(blocker)


class DjangoReadOnlyError(Exception):
    pass


def blocker(execute, sql, params, many, context):
    if read_only and should_block(sql):
        raise DjangoReadOnlyError("Write queries are currently disabled")
    return execute(sql, params, many, context)


def should_block(sql):
    return (
        not sql.startswith(
            (
                "PRAGMA ",
                "ROLLBACK TO SAVEPOINT ",
                "RELEASE SAVEPOINT ",
                "SAVEPOINT ",
                "SELECT ",
                "SET ",
            )
        )
        and sql not in ("BEGIN", "COMMIT")
    )


def enable_writes():
    global read_only
    read_only = False


def disable_writes():
    global read_only
    read_only = True


@contextmanager
def temp_writes():
    enable_writes()
    try:
        yield
    finally:
        disable_writes()