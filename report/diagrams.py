"""Draw the flowchart figures used by the Lab 1 report.

Why the figures are generated instead of drawn by hand
------------------------------------------------------
Every claim in the report has a shape: a request path, a decision, a chain of
causes. Prose describes that shape one sentence at a time, and the reader has
to rebuild it in their head. A generated diagram carries the same information
in one glance - and because it is drawn from a list of boxes and arrows, it can
be corrected and regenerated when the text changes, which a hand-made drawing
cannot.

How a figure is built
---------------------
Each figure is a list of nodes and arrows on a plain Cartesian canvas:

    node(ax, cx, cy, w, h, "title", "sub")   a rounded box, centred on cx/cy
    diamond(ax, cx, cy, w, h, "question")    a decision point
    arrow(ax, p, q, "label")                 an arrow from point p to point q

Coordinates are not pixels: the canvas is 100 units wide and the y range is
chosen per figure, so a box is placed by "centre it at x=50" rather than by
pixel arithmetic. axis("off") hides the frame; nothing is plotted as data.

Output
------
PNG at 220 dpi in docs/diagrams/. The report embeds them through
docx_builder.shot(), which reads the pixel size from the PNG header and scales
the picture to the text column, so the aspect ratio chosen here is the aspect
ratio the reader sees.

Run:  python3 report/diagrams.py
"""

import os

import matplotlib

# Agg is the non-interactive backend: it renders to a file without needing a
# display server. Importing pyplot *after* this line is what makes the choice
# stick - pyplot picks its backend at import time.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon  # noqa: E402

# docs/diagrams/ sits next to docs/screenshots/, both two levels up from this
# file (report/ -> Lab1/).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "diagrams")

# One palette for every figure, so the report looks like one document rather
# than nine unrelated pictures. The colours match the docx headings (#1F3864)
# and the table headers (#E8EEF4).
INK = "#1F3864"        # headings and box titles
ACCENT = "#2E5496"     # box outline
SUBTEXT = "#3D3D3D"    # the second line inside a box
MUTE = "#6E6E6E"       # arrows and their labels

# kind -> (fill, outline)
STYLES = {
    "step": ("#E8EEF4", ACCENT),    # an ordinary step
    "ok": ("#E3F0E5", "#4C7A56"),   # the outcome that is wanted
    "bad": ("#FBE7E4", "#A5433B"),  # the outcome that is prevented
    "warn": ("#FDF3DC", "#B08024"),  # the decisive line in a chain
    "note": ("#F7F7F7", "#C9C9C9"),  # an aside, not part of the flow
}


def node(ax, cx, cy, w, h, title, sub="", kind="step", fs=10.5, sfs=8.4):
    """A rounded box centred on (cx, cy) holding a title and an optional line.

    The box is returned as (cx, cy, w, h) so the edge helpers below can attach
    an arrow to the exact border instead of to the centre.
    """
    fill, edge = STYLES[kind]
    ax.add_patch(FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0,rounding_size=1.4",
        linewidth=1.3, facecolor=fill, edgecolor=edge, zorder=2))
    # With a sub-line the title sits above the centre, otherwise it is centred:
    # two lines of text inside a fixed box always need this offset, or the
    # block looks bottom-heavy.
    ax.text(cx, cy + (h * 0.17 if sub else 0), title, ha="center", va="center",
            fontsize=fs, color=INK, fontweight="bold", zorder=3, linespacing=1.2)
    if sub:
        ax.text(cx, cy - h * 0.17, sub, ha="center", va="center",
                fontsize=sfs, color=SUBTEXT, zorder=3, linespacing=1.35)
    return (cx, cy, w, h)


def diamond(ax, cx, cy, w, h, text, kind="warn", fs=9.2):
    """A decision point: a rhombus with the question inside."""
    fill, edge = STYLES[kind]
    ax.add_patch(Polygon([[cx, cy + h / 2], [cx + w / 2, cy],
                          [cx, cy - h / 2], [cx - w / 2, cy]],
                         closed=True, facecolor=fill, edgecolor=edge,
                         linewidth=1.3, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=INK,
            fontweight="bold", zorder=3, linespacing=1.25)
    return (cx, cy, w, h)


# Edge points of a box: right, left, top, bottom.
def R(b):
    return (b[0] + b[2] / 2, b[1])


def L(b):
    return (b[0] - b[2] / 2, b[1])


def T(b):
    return (b[0], b[1] + b[3] / 2)


def B(b):
    return (b[0], b[1] - b[3] / 2)


def arrow(ax, p, q, label="", color=MUTE, ls="-", lw=1.4, rad=0.0,
          conn=None, lo=(0, 1.6), fs=8.2, ha="center", fw="normal"):
    """An arrow from p to q with an optional label at its midpoint.

    conn overrides the curve: "angle,angleA=-90,angleB=0" draws an elbow,
    which is what a branch that has to leave a box sideways and arrive from
    above needs. rad=0.15 bends a straight arrow slightly so two parallel
    paths stay distinguishable.
    """
    style = conn or f"arc3,rad={rad}"
    ax.add_patch(FancyArrowPatch(
        p, q, arrowstyle="-|>", mutation_scale=13, color=color,
        linewidth=lw, linestyle=ls, shrinkA=1.5, shrinkB=1.5,
        connectionstyle=style, zorder=1))
    if label:
        mx = p[0] + (q[0] - p[0]) * 0.5 + lo[0]
        my = p[1] + (q[1] - p[1]) * 0.5 + lo[1]
        # The white background box keeps the label readable where it overlaps
        # a grid line or the arrow itself.
        ax.text(mx, my, label, fontsize=fs, color=color, ha=ha, va="center",
                zorder=4, fontweight=fw, linespacing=1.3,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none",
                          alpha=0.92))


def canvas(w_in, h_in, xlim, ylim):
    """An empty figure with equal aspect, so boxes are not stretched."""
    fig, ax = plt.subplots(figsize=(w_in, h_in))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def save(fig, name):
    out = os.path.join(OUT_DIR, name)
    # bbox_inches="tight" trims the empty margin, pad_inches keeps 0.12 in of
    # breathing space so Word does not butt the caption against the drawing.
    fig.savefig(out, dpi=220, bbox_inches="tight", pad_inches=0.12,
                facecolor="white")
    plt.close(fig)
    return out


# ---------------------------------------------------------------- figure 1
def fig_lifecycle():
    """The four stages of the work, and what each one produces."""
    fig, ax = canvas(10, 3.3, (0, 100), (0, 33))
    cy, w, h = 18, 21, 18
    xs = [12, 37, 62, 87]
    # Subtitles are short on purpose: a box of 21 units holds about 22
    # characters per line at 7.8 pt, and a line that overflows the border is
    # the one defect a reader notices immediately.
    boxes = [
        node(ax, xs[0], cy, w, h, "1 · Build",
             "Flask API\nbound SQL · escaping\nbcrypt + JWT", "step", fs=10, sfs=7.8),
        node(ax, xs[1], cy, w, h, "2 · Gate",
             "CI on every push\npytest · bandit\npip-audit", "step", fs=10, sfs=7.8),
        node(ax, xs[2], cy, w, h, "3 · Attack",
             "Druid 0.20.0\nempty-key RCE\nCVSS 8.8", "bad", fs=10, sfs=7.8),
        node(ax, xs[3], cy, w, h, "4 · Prove",
             "0.20.1 refuses\nthe same request\nand stays up", "ok", fs=10, sfs=7.8),
    ]
    for a, b in zip(boxes, boxes[1:]):
        arrow(ax, R(a), L(b), color="#9AA7B8")
    return save(fig, "d01-lifecycle.png")


# ---------------------------------------------------------------- figure 2
def fig_request_path():
    """What happens to one authenticated request, including the fail-closed exit."""
    fig, ax = canvas(10, 4.8, (0, 100), (0, 54))
    n1 = node(ax, 50, 50, 50, 8, "Client request",
              "GET /api/data?q=…   Authorization: Bearer <token>", "step", fs=10)
    d1 = diamond(ax, 50, 37, 40, 14, "token present,\nsigned and not expired?")
    red = node(ax, 15, 37, 24, 11, "401 Unauthorized", "no handler code runs", "bad", fs=9.5)
    b1 = node(ax, 50, 23, 56, 10, "handler · SELECT … WHERE title LIKE ?",
              "the value is bound, never concatenated into the SQL text", "step", fs=9.8)
    # The last step doubles as the successful exit: a separate "200" box would
    # have to sit outside the text column, and an arrow that ends on the edge
    # of the canvas reads worse than a green box.
    b2 = node(ax, 50, 9, 62, 11, "response · 200 JSON",
              "html.escape() on every field, plus nosniff and a CSP", "ok", fs=9.8)

    arrow(ax, B(n1), T(d1))
    arrow(ax, L(d1), R(red), "no", lo=(0, 0), fs=8)
    arrow(ax, B(d1), T(b1), "valid", lo=(9, 0.6), fs=7.8)
    arrow(ax, B(b1), T(b2))
    return save(fig, "d02-request-path.png")


# ---------------------------------------------------------------- figure 3
def fig_auth_flow():
    """Login: one bcrypt comparison on every path, then either a token or 401."""
    fig, ax = canvas(10, 6.2, (0, 100), (0, 62))
    n1 = node(ax, 50, 55, 50, 8, "POST /auth/login",
              '{"username": … , "password": …}', "step", fs=10)
    d1 = diamond(ax, 50, 44, 40, 13, "account exists?")
    bc = node(ax, 50, 31, 58, 9, "exactly one bcrypt.checkpw()",
              "a dummy hash is compared when no row was found", "step", fs=9.8)
    d2 = diamond(ax, 50, 19, 40, 13, "password matches?")
    red = node(ax, 13, 19, 24, 11, "401", '"invalid credentials"', "bad", fs=9.5)
    sign = node(ax, 85, 19, 26, 11, "sign a JWT", "HS256 · 30 min TTL", "step", fs=9)
    ok = node(ax, 85, 5, 26, 9, "200 + access_token", "expires_in: 1800", "ok", fs=8.8)

    # Only the two points that are easy to get wrong carry a label: the same
    # comparison runs when the account is missing, and the failure answer is
    # indistinguishable from a wrong password. "yes"/"no" on a vertical arrow
    # whose meaning is obvious would only add clutter.
    arrow(ax, B(n1), T(d1))
    arrow(ax, B(d1), T(bc))
    arrow(ax, L(d1), L(bc), "no → dummy hash", lo=(-9, 0), fs=7.6, rad=-0.35)
    arrow(ax, B(bc), T(d2))
    arrow(ax, L(d2), R(red), "no", lo=(0, -2.4), fs=8)
    arrow(ax, R(d2), L(sign))
    arrow(ax, B(sign), T(ok))
    ax.text(44, 6, "both exits cost one bcrypt comparison —\nthe message and the timing reveal nothing",
            fontsize=8.2, color=MUTE, ha="center", va="center", style="italic")
    return save(fig, "d05-auth-flow.png")


# ---------------------------------------------------------------- figure 4
def fig_sqli():
    """The same payload against parameter binding and against concatenation."""
    fig, ax = canvas(10, 4.2, (0, 100), (0, 41))
    src = node(ax, 14, 25, 22, 11, "q = ' OR 1=1--", "one query parameter", "step", fs=9.5)
    par = node(ax, 45, 25, 26, 11, "bound parameter", "sent next to the SQL text", "ok", fs=9.5)
    res = node(ax, 79, 25, 24, 11, "0 rows", "treated as a literal term", "ok", fs=9.5)
    bad1 = node(ax, 45, 9, 26, 11, "f-string concatenation", "the input becomes SQL", "bad", fs=9.5)
    bad2 = node(ax, 79, 9, 24, 11, "every row", "the parse tree was rewritten", "bad", fs=9.5)

    arrow(ax, R(src), L(par), "as a value", lo=(0, 2.6), fs=7.8)
    arrow(ax, R(par), L(res), "", color="#4C7A56")
    # The rejecting branch is dashed: it shows what the code deliberately does
    # not do, not a path the reader can take.
    arrow(ax, B(src), L(bad1), "", color="#A5433B", ls="--",
          conn="angle,angleA=0,angleB=90")
    arrow(ax, R(bad1), L(bad2), "", color="#A5433B", ls="--")
    ax.text(22, 15, "if the value were\ninterpolated", fontsize=8, color="#A5433B",
            ha="center", va="center", style="italic")
    return save(fig, "d03-sqli.png")


# ---------------------------------------------------------------- figure 5
def fig_xss():
    """Store verbatim, escape on output: where the payload is neutralised."""
    fig, ax = canvas(10, 4.0, (0, 100), (0, 38))
    s = node(ax, 11, 27, 20, 11, 'body: <script>…', "typed by the attacker", "step", fs=8.8)
    db = node(ax, 37, 27, 22, 11, "stored verbatim", "no mangling on write", "step", fs=9.2)
    enc = node(ax, 63, 27, 22, 11, "escaped on output", "html.escape per field", "ok", fs=9.2)
    br = node(ax, 89, 27, 20, 11, "browser gets text", "text, not markup", "ok", fs=8.8)
    bad = node(ax, 37, 8, 34, 11, "escaped before storing", "the data itself is corrupted", "bad", fs=9.2)

    arrow(ax, R(s), L(db))
    arrow(ax, R(db), L(enc))
    arrow(ax, R(enc), L(br))
    arrow(ax, B(db), T(bad), "", color="#A5433B", ls="--")
    ax.text(41, 15.5, "the shortcut that is not taken", fontsize=7.8, color="#A5433B",
            ha="left", va="center", style="italic")
    return save(fig, "d04-xss.png")


# ---------------------------------------------------------------- figure 6
def fig_pipeline():
    """The CI job as a snake: four preparation steps, four gates, one verdict."""
    fig, ax = canvas(10, 5.0, (0, 100), (0, 52))
    xs = [12, 37, 62, 87]
    w, h = 22, 13
    top = [
        node(ax, xs[0], 41, w, h, "push / pull request", ".github/workflows/ci.yml", "step", fs=8.8),
        node(ax, xs[1], 41, w, h, "checkout + Python", "3.11, with a pip cache", "step", fs=8.8),
        node(ax, xs[2], 41, w, h, "install deps + tools", "bandit · pip-audit · pytest", "step", fs=8.6),
        node(ax, xs[3], 41, w, h, "write .env.ci", "throwaway key, temp DB", "step", fs=8.8),
    ]
    bottom = [
        node(ax, xs[0], 17, w, h, "summarise + upload", "one verdict, artifact", "ok", fs=8.8),
        node(ax, xs[1], 17, w, h, "pip-audit", "SCA · 9 deps audited", "step", fs=8.8),
        node(ax, xs[2], 17, w, h, "bandit", "SAST · 286 lines", "step", fs=8.8),
        node(ax, xs[3], 17, w, h, "pytest + smoke", "12 tests, 4 live calls", "step", fs=8.8),
    ]
    for a, b in zip(top, top[1:]):
        arrow(ax, R(a), L(b))
    arrow(ax, B(top[3]), T(bottom[3]))
    for a, b in zip(bottom[3:], bottom[2::-1]):
        arrow(ax, L(a), R(b))
    ax.text(50, 4, "every step must pass: a failing test, a finding or an advisory fails the build",
            fontsize=8.8, color="#A5433B", ha="center", va="center")
    return save(fig, "d06-pipeline.png")


# ---------------------------------------------------------------- figure 7
def fig_attack():
    """The CVE-2021-25646 chain, with the empty key as the pivot."""
    fig, ax = canvas(10, 5.2, (0, 100), (0, 54))
    xs = [12, 37, 62, 87]
    w, h = 22, 13
    top = [
        node(ax, xs[0], 43, w, h, "POST /sampler", "no credentials", "step", fs=9),
        node(ax, xs[1], 43, w, h, "Jackson parses", "parseSpec into a map", "step", fs=9),
        node(ax, xs[2], 43, w, h, 'key "" accepted', "merged into that map", "warn", fs=9.4),
        node(ax, xs[3], 43, w, h, 'enabled = "true"', "default overwritten", "warn", fs=9.4),
    ]
    bottom = [
        node(ax, xs[0], 18, w, h, "output returned", "inside the response", "bad", fs=9),
        node(ax, xs[1], 18, w, h, "runs as root", "the image's default", "bad", fs=9),
        node(ax, xs[2], 18, w, h, "Runtime.exec('id')", "a real shell", "bad", fs=9),
        node(ax, xs[3], 18, w, h, "Rhino evaluates it", "Runtime is in reach", "bad", fs=9),
    ]
    for a, b in zip(top, top[1:]):
        arrow(ax, R(a), L(b))
    arrow(ax, B(top[3]), T(bottom[3]))
    for a, b in zip(bottom[3:], bottom[2::-1]):
        arrow(ax, L(a), R(b))
    ax.text(50, 5, "one unvalidated map key turns a disabled feature into remote code execution",
            fontsize=8.8, color=INK, ha="center", va="center", fontweight="bold")
    return save(fig, "d07-attack-chain.png")


# ---------------------------------------------------------------- figure 8
def fig_fix_compare():
    """The same request against both versions: the fix is the refused override."""
    fig, ax = canvas(10, 4.4, (0, 100), (0, 46))
    req = node(ax, 50, 41, 56, 8, "the same crafted POST", "byte-identical request", "step", fs=9.6)
    vuln = node(ax, 25, 29, 38, 12, "0.20.0 · vulnerable", "the override is accepted", "bad", fs=9.6)
    out1 = node(ax, 25, 12, 38, 12, "function is executed", "uid=0(root) comes back", "bad", fs=9.6)
    fixed = node(ax, 75, 29, 38, 12, "0.20.1 · patched", "the override is rejected", "ok", fs=9.6)
    out2 = node(ax, 75, 12, 38, 12, '"JavaScript is disabled"', "no output, console answers 302", "ok", fs=9)

    arrow(ax, B(req), T(vuln), "", color="#A5433B", conn="arc3,rad=-0.1")
    arrow(ax, B(req), T(fixed), "", color="#4C7A56", conn="arc3,rad=0.1")
    arrow(ax, B(vuln), T(out1), "", color="#A5433B")
    arrow(ax, B(fixed), T(out2), "", color="#4C7A56")
    ax.text(50, 2, "same base image, launcher and ports — the only variable is the jar version",
            fontsize=8.4, color=MUTE, ha="center", va="center", style="italic")
    return save(fig, "d09-fix-compare.png")


# ---------------------------------------------------------------- figure 9
def fig_root_cause():
    """Five links, each one the reason the next one is possible."""
    fig, ax = canvas(10, 5.2, (-2, 100), (-8, 60))
    cx, w, h = 34, 58, 10
    ys = [54, 41, 28, 15, 2]
    boxes = [
        node(ax, cx, ys[0], w, h, "JavaScript parsing is off by default",
             "the guard is a configuration flag, not a boundary", "step", fs=9.2),
        node(ax, cx, ys[1], w, h, 'an empty key is accepted',
             "Jackson merges it into parseSpec", "warn", fs=9.5),
        node(ax, cx, ys[2], w, h, "the enabled flag is overwritten",
             "the client now writes a server-side setting", "step", fs=9.2),
        node(ax, cx, ys[3], w, h, "Rhino runs JavaScript without a sandbox",
             "java.lang.Runtime is reachable", "step", fs=9.2),
        node(ax, cx, ys[4], w, h, "the sampler endpoint asks for no credentials",
             "remote code execution as root", "bad", fs=9.2),
    ]
    for a, b in zip(boxes, boxes[1:]):
        arrow(ax, B(a), T(b), "so", lo=(2.6, 0), fs=7.8)

    # The two annotations name the two ends of the chain: the defect itself and
    # the consequence the grader is asked to explain. xy is the box border,
    # xytext the label start, so the arrow has a visible length.
    ax.annotate("root cause", xy=(w + 1, ys[1]), xytext=(w + 9, ys[1]),
                fontsize=9, color="#B08024", fontweight="bold", va="center",
                ha="left",
                arrowprops=dict(arrowstyle="-|>", color="#B08024", lw=1.2))
    ax.annotate("impact", xy=(w + 1, ys[4]), xytext=(w + 9, ys[4]),
                fontsize=9, color="#A5433B", fontweight="bold", va="center",
                ha="left",
                arrowprops=dict(arrowstyle="-|>", color="#A5433B", lw=1.2))
    return save(fig, "d08-root-cause.png")


# Listed in the order the report presents them, which is also the order of the
# file names (d01 ... d09) and of the figure numbers in the captions.
FIGURES = [
    fig_lifecycle,      # Figure 1 - section 1
    fig_request_path,   # Figure 2 - section 3
    fig_sqli,           # Figure 3 - section 4.1
    fig_xss,            # Figure 4 - section 4.2
    fig_auth_flow,      # Figure 5 - section 4.3
    fig_pipeline,       # Figure 6 - section 5
    fig_attack,         # Figure 7 - section 8
    fig_root_cause,     # Figure 8 - section 9
    fig_fix_compare,    # Figure 9 - section 11
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for draw in FIGURES:
        path = draw()
        print(f"{os.path.basename(path):24} {os.path.getsize(path) // 1024:4} KB")


if __name__ == "__main__":
    main()
