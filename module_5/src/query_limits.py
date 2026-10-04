"""Shared limits for database result queries and batch processing."""

DEFAULT_QUERY_LIMIT = 1
MAX_QUERY_LIMIT = 100
QUERY_BATCH_SIZE = MAX_QUERY_LIMIT


def clamp_query_limit(value):
    """Parse a requested result limit and clamp it to the supported range.

    Args:
        value (str | int | None): User-supplied result limit.

    Returns:
        int: Limit between 1 and ``MAX_QUERY_LIMIT``.

    Raises:
        ValueError: If the supplied value is not an integer.
    """
    if value is None:
        return DEFAULT_QUERY_LIMIT
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("limit must be an integer")
    try:
        requested_limit = int(value)
    except ValueError as error:
        raise ValueError("limit must be an integer") from error
    return min(MAX_QUERY_LIMIT, max(1, requested_limit))


def iter_query_batches(cursor, statement):
    """Yield all rows from a p_id-keyset query in bounded batches.

    The statement must select ``p_id`` first, filter with ``p_id > %s``,
    order by ``p_id``, and finish with ``LIMIT %s``.
    """
    last_id = 0
    while True:
        cursor.execute(statement, (last_id, QUERY_BATCH_SIZE))
        rows = cursor.fetchall()
        if not rows:
            return
        yield rows
        last_id = rows[-1][0]
