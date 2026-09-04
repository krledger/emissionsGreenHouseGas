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
REFERENCE_DIR = os.path.join(ROOT, 'Scope3')
OUT_DIR = os.path.join(ROOT, 'Out')
DOCS_DIR = os.path.join(ROOT, 'Documentation')
TO_DELETE_DIR = os.path.join(ROOT, '_ToDelete_')
NGA_SOURCE_DIR = os.path.join(DATA_DIR, 'NgaSource')


def data(*parts):
    """A path inside Data."""
    return os.path.join(DATA_DIR, *parts)


def reference(*parts):
    """A path inside the reference tables."""
    return os.path.join(REFERENCE_DIR, *parts)


def out(*parts):
    """A path inside the output folder."""
    return os.path.join(OUT_DIR, *parts)
