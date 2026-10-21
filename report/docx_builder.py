"""Build a valid .docx for the Lab 1 report without third-party libraries.

A .docx file is an OPC package: a ZIP archive with a fixed set of XML parts.
Writing those parts directly keeps the build hermetic (no temp files, no
dependency on python-docx) while still producing a file Word/WPS opens natively.
"""

import glob
import os
import struct
import zipfile
from xml.sax.saxutils import escape

A4_W, A4_H = 11906, 16838
MARGIN_SIDE, MARGIN_TOP, MARGIN_BOTTOM = 1418, 1418, 1418

# Text area is 9070 twips wide (A4 minus two side margins). Figures are
# centred inside it and never taller than a third of the page, so a screenshot
# can never push a caption onto the next page on its own.
MAX_IMG_W = 5_700_000   # EMU (about 6.2 in)
MAX_IMG_H = 3_900_000   # EMU (about 4.3 in)

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# (relationship id, file name, path, width EMU, height EMU), filled by shot()
IMAGES = []
SHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "screenshots")



def run(text, bold=False, italic=False, mono=False, size=None, color=None):
    fonts = ""
    if mono:
        fonts = ('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>')
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
        props.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    props.append("</w:rPr>")
    rpr = "".join(props)
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(text="", style=None, bold=False, italic=False, mono=False, size=None,
         color=None, align=None, spacing_before=0, spacing_after=120,
         line=None, indent=None, shade=None, keep_next=False):
    pr = ["<w:pPr>"]
    if style:
        pr.append(f'<w:pStyle w:val="{style}"/>')
    if keep_next:
        pr.append("<w:keepNext/>")
    if shade:
        pr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>')
    pr.append(f'<w:spacing w:before="{spacing_before}" w:after="{spacing_after}"'
              + (f' w:line="{line}" w:lineRule="auto"' if line else "") + "/>")
    if indent:
        pr.append(f'<w:ind w:left="{indent}" w:firstLine="0"/>')
    if align:
        pr.append(f'<w:jc w:val="{align}"/>')
    pr.append("</w:pPr>")
    body = f'<w:r>{""}</w:r>' if not text else run(text, bold, italic, mono, size, color)
    return f"<w:p>{''.join(pr)}{body}</w:p>"


def h1(text):
    return para(text, style="Heading1", keep_next=True, spacing_before=240, spacing_after=120)


def h2(text):
    return para(text, style="Heading2", keep_next=True, spacing_before=200, spacing_after=100)


def body(text):
    return para(text, spacing_after=140, line=276)


def bullet(text, level=0):
    indent = (360 + 360 * level)
    p = ['<w:pPr><w:pStyle w:val="ListParagraph"/>',
         '<w:spacing w:before="0" w:after="60" w:line="264" w:lineRule="auto"/>',
         f'<w:ind w:left="{indent}" w:hanging="220"/>',
         '</w:pPr>']
    mark = "\u2022" if level == 0 else "\u2013"
    r = (f'<w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/></w:rPr>'
         f'<w:t xml:space="preserve">{mark}\t</w:t></w:r>')
    return f"<w:p>{''.join(p)}{r}{run(text)}</w:p>"


def code(lines):
    out = []
    for i, line in enumerate(lines):
        out.append(para(line, mono=True, size=17, shade="F4F4F4",
                        spacing_before=60 if i == 0 else 0,
                        spacing_after=60 if i == len(lines) - 1 else 0,
                        line=240, indent=120))
    return "".join(out)


def png_size(path):
    with open(path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", head[16:24])


def fit_image(path):
    """Return (width, height) in EMU, preserving the aspect ratio."""
    px_w, px_h = png_size(path)
    width = float(MAX_IMG_W)
    height = width * px_h / px_w
    if height > MAX_IMG_H:
        height = float(MAX_IMG_H)
        width = height * px_w / px_h
    return int(width), int(height)


def find_screenshot(caption):
    """Map '... (screenshot 04)' to docs/screenshots/04-*.png."""
    marker = "screenshot "
    key = caption.rstrip(")").split(marker)[-1].strip() if marker in caption else ""
    if not key:
        return None
    prefix = key.zfill(2) if key.isdigit() else key
    matches = sorted(glob.glob(os.path.join(SHOT_DIR, f"{prefix}-*.png")))
    return matches[0] if matches else None


def shot(caption, image=None):
    """Centred figure with a caption underneath.

    When the image cannot be resolved the caption is still written, marked as a
    placeholder, so a missing file is visible in the document instead of silent.
    """
    path = image or find_screenshot(caption)
    if not path or not os.path.exists(path):
        return para(f"[Screenshot placeholder] {caption}", italic=True, size=18,
                    color="808080", spacing_before=60, spacing_after=160, align="center")

    index = len(IMAGES) + 1
    rel_id = f"rId{100 + index}"
    cx, cy = fit_image(path)
    IMAGES.append((rel_id, f"image{index}.png", path, cx, cy))

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


def table(rows, widths, header=True):
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>',
           '<w:tblW w:w="0" w:type="auto"/>',
           '<w:tblLayout w:type="fixed"/>',
           '<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
           '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>',
           "</w:tblPr>", f"<w:tblGrid>{grid}</w:tblGrid>"]
    for r_idx, row in enumerate(rows):
        is_head = header and r_idx == 0
        out.append("<w:tr>")
        if is_head:
            out.append('<w:trPr><w:tblHeader/></w:trPr>')
        for c_idx, cell in enumerate(row):
            shade = ('<w:shd w:val="clear" w:color="auto" w:fill="E8EEF4"/>' if is_head else "")
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
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


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

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>"""

CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Laboratory Work 1 - Secure REST API, CI/CD and CVE analysis</dc:title>
<dc:creator>Student</dc:creator>
<cp:lastModifiedBy>Student</cp:lastModifiedBy>
</cp:coreProperties>"""

APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Microsoft Office Word</Application>
</Properties>"""


def styles_xml():
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{NS_W}">
<w:docDefaults>
<w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/>
<w:color w:val="1A1A1A"/><w:sz w:val="21"/><w:szCs w:val="22"/>
</w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Calibri Light" w:hAnsi="Calibri Light"/><w:b/><w:color w:val="1F3864"/><w:sz w:val="30"/><w:szCs w:val="30"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:next w:val="Normal"/><w:qFormat/>
<w:pPr><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Calibri Light" w:hAnsi="Calibri Light"/><w:b/><w:color w:val="2E5496"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>
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
    links = "".join(
        f'<Relationship Id="{rel_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/{name}"/>'
        for rel_id, name, _path, _cx, _cy in IMAGES
    )
    return DOC_RELS.replace("</Relationships>", links + "</Relationships>")


def build(body_xml, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/_rels/document.xml.rels", doc_rels())
        z.writestr("word/document.xml", document_xml(body_xml))
        z.writestr("word/styles.xml", styles_xml())
        z.writestr("word/footer1.xml", footer_xml())
        z.writestr("docProps/core.xml", CORE)
        z.writestr("docProps/app.xml", APP)
        for _rel_id, name, path, _cx, _cy in IMAGES:
            z.write(path, f"word/media/{name}")
    return out_path
