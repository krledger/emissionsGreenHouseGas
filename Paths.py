"""Where the repository is, and where its data lives.

Every module asks here rather than deriving a path from its own location.  A
module that computes its data folder from __file__ silently changes what it
reads the moment it is moved into a package, and the failure is a file not
found rather than a wrong figure, which is the only mercy in it.

ROOT is resolved from this module's position, so it holds wherever the
repository is checked out and whatever the working directory happens to be
when Streamlit starts.
"""

import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, 'Data')
REFERENCE_DIR = os.path.join(ROOT, 'Reference')
DOCS_DIR = os.path.join(ROOT, 'Documentation')
TO_DELETE_DIR = os.path.join(ROOT, '_ToDelete_')
# The publications the factors are imported from, kept beside the data
# they produced so a factor can always be traced back to its edition.
NGA_SOURCE_DIR = os.path.join(DATA_DIR, 'NgaSource')
SPEND_SOURCE_DIR = os.path.join(DATA_DIR, 'SpendBasedSource')


# ---------------------------------------------------------------------
# PREPDATA
# ---------------------------------------------------------------------
# The operational data and the two reference files that come with it are
# read where PrepData writes them, not from a copy.  PrepData rebuilds its
# outputs on every run, and a copy distributed into Data is only ever as
# current as the last time somebody sent it.
#
# PrepData sits beside this repository.  Where it does not, as on a deployed
# copy of the reporting application, the files are read from Data under the
# names they were distributed as.  One rule for all four, decided by whether
# the PrepData folder is there, so the two locations are never mixed within
# one build.  source_label() says which is in use.
PREPDATA_DIR = os.path.join(os.path.dirname(ROOT), 'PrepData')

# key: (PrepData folder, PrepData name, name when distributed into Data)
PREPDATA_SOURCES = {
    'actual':   ('Outputs', 'ActivityActual.csv', 'OperationsMetricsActual.csv'),
    'forecast': ('Outputs', 'ActivityForecast.csv', 'OperationsMetricsBudget.csv'),
    'lom':      ('Reference', 'ReferenceLifeOfMine.yaml', 'LOM.yaml'),
    'fx':       ('Reference', 'ReferenceFx.csv', 'ReferenceFx.csv'),
}


def prepdata_present():
    """True where PrepData's outputs folder sits beside this repository."""
    return os.path.isdir(os.path.join(PREPDATA_DIR, 'Outputs'))


def source(key):
    """The file PrepData supplies under this key, where it is read from."""
    folder, name, distributed = PREPDATA_SOURCES[key]
    if prepdata_present():
        return os.path.join(PREPDATA_DIR, folder, name)
    return os.path.join(DATA_DIR, distributed)


def source_for_name(name):
    """The same, looked up by the name a caller has always asked for."""
    for key, (_, current, distributed) in PREPDATA_SOURCES.items():
        if name in (current, distributed):
            return source(key)
    return os.path.join(DATA_DIR, name)


def source_label():
    """Where the operational data is being read from, in words."""
    if prepdata_present():
        return f'PrepData outputs, {PREPDATA_DIR}'
    return f'distributed copies in {DATA_DIR}'


def data(*parts):
    """A path inside Data."""
    return os.path.join(DATA_DIR, *parts)


def reference(*parts):
    """A path inside the reference tables."""
    return os.path.join(REFERENCE_DIR, *parts)


