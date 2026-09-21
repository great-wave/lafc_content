"""Export notebook figures as After Effects-ready SVG triplets.

Each chart leaves here as three files sharing one coordinate space:

  {name}_plate_V01.svg              axes, gridlines, labels -- all static
  {name}_marks_01_{category}_V01.svg  one file per category, the animatable part
  {name}_legend_V01.svg             the category swatches and their labels

MARKS ARE SPLIT BY CATEGORY. After Effects breaks a vector composition into one
shape layer per drawn element, which for a six-category box plot means roughly
sixty layers to hand-animate. Writing one file per category instead gives six
layers with the same motion available, each still fully editable vector. The
numeric prefix preserves the chart's own category order, so the files import
and stagger in the order they are drawn.

After Effects ingests them differently. The plate goes in as Footage, which
keeps a live link to the file on disk, so re-running the notebook on fresh data
updates the artwork in place. The marks and legend go in as "Composition -
Retain Layer Sizes", which explodes each into one shape layer per element.

VERSIONING IS PER RUN, NOT PER FILE. Every file written by one export() call
carries the same version number, and the next call writes the next number
instead of overwriting. This matters because a chart's plate, marks and legend
only stack correctly if they came from the same render -- letting files version
independently would eventually pair a V02 plate with a V03 marks and misalign
them by whatever changed in between. One run, one number, across the whole set.

HOW REGISTRATION IS GUARANTEED. The obvious way to split a chart -- hide the
axes for the marks pass -- silently breaks alignment, because Plotly sizes its
plot area around whatever labels are present. Remove them and the drawing area
grows, sliding every mark a few pixels. So nothing that carries layout weight
is ever removed. All three passes render the same figure at the same size and
paint the groups they don't want transparent. Verified: the box path
coordinates come out identical across all three passes.

THE LEGEND IS THE EXCEPTION. Plotly draws legend swatches from each trace's own
styling, so no layout-safe setting can hide them -- trace opacity does not
reach them. They are removed from the SVG after rendering instead, which cannot
disturb anything because the geometry is already baked by then.
"""

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

TRANSPARENT = "rgba(0,0,0,0)"
SIZE = (1920, 1080)

# Keep ElementTree from rewriting the SVG namespace as ns0: on output.
_SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", _SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

# Plotly wraps the plot area in clipping regions so marks cannot spill past the
# axes. The viewBox already crops, and in After Effects these can arrive as
# per-layer masks that clutter the shape tree, so strip them on the way out.
_CLIP = re.compile(r"<clipPath\b.*?</clipPath>|\s+clip-path=\"[^\"]*\"", re.S)

# Trailing _V01, _V02 ... on an exported filename.
_VERSION = re.compile(r"_V(\d+)\.svg$")


def _next_version(out_dir):
    """The version number this run should write.

    Reads the highest number already on disk and adds one, scanning the whole
    directory rather than each filename separately so every file in a run
    shares one number - see the note on versioning in the module docstring.
    Returns 1 for an empty or missing directory.
    """
    highest = 0
    for path in out_dir.glob("*_V*.svg"):
        match = _VERSION.search(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _prepare(fig, size):
    """Deep-copy the figure and pin what every pass must share.

    The copy matters: these are the notebook's live figure objects, still
    displayed in their cells. Mutating them would repaint the analysis.

    Note what is NOT set here - showlegend. Each figure keeps its own setting,
    so every pass reserves the same legend space and lays out identically.
    """
    out = copy.deepcopy(fig)
    width, height = size
    out.update_layout(width=width, height=height,
                      paper_bgcolor=TRANSPARENT, plot_bgcolor=TRANSPARENT)
    return out


def _hide_marks(fig):
    """Boxes and points go transparent, keeping their layout space."""
    fig.update_traces(opacity=0)


def _hide_chrome(fig):
    """Axes, labels, title and reference lines go transparent.

    Gridlines are switched off rather than painted transparent: setting
    gridcolor makes Plotly draw gridlines on axes that had none, which would
    land in After Effects as invisible junk layers. Turning them off is safe
    because gridlines sit inside the plot area and carry no layout weight -
    unlike the tick labels, which must stay and only change color.
    """
    axes = dict(showgrid=False, linecolor=TRANSPARENT, zerolinecolor=TRANSPARENT,
                tickcolor=TRANSPARENT, tickfont_color=TRANSPARENT,
                title_font_color=TRANSPARENT)
    fig.update_xaxes(**axes)
    fig.update_yaxes(**axes)
    fig.update_layout(title_font_color=TRANSPARENT)
    # add_vline / add_hline reference lines are chrome too - reach_vs_engagement
    # draws two. No-op on figures that have no shapes.
    fig.update_shapes(line_color=TRANSPARENT)


def _clear_legend_frame(fig):
    """Drop the legend's own background and border.

    Plotly fills the legend box with opaque white, which would arrive in After
    Effects as a white rectangle behind the swatches.
    """
    fig.update_layout(legend=dict(bgcolor=TRANSPARENT, bordercolor=TRANSPARENT))


# A trace Plotly rendered fully faded - style="opacity: 0" - but not 0.5 etc.
_FADED = re.compile(r"opacity:\s*0\s*(?:;|$)")


def _prune(svg, keep_legend):
    """Delete from rendered SVG what transparency alone cannot remove.

    Two things need it. Legend swatches take their color from the traces, so no
    layout-safe setting hides them. Faded-out traces are still real elements,
    and After Effects would turn each one into its own shape layer - exactly
    the clutter the per-category split exists to avoid.

    Both are safe here because the geometry is already baked: removing an
    element from finished SVG cannot move anything that remains. A parser is
    used rather than a regex because these groups contain nested <g> elements.
    """
    root = ET.fromstring(svg)
    for parent in root.iter():
        for child in list(parent):
            classes = (child.get("class") or "").split()
            faded = _FADED.search(child.get("style") or "")
            if ("legend" in classes and not keep_legend) or ("trace" in classes and faded):
                parent.remove(child)
    return ET.tostring(root, encoding="unicode")


def _isolate_trace(fig, index):
    """Leave one trace visible and fade the rest.

    Only the others are touched, so the kept trace holds whatever opacity it
    was given. Opacity is purely visual, so every category renders into the
    same layout and the files stack.
    """
    for position, trace in enumerate(fig.data):
        if position != index:
            trace.opacity = 0


def _slug(text):
    """Filename-safe version of a category name.

    Playlist titles carry spaces and punctuation, so anything that is not
    alphanumeric collapses to a single underscore.
    """
    return re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_") or "trace"


def _trace_labels(fig):
    """One slug per trace, in the order the chart draws them.

    A trace with no name is a single unsplit series - the histograms - and is
    labelled "all" rather than given a meaningless number.
    """
    return [_slug(trace.name or "all") for trace in fig.data]


def _render_pass(fig, size, hiders, keep_legend=False, isolate=None):
    """Render one pass of a figure and return finished SVG text."""
    out = _prepare(fig, size)
    for hide in hiders:
        hide(out)
    if isolate is not None:
        _isolate_trace(out, isolate)
    if keep_legend:
        _clear_legend_frame(out)
    svg = out.to_image(format="svg").decode()
    return _CLIP.sub("", _prune(svg, keep_legend))


def export(figures, out_dir, sizes=None):
    """Write a plate, a legend and one marks file per category, per figure.

    figures  name -> plotly figure; the notebook's FIGURES dict
    sizes    optional name -> (width, height) for charts needing more canvas

    Nothing is ever overwritten: the run takes the next free version number and
    stamps it on every file it writes. Returns that number.

    File count follows the number of categories, so the two playlist charts
    produce a marks file per playlist. Charts with no legend still get a legend
    file, it just comes out nearly empty.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = sizes or {}

    version = _next_version(out_dir)
    written = 0

    for name, fig in figures.items():
        size = sizes.get(name, SIZE)
        labels = _trace_labels(fig)

        def save(suffix, svg):
            (out_dir / f"{name}_{suffix}_V{version:02d}.svg").write_text(svg)

        # Static chrome: the marks fade out, everything else stays.
        save("plate", _render_pass(fig, size, (_hide_marks,)))

        # One file per category, each holding only its own boxes.
        for index, label in enumerate(labels):
            save(f"marks_{index + 1:02d}_{label}",
                 _render_pass(fig, size, (_hide_chrome,), isolate=index))

        # Swatches and their text, with the chart itself faded out.
        save("legend", _render_pass(fig, size, (_hide_marks, _hide_chrome),
                                    keep_legend=True))

        written += len(labels) + 2
        print(f"{name}  {size[0]}x{size[1]}  {len(labels)} categories")

    print(f"-> wrote V{version:02d} ({written} files) to {out_dir}")
    return version
