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
                    PROCESS_POWER_SUBACTIVITIES)
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


def reclaim_tonnes(frame):
    return ((frame['Activity'] == 'Mining')
            & (frame['SubActivity'].astype(str).str.contains('Reclaim',
                                                             na=False)))


def tailings(frame):
    return _diesel(frame) & frame['CostCentre'].astype(str).isin(
        ['Tailings Disposal', 'NPE Dredge'])


def crushing(frame):
    # Crusher feed only.  The raw 'Ore Crushed' set carries both feed
    # throughput and product feed for every crusher, plus a parallel
    # beneficiation series in dry metric tonnes; summing them counts the same
    # tonnes two or three times.
    return ((frame['Activity'] == 'Crushing')
            & (frame['SubActivity'] == 'Ore Crushed')
            & (frame['Description'].astype(str)
               .str.contains('Feed Throughput', na=False)))


def crushed_tonnes(frame):
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


def gold_sold(frame):
    return ((frame['Activity'] == 'Revenue')
            & (frame['SubActivity'] == 'Gold Sold'))


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
    'TSF and tailings': tailings,
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
    drift = _band(measured, planned, GRADE_TOLERANCE)
    rows.append({
        'Check': 'Mill head grade',
        'Measured': measured, 'Planned': planned, 'Unit': 'g/t',
        'Drift': drift, 'Tolerance': GRADE_TOLERANCE,
        'Verdict': _verdict(drift, GRADE_TOLERANCE),
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


    # Two measures against each other, rather than against the plan.
    #
    # Every other check here compares one series to what the plan says it
    # should be, and a forecast can satisfy all of them and still be
    # internally inconsistent: diesel winding down with the fleet while
    # electricity holds flat is two individually plausible series whose
    # ratio is not.  A plant does not double its specific energy
    # consumption, so a year well away from the rest of the series is a
    # forecast that stopped reading the mill.
    #
    # This reports and changes nothing.  The quantity is written upstream
    # and is read here as it arrives.
    power = annual(dated, process_power, year_type)
    together = pd.concat([power.rename('kWh'), milled.rename('t')], axis=1)
    together = together.dropna()
    together = together[together['t'] > 0]
    if len(together) >= 3:
        rate = together['kWh'] / together['t']
        settled = float(rate.median())
        apart = (rate - settled).abs() / settled
        adrift = apart[apart > POWER_INTENSITY_TOLERANCE].sort_values()
        worst = rate.loc[adrift.index[-1]] if len(adrift) else settled
        rows.append({
            'Check': 'Power against tonnes milled',
            'Measured': round(float(worst), 1),
            'Planned': round(settled, 1), 'Unit': 'kWh per t',
            'Drift': _band(worst, settled, POWER_INTENSITY_TOLERANCE),
            'Tolerance': POWER_INTENSITY_TOLERANCE,
            'Verdict': 'agrees' if adrift.empty else 'disagrees',
            'Means': ('Every year draws power in step with what it milled.'
                      if adrift.empty else
                      'Out of step in %s.  A plant does not change its '
                      'energy per tonne by this much, so the power for '
                      'those years is not following the mill, and the '
                      'Scope 2 that rests on it is wrong.'
                      % ', '.join(str(int(y)) for y in adrift.index))})

    # A stream that runs for a different span than the ore it belongs to.
    spans = continuity(dated, year_type)
    gapped = spans[spans['Gaps'] > 0]
    rows.append({
        'Check': 'Streams without gaps',
        'Measured': int(len(spans) - len(gapped)), 'Planned': int(len(spans)),
        'Unit': 'streams', 'Drift': None, 'Tolerance': 0.0,
        'Verdict': 'agrees' if gapped.empty else 'disagrees',
        'Means': ('Every activity stream runs without a break.' if gapped.empty
                  else 'Gaps in: %s.  A stream that stops mid life takes its '
                       'emissions with it and the total reads as an '
                       'abatement.' % ', '.join(gapped['Stream']))})

    frame_out = pd.DataFrame(rows)
    frame_out['Plan'] = LOM.plan_name
    return frame_out


def continuity(frame, year_type='CY'):
    """Years where a stream that was running stops, or starts from nothing.

    A stream that ends mid-forecast is how a wind-down assumption fails
    quietly: the tonnes stop, the emissions stop with them, and the total
    looks like an abatement.
    """
    found = streams(frame, year_type)
    rows = []
    for name, series in found.items():
        if series.empty:
            rows.append({'Stream': name, 'Years': 0, 'First': None,
                         'Last': None, 'Gaps': 0,
                         'Note': 'No data at all.'})
            continue
        years = [int(y) for y in series.index]
        span = set(range(min(years), max(years) + 1))
        gaps = sorted(span - set(years))
        rows.append({
            'Stream': name, 'Years': len(years), 'First': min(years),
            'Last': max(years), 'Gaps': len(gaps),
            'Note': ('Runs without a break.' if not gaps
                     else 'No data in %s.' % ', '.join(str(g) for g in gaps[:6]))})
    return pd.DataFrame(rows)
