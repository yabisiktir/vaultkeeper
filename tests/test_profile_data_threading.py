"""Reading the profile while a background job writes to it.

Downloads and installs moved to a worker thread, and the window keeps drawing the
mod list from the same dictionaries the job is editing. Python does not tolerate
that: listing mods while one is being created raises "dictionary changed size
during iteration". These tests hold that shut.
"""

from __future__ import annotations

import threading
import time

from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path):
    mods = tmp_path / "Profiles" / "P"
    mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _hammer(reader, writer, seconds: float = 1.5):
    """Run a reader and a writer together; return whatever blew up."""
    errors: list[tuple[str, BaseException]] = []
    stop = threading.Event()
    counts = {"reads": 0, "writes": 0}

    def run(name, fn, tally):
        while not stop.is_set():
            try:
                fn()
                counts[tally] += 1
            except BaseException as exc:  # noqa: BLE001 — that is the point
                errors.append((name, exc))
                return

    threads = [
        threading.Thread(target=run, args=("writer", writer, "writes"), daemon=True),
        threading.Thread(target=run, args=("reader", reader, "reads"), daemon=True),
        threading.Thread(target=run, args=("reader", reader, "reads"), daemon=True),
    ]
    for thread in threads:
        thread.start()
    time.sleep(seconds)
    stop.set()
    for thread in threads:
        thread.join(2)
    return errors, counts


def test_listing_mods_while_one_is_created_does_not_blow_up(tmp_path):
    """The exact crash: a comprehension over mod_list while a mod is inserted."""
    controller = _controller(tmp_path)
    for index in range(200):
        controller.create_mod(f"Mod {index:03d}")
    made = iter(range(100_000))

    def write():
        controller.create_mod(f"Worker {next(made)}")

    def read():
        controller.groups()
        controller.counts()

    errors, counts = _hammer(read, write)
    assert not errors, errors[:2]
    assert counts["reads"] > 0 and counts["writes"] > 0  # they really did overlap


def test_walking_a_mods_files_while_an_install_rewrites_them_is_safe(tmp_path):
    """The mod list was only the first dict — file_list crashed the same way."""
    from vaultkeeper.core.archive import FakeArchiveExtractor
    from vaultkeeper.vault.http import FakeHttpClient, HttpResponse
    from vaultkeeper.vault.scraper_info import VaultScraperInfo

    controller = _controller(tmp_path)
    urls = {
        f"http://cdn/p{i}.zip": HttpResponse(f"http://cdn/p{i}.zip", 200, content=b"Z")
        for i in range(30)
    }
    controller._http = FakeHttpClient(urls)
    controller._extractor = FakeArchiveExtractor(contents={
        f"p{i}.zip": {f"override/o{i}_{j}.2da": b"O" for j in range(8)}
        for i in range(30)
    })
    installs = iter(range(30))

    def write():
        index = next(installs)
        controller.install_downloaded_project(
            [VaultScraperInfo(direct_url=f"http://cdn/p{index}.zip",
                              filename=f"p{index}.zip")],
            f"Job Mod {index}",
        )

    def read():
        controller.groups()
        for name in controller.pd.mod_keys:
            md = controller.pd.mod_item(name)
            if md is not None:
                list(md.files)                       # the Contents pane
        controller.pd.get_conflicts("override\\o1_1.2da")   # walks file_list
        controller.installed_by_group()                     # walks installed state

    errors, counts = _hammer(read, write, seconds=2.0)
    assert not errors, errors[:2]
    assert counts["reads"] > 0 and counts["writes"] > 0


def test_the_lock_is_re_entrant(tmp_path):
    """Guarded operations call each other — adding a mod seeds its group row."""
    controller = _controller(tmp_path)
    with controller.pd.lock:
        controller.create_mod("Nested")          # takes it again from the inside
        assert controller.pd.mod_item("Nested") is not None


def test_a_job_no_longer_disables_the_window(qtbot, tmp_path):
    """It used to, because reading while a job wrote really did crash.

    ProfileData guards itself now, so the point of the flag is only that two
    installs would fight over the same game files.
    """
    from PySide6.QtWidgets import QWidget

    from vaultkeeper.ui.background import claim, job_running

    window = QWidget()
    qtbot.addWidget(window)
    dialog = QWidget(window)
    assert not job_running()

    release = claim(dialog)
    assert job_running()
    assert window.isEnabled()      # the whole point
    release()
    assert not job_running()


def test_two_dialogs_do_not_release_each_others_claim(qtbot):
    from PySide6.QtWidgets import QWidget

    from vaultkeeper.ui.background import claim, job_running

    first, second = QWidget(), QWidget()
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    release_first = claim(first)
    release_second = claim(second)
    release_first()
    assert job_running()           # the second is still going
    release_second()
    assert not job_running()
