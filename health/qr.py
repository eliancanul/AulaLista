"""Local QR rendering for AulaLista access URLs.

Segno performs the QR encoding locally (no CDN, network request, or remote
service).  We render its matrix ourselves so the HTML contract stays small,
keeps a visible white quiet zone, and exposes the encoded value for accessible
fallbacks and diagnostics.
"""

from html import escape

import segno


def _reed_solomon_generator(degree):
    """Keep the old small helper available to existing health checks.

    QR encoding is now delegated to Segno.  This helper remains deliberately
    dependency-free because older consumers imported it for a mathematical
    sanity check; it is not used to construct production symbols.
    """

    def gf_multiply(x, y):
        result = 0
        while y:
            if y & 1:
                result ^= x
            y >>= 1
            x <<= 1
            if x & 0x100:
                x ^= 0x11D
        return result

    generator = [1]
    factor = 1
    for _ in range(degree):
        next_generator = [0] * (len(generator) + 1)
        for position, coefficient in enumerate(generator):
            next_generator[position] ^= coefficient
            next_generator[position + 1] ^= gf_multiply(coefficient, factor)
        generator = next_generator
        factor = gf_multiply(factor, 2)
    return generator


def qr_matrix(text):
    """Return Segno's dark-module matrix for a byte-capable QR symbol.

    Error correction is explicitly M and ``boost_error=False`` prevents the
    encoder from silently changing that contract while selecting a version.
    ``micro=False`` guarantees a camera-compatible full QR symbol.
    """

    qr = segno.make(text, error="m", boost_error=False, micro=False)
    return tuple(tuple(bool(value) for value in row) for row in qr.matrix)


def qr_svg(text, border=4, module_size=6):
    """Render *text* as a high-contrast, camera-friendly inline SVG.

    ``border`` is measured in QR modules; four is the ISO-recommended quiet
    zone.  Keeping individual rectangles instead of relying on SVG strokes
    makes module boundaries and the white background deterministic in browsers
    and in raster-based QR readers.
    """

    if border < 4:
        raise ValueError("El QR necesita una zona blanca de al menos 4 módulos.")
    if module_size < 1:
        raise ValueError("El tamaño del módulo debe ser positivo.")

    matrix = qr_matrix(text)
    size = len(matrix)
    dimension = (size + border * 2) * module_size
    modules = []
    for row, values in enumerate(matrix):
        for column, value in enumerate(values):
            if value:
                modules.append(
                    f'<rect x="{(column + border) * module_size}" '
                    f'y="{(row + border) * module_size}" width="{module_size}" '
                    f'height="{module_size}"/>'
                )

    encoded = escape(text, quote=True)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Código QR para {encoded}" '
        f'viewBox="0 0 {dimension} {dimension}" width="{dimension}" '
        f'height="{dimension}" shape-rendering="crispEdges" '
        f'data-qr-value="{encoded}" data-qr-error="M" '
        f'data-qr-border="{border}">'
        f'<rect width="100%" height="100%" fill="white"/>'
        f'<g fill="black">{"".join(modules)}</g>'
        "</svg>"
    )
