"""Time conversion utilities."""

import re


def convert_et_to_ct(time_str: str) -> str:
    """Convert Eastern Time string to Central Time.

    Args:
        time_str: Time string like "7:00 pm ET"

    Returns:
        Time string like "6:00 PM CT"
    """
    if not time_str or 'ET' not in time_str:
        return time_str

    match = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)\s*ET', time_str.strip(), re.IGNORECASE)
    if not match:
        return time_str

    hour = int(match.group(1))
    minute = match.group(2)
    period = match.group(3).upper()

    if period == 'PM' and hour != 12:
        hour += 12
    elif period == 'AM' and hour == 12:
        hour = 0

    hour -= 1
    if hour < 0:
        hour += 24

    if hour == 0:
        display_hour = 12
        display_period = 'AM'
    elif hour < 12:
        display_hour = hour
        display_period = 'AM'
    elif hour == 12:
        display_hour = 12
        display_period = 'PM'
    else:
        display_hour = hour - 12
        display_period = 'PM'

    return f"{display_hour}:{minute} {display_period} CT"
