"""The Mod Web Links validation run and its report (VB ``ValidateModLinks``).

Checking a few hundred links is a few hundred web requests, so the pass runs on
a worker thread and says where it has got to. What comes back is a report and,
where the Vault gave a definite new address, an **Update** that writes those
links back — one button for the whole set, because reading a hundred rows and
retyping each is not a review, it is a chore nobody finishes.

Only unambiguous revisions are ever written. A mod several pages could match is
listed with its candidates and left alone; picking one is *Find Mod's Web Page
Link*, one mod at a time, with the user choosing.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.background import BackgroundJob, claim, job_running


class ModLinksReportDialog(QDialog):
    """Runs the validation, shows the report, and offers to apply the revisions."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._findings: list = []
        self._job: BackgroundJob | None = None
        self._release = None

        self.setWindowTitle("Mod Web Links Validation Report")
        self.setWindowIcon(R.get_icon("DynamicWebSite_16x"))
        geometry.remember(self, "ModLinksReportDialog", 820, 560)

        layout = QVBoxLayout(self)
        self.status = QLabel("Validating mod web links…")
        layout.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate until the first mod reports
        layout.addWidget(self.progress)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.report.setFont(QFont("Menlo", 11))
        layout.addWidget(self.report)

        buttons = QHBoxLayout()
        self.update_button = QPushButton(R.get_icon("Hyperlink"), "Update Links")
        self.update_button.setEnabled(False)
        self.update_button.setToolTip(
            "Write the corrected addresses back to the mods that have one."
        )
        self.update_button.clicked.connect(self._on_update)
        buttons.addWidget(self.update_button)
        buttons.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)
        layout.addLayout(buttons)

    # -- Running the pass --------------------------------------------------- #
    def start(self) -> None:
        """Begin the validation on a worker thread."""
        if job_running():
            self.status.setText("Another job is running — try again when it finishes.")
            self.progress.setRange(0, 1)
            return
        self._release = claim(self)
        controller = self.controller

        def work(job: BackgroundJob):
            def progress(done: int, total: int) -> None:
                job.phase.emit("Validating", done, total)

            return controller.validate_mod_web_links(on_progress=progress)

        self._job = BackgroundJob(work, self)
        self._job.phase.connect(self._on_phase)
        self._job.done.connect(self._on_done)
        self._job.failed.connect(self._on_failed)
        self._job.start()

    def _on_phase(self, _label: str, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.setText(f"Validating mod web links… {done} of {total}")

    def _on_done(self, result) -> None:
        self._finish()
        if not result.get("ok"):
            self.status.setText(result.get("message", ""))
            self.report.setPlainText(result.get("message", ""))
            return
        self._findings = result["findings"]
        self.status.setText(result["summary"])
        self.report.setPlainText(result["report"])
        count = sum(1 for f in self._findings if f.actionable)
        self.update_button.setEnabled(count > 0)
        self.update_button.setText(
            f"Update {count} Link{'s' if count != 1 else ''}" if count else "Update Links"
        )

    def _on_failed(self, message: str) -> None:
        self._finish()
        self.status.setText(f"Validation failed: {message}")

    def _finish(self) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        if self._release is not None:
            self._release()
            self._release = None

    # -- Applying the revisions --------------------------------------------- #
    def _on_update(self) -> None:
        result = self.controller.apply_mod_link_revisions(self._findings)
        self.status.setText(result["message"])
        self.update_button.setEnabled(False)
        QMessageBox.information(self, "Update Links", result["message"])

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt name
        # The pass is read-only, so abandoning it costs nothing but the requests
        # already in flight; those finish on their own thread and are discarded.
        self._finish()
        super().closeEvent(event)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> ModLinksReportDialog:
        dlg = cls(controller, parent)
        dlg.show()
        dlg.start()
        return dlg
