"""About dialog — application info, version, and library credits.

Ported from the VB ``NIT.Menu.vb:MsAbout_Click`` handler. Shows the app name,
description, version, and credits for bundled libraries (BicFileReader, TargaImage, UDE).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R


class AboutDialog(QDialog):
    """Modal dialog showing application info and library credits."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Vaultkeeper")
        self.setWindowIcon(R.app_icon())
        geometry.remember(self, "AboutDialog", 480, 380)

        layout = QVBoxLayout(self)

        # App icon
        icon_label = QLabel()
        icon_label.setPixmap(R.app_icon().pixmap(64, 64))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # Product name (bold, larger)
        title_label = QLabel("Vaultkeeper")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "A faithful cross-platform port of the Neverwinter Nights "
            "Installer Tool by Surazal."
        )
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Version
        try:
            app_version = version("vaultkeeper")
        except PackageNotFoundError:
            app_version = "0.0.1"
        version_label = QLabel(f"Version: {app_version}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        # Credits (rich text in QTextBrowser)
        credits_text = (
            "<b>Credits</b><br/><br/>"
            # The tool this one is a port of. It credited its own dependencies
            # but not its author, which is the wrong way round: Surazal's NIT is
            # where the folder mapping, the install engine and these screens
            # come from. He asks to be credited under that pseudonym.
            "<p>Vaultkeeper is a port of the <b>NWN Installer Tool</b> by "
            "<b>Surazal</b>, whose design and behaviour it follows throughout.</p>"
            "<ul style='margin-left: 20px;'>"
            "<li><a href='https://neverwintervault.org/users/kevls'>BicFileReader</a> "
            "— kevL's</li>"
            "<li><a href='https://www.codeproject.com/articles/31702/net-targa-image-reader'>"
            "TargaImage</a> — .NET Targa Image Reader</li>"
            "<li><a href='https://www.nuget.org/packages/UDE.CSharp'>UDE</a> "
            "— UDE package on nuget.org</li>"
            "</ul>"
        )
        credits_browser = QTextBrowser()
        credits_browser.setHtml(credits_text)
        credits_browser.setReadOnly(True)
        # Make the browser not focusable to keep focus on buttons
        credits_browser.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(credits_browser)

        # OK button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @classmethod
    def show_dialog(cls, parent: QWidget | None = None) -> None:
        """Construct and show the About dialog (modal)."""
        dlg = cls(parent)
        dlg.exec()
