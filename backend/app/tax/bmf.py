"""Qualified donee verification against the IRS Exempt Organizations Business Master File (EO BMF).

The EO BMF extract is public: https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf
(state files at https://www.irs.gov/pub/irs-soi/eo_<state>.csv; codes explained in
https://www.irs.gov/pub/foia/ig/tege/eo-info.pdf). Codes used here, from that information sheet:
  SUBSECTION 03 = 501(c)(3)
  FOUNDATION 04 = private non-operating foundation (not a qualified donee for IRC 170(e)(3))
  DEDUCTIBILITY 1 = contributions are deductible
An admin reviews the match and confirms. Manual checks: IRS Tax Exempt Organization Search.
"""
from __future__ import annotations

import csv
import io
import os
import re
from typing import Any, Dict, Iterable, Optional

import httpx
from sqlalchemy.orm import Session

from app import clock
from app.models import EOBMFRecord, ReceiverProfile

EO_BMF_URL = os.getenv("EO_BMF_URL", "https://www.irs.gov/pub/irs-soi/eo_fl.csv")
EO_BMF_INFO_URL = "https://www.irs.gov/pub/foia/ig/tege/eo-info.pdf"
TEOS_URL = "https://apps.irs.gov/app/eos/"


def digits(ein: Optional[str]) -> str:
    return re.sub(r"\D", "", ein or "")


def import_rows(db: Session, rows: Iterable[Dict[str, str]], source: str) -> int:
    """Replace records for the states present in this file."""
    batch, states = [], set()
    now = clock.now()
    for row in rows:
        ein = digits(row.get("EIN"))
        if len(ein) != 9:
            continue
        st = (row.get("STATE") or "").strip()[:2]
        states.add(st)
        batch.append(EOBMFRecord(ein=ein, name=(row.get("NAME") or "")[:200], street=(row.get("STREET") or "")[:200],
                                 city=(row.get("CITY") or "")[:100], state=st, zip=(row.get("ZIP") or "")[:12],
                                 subsection=(row.get("SUBSECTION") or "").strip()[:2],
                                 foundation=(row.get("FOUNDATION") or "").strip()[:2],
                                 deductibility=(row.get("DEDUCTIBILITY") or "").strip()[:1],
                                 status=(row.get("STATUS") or "").strip()[:2], source=source, imported_at=now))
    for st in states:
        db.query(EOBMFRecord).filter_by(state=st).delete()
    db.bulk_save_objects(batch)
    db.flush()
    return len(batch)


def import_csv_text(db: Session, text: str, source: str) -> int:
    return import_rows(db, csv.DictReader(io.StringIO(text)), source)


def fetch_and_import(db: Session, url: str = EO_BMF_URL) -> int:
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        text = r.read().decode("utf-8", "replace")
    return import_csv_text(db, text, f"{url} (downloaded {clock.now().date().isoformat()})")


def match(db: Session, profile: ReceiverProfile) -> Dict[str, Any]:
    ein = digits(profile.ein)
    rec = db.query(EOBMFRecord).filter_by(ein=ein).order_by(EOBMFRecord.imported_at.desc()).first() if ein else None
    org = profile.organization
    base = {"organization_id": org.id, "our_name": org.legal_name or org.name, "our_ein": profile.ein,
            "teos_url": TEOS_URL, "codes_reference": EO_BMF_INFO_URL}
    if rec is None:
        return {**base, "found": False, "message": "No EO BMF record for this EIN in the imported files. "
                                                   "Check the IRS Tax Exempt Organization Search manually."}
    checks = {"is_501c3": rec.subsection == "03", "not_private_nonoperating_foundation": rec.foundation != "04",
              "contributions_deductible": rec.deductibility == "1"}
    return {**base, "found": True, "record": {"ein": rec.ein, "name": rec.name, "street": rec.street, "city": rec.city,
                                               "state": rec.state, "zip": rec.zip, "subsection": rec.subsection,
                                               "foundation": rec.foundation, "deductibility": rec.deductibility,
                                               "source": rec.source},
            "checks": checks, "qualified_donee": all(checks.values())}
