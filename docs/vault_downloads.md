# Downloading from the Neverwinter Vault

Two things decide how a Vault project is read, and both are under
**Settings → Downloads**.

## How a project is read

| Setting | What happens |
|---|---|
| **The Vault's API** (default) | One request to `neverwintervault.org/api/v1/` returns the project's title, every attachment with its real filename and byte size, and the projects it requires. |
| **Read the project's web page** | The project page's HTML is fetched and the file rows parsed out of it, as the port did before — and as NIT did up to v7.4.1. |

The API is the default because it is the one the Vault intends to keep
answering. NIT v8.0 switched to it for a stated reason: the Vault is being
redesigned, and a redesign moves the markup a scraper depends on without
changing a single fact the scraper was after. It is also simply better
information — the page gives a link's display text, where the API gives the
filename that will land on disk and the size before anything is fetched.

Page scraping stays as a fallback for as long as the pages exist. If the API is
ever unavailable and the pages are not, switching back is one setting, not a new
release.

Either way the result is the same list of files, so nothing downstream — the
file list, the checkboxes, the download queue, the Required Projects panel —
knows or cares which one answered.

### What the API is asked

Four queries, all addressed from the download rules rather than from the code:

| Query | Used for |
|---|---|
| `projects/by-url?url=…` | a project from its page URL |
| `projects/<id>` | a project from its Vault id — one request fewer, used whenever the URL carries an id |
| `projects/by-title?title=…` | finding a module's page from an archive's name (Install PRC Module) |
| `files/by-fid?fid=…` | the file behind a `pubdlcnt.php?fid=…` counter link |

A counter link is still followed to the file when the download starts: the API
describes files, it does not serve them.

## Keeping a mod's Vault page attached to it

Three commands, all of them the API's doing — none was practical against a
scraped page.

| Where | Command | What it does |
|---|---|---|
| Edit menu | **Find Mod's Web Page Link** | Works out which Vault project a mod came from, and offers to save it. |
| Edit menu | **Check for Mod Updates** | Opens Download Project on the mod's own link, already fetched, so its current files can be compared with what was downloaded. |
| Tools menu | **Validate Mod Web Links** | Checks every recorded link at once and reports what has gone stale. |

### How a page is identified

Searching the Vault for a mod's name is not enough: "A Call for Heroes" matches
three Selendi modules and a music pack, and nothing about the titles says which.

So the title search is only the shortlist. Each candidate project is then asked
what files it publishes, and the ones publishing a **file the mod already
holds** are kept. That is evidence rather than resemblance — the mod folder
holds `almraivenhak.rar`, and exactly one project on the Vault publishes a file
by that name.

Where no project publishes any of the mod's files, a project whose title is
*exactly* the mod's name is offered instead, marked as matched by name only.
This is the case for anything repackaged by someone else — a PRC-ified module
arrives as `Cormyrean Nights [PRC8-CEP3].7z`, which appears on no Vault page —
and it is a suggestion, not a finding.

### What gets written, and what does not

**Validate Mod Web Links** changes nothing by itself. Its *Update* button writes
back only the unambiguous corrections: a link the Vault answered with a
different address for, or a single project publishing one of the mod's own
files. Everything else is listed with its candidates and left alone, because a
batch that writes one wrong link writes it to every mod at once.

Name-only matches and several-candidate cases are settled one mod at a time
through **Find Mod's Web Page Link**, where the choice is shown and confirmed.

### The report

Five sections, matching the original's:

* **Revised** — the Vault answers with a different address (usually the
  `neverwintervault.net` → `.org` migration).
* **Non-migrated Rolovault** — a live Rolo Vault address, which has no project
  page at all.
* **Invalid** — a Vault project address the Vault does not recognise.
* **No web link** — a mod that could have one and has not.
* **Non-Vault** — a Nexus or forum link. Left alone; it is not wrong, it is
  just not a Vault page.

Restorers, the base-game modules NWN installed, converted `.nwm` mods and the
application's own auto-maintained mods are skipped: none has a Vault page, and
searching for one would report two dozen problems that are nothing of the kind.

## The download rules

The rules file is **published online, not shipped with the application**, and
that is the point of it. It carries the Vault's API addresses, URL redirects,
save-name mappings, excluded extensions and per-project fixes. When something
at the Vault changes, the rules are edited once on the server and every
installation picks the change up — nobody waits for a release.

**Keep the Vault download rules up to date** (on by default) fetches them, at
most once a day, from:

1. `https://lazworks.azurewebsites.net/DownloadRulesV3.txt`
2. `https://file-metadata.nexusmods.com/file/nexus-readmes/180/869/DownloadRulesV3.txt`

— the second being the standby if the first cannot be reached. Whichever
answers is cached in the Vaultkeeper data folder beside the profile store.

Turning the setting off uses only what is already on this machine. There is
always something: a copy of the published file ships inside the package as the
floor, so an offline machine gets a complete, coherent rule set rather than
none. The bundled copy is only ever the fallback — a fetched or cached file
always wins.

Pressing Play never waits on this. The play loop needs the rules' save-name map,
and takes the cached or bundled copy immediately rather than risking a stalled
game launch on a bad connection.

### Format

`V3` in the filename is the *format* version; `RevisionNumber` inside the file
is the content version, bumped by whoever edits the published rules. An
application reads the format version it understands, so a newer format can be
published beside the current one without breaking anything already installed.

The port parses the parts it acts on — the API addresses, the save-name map,
redirects, filename prefixes, excluded extensions, unsupported and
no-installer projects. The file also carries 224 per-project blocks assigning
each Vault project a mod folder and group; those are not read yet, and a
download's folder and group come from the dialog instead.
