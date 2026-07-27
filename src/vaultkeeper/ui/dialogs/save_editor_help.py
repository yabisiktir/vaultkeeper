"""An in-app guide for the Save Game Editor (a read-only help dialog)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

_HELP_HTML = """
<h2>Save Game Editor — Guide</h2>
<p>The Save Game Viewer can also <b>edit</b> a save and write the result to a
<b>brand-new save</b>. Your original save is never modified — it is your backup —
so editing is safe to experiment with.</p>

<h3>Quick start</h3>
<ol>
  <li>Pick a save on the left.</li>
  <li>Click <b>Edit</b> to turn on edit mode — a <b>pending changes</b> panel
      appears.</li>
  <li>Make changes (below). Each is <i>staged</i> (nothing is written yet) and
      listed in the panel, with a ● marker on what you changed.</li>
  <li>Commit with <b>Save as New Save…</b> (writes a new save, original untouched) or
      <b>Overwrite This Save…</b> (replaces the selected save — the old version is
      moved to a timestamped <code>vaultkeeper_backups</code> folder first, and the
      edited save is written &amp; verified before the old one is touched).</li>
</ol>
<p>Use <b>Discard All</b> to drop staged changes; turning <b>Edit</b> off asks first
if there are unsaved changes.</p>

<h3>What you can edit</h3>
<p>Most edits are reached by <b>selecting</b> a node or <b>right-clicking</b> it in
edit mode.</p>
<ul>
  <li><b>Stores:</b> area → Stores → select a store → <b>Edit Store…</b> (pricing,
      gold, black market).</li>
  <li><b>Item property value:</b> select a property under one of your items →
      <b>Edit…</b> (magnitude, or a Cast-Spell property's uses/day).</li>
  <li><b>Add / remove a property:</b> right-click an item → <b>Add a property…</b>;
      right-click a property → <b>Remove this property</b>.</li>
  <li><b>Add items:</b> right-click one of your items — or any store / creature /
      container item — → <b>Add a copy to my inventory</b>.</li>
  <li><b>Skills:</b> select a skill → <b>Edit…</b> to set its rank.</li>
  <li><b>Feats:</b> right-click <b>Feats</b> → <b>Add a feat…</b>; right-click a feat
      → <b>Remove this feat</b>.</li>
  <li><b>Spells:</b> Spells → class → a Known/Memorized level; right-click the level
      → <b>Add a spell…</b>, or a spell → <b>Remove this spell</b>.</li>
</ul>
<p>The feat/spell picker is a browsable <b>ID + Name</b> table: scroll and click, or
type to filter by name or the raw id.</p>

<h3>PRC content</h3>
<p>If your game uses the <b>PRC</b>, it manages much of the character through its own
scripts and the hidden <i>skin</i> item:</p>
<ul>
  <li><b>Base-game</b> feats/skills/spells edit cleanly and persist.</li>
  <li><b>PRC</b> feats and <b>PRC prestige-class</b> spellbooks are marked
      <b>(PRC)</b>; PRC regenerates them on rest / level-up / load, so an edit here
      <b>may not stick</b>. The editor warns you first.</li>
</ul>
<p>Derived stats (AC, attack, saves, max HP) are recomputed by the engine from your
abilities, feats and gear — edit those <i>sources</i>, not the numbers.</p>

<h3>Safety</h3>
<ul>
  <li>Your original save is <b>never touched</b> — every save is a new folder.</li>
  <li>Edits apply to the save's <code>module.ifo</code> character and its
      <code>player.bic</code> mirror; the new save is re-read and verified.</li>
</ul>
<p><b>Always test an edited save in-game before relying on it</b>, especially
anything PRC-related.</p>
"""


class SaveEditorHelpDialog(QDialog):
    """A scrollable guide to editing saves."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Save Game Editor — Guide")
        self.resize(560, 640)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(_HELP_HTML)
        browser.setOpenExternalLinks(False)
        layout.addWidget(browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
