from datetime import datetime


def current_time_context() -> str:
    """Human-readable current date/time block to prepend/append to the
    system prompt so the model has an accurate sense of 'now'."""
    now = datetime.now()
    return (
        f"Current date and time: {now.strftime('%A, %B %d, %Y — %I:%M %p')} "
        f"(local server time)."
    )
