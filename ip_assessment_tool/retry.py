"""Retry utility with exponential backoff for AWS API throttling."""

import logging
import time

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

THROTTLING_ERROR_CODES = {"Throttling", "ThrottlingException", "RequestLimitExceeded"}


def retry_with_backoff(func, *args, max_retries: int = 5, base_delay: float = 1.0, **kwargs):
    """Execute func with exponential backoff on throttling errors.

    Calls func(*args, **kwargs). On throttling ClientErrors, retries up to
    max_retries times with exponential backoff (delay = base_delay * 2^attempt).
    Raises the original exception after max_retries exhausted.

    Args:
        func: Callable to execute.
        *args: Positional arguments passed to func.
        max_retries: Maximum number of retry attempts (default 5).
        base_delay: Base delay in seconds for backoff calculation (default 1.0).
        **kwargs: Keyword arguments passed to func.

    Returns:
        The return value of func on success.

    Raises:
        ClientError: Re-raised after max_retries exhausted for throttling errors.
        Exception: Any non-throttling exception is raised immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code not in THROTTLING_ERROR_CODES:
                raise

            if attempt >= max_retries:
                logger.error(
                    "Max retries (%d) exhausted for throttling error: %s",
                    max_retries,
                    error_code,
                )
                raise

            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Throttling error (%s), retrying in %.1fs (attempt %d/%d)",
                error_code,
                delay,
                attempt + 1,
                max_retries,
            )
            time.sleep(delay)
