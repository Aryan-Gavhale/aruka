"""The vocabulary of a project.

These live here rather than in the admin blueprint because the client portal shows
the same words back to the client. A project that reads "In build" on the delivery
board and "active" in the portal is the kind of small inconsistency that generates
an email asking which one is true.
"""

from __future__ import annotations

STATUSES = {
    "planned": "Planned",
    "active": "In build",
    "review": "With the client",
    "launched": "Live",
    "maintenance": "Maintenance",
    "on_hold": "On hold",
    "closed": "Closed",
    "cancelled": "Cancelled",
}

HEALTH = {"green": "On track", "amber": "Slipping", "red": "In trouble"}

TASK_COLUMNS = {"todo": "To do", "doing": "Doing", "review": "Review", "done": "Done"}

# What the client is allowed to be told. "In trouble" is a conversation to have on
# the phone, not a red dot they find on a Sunday.
CLIENT_VISIBLE_STATUSES = ("planned", "active", "review", "launched", "maintenance")
