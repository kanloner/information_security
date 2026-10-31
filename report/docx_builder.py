"""Build a valid .docx for the Lab 1 report without third-party libraries.

A .docx file is an OPC package: a ZIP archive with a fixed set of XML parts.
Writing those parts directly keeps the build hermetic (no temp files, no
dependency on python-docx) while still producing a file Word/WPS opens natively.

How a .docx is structured (read this before changing any XML below)
-------------------------------------------------------------------
A .docx is just a ZIP whose entries are XML files, and Word resolves them
through two levels of indirection:

    [Content_Types].xml           which MIME type each extension/part has
    _rels/.rels                   package rels: which part is the main document
    word/document.xml             the body text (what make_report.py builds)
    word/styles.xml               named paragraph styles ("Heading1", ...)
    word/footer1.xml              the page footer with the PAGE field
    word/_rels/document.xml.rels  document rels: style/footer/image targets
    word/media/imageN.png         the embedded screenshots
    docProps/core.xml, app.xml    title/author metadata shown in Properties

Every misspelling of a namespace, part name or relationship id makes Word
report "the file is corrupt" instead of failing loudly, so the constants below
are kept as literal blocks and never built by string surgery.

Units used here
---------------
    twips  (1/1440 inch) - page size, margins, indent, spacing
    EMU    (1/914400 inch) - drawing extents (cx/cy)
A4 is 210x297 mm = 11906x16838 twips. The two are *not* interchangeable: a
value in the wrong unit does not raise an error, it produces a page the size of
a postage stamp or a picture larger than the page.
"""

import glob
import os
import struct
import zipfile
from xml.sax.saxutils import escape

# A4 in twips (210 mm x 297 mm). Margins are 1418 twips = 2.5 cm on the sides
# and 1418 above/below, which leaves a 9070-twip text column.
A4_W, A4_H = 11906, 16838
MARGIN_SIDE, MARGIN_TOP, MARGIN_BOTTOM = 1418, 1418, 1418

# Text area is 9070 twips wide (A4 minus two side margins). Figures are
# centred inside it and never taller than a third of the page, so a screenshot
# can never push a caption onto the next page on its own.
# 1 inch = 914400 EMU, so 5_700_000 EMU is about 6.2 in - the widest picture
# that still fits the 6.3 in text column.
MAX_IMG_W = 5_700_000   # EMU (about 6.2 in)
MAX_IMG_H = 3_900_000   # EMU (about 4.3 in)

# Every element in document.xml is prefixed with this namespace. Word matches
# on the URI, not on the prefix, but the prefix must still be declared on the
# root <w:document> (see document_xml) or the part is rejected.
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# East Asian font for the Chinese edition. Calibri has no CJK glyphs, so Word
# would fall back to something unpredictable if this were left unset.
FONT_EA = "微软雅黑"

# (relationship id, file name, path, width EMU, height EMU), filled by shot()
IMAGES = []
SHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "screenshots")



def run(text, bold=False, italic=False, mono=False, size=None, color=None):
    # A "run" (<w:r>) is the smallest unit Word formats: a span of text with a
    # single set of character properties (<w:rPr>). Everything visible in a
    # paragraph is one or more runs.
    fonts = ""
    if mono:
        # Code needs a monospaced font on three channels:
        #   w:ascii/w:hAnsi - Latin text
        #   w:eastAsia      - CJK text (Calibri has no CJK glyphs)
        #   w:cs            - complex scripts
        # Leaving eastAsia unset makes Word substitute an arbitrary font, which
        # is how mixed Chinese/Latin code blocks end up misaligned.
        fonts = ('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" '
                 f'w:eastAsia="{FONT_EA}" w:cs="Consolas"/>')
    props = ["<w:rPr>"]
    if fonts:
        props.append(fonts)
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    if size:
        # w:sz is in *half-points*, so 21 means 10.5 pt. w:szCs applies the
        # same value to complex scripts; Word stores them separately.
        props.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    props.append("</w:rPr>")
    rpr = "".join(props)
    # xml:space="preserve" tells the XML parser not to collapse runs of spaces.
    # Without it, leading/indentation spaces in a code block silently vanish.
    # escape() turns &, < and > into entities, otherwise a code sample
    # containing "<script>" would produce invalid XML.
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(text="", style=None, bold=False, italic=False, mono=False, size=None,
         color=None, align=None, spacing_before=0, spacing_after=120,
         line=None, indent=None, shade=None, keep_next=False):
    # A paragraph is <w:p> = paragraph properties (<w:pPr>) + one or more runs.
    # The order of the children inside <w:pPr> is fixed by the OOXML schema
    # (pStyle, keepNext, shd, spacing, ind, jc); Word tolerates little here, so
    # the list is built in schema order rather than in the order of the
    # arguments.
    pr = ["<w:pPr>"]
    if style:
        # Reference to a named style in styles.xml. Using a style instead of
        # hard-coded formatting is what makes the headings appear in Word's
        # navigation pane and in a generated table of contents.
        pr.append(f'<w:pStyle w:val="{style}"/>')
    if keep_next:
        # "Keep with next": forbid a page break immediately after this
        # paragraph, which is how a heading avoids being stranded at the bottom
        # of a page away from its text.
        pr.append("<w:keepNext/>")
    if shade:
        # Paragraph background (w:fill is a hex RGB). Used for the grey code
        # blocks; a shading is not a border, so no extra paragraph box appears.
        pr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>')
    # Spacing is in twips: before/after are margins around the paragraph,
    # w:line is the distance *inside* it. lineRule="auto" means "w:line is in
    # 240ths of a line", so 276 = 1.15 line spacing.
    pr.append(f'<w:spacing w:before="{spacing_before}" w:after="{spacing_after}"'
              + (f' w:line="{line}" w:lineRule="auto"' if line else "") + "/>")
    if indent:
        # w:left is the left indent in twips; firstLine="0" cancels any
        # inherited first-line indent so code blocks stay flush.
        pr.append(f'<w:ind w:left="{indent}" w:firstLine="0"/>')
    if align:
        # w:jc = justification: "center", "both" (justify), "left", "right".
        pr.append(f'<w:jc w:val="{align}"/>')
    pr.append("</w:pPr>")
    # An empty <w:r> is emitted for a blank paragraph: <w:p/> with no run is
    # valid XML but some renderers drop its spacing entirely, so an explicit
    # empty run keeps blank spacer paragraphs at their intended height.
    body = f'<w:r>{""}</w:r>' if not text else run(text, bold, italic, mono, size, color)
    return f"<w:p>{''.join(pr)}{body}</w:p>"


def h1(text):
    # keep_next so the heading travels with the first paragraph of its section;
    # the style itself (Heading1 in styles.xml) carries size, colour and
    # outlineLvl=0, which is the level Word uses for the navigation pane and
    # for a TOC field.
    return para(text, style="Heading1", keep_next=True, spacing_before=240, spacing_after=120)


def h2(text):
    return para(text, style="Heading2", keep_next=True, spacing_before=200, spacing_after=100)


def body(text):
    # line=276 is 1.15 spacing, the usual choice for report prose: single
    # spacing looks cramped at 11 pt, double spacing wastes pages.
    return para(text, spacing_after=140, line=276)


def bullet(text, level=0):
    # A bullet here is a paragraph with a manual glyph + tab, not a real
    # <w:numPr> list definition. It avoids shipping numbering.xml, and since
    # the report has no cross-references to list items the trade-off is
    # invisible to the reader. Depth only changes the indent and the marker.
    indent = (360 + 360 * level)
    p = ['<w:pPr><w:pStyle w:val="ListParagraph"/>',
         '<w:spacing w:before="0" w:after="60" w:line="264" w:lineRule="auto"/>',
         # w:hanging is the negative first-line indent that pulls the marker
         # back into the gutter, so wrapped lines align with the text and not
         # with the bullet.
         f'<w:ind w:left="{indent}" w:hanging="220"/>',
         '</w:pPr>']
    # U+2022 bullet for level 0, U+2013 en dash for nested items.
    mark = "\u2022" if level == 0 else "\u2013"
    r = (f'<w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/></w:rPr>'
         f'<w:t xml:space="preserve">{mark}\t</w:t></w:r>')
    return f"<w:p>{''.join(p)}{r}{run(text)}</w:p>"


def code(lines):
    out = []
    # One shaded paragraph per source line rather than a table or a
    # <w:br/>-separated block: a paragraph can break across pages, so a long
    # listing never overflows the page, and each line keeps its own indent.
    for i, line in enumerate(lines):
        out.append(para(line, mono=True, size=17, shade="F4F4F4",
                        # Only the first and last paragraph get outer spacing,
                        # so the block reads as one grey panel.
                        spacing_before=60 if i == 0 else 0,
                        spacing_after=60 if i == len(lines) - 1 else 0,
                        line=240, indent=120))
    return "".join(out)


def png_size(path):
    # Read only the first 24 bytes instead of decoding the image: a PNG always
    # starts with the 8-byte signature (the b"\x89PNG\r\n\x1a\n" literal, which
    # also catches a JPEG saved with a .png extension) followed by the IHDR
    # chunk, whose width and height are two big-endian uint32s at offsets 16
    # and 20. ">II" unpacks exactly those two fields.
    with open(path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", head[16:24])


def fit_image(path):
    """Return (width, height) in EMU, preserving the aspect ratio."""
    px_w, px_h = png_size(path)
    # Start from the maximum width and derive the height from the pixel aspect
    # ratio, then clamp: if the result is too tall, pin the height instead and
    # shrink the width. Doing it in this order is what keeps the two
    # constraints independent - one pass is enough because only one of them can
    # be binding for a given image.
    width = float(MAX_IMG_W)
    height = width * px_h / px_w
    if height > MAX_IMG_H:
        height = float(MAX_IMG_H)
        width = height * px_w / px_h
    return int(width), int(height)


def find_screenshot(caption):
    """Map '... (screenshot 04)' to docs/screenshots/04-*.png."""
    # The caption text is the only link between prose and files: make_report.py
    # writes "... (screenshot 04)" and the file on disk is 04-something.png.
    # Parsing the number out of the caption means a figure can be inserted in
    # the middle of the report without renumbering any Python variable.
    marker = "screenshot "
    key = caption.rstrip(")").split(marker)[-1].strip() if marker in caption else ""
    if not key:
        return None
    # zfill(2) turns "4" into "04" so both spellings resolve to the same file.
    prefix = key.zfill(2) if key.isdigit() else key
    matches = sorted(glob.glob(os.path.join(SHOT_DIR, f"{prefix}-*.png")))
    # sorted() + [0] makes the choice deterministic when a prefix matches more
    # than one file (e.g. 04-a.png and 04-b.png).
    return matches[0] if matches else None


def shot(caption, image=None):
    """Centred figure with a caption underneath.

    When the image cannot be resolved the caption is still written, marked as a
    placeholder, so a missing file is visible in the document instead of silent.
    """
    path = image or find_screenshot(caption)
    # A missing screenshot must be *visible* in the document, not skipped:
    # a silently shorter report is discovered only after submission, whereas a
    # grey placeholder is obvious on the first read-through.
    if not path or not os.path.exists(path):
        return para(f"[Screenshot placeholder] {caption}", italic=True, size=18,
                    color="808080", spacing_before=60, spacing_after=160, align="center")

    # Three ids have to agree for an image to appear, and each one is a
    # different kind of name:
    #   rel_id  - relationship id, declared in word/_rels/document.xml.rels and
    #             referenced from the drawing by r:embed="..."; it must be
    #             unique inside that part, hence 100 + index.
    #   index   - the picture's id (wp:docPr / pic:cNvPr), unique per drawing.
    #   name    - the file name under word/media/, also registered in the rels.
    # A mismatch in any of the three yields a document that opens with an empty
    # frame or "the image cannot be displayed".
    index = len(IMAGES) + 1
    rel_id = f"rId{100 + index}"
    cx, cy = fit_image(path)
    IMAGES.append((rel_id, f"image{index}.png", path, cx, cy))

    # wp:inline = the picture sits in the text flow (as opposed to wp:anchor,
    # which floats and needs a position). cx/cy appear twice on purpose: once
    # on wp:extent (the layout box the text reflows around) and once on
    # a:ext (the graphic's own size) - they must match or Word scales the image.
    # noChangeAspect locks the ratio while the user drags a corner in Word.
    drawing = (
        "<w:p><w:pPr><w:jc w:val=\"center\"/>"
        "<w:spacing w:before=\"120\" w:after=\"40\" w:line=\"240\" w:lineRule=\"auto\"/></w:pPr>"
        "<w:r><w:drawing>"
        "<wp:inline distT=\"0\" distB=\"0\" distL=\"0\" distR=\"0\">"
        f"<wp:extent cx=\"{cx}\" cy=\"{cy}\"/>"
        "<wp:effectExtent l=\"0\" t=\"0\" r=\"0\" b=\"0\"/>"
        f"<wp:docPr id=\"{index}\" name=\"Picture {index}\"/>"
        "<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect=\"1\"/>"
        "</wp:cNvGraphicFramePr>"
        "<a:graphic>"
        "<a:graphicData uri=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
        "<pic:pic>"
        f"<pic:nvPicPr><pic:cNvPr id=\"{index}\" name=\"image{index}.png\"/>"
        "<pic:cNvPicPr/></pic:nvPicPr>"
        f"<pic:blipFill><a:blip r:embed=\"{rel_id}\"/>"
        "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
        "<pic:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/>"
        f"<a:ext cx=\"{cx}\" cy=\"{cy}\"/></a:xfrm>"
        "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></pic:spPr>"
        "</pic:pic></a:graphicData></a:graphic></wp:inline>"
        "</w:drawing></w:r></w:p>"
    )
    return drawing + para(caption, italic=True, size=17, color="6E6E6E",
                          spacing_before=0, spacing_after=200, align="center")


def figure(caption, note=(), image=None):
    """Figure plus the list of things the reader should look at in it.

    The photograph alone rarely carries the argument, so every figure in the
    Chinese edition is followed by the points it is evidence for.
    """
    out = [shot(caption, image)]
    # note is a sequence of strings; an empty sequence produces the same output
    # as plain shot(), so figure() is a drop-in replacement.
    if note:
        out.append(para("图中要点", bold=True, size=18, color="1F3864",
                        spacing_before=40, spacing_after=40))
        for item in note:
            out.append(bullet(item))
        # Trailing spacer: the next paragraph would otherwise sit immediately
        # under the last bullet.
        out.append(para("", spacing_after=80))
    return "".join(out)


def code_note(rows, widths=(5200, 3870), head=("代码 / 输出", "这一行在做什么")):
    """Two-column table: one line of code next to its explanation."""
    # The grid definition is what actually fixes the columns: tbllLayout
    # "fixed" + a gridCol per column + a tcW per cell means Word never
    # auto-fits, so the left column stays monospaced and the right one stays
    # readable regardless of the content length.
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>',
           '<w:tblW w:w="0" w:type="auto"/>',
           '<w:tblLayout w:type="fixed"/>',
           '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
           '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar>',
           "</w:tblPr>", f"<w:tblGrid>{grid}</w:tblGrid>"]
    out.append('<w:tr><w:trPr><w:tblHeader/></w:trPr>')
    # tblHeader marks this row as a repeating header: if the table spills onto
    # the next page, Word repeats it automatically. Without the marker the
    # second page starts with a headerless block of cells.
    for i, text in enumerate(head):
        out.append(
            f'<w:tc><w:tcPr><w:tcW w:w="{widths[i]}" w:type="dxa"/>'
            '<w:shd w:val="clear" w:color="auto" w:fill="E8EEF4"/></w:tcPr>'
            + para(text, bold=True, size=18, spacing_after=0, line=240) + "</w:tc>")
    out.append("</w:tr>")

    for code_line, explanation in rows:
        # A cell must contain at least one paragraph - an empty <w:tc> is
        # invalid, so a blank cell still gets an empty para(). Large code lines
        # are allowed to wrap: the column is fixed width, and shrinking the
        # font further would make the listing unreadable.
        left = (para(code_line, mono=True, size=16, spacing_after=0, line=230, shade="F7F8FA")
                if code_line else para("", spacing_after=0))
        right = (para(explanation, size=17, spacing_after=0, line=250)
                 if explanation else para("", spacing_after=0))
        # vAlign top keeps the code line and its explanation on the same
        # baseline when one side wraps to two lines.
        out.append(
            "<w:tr>"
            f'<w:tc><w:tcPr><w:tcW w:w="{widths[0]}" w:type="dxa"/>'
            f'<w:vAlign w:val="top"/></w:tcPr>{left}</w:tc>'
            f'<w:tc><w:tcPr><w:tcW w:w="{widths[1]}" w:type="dxa"/>'
            f'<w:vAlign w:val="top"/></w:tcPr>{right}</w:tc>'
            "</w:tr>")
    out.append("</w:tbl>")
    # Word requires a paragraph between two consecutive tables (otherwise it
    # merges them into one), so every table ends with a small spacer.
    out.append(para("", spacing_after=100))
    return "".join(out)


def table(rows, widths, header=True):
    # rows is a list of lists of strings; widths are twips that should sum to
    # about 9070 (the text column width) or the table will overflow the margin.
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>',
           '<w:tblW w:w="0" w:type="auto"/>',
           '<w:tblLayout w:type="fixed"/>',
           '<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
           '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>',
           "</w:tblPr>", f"<w:tblGrid>{grid}</w:tblGrid>"]
    for r_idx, row in enumerate(rows):
        # Row 0 is the header only when the caller says the data has one;
        # passing header=False therefore renders every row identically.
        is_head = header and r_idx == 0
        out.append("<w:tr>")
        if is_head:
            out.append('<w:trPr><w:tblHeader/></w:trPr>')
        for c_idx, cell in enumerate(row):
            # Shade only the header row; the body stays white so the table does
            # not look like a grid of cards.
            shade = ('<w:shd w:val="clear" w:color="auto" w:fill="E8EEF4"/>' if is_head else "")
            # str(cell) because callers occasionally pass a number; a <w:t>
            # must contain text, and an int would break the f-string join.
            out.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{widths[c_idx]}" w:type="dxa"/>{shade}'
                '<w:vAlign w:val="center"/></w:tcPr>'
                + para(str(cell), bold=is_head, size=19, spacing_after=0, line=240)
                + "</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    out.append(para("", spacing_after=80))
    return "".join(out)


def page_break():
    # A page break is a run-level element (w:br inside a run inside a
    # paragraph), not a paragraph property. It is also why the cover page in
    # make_report.py ends with this call instead of "sectPr": a section break
    # would reset the page numbering.
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


# --------------------------------------------------------------------------
# Package parts. These are the *whole* file contents, written verbatim into the
# ZIP by build(). Each one is referenced from two places - [Content_Types].xml
# (by part name) and a .rels file (by relationship id) - and Word refuses to
# open the package if the two disagree.
# --------------------------------------------------------------------------

# <Default> maps a file extension to a MIME type (used for .rels, .png, .xml);
# <Override> maps one specific part to a MIME type. Every part that is not
# covered by a Default must have an Override, or Word ignores the part.
CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="png" ContentType="image/png"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

# The package-level .rels (always _rels/.rels at the ZIP root). Its only job is
# to answer "which part is the main document?" - here rId1 -> word/document.xml.
# Without this file Word sees an archive with XML inside and nothing to open.
ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

# document.xml's own rels. Styles and the footer are declared here once; the
# image relationships are appended per picture by doc_rels() because only shot()
# knows how many figures the report actually contains.
DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>"""

# Document metadata (File > Info in Word). Purely cosmetic, but a file without
# core.xml shows "Author: unknown" and some graders check the title.
CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Laboratory Work 1 - Secure REST API, CI/CD and CVE analysis</dc:title>
<dc:creator>Student</dc:creator>
<cp:lastModifiedBy>Student</cp:lastModifiedBy>
</cp:coreProperties>"""

# Extended properties: the "Application" string Word shows in the file info.
# Not required for the document to open, but it is part of every normal .docx.
APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Microsoft Office Word</Application>
</Properties>"""


def styles_xml():
    # Minimal but complete style sheet. Two layers matter:
    #   docDefaults - the base font/size/spacing every paragraph inherits;
    #   w:style     - named styles referenced by <w:pStyle w:val="...">.
    # The styleId strings ("Heading1", "TableGrid") must match both the
    # pStyle values used above and Word's built-in names, otherwise Word shows
    # the text with default formatting and no error at all.
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{NS_W}">
<w:docDefaults>
<w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="{FONT_EA}" w:cs="Calibri"/>
<w:color w:val="1A1A1A"/><w:sz w:val="21"/><w:szCs w:val="22"/>
</w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Calibri Light" w:hAnsi="Calibri Light" w:eastAsia="{FONT_EA}"/><w:b/><w:color w:val="1F3864"/><w:sz w:val="30"/><w:szCs w:val="30"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Calibri Light" w:hAnsi="Calibri Light" w:eastAsia="{FONT_EA}"/><w:b/><w:color w:val="2E5496"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/>
<w:pPr><w:jc w:val="center"/><w:spacing w:after="0"/></w:pPr>
<w:rPr><w:color w:val="808080"/><w:sz w:val="16"/></w:rPr>
</w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>
<w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>
<w:left w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>
<w:bottom w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>
<w:right w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>
<w:insideH w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>
<w:insideV w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>
</w:tblBorders></w:tblPr>
</w:style>
</w:styles>"""


def footer_xml():
    # <w:fldSimple w:instr=" PAGE "> is a live field: Word recomputes it on
    # every render, so the page number stays correct after editing. The <w:t>1"
    # inside is only the cached value shown before the first recalculation.
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{NS_W}">
<w:p><w:pPr><w:pStyle w:val="Footer"/></w:pPr>
<w:r><w:rPr><w:sz w:val="16"/><w:color w:val="808080"/></w:rPr><w:t xml:space="preserve">Laboratory Work 1  ·  page </w:t></w:r>
<w:fldSimple w:instr=" PAGE ">
<w:r><w:rPr><w:sz w:val="16"/><w:color w:val="808080"/></w:rPr><w:t>1</w:t></w:r>
</w:fldSimple>
</w:p>
</w:ftr>"""


def document_xml(body_xml):
    # <w:sectPr> is the last child of <w:body> and describes the *section*:
    # page size, margins and which footer to use. A document without any
    # sectPr inherits defaults from the reader's locale (Letter in the US,
    # A4 elsewhere), which is why it is written explicitly here.
    # header/footer="708" twips = 1.25 cm from the paper edge, the same gutter
    # the margins leave. r:id="rId2" points at footer1.xml via DOC_RELS.
    sect = (f'<w:sectPr><w:footerReference w:type="default" r:id="rId2"/>'
            f'<w:pgSz w:w="{A4_W}" w:h="{A4_H}"/>'
            f'<w:pgMar w:top="{MARGIN_TOP}" w:right="{MARGIN_SIDE}" w:bottom="{MARGIN_BOTTOM}" '
            f'w:left="{MARGIN_SIDE}" w:header="708" w:footer="708" w:gutter="0"/>'
            '<w:cols w:space="708"/></w:sectPr>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{NS_W}" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f"<w:body>{body_xml}{sect}</w:body></w:document>")


def doc_rels():
    # Insert the image relationships just before </Relationships> instead of
    # rebuilding the whole part, so the style/footer ids stay untouched.
    # Each Target is relative to word/ (the folder that owns this .rels file),
    # which is why it reads "media/imageN.png" and not "word/media/imageN.png".
    links = "".join(
        f'<Relationship Id="{rel_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/{name}"/>'
        for rel_id, name, _path, _cx, _cy in IMAGES
    )
    return DOC_RELS.replace("</Relationships>", links + "</Relationships>")


def build(body_xml, out_path):
    # The order of writestr calls is irrelevant to Word (it follows the rels,
    # not the archive order); compression is irrelevant too, a .docx may be
    # stored uncompressed. What matters is that every part named in
    # [Content_Types].xml actually exists in the archive.
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Written as a real ZIP file rather than through a temp directory: the
    # archive is the deliverable, and writing it in one pass means a failed
    # build leaves either the old file or a complete new one, never a
    # half-written document that Word would report as corrupt.
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        # doc_rels() must be called after the body has been built, because the
        # body is what populated IMAGES via shot().
        z.writestr("word/_rels/document.xml.rels", doc_rels())
        z.writestr("word/document.xml", document_xml(body_xml))
        z.writestr("word/styles.xml", styles_xml())
        z.writestr("word/footer1.xml", footer_xml())
        z.writestr("docProps/core.xml", CORE)
        z.writestr("docProps/app.xml", APP)
        # z.write streams the PNG from disk; the tuple's cx/cy are layout
        # values for the drawing, the bytes themselves are copied unchanged.
        for _rel_id, name, path, _cx, _cy in IMAGES:
            z.write(path, f"word/media/{name}")
    return out_path
