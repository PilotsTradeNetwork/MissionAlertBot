"""
Module to return formatted date strings.

Depends on: constants
"""

# import libraries
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time

# import local constants
from ptn.missionalertbot.constants import seconds_long, seconds_short, seconds_very_short


# get date and time
def get_formatted_date_string():
    print("Called get_formatted_date_string")
    """
    Returns a tuple of the Elite Dangerous Time and the current real world time.

    :rtype: tuple
    """
    posix_time_string = int(time.time())
    print(f"POSIX time is {posix_time_string}")

    dt_now = datetime.utcnow()
    # elite_time_string is the current time as reported by Elite Dangerous, UTC plus 1286 years
    elite_time_string = (dt_now + relativedelta(years=1286)).strftime("%d %B %Y %H:%M %Z")
    print(f"Elite time string: {elite_time_string}")

    current_time_string = dt_now.strftime("%Y%m%d_%H%M%S")
    print(f"Current time string: {current_time_string}")

    return elite_time_string, current_time_string, posix_time_string

def get_mission_delete_hammertime():
    posix_time_string = get_formatted_date_string()[2]
    posix_time_string = posix_time_string + seconds_long() + seconds_very_short()
    hammertime = f"<t:{posix_time_string}:R>"
    return hammertime

def get_final_delete_hammertime():
    posix_time_string = get_formatted_date_string()[2]
    posix_time_string = posix_time_string + seconds_very_short()
    hammertime = f"<t:{posix_time_string}:R>"
    return hammertime

def get_inactive_hammertime(from_time=None):
    if from_time:
        from_datetime = datetime.utcfromtimestamp(from_time)
        time_inactive = from_datetime + relativedelta(days=28)
    else:
        time_inactive = datetime.utcnow() + relativedelta(days=28)
    posix_time_string = int(time_inactive.timestamp())
    hammertime = f"<t:{posix_time_string}:F>"
    return hammertime
