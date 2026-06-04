"""Convert dashboard SVG fragments to PNG data URIs for email embedding."""

from __future__ import annotations

import base64
from io import BytesIO

CHART_BG = "#0b0c0e"


def _cairosvg_png(svg: str, width: int) -> bytes | None:
    import cairosvg

    return cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=width,
        background_color=CHART_BG,
    )


def _svglib_png(svg: str, width: int) -> bytes | None:
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg

    drawing = svg2rlg(BytesIO(svg.encode("utf-8")))
    if drawing is None or not drawing.width:
        return None
    scale = width / float(drawing.width)
    drawing.width = width
    drawing.height = drawing.height * scale
    drawing.scale(scale, scale)
    return renderPM.drawToString(drawing, fmt="PNG")


def svg_to_png_data_uri(svg: str, *, width: int = 680) -> str | None:
    png: bytes | None = None
    for renderer in (_cairosvg_png, _svglib_png):
        try:
            png = renderer(svg, width)
        except Exception:
            png = None
        if png:
            break
    if not png:
        return None
    encoded = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{encoded}"
