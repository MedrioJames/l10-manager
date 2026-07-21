"""Shared rounded-rectangle geometry for the app's hand-rolled canvas
widgets (see ui/rounded_card.py). One canvas polygon item traces the whole
shape - fill and outline both live on that single item, so a hover/active
color change is one itemconfigure() call rather than several arc/rectangle
items that could desync. There's no anti-aliasing available on a stdlib Tk
canvas (no Pillow in this app) - splinesteps is bumped to keep corners
reasonably smooth, and small radii are simply accepted as slightly
un-anti-aliased, consistent with the rest of the app's non-AA rendering
(e.g. the "clam" theme's own scrollbar arrows).
"""

SPLINESTEPS = 24


def rounded_rect_points(x0: float, y0: float, x1: float, y1: float, radius: float) -> list:
    """Point list for canvas.create_polygon(..., smooth=True, splinesteps=SPLINESTEPS)
    tracing a rounded rectangle from (x0, y0) to (x1, y1). radius is clamped
    to half the smaller dimension so it never turns the shape inside out."""
    radius = max(0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    return [
        x0 + radius, y0, x1 - radius, y0,
        x1, y0, x1, y0 + radius,
        x1, y1 - radius, x1, y1,
        x1 - radius, y1, x0 + radius, y1,
        x0, y1, x0, y1 - radius,
        x0, y0 + radius, x0, y0,
    ]
