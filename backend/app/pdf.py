"""A tiny text-only PDF writer (no dependencies): titled pages of monospaced lines."""
from __future__ import annotations

from typing import List

LINES_PER_PAGE = 60
WRAP = 95


def _esc(s: str) -> str:
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(lines: List[str]) -> List[str]:
    out = []
    for line in lines:
        while len(line) > WRAP:
            cut = line.rfind(" ", 0, WRAP)
            cut = cut if cut > 20 else WRAP
            out.append(line[:cut])
            line = "  " + line[cut:].lstrip()
        out.append(line)
    return out


def render(title: str, lines: List[str]) -> bytes:
    body = _wrap(lines)
    pages = [body[i:i + LINES_PER_PAGE] for i in range(0, max(len(body), 1), LINES_PER_PAGE)] or [[]]
    objects: List[bytes] = []
    font_id = 3
    page_ids = []
    for n, page in enumerate(pages):
        text = ["BT", "/F1 14 Tf", "50 760 Td", f"({_esc(title)}) Tj", "/F1 9 Tf", "0 -22 Td", "11 TL"]
        text += [f"({_esc(l)}) '" for l in page]
        text += ["0 -16 Td", f"(Page {n + 1} of {len(pages)}) Tj", "ET"]
        stream = "\n".join(text).encode("latin-1", "replace")
        content_id = 4 + 2 * n
        page_id = content_id + 1
        page_ids.append(page_id)
        objects.append((content_id, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
        objects.append((page_id, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
                                 f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()))
    head = [(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>".encode()),
            (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")]
    all_objs = sorted(head + objects)
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for oid, content in all_objs:
        offsets[oid] = len(out)
        out += f"{oid} 0 obj\n".encode() + content + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(all_objs) + 1}\n0000000000 65535 f \n".encode()
    for oid, _ in all_objs:
        out += f"{offsets[oid]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(all_objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
