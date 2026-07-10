"""CharacterViewer — the Character Explorer / Character Summary dialog (VB CharacterViewer).

Lists the player's characters (local vault + one per game save) on the left and
shows the selected character's multi-line summary plus portrait on the right.
Read-only. Data comes from ``ProfileController.character_files`` /
``portrait_path``; the summary text is produced by ``game.character``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.formats.tga_reader import TGAReader
from vaultkeeper.ui import resources as R

_PORTRAIT_BOX = 128  # px — the portrait preview is a square this size.


def tga_to_pixmap(path: Path, *, box: int = _PORTRAIT_BOX) -> QPixmap | None:
    """Load a TGA portrait as a QPixmap scaled to fit ``box`` (None on failure)."""
    image = TGAReader().read_file(path)
    if image is None or image.width <= 0 or image.height <= 0:
        return None
    qimg = QImage(
        image.to_rgba(),
        image.width,
        image.height,
        QImage.Format.Format_RGBA8888,
    )
    if qimg.isNull():
        return None
    return QPixmap.fromImage(qimg).scaled(
        box,
        box,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class CharacterViewer(QDialog):
    """Browse characters with their summary and portrait."""

    def __init__(
        self, characters: list, portrait_resolver=None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        # VB title shows the file count (e.g. "Character Explorer — 751 files shown").
        count = len(characters)
        suffix = f" — {count:,} file{'s' if count != 1 else ''} shown" if count else ""
        self.setWindowTitle(f"Character Explorer{suffix}")
        self.setWindowIcon(R.get_icon("LookupUser_16x"))
        self.resize(680, 460)
        self._characters = characters
        self._resolve_portrait = portrait_resolver

        layout = QHBoxLayout(self)

        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        for cf in characters:
            level = cf.info.level if cf.info.is_valid else "?"
            item = QListWidgetItem(f"{cf.display_name}  (L{level})")
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_row)
        layout.addWidget(self._list)

        right = QVBoxLayout()
        self._portrait = QLabel()
        self._portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._portrait.setFixedHeight(_PORTRAIT_BOX)
        right.addWidget(self._portrait)

        self._tabs = QTabWidget()
        self._summary = QTextEdit()
        self._summary.setReadOnly(True)
        self._tabs.addTab(self._summary, "Summary")
        self._tabs.addTab(self._build_skills_tab(), "Skills")
        self._tabs.addTab(self._build_feats_tab(), "Feats")
        right.addWidget(self._tabs, 1)
        layout.addLayout(right, 1)

        if characters:
            self._list.setCurrentRow(0)
        else:
            self._summary.setPlainText("No character files detected.")

    def _build_skills_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._skills = QTreeWidget()
        self._skills.setHeaderLabels(["Skill", "Rank"])
        self._skills.setRootIsDecorated(False)
        self._skills.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._skills.currentItemChanged.connect(self._on_skill)
        splitter.addWidget(self._skills)
        self._skill_desc = QTextEdit()
        self._skill_desc.setReadOnly(True)
        splitter.addWidget(self._skill_desc)
        splitter.setSizes([260, 120])
        return splitter

    def _build_feats_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._feats = QListWidget()
        self._feats.currentRowChanged.connect(self._on_feat)
        splitter.addWidget(self._feats)
        self._feat_desc = QTextEdit()
        self._feat_desc.setReadOnly(True)
        splitter.addWidget(self._feat_desc)
        splitter.setSizes([260, 120])
        return splitter

    def _on_row(self, row: int) -> None:
        if row < 0 or row >= len(self._characters):
            self._summary.clear()
            self._portrait.clear()
            self._skills.clear()
            self._feats.clear()
            self._skill_desc.clear()
            self._feat_desc.clear()
            return
        cf = self._characters[row]
        self._summary.setPlainText(cf.summary(show_stats=True))
        self._show_portrait(cf)
        self._populate_skills_and_feats(cf)

    def _populate_skills_and_feats(self, cf) -> None:
        self._skills.clear()
        self._skill_desc.clear()
        self._feats.clear()
        self._feat_desc.clear()
        self._skill_rows = cf.skills() if cf.info.is_valid else []
        for name, rank, _desc in self._skill_rows:
            self._skills.addTopLevelItem(QTreeWidgetItem([name, str(rank)]))
        self._feat_rows = cf.feats() if cf.info.is_valid else []
        for name, _desc in self._feat_rows:
            self._feats.addItem(name)
        if self._skill_rows:
            self._skills.setCurrentItem(self._skills.topLevelItem(0))
        if self._feat_rows:
            self._feats.setCurrentRow(0)

    def _on_skill(self, current, _previous=None) -> None:
        row = self._skills.indexOfTopLevelItem(current) if current is not None else -1
        if 0 <= row < len(getattr(self, "_skill_rows", [])):
            self._skill_desc.setPlainText(self._skill_rows[row][2])
        else:
            self._skill_desc.clear()

    def _on_feat(self, row: int) -> None:
        if 0 <= row < len(getattr(self, "_feat_rows", [])):
            self._feat_desc.setPlainText(self._feat_rows[row][1])
        else:
            self._feat_desc.clear()

    def _show_portrait(self, cf) -> None:
        self._portrait.clear()
        resref = cf.info.portrait_resref if cf.info.is_valid else ""
        if not resref or self._resolve_portrait is None:
            return
        path = self._resolve_portrait(resref, cf.path.parent)
        if path is not None:
            pixmap = tga_to_pixmap(path)
            if pixmap is not None:
                self._portrait.setPixmap(pixmap)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> CharacterViewer:
        """Build and show the viewer from a controller's character files."""

        def resolver(resref: str, own_folder: Path):
            return controller.portrait_path(resref, extra_dirs=[own_folder])

        dlg = cls(controller.character_files(), resolver, parent)
        dlg.show()
        return dlg
