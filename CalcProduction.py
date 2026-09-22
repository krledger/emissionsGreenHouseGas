"""The physical measures, and whether they agree with the plan.

Emissions are a function of physicals, so a physical that is wrong produces
an emissions figure that is wrong and still looks reasonable.  Tonnes entered
in the wrong unit, a stream that stops mid-forecast, gold recorded against
the wrong activity: none of these announce themselves in a tonnage of CO2-e.

What catches them is the plan.  LOM.yaml carries what the life of mine says
this operation does: the grade of the ore, the recovery the plant achieves,
the capacity of the mill and the crusher, and the total to be mined.  A build
that disagrees with the plan is either a data fault or a change worth
knowing, and both are worth stopping for before anything is published.

Head grade is the sharpest of these.  Contained gold and milled tonnes reach
the model as separate series from separate sources, so a unit error in either
moves the grade immediately while the emissions total stays plausible.

Nothing here decides what a figure should be.  The reference values are read
from the plan, the tolerances from Data/Assumptions.yaml, and this module
computes what the data says and compares the two.
"""

import numpy as np
import pandas as pd

from CalcCalendar import date_to_cy, date_to_fy
from CalcUnits import (GRAMS_PER_TROY_OUNCE, TONNES_PER_KILOTONNE,
                       TONNES_PER_MEGATONNE)
from Config import (NGER_FY_START_MONTH, GRADE_TOLERANCE,
                    RECOVERY_TOLERANCE,
                    THROUGHPUT_TOLERANCE, RECOVERY_PLAUSIBLE_LOW,
                    RECOVERY_PLAUSIBLE_HIGH,
                    POWER_INTENSITY_TOLERANCE,
                    PROCESS_POWER_SUBACTIVITIES,
                    HEAD_GRADE_TOLERANCE,
                    DEFAULT_END_PROCESSING_DATE,
                    DIESEL_INTENSITY_TOLERANCE)

# Recorded months needed before a stream can be read against its driver.
# A year gives a floor and a rate that mean something; fewer does not.
DRIVER_FIT_MONTHS = 12
KWH_PER_GWH = 1_000_000.0

# Stockpile rehandle feeds the mill and runs after the pit closes, so it
# is not pit work.  Named by cost centre, as the site codes it.
REHANDLE_PATTERN = r'Rehandl|Bene Rejects'
from LoaderLom import LOM


# ---------------------------------------------------------------------
# THE STREAMS
# ---------------------------------------------------------------------
# Each stream is a rule for selecting rows, held here rather than in a screen
# so that the same tonnes answer the same question wherever it is asked.
# Grouping is by work type and not by emission scope: the question these
# answer is whether the operation makes sense, not what it emitted.

def rom_mined(frame):
    return (frame['Activity'] == 'Mining') & (frame['SubActivity'] == 'Ore ROM')


def _diesel(frame):
    return ((frame['Activity'] == 'Combustion')
            & (frame['SubActivity'] == 'Diesel'))


def reclaim(frame):
    # Diesel only.  A cost centre carries kL, tonnes, hours and 'Each', which
    # cannot be summed into one series.
    return _diesel(frame) & frame['CostCentre'].astype(str).isin(['Rehandling'])


def tailings(frame):
    # Tailings deposition is pumped, so its diesel is next to nothing and
    # arrives in odd years.  The flocculant dosed to the tailings is the
    # measure that runs whenever the plant does.
    return ((frame['Activity'] == 'Reagent')
            & (frame['SubActivity'] == 'Flocculant')
            & (frame['CostCentre'].astype(str) == 'Tailings Disposal'))


def dredging(frame):
    # The dredges' diesel.  Kept apart from tailings, because a dredge runs
    # when there is ore to dredge and not every year.
    return _diesel(frame) & frame['CostCentre'].astype(str).isin(
        ['NPE Dredge', 'Sarsfield Dredging'])


def crushing(frame):
    # Crusher feed only.  The raw 'Ore Crushed' set carries both feed
    # throughput and product feed for every crusher, plus a parallel
    # beneficiation series in dry metric tonnes; summing them counts the same
    # tonnes two or three times.
    return ((frame['Activity'] == 'Crushing')
            & (frame['SubActivity'] == 'Ore Crushed')
            & (frame['Description'].astype(str)
               .str.contains('Feed Throughput', na=False)))


def milling(frame):
    return ((frame['Activity'] == 'Milling')
            & (frame['SubActivity'] == 'Ore Milled'))


def process_power(frame):
    """Electricity drawn by the plant, whichever supply it came from.

    Grid Power and Site Power are the same draw from two sources, and the
    plan swaps one for the other at grid connection, so a check on how much
    the plant used has to read both.  Camp, warehouse and water delivery are
    site services and do not move with the mill.
    """
    return ((frame['Activity'] == 'Electricity')
            & frame['SubActivity'].astype(str).isin(
                PROCESS_POWER_SUBACTIVITIES))


def contained_gold(frame):
    return ((frame['Activity'] == 'Milling')
            & (frame['SubActivity'] == 'Ore Gold'))


def gold_poured(frame):
    return ((frame['Activity'] == 'Revenue')
            & (frame['SubActivity'] == 'Gold Poured'))


def reagents(frame):
    return (frame['Activity'] == 'Reagent') & (frame['UOM'].astype(str) == 't')


def grid_power(frame):
    return ((frame['Activity'] == 'Electricity')
            & (frame['SubActivity'] == 'Grid Power'))


def site_generation(frame):
    return _diesel(frame) & (frame['CostCentre'].astype(str)
                             == 'Site Power Generation')


def mining_fleet(frame):
    return _diesel(frame) & (frame['Department'].astype(str)
                             .str.startswith('Mining'))


def light_vehicles(frame):
    return _diesel(frame) & (frame['CostCentre'].astype(str) == 'Light Vehicles')


STREAMS = {
    'ROM ore mined': rom_mined,
    'Mining fleet diesel': mining_fleet,
    'Reclaim rehandle': reclaim,
    'Tailings': tailings,
    'Dredging': dredging,
    'Crushing': crushing,
    'Milling': milling,
    'Reagents': reagents,
    'Grid electricity': grid_power,
    'Site generation': site_generation,
    'Light vehicles': light_vehicles,
}


# ---------------------------------------------------------------------
# ANNUAL SERIES
# ---------------------------------------------------------------------

def material_moved(frame):
    """Ore and waste tonnes taken from the pit: what the mining fleet works on."""
    return ((frame['Activity'] == 'Mining')
            & frame['SubActivity'].isin(['Ore ROM', 'Ore Waste'])
            & (frame['UOM'].astype(str) == 't'))


def pit_diesel(frame):
    """Mining fleet diesel spent in the pit.

    The fleet less stockpile rehandle, which feeds the mill and runs after the
    pit closes, and less the dredges, which run on a span of their own.
    """
    rehandle = frame['CostCentre'].astype(str).str.contains(
        REHANDLE_PATTERN, regex=True)
    return mining_fleet(frame) & ~rehandle & ~dredging(frame)


def _fit_line(driven, used, floor):
    """Consumption against its driver, as a rate and optionally a floor.

    Theil-Sen: the rate is the median of the slopes between every pair of
    months, and the floor the median of what each month leaves over.  A
    median fit is not pulled by an odd month the way least squares is.

    Without a floor, or where the fit gives a negative floor or a rate at or
    below nil (which describes no real plant), the line is a straight rate:
    total consumption over total driver in the months read.

    Returns (floor, rate).
    """
    x = np.asarray(driven, dtype=float)
    y = np.asarray(used, dtype=float)
    straight = (0.0, float(y.sum() / x.sum()) if x.sum() > 0 else 0.0)
    if not floor:
        return straight
    first, second = np.triu_indices(len(x), 1)
    step = x[second] - x[first]
    usable = np.abs(step) > 0
    if not usable.any():
        return straight
    rate = float(np.median((y[second] - y[first])[usable] / step[usable]))
    base = float(np.median(y - rate * x))
    if base < 0 or rate <= 0:
        return straight
    return base, rate


def driver_line(frame, consumer, driver, floor):
    """One consumption stream against the driver it should follow.

    Derived from the recorded months only, never from the forecast being
    checked: consumption a month = floor + rate x driver, fitted over every
    recorded month in which both were measured.  The floor is what the plant
    draws to run at all, so a year at part throughput draws more per tonne
    than a full one and still sits on the line; it applies only in a month
    the driver runs.  A stream with no floor is a straight rate.

    Takes a frame from with_year().  Returns None with fewer than
    DRIVER_FIT_MONTHS recorded months to read, otherwise a dict:
        years     one row per year from the first year the driver is
                  measured: Used, Driver, Running (months the driver ran),
                  Expected (on the line), Apart (share away from the line)
        floor     consumption a running month before any tonne
        rate      consumption per unit of driver
        months    recorded months the line was read from
    """
    if 'Date' not in frame.columns or 'DataSet' not in frame.columns:
        return None
    used = frame[consumer(frame)]
    driving = frame[driver(frame)]

    recorded = lambda part: part[part['DataSet'].astype(str) == 'Actual']
    fit = pd.concat([
        recorded(used).groupby('Date')['Quantity'].sum().rename('used'),
        recorded(driving).groupby('Date')['Quantity'].sum().rename('driver'),
    ], axis=1, sort=True).dropna()
    fit = fit[(fit['driver'] > 0) & (fit['used'] > 0)]
    if len(fit) < DRIVER_FIT_MONTHS:
        return None
    base, rate = _fit_line(fit['driver'], fit['used'], floor)

    months = pd.concat([
        used.groupby(['_yr', 'Date'])['Quantity'].sum().rename('used'),
        driving.groupby(['_yr', 'Date'])['Quantity'].sum().rename('driver'),
    ], axis=1, sort=True).fillna(0.0).reset_index()
    if months.empty:
        return None
    # Before the driver is first measured there is nothing to hold the stream
    # to, and a month of consumption with no recorded driver is a gap in the
    # history, not a fault in the forecast.  Cut at the month, not the year,
    # so a year that starts before the driver does is read from its start.
    begins = months.loc[months['driver'] > 0, 'Date'].min()
    months = months[months['Date'] >= begins]
    years = months.groupby('_yr').agg(
        Used=('used', 'sum'), Driver=('driver', 'sum'),
        Running=('driver', lambda s: int((s > 0).sum())))
    years['Expected'] = base * years['Running'] + rate * years['Driver']

    # A year the driver does not run is held to nothing, and measured against
    # a typical recorded year so a trickle (a camp meter after closure) is not
    # reported while a fleet still burning at half its rate is.
    typical = float(recorded(used).groupby(
        recorded(used)['Date'].dt.year)['Quantity'].sum().median() or 0.0)
    apart = pd.Series(0.0, index=years.index)
    on = years['Expected'] > 0
    apart[on] = ((years.loc[on, 'Used'] - years.loc[on, 'Expected']).abs()
                 / years.loc[on, 'Expected'])
    idle = ~on & (years['Used'] > 0)
    if typical > 0:
        apart[idle] = years.loc[idle, 'Used'] / typical
    years['Apart'] = apart
    return {'years': years, 'floor': base, 'rate': rate, 'months': len(fit)}


# Each consumption stream the forecast carries, the driver it should follow,
# and whether the plant has a floor under it.  Power has one: a mill draws
# power to turn at all, whatever the tonnes.  Pit diesel is a straight rate
# on the tonnes the fleet moves.
DRIVER_CHECKS = (
    {'Check': 'Power against tonnes milled', 'consumer': process_power,
     'driver': milling, 'floor': True, 'scale': 1.0, 'unit': 'kWh per t',
     'tolerance': 'power', 'scope': 'Scope 2',
     'floor_says': lambda v: f'{v / KWH_PER_GWH:,.1f} GWh a month while the '
                             f'mill runs',
     'rate_says': lambda v: f'{v:,.1f} kWh per tonne milled',
     'follows': 'the mill'},
    {'Check': 'Pit diesel against material moved', 'consumer': pit_diesel,
     'driver': material_moved, 'floor': False, 'scale': 1000.0,
     'unit': 'kL per kt', 'tolerance': 'diesel', 'scope': 'Scope 1',
     'floor_says': lambda v: '',
     'rate_says': lambda v: f'{v * 1000:,.2f} kL per thousand tonnes of ore '
                            f'and waste moved',
     'follows': 'the mine'},
)


def _driver_row(spec, dated):
    """The plan check row for one DRIVER_CHECKS entry, or None."""
    line = driver_line(dated, spec['consumer'], spec['driver'], spec['floor'])
    if line is None:
        return None
    tolerance = (POWER_INTENSITY_TOLERANCE if spec['tolerance'] == 'power'
                 else DIESEL_INTENSITY_TOLERANCE)
    years = line['years']
    adrift = years[years['Apart'] > tolerance]
    said = spec['rate_says'](line['rate'])
    if line['floor'] > 0:
        said = f"a floor of {spec['floor_says'](line['floor'])}, plus {said}"
    basis = (f"The {line['months']} recorded months give {said}")

    # The figure shown is the worst year the driver ran in, as consumption
    # per unit of driver against the line's own figure for that year.
    ran = years[years['Driver'] > 0]
    shown = adrift[adrift['Driver'] > 0] if not adrift.empty else ran
    if shown.empty:
        shown = ran
    worst = shown['Apart'].idxmax() if not shown.empty else None
    measured = planned = None
    if worst is not None:
        measured = float(years.loc[worst, 'Used'] / years.loc[worst, 'Driver']
                         * spec['scale'])
        planned = float(years.loc[worst, 'Expected'] / years.loc[worst, 'Driver']
                        * spec['scale'])
    if adrift.empty:
        means = (f"{basis}.  Every year sits within "
                 f"{tolerance:.0%} of that line.")
    else:
        idle = adrift[adrift['Driver'] <= 0].index
        moved = adrift[adrift['Driver'] > 0].index
        parts = []
        if len(moved):
            parts.append('off the line in ' + ', '.join(
                str(int(y)) for y in moved))
        if len(idle):
            parts.append('running with nothing to drive it in ' + ', '.join(
                str(int(y)) for y in idle))
        means = (f"{basis}.  The forecast is {' and '.join(parts)}, so it is "
                 f"not following {spec['follows']} and the {spec['scope']} "
                 f"that rests on it sits in the wrong years.  The forecast "
                 f"is corrected in PrepData.")
    return {
        'Check': spec['Check'],
        'Measured': None if measured is None else round(measured, 2),
        'Planned': None if planned is None else round(planned, 2),
        'Unit': spec['unit'],
        'Drift': _band(measured, planned, tolerance),
        'Tolerance': tolerance,
        'Verdict': 'agrees' if adrift.empty else 'disagrees',
        'Means': means}


def with_year(frame, year_type='CY'):
    """The frame with a plain integer year column for the chosen basis.

    Computed on the whole column at once.  A per row call into the calendar
    helpers costs about half a minute on four hundred thousand rows and this
    runs several times on one page, which is the difference between a check
    somebody waits for and a check somebody skips.

    The two bases are the same arithmetic: a calendar year is the year, and a
    financial year is the year plus one from July.
    """
    if '_yr' in frame.columns:
        return frame
    out = frame.copy()
    if 'Date' in out.columns:
        dates = pd.to_datetime(out['Date'], errors='coerce')
    else:
        dates = pd.to_datetime(dict(year=out['Year'], month=out['Month'],
                                    day=1), errors='coerce')
    years = dates.dt.year
    if year_type == 'FY':
        years = years + (dates.dt.month >= NGER_FY_START_MONTH).astype('int64')
    out['_yr'] = years
    return out.dropna(subset=['_yr'])


def annual(frame, stream, year_type='CY'):
    """Annual total quantity for one stream."""
    dated = frame if '_yr' in frame.columns else with_year(frame, year_type)
    rows = dated[stream(dated)]
    if rows.empty:
        return pd.Series(dtype=float)
    return rows.groupby('_yr')['Quantity'].sum().sort_index()


def streams(frame, year_type='CY'):
    """Every stream as an annual series, in one pass over the frame."""
    dated = with_year(frame, year_type)
    return {name: annual(dated, rule, year_type)
            for name, rule in STREAMS.items()}


# ---------------------------------------------------------------------
# THE DERIVED MEASURES
# ---------------------------------------------------------------------

def head_grade(frame, year_type='CY'):
    """Contained gold over milled tonnes, in grams per tonne.

    The two series come from different sources and are recorded in different
    units, gold in ounces and ore in tonnes, so this is the check that a unit
    error upstream cannot survive.  A grade of six grams where the plan says
    zero point six is a factor of ten somewhere, and the emissions total will
    not have blinked.
    """
    dated = with_year(frame, year_type)
    gold_oz = annual(dated, contained_gold, year_type) / GRAMS_PER_TROY_OUNCE
    milled_t = annual(dated, milling, year_type)
    if gold_oz.empty or milled_t.empty:
        return pd.Series(dtype=float)
    grams = gold_oz * GRAMS_PER_TROY_OUNCE
    grade = grams / milled_t.reindex(gold_oz.index)
    return grade.replace([np.inf, -np.inf], np.nan).dropna()


def recovery(frame, year_type='CY'):
    """Gold poured over contained gold, as a percentage.

    Contained and poured are separate source series and do not align at the
    shoulders of the mine life, where a mill is running on stockpile that was
    counted as contained in an earlier year.  Anything outside a plausible
    metallurgical band is a timing artefact rather than a recovery result,
    which is why the band is applied rather than the number reported raw.
    """
    dated = with_year(frame, year_type)
    contained = annual(dated, contained_gold, year_type) / GRAMS_PER_TROY_OUNCE
    poured = annual(dated, gold_poured, year_type)
    if contained.empty or poured.empty:
        return pd.Series(dtype=float)
    result = poured / contained.reindex(poured.index) * 100.0
    return result.replace([np.inf, -np.inf], np.nan).dropna()


def implausible_recovery(frame, year_type='CY'):
    """The years whose recovery cannot be a recovery.

    Not a list of bad years so much as a measure of how well the two gold
    series line up.  A handful is the ordinary shoulder effect at the start
    and end of the mine life.  Most of them means the two series are keyed to
    different things and one of them is not what it is labelled.
    """
    result = recovery(frame, year_type)
    if result.empty:
        return result
    return result[(result < RECOVERY_PLAUSIBLE_LOW)
                  | (result > RECOVERY_PLAUSIBLE_HIGH)]


def recovery_overall(frame, year_type='CY'):
    """Total gold poured over total gold contained, across the whole span.

    The only honest way to state a recovery from these two series.  Annually
    they are not the same gold: ore waits on a stockpile, a mill runs on last
    year's feed, and a pour lands after the run that produced it.  Over the
    life every ounce milled is eventually poured, so the cumulative ratio is
    a recovery where the annual one is a timing artefact.

    Measured over the years both series carry, so a mill year with no pour
    recorded against it does not drag the figure down.
    """
    dated = with_year(frame, year_type)
    contained = annual(dated, contained_gold, year_type) / GRAMS_PER_TROY_OUNCE
    poured = annual(dated, gold_poured, year_type)
    if contained.empty or poured.empty:
        return None
    shared = contained.index.intersection(poured.index)
    if len(shared) == 0:
        return None
    total_contained = float(contained.loc[shared].sum())
    if total_contained <= 0:
        return None
    return float(poured.loc[shared].sum()) / total_contained * 100.0


def intensity(frame, year_type='CY', scope_columns=('Scope1_tCO2e',)):
    """Emissions per tonne of ROM ore, in kilograms.

    The measure a Safeguard baseline is built on, so a step change in it is
    either a real change in how the operation runs or a fault in one of the
    two series underneath it.
    """
    dated = with_year(frame, year_type)
    held = [column for column in scope_columns if column in dated.columns]
    if not held:
        return pd.Series(dtype=float)
    tonnes = dated.groupby('_yr')[held].sum().sum(axis=1)
    ore = annual(dated, rom_mined, year_type)
    if ore.empty:
        return pd.Series(dtype=float)
    result = tonnes.reindex(ore.index) / ore * 1000.0
    return result.replace([np.inf, -np.inf], np.nan).dropna()


# ---------------------------------------------------------------------
# AGAINST THE PLAN
# ---------------------------------------------------------------------

def _band(value, target, tolerance):
    """Where a value sits against a target, as a proportion out."""
    if target in (None, 0) or value is None or pd.isna(value):
        return None
    return (float(value) - float(target)) / float(target)


def _verdict(drift, tolerance):
    if drift is None:
        return 'unknown'
    if abs(drift) <= tolerance:
        return 'agrees'
    if abs(drift) <= tolerance * 2:
        return 'drifting'
    return 'disagrees'


def plan_checks(frame, year_type='CY'):
    """Every physical measure against what the plan says it should be.

    One row per check: what the data says, what the plan says, how far apart
    they are and whether that is within tolerance.  A check the plan does not
    cover is reported as unknown rather than passed, because a check that
    silently passes when it cannot run is worse than no check.
    """
    # The plan, as the loader parsed it.  Attributes rather than a
    # mapping, so a key the file does not carry is an empty dict and not
    # an exception on a page whose job is to report problems.
    totals = LOM.lom_totals or {}
    plant = LOM.plant or {}
    rows = []

    dated = with_year(frame, year_type)
    milled = annual(dated, milling, year_type)
    crushed = annual(dated, crushing, year_type)
    ore = annual(dated, rom_mined, year_type)

    # Head grade against the plan's ore grade.
    grade = head_grade(dated, year_type)
    measured = float(grade.mean()) if not grade.empty else None
    planned = totals.get('ore_grade_gpt')
    drift = _band(measured, planned, HEAD_GRADE_TOLERANCE)
    rows.append({
        'Check': 'Mill head grade',
        'Measured': measured, 'Planned': planned, 'Unit': 'g/t',
        'Drift': drift, 'Tolerance': HEAD_GRADE_TOLERANCE,
        'Verdict': _verdict(drift, HEAD_GRADE_TOLERANCE),
        'Means': 'Contained gold over milled tonnes.  A large drift is a '
                 'unit error before it is a geology result.'})

    # Recovery against the plan, cumulatively.  An annual ratio of these two
    # series is a timing artefact and not a recovery; see recovery_overall.
    measured = recovery_overall(dated, year_type)
    planned = (float(totals['metallurgical_recovery']) * 100.0
               if totals.get('metallurgical_recovery') is not None else None)
    drift = _band(measured, planned, RECOVERY_TOLERANCE)
    rows.append({
        'Check': 'Metallurgical recovery',
        'Measured': measured, 'Planned': planned, 'Unit': '%',
        'Drift': drift, 'Tolerance': RECOVERY_TOLERANCE,
        'Verdict': _verdict(drift, RECOVERY_TOLERANCE),
        'Means': 'All gold poured over all gold contained, across the life.  '
                 'Annually the two are not the same gold.'})

    # How well the two gold series align, which is a different question from
    # what the recovery is.
    milled_years = annual(dated, contained_gold, year_type)
    odd = implausible_recovery(dated, year_type)
    share = (len(odd) / len(milled_years)) if len(milled_years) else None
    rows.append({
        'Check': 'Gold series alignment',
        'Measured': (round(share * 100.0, 1) if share is not None else None),
        'Planned': 20.0, 'Unit': '% of years',
        'Drift': (_band(share * 100.0, 20.0, 1.0) if share is not None
                  else None),
        'Tolerance': 1.0,
        'Verdict': ('agrees' if share is not None and share <= 0.2
                    else 'drifting' if share is not None and share <= 0.4
                    else 'disagrees' if share is not None else 'unknown'),
        'Means': 'Years whose poured over contained ratio cannot be a '
                 'recovery.  A few is the shoulder of the mine life.  Most '
                 'of them means the two series are keyed differently.'})

    # Throughput against what the plant can do.  A year above nameplate is
    # not an achievement, it is a data fault.
    peak = float(milled.max()) / TONNES_PER_MEGATONNE if not milled.empty else None
    capacity = plant.get('mill_nameplate_mtpa')
    drift = _band(peak, capacity, THROUGHPUT_TOLERANCE)
    rows.append({
        'Check': 'Peak milling against nameplate',
        'Measured': peak, 'Planned': capacity, 'Unit': 'Mtpa',
        'Drift': drift, 'Tolerance': THROUGHPUT_TOLERANCE,
        'Verdict': ('disagrees' if drift is not None and drift > THROUGHPUT_TOLERANCE
                    else _verdict(0.0 if drift is not None else None,
                                  THROUGHPUT_TOLERANCE)),
        'Means': 'The busiest year the model projects, against what the mill '
                 'is rated to do.  Above nameplate is a fault.'})

    peak = float(crushed.max()) / TONNES_PER_MEGATONNE if not crushed.empty else None
    capacity = plant.get('crushing_capacity_mtpa')
    drift = _band(peak, capacity, THROUGHPUT_TOLERANCE)
    rows.append({
        'Check': 'Peak crushing against capacity',
        'Measured': peak, 'Planned': capacity, 'Unit': 'Mtpa',
        'Drift': drift, 'Tolerance': THROUGHPUT_TOLERANCE,
        'Verdict': ('disagrees' if drift is not None and drift > THROUGHPUT_TOLERANCE
                    else _verdict(0.0 if drift is not None else None,
                                  THROUGHPUT_TOLERANCE)),
        'Means': 'The busiest year against the crusher rating.'})

    # The whole life, against the whole plan.
    mined = float(ore.sum()) / TONNES_PER_MEGATONNE if not ore.empty else None
    planned = totals.get('ore_mined_mt')
    drift = _band(mined, planned, GRADE_TOLERANCE)
    rows.append({
        'Check': 'Ore mined over the life',
        'Measured': mined, 'Planned': planned, 'Unit': 'Mt',
        'Drift': drift, 'Tolerance': GRADE_TOLERANCE,
        'Verdict': _verdict(drift, GRADE_TOLERANCE),
        'Means': 'Everything the model mines, against the reserve the plan '
                 'is built on.'})


    # Each consumption stream against the driver it should follow, rather
    # than against the plan.  A forecast can satisfy every check above and
    # still be internally inconsistent: diesel held flat while the pit winds
    # down is two individually plausible series whose ratio is not.
    #
    # The line is derived from the recorded months (driver_line), so the
    # forecast is held to what the operation has done rather than to a value
    # somebody typed.  This reports and changes nothing: the quantities are
    # written upstream and read here as they arrive.
    for spec in DRIVER_CHECKS:
        row = _driver_row(spec, dated)
        if row is not None:
            rows.append(row)

    # A stream that runs for a different span than the ore it belongs to.
    spans = continuity(dated, year_type)
    gapped = spans[(spans['Gaps'] > 0) | (spans['Overrun'] > 0)]
    said = []
    for row in gapped.itertuples():
        said.append(f'{row.Stream}: {row.Note}')
    rows.append({
        'Check': 'Streams as expected',
        'Measured': int(len(spans) - len(gapped)), 'Planned': int(len(spans)),
        'Unit': 'streams', 'Drift': None, 'Tolerance': 0.0,
        'Verdict': 'agrees' if gapped.empty else 'disagrees',
        'Means': ('Every activity stream runs as expected.' if gapped.empty
                  else '  '.join(said) + '  A stream that stops mid life '
                       'takes its emissions with it, and one that runs past '
                       'its end carries emissions that will not happen.  '
                       'Correct the forecast in PrepData, or the stated '
                       'span under Streams on the Assumptions page.')})

    frame_out = pd.DataFrame(rows)
    frame_out['Plan'] = LOM.plan_name
    return frame_out


def continuity(frame, year_type='CY'):
    """Years where a stream that was running stops, or starts from nothing.

    A stream that ends mid-forecast is how a wind-down assumption fails
    quietly: the tonnes stop, the emissions stop with them, and the total
    looks like an abatement.

    A stream set as intermittent in streams.expected (ReferenceInputs.yaml)
    is not faulted for a gap, and a stream with a last_year is faulted for
    every year it runs past it.  Gaps and Overrun count only what is a fault.
    """
    from LoaderReference import load_settings
    expected = {str(item.get('name')): item for item in
                ((load_settings().get('streams', {}) or {})
                 .get('expected') or []) if isinstance(item, dict)}
    found = streams(frame, year_type)
    rows = []
    for name, series in found.items():
        setting = expected.get(name, {})
        intermittent = bool(setting.get('intermittent', False))
        try:
            last_year = int(setting.get('last_year'))
        except (TypeError, ValueError):
            last_year = None
        if series.empty:
            rows.append({'Stream': name, 'Years': 0, 'First': None,
                         'Last': None, 'Gaps': 0, 'Overrun': 0,
                         'Note': 'No data at all.'})
            continue
        years = [int(y) for y in series.index]
        span = set(range(min(years), max(years) + 1))
        gaps = sorted(span - set(years))
        past = sorted(y for y in years if last_year and y > last_year)
        notes = []
        if gaps:
            said = ', '.join(str(g) for g in gaps[:6])
            notes.append(f'No data in {said}, which is expected: set as '
                         f'intermittent.' if intermittent
                         else f'No data in {said}.')
        if past:
            notes.append(f'Runs to {max(past)}, past its stated last year '
                         f'{last_year}.')
        rows.append({
            'Stream': name, 'Years': len(years), 'First': min(years),
            'Last': max(years),
            'Gaps': 0 if intermittent else len(gaps),
            'Overrun': len(past),
            'Note': '  '.join(notes) or 'Runs without a break.'})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# UNIT SLIPS
# ---------------------------------------------------------------------
# A quantity recorded in kilograms under a tonne heading is a thousand times
# too big, and it still sums, still charts and still produces an emission.
# Nothing downstream can tell, because the unit on the row says tonnes.
# What gives it away is the stream itself: the same line, month after month,
# jumping by orders of magnitude when nothing on site changed that much.
#
# Each month of each stream is compared with that stream's typical (median)
# month.  A slip between the units in use on site is a factor of a thousand
# (kg and t, L and kL), so a hundredfold departure catches every one with a
# wide margin, while a mine winding down, a new ore source or a plant
# switching over moves a stream by tens at most and is left alone.
UNIT_SLIP_RATIO = 100.0

# Streams measured in a physical unit.  Stores and services are in counts
# and dollars, where a hundredfold month is a big order, not a unit slip.
_SLIP_ROWTYPES = ('consumption', 'fuel', 'production', 'electricity')


def unit_slips(frame, ratio=UNIT_SLIP_RATIO):
    """Streams with months a hundredfold away from their typical month.

    Actual and forecast are read together, after the forecast superseded by
    an actual is dropped, so a forecast built in the wrong unit shows against
    the record and the other way round.

    Returns one row per stream carrying any such month:
        Activity, SubActivity, UOM, Typical, Months, High, Low, From, To,
        Actual, Forecast
    where High and Low count months above and below, and Actual and Forecast
    count the flagged months in each dataset.
    """
    columns = ['Activity', 'SubActivity', 'UOM', 'Typical', 'Months', 'High',
               'Low', 'From', 'To', 'Actual', 'Forecast']
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    from CalcNga import dedupe_actual_over_budget
    work = dedupe_actual_over_budget(frame)
    measured = work['RowType'].astype(str).isin(_SLIP_ROWTYPES)
    if 'NGAFuel' in work.columns:
        measured |= work['NGAFuel'].astype(str).ne('')
    work = work[measured]
    # Only the operating years.  After processing ends every stream falls to
    # a rehabilitation trickle, a hundred times below its operating month by
    # design, and flagging each of those months buried anything real.
    if DEFAULT_END_PROCESSING_DATE is not None and 'Date' in work.columns:
        work = work[work['Date'] <= pd.Timestamp(DEFAULT_END_PROCESSING_DATE)]
    if work.empty:
        return pd.DataFrame(columns=columns)

    keys = ['Activity', 'SubActivity', 'UOM']
    monthly = (work.assign(**{k: work[k].astype(str) for k in keys},
                           DataSet=work['DataSet'].astype(str))
               .groupby(keys + ['Date'], observed=True)
               .agg(Quantity=('Quantity', 'sum'),
                    Actual=('DataSet', lambda d: (d == 'Actual').any()))
               .reset_index())
    monthly = monthly[monthly['Quantity'] > 0]
    if monthly.empty:
        return pd.DataFrame(columns=columns)
    monthly['Typical'] = monthly.groupby(keys)['Quantity'].transform('median')
    monthly['Ratio'] = monthly['Quantity'] / monthly['Typical']
    flagged = monthly[(monthly['Ratio'] >= ratio)
                      | (monthly['Ratio'] <= 1.0 / ratio)]
    if flagged.empty:
        return pd.DataFrame(columns=columns)

    found = flagged.groupby(keys).agg(
        Typical=('Typical', 'first'),
        Months=('Ratio', 'size'),
        High=('Ratio', lambda r: int((r >= ratio).sum())),
        Low=('Ratio', lambda r: int((r <= 1.0 / ratio).sum())),
        From=('Date', 'min'),
        To=('Date', 'max'),
        Actual=('Actual', 'sum'),
    ).reset_index()
    found['Actual'] = found['Actual'].astype(int)
    found['Forecast'] = found['Months'] - found['Actual']
    return found.sort_values('Months', ascending=False)[columns] \
        .reset_index(drop=True)
