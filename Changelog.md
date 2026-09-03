# Changelog

All notable changes to the Ravenswood Gold Emissions Calculator.  
Format: release date, summary of changes.  Each release is a dated block.

Every block opens with a status line.  **Released** means the change is in a
formal release and any build carrying that release date or later has it.
**Unreleased** means the change is in the code and has not been through a
release, so a figure produced by the last released build will differ where the
change affects it.  The most recent formal release is 30 July 2026.

Each block also carries an impact line.  A defect entry describes what went
wrong, which reads as an incident whether or not it ever reached a released
build.  The impact line states what a released build actually produced, so a
reader can tell at once whether any reported figure is affected.

---

## 2026-09-03m

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** Not published.  Scope 2 falls 60,624 tCO2-e and Scope 3 rises by
the same amount, so the total does not move.  That is a reclassification, not
an abatement, and it must not be read as one.

### Added - National Greenhouse Accounts Factors 2026

The 2026 workbook is in the repository beside 2021 to 2025 and
`NgaFactors.csv` is rebuilt from all six, 679 rows.  Every financial year
past the last published edition takes the latest, so the whole forecast now
prices on 2026 rather than 2025.

**No fuel factor moved.**  Diesel 2,709.72 kg CO2-e/kL Scope 1 and 667.78
Scope 3, LPG 1,557.42 and 519.14, petroleum oils 539.32 and 698.40, greases
135.80 and 698.40, energy contents identical.  Scope 1 is unchanged to the
tonne, so nothing about the Safeguard position changes.

**Queensland electricity moved, and the movement is a reallocation.**

    QLD   scope 2   0.67 -> 0.65     scope 3   0.09 -> 0.11
          combined  0.76 -> 0.76

The Accounts moved 0.02 kg CO2-e/kWh from the generation factor to the
transmission loss factor.  Nothing about the Queensland grid got cleaner.
Scope 2 falls 60,624 tCO2-e and Category 3 rises by the same 60,624, and
anyone reading the 2.99% Scope 2 reduction as decarbonisation would be
wrong.  New South Wales, the North West Interconnected System and the
national factor are the same story; Victoria and South Australia fell 0.02 on
the combined figure and Tasmania rose 0.03, and those three are real.

The 2026 edition also adds two things this model does not yet use.  Table 2
publishes **market-based** factors for the first time, a national residual mix
of 0.79 kg CO2-e/kWh scope 2, which is what AASB S2 asks for alongside the
location-based figure where contractual instruments are held.  Table 3
publishes grid factors separately, including an off-grid factor of 0.67.

Western Australia and the Northern Territory now extract as well, which is why
the electricity row count rises from 14 to 18.

### Note - what is waiting to be published

Three changes stand between the published build and this one:

    grinding media on mass          +205,656 tCO2-e
    category 10 refining at 7.02       +  631 tCO2-e
    NGA 2026                                  0    (scope 2 -60,624,
                                                    scope 3 +60,624)
    total                           +206,287 tCO2-e

Scope 1 does not move at all, so the Safeguard position is untouched.

---

## 2026-09-03l

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** Not published.  The build now carries 205,656 tCO2-e more than the
published one, Scope 3 up 14.3% and the inventory up 3.7%, and it stays
unpublished until somebody reviews it on Changes and publishes it.

### Changed - grinding media is priced on tonnes, not on dollars

Grinding media is bought and reported by the tonne: 967 lines, every one in
tonnes, 129,662 t over the life of mine, which is 1.03 kg per tonne milled.
The mass was already there and the model was pricing it on expenditure
anyway.

On expenditure it came to 45,900 tCO2-e, which is **0.354 t CO2-e per tonne
of steel**.  Published steel is 1.92.  The spend basis was understating it
more than five fold.

The reason is not the country of origin, and looking for a country adjustment
would have hidden it.  The US EPA Iron Foundries factor is per dollar of
*foundry sector output*, which carries labour, machining and overhead as well
as metal.  Grinding media is close to pure metal by value, so a sector average
dollar prices it far too cheaply.  A country ratio applied to a diluted factor
would still have been wrong, and would have looked defensible.

It is now priced at **1.92 t CO2-e per tonne**, the worldsteel figure for 2024
collected from 93 companies representing 51% of world production.  Grinding
media rises to 251,557 tCO2-e - 1.94 per tonne once the Category 4 transport
margin is added on top, which stays on expenditure because it is distribution
rather than metal.

This is an interim.  A supplier product carbon footprint with the recycled
content stated is the better figure, and against a blast furnace route with
forging on top 1.92 is conservative.

The same problem applies to mill liners, wear parts and crusher spares, $84M
between them, but they are bought "Each" with no mass recorded, so they cannot
move without supplier data.

### Fixed - an assignment could have applied a per tonne factor to spend

Pointing an item at a factor changed the value and the source but not the
basis.  Assigning 1.92 t CO2-e per tonne to a group priced on expenditure
would have multiplied it by the money, which for grinding media would have
been 1.92 against $358M.

The factors offered are now narrowed to those measured in the same unit as
the items selected.  A selection spanning two units says so and offers
nothing, rather than letting one be applied to the other.

### Fixed - selecting an existing factor showed no fields

Choosing a regulated factor answered with a warning and nothing else, which
reads as a screen that has failed.  The fields are shown, read only, with the
reason they cannot be typed into beside them and the items the factor prices
underneath.

---

## 2026-09-03k

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None.  Both registers are empty, so every factor is still the
distributed one and no figure changes.

### Changed - a factor is added once, and items are pointed at it

Overrides were a mechanism of their own, with two kinds of record and a
precedence rule between them.  Then the override went too, because replacing a
factor everywhere is selecting every item that uses it and pointing them
somewhere else - the same act done in bulk, not a second mechanism.

There is one thing now, a factor, and two acts.

**Adding a factor** puts it in `Scope3/FactorRegister.csv` with a source, a
value, a unit and a reason.  It changes nothing on its own; it becomes
available to be pointed at.

**Assigning items** points one or more product groups at a factor already in
the register, in `Scope3/ItemFactors.csv`.  That is the only way a factor
other than the distributed one reaches an item.

Nobody types a value against an item.  A value only enters when a factor is
added, and a factor cannot be added without a reason, which is what stops the
model accumulating values nobody can account for.

A factor that is no longer right is marked **obsolete** rather than deleted.
It stays readable, so what an older figure was calculated on can still be
seen, and it drops out of the list items can be pointed at.

Tested end to end: seventeen items on the EPA Iron Foundries factor pointed at
one new factor together, then grinding media re-pointed at a second on its
own, with 0.349 preserved as the distributed figure on all seventeen.

**Factor maintenance** is one tab with two modes.  New presents empty fields.
Existing offers a keyword search and a dropdown, fills the fields and takes
the edit - for a factor added here, or for a distributed one that is not used
as its publisher issued it.  A regulated factor says plainly that it is not
edited here and points at the alternative: add the factor that should replace
it, then assign the items.

Items are searched, selected and assigned under **All factors**, beneath the
factor they currently carry, so choosing a factor and choosing what it applies
to are the same screen.

History moved to the foot of the sidebar.

### Fixed - the tracked input list still named the retired override file

`AttributeError: module 'LoaderFactors' has no attribute 'overrides_path'` on
startup.  The register and the assignments are tracked in its place, so
adding either marks the build stale.

---

## 2026-09-03j

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None.  No figure changes.  Editing a factor now reaches every
product group it prices, which is what it always meant.

### Changed - the factor tabs show factors, and where each one is used

The tables were listing the mapping rather than the factors.  A published
factor is carried against every product group it prices, so 387 rows are 66
factors, and reading them as a list makes one figure look like dozens of
duplicates.

The shape follows what the data actually is:

    Factor  (source and value)
      Group  (key)
        Description

Every factor tab now leads with the factors.  Beneath it is the list of items
those factors price, and selecting one or more factors filters that list to
what they touch.  "What does this factor reach" is the first question anybody
changing one asks, so it is a selection rather than a search.

A factor is its source **and** its value, not its source: all twenty six
capital spend bands cite the same EPA publication and differ only in the
figure.

  All factors    66 factors over 387 items
  Internal       27 factors over  30 items
  Spend-based    37 factors over 355 items

Exclusions moved into an expander on All factors, since they price nothing and
are not factors.

### Changed - a factor is maintained once

The maintenance grid was editing mapping rows, so correcting the Iron
Foundries factor would have meant typing the same figure seventeen times and
seventeen chances to type it differently.

It edits factors now, and the write reaches every group the factor prices.
The edit is keyed on the factor as it stood, so changing the value still finds
the rows it belonged to.  Regulated factors are refused here as everywhere
else; those are superseded with an override rather than retyped.

The override selector carries a keyword search and nothing else.  A keyword
reaches a factor through its source or through any group it prices, which is
how somebody looks for one; the category and the publication are already
columns in the list underneath.

Where two asset classes share a band, they share a factor, and changing it
changes both.  Three classes carry the 139.0 band - poured concrete
foundations, electrical contractors and other specialty trades - and that is
the band saying they are priced the same, not an accident.

---

## 2026-09-03i

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None.  No figure changes.  Publications made before this are still
readable and are listed beside the new ones.

### Changed - Changes compares against whichever build you name

The page had two fixed comparisons, one against the build this session opened
on and one against the published build.  They are the same question asked of
different baselines, so there is one comparison now and a control that says
what it is measured against:

- the published build, which is the default because it is what publishing
  writes
- the build this session opened on, which answers what have I done today
- any earlier publication still on disk, which answers what changed between
  two disclosures

Every published build is archived whole, so the third costs nothing but the
control to choose it.  Whatever is on screen, publishing still writes the
difference against the current published build, and the page says so.

### Changed - a publication is archived by when it happened

The archive was keyed on the build identifier, which is derived from the
inputs.  So republishing unchanged inputs produced the same folder name and
quietly overwrote the copy already there, which is exactly the history
somebody would come to the archive for.

A publication is an event and now gets its own folder, named
`<date>_<time>_<build id>`.  Nothing is overwritten.

Folders written under the old scheme carry the identifier alone and are still
read: the reader accepts both shapes and takes the publication date from the
build log where the folder name does not carry one.  Only the new shape is
written.  Both of the existing publications list and load correctly.

---

## 2026-09-03h

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.  No figure changes from any of this.
The refining factor entered separately moves Scope 3 by 630.7 tCO2-e, which
is the Category 10 figure and not a defect.

### Fixed - two thirds of the build was answering fifty questions eight hundred thousand times

Building the table took thirty three seconds.  Twenty one of them were in one
block: four functions mapped row by row over the finished frame to work out,
for each row, which publication its factor came from, what was done to it and
whether it may be edited.

Those functions are Python, do string work and call one another, so three of
them ran the fourth again.  There are about fifty distinct source strings in
eight hundred thousand rows, so the answer was computed three million times to
resolve fifty cases.

Resolved on the distinct values now and mapped back.  The build is 12.1
seconds.  Startup, which loads, projects and builds, is about half what it
was.

Also dropped a lowercasing pass over every text column, which was looking for
spellings of "nan" that the literal list already covers.

### Fixed - the override selector listed mappings, not factors

Searching for "steel" returned 71 rows that looked like duplicates, because
they are.  The factor table is a mapping: one published factor is carried
against every product group it prices.  The EPA Iron Foundries factor sits on
seventeen rows, Iron and Steel Forging on twenty three, Iron and Steel Mills
on twelve.  There are 44 factors behind 387 rows.

The selector now lists factors.  "steel" returns five.  Selecting one shows
the product groups it prices in a table beneath it, so the mapping is visible
without being the thing you have to read.

A factor is a source and a value together, not a source: all twenty six
capital spend bands cite the same EPA publication and differ only in the
figure, so a source alone would have caught all of them.  The search expands
on the pair for the same reason - a group whose description matches brings its
factor with it, and the factor brings the other groups it prices.

### Changed - an override can replace a factor everywhere it is used

"The EPA steel factor is wrong for this operation" is one decision.  Entering
it against each product group separately would have meant fifty two records
and fifty two chances to enter it differently.

An override now names either one product group or one factor.  A factor
override applies to every group priced by it; a group override is the
exception on top of that and wins where both apply.  The published figure is
recorded once, so a group override sitting inside a factor override still
reports what the publication said rather than what the other override made of
it.

### Changed - Changes says what this session did, then what publishing would write

The page compared the build against the published one, which is everything
that has accumulated since the last publication rather than the work in front
of you.

It now opens with what has moved since this session started, by scope and by
year, and says plainly when nothing has.  Beneath it, unchanged, is the
comparison against the published build, because that is what publishing
writes.  Publishing resets the session baseline to what was written.

A future reader could compare any two archived builds - every published build
is kept whole under Data/Published - but that is a separate screen and is not
built here.

---

## 2026-09-03g

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None.  Naming and navigation only.  No figure changes.

### Changed - the factors page is named on one principle

Six tabs named on three different principles.  "Maintained here" and "Used as
published" read as opposites and were not: one said who maintains a factor,
the other said how it is used.  "Used as published" and "National Greenhouse
Account" split the fixed factors by which file they sit in, which is an
implementation detail rather than a distinction.  "Without a publication"
read as a category when it is a list of one thing to fix.

Five tabs now, named for what each holds:

- **All factors** - every row, exclusions included, searchable, read only,
  with a status column saying where each number came from
- **Internal factors** - everything this company maintains
- **NGA factors** - the National Greenhouse Accounts, Scope 1 and 2 and the
  two Scope 3 rows drawn from them
- **Spend-based factors** - the environmentally extended input output set
- **Overrides** - published factors superseded by a company assumption

The fourth is named for the method rather than the publisher.  The GHG
Protocol calls this the spend-based method for Category 1, priced per dollar
of expenditure using environmentally extended input output factors.  The
database behind it is currently the US EPA supply chain factors version 1.3,
and naming a tab after a database that can be replaced would mean renaming the
tab when it is.  The publication is named on the row, where it belongs.

The maintenance tab holds everything editable rather than everything derived.
The AusLCI explosives factor is used exactly as published and is still this
company's to keep current, and it prices 188,585 tCO2-e - the second largest
line in Scope 3 - so a maintenance screen that left it out would send somebody
hunting through four hundred rows for it.  The status column distinguishes the
two.

The search sits on the override selector and nowhere else.  That is the one
place a factor has to be picked out by hand from nearly four hundred labels;
the grids elsewhere are read only and carry their own sort and search in the
toolbar.

### Note - one factor still names no publication

The Brisbane to Townsville air sector, 0.155 kg CO2-e per passenger
kilometre.  Every factor should trace to a source, so this is a defect rather
than a category, and the page counts it and warns while it stands.

---

## 2026-09-03f

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.  No figure changes.  The application
stops recomputing what it has already computed.

### Fixed - the table was rebuilt on every click

Loading and projecting were cached; the build was not.  So every page change
paid for an eight hundred thousand row build again to group figures it had
already produced.  Loading takes about ten seconds and projecting about
sixteen, both once; the build was the rest of the wait, every time.

The build is cached now, so it is made once and every page reads it.

### Changed - the build changes when Rebuild is pressed, and at no other time

Caching the build on the inputs would have rebuilt it the moment an
assumption was saved, which is half a minute of projection spent on a
keystroke and, worse, a figure that moves underneath somebody reading it.

The build is held against a token instead.  Saving an input writes it to
disk, marks the build stale and says so in the sidebar; the screen keeps
showing the build it was showing.  **Rebuild** is the only thing that changes
what is on screen, and an input changed on disk by something else is caught
the same way, by comparing the fingerprint against the one recorded when the
build was made.

An old figure that says it is old is better than a new one that arrives
unannounced.

### Changed - the Changes page is the previous Preview page

Renamed, with the publication note, the confirmation and the publish button
removed to the sidebar, and a year by year comparison with a total added
beneath the headline.  It always builds, because comparing the current inputs
against the published figures is the whole question it answers.

### Added - a search on the override selector

Choosing which factor to override meant reading a list of nearly four hundred
labels.  The selector now has a search across the description, the key and the
source, and filters for category and publication: "steel" narrows it to 71,
"grinding" to 2.

The search sits outside the entry form rather than in it.  A form submits only
on its own button, so a term typed inside one would not narrow anything until
the override had already been added.

---

## 2026-09-03e

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None.  No override is entered, so no figure changes.  The
mechanism is in place and does nothing until somebody uses it.

### Added - a company assumption can supersede a published factor

The US EPA supply chain factors are drawn from US production, and the EPA
says so: its own limitations state that international goods are modelled like
their domestic equivalents.  US steel is about two thirds electric arc
furnace and among the least carbon intensive in the world, so media and wear
parts bought from a blast furnace producer are priced by a factor from the
wrong industry.  Because the factor is per dollar rather than per tonne, the
cheaper import compounds the understatement rather than offsetting it.

Iron and steel sourced purchases carry 62,062 tCO2-e on $442.5M of spend,
4.3% of Scope 3, and grinding media alone is 45,900 tCO2-e of that on $358.6M.

Retyping the EPA number would have been the wrong answer.  A regulated factor
that a user can edit is not auditable, and a figure changed in place loses
the argument for changing it.

An override is a separate record instead.  It names the factor it replaces,
carries its own figure, unit, year and source, and requires a reason, which
is the disclosure.  The published factor stays in the table, unedited and
visible, and is carried beside the figure that superseded it, so an assessor
sees both numbers and the reasoning between them.

`Scope3/FactorOverrides.csv` holds the register.  Overrides are applied where
the factor table is read, so every category picks them up and none of them
has to know it happened.  Category, basis and key are copied from the factor
being replaced rather than typed, because they decide which activity the
override prices.  Retiring an override restores the published factor;
correcting one is entering another, so the history stays readable.

An **Overrides** tab on the Factors page adds them, maintains them and shows
what each one is doing.  Every change is written to the change history, and
entering one rebuilds the inventory, so it appears on the Changes page like
any other edit and is published the same way.

Tested end to end against grinding media: the Category 1 factor moved from
0.349 to 0.65 kg per USD, grinding media from 45,900 to 83,241 tCO2-e, and
Scope 3 from 1,442,231 to 1,480,202 tCO2-e, with all 159 reconciliation
checks still passing.  The test override was then removed.

### Fixed - the credits page could not open

`StreamlitAPIException: the configured column type date for column Date is
not compatible for editing the underlying data type STRING`.  The credit
ledger is read from a csv, so its dates arrive as text, and a date column a
person is meant to edit has to be a date.

Dates are parsed on the way in and written back as plain dates, so the file
stays readable by anything.  The numeric and text columns are settled the
same way, so a blank in the ledger cannot decide a column's type.

---

## 2026-09-03d

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.  No total moves.  Mining reports under
one name instead of two, so a figure read off a department grouping changes
even though the emissions behind it do not.

### Fixed - a blank published as a blank came back as a null

The Inventory page raised `TypeError: '<' not supported between instances of
'float' and 'str'` on the department filter.  The published table writes a
blank where a row has nothing to say - a physical row carries no scope, a
transaction carries no cost centre - and `read_csv` turns an empty field into
a null.  Sorting the filter choices then compared a null against the strings
beside it.

Nine text columns were affected, 4,007 rows of them on the scope column
alone.  A blank now reads back as a blank, which is also what it means: the
table said "nothing to say", not "not asked".

The filter choices are built by one helper on every page, which drops blanks
and sorts as text, so a null arriving from anywhere cannot take a page down
again.

### Changed - one name per department

A grouping by department was reporting the mining operation twice, as `Mining
Open Pit` with 1,777,069 tCO2-e and as `Mining` with 10, because the chart of
accounts writes it both ways.  Processing had the same problem with a code
prefixed variant.  Neither total was the operation's.

`Config.py` now holds the department vocabulary beside the factor vocabulary,
and it is applied once, where the monthly aggregate is finished, so every
consumer groups the same way.  Mining reports 1,777,080 tCO2-e on one row.
Matching against the chart of accounts still accepts every spelling; only what
is reported is settled.

The Scope 3 factor builder had its own copy of this map, pointing the other
way, so the two halves of the model could have settled on different names for
the same department.  It now imports the one in Config.

### Fixed - a missing label was reported as the word "nan"

A part that cast a null column to text before the schema was settled left the
literal string `nan` behind, which grouped as a department of its own carrying
one tonne.  A missing label is now blank.

---

## 2026-09-03c

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.  No figure changes.  Publishing is now
a deliberate act behind a confirmation rather than a button on a page.

### Changed - published by default, preview on request, publish on confirmation

Every screen was rebuilding the whole inventory before it drew anything.  A
twenty seven year projection over 461,252 lines takes about thirty five
seconds, and the application was paying it to answer questions the published
file already holds.

The Builder now opens on the published build, which is a file read.  Three
controls in the sidebar:

**Preview changes** rebuilds from the current assumptions, capital items and
factors and shows that instead.  Nothing is written.  The sidebar says plainly
that what is on screen is not published.

**Back to published** returns to the record.

**Publish** is offered only against a preview that reconciled, and asks before
it writes.  There is no way to publish a build nobody has looked at, and an
edit made after a preview withdraws the permission that preview granted.

The **Preview and publish** page is now **Changes**, and it only reports:
published against preview by scope and basis, then year by year with a total,
then the largest moves, the Scope 3 categories and the outstanding items.  A
total that has not moved can still hide two years that moved against each
other, which is exactly what the category 6 and 7 relabelling did, so the year
table is not optional.

Three screens genuinely need the engine rather than the published file: the
Scope 3 category positions, the reconciliation, and the list of activity that
resolved to no factor.  Each says so and points at Preview rather than
reporting nil.

### Changed - the table is read as categories, and published columnar as well

The published table held 484 MB of Python strings for 297,839 rows.  Every
text column on it is a label from a short list; the widest holds 186 distinct
values.  Read as categories the same table costs 34 MB and a grouping becomes
an integer operation - the year and scope grouping went from 20 milliseconds
to under one.  The built table gets the same treatment, after the parts are
concatenated rather than before, because concatenating categoricals with
different categories gives objects back.

Publishing now writes `EmissionsTable.parquet` beside `EmissionsTable.csv.gz`.
The gzipped csv is still the distributed artefact, because anything can open
it; the parquet is what the application reads, because opening the csv costs
six seconds every time and the application opens it constantly.  Both are
written together and archived together, so the two cannot drift.  A build
published before the parquet existed writes one on first read.

---

## 2026-09-03b

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.  No total moves.  Explosives change
status from estimated to calculated and carry a factor where they carried a
blank, and one factor is now shown as having no publication rather than as
belonging to the Company.

### Changed - a publication and a derivation are two different facts

Asking one question of a factor lost the answer to the other.  The capital
spend bands read as `Company`, which said who may edit them and threw away
where they came from: they are the US EPA supply chain factors, converted to
Australian dollars and banded into asset classes.  An assessor asking for the
provenance of a generator factor was being told the company made it up.

Every factor now carries two columns.  The publication is where the number
came from and survives a conversion.  The derivation is what was done to it
here - `Published` where the figure stands as its publisher issued it,
`Derived` where somebody converted, banded or calibrated it, `Unattributed`
where no publication was named at all.

A factor is fixed only when both hold: published by a relied upon body and
used as published.  Anything derived from one of those publications is this
company's own arithmetic and stays editable, because the judgement is in the
derivation.  The capital bands now read `EPA SCEF`, `Derived`, editable.

### Fixed - explosives were reported as an estimate against no factor

Explosive quantities are weighed in tonnes and priced by a published factor,
0.17 t CO2 per tonne of ANFO from the Australian Greenhouse Office 2004
Table 11.  The table was carrying that as a source of `Config, GHG only`, a
blank factor and a status of estimated, which reads as a figure nobody can
trace.

The source now names the publication, the factor is carried as 170 kg CO2-e
per tonne, and the row multiplies out on the face of the table: 88,955 t of
explosive at 0.17 gives the 15,122 tCO2-e reported.  The status rule follows
the derivation rather than the regulator, so a published factor on metered
activity is calculated whoever published it.  Explosives remain outside NGER
and the Safeguard Mechanism, which is a separate fact carried by the
applicability flags.

### Fixed - a filter reset itself when the page reran

Clearing `Forecast` from the basis filter rebuilt the page and brought
`Forecast` back.  The filter widgets carried a default and no key, so any
rerun the page did not itself ask for - a cache clear, a rebuild - recreated
them from their defaults and discarded the selection.

Every filter now carries a key, which is what makes a choice survive a rerun.
The filters also moved to the sidebar: they are read against the result, and a
control that scrolls away with the page is a control the reader has to go
looking for.

### Changed - an exclusion is not a factor with a missing number

Twelve rows in the factor table are exclusions: a product group deliberately
not priced in a category.  Shown in a factor grid they read as nine factors
with no publication and three more with no figure, which makes the register
look full of gaps it does not have.

They now have their own tab, with the reason and the place each is counted
instead.  Diesel and petrol, lubricants and propane are the ones worth
reading: they are burnt rather than consumed as a purchased good, so the
combustion is Scope 1 and the upstream well to tank share is Category 3 on
the National Greenhouse Account factors named beside them.  Nothing there is
missing from the inventory.

### Added - a factor with no publication is shown as a gap

With the exclusions moved aside, one priced factor names no publication: the
Brisbane to Townsville air sector at 0.155 kg CO2-e per passenger kilometre,
attributed to "recognised aviation factor, domestic short haul, economy".
That is a description, not a source.  It prices 492 tCO2-e across the plan.

The Factors page counts these separately, warns while any remain and offers
them in their own editable tab.  The National Greenhouse Accounts publish
aviation fuel factors but no passenger kilometre factor, so this one has to
be sourced elsewhere and the page says so.

---

## 2026-09-03

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.  Two defects in this block understated
what the Builder could report, and both were introduced after the 30 July 2026
release.  No figure issued from a released build is affected.

### Added - one publication per factor, and only a company factor can be edited

A factor is either published by somebody else or chosen here, and the two are
not maintained the same way.  The National Greenhouse Account factors and the
US EPA supply chain factors are regulated inputs: they are what the publication
says, and a model that lets a user retype one has stopped being auditable.  A
refining factor, a physical factor for steel or a capital spend band is a
judgement this company made, and a judgement belongs to the person who has to
defend it.

`Config.py` now holds the vocabulary.  Every factor source resolves to one
publication - `NgaFactors`, `EPA SCEF`, `EPA SCEF Margins`, `AusLCI`, `AGO` or
`Company` - and to a regulated flag taken from that publication rather than
from the file a factor happened to arrive in.  The canonical table carries
both, so a view filters on the publication instead of matching text.

The source names were tidied at the same time.  One publication had four
spellings - `NgaFactors.csv`, `National Greenhouse Account Factors`, `NGA
Factors` and `NGA -` - which read as four sources.  `.csv` is gone from every
name, because the file a factor was distributed in is not part of its identity.
The scope is gone too: a source read `National Greenhouse Account Factors,
Scope 3` beside a `GHG Scope` column already saying Scope 3.

A **Factors** page in the Builder shows the lot.  Company and AusLCI factors
are editable, with the category, basis and key held fixed because they decide
which activity the factor prices; every change is written to the change
history.  Regulated factors and the National Greenhouse Account table are
shown as published and cannot be edited.

The **Inventory** page gained a factor set and a factor source filter, so the
question "which rows did the EPA factors price" is a control rather than a
download and a spreadsheet.

### Added - a Scope 1 and 2 page

The Scope 3 page asks of every category whether it carries a position.  The
same question is worth asking of combustion and electricity, where the failure
is quieter: an activity that never resolved to a factor produces nothing and
reads as nil rather than as missing.

The page lists every Scope 1 and Scope 2 source with its quantity, its factor,
the publication behind it, recorded and forecast tonnes side by side and a
share of the total.  It also lists activity that names a fuel and produced no
emission at all, which is the gap a total cannot show.  Nothing is outstanding
on the current build.

The framework panel states the three coverages against each other: 4,059,556
tCO2-e reported, 4,044,433 covered by NGER, 1,805,503 covered by the Safeguard
Mechanism.  The differences are explosives and Scope 2, and reading them side
by side is the point.

### Fixed - NGER and Safeguard applicability was false on every row

`NGERApplicable` and `SafeguardApplicable` were tested by matching the factor
source against the literal string `NgaFactors.csv`.  The canonicalisation added
a few lines earlier in the same function had already rewritten that source to
`NgaFactors`, so the test never matched, every row fell out of both schemes and
the framework filter returned nothing.

Both flags are now tested on the publication rather than on a file name.
Covered Scope 1 is 1,805,503 tCO2-e, which is total Scope 1 of 1,820,625 less
the 15,122 tCO2-e of explosives that sit outside both schemes, and NGER at
4,044,433 tCO2-e is that figure plus Scope 2.

### Fixed - modelled categories were labelled forecast in months already recorded

Categories 6 and 7 are modelled across the whole plan rather than taken from
transactions, so they arrive on neither the actual nor the budget dataset.
Anything that was not the actual dataset was labelled a forecast, which put
5,346 tCO2-e of business travel and employee commuting in months between
January 2022 and July 2026 on the forecast side of the split.

A modelled line falling in a month that has already happened belongs to the
record: it is an estimate of what occurred, not a projection of what will.
The label now follows the date against the end of the recorded period, taken
from the data rather than from a constant.  Recorded Scope 3 rises from 249,238
to 254,584 tCO2-e and forecast Scope 3 falls by the same amount.  No total
moves.

### Changed - the inventory reads in calendar years, most recent first

Three things about the row list were wrong at once.  It showed the first two
thousand rows of an unordered table, so a filter on 2026 and 2027 appeared to
hold nothing after February 2026 while the record runs to July.  It carried a
calendar year and a financial year column beside a date that already said both.
And it offered a year basis selector, as though the table held two versions of
the same figure.

Rows are now ordered most recent first and the list says how many of how many
it is showing.  The date is a date and carries no time.  The year columns are
gone from the view.  The table holds calendar years, because a financial year
is the same date read against a July boundary and that is a way of grouping
rather than a second version of the data.  Years are typed into a from and a
to box instead of dragged on a slider.

### Fixed - the capital register page could not open

An over wide rename had left two calls to `LoaderLoaderCapital`, so opening the
capital goods register raised a `NameError` before it drew anything.

### Changed - a source with no factor of its own carries none

Explosives are priced in `Config.py` rather than by the National Greenhouse
Account factors, and the table was recording that as a factor of zero.  Zero
reads as priced at nil, which is a different claim from priced elsewhere.  The
factor and its unit are now blank on any source the Accounts do not reach.  The
emission is unchanged.

---

## 2026-09-02

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.  Every change in this block, the greases unit fix included, sits after the 30 July 2026 release and no figure issued from a released build is affected.

### Changed - the GHG dashboard is drawn over the life of mine

The headline chart now plots a year at a time across the whole plan rather
than a month at a time across one reporting period.  The plan runs to 2049,
so the year is the readable grain: a month level view of twenty seven years
is a picket fence.

Behind the bars the plan phases are shaded and the four milestones are marked
on the axis - grid connection, end of mining, end of processing, end of
rehabilitation - all read from `Data/LOM.yaml`, so the chart cannot drift from
the plan the rest of the model uses.  A forecast year is drawn paler than a
recorded one.

Two views are added.  Emissions by lifecycle phase collects the same figures
into the phases of the plan, stacked by scope.  Life of mine total states the
whole plan as one figure and one stacked bar.  The plan total is kept off the
phase axis, because a total several times the largest phase flattens every
phase it is meant to be read against.

Intensity over the life of mine replaces the two monthly sparklines.  It plots
both measures by year across the plan, each on its own axis: tonnes per ounce
and kilograms per tonne of ore are three orders of magnitude apart, so one
axis would flatten one of them.  The plan phases are shaded behind the lines
on the same footing as the emissions chart, so a turn in the intensity can be
read against the phase it happens in.

The ore series stops at the last full year of mining.  Mining winds down over
its closing year, so a full year of emissions is divided by part of a year of
ore: on the current plan CY2037 mines 0.9 Mt against 8.7 Mt the year before
and returns 268 kg per tonne, which is a reading of the wind down and not of
performance.  Processing does not have the same problem, because gold keeps
being poured from stockpile to the end, so the gold series runs to the end of
processing, CY2039, which is where the plan itself ends.  Both axes rescale
accordingly and the two measures can be read against each other for the first
time.

Emissions by lifecycle phase is a stacked bar per phase.  Mining is nine
tenths of the plan, so any chart that draws the phases against each other on
one scale leaves Processing and Rehabilitation as slivers that cannot be read.
Each phase gets the full width instead, and the bar carries the scope mix
within that phase, which is legible whether the phase is nine tenths of the
plan or one hundredth.  Magnitude is carried by the tonnes and the share
beside it, and the life of mine sits on the same footing at the foot.

Where the record stops and the forecast begins is now a labelled divider on
the year chart rather than a fade on the forecast bars.  A bar drawn paler for
no stated reason reads as a rendering fault.

Every bar, arc and point carries the figures behind it on hover.  A native SVG
title only appears after the pointer has been still for about a second, which
reads as no tooltip at all, so the panel draws its own from `data-tip`
attributes.  The script is a dozen lines at the foot of the page and fetches
nothing.  Each bar and each year of the intensity chart has an invisible hit
column over its whole slot, so the pointer finds the reading without having to
land on a four pixel dot.

There are three phases: Mining, Processing, Rehabilitation.  Grid connection
is a milestone within mining rather than a phase of its own, so it is marked
on the axis and no longer splits the phase in two.  `get_phase_name` keeps its
grid argument so existing call sites read unchanged; the Lifecycle tab, which
is about that transition, still draws its own band at the connection date.

A department or a year carrying nothing is left off the charts rather than
drawn as an empty slot.  The heading and the coverage line above the dashboard
were repeated inside it and have been removed from above.  The headline
figures, the department bars and the department labels are larger.  Cards and
bars carry a wider corner radius and a soft shadow, so the panel reads as
layered rather than flat.

The page is laid out in two rows under the headline chart: department and cost
centre at half the width with lifecycle and scope at a quarter each, then
intensity and the top sources at half each.

The charts that used to sit below the dashboard are removed: the emissions
summary, the life of mine projection, the breakdown pareto charts, the
department sunburst and the intensity chart.  The dashboard answers the same
questions in one place and in one visual language, and a second answer in a
second style is a second thing to keep right.  The tables stay.  Tab1Ghg no
longer imports plotly.

Streamlit deprecates `st.components.v1.html` in favour of `st.iframe`, which
takes a URL rather than markup and so is not a replacement for a page rendered
in place.  The panel keeps the deprecated call until a replacement that
renders markup in a frame exists.  The frame is not optional: the panel
carries its own stylesheet with element selectors, which would reach the whole
application if it were rendered inline.

### Changed - the method documents are written to be audited

The About tab reads prepared markdown from `Documentation/` at run time and
renders it in place; nothing is generated.  That was already the case.  What
changed is the depth of what it reads.

The five method documents are rewritten so an assessor can reproduce any
figure on any view from the source files without reading code.  Each now
carries the boundary, the data lineage column by column, every formula with
its symbols defined, every constant with the authority it comes from, every
unit conversion, a worked reconciliation against real figures, the stated
limitations and a map of which file holds which concern.

- **GHG emissions method** carries the full NGA 2025 factor table, the unit
  table, the matching rules and a CY2025 reconciliation that arrives at the
  reported tonnes from the recorded quantities.
- **Safeguard Mechanism method** carries the Section 11 formula, the ERC
  decline in both phases, the hybrid transition schedule, the s10(1) floor
  against the s56(4) unfloored baseline, the four SMC phases, the s58B test
  and a worked FY2025 example.
- **Scope 3 method** is now the detailed technical paper the Scope 3
  executive summary refers to.  It carries the AASB S2 requirements, the
  boundary and why operational control, the GHG Protocol method selection and
  why supplier data was not collected, the manufacturing origin test, the
  provenance classes, the uncertainty simulation, all fifteen categories with
  their formulas, the results for the period tested and the position against
  the sector.  The Scope 3 factor sources are folded in, so the factors sit
  with the method that uses them rather than in a separate document.
- **GRI 14 method** carries every disclosure with its GRI reference, its unit
  and its source, and states which topics the model does not produce.
- **NGER and NGA factors** keeps to Scope 1 and Scope 2: the file, the
  matching rules, year resolution, unit reconciliation and the audit table.

### Added - Emissions Data Builder, and a published inventory

PrepData prepares operational data every consumer needs.  Deciding which
factor applies to a purchase, what counts as a capital good, and when a figure
becomes the reported one are questions only this program asks, so they move
here.  Nine registers, the Scope 3 configuration and the factor builder now
live in `Scope3/` under Emissions.  PrepData no longer distributes them and no
longer needs to: nothing else consumed them.

**One published file.**  `CalcEmissionsTable.py` projects what the engines
already computed into one canonical monthly table: every scope, every Scope 3
category, and the physical measures the intensities are read against, each row
carrying the quantity, the factor, the factor source and which frameworks it
counts towards.  It calculates nothing.  `ExportEmissionsTable.py` publishes
it as a single gzipped file - 298,167 rows, 12.9 MB - with a build log, the
outstanding items and the assumptions in force, and archives a copy under the
build identifier so an earlier disclosure can be reproduced rather than
argued about.

The build identifier is derived from the inputs rather than from the clock, so
the same inputs give the same identifier and a rebuild can be shown to be a
rebuild.  Rebuilding with nothing changed moves no figure by any amount.

**Reconciliation is the gate.**  The table is a projection, so a difference
between it and the engine that produced a figure is a fault in the projection.
159 year and scope checks run on both the calendar and the financial basis,
and publication is blocked while any of them fails.  All 159 reconcile.

**The Builder** is a separate application, not a reporting tab, launched
beside the reporting one:

    streamlit run AppBuilder.py --server.port 8502

It carries seven sections: build status with the reconciliation result and the
input fingerprints; the inventory, filterable by basis, scope, department,
category and framework, in monthly buckets with the physical measures beside
them; Scope 3 with an explicit position for every one of the fifteen
categories; assumption editing that writes to the configuration file rather
than to a Python constant; the capital goods register; the credit ledger; and
preview against the published build before publishing.

**Capital goods** get an emissions-owned register.  An item is entered once
and keeps one identifier through two states: expected, with an expected date
and value, contributing to the forecast; and commissioned, with the date and
value that actually applied, contributing to the record and superseding its
own forecast.  It is never both.  A rental is an expensed service and is
recorded as not counting rather than left out, and an item without a
commissioning date is reported as outstanding - no date is invented to make it
countable.  Seeded from the review register: 30 items, 22 rentals, 8
outstanding for want of a date.

**Credits** are recorded here too.  Issuance, surrender, sale, purchase and
correction, with anything leaving the holding stored negative so the running
sum is the holding the registry should agree with.

**All fifteen Scope 3 categories carry a position** - Calculated, Estimated,
Outstanding, Excluded or Not applicable.  On the current data: four
calculated, two estimated, two outstanding, two excluded and five not
applicable.  Missing data is surfaced, never reported as nil.

The reporting application is unchanged and keeps working whether or not the
Builder is running.  It shows the published build identifier in the footer.

### Changed - a source is named for what it is, not for where it discloses

Explosives were carried under the pseudo fuel name `Explosives (GHG only)`.
That put a disclosure question inside an identity field: the name said where
the source reports rather than what it is.

The source is now named `Explosives`.  Where it discloses is carried where it
belongs - by `GHG_Source` on the frame and by the applicability flags on the
canonical table, which for explosives are false for NGER and for the Safeguard
Mechanism and true for GRI.  A view that needs covered emissions filters on
the flag rather than reading a name.

No figure changes.  Covered Scope 1 remains 1,805,503 tCO2-e and total Scope 1
1,820,625.

The unmatched-factor warning was also making noise for something deliberate.
A source that resolves to no NGA factor and already carries an emission has
been priced by something holding a factor the Accounts do not publish; that is
by design and no longer warns.  A source carrying nothing is a real gap and
still says so, in words that name the fix.

### Fixed - saving an assumption emptied the configuration file

Saving one assumption through the Builder left `Scope3Inputs.yaml` at zero
bytes and every other assumption gone from the screen.  Three faults, all in
the same six lines, and the first one is the serious one.

**The file was truncated before there was anything to write.**  Opening a file
for writing empties it, so a failure between the open and the write leaves
nothing at all.  The failure came from the second fault: a number out of a
data editor is a numpy scalar, which the YAML dumper will not serialise.  So
the file was emptied, the dump raised, and nothing was written back.

**The third fault would have destroyed the file's value even on success.**
Serialising a parsed document over the file drops every comment in it, and
`Scope3Inputs.yaml` carries a hundred and eighty one comment lines explaining
why each assumption is what it is.  Those comments are the greater part of the
file: a factor a reader cannot trace is a factor they cannot check.

`ConfigEdit.py` replaces the whole approach.  It does not serialise.  It finds
the line carrying the value and rewrites that line, so everything else is byte
for byte what it was.  The new text is written beside the file and moved over
it, so the file is either the old one or the new one and never empty.  Values
are coerced to plain python before they go anywhere near it.  A value that
cannot be located raises, and nothing at all is written: a partly edited
configuration is worse than an unedited one, because it is harder to notice.

`CalcScope3Status.save_config` now raises rather than existing as a trap.

Verified on a copy: two values written, four lines changed, 181 comments and
all eight categories intact, and the change recorded.

### Added - change history

Every edit made through the Builder is recorded: the path, the value before
and after, who made it and when.  Assumptions, the capital register and the
credit ledger all write to `Scope3/ChangeHistory.csv`, and a History page
shows it with a file filter, a search and a download.  A published figure that
moved should be explainable, and this is where the explanation lives.

### Changed - one way to maintain a register

Assumptions, capital goods and credits were each maintained differently: some
had an entry form above a grid, some only a grid.  All three are now the same
- edit the grid, save, and the change is recorded.  A person who learns one
screen has learned all of them.

### Changed - a capital factor follows from the asset class

The register asked for a factor.  Nobody entering a capital item knows its
emission factor and nobody should be asked to.  The asset class is now chosen
from the seventeen the configuration maps, and the factor class and the factor
are derived from it and shown read only.  The register cannot carry a factor
that disagrees with the class beside it.

Tenure is stated at the point of entry rather than left to a one word label.
An acquisition, owned or under a finance lease, produces a Category 2 event
because the Company takes the asset.  A rental does not: it is a service
bought over time, its emissions are the supplier's, and they reach the Company
through Category 1 in the periods it is used.

### Changed - the inventory filters by year

The inventory page filters on a year range, on either the calendar or the
financial basis, alongside the existing basis, scope, department, category and
framework filters.  Figures throughout carry thousands separators, and the
annual table carries a total column.

### Fixed - string operations that assumed one pandas backend

Two faults of the same kind, found on a newer pandas than the one they were
written against.  Recent pandas stores text with an Arrow backend rather than
as python objects, and numpy's character functions have no loop for it.

`CalcEmissionsTable` classified the Scope 3 provenance with `np.char.find`
over a column of bases.  It now tests with `Series.str.contains`, which stays
inside pandas and works whatever backend is in use.  Two `np.where` calls
choosing between string columns moved to `Series.where` for the same reason.

`ExportEmissionsTable` computed the percentage change in the preview by
replacing zero denominators with a null before dividing, which turns a float
column to object and takes the division with it.  It now divides only where
there is something to divide by.

The lesson generalises and is worth stating: a frame arrives with whichever
string and numeric backend the installed pandas chose, so anything reaching
around pandas into numpy to work on its columns is a guess about somebody
else's installation.

### Fixed - float32 columns and a float64 result

Introduced and corrected in the same day's work.  The loader stores the
emission and energy columns as float32 to save memory across four hundred and
sixty thousand rows.  `apply_emissions_to_df` used to assign each column
whole, which replaced it with a fresh float64 column as a side effect.  Once
the reset was narrowed so a GHG-only emission would survive recalculation,
the column survived too, and the float64 results had nowhere to go: pandas
declines to write a float64 array into a float32 column rather than silently
losing precision, which is correct and has to be respected rather than worked
around.

The widening is now explicit, in `apply_emissions_to_df` and in `CalcGhg`
where the explosives overlay is written.  `CalcGhg` did not fail, because the
promotion rules of the installed numpy happened to keep that product float32;
depending on which version is installed is not a basis for arithmetic, so it
widens too.

### Fixed - explosives vanished from every forecast year

`apply_emissions_to_df` reset all four emission columns on entry, then
calculated the rows carrying an NGA factor.  Explosives carry the fuel name
`Explosives (GHG only)`, which deliberately resolves to no NGA factor because
there is none, and their Scope 1 is set by `CalcGhg` from a factor the NGA
does not publish.

The reset destroyed that value whenever the frame was recalculated, which the
projection does for every budget row.  The effect was that explosives counted
in recorded years and silently vanished from every forecast year.

Only the rows the function will actually compute are reset now.  **Scope 1
over the life of mine rises from 1,805,503 to 1,820,625 tCO2-e**, the
difference being 15,122 tonnes of forecast explosives that were being dropped.
Recorded years are unaffected; every figure for a year to 31 July 2026 is
unchanged.  The Safeguard position is unaffected in both: explosives carry no
NGA factor, are outside NGER and the Safeguard Mechanism, and covered
emissions remain 1,805,503 tonnes.

### Fixed - Scope 3 was understated in the GRI export

The GRI Scope 3 disclosure read the `Scope3` column, which is Category 3 on
its own, and published it as gross Scope 3.  On CY2025 it reported **47,231
tCO2-e against a true 59,608, an understatement of 26%**.  The disclosure now
reads `Scope3_Total`, being Category 3 plus the other fourteen categories, and
falls back to the narrower column only where the Scope 3 build did not run, so
a partial figure is never published as a gross one.

The export also read the Safeguard annual frame, which carries no Scope 3
columns beyond Category 3.  It now reads the GHG frame, which carries the same
Scope 1 and Scope 2 figures plus the full Scope 3 set.

Every Scope 3 category is now published as its own disclosure line, with a
count of how many of the fifteen carry a figure.  The disclosure requires the
categories included in the measure to be stated, and a total alone does not
state them.  The category lines reconcile to the total exactly.

### Changed - GRI references, waste and the Safeguard provisions

**GRI references.**  Fourteen consumable lines carried `14.1-consumables`,
`14.5-waste` or `14.3-emissions`, none of which is a GRI reference.  GRI 14
numbers its disclosures `14.x.y`, and reagent consumption has no GRI 14
requirement behind it at all: it is voluntary content under GRI 301-1.  All
fourteen now carry `301-1a`.  The single-site Scope 1 and Scope 2 lines carry
the disclosure they belong to with a site marker, the intensity denominator
moved from the withdrawn `302-3b` to `102-8b`, and strip ratio is marked as
the sector recommendation it is.

**Waste.**  Rock waste and tailings were reported as Limited and outside the
total, on the basis that on-site process residue retained under environmental
authority EPML00979013 is not waste transferred for treatment.  That basis
does not survive the standard: GRI 306 defines waste as anything the holder
discards, intends to discard or is required to discard, names tailings as a
sector-relevant stream, and nothing permits either to be left out of the
total.  Both are now inside a total waste generated figure as the composition
breakdown 306-3 asks for, and marked Full, because both are measured
quantities from the monthly operating report.  The retention point belongs in
the contextual disclosure 306-3(b) requires, not in an omission.

**Biogenic carbon dioxide** is published as an explicit nil rather than left
out.  The facility has no material biogenic source, but the disclosure
requires the nil to be stated.

**Safeguard.**  `calculate_annual_baseline` now carries the borrowing
adjustment as an explicit argument, defaulting to zero, so the code matches
the provision it implements rather than omitting a term of it.  Section 10(3)
is applied: the baseline is zero for a financial year beginning after 30 June
2049, which makes FY2050 the first qualifying year, not FY2051, and the model
horizon reaches it.  The function documents that it computes the Q branch of
section 11 alone, and why that is right here: the facility holds an emissions
intensity determination for both production variables, so the quantity outside
a determination is zero and the best practice branch does not arise.

**Category 10.**  The dore composition is recorded in `Scope3Inputs.yaml`
beside the null factor: approximately 95 per cent gold and 5 per cent silver,
no copper, refined by Miller chlorination and Wohlwill or by aqua regia.  A
published intensity is only usable here if it states both the dore grade and
the refining route, because a base metal bearing dore refines electrolytically
at a materially higher intensity.  Recording the requirement beside the gap
means whoever supplies the number knows what it has to be.

### Fixed - the method documents reviewed against the standards

The five documents were checked line by line against AASB S2, the GHG Protocol
Corporate and Scope 3 Standards, GRI 14 Mining Sector 2024 and the Safeguard
Mechanism Rule 2015.  Errors of fact were corrected and gaps were written up
rather than left implicit.  Nothing in the calculations changed; every finding
is a documentation finding.

**Safeguard.**  The Section 11 formula as documented was the reduction that
applies to this facility, not the provision.  The full formula is now stated,
with the best practice branch and the borrowing adjustment term, and the
reason each is nil here: the facility holds an emissions intensity
determination for both production variables, so the quantity outside a
determination is zero and the best practice branch does not arise.  The
Phase 2 decline rate was described as indicative and not legislated; it is a
legislated default under s31, being the previous year's value less 0.03285,
and the entry now says so while keeping the caveat that the trajectory is
subject to the 2026-27 review.  The s56(4) quotation said "as if" where the
provision says "if".  Section 58B was presented as a single test; it provides
three pathways and the model implements one, which makes the modelled exit
date the earliest possible rather than the actual one.  The production
variable is named as the Rule names it, run-of-mine metal ore.  Section 10(3)
zeroes the baseline for years beginning after 30 June 2049, which the model
does not implement and which affects its last modelled year.

**Scope 3.**  "Gold is recycled indefinitely" was given as a ground for
excluding Category 12.  It is not one: recycling is expressly an end-of-life
treatment inside that category, and the conformant treatment is to report the
category with a small factor rather than declare it inapplicable.  Categories
11 and 12 are now reported as nil and de minimis with their reasons, not
excluded.  The category names are the standard's own.  The completeness
requirement, the minimum boundaries of Table 5.4, the seven relevance criteria
and the five data quality indicators are now stated, along with a base year
and a recalculation policy, which the GHG Protocol requires and the document
did not carry.  The 5% threshold is marked as a Company convention rather than
a standard requirement, which is what it is.  AASB S2 paragraph references are
given throughout, the AR5 global warming potential basis is stated with its
jurisdictional relief, and the ASSA 5010 assurance phase-in is set out, since
Scope 3 carries limited assurance from the second reporting year and
reasonable assurance from the fourth.

Category 10 is restated as the most material open item in the method rather
than one of nine.  Dore is an intermediate product and third-party refining is
squarely inside the category; the sector reports it at 43% of Scope 3, so the
current nil is a gap of potentially material size and the 28% share of total
emissions should be read as an understatement until it is closed.

**GRI 14.**  The document carried topic 14.1 as "Climate change", which is the
January 2026 aligned version, alongside 305-x disclosure references, which are
the 2024 version.  The two are now separated, the model is stated to produce
the 2024 set, and the remapping to GRI 102 and GRI 103 needed before FY2027
reporting is recorded.  References of the form `14.1-consumables` are not GRI
references and are marked as a defect to correct in `ExportGri14.py`; reagent
and consumable reporting is voluntary content with no GRI 14 requirement
behind it, and belongs against GRI 301-1 if it is referenced at all.  A gap
register now lists every requirement the model does not produce, ranked, from
the missing 305-3(d) category list and the unset base year through to topic
14.6, the tailings facility register, which is outside the model entirely.
The position that waste rock and tailings sit outside 306-3 is marked as a
Company position rather than a fact, because GRI 14 recommends their inclusion
as composition breakdowns and nothing reviewed permits their exclusion.

**GHG emissions and NGER factors.**  The global warming potential basis is
named as AR5 with the jurisdictional relief that permits it.  Biogenic carbon
dioxide is addressed, nil at this facility but required to be stated.  The
consolidation approach carries the Protocol's own wording, and the reporting
entity is distinguished from the organisational boundary.

### Fixed - precompute at projection scale

A forecast re-run took the budget file from 79,985 rows to 449,198, and the
load and precompute went with it.  Four calculations were written as a call
per row, which is affordable at eighty thousand rows and is not at four
hundred and fifty thousand:

- the financial year was derived one date at a time.  `CalcCalendar` now
  carries `series_to_fy`, which does it in one pass
- the monthly aggregation used a python function for the issue mass, which
  forces pandas out of its fast path.  The same rule is now expressed as a
  sum and a count
- the identifier lookup resolved a classification for every row.  The frame
  carries a few hundred distinct pairs however many rows it holds, so the
  classification is resolved once per pair and mapped back
- the supersession rule - a recorded month replaces the budget for the same
  line - tested every budget row against a set.  It is now index arithmetic

The supersession rule also existed in four places with four implementations.
There is now one, `CalcEmissions.dedupe_actual_over_budget`, and the
projection, the Scope 3 build, the dashboard and the data query all use it.

No figure changes.  Load falls from over thirty eight seconds to eight and a
half; precompute from over two minutes to nineteen seconds.

### Changed - Category 1 is assessed on expenditure, with physical factors where they are better

The method is settled and stated here so it is not rediscovered.  Expenditure
is the basis for Category 1.  Where a physical unit factor exists and is a
better basis for that commodity, it takes precedence, and the model uses it.

That is not a compromise for most of the register.  Of 8,113 items, 7,980
report in a count: Each, Box, Roll, Pair, Kit.  A count cannot be read against
a factor per tonne, and an item that touches no other scope needs no measure
beyond the dollars it cost.  Those are assessed on the EPA supply chain
factors and that is the end of it.

The exception is the handful of groups where the spend factor is demonstrably
wrong for the commodity.  For those the upstream register now carries a mass
per reporting unit and the physicals carry `Mass_kg`, so a count becomes a
measure and a factor per tonne can be applied.  The column arrives empty; the
values are a data exercise on the material groups only.

Recorded Category 1 expenditure splits:

| Rows priced on | Spend | tCO2-e |
|---|---:|---:|
| A count unit | $29,635,323 | 5,581 |
| A real unit | $24,152,994 | 14,436 |

Forty five per cent of assessable expenditure carries 28 per cent of the
Category 1 result on a count, and stays on dollars.

### Changed - Scope 3 inputs come from PrepData

This model held the Scope 3 factors and the assessment parameters itself.  It
now holds neither.  Both are produced by `PrepData/BuildScope3Factors.py` and
distributed with the physicals, requested by `Data/PrepData.txt` exactly as
`LOM.yaml` and `ReferenceFx.csv` are.

    Data/Scope3Factors.csv   399 factors with unit, dollar year, source and
                             NAICS class
    Data/Scope3Inputs.yaml   roster, travel pattern, waste streams, currency
                             basis, projection rule, exclusion register

Removed from this project: `Data/Scope3/`, `Data/ConfigScope3.yaml` and
`UtilityScope3ToCsv.py`.  The registers behind the factor table live in
`PrepData/Scope3/`; their content reaches this model inside the factor table,
so they are not read here.  Three registers are read at run time and are
distributed as written: the capital asset register, the capital project screen
and the supplier spend classification.

A missing input is reported and nothing is computed from it.  There is no
fallback value anywhere in this model, so a factor corrected upstream cannot
be stale here.

### Fixed - GRI consumables were reported in the wrong unit

A GRI disclosure declares a unit.  The consumables getter summed the quantity
as recorded and returned it under that label with no conversion, so cyanide
recorded in tonnes was published as kilograms: 4,763.57 became the figure
against a kilogram heading.  Caustic soda, hydrochloric acid, flocculant and
explosives carried the same error, all understating by a thousand.

`_sum_in_uom()` now carries each matched row to the unit the disclosure is
published in before adding it, using `CalcUnits`.  A row that cannot be
carried there is reported and excluded, which is how a count against a mass,
or a stores line that has taken the name of a mapped line, is kept out.

CY2025, corrected: cyanide 4,763,571 kg, caustic soda 799,695 kg,
hydrochloric acid 505,827 kg, flocculant 141,780 kg, explosives 5,286,000 kg.

Also fixed in the same pass: activated carbon matched on the common name
`Carbon` where the lookup sets `Activated carbon`, so the disclosure reported
a silent nil.  It now reads 234 t.  Tyres matched a lower case unit against
`Each` and returned nothing; `factor()` compares a count case insensitively.

### Changed - Metric units are written in the abbreviated form

kg not kilogram, t not Tonne, m not Meter, and L, kL, m3, g, km, kWh
likewise.  One spelling per unit across the pipeline and this model, so a
quantity always groups with the rest of its own line.  A count is not a metric
unit and keeps its own word: Each, Box, Roll, Pair, Kit, Set.

The upstream register is corrected accordingly, so 25 rows of
`OperationsMetricsActual.csv` move from `Meter` to `m` on the next run and
join the existing `m` lines.  `CalcUnits.canonical()` holds the same rule, so
a variant that reaches this model from any source is normalised on read
rather than becoming a second unit.

### Changed - CalcUnits.py, one definition of units for the model

Every unit conversion in the model now comes from one place.  Nothing else
divides by a thousand, multiplies by 31.1034768, or decides that a litre is a
thousandth of a kilolitre.

Each unit is declared once, as a dimension and a multiple of that dimension's
base unit, and a conversion is derived rather than listed:

    factor(a, b) = size of a / size of b

Two consequences.  A conversion and its inverse cannot disagree, because both
come from the same two numbers.  And a conversion between different dimensions
cannot be written down at all, so litres cannot become kilograms by a typo:
`factor('L', 'kg')` raises.

Spelling and arithmetic are kept apart.  `canonical()` collapses two ways of
writing one unit and changes no quantity.  `factor()` scales.  A count such as
Each, Kit or Roll is not a unit of measure and passes through both untouched.

Rewired to it: `CalcEmissions` for the reporting unit against the factor unit
and for kilograms to tonnes, `LoaderData` for spelling, `CalcScope3` for the
troy ounce and every kilogram to tonne, `CalcPrecompute` and `Projections` for
tonnes to megatonnes and kilowatt hours to megawatt hours, `Tab7Lifecycle` for
the troy ounce and tonnes to kilotonnes.  `Config.UOM_CONVERSIONS` and
`Config.UOM_SYNONYMS` remain as aliases so existing call sites read unchanged.

Currency is not a unit of measure and stays out: the capital goods factor is
per million dollars and that constant is named where it is used.

### Fixed - Explosives were charged in boxes as well as tonnes

The GHG overlay charged every row named Explosives at 0.17 tonnes of carbon
dioxide per tonne, whatever unit the row carried.  Stores issues rock rivets
by the box under a subactivity of the same name, so 15 boxes were charged as
15 tonnes: 2.6 tCO2-e added to Scope 1 on the GHG view.  Small, and wrong for
the same reason greases were wrong.

The overlay now reads the expected unit from the identifier lookup and charges
only rows carrying it, reporting the rest.

### Fixed - Two stores lines took the name of a mapped line

The activity level fallback added this release names a stores line by its
subactivity, and a stores subactivity can carry the name of a mapped line
while meaning something else in another unit.  `Stores/Explosives` is rock
rivets in boxes; `Stores/Lubricants` is tins, cans and drums.  Both collided
with the mapped line of the same name, so any consumer grouping on the common
name summed boxes with tonnes and tins with kilolitres.

A colliding fallback name is now qualified, `Explosives (stores)` and
`Lubricants (stores)`.

### Added - Every mapped line declares its reporting unit

`IDENTIFIER_LOOKUP` gains `UOM` on all 56 entries, so the unit is part of the
line's identity rather than an assumption in a comment at each point of use.
The loader reports any line whose unit is not the one its mapping declares.

Three pairs declare `None`, being the three the upstream pipeline flags as
deliberate: `Mining/Ore Waste` in BCM and tonnes, `Mining/Productivity` in BCM
and hours, `Milling/Productivity` in hours and a count.  No single unit
applies to those, so they must be summed within a unit or not at all.

### Added - GHG dashboard

The GHG view opens on a dashboard.  Six cards, a trend, a scope contribution,
the top sources, the departments, the largest cost centres and the two
intensity runs, then the existing detail below, closed.

**Drawn server side as SVG, with no script and no external request.**  A chart
library has to be fetched from a content delivery network at render time, and
a dashboard that goes blank because that network is unreachable is worse than
no dashboard.  The container this was built in cannot reach the network at
all, which is exactly the failure the approach avoids.  SVG scales with its
container, so nothing runs off the screen and a narrow window stacks rather
than clipping.

**Cards.**  Total, the three scopes and both intensities, each against the
same period a year earlier.  A fall in emissions reads as the good direction.

**Emissions over time.**  Monthly, stacked by scope, with the prior year total
as a dashed line, matched month position by month position.

**Scope contribution and sources.**  The three scopes against the total, and
a ring of the largest sources with the tail collapsed into one slice.

**By department and cost centre.**  The full width of the page: one row per
department carrying its scope split as a proportion bar, its total and its
share, expanding to its cost centres on the same bar scale, so a cost centre
reads against the department above it and against every other line.  It opens
and closes on native details and summary elements, so there is still no
script.  No table.

**Both themes.**  The frame does not inherit the app's theme, so the palette
is passed in and every colour on the page, the chart axes and grid lines
included, comes from the same two sets of variables.  A light panel inside a
dark app reads as a bug.

A row with no department is named Unallocated rather than left as the string
nan, which reads as a fault in the model.

Everything on the page covers the same months as the headline.  The breakdown
applies the same actual over budget rule as the projection, so a period that
is part recorded and part forecast is counted once and the parts add to the
total.  A movement against a prior period that barely existed is reported as
nothing rather than as a five figure percentage.

`CalcDashboard.py` holds every aggregation.  The view formats and draws and
derives nothing.


The GHG view opens on a dashboard rather than a summary table.  Four cards,
a trend, two intensity measures and a breakdown, in that order, so the page
answers how much, which way it is moving, how efficiently and where it comes
from before it offers any detail.

**Cards.**  Total, Scope 1, Scope 2 and Scope 3, each against the same period
a year earlier, with each scope's share of the total.  A fall in emissions
reads as the good direction; the sign is not flipped in the data to achieve
it.

**Emissions over time.**  Monthly, stacked by scope, with the prior year total
as a dashed line.  The prior year is matched month position by month position,
so July sits against July on a financial year, and the line is present in a
period the record does not otherwise reach.

**Intensity.**  Per ounce of gold sold and per tonne of run of mine ore, on
the whole inventory.  The headline is the period total over the period
denominator, not the mean of the monthly ratios: the two differ whenever
production varies and only the first is the intensity of the period.  A month
with no denominator carries no ratio rather than a spike.

**Breakdown.**  Department, largest first, each carrying its share of the
period and expanding to its cost centres with the scope split.  The Scope 3
categories other than 3 carry the department and cost centre of the line they
came from, so they sit inside the breakdown rather than beside it.

One colour per scope across every chart, bar and legend on the page.

`CalcDashboard.py` holds every aggregation.  The view formats and plots and
derives nothing, per the file conventions, and `CalcGhg.py` is untouched.

The existing detail is unchanged and moves below the dashboard, closed: the
summary table, the life of mine projection, the emissions breakdown, the
intensity charts, the fuel consumption detail, the data table and the Scope 3
panel.

### Changed - The sidebar carries filters, the tabs carry their own settings

The sidebar held the Safeguard constants, the credit market scenario and the
carbon tax scenario, none of which affect more than one view.  It now holds
what applies across the model: the reporting period and basis, the dataset,
and department and scope filters, with the options taken from the data so a
department that stops reporting leaves the list on its own.

The Safeguard constants and the credit market scenario move onto the
Safeguard view, beside the baseline and the credit position they govern.  The
carbon tax scenario moves onto the Carbon Tax view.

A department or scope filter narrows the GHG view only.  The Safeguard and
GRI views are facility wide and whole of period because that is what is
reported, and the sidebar says so rather than leaving a reader to wonder why a
filter did nothing.

### Changed - No Scope 3 tab

Scope 3 is one line of the inventory and is reported as one figure on the GHG
view.  Its composition, the method and factor source per category, the
expenditure reconciliation, the implied intensity check and the audit download
now sit under that figure in a closed panel.

### Changed - Three main views, and a document behind each

The tab set is now GHG Emissions, Safeguard Mechanism and GRI 14 Reporting as
the reporting views, with Carbon Tax, Data Query, Lifecycle and Scope 3 beside
them and About last.

`Tab4Nger`, the model reference and factor listing, is retired.  Its content is
`Documentation/NgerFactors.md`, read in the About tab: the factor file and how
it is built, which factor applies to which line and year, the diesel
classification rule, the reporting unit reconciliation and the explosives
position.

Five documents are registered in About and open in the reader:

| Document | Covers |
|---|---|
| `GhgEmissionsMethod.md` | Boundary, calculation, Scope 3 on the GHG view, intensity, life of mine |
| `SafeguardMechanismMethod.md` | Covered emissions, the Section 11 baseline, decline and transition schedules, threshold and s58B, credits |
| `Gri14Method.md` | What the model answers against GRI 14, basis of preparation, the coverage report |
| `Scope3Method.md` | All fifteen categories, factor hierarchy, currency, projection, expenditure reconciliation |
| `NgerFactors.md` | The National Greenhouse Account factor set and its application |

### Changed - The consumer adapts to PrepData, not the reverse

PrepData feeds several programs.  A change to a shared output to suit one
consumer moves the problem to the others, so this model absorbs the difference
on read and asks for nothing upstream.

Three places that principle now shows.

**Unit spellings.**  `UOM_SYNONYMS` in `Config.py` normalises a spelling
variant to the spelling this model works in, on read, in memory.  A synonym is
a spelling and never a conversion, so both sides are the same physical unit
and the quantity is untouched.  The current files carry `Meter` on 25 rows and
`kilogram` on one; both are normalised and the count is reported on load.

**Unit conversion.**  Where the reporting unit and the factor unit genuinely
differ, the quantity is converted at the point the factor is applied and
nowhere else.  `Quantity` is never rewritten and no source file is written to.

**Budget value.**  The forward projection prefers a value recorded on the
budget row and falls back to a rate fitted from the closed months of 2026.
The budget physicals carry no value today and this model does not ask for one;
the test costs nothing and means a value column appearing upstream is used the
day it arrives, in preference to a fitted rate.  A row's own product group
likewise beats the group the rate was fitted on.

Nothing in the current results changes: the recorded path is dormant because
the budget carries no value.

### Fixed - Scope 3 failed on a newer pandas

`pd.unique()` was called on a plain list.  Pandas 2.3 warns and a later version
raises, so the whole Scope 3 calculation failed with `TypeError: unique
requires a Series, Index, ExtensionArray, np.ndarray` and the tab reported
Scope 3 as absent.  The rate lookup now coerces to an Index first and takes
the column directly rather than copying it to a list.

The pipeline is run with `FutureWarning` and `DeprecationWarning` raised as
errors, so a deprecation cannot pass as a log line and fail later on a
different machine.

### Changed - Naming, value chain is the whole of Scope 3

The GHG Protocol standard is titled Corporate Value Chain (Scope 3), so value
chain names all fifteen categories and cannot also name the part that excludes
Category 3.  The split on the GHG view is now Scope 3 fuel and energy against
Scope 3 other categories, and the column is `Scope3_Other`.

The split exists because the two halves have different standing, Category 3
being the only part inside the NGER position, not because they are different
kinds of emission.

### Changed - Scope 3 charts as one band by default

The GHG chart carried Scope 3 as two stacked bands, which read as though
Scope 3 were smaller than it is.  It now charts as one band, with a control to
split it, and the summary carries each scope as a share of the total.

After grid connection the three scopes are close to an even split.  CY2029:
Scope 1 130,921 at 33 per cent, Scope 2 154,007 at 39 per cent, Scope 3
108,267 at 28 per cent, total 393,195 tCO2-e.

### Note - Safeguard and GRI 14 frames are untouched by the Scope 3 work

Confirmed by test rather than by intent.  `annual_fy` and `annual_cy`, which
the Safeguard and GRI 14 views read, carry none of the Scope 3 columns:
`Scope3_Other`, `Scope3_Total`, `Total_WithScope3` and `Scope3_Cat3` exist only
on `ghg_annual_fy` and `ghg_annual_cy`.  Their `Scope3` column is still
Category 3 and the baseline, the credit position and the source tables are
computed exactly as before.

Two changes in this block do move the numbers those views report, and neither
comes from Scope 3:

- the greases unit fix lowers Scope 1, which lowers covered emissions and
  therefore the credit position; and
- end of processing moving from 31 December 2045 to 31 December 2039 removes
  six years from the projection horizon.

Separately: the GRI 14 extract reports Scope 3 as Category 3 alone.  A GRI
305-3 disclosure needs all fifteen categories, so that extract is incomplete
on Scope 3 until the categories are carried into the GRI frame.  The method
document and the coverage position say so rather than leaving it implied.

### Changed - Scope 3 reaches the GHG view

`add_value_chain_to_annual()` puts the categories other than 3 onto the GHG
annual frames.  The GHG view now separates Scope 3 into fuel and energy
related activities, which is the Category 3 figure inside the NGER position,
and other categories, which is the rest, and totals on both.  The intensity
series take the inclusive total as their numerator.

The Safeguard and NGER frames are untouched.  Their `Scope3` column still means
Category 3, because that is what the baseline and the reported position are
built on.

CY2026: Scope 1 165,083, Scope 2 86,215, Scope 3 fuel and energy 52,516,
Scope 3 other categories 47,561, total 351,376 tCO2-e.

### Changed - The reader renders markdown and offers the source

The About reader shows a markdown document rendered, with a source view beside
it and the download inside it.  Where Scope 3 is absent the tab now reports
why, and names a stale cache as the first thing to check, rather than pointing
at files that are present.

### Fixed - Greases unit mismatch, caught before release

**No reported figure is affected and no released build ever produced this
result.**  The unit changed upstream on 19 August 2026, three weeks after the
30 July release, and the defect only appears when the model reads physicals
regenerated on or after that date.  No disclosure has used those physicals.
The fix is in the same unreleased window as the change that caused it.

What happened.  `OperationsMetricsActual.csv` reports greases in litres.
PrepData moved the line from kL to L on 19 August 2026 because the quantity
was unreadable in kilolitres.  The NGA factor for petroleum based greases is
published per kilolitre, so a litre quantity charged against it is a thousand
times too large.

The model logged `UOM MISMATCH ... Emissions will be WRONG for these rows` and
carried on regardless.  Reading the current physicals, 1,639,840 litres over
the life of mine would have been charged as 1,639,840 kilolitres.

Life of mine, on the current physicals.  The unfixed column is what an
unpatched build would have produced had one been run against this data; it is
not a figure anyone was given.

| | unfixed | fixed |
|---|---:|---:|
| Greases Scope 1 | 222,690 tCO2-e | 222.7 tCO2-e |
| Greases Scope 3 | 1,145,264 tCO2-e | 1,145.3 tCO2-e |
| Life of mine Scope 1 | 2,135,589 | 1,913,122 |
| Life of mine Scope 3 | 1,927,390 | 783,270 |

Scope 2 is unaffected.

`UOM_CONVERSIONS` in `Config.py` reconciles the reporting unit to the factor
unit on exact definitions, and `CalcEmissions.apply_emissions_to_df()` now
converts rather than logging.  A pair with no defined conversion raises: a
factor applied against the wrong unit is out by orders of magnitude and must
not pass as a log line.

The conversion happens at the point the factor is applied and nowhere else.
`Quantity` is never rewritten: the frame carries the quantity in the unit the
site reports it in, greases in litres, and the converted value exists only as
a local inside the calculation.  The source files are read and not touched.

The Safeguard source table gains `Factor_UOM`, `UOM_Conversion` and
`Quantity_Factor_Basis`, so a row reconciles without the reader having to know
which units disagreed:

    Quantity_Factor_Basis = Quantity x UOM_Conversion
    tCO2-e                = Quantity_Factor_Basis x EF / 1000

`UOM_Conversion` is 1.0 on every line whose unit already matches its factor.

The other five lines PrepData restated carry no NGA factor, so greases was the
only one that reached a calculation.

The exposure, stated in full: a build without this fix reading physicals
regenerated on or after 19 August 2026.  That combination has existed only in
development since 19 August.  Recalculate any working figure taken from the
model in that window; nothing issued needs restating.

### Added - Spend based result tested against the physical quantity

A spend factor is an economic average for a commodity class produced in one
country.  The EPA set is United States production, and the method takes the
position that manufacturing intensity per dollar is broadly comparable across
countries for a traded commodity.  That position holds better for some classes
than others.

`CalcScope3.implied_intensity_table()` divides the Category 1 result by the
quantity the same rows carry, for every group whose physicals are in a mass or
volume unit, and the Scope 3 tab shows it beside the published factor source.
Recorded expenditure only; a projected line inherits the intensity by
construction.

| Group | Unit | Quantity | AUD per unit | Implied tCO2-e per unit |
|---|---|---:|---:|---:|
| Cyanide | t | 2,724.7 | 4,169 | 2.806 |
| Grinding media | t | 3,500.7 | 1,708 | 0.412 |
| Lime | t | 4,804.7 | 400 | 0.431 |
| Activated carbon | t | 102.0 | 6,771 | 2.208 |
| Oxygen, bulk | m3 | 2,075,003 | 1.39 | 0.0011 |

Six of 149 product groups in the physicals carry a mass or volume unit.  The
rest are counted in Each, Kit, Roll, Pair or Set, and a count cannot be read
against a factor per tonne without a mass per item.

`physical_factor_status()` reports the basis in force per group: one on a
physical unit, 181 on spend.  Moving a group across is a configuration change,
an entry in `category_1.physical_unit_factors` and a rebuild of the factor
table.

### Added - Scope3Factors.csv

One flat factor table, built by `UtilityScope3ToCsv.py` from the product group
register, the EPA NAICS mapping, the capital goods intensities and the factors
stated in the parameter file.  The model reads one file, for the same reason
it reads `NgaFactors.csv` rather than five National Greenhouse Account
workbooks.

399 factors, each with its unit, dollar year, source, NAICS class and the
reason it is excluded where it is.  `ConfigScope3.yaml` keeps the activity
data and the policy: the roster, the travel pattern, the waste streams, the
currency basis, the projection rule and the exclusion register.  Rebuild the
table after changing either.

### Added - Scope 3, all fifteen categories

`CalcScope3.py`, `LoaderScope3.py`, `Data/ConfigScope3.yaml` and `Tab8Scope3.py`.
Every GHG Protocol category now appears in the output, whether it carries a
number, awaits data or is a documented exclusion.

Category 3 is unchanged.  It is still computed at transaction level in
`CalcEmissions.py` from NGA Scope 3 coefficients, still carried on
`Scope3_tCO2e`, and still the column the Safeguard baseline and the NGER
position read.  Nothing in the new module writes to it, and no tab reading
those frames sees the other categories.

| Cat | Method | Basis |
|---|---|---|
| 1 | Spend, with physical unit factors taking precedence | EPA SCEF by product group; AusLCI 2.12 t/t on explosives |
| 2 | Capitalised value | Cat2FactorMap intensity per $M, owned and finance leased only |
| 3 | NGA straight | unchanged, read not recomputed |
| 4 | Spend, margin component | EPA SCEF margins, fuel freight excluded as Cat 3 |
| 5 | Volume estimate | awaiting contractor volumes |
| 6 | Stated travel pattern | Brisbane to Townsville, 1.5 return sectors a week |
| 7 | Roster headcount and distance | 500 personnel, four on three off, 52 return trips |
| 10 | Gold mass times refining intensity | awaiting the refiner intensity |
| 8, 9, 11 to 15 | Documented exclusions | rationale carried in the parameter file |

`ConfigScope3.yaml` is the single input file.  It names the factor registers,
the currency basis, the parameters for every category the physicals cannot
supply, the exclusion register and the projection rule, and it carries no
factor of its own: those stay in `Data/Scope3/` as distributed registers.

**Currency.**  EPA factors are kilograms per 2022 United States dollar and
site expenditure is Australian dollars at the date incurred.  The quarter's
rate comes from `ReferenceFx.csv`, which PrepData distributes and never
applies.  The deflator restating spend-year dollars into 2022 dollars is
present and set to 1.00, so it is not applied and the result is understated
by United States producer price inflation since 2022.  Against the working
paper, which used a flat 0.6290, every spend line is 10.0 per cent higher:
cyanide 7,645 tCO2-e against 6,959.

**Forward projection.**  Expenditure is recorded on inventory transactions
from January 2026 and the budget physicals carry no value at all.  A dollar
per reporting unit rate is fitted per activity, subactivity and unit over the
seven closed months of 2026 and applied to budget quantities.  Rates are
nominal.  A line with no fitted rate projects nothing and is named on the tab.

**Reconciliation.**  Recorded expenditure $115,141,171, of which $61,346,669
is fuel charged as Scope 1 combustion and Category 3 well to tank, $53,788,317
is priced into Category 1, and $6,185 is explosives priced on physical units
instead.  The three account for the file exactly.

CY2026: Category 3 52,516 tCO2-e, Category 1 44,690, Category 4 1,696,
Category 7 1,141, Category 6 27, Category 2 8.  Category 3 is 52.5 per cent of
Scope 3 and Category 1 is 44.7 per cent; together they are 97.1 per cent.

### Added - Milestones come from LOM.yaml

`LoaderLom.py` reads `Data/LOM.yaml`, the shared reference PrepData
distributes, and `Config.py` takes its milestone dates from it.  The literals
remain as a fallback for a missing file or key, and the sidebar names the plan
revision in force.

`DEFAULT_END_PROCESSING_DATE` moves from 31 Dec 2045 to 31 Dec 2039.  The
2045 value was derived from stockpile exhaustion; PrepData now takes its
physicals from the budget and milling stops when the plan says it stops.  Six
years of projected emissions come out of every total.

### Changed - The loader carries product group and value

`OperationsMetricsActual.csv` gained `ProductGroup` and `Value` in the 2026-08
PrepData change; the budget CSV has neither.  `LoaderData.py` creates
whichever column is absent, carries both through aggregation and groups on
product group.  `Value` stays float64: spend runs to nine figures and float32
loses dollars at that magnitude.

### Fixed - 12,271 rows carried no classification

The inventory change raised the item register from 150 items to 8,113 and put
138 stores product groups into the physicals.  `LookupIdentifiers.py` gains an
activity level fallback for Stores and Headcount, whose subactivity lists are
open, and exact entries for `Mining / Ore Rehandle` and `Blasting / Broken
Stock`.  Every row in both files is now classified.

The `Total Other` rollup rows introduced by the 80/20 disclosure change keep
their activity and subactivity, so they mapped correctly already.

### Added - About tab

`AboutPanel.py`, a portable panel that renders the release history from this
file with a release picker and a search box.  Supporting documents open in a
modal reader rather than downloading, with the download offered inside it.

---

## 2026-08-13

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.

### Fixed - Lifecycle phase dates did not match the data
`Config.py` carried phase boundaries that no longer reflected the budget
physicals.  Verified against `OperationsMetricsBudget.csv` and corrected:

| Constant | Was | Now | Evidence |
|---|---|---|---|
| `DEFAULT_END_MINING_DATE` | 31 Mar 2037 | 31 Dec 2037 | last `Mining/Ore ROM` record |
| `DEFAULT_END_PROCESSING_DATE` | 31 Dec 2039 | 31 Dec 2045 | last `Revenue/Gold Sold`; stockpile exhaustion derived in PrepData |
| `DEFAULT_END_REHABILITATION_DATE` | 31 Dec 2044 | 31 Dec 2049 | last budget record of any kind |
| `DEFAULT_GRID_CONNECTION_DATE` | 1 Jul 2027 | 1 Jul 2028 | operational input |

`DEFAULT_END_REHABILITATION_DATE` also serves as the model horizon (`end_date`),
so the previous value truncated five years of budget data - the whole
rehabilitation phase.  Totals move accordingly.

Note: the budget physicals still step grid power up and cut power-generation
diesel at Jul 2027, one year ahead of the corrected connection date.  PrepData
`PlantConfig.yaml` has been updated to 2028-07-01; the budget CSV in `Data/`
needs regenerating before the two agree.

### Added - Tab 7 Lifecycle
New `Tab7Lifecycle.py`, registered in `App.py` as the seventh tab.  Display
only, per file conventions - no emissions maths.  Puts the lifecycle
assumptions next to the physicals they drive:

- **Key dates** with derived-versus-input labelling, and a phase bar.
- **Throughput sanity check** - ROM mined, stockpile reclaim, crusher feed and
  mill feed on one chart.  If milling continues after ROM ore stops, the
  difference has to be reclaim, and there has to be a rehandle line carrying
  the fuel to move it.  A gap here is the fastest check on the wind-down.
- **Mill head grade** (g/t) - contained gold over milled tonnes, both from the
  same source series, so it is unit-safe.
- **Gold production and implied recovery**, with years outside 50-95% withheld
  and explained.  Gold poured is capped at 200,000 oz/yr in the forecast, so it
  runs flat while contained gold varies with grade; implied recovery reflects
  the cap, not the plant.
- **Activity decline** - every stream as a percentage of its own peak, so
  streams in kL, t, kWh and oz share one axis.  Shows what stops at end of
  mining, what carries to end of processing and what runs into rehabilitation.
- **Wind-down methodology** table and an open-items register of every
  placeholder still awaiting a department.

Charting notes, both found while building the tab:
- `Crushing/Ore Crushed` carries feed throughput AND product feed for every
  crusher, plus a parallel beneficiation series in dmt.  Summing the subactivity
  double counts the same tonnes two or three times, so the chart uses the
  `Feed Throughput` descriptions only.
- Cost-centre level series mix kL, t, hrs and Each.  Every activity-group
  matcher is restricted to a single unit.

---

## 2026-08-06

**Status:** Unreleased, after the 30 July 2026 release  
**Impact:** None on any released build.

### Fixed
- Tab 1 emissions intensity chart: neither series was inclusive of all emissions
  across the projection horizon.  Two independent causes:
  - **Gold series truncated at the last actual year.**  `Tab1Ghg.py` derived
    ounces from the raw DataFrame using `CommonName == 'Gold recovered'` with
    `RowType == 'production'`.  That series exists only in
    `OperationsMetricsActual.csv`; the budget CSV carries `Gold Sold` and
    `Gold Poured` only.  Every budget year therefore returned `gold_oz = 0` and
    was dropped, so the gold trace covered FY2024-FY2026 while the emissions
    numerator ran to FY2050.
  - **ROM series dropped its final mining year.**  `ROM_Intensity` was gated on
    `fy_num < _end_mining_yr` in addition to the `ROM_Mt > 0` test.  The extra
    gate was redundant and truncated FY2038.
- Numerator and denominator used different de-duplication rules.  Gold was
  de-duplicated inside the tab by a month-level "prefer actual over budget"
  test, while the emissions numerator used the loader's `(Date, MatchKey)`
  exclusion.  The two were not guaranteed to reconcile in the actual/budget
  overlap period.

### Added
- `GOLD_SUBACTIVITY = 'Gold Sold'` in `Config.py`, alongside `ROM_SUBACTIVITY`.
  `Gold Sold` is the only gold measure present in both the actual and budget
  CSVs for the full life of mine, so it is the only denominator that supports
  an intensity series across the whole horizon.
- `Gold_oz` column in `Projections.aggregate_to_monthly()`, extracted from the
  same de-duplicated actual+budget frame that produces the emissions totals, so
  numerator and denominator always cover an identical set of months.
- `Gold_oz` and `Gold_Intensity` columns in `CalcPrecompute._aggregate_annual()`.
  `Gold_Intensity` uses the same `Total` (Scope 1 + 2 + 3) numerator as
  `Total_Intensity`, so both series are inclusive of every scope rather than
  mining-phase sources alone.

### Changed
- `Tab1Ghg.py` intensity block now reads `Gold_oz` and `ROM_Mt` straight from
  the projection frame instead of re-deriving gold from the raw DataFrame.
- Chart title, legend and left axis relabelled to "per Ounce Gold Sold" /
  "tCO2-e / oz Au sold" to state the denominator explicitly.
- `Gold_oz` aggregation in `_aggregate_annual()` is guarded on column presence
  so a stale cached monthly frame does not raise.

### Verified
- Rebuilt from live data.  Gold intensity now spans FY2024-FY2045 (was
  FY2024-FY2026); ROM intensity spans FY2024-FY2038 (was FY2024-FY2037).

  | FY | ROM (Mt) | Gold sold (oz) | Total tCO2-e | tCO2-e/t ROM | tCO2-e/oz Au |
  |---|---|---|---|---|---|
  | FY2026 | 4.53 | 125,302 | 297,459 | 0.0656 | 2.374 |
  | FY2029 | 19.56 | 197,180 | 351,204 | 0.0180 | 1.781 |
  | FY2038 | 0.45 | 196,850 | 206,110 | 0.4547 | 1.047 |
  | FY2045 | 0.00 | 14,217 | 17,831 | - | 1.254 |

### Fixed (second pass, same day)
- Intensity spiked in the year each phase ceased.  Emissions accrue for the
  whole year, but the denominator only covers the part year up to shutdown, so
  the ratio steps near vertical.  Mining ends 31 Mar 2037, so CY2037 carried
  0.9 Mt ROM against a full year of processing emissions and rendered a cliff
  on the secondary axis.  The same effect appeared at the tail of the gold
  series.
- Each series is now plotted only for years in which its phase is active on
  every day of the period: ROM intensity to the last full year of mining, gold
  intensity to the last full year of processing.  ROM now ends CY2036 / FY2036,
  gold ends CY2039 / FY2039.  Part years are dropped rather than shown as an
  artefact.

### Investigated - intensity trend is not a decarbonisation signal
Scepticism about the Scope 1 + 2 + 3 trend is well founded.  The downward slope
is driven by two flat inputs in the budget CSV, not by abatement:

- **Scope 2 is a constant block.**  Budget `Grid Power` is held at roughly
  229 GWh per year from CY2028 to CY2042, unchanged while ROM swings from
  19.9 Mt (CY2029) to 0.0 Mt (CY2038).  Grid consumption is fully decoupled
  from production.  The resulting Scope 2 is flat at about 154,300 tCO2-e per
  year across those fifteen years, rising from 43 per cent of total emissions
  in CY2029 to 83 per cent in CY2042.
- **Gold sold is also flat**, at roughly 196,000 to 198,000 oz per year over
  the same span.
- With both the constant Scope 2 block and the denominator fixed, the only
  moving part is the Scope 1 diesel fleet winding down.  The apparent
  improvement from 2.5 to 0.95 tCO2-e/oz is that wind-down divided by two
  constants, not an emissions reduction trajectory.
- **No grid decarbonisation is modelled.**  `NgaFactors.csv` holds 2022-2025
  only, and `LoaderNga._resolve_year()` clamps any year above the maximum to
  the maximum.  Every kWh from CY2026 to CY2049 is costed at the 2025 QLD
  factor.  Conservative for disclosure, but it means the flat Scope 2 block is
  artificial on both quantity and factor.
- **The trend line is not a valid fit.**  `Tab1Ghg.py` runs a first-order
  `np.polyfit` across a series that rises to a peak then decays, and adds a
  hard-coded `+ 0.2` offset.  A straight line through a non-monotonic series
  crosses it rather than describing it.

No code change made for the above - these are data and model questions, not
plotting defects.  Raised for decision.

### Open - budget data conflicts with configured phase dates
`Config.DEFAULT_END_PROCESSING_DATE` is 31 Dec 2039, but the budget CSV carries
gold sales for five years beyond it: CY2040 198,088 oz, CY2041 197,216 oz,
CY2042 196,163 oz, CY2043 151,503 oz, CY2044 53,432 oz.  Grid Power runs to
CY2044 on the same profile.  The phase-based truncation above therefore drops
those years from the gold series.  One of the two sources is wrong - either the
end-of-processing date is stale, or the budget extends processing past the
modelled mine life.  Not resolved here.

### Unchanged
- `ExportGri14.py` continues to use `Gold recovered` for GRI 14 production
  metrics.  GRI reports actuals only, so the budget gap does not apply there.
- `Total_Intensity` (Scope 1 + 2 + 3 per tonne ROM) in the Tab 1 summary table
  and `Scope1_Intensity` used by Safeguard: calculation unaltered.

### Notes
- `st.cache_resource` must be cleared (restart the app) so `precompute_all()`
  rebuilds with the new `Gold_oz` column.
- FY2038 ROM intensity of 0.4547 is arithmetically correct - mining winds down
  to 0.45 Mt while processing continues - but renders as a step change on the
  secondary axis.  Suppression or a log axis is a display decision, not raised
  here.
- Pre-existing and untouched: the gold trend line in `Tab1Ghg.py` adds a
  hard-coded `+ 0.2` offset, which is material against intensities near 1.0.

---

## 2026-07-28

**Status:** Released 30 July 2026

### Changed
- Project-wide file and folder naming convention moved to PascalCase.  Module
  renames (22 files):

  | Old | New | Old | New |
  |---|---|---|---|
  | `app.py` | `App.py` | `loader_data.py` | `LoaderData.py` |
  | `calc_calendar.py` | `CalcCalendar.py` | `loader_nga.py` | `LoaderNga.py` |
  | `calc_emissions.py` | `CalcEmissions.py` | `lookup_identifiers.py` | `LookupIdentifiers.py` |
  | `calc_ghg.py` | `CalcGhg.py` | `projections.py` | `Projections.py` |
  | `calc_precompute.py` | `CalcPrecompute.py` | `tab1_ghg.py` | `Tab1Ghg.py` |
  | `config.py` | `Config.py` | `tab2_safeguard.py` | `Tab2Safeguard.py` |
  | `crypto_utils.py` | `CryptoUtils.py` | `tab3_carbon_tax.py` | `Tab3CarbonTax.py` |
  | `export_builder.py` | `ExportBuilder.py` | `tab4_nger.py` | `Tab4Nger.py` |
  | `export_gri14.py` | `ExportGri14.py` | `tab5_query.py` | `Tab5Query.py` |
  | `export_package.py` | `ExportPackage.py` | `tab6_gri.py` | `Tab6Gri.py` |
  | `fabric_report_export.py` | `FabricReportExport.py` | `Utility_NGA_to_csv.py` | `UtilityNgaToCsv.py` |

- Folders: `data/` -> `Data/`, `out/` -> `Out/`.  Note the code already expected
  `Data`; macOS case-insensitivity was masking the mismatch and it would have
  failed on a case-sensitive filesystem (Linux deploy, Docker, CI).
- Data files: `NgaFactors.csv`, `OperationsMetricsActual.csv(.enc)`,
  `OperationsMetricsBudget.csv(.enc)`, `SmcTransactions.csv`, `PrepData.txt`.
- Output files: `Out/AasbS2.csv`, `Out/Combined.csv`, `Out/Gri14.csv`, `Out/Ngers.csv`.
- NGA workbooks: `national-greenhouse-account-factors-YYYY.xlsx` ->
  `NationalGreenhouseAccountFactorsYYYY.xlsx` (2021-2025).
- Root: `CHANGELOG.md` -> `Changelog.md`, `data_loading.log` -> `DataLoading.log`.
- Documentation: `SystemDocumentation.md`, `Jan2026UpdateWorkingPaperAddendum.md`,
  `MethodologyPaperV2.docx`, `MethodologyPaperV3.docx`,
  `Gri14MiningSector2024V11.pdf`, `Budget/RwgBudgetBook2026Final20260113.pdf`,
  `Budget/Rom.jpg`, `Budget/Image001.png`.
- All import statements, data path strings, docstrings and comments updated to
  match.  `Config.py` NGA default is now `NationalGreenhouseAccountFactors2025.xlsx`.
- `UtilityNgaToCsv.py` now looks for `NationalGreenhouseAccountFactors{year}.xlsx`
  first and retains the government hyphenated filename as a fallback, so freshly
  downloaded DCCEEW workbooks still resolve without renaming.
- `ExportPackage.py` writes CSVs into `Data/` inside the generated ZIP (was `data/`).

### Unchanged
- Runtime-generated export filenames (`tab1_emissions_summary_FY*.csv`,
  `tab3_carbon_tax_liability.png`, etc.) keep their existing names so downstream
  consumers of exported packages are not broken.
- Tool-mandated names: `requirements.txt`, `.gitignore`, `.streamlit/secrets.toml`,
  `.idea/`, `.venv/`.
- Earlier entries in this changelog retain the original file names as written at
  the time, for historical accuracy.

### Notes
- PyCharm run configurations in `.idea/workspace.xml` still reference `app.py`;
  update the Streamlit run configuration to `App.py`.
- Stale `__pycache__/*.pyc` for the old module names remain tracked in git despite
  `.gitignore`; `git rm -r --cached __pycache__` clears them.
- Known pre-existing defect (not introduced here): `ExportGri14.py` looks for
  `NgaFactors.csv` in the module directory rather than `Data/`.

---

## 2026-05-19

**Status:** Released, superseded by the 30 July 2026 release

### Added
- GHG Protocol Scope 1 emissions for explosives (ANFO) detonation on Tab 1 (GHG).
  Factor: 0.17 t CO₂/t ANFO (AGO / Dept of Climate Change).  Confirmed: NGA Factors
  (2022–2025 editions) do not include explosives — consistent with CER s2.7 exclusion.
- New module `calc_ghg.py`: builds a GHG Protocol DataFrame by overlaying GHG-only
  emissions (currently explosives) onto the clean NGER frame.  Extensible for future
  GHG-only items.
- `GHG_EXPLOSIVES_EF_T_CO2_PER_T` and `GHG_EXPLOSIVES_EF_KG_CO2_PER_KG` constants
  in `config.py`.
- GHG frame fields in `PrecomputedData`: `ghg_df`, `ghg_annual_fy`, `ghg_annual_cy`.
- `get_ghg_annual()` function in `calc_precompute.py`.
- Explanatory section in Tab 4 (NGER/Model Reference): GHG vs NGER treatment of
  explosives, citing CER guideline s2.7 (July 2025).
- This changelog (`CHANGELOG.md`).

### Fixed
- `calc_precompute.py`: `precompute_all()` was importing `build_ghg_frame` but
  never calling it — GHG dataclass fields defaulted to empty DataFrames, so
  Tab 1 always fell back to the NGER frame (no explosives).  Now wired up:
  calls `build_ghg_frame(df)`, runs a separate `build_projection()` pass and
  aggregates to `ghg_annual_fy` / `ghg_annual_cy`.
- `operations_metrics_actual.csv`: 50 explosives rows had raw kg values
  mislabelled as `t` (pint conversion failed silently in earlier prepData
  import runs).  Quantities divided by 1000.  All 55 rows now 60–418 t range.

### Changed
- `app.py`: Tab 1 (GHG) now receives `precomputed.ghg_df` and `ghg_frame` (GHG
  annual data) instead of the NGER equivalents.
- `tab4_nger.py`: New Section 7A expander explaining dual-framework treatment.

### Unchanged
- NGER frame: explosives remain zero emissions per CER guideline s2.7 (July 2025).
  Fuel oil in ANFO reported as consumed without combustion by Orica (operational control).
- Tab 2 (Safeguard), Tab 3 (Carbon Tax): no changes — continue to use NGER frame.
- `calc_emissions.py`, `projections.py`, `tab1_ghg.py`, `tab2_safeguard.py`,
  `tab3_carbon_tax.py`, `lookup_identifiers.py`: no modifications.

### Architecture
- NGER frame = clean data, used by Safeguard (Tab 2) and Carbon Tax (Tab 3).
- GHG frame = NGER + GHG-only overlay, used by GHG (Tab 1).
- GHG frame includes all scopes (1, 2, 3); Safeguard uses Scope 1 only.

### References
- CER: Reporting blended fuels, other fuel mixes, bitumen and explosives guideline (July 2025)
- AGO / Dept of Climate Change: 0.17 t CO₂/t ANFO emission factor (pre-NGA methodology;
  NGA Factors 2022–2025 confirmed to contain no explosives/ANFO entries)
- Balmoral South Iron Ore Project GHG Assessment (Kewan Bond, 2008) — precedent for
  Scope 1 treatment of ANFO under AGO methods
