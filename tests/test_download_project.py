

def test_copy_direct_link_is_offered_only_when_there_is_one(qtbot):
    """VB CmCopyLink. A menu entry that silently copies "" is worse than a
    greyed-out one, so the action follows whether the file has a link."""
    from vaultkeeper.vault.scraper_info import VaultScraperInfo

    with_link = VaultScraperInfo(filename="a.zip", direct_url="https://x.invalid/a.zip")
    without = VaultScraperInfo(filename="b.zip")
    assert bool(with_link.direct_url or with_link.counter_url)
    assert not (without.direct_url or without.counter_url)
