"""
Arma a mano un PDF mínimo con texto real.

Armarlo byte a byte permite controlar exactamente el texto, las fuentes y los
metadatos que trae, y así verificar lo que extrae el servicio.
"""


def build_pdf(
    *pages: str,
    font: str = "Helvetica",
    sizes: tuple[int, ...] = (),
    info: dict[str, str] | None = None,
) -> bytes:
    """PDF con una página por texto recibido (sólo ASCII), en cuerpo 12 salvo `sizes`.

    `info` es el diccionario de metadatos del PDF, por ejemplo {"Author": "Ana"}.
    """
    sizes = sizes or (12,) * len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        f"<< /Type /Font /Subtype /Type1 /BaseFont /{font} >>".encode(),
    ]
    for i, (text, size) in enumerate(zip(pages, sizes)):
        stream = f"BT /F1 {size} Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    info_ref = b""
    if info is not None:
        entries = " ".join(f"/{name} ({value})" for name, value in info.items())
        objects.append(f"<< {entries} >>".encode())
        info_ref = b" /Info %d 0 R" % len(objects)

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (number, body)

    xref_offset = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        pdf += b"%010d 00000 n \n" % offset
    pdf += b"trailer\n<< /Size %d /Root 1 0 R%s >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        info_ref,
        xref_offset,
    )
    return bytes(pdf)
