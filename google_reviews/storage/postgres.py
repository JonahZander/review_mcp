"""PostgreSQL connectivity primitives built on top of psycopg."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Condition

import psycopg
from psycopg import Connection


class PsycopgConnectionPool:
    """Small connection pool backed by psycopg connections."""

    def __init__(self, *, dsn: str, min_size: int = 1, max_size: int = 5) -> None:
        """Validate pool bounds and eagerly open min_size connections."""
        if min_size < 1:
            raise ValueError("min_size must be >= 1")
        if max_size < min_size:
            raise ValueError("max_size must be >= min_size")

        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._condition = Condition()
        self._available: list[Connection] = []
        self._created = 0
        self._is_closed = False

        for _ in range(self._min_size):
            self._available.append(self._new_connection())
            self._created += 1

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """Acquire and release a pooled connection."""

        connection = self._acquire()
        try:
            yield connection
        finally:
            self._release(connection)

    def close(self) -> None:
        """Close all idle connections in the pool."""

        with self._condition:
            self._is_closed = True
            for connection in self._available:
                if not connection.closed:
                    connection.close()
            self._available.clear()
            self._created = 0
            self._condition.notify_all()

    def _acquire(self) -> Connection:
        """Pop an available connection or create a new one up to max_size; block when the pool is full."""
        with self._condition:
            while True:
                if self._is_closed:
                    raise RuntimeError("Connection pool has been closed.")

                if self._available:
                    connection = self._available.pop()
                    if connection.closed:
                        self._created -= 1
                        continue
                    return connection

                if self._created < self._max_size:
                    connection = self._new_connection()
                    self._created += 1
                    return connection

                self._condition.wait()

    def _release(self, connection: Connection) -> None:
        """Return a connection to the pool, rolling back any open transaction first."""
        with self._condition:
            if self._is_closed or connection.closed:
                if not connection.closed:
                    connection.close()
                self._created = max(0, self._created - 1)
                self._condition.notify()
                return

            if connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                connection.rollback()

            self._available.append(connection)
            self._condition.notify()

    def _new_connection(self) -> Connection:
        """Open and return a new psycopg connection using the configured DSN."""
        return psycopg.connect(self._dsn)
