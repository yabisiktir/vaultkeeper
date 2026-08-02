# Installing a PRC-ified Vault module — Guide

**Play → Install a PRC-ified Vault Module** opens a four-step dialog for the public
Google Drive collection of Neverwinter Vault modules rebuilt to run under PRC.

It sits beside **Download and Install Neverwinter Vault Project**, which it does not
replace: that one takes a Vault page and downloads its files. This one takes an
archive from Drive, then goes and finds the Vault page itself, because the two halves
of a PRC-ified module live in different places.

## Why it takes four steps

The Drive folder holds the archive and nothing else. What the module *needs* — CEP,
tilesets, override haks — is documented on its Vault page, and the folder does not
link to it. So the module and its requirements have to be paired up, and both ends of
that pairing are guesses that only you can confirm:

* The **file name** is the only clue to which Vault page belongs to this archive, and
  the Vault's search is not precise. "A Call for Heroes" returns *Selendi: A Call For
  Heroes* 1, 2 and 3 with identical scores. Ranking sorts the shortlist; it cannot
  pick, and the wrong page attaches the wrong dependencies.
* The **Vault page describes the original module**; the archive is a rebuild. They can
  legitimately disagree — the page says CEP 2.65, the file name says `[PRC8-CEP3]`.
  The archive's tag is about the thing actually being installed, so it is
  *recommended*, but it is also three characters typed by hand by whoever published
  the folder, and a wrong CEP is a broken install.

Nothing in either case is decided for you.

## The four steps

1. **Choose the module.** The address box starts on the published collection; press
   **Browse** to list it. Subfolders open on a double-click and **Up** goes back.
   Selecting an archive fills in the rest of the dialog. You can also paste a link to
   one file — a link carries no name and no build tag, so you type the module's title
   yourself and its requirements then come from the Vault page alone.
2. **Confirm the Vault page.** Ranked, never chosen. Pick the row and press **Use this
   page**. If the module has no Vault page at all, **No Vault page** carries on with
   just the build tag.
3. **Settle what it needs.** Any disagreement appears as a question with both answers
   offered and neither selected; **Install** stays disabled until every one is
   answered. Below it, the settled requirements:
   * *Will be downloaded from the Vault* — ticked.
   * *Already installed as '…'* — listed and **unticked**, so you can see that the CEP
     you have answers the CEP this wants, and decide. Re-tick it to reinstall anyway.
     The match is by family, so an installed "CEP 2.65" answers a required "CEP3".
   * *No Vault page known* — a build tag like `PRC8` names no page, so there is nothing
     to download and the row has no tick box. Install that one yourself.
4. **Install.** Name the mod folder, optionally pick a group, and go. Dependencies are
   installed **first and each as its own mod**, not folded into the module's installer,
   because CEP is shared between modules and has to stay separately uninstallable.
   Every step reports its own outcome, so a partial failure names itself.

## While it is working

The whole job runs in the background, so the window keeps painting and keeps
telling you where it is — through the download (megabytes of megabytes) and then
through the half that takes just as long: extracting the archive, building the
installer, and copying the files into the game. Where there is a count you get a
real bar; where there isn't — extracting a big archive is one opaque step — the
bar just shows it is busy and the line names what it is doing.

**Cancel** stops the transfer between chunks and removes the part-downloaded file,
so nothing half-written is ever left under an archive's name. Anything already
installed before you cancelled stays installed.

The main window is disabled until the job finishes. That is deliberate: installing
creates mods and rewrites the tool's own records, and no other screen expects that
to happen underneath it. The dialog will not close mid-job for the same reason —
cancel first, or wait.

## When Drive says no

Google Drive answers three different failures with HTTP 200 and a web page: a
confirmation step for a very large file, "quota exceeded" when a file has been popular
that day, and a sign-in prompt if sharing changed. Trusting the status code would
leave a web page on disk named `.7z`, and you would only find out when the install
failed. The download checks what actually came back: a confirmation is followed
automatically, and the other two stop with the reason in the results list. A quota
refusal usually clears within a day.
