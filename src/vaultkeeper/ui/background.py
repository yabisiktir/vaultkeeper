"""Running one long job off the UI thread.

Downloads run into the gigabytes and installs extract them again, so doing either
on the UI thread stops the window painting for minutes at a time — which a user
reads as a crash, not as patience. The stopgap for that was to pump the event loop
from the progress callback, and it had the flaw that stopgap always has: the loop
turning mid-download means a second click arrives *inside* the first one.

So the work moves to a worker thread and the loop is left alone. Progress comes
back as **signals**, which Qt queues onto the UI thread by itself, so a callback
running on the worker never touches a widget.

One job at a time, deliberately — two installs would fight over the same game
files. That is now the only reason: :class:`~vaultkeeper.core.profile_data.ProfileData`
guards its own dictionaries, so the window no longer has to be disabled while a
job runs and you can browse mods through a twenty-minute download. See
:func:`claim`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from nwnfile.log import get_logger
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

log = get_logger(__name__)


class BackgroundJob(QThread):
    """One callable, run on a worker thread, reporting back through signals.

    The callable is handed the job itself so it can emit progress and, more
    importantly, notice :attr:`cancelled` — cancellation is cooperative, because
    killing a thread mid-write is how a half-written archive ends up on disk under
    a finished archive's name.
    """

    #: The work returned normally; carries whatever it returned.
    done = Signal(object)
    #: The work raised. Carries a sentence worth showing someone.
    failed = Signal(str)
    #: The user cancelled, and the work stopped where it was.
    cancelled_early = Signal()
    #: Moving on to a new item: (label, index, count).
    step = Signal(str, int, int)
    #: Progress through the current item: (bytes done, bytes total or 0).
    bytes_progress = Signal(int, int)
    #: What the job is doing right now: (label, done, total). A ``total`` of 0 means
    #: the phase has no count — extracting a 2 GB archive is one opaque operation,
    #: and a bar for it would have to invent its position.
    phase = Signal(str, int, int)

    def __init__(self, work: Callable[[BackgroundJob], object], parent=None) -> None:
        super().__init__(parent)
        self._work = work
        #: Set from the UI thread; read from the worker between chunks.
        self.cancelled = threading.Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def raise_if_cancelled(self) -> None:
        """Stop the transfer if the user has asked to. Called between chunks."""
        from vaultkeeper.vault.http import TransferCancelled

        if self.cancelled.is_set():
            raise TransferCancelled()

    def run(self) -> None:  # pragma: no cover - exercised through the dialogs
        from vaultkeeper.vault.http import TransferCancelled

        try:
            result = self._work(self)
        except TransferCancelled:
            self.cancelled_early.emit()
        except Exception as ex:  # a worker thread must never raise into Qt
            log.exception("Background job failed")
            self.failed.emit(str(ex) or ex.__class__.__name__)
        else:
            self.done.emit(result)


def claim(dialog: QWidget | None) -> Callable[[], None]:
    """Note that a job is running; returns the release. **Leaves the UI usable.**

    This used to disable the whole window, because a job creates mods and rewrites
    the store while the mod list is being drawn from those same dictionaries — and
    that really did crash: listing mods while one was being created raises
    "dictionary changed size during iteration", reproducibly, in under three
    seconds. Disabling everything was the cheap way to be sure.

    :class:`~vaultkeeper.core.profile_data.ProfileData` now guards the shape of its
    dictionaries itself, so reading while a job writes is safe and the window can
    stay live. Measured with two reader threads against forty back-to-back
    installs: 190,000 read passes, no errors, worst single read 169 ms.

    What remains is not a data race but a sensible restriction — two installs at
    once would fight over the same game files — so the flag is kept and the
    dialogs refuse to start a second job while one is running.
    """
    _running.append(dialog)

    def release() -> None:
        if dialog in _running:
            _running.remove(dialog)

    return release


#: Dialogs with a job in flight. A list, not a bool, so overlapping jobs from two
#: different dialogs cannot release each other's claim.
_running: list = []


def job_running() -> bool:
    """Whether any dialog currently has a background job in flight."""
    return bool(_running)
