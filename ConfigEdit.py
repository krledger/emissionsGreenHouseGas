"""Editing a hand-maintained configuration file without destroying it.

`ReferenceInputs.yaml` is maintained by people as much as by this application.
It carries a hundred and eighty comment lines explaining why each assumption
is what it is, and that explanation is the greater part of its value: a factor
a reader cannot trace is a factor they cannot check.

Serialising a parsed document back over the file destroys all of it.  Comments
are not part of the parsed structure, so a round trip through the parser drops
every one, reorders what is left, and rewrites the file in a shape the people
who maintain it would not recognise.

So this module does not serialise.  It finds the line carrying the value and
changes that line.  Everything else in the file is byte for byte what it was,
which is the only honest way to let a form edit a document somebody else
writes.

Two further rules, both learned the hard way:

    Never truncate before you have something to write.  Opening the file for
    writing empties it, so a failure between the open and the write leaves
    nothing at all.  The new text is written beside the file and moved over
    it, so the file is either the old one or the new one and never empty.

    Never hand a numpy value to a serialiser.  A number out of a data editor
    is a numpy scalar, which no YAML dumper will accept, and the failure
    arrives after the file has been emptied.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime

__all__ = ['set_values', 'plain', 'format_scalar', 'HistoryError']


class HistoryError(RuntimeError):
    """A value could not be located in the file, so nothing was written."""


def plain(value):
    """A python scalar a YAML file can carry.

    Numpy scalars arrive from data editors and from pandas; they serialise as
    opaque objects or not at all.  Converted here, once, so nothing further
    down has to know where the value came from.
    """
    if value is None:
        return None
    if hasattr(value, 'item'):                   # numpy scalar
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def format_scalar(value):
    """A scalar as YAML writes it."""
    value = plain(value)
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    # Quote anything that would otherwise read as structure rather than text.
    if text == '' or re.search(r'^[\s>|*&!%@`\-?{\[]|:\s|\s#|["\']', text):
        return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return text


# ---------------------------------------------------------------------
# LOCATING A VALUE
# ---------------------------------------------------------------------

def _indent(line):
    return len(line) - len(line.lstrip())


def _is_content(line):
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith('#')


def _block_end(lines, start, indent):
    """Where the block opened at `start` ends."""
    for index in range(start + 1, len(lines)):
        if _is_content(lines[index]) and _indent(lines[index]) <= indent:
            return index
    return len(lines)


def _find_key(lines, start, end, key):
    """The line carrying `key:` at the shallowest indent in the window."""
    pattern = re.compile(r'^(\s*)(-\s+)?' + re.escape(key) + r'\s*:')
    best, best_indent = None, None
    for index in range(start, end):
        line = lines[index]
        if not _is_content(line):
            continue
        match = pattern.match(line)
        if not match:
            continue
        indent = _indent(line)
        if best_indent is None or indent < best_indent:
            best, best_indent = index, indent
    return best


def _find_named_item(lines, start, end, name):
    """The block of a list entry whose `name:` matches.

    Legs and streams are identified by their name rather than their position,
    so reordering the file does not send an edit to the wrong leg.
    """
    pattern = re.compile(r'^(\s*)-?\s*name\s*:\s*(.+?)\s*$')
    for index in range(start, end):
        if not _is_content(lines[index]):
            continue
        match = pattern.match(lines[index])
        if not match:
            continue
        value = match.group(2).strip().strip('"\'')
        if value != str(name).strip():
            continue
        # The entry runs until the next line at or shallower than the dash
        # that opened it.
        opener = _indent(lines[index])
        for tail in range(index + 1, end):
            if _is_content(lines[tail]) and (
                    _indent(lines[tail]) < opener
                    or lines[tail].lstrip().startswith('- ')):
                return index, tail
        return index, end
    return None


def locate(lines, path):
    """The index of the line carrying the value at `path`, or None.

    Path segments are mapping keys, except where a segment names an entry in
    a list of mappings, which is matched on that entry's own name.
    """
    start, end = 0, len(lines)
    for position, segment in enumerate(path):
        segment = str(segment)
        last = position == len(path) - 1
        if segment == '':
            continue                              # an unnamed container
        index = _find_key(lines, start, end, segment)
        if index is not None:
            if last:
                return index
            start, end = index + 1, _block_end(lines, index, _indent(
                lines[index]))
            continue
        # Not a key here: it may name an entry in a list.
        found = _find_named_item(lines, start, end, segment)
        if found is None:
            return None
        start, end = found
    return None


# ---------------------------------------------------------------------
# WRITING
# ---------------------------------------------------------------------

_VALUE_LINE = re.compile(r'^(?P<lead>\s*(?:-\s+)?[^:#]+:\s*)'
                         r'(?P<value>.*?)'
                         r'(?P<comment>\s+#.*)?$')


def _rewrite_line(line, value):
    """Replace the scalar on a line, keeping its key, indent and comment."""
    match = _VALUE_LINE.match(line.rstrip('\n'))
    if match is None:
        raise HistoryError(f'Cannot read the value on line: {line!r}')
    return (match.group('lead') + format_scalar(value)
            + (match.group('comment') or '') + '\n')


def current_value(lines, path):
    """The scalar at `path` as written, for the history record."""
    index = locate(lines, path)
    if index is None:
        return None
    match = _VALUE_LINE.match(lines[index].rstrip('\n'))
    return match.group('value').strip() if match else None


def set_values(path_to_file, changes, history_path=None, author=''):
    """Apply edits to the file, and record what changed.

    Args:
        path_to_file: the configuration file.
        changes:      iterable of (path, value) where path is a list of
                      segments, as `locate` reads them.
        history_path: where to append the record of the change.
        author:       who made it.

    Returns:
        The list of records written.

    Raises:
        HistoryError where any value cannot be located.  Nothing is written
        in that case: a partial edit of a configuration is worse than none,
        because it is harder to notice.
    """
    with open(path_to_file, encoding='utf-8') as handle:
        lines = handle.readlines()

    records, edited = [], list(lines)
    for path, value in changes:
        index = locate(edited, path)
        if index is None:
            raise HistoryError(
                f"'{'.'.join(str(p) for p in path)}' is not in "
                f'{os.path.basename(path_to_file)}.  Nothing was written.')
        before = current_value(edited, path)
        edited[index] = _rewrite_line(edited[index], value)
        records.append({
            'ChangedAt': datetime.now().isoformat(timespec='seconds'),
            'ChangedBy': author or os.environ.get('USER', 'unknown'),
            'File': os.path.basename(path_to_file),
            'Path': '.'.join(str(p) for p in path if str(p) != ''),
            'From': before,
            'To': format_scalar(value),
        })

    # Write beside the file and move it over, so the file is either the old
    # one or the new one and never a half written one.
    temporary = path_to_file + '.writing'
    with open(temporary, 'w', encoding='utf-8') as handle:
        handle.writelines(edited)
    shutil.copystat(path_to_file, temporary)
    os.replace(temporary, path_to_file)

    if history_path and records:
        append_history(history_path, records)
    return records


HISTORY_COLUMNS = ['ChangedAt', 'ChangedBy', 'File', 'Path', 'From', 'To',
                   'Note']


def append_history(history_path, records, note=''):
    """Append change records, creating the log where it does not exist."""
    import csv
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    exists = os.path.exists(history_path)
    with open(history_path, 'a', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        if not exists:
            writer.writeheader()
        for record in records:
            row = {column: record.get(column, '') for column in
                   HISTORY_COLUMNS}
            row['Note'] = record.get('Note', note)
            writer.writerow(row)
    return history_path


def read_history(history_path):
    """The change log, newest first, or an empty frame."""
    import pandas as pd
    if not os.path.exists(history_path):
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    frame = pd.read_csv(history_path)
    return frame.sort_values('ChangedAt', ascending=False).reset_index(
        drop=True)
