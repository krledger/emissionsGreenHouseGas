"""Scope 3 position, category by category, and the assumptions behind it.

Every one of the fifteen categories has an explicit position.  A category
without a figure is not silent: it says whether it is excluded by
determination, not applicable as a matter of fact, or outstanding because a
number has not been obtained yet.  The three are different and a reader is
entitled to know which one applies.

    Calculated       a figure, from transactions or physicals
    Estimated        a figure, from a stated assumption rather than a record
    Outstanding      applies, no figure yet, and the reason is recorded
    Excluded         considered and excluded, with the reason
    Not applicable   does not arise for this operation
"""

from __future__ import annotations

import pandas as pd

from CalcGhgCategories import CATEGORY_NAMES

__all__ = ['CATEGORY_STATUSES', 'category_status', 'assumption_rows']

CATEGORY_STATUSES = ('Calculated', 'Estimated', 'Outstanding', 'Excluded',
                     'Not applicable')

# A category the operation does not have, as distinct from one considered and
# excluded on materiality or boundary grounds.  Both are stated; only the
# reason differs.
NOT_APPLICABLE = {11, 12, 13, 14, 15}


def category_status(result, reference):
    """One row per category: position, basis, tonnes and what is outstanding.

    Args:
        result:    Scope3Result from CalcGhgCategories.build_scope3, or None.
        reference: Scope3Reference, for the configuration and exclusions.

    Returns:
        DataFrame with fifteen rows, in category order.
    """
    config = getattr(reference, 'config', {}) or {}
    detail = getattr(result, 'detail', None)
    outstanding = pd.DataFrame(getattr(result, 'outstanding', None) or [])

    # Exclusions arrive as a frame of category and rationale.  Reduced to a
    # mapping here so the loop below asks one question of it.
    excluded_frame = getattr(result, 'exclusions', None)
    exclusions = {}
    if isinstance(excluded_frame, pd.DataFrame) and not excluded_frame.empty:
        exclusions = dict(zip(
            pd.to_numeric(excluded_frame['Category'],
                          errors='coerce').dropna().astype(int),
            excluded_frame['Rationale'].astype(str)))
    elif isinstance(excluded_frame, dict):
        exclusions = {int(k): str(v) for k, v in excluded_frame.items()}

    totals, methods, bases, estimated = {}, {}, {}, set()
    if detail is not None and not detail.empty:
        numeric = pd.to_numeric(detail['Category'], errors='coerce')
        grouped = detail.assign(_cat=numeric).groupby('_cat', observed=True)
        totals = grouped['tCO2e'].sum().to_dict()
        methods = grouped['Method'].first().to_dict()
        bases = grouped['Basis'].first().to_dict()
        # A line the build produced from a stated assumption rather than from
        # a recorded transaction marks the whole category as estimated.
        marked = detail[~detail['DataSet'].astype(str).str.lower()
                        .isin(['actual', 'budget'])]
        estimated = set(pd.to_numeric(marked['Category'],
                                      errors='coerce').dropna().astype(int))

    rows = []
    for number in range(1, 16):
        settings = config.get(f'category_{number}', {}) or {}
        tonnes = float(totals.get(number, 0.0) or 0.0)
        open_items = (outstanding[outstanding['Category'] == number]
                      if (not outstanding.empty
                          and 'Category' in outstanding.columns)
                      else pd.DataFrame())

        if number in exclusions or settings.get('applies') is False:
            status = ('Not applicable' if number in NOT_APPLICABLE
                      else 'Excluded')
            reason = str(exclusions.get(number, '')) or \
                str(settings.get('exclusion_reason', ''))
        elif tonnes > 0:
            status = 'Estimated' if number in estimated else 'Calculated'
            reason = ''
        else:
            status = 'Outstanding'
            reason = ('; '.join(open_items['Item'].astype(str))
                      if not open_items.empty
                      else 'Applies, no figure obtained')

        rows.append({
            'Category': number,
            'Name': CATEGORY_NAMES.get(number, ''),
            'Status': status,
            'ActualBasis': str(settings.get('method', '')) or str(
                bases.get(number, '')),
            'ForecastBasis': str(settings.get('forecast_basis', ''))
                             or str(settings.get('scale_to_subactivity', ''))
                             or ('Fitted unit rate on the operational driver'
                                 if tonnes > 0 else ''),
            'tCO2e': round(tonnes, 2),
            'OpenItems': int(len(open_items)),
            'Reason': reason,
            'Method': str(methods.get(number, '')),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# ASSUMPTIONS
# ---------------------------------------------------------------------
# A user-maintained assumption belongs in the configuration file, not in a
# Python constant.  These two functions are the whole of the contract: the
# Builder shows what is editable and writes it back, and nothing else in the
# program needs to know an assumption was changed.

# Scalars a user maintains, by category, with the unit they are stated in.
# Anything not listed here is methodology and is changed by editing the file
# deliberately, not through a form.
EDITABLE = {
    6: [('air_legs', 'sectors_per_week', 'sectors per week'),
        ('air_legs', 'km_per_sector', 'km'),
        ('air_legs', 'factor_kgco2e_per_pkm', 'kg CO2-e per passenger km')],
    7: [('roster', 'workforce_headcount', 'people'),
        ('roster', 'return_trips_per_person_per_year', 'trips per year'),
        ('roster', 'occupancy', 'people per vehicle'),
        ('roster', 'factor_kgco2e_per_km', 'kg CO2-e per km')],
    5: [('streams', 'tonnes_per_year', 't per year'),
        ('streams', 'factor_tco2e_per_t', 't CO2-e per t')],
    10: [(None, 'refining_intensity_kgco2e_per_kg_au',
          'kg CO2-e per kg gold')],
}


def assumption_rows(config):
    """Every user-maintained assumption in force, flattened for review.

    Returned as data rather than rendered, so the same rows can be shown in
    the Builder, written to EmissionsAssumptions.csv beside a published
    build, and compared between builds.
    """
    rows = []
    for number, fields in sorted(EDITABLE.items()):
        settings = (config or {}).get(f'category_{number}', {}) or {}
        for container, key, unit in fields:
            if container is None:
                rows.append({
                    'Category': number, 'Group': '', 'Parameter': key,
                    'Value': settings.get(key), 'Unit': unit,
                    'Path': f'category_{number}.{key}',
                    'Source': str(settings.get('factor_source', '')),
                })
                continue
            block = settings.get(container)
            if isinstance(block, dict):
                block = [block]
            for item in (block or []):
                if not isinstance(item, dict) or key not in item:
                    continue
                rows.append({
                    'Category': number,
                    'Group': str(item.get('name', container)),
                    'Parameter': key, 'Value': item.get(key), 'Unit': unit,
                    'Path': f'category_{number}.{container}.'
                            f"{item.get('name', '')}.{key}",
                    'Source': str(item.get('factor_source', '')),
                })
            # A roster is a mapping rather than a list of legs.
            if isinstance(settings.get(container), dict) and \
                    key in settings[container] and not rows[-1:]:
                pass
    return pd.DataFrame(rows)

