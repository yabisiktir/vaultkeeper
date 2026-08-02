"""Running one long job off the UI thread.

Downloads run into the gigabytes and installs extract them again, so doing either
on the UI thread stops the window painting for minutes at a time — which a user
reads as a crash, not as patience. The stopgap for that was to pump the event loop
from the progress callback, and it had the flaw that stopgap always has: the loop
turning mid-download means a second click arrives *inside* the first one.

So the work moves to a worker thread and the loop is left alone. Progress comes
back as **signals**, which Qt queues onto the UI thread by itself, so a callback
running on the worker never touches a widget.

One job at a time, deliberately. The controller and the profile data it edits are
single-threaded everywhere else in this application, and a background job may
create mods, build installers and persist the store. Rather than make all of that
thread-safe, :meth:`BackgroundJob.claim` takes the application out of the user's
hands for the duration — the windows stay painted and the job stays cancellable,
but nothing else can start editing the same data underneath it.
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
    """Take the window behind ``dialog`` out of play; returns the undo.

    A running job can create mods and rewrite the store, and every other screen
    assumes it is the only thing doing that. Disabling the window that opened the
    dialog is cruder than making the model thread-safe, and far easier to be sure
    of. A parentless dialog (a test, or the editor run on its own) claims nothing.
    """
    parent = dialog.parent() if dialog is not None else None
    top = parent.window() if parent is not None else None
    if top is None:
        return lambda: None
    top.setEnabled(False)
    return lambda: top.setEnabled(True)
