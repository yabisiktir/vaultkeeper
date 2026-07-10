"""Tests for the help content model (VB HelpFileManager + bundled CHM topics)."""

from __future__ import annotations

from vaultkeeper.ui import help_model as H


def test_help_content_is_bundled():
    assert H.available()
    assert (H.help_root() / "toc.hhc").is_file()


def test_topic_for_control_is_case_insensitive():
    # VB opens "<ControlName>.htm"; the bundled files are lower-cased.
    assert H.topic_for_control("BhMapFiles").name == "bhmapfiles.htm"
    assert H.topic_for_control("MSVIEWHELP").name == "msviewhelp.htm"
    # A trailing .htm is tolerated.
    assert H.topic_for_control("RbLoadscreenHelp.htm").name == "rbloadscreenhelp.htm"


def test_topic_for_control_unknown_returns_none():
    assert H.topic_for_control("NoSuchControl12345") is None


def test_topic_for_control_blank_falls_back_to_default():
    assert H.topic_for_control("").name == H.DEFAULT_TOPIC.lower()


def test_topic_title_reads_html_title():
    path = H.topic_for_control("managemenu")
    assert path is not None
    assert H.topic_title(path) == "Use the Manage menu"


def test_load_toc_builds_nested_tree():
    toc = H.load_toc()
    assert toc  # non-empty
    # The first section is the product root with real children.
    root = toc[0]
    assert root.name == "Neverwinter Nights Installer Tool"
    assert root.local == "MsViewHelp.htm"
    assert root.children
    child_names = {c.name for c in root.children}
    assert "Overview" in child_names
    # A section with grandchildren (What's new -> Version History).
    whats_new = next(c for c in root.children if c.name == "What's new")
    assert any(g.name == "Version History" for g in whats_new.children)


def test_parse_toc_handles_minimal_sitemap():
    hhc = """
    <ul>
      <li><object type="text/sitemap">
        <param name="Name" value="Root">
        <param name="Local" value="root.htm">
      </object>
      <ul>
        <li><object type="text/sitemap">
          <param name="Name" value="Child">
          <param name="Local" value="child.htm">
        </object></li>
      </ul>
      </li>
    </ul>
    """
    nodes = H.parse_toc(hhc)
    assert len(nodes) == 1
    assert nodes[0].name == "Root"
    assert nodes[0].local == "root.htm"
    assert [c.name for c in nodes[0].children] == ["Child"]
