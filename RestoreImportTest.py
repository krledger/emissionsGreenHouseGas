"""Put the operations file back the way it was, and run the test again.

    python3 RestoreImportTest.py            put the original back
    python3 RestoreImportTest.py --check    say what differs, change nothing

The backup is taken once, the first time the test file is built, and is never
overwritten afterwards.  That matters: a restore that quietly re-backed-up a
corrupted file would leave nothing to restore from, and the first test would
be the last one anybody could run.
"""
import argparse
import hashlib
import os
import shutil
import sys

import Paths

LIVE = Paths.data('OperationsMetricsActual.csv')
BACKUP = Paths.data('ImportTest', 'OperationsMetricsActual.original.csv')


def digest(path):
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='report only, change nothing')
    arguments = parser.parse_args()

    if not os.path.exists(BACKUP):
        print('No backup at %s.  Nothing to restore from.' % BACKUP)
        return 1

    live, kept = digest(LIVE), digest(BACKUP)
    live_rows = sum(1 for _ in open(LIVE, encoding='utf-8')) - 1
    kept_rows = sum(1 for _ in open(BACKUP, encoding='utf-8')) - 1

    print('live    %s  %6d rows  %s' % (live, live_rows, LIVE))
    print('backup  %s  %6d rows  %s' % (kept, kept_rows, BACKUP))

    if live == kept:
        print('\nAlready identical.  Nothing to do.')
        return 0

    if arguments.check:
        print('\nThey differ by %d rows.  Run without --check to put the '
              'original back.' % (live_rows - kept_rows))
        return 0

    shutil.copy2(BACKUP, LIVE)
    print('\nRestored.  %s is the file as it was before any import test.'
          % LIVE)
    print('Press Rebuild in the Builder to clear the cached build.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
