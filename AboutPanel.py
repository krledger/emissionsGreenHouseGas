"""Portable About panel for Streamlit applications.

Drop this file beside any Streamlit app, then::

    from AboutPanel import render_about

    with tab_about:
        render_about(
            app_name="My Application",
            changelog="Changelog.md",
            description="One line on what the application does.",
        )

It renders an application header, a browsable release history parsed from a
markdown changelog, a search box across that history, optional links to
supporting documents and an optional environment section.

Supporting documents open in a modal reader rather than downloading, so a
method statement or a design note can be read next to the numbers it governs.
Markdown and plain text render in place; anything else falls back to a
download button, and a download is always offered alongside the reader.

Nothing here knows anything about the host application.  The only hard
dependency is Streamlit; everything else is the standard library.

Changelog format
----------------
Releases are ``## `` headings.  The heading is parsed for a version and a date
so the picker can be ordered and labelled, and the following formats are all
understood::

    ## 2026-09-01
    ## [1.4.0] - 2026-09-01
    ## v1.4.0 (2026-09-01)
    ## Unreleased

Anything that does not match still renders; it simply carries no version or
date.  Content between headings is passed through as markdown untouched.

Release status
--------------
A release block may open with a status line::

    **Status:** Released 30 July 2026
    **Status:** Unreleased, after the 30 July 2026 release

The word after "Status:" decides how the block reads.  A block whose status
begins with "Unreleased" is work that is in the code and not in a formal
release, and the panel says so at the top: without that, a reader seeing a bug
fixed on a date they never received has no way to tell whether their build
carries it.  A block with no status line is treated as released, which is the
safe reading for a history written before the convention existed.

A block may also carry an impact line::

    **Impact:** None.  No released build carries this change.
    **Impact:** Figures move.  Recalculate anything issued since 19 August.

A defect entry states what went wrong, which reads as an incident whether or
not it ever reached a released build.  The impact line answers the question
that actually matters to the reader, and the panel puts it above the detail
rather than leaving it to be found at the end.
"""

from __future__ import annotations

import platform
import re
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

__all__ = ["render_about", "parse_changelog", "read_document", "Release"]

_DATE_PATTERNS = (
    "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y",
    "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
)
_VERSION_RE = re.compile(r"\[?v?(\d+(?:\.\d+){0,3}[A-Za-z0-9.\-]*)\]?")
_STATUS_RE = re.compile(r"^\s*\*\*Status:\*\*\s*(.+?)\s*$", re.MULTILINE)
# The impact runs to the end of its paragraph, which may wrap over several lines.
_IMPACT_RE = re.compile(r"^\s*\*\*Impact:\*\*\s*(.+?)\s*(?:\n\s*\n|\Z)",
                        re.MULTILINE | re.DOTALL)
_DATE_RE = re.compile(
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"
    r"|(\d{1,2}[-/]\d{1,2}[-/]\d{4})"
    r"|(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"
    r"|([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})"
)

# Extensions the reader can render in place.  Anything else is offered as a
# download only, because rendering a binary in a dialog helps nobody.
_READABLE = {".md", ".markdown", ".txt", ".yaml", ".yml", ".json", ".csv"}
_CODE_LANGUAGE = {".yaml": "yaml", ".yml": "yaml", ".json": "json"}


class Release:
    """One release block from a changelog."""

    __slots__ = ("heading", "version", "date", "body", "status", "impact")

    def __init__(self, heading: str, version: str | None,
                 date: datetime | None, body: str, status: str = "",
                 impact: str = ""):
        self.heading = heading
        self.version = version
        self.date = date
        self.body = body
        self.status = status
        self.impact = impact

    @property
    def released(self) -> bool:
        """False only where the block says it is unreleased."""
        return not self.status.strip().lower().startswith("unreleased")

    @property
    def label(self) -> str:
        """Short label for a picker, preferring version then date."""
        if self.version and self.date:
            base = f"{self.version} — {self.date:%d %B %Y}"
        elif self.version:
            base = self.version
        elif self.date:
            base = f"{self.date:%d %B %Y}"
        else:
            base = self.heading
        return base if self.released else f"{base}  ·  unreleased"

    @property
    def summary(self) -> str:
        """First subsection heading, or the first non-empty line."""
        for line in self.body.splitlines():
            stripped = line.strip()
            if stripped.startswith("###"):
                return stripped.lstrip("# ").strip()
            if stripped and not stripped.startswith(("-", "*", ">")):
                return stripped
        return ""

    @property
    def no_impact(self) -> bool:
        """True where the impact line says nothing reached a released build."""
        return self.impact.strip().lower().startswith(("none", "no impact", "nil"))

    def __repr__(self) -> str:
        return f"Release({self.label!r})"


def _parse_date(text: str):
    match = _DATE_RE.search(text)
    if not match:
        return None
    raw = next(g for g in match.groups() if g)
    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(raw.replace("/", "-")
                                     if "-" in pattern else raw, pattern)
        except ValueError:
            continue
    return None


def _parse_version(text: str, date_text: str | None):
    candidate = text
    if date_text:
        candidate = candidate.replace(date_text, " ")
    match = _VERSION_RE.search(candidate)
    if not match:
        return None
    value = match.group(1)
    # A bare four digit number is a year, not a version.
    if re.fullmatch(r"\d{4}", value):
        return None
    return value


def parse_changelog(text: str) -> list[Release]:
    """Split changelog markdown into releases, newest first as written.

    The preamble before the first ``## `` heading is discarded, since it is
    normally a title and a note on the format rather than release content.
    """
    releases: list[Release] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush():
        if heading is None:
            return
        date = _parse_date(heading)
        date_match = _DATE_RE.search(heading)
        version = _parse_version(heading, date_match.group(0) if date_match else None)
        body = "\n".join(buffer).strip()
        status_match = _STATUS_RE.search(body)
        status = status_match.group(1) if status_match else ""
        impact_match = _IMPACT_RE.search(body)
        impact = " ".join(impact_match.group(1).split()) if impact_match else ""
        # Status and impact are shown above the detail, so they are taken out
        # of it rather than repeated.
        for match in sorted((m for m in (status_match, impact_match) if m),
                            key=lambda m: m.start(), reverse=True):
            body = body[:match.start()] + body[match.end():]
        body = body.strip()
        releases.append(Release(heading, version, date, body, status, impact))

    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("###"):
            flush()
            heading = line[3:].strip()
            buffer = []
        elif heading is not None:
            buffer.append(line)
    flush()
    return releases


def _resolve(path) -> Path:
    """Absolute path, searched from the working directory then this module."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    for base in (Path.cwd(), Path(__file__).resolve().parent):
        if (base / candidate).exists():
            return base / candidate
    return candidate


def read_document(path) -> tuple[str | None, Path | None, str | None]:
    """Return (text, resolved path, error).  Binary files return no text."""
    if path is None:
        return None, None, None
    candidate = _resolve(path)
    if candidate.suffix.lower() not in _READABLE:
        return None, candidate, None
    try:
        return candidate.read_text(encoding="utf-8"), candidate, None
    except FileNotFoundError:
        return None, candidate, f"Not found: {candidate}"
    except UnicodeDecodeError:
        return None, candidate, f"Not readable as text: {candidate.name}"
    except Exception as exc:                     # pragma: no cover - defensive
        return None, candidate, f"Could not read {candidate}: {exc}"


def _highlight(body: str, term: str) -> str:
    if not term:
        return body
    return re.sub(re.escape(term), lambda m: f"**{m.group(0)}**", body,
                  flags=re.IGNORECASE)


# ---------------------------------------------------------------------
# DOCUMENT READER
# ---------------------------------------------------------------------

def _render_document_body(text: str, resolved: Path) -> None:
    """Render a document inside the reader, by extension."""
    suffix = resolved.suffix.lower()
    if suffix in (".md", ".markdown"):
        st.markdown(text)
    elif suffix in _CODE_LANGUAGE:
        st.code(text, language=_CODE_LANGUAGE[suffix])
    elif suffix == ".csv":
        st.code(text, language="text")
    else:
        st.text(text)


def _reader(label: str, resolved: Path, text: str | None, error: str | None,
            key: str) -> None:
    """Body of the modal reader.  Also offers the file itself."""
    st.markdown(f"#### {label}")
    st.caption(str(resolved))
    if error:
        st.warning(error)
    elif text is None:
        st.info("This document cannot be shown in the reader.  "
                "Download it to open it in its own application.")
    else:
        # Markdown renders by default.  The source view is there for a reader
        # who wants the file as written, and for anything the renderer
        # mangles.
        rendered = True
        if resolved.suffix.lower() in (".md", ".markdown"):
            rendered = st.radio(
                "View", ["Rendered", "Source"], horizontal=True,
                label_visibility="collapsed", key=f"{key}_view") == "Rendered"
        with st.container(height=520, border=False):
            if rendered:
                _render_document_body(text, resolved)
            else:
                st.code(text, language="markdown")
    if resolved.exists():
        st.download_button(
            f"Download {resolved.name}",
            data=resolved.read_bytes(),
            file_name=resolved.name,
            key=f"{key}_download",
            width="stretch",
        )


def _open_reader(label: str, resolved: Path, key: str) -> None:
    """Open the reader, as a dialog where Streamlit supports one."""
    text, resolved, error = read_document(resolved)

    dialog = getattr(st, "dialog", None)
    if dialog is None:                            # older Streamlit
        with st.expander(label, expanded=True):
            _reader(label, resolved, text, error, key)
        return

    @dialog(label, width="large")
    def _show():
        _reader(label, resolved, text, error, key)

    _show()


def _render_documents(documents, key_prefix: str) -> None:
    """A button per document, each opening the reader."""
    available = []
    for label, path in documents:
        resolved = _resolve(path)
        if resolved.exists():
            available.append((label, resolved))

    if not available:
        return

    st.markdown("**Documents**")
    columns = st.columns(min(len(available), 3))
    for index, (label, resolved) in enumerate(available):
        with columns[index % len(columns)]:
            if st.button(label, key=f"{key_prefix}_open_{index}",
                         width="stretch"):
                st.session_state[f"{key_prefix}_reading"] = index

    reading = st.session_state.get(f"{key_prefix}_reading")
    if reading is not None and reading < len(available):
        label, resolved = available[reading]
        _open_reader(label, resolved, f"{key_prefix}_doc_{reading}")
        st.session_state[f"{key_prefix}_reading"] = None


# ---------------------------------------------------------------------
# PANEL
# ---------------------------------------------------------------------

def render_about(app_name: str,
                 changelog=None,
                 description: str = "",
                 version: str | None = None,
                 documents=None,
                 facts=None,
                 show_environment: bool = True,
                 key_prefix: str = "about") -> None:
    """Render the About panel.

    Parameters
    ----------
    app_name
        Displayed as the heading.
    changelog
        Path to a markdown changelog, absolute or relative to the working
        directory or to this module.  Omit to render the panel without a
        release history.
    description
        One or two lines under the heading.
    version
        Overrides the version read from the changelog.
    documents
        Iterable of ``(label, path)``.  Each is offered as a button that opens
        the document in a reader, with a download inside it.
    facts
        Mapping of label to value, shown as a definition list.  Use it for
        anything the host application knows and this module cannot, such as
        the data file in use or the active configuration.
    show_environment
        Include the Python and Streamlit versions and the working directory.
    key_prefix
        Prefix for widget keys, so two panels can coexist in one app.
    """
    text, path, error = read_document(changelog)
    releases = parse_changelog(text) if text else []
    latest = releases[0] if releases else None

    shown_version = version or (latest.version if latest else None)
    header = f"### {app_name}"
    if shown_version:
        header += f"  ·  version {shown_version}"
    st.markdown(header)
    if description:
        st.caption(description)
    if latest and latest.date:
        st.caption(f"Last change {latest.date:%d %B %Y}"
                   + (f"  ·  {latest.summary}" if latest.summary else ""))

    # Work that is in the code and not in a formal release.  A reader seeing a
    # bug fixed on a date they never received needs to know whether their
    # build carries the fix.
    unreleased = [r for r in releases if not r.released]
    if unreleased:
        last_released = next((r for r in releases if r.released), None)
        since = (f" since the release of {last_released.date:%d %B %Y}"
                 if last_released and last_released.date else "")
        st.warning(
            f"{len(unreleased)} change "
            f"{'set' if len(unreleased) == 1 else 'sets'}{since} "
            f"{'is' if len(unreleased) == 1 else 'are'} in the code and not in a "
            f"formal release.  Figures produced by a released build will differ "
            f"where those changes affect them.  Each is marked unreleased in "
            f"the history below, with its impact on released builds stated."
        )

    if facts:
        st.markdown("**This installation**")
        for label, value in dict(facts).items():
            st.markdown(f"- {label}: `{value}`")

    if documents:
        _render_documents(documents, key_prefix)

    st.divider()

    if error:
        st.warning(f"Change history unavailable.  {error}")
        return
    if not releases:
        st.caption("No change history to show.")
        return

    st.markdown("**Change history**")
    left, right = st.columns([2, 3])
    with left:
        choices = ["All releases"] + [r.label for r in releases]
        picked = st.selectbox("Release", choices, key=f"{key_prefix}_release",
                              label_visibility="collapsed")
    with right:
        term = st.text_input("Search", key=f"{key_prefix}_search",
                             placeholder="Search the change history",
                             label_visibility="collapsed")

    selected = releases if picked == "All releases" else \
        [r for r in releases if r.label == picked]
    if term:
        selected = [r for r in selected
                    if term.lower() in r.body.lower()
                    or term.lower() in r.heading.lower()]
        if not selected:
            st.caption(f"Nothing matching “{term}”.")

    st.caption(f"{len(selected)} of {len(releases)} releases"
               + (f", filtered on “{term}”" if term else ""))

    for release in selected:
        with st.expander(release.label, expanded=(len(selected) == 1)):
            if release.status:
                if release.released:
                    st.caption(release.status)
                else:
                    st.warning(release.status)
            if release.impact:
                # The impact line answers the reader's actual question, so it
                # goes above the detail rather than at the end of it.
                if release.no_impact:
                    st.success(f"Impact: {release.impact}")
                else:
                    st.info(f"Impact: {release.impact}")
            st.markdown(_highlight(release.body, term) or "_No detail recorded._")

    if path is not None and text is not None:
        st.download_button("Download the full change history",
                           data=text.encode("utf-8"),
                           file_name=path.name, mime="text/markdown",
                           key=f"{key_prefix}_download")

    if show_environment:
        with st.expander("Environment", expanded=False):
            rows = {
                "Python": platform.python_version(),
                "Streamlit": getattr(st, "__version__", "unknown"),
                "Platform": f"{platform.system()} {platform.release()}",
                "Working directory": Path.cwd(),
                "Change history": path,
                "Interpreter": sys.executable,
            }
            for label, value in rows.items():
                st.markdown(f"- {label}: `{value}`")


if __name__ == "__main__":                       # pragma: no cover
    # Standalone check:  streamlit run AboutPanel.py
    st.set_page_config(page_title="About", layout="wide")
    render_about(
        app_name="About panel",
        changelog="Changelog.md",
        description="Standalone render of this module against the changelog "
                    "in the working directory.",
    )
