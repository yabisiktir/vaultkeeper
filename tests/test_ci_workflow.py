"""The CI workflow, checked against the build script it drives.

These cannot run the workflow — that needs GitHub — but they can catch the way
it rots: a path renamed in build_app.py while the workflow still names the old
one, which shows up as a green build uploading nothing, or a red one on a runner
nobody looks at for a week.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "build.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def test_the_workflow_exists_and_parses(workflow):
    assert set(workflow["jobs"]) == {"test", "build", "release"}


def test_it_builds_on_every_os_it_ships_for(workflow):
    """No cross-building: each artifact is made on the OS it targets."""
    labels = [m["label"] for m in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]]
    assert any("Windows" in label for label in labels)
    assert any("Linux" in label for label in labels)
    assert any("macOS" in label for label in labels)


def test_macos_is_built_for_both_cpus(workflow):
    """PySide6 wheels are per-arch, so one macOS build serves only one CPU."""
    runners = [m["os"] for m in workflow["jobs"]["build"]["strategy"]["matrix"]["include"]]
    assert "macos-14" in runners, "Apple Silicon"
    assert "macos-13" in runners, "Intel"


def test_it_runs_the_same_build_script_a_developer_runs(workflow):
    steps = workflow["jobs"]["build"]["steps"]
    assert any("scripts/build_app.py" in str(step.get("run", "")) for step in steps)


def test_the_uploaded_paths_match_what_the_build_script_produces(workflow):
    """The quiet failure: a renamed artifact and a workflow still globbing the
    old name. `if-no-files-found: error` turns that red, but only if the globs
    are right in the first place."""
    upload = next(
        step for step in workflow["jobs"]["build"]["steps"]
        if "upload-artifact" in str(step.get("uses", ""))
    )
    globs = upload["with"]["path"]
    driver = (_ROOT / "scripts" / "build_app.py").read_text(encoding="utf-8")
    for suffix, produced_by in ((".dmg", "package_macos"), (".zip", "package_windows"),
                                (".tar.gz", "package_linux")):
        assert suffix in globs, f"{suffix} is produced but never uploaded"
        assert produced_by in driver
    assert upload["with"]["if-no-files-found"] == "error"


def test_a_frozen_binary_that_cannot_start_fails_the_build(workflow):
    """The failure mode a build alone never catches."""
    steps = workflow["jobs"]["build"]["steps"]
    assert sum("Smoke test" in str(step.get("name", "")) for step in steps) >= 3


def test_the_smoke_tests_name_the_paths_pyinstaller_actually_writes(workflow):
    """EXE(name=...) and COLLECT(name=...) in the spec decide these."""
    spec = (_ROOT / "packaging" / "vaultkeeper.spec").read_text(encoding="utf-8")
    assert 'name="vaultkeeper"' in spec       # the executable and the folder
    assert 'name="Vaultkeeper.app"' in spec    # the macOS bundle

    steps = str(workflow["jobs"]["build"]["steps"])
    assert "Vaultkeeper.app/Contents/MacOS/vaultkeeper" in steps
    assert "dist/vaultkeeper/vaultkeeper" in steps


def test_tests_run_before_anything_is_built(workflow):
    assert workflow["jobs"]["build"]["needs"] == "test"


def test_a_release_is_only_cut_from_a_tag_and_starts_as_a_draft(workflow):
    release = workflow["jobs"]["release"]
    assert "refs/tags/v" in release["if"]
    publish = next(s for s in release["steps"] if "gh-release" in str(s.get("uses", "")))
    assert publish["with"]["draft"] is True, "a human should see the artifacts first"


def test_it_checks_out_the_save_editor_too(workflow):
    """Vaultkeeper depends on it and pip cannot resolve it from PyPI, so every
    job needs both repositories present."""
    for job in ("test", "build"):
        checkouts = [
            step for step in workflow["jobs"][job]["steps"]
            if "checkout" in str(step.get("uses", ""))
        ]
        assert len(checkouts) == 2, f"{job} must check out both repos"
        assert any("SAVE_EDITOR_REPO" in str(c.get("with", {})) for c in checkouts)


def test_the_editor_is_installed_before_vaultkeeper(workflow):
    """pip install -e . would otherwise try, and fail, to resolve it."""
    runs = [str(s.get("run", "")) for s in workflow["jobs"]["build"]["steps"]]
    editor = next(i for i, r in enumerate(runs) if "install -e ./nwn-save-editor" in r)
    vaultkeeper = next(i for i, r in enumerate(runs) if "install -e ./vaultkeeper" in r)
    assert editor < vaultkeeper


def test_the_editor_repo_is_named_for_real(workflow):
    """It was a placeholder until the repos existed; now it must be a real one."""
    repo = workflow["env"]["SAVE_EDITOR_REPO"]
    owner, _, name = repo.partition("/")
    assert owner and name, repo
    assert owner != "OWNER", "still the placeholder"
    assert name == "nwn-save-editor", repo


def test_every_editor_checkout_carries_a_token(workflow):
    """The editor repo is private, and the automatic token cannot see it.

    ``GITHUB_TOKEN`` is scoped to the repository running the workflow, so a
    cross-repo checkout of a private repo fails with "Repository not found" —
    which reads like the name is wrong rather than the permission.
    """
    for job in ("test", "build"):
        checkouts = [
            step for step in workflow["jobs"][job]["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout")
            and "repository" in (step.get("with") or {})
        ]
        assert checkouts, f"{job} does not check the editor out"
        for step in checkouts:
            assert "token" in step["with"], f"{job}: cross-repo checkout without a token"


def test_the_bundled_seven_zip_is_verified_before_a_build(workflow):
    """Without it a built Vaultkeeper installs nothing, and nothing else notices."""
    steps = str(workflow["jobs"]["test"]["steps"])
    assert "fetch_tools.py --check" in steps


def test_linux_gets_the_libraries_qt_needs(workflow):
    """Qt will not start on a bare ubuntu runner; this is the usual first red."""
    steps = str(workflow["jobs"]["build"]["steps"])
    for library in ("libegl1", "libxkbcommon-x11-0", "libxcb-cursor0"):
        assert library in steps
