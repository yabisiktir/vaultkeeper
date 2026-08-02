"""Combining a PRC-ified archive's build tag with its Vault page's requirements."""

from __future__ import annotations

from vaultkeeper.vault.prc_dependencies import family_of, merge


def _vault(*titles):
    return [{"title": t, "url": f"https://neverwintervault.org/{t}"} for t in titles]


def _names(requirements):
    return sorted(r.name for r in requirements)


# -- what needs no asking ----------------------------------------------------- #
def test_things_only_the_vault_knows_about_are_taken_as_read():
    """Tilesets and haks are why the Vault page is consulted at all."""
    plan = merge(("PRC8",), _vault("Lord of Worms Tileset", "Project Q"))
    assert plan.settled
    assert _names(plan.agreed) == ["Lord of Worms Tileset", "PRC8", "Project Q"]


def test_things_only_the_archive_knows_about_are_taken_as_read():
    """The Vault page describes the original, which may not have needed PRC."""
    plan = merge(("PRC8",), _vault("Project Q"))
    assert plan.settled
    assert _names(plan.agreed) == ["PRC8", "Project Q"]


def test_agreement_is_not_a_question():
    plan = merge(("CEP3",), _vault("CEP 3"))
    assert plan.settled
    assert _names(plan.agreed) == ["CEP3"]


def test_a_module_with_no_requirements_at_all_is_settled():
    plan = merge((), [])
    assert plan.settled and plan.agreed == []


# -- what does need asking ---------------------------------------------------- #
def test_a_disagreement_within_one_family_becomes_a_choice():
    """The page says CEP 2.65 because it describes the module before the rebuild."""
    plan = merge(("PRC8", "CEP3"), _vault("CEP 2.65", "Project Q"))
    assert not plan.settled
    assert [c.family for c in plan.choices] == ["CEP"]
    assert _names(plan.agreed) == ["PRC8", "Project Q"]


def test_the_archive_is_recommended_but_not_imposed():
    """It describes the file being installed; the page describes its ancestor."""
    plan = merge(("CEP3",), _vault("CEP 2.65"))
    choice = plan.choices[0]
    assert choice.recommended.name == "CEP3"
    assert choice.recommended.source == "archive"
    assert _names(choice.options) == ["CEP 2.65", "CEP3"]


def test_the_question_names_both_sides():
    plan = merge(("CEP3",), _vault("CEP 2.65"))
    question = plan.choices[0].question
    assert "CEP3" in question and "CEP 2.65" in question


def test_a_vault_link_is_kept_so_the_user_can_go_and_look():
    plan = merge(("CEP3",), _vault("CEP 2.65"))
    vault_option = next(o for o in plan.choices[0].options if o.source == "vault")
    assert vault_option.url.startswith("https://neverwintervault.org/")


# -- resolving ---------------------------------------------------------------- #
def test_the_users_pick_wins():
    plan = merge(("CEP3",), _vault("CEP 2.65"))
    assert _names(plan.resolve({"CEP": "CEP 2.65"})) == ["CEP 2.65"]


def test_an_unanswered_choice_falls_back_to_the_recommendation():
    """Dropping it would leave the module missing a dependency entirely."""
    plan = merge(("PRC8", "CEP3"), _vault("CEP 2.65"))
    assert _names(plan.resolve({})) == ["CEP3", "PRC8"]


def test_resolving_keeps_everything_that_was_never_in_question():
    plan = merge(("CEP3",), _vault("CEP 2.65", "Project Q"))
    assert _names(plan.resolve({"CEP": "CEP 2.65"})) == ["CEP 2.65", "Project Q"]


# -- grouping ----------------------------------------------------------------- #
def test_the_families_that_can_conflict_are_recognised_by_more_than_a_prefix():
    assert family_of("CEP 2.65") == "CEP"
    assert family_of("Community Expansion Pack 2") == "CEP"
    assert family_of("PRC8") == "PRC"
    assert family_of("Player Resource Consortium") == "PRC"


def test_unrelated_projects_never_collide():
    assert family_of("Project Q") != family_of("Lord of Worms Tileset")
    plan = merge((), _vault("Project Q", "Lord of Worms Tileset"))
    assert plan.settled and len(plan.agreed) == 2


def test_the_same_project_listed_twice_is_listed_once():
    plan = merge(("CEP3",), _vault("CEP 3", "CEP3"))
    assert plan.settled
    assert len(plan.agreed) == 1


def test_a_blank_entry_is_ignored_rather_than_becoming_a_requirement():
    plan = merge(("", None), [{"title": "  ", "url": ""}, {"title": "Project Q"}])
    assert _names(plan.agreed) == ["Project Q"]
