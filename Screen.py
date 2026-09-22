"""Screen.py

One screen, drawn the same way wherever a person reads rows and writes
something.

The Builder grew eleven pages that each laid themselves out: a row of
tiles that counted but could not be pressed, a separate control that
filtered in different words, a publish gate in the sidebar away from the
figures it was about, and a save button that did not say what it would
write.  The sister application settled these questions and they are
settled the same way here, so a person moving between the two reads one
screen twice rather than two screens once.

What is here, and nothing else:

    cards()    counts in line, each one a filter on the table beneath them
    table()    one table, drawn one way, saying how much of itself is shown
    gate()     the publish button on a third of the width, the rest beside it
    nothing()  a page with nothing in it, still drawn as a page
    months()   a month, written the way a person reads one

A page passes what it has.  It does not draw its own row of cards, its own
columns or its own confirmation.

Last updated: 2026-09-11
"""

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# The look
# ---------------------------------------------------------------------------
# Injected once a run.  A count you can read across the room, every tile the
# same height whatever its sentence runs to, so the row reads as one row and
# the buttons under it line up.

CSS = """
<style>
  .eg-card  { border: 1px solid #8884; border-radius: 10px;
              padding: 0.8rem 1rem; height: 10.5rem; overflow: hidden;
              display: flex; flex-direction: column; box-sizing: border-box; }
  .eg-card-says { font-size: 0.88rem; line-height: 1.45; opacity: 0.65;
                  margin-top: 0.3rem; }
  .eg-count { font-size: 2.6rem; font-weight: 650; line-height: 1.05; }
  .eg-count-word { font-size: 1rem; opacity: 0.85; }
  div[data-testid="stDataFrame"] { font-size: 13px; }
  div[data-testid="stDataFrame"] * { font-size: 13px !important; }

  /* The rest is PrepData's, so the two applications read as one.  The
     screens down the sidebar as real buttons, full width, the label against
     the right edge; the one you are on filled and marked. */
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
      width: 100%; border: 1px solid #8886; border-radius: 8px;
      padding: 0.5rem 0.9rem; font-size: 1rem; font-weight: 500;
      margin-bottom: 0.3rem; }
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button > div,
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button p {
      width: 100%; text-align: right; }
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
      border-color: currentColor; background: #8881; }
  section[data-testid="stSidebar"]
      div[data-testid="stButton"] > button[kind="primary"],
  section[data-testid="stSidebar"] div[data-testid="stButton"]
      > button[data-testid="stBaseButton-primary"] {
      font-weight: 700; border-color: currentColor; }
  .eg-nav-title { font-size: 0.82rem; letter-spacing: 0.06em;
                  text-transform: uppercase; opacity: 0.55; font-weight: 600;
                  margin: 0.2rem 0 0.4rem 0; text-align: right; }

  .eg-headline { font-size: 1.9rem; font-weight: 650; line-height: 1.3;
                 margin: 0.2rem 0 0.1rem 0; }
  .eg-subhead  { font-size: 1.15rem; opacity: 0.8; margin-bottom: 1.1rem; }

  /* What a file holds, read from the doorway: the range large, the name
     above it as the label. */
  .eg-held { padding: 0.1rem 0 0.4rem 0; }
  .eg-held-name { font-size: 0.82rem; letter-spacing: 0.05em;
                  text-transform: uppercase; opacity: 0.6; font-weight: 600; }
  .eg-held-range { font-size: 1.6rem; font-weight: 700; line-height: 1.25;
                   margin: 0.1rem 0; }
  .eg-held-rows { font-size: 0.85rem; opacity: 0.65; }
</style>
"""

_DRAWN = "_eg_css"

# What each word means, and the colour it carries.  A verdict is the same
# colour on every page, because a person learns a colour once.
COLOUR = {
    # What an import says about a row.
    "rejected": "#e34948", "questioned": "#eda100", "restated": "#2f6fb3",
    "absent": "#8a6fb3", "new": "#2e8b57", "unchanged": "#666",
    "left out": "#888",
    # What a scope 3 category says about itself.  The same three colours the
    # badges carried, in the count rather than beside it.
    "Calculated": "#2e8b57", "Estimated": "#eda100",
    "Outstanding": "#e34948", "Excluded": "#888",
    "Not applicable": "#888",
    # And the words a check uses.
    "error": "#e34948", "warning": "#eda100", "fine": "#2e8b57",
}


def dressed():
    """The stylesheet, on every run.

    Streamlit redraws the page from nothing on each run, so a stylesheet
    drawn once and remembered is gone from the second draw onward.
    """
    st.markdown(CSS, unsafe_allow_html=True)


def navigation(screens, key='screen'):
    """The screens down the sidebar, one selected, as PrepData draws them.

    `screens` is a list of (name, icon).  Returns the name selected.  Set
    and carried on, not rerun, so pressing a screen draws it on this pass
    rather than flashing the one being left.
    """
    names = [name for name, _ in screens]
    st.session_state.setdefault(key, names[0])
    if st.session_state[key] not in names:
        st.session_state[key] = names[0]
    st.sidebar.markdown('<div class="eg-nav-title">Screens</div>',
                        unsafe_allow_html=True)
    for name, icon in screens:
        here = st.session_state[key] == name
        if st.sidebar.button(name, icon=icon, key=f'nav_{name}',
                             width='stretch',
                             type='primary' if here else 'secondary'):
            st.session_state[key] = name
    return st.session_state[key]


def headline(text, under=None):
    """The one sentence that says where you are."""
    st.markdown(f'<div class="eg-headline">{text}</div>',
                unsafe_allow_html=True)
    if under:
        st.markdown(f'<div class="eg-subhead">{under}</div>',
                    unsafe_allow_html=True)


def held(tiles):
    """What each file holds, large enough to read from the doorway.

    `tiles` is a list of (name, range, detail).
    """
    columns = st.columns(len(tiles))
    for column, (name, covers, detail) in zip(columns, tiles):
        column.markdown(
            f'<div class="eg-held"><div class="eg-held-name">{name}</div>'
            f'<div class="eg-held-range">{covers}</div>'
            f'<div class="eg-held-rows">{detail}</div></div>',
            unsafe_allow_html=True)


def card(count, word, says=None):
    """A count and what it means, big enough to read at a glance."""
    colour = COLOUR.get(str(word), "#666")
    return (f'<div class="eg-card">'
            f'<div class="eg-count" style="color:{colour}">{count:,}</div>'
            f'<div class="eg-count-word">{word}</div>'
            f'<div class="eg-card-says">{says or ""}</div></div>')


def cards(words, counts, focus_key, prefix, means=None, also=None):
    """Counts in line, each one a filter on the table beneath them.

    Pressing a count narrows the table to it and pressing it again clears
    it, which is the whole of the filtering: a row of tiles that counts and
    a separate control that filters are two controls saying the same thing
    in different words, and the words did not match.

    `also` is one more count beside them, as (count, word, means), for a
    number the page has taken out of the table and still has to show.  It
    carries no button because there is nothing to look at.
    """
    dressed()
    columns = st.columns(len(words) + (1 if also else 0))
    for column, word in zip(columns, words):
        count = int(counts.get(word, 0) or 0)
        with column:
            st.markdown(card(count, word, (means or {}).get(word)),
                        unsafe_allow_html=True)
            if count and st.button(f"Only {word}", width="stretch",
                                   key=f"{prefix}_focus_{word}"):
                st.session_state[focus_key] = (
                    None if st.session_state.get(focus_key) == word else word)
                st.rerun()
    if also:
        count, word, says = also
        with columns[-1]:
            st.markdown(card(max(int(count), 0), word, says),
                        unsafe_allow_html=True)


def focus(focus_key):
    """What the tiles are narrowed to, if anything."""
    return st.session_state.get(focus_key)


def unfilter(focus_key, said="Nothing sits here."):
    """A way off a filter that has left nothing."""
    st.caption(said)
    if st.session_state.get(focus_key) and st.button(
            "Show every row", key=f"{focus_key}_all"):
        st.session_state[focus_key] = None
        st.rerun()


def table(frame, key, held=None, column_config=None, height=420,
          selection=False, caption=None):
    """One table, drawn one way.

    `held` is how many rows there are before the filter, so the caption can
    say how much of itself is shown: a table that shows five hundred of
    twenty thousand rows and does not say so is a table somebody reads as
    the whole of it.

    Headings are the data's own names.  A column renamed for the screen is
    a field a person then cannot find in the file it was written to, which
    is how `Date` came to read `Completed` on one page of the sister
    application and nowhere else.
    """
    dressed()
    if frame is None or len(frame) == 0:
        return None
    shown = len(frame)
    st.caption(caption or (f"{shown:,} of {int(held):,} rows"
                           if held is not None and int(held) != shown
                           else f"{shown:,} row(s)"))
    how = {}
    if selection:
        # Only where a page answers a ticked row: Streamlit refuses a
        # selection mode without a selection to put it in.
        how = {"on_select": "rerun", "selection_mode": "single-row"}
    return st.dataframe(
        frame, width="stretch", hide_index=True, height=height,
        column_config=column_config or {}, key=key, **how)


def gate(name, label, summary, question="Are you sure?", detail=None,
         disabled=False, blocked="", note="", beside=None,
         confirm="Yes, write it", cancel="Cancel"):
    """The publish button, where every screen puts it.

    A third of the width for the button and what it will change, the rest
    for whatever the page reports.  The same proportions and the same order
    everywhere, and the figures beside the button rather than on another
    page: a person pressing Publish should not have to remember what they
    read two screens ago.

    Returns True once, when the question has been answered.
    """
    dressed()
    st.markdown("---")
    left, right = st.columns([1, 2], gap="medium")
    pressed = False
    with left:
        if blocked:
            st.error(blocked)
        asked = f"{name}_asked"
        if st.session_state.get(asked):
            st.markdown(f"**{question}**")
            if summary:
                st.caption(summary)
            if detail is not None and len(detail):
                st.dataframe(detail, width="stretch", hide_index=True)
            go, stop = st.columns(2)
            if go.button(confirm, type="primary", width="stretch",
                         key=f"{name}_go"):
                st.session_state[asked] = False
                pressed = True
            if stop.button(cancel, width="stretch", key=f"{name}_stop"):
                st.session_state[asked] = False
                st.rerun()
        else:
            if st.button(label, type="primary", width="stretch",
                         key=f"{name}_open",
                         disabled=bool(blocked) or disabled):
                st.session_state[asked] = True
                st.rerun()
            if summary:
                st.caption(summary)
            if note:
                st.caption(note)
    with right:
        if beside:
            beside()
    return pressed


def nothing(headline, says=""):
    """A page with nothing in it, still drawn as a page.

    A bare banner and an early return is a page that stops being a page:
    the heading tells a person where they are and the sentence tells them
    why there is nothing here, which is the answer rather than the absence
    of one.
    """
    dressed()
    st.subheader(headline)
    if says:
        st.caption(says)


def months(series):
    """A month, written the way a person reads one: Aug-2026."""
    when = pd.to_datetime(series, errors="coerce", dayfirst=True)
    return when.dt.strftime("%b-%Y").fillna("")
