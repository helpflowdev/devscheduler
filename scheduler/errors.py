"""Domain errors.

The `app/` layer catches `DomainError` and shows `str(e)` to the user, so
messages must be user-readable.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base for all expected, user-facing rule violations."""


class DuplicateNameError(DomainError):
    """An active person with this name already exists."""


class NotFoundError(DomainError):
    """A referenced record does not exist."""


class ValidationError(DomainError):
    """Input failed a business rule (empty name, end <= start, etc.)."""


class OverwriteRequiredError(DomainError):
    """Existing entries block a non-overwrite apply (FR-4).

    Carries the conflicting entries so the UI can list them before the
    user confirms an overwrite.
    """

    def __init__(self, conflicts: dict[str, list]):
        self.conflicts = conflicts  # {work_date: [Entry, ...]}
        dates = ", ".join(sorted(conflicts))
        super().__init__(
            f"{sum(len(v) for v in conflicts.values())} existing "
            f"entr{'y' if sum(len(v) for v in conflicts.values()) == 1 else 'ies'} "
            f"on: {dates}. Confirm to overwrite."
        )
