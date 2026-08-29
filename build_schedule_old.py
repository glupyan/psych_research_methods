#!/usr/bin/env python3
"""
build_schedule.py (v13)

- Expands date macros:
    * new: `r advdate(lecture, 2)` / `r advdate(section, 2)` (Wednesdays/Mondays), using base dates
      parsed from the markdown (lecture <- as.Date("YYYY-MM-DD"), section <- as.Date("YYYY-MM-DD")).
- Replaces @keys with clickable/hoverable popovers containing APA-style HTML
  references (DOI/URL clickable) and a "Copy reference" button (plain-text APA).
- In-text citation label is APA-style: "Author (Year)".
- Year handling:
    * "YYYY-MM" or "YYYY-MM-DD" -> "YYYY"
    * "YYYY" -> "YYYY"
    * literal "in press"/"forthcoming" preserved (also if present in note)
- Popover HTML includes a publication container (journal/booktitle/publisher/
  howpublished/institution/organization/school/series/eprinttype or URL host).
"""
import argparse, re, os, unicodedata, html
from typing import Dict, Tuple, List, Set
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

# ---------------- Utilities ----------------
def slugify_id(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def strip_title_braces(title: str) -> str:
    return title.replace("{", "").replace("}", "")

def split_top_level(text: str, sep: str = ",") -> List[str]:
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth-1)
        if ch == sep and depth == 0:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts

# ---------------- .bib parsing ----------------
def parse_bib(bib_text: str) -> Dict[str, Dict]:
    entries = {}
    i, n = 0, len(bib_text)
    while True:
        at = bib_text.find("@", i)
        if at == -1: break
        j = at+1
        while j < n and bib_text[j].isalpha(): j += 1
        etype = bib_text[at+1:j].lower()
        while j < n and bib_text[j] != "{": j += 1
        if j >= n: break
        start = j; depth = 0; k = j
        while k < n:
            ch = bib_text[k]
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    k += 1; break
            k += 1
        block = bib_text[at:k]; i = k
        try:
            brace = block.find("{"); comma = block.find(",", brace+1)
            key = block[brace+1:comma].strip()
        except Exception:
            continue
        fields = {}
        rest = block[comma+1:].strip()
        if rest.endswith("}"): rest = rest[:-1]
        for pair in split_top_level(rest, sep=","):
            if "=" not in pair: continue
            name, val = pair.split("=", 1)
            name = name.strip().lower(); val = val.strip().strip(",").strip()
            if val.startswith("{") and val.endswith("}"):
                val = val[1:-1].strip()
            elif val.startswith('"') and val.endswith('"'):
                val = val[1:-1].strip()
            fields[name] = val
        entries[key] = {"type": etype, "key": key, "fields": fields}
    return entries

# ---------------- Authors ----------------
def parse_structured_author(token: str):
    """family=Maas, given=Han L. J., prefix=van der, useprefix=true"""
    attrs = {}
    for piece in split_top_level(token, sep=","):
        if "=" in piece:
            k, v = piece.split("=", 1)
            attrs[k.strip().lower()] = v.strip()
    family = attrs.get("family", "").strip()
    given = attrs.get("given", "").strip()
    prefix = attrs.get("prefix", "").strip()
    useprefix = attrs.get("useprefix", "").lower() in ("true","1","yes")
    last_for_intext = (prefix + " " if useprefix and prefix else "") + family if family else family or prefix
    initials = " ".join([p[0] + "." for p in given.split() if p])
    full_apa = f"{family}, {initials}".strip().rstrip(",")
    if prefix:
        full_apa = f"{prefix} {full_apa}"
    return last_for_intext.strip(), full_apa.strip()

def parse_person(token: str):
    token = token.strip()
    if "family=" in token and "given=" in token:
        return parse_structured_author(token)
    if "," in token:
        last, firsts = [x.strip() for x in token.split(",", 1)]
    else:
        parts = token.split(); last = parts[-1]; firsts = " ".join(parts[:-1])
    initials = " ".join([p[0] + "." for p in firsts.split() if p])
    return last, f"{last}, {initials}".strip().rstrip(",")

def format_authors(author_field: str) -> Tuple[str, str]:
    raw = [a.strip() for a in author_field.split(" and ") if a.strip()]
    last_names, full_list = [], []
    for tok in raw:
        last, full = parse_person(tok)
        last_names.append(last); full_list.append(full)
    if len(last_names)==0:
        in_author=""
    elif len(last_names)==1:
        in_author=last_names[0]
    elif len(last_names)==2:
        in_author=f"{last_names[0]} & {last_names[1]}"
    else:
        in_author=f"{last_names[0]} et al."
    if len(full_list)==1: full_authors=full_list[0]
    elif len(full_list)==2: full_authors=f"{full_list[0]} & {full_list[1]}"
    else: full_authors=", ".join(full_list[:-1]) + f", & {full_list[-1]}"
    return in_author, full_authors

# ---------------- APA-ish formatter ----------------
def format_year(fields: Dict[str,str]) -> str:
    y = (fields.get("year") or fields.get("date") or "").strip()
    if y:
        y_clean = y.replace("{","").replace("}","").strip()
        # ISO-like date -> take leading year
        m_iso = re.match(r'^(\d{4})(?:[-/ ].*)?$', y_clean)
        if m_iso:
            return m_iso.group(1)
        if re.fullmatch(r'\d{4}', y_clean):
            return y_clean
        if re.search(r'\b(in\s+press|forthcoming)\b', y_clean, re.I):
            return y_clean
        m_any = re.search(r'(\d{4})', y_clean)
        if m_any:
            return m_any.group(1)
        return y_clean
    note = (fields.get("note") or "").replace("{","").replace("}","").strip()
    if note:
        m2 = re.search(r'\b(in\s+press|forthcoming)\b', note, re.I)
        if m2: return m2.group(1)
    return "n.d."

def apa_html_and_plain(entry: Dict) -> Tuple[str, str, str]:
    f = entry["fields"]; et = entry["type"]
    authors = f.get("author", "")
    in_author, full_authors = format_authors(authors) if authors else ("", "")
    year = format_year(f)
    title = strip_title_braces(f.get("title", "").rstrip("."))

    doi = f.get("doi", "").strip()
    url = f.get("url", "").strip()
    pages = f.get("pages", "").replace("--", "–")
    volume = f.get("volume", "")
    number = f.get("number", "") or f.get("issue", "")
    publisher = f.get("publisher", "")
    # Journal/container detection includes BibLaTeX fields
    journal = (f.get("journal") or f.get("journaltitle") or f.get("shortjournal") or f.get("booktitle") or "")
    howpub = f.get("howpublished") or ""
    institution = f.get("institution") or ""
    organization = f.get("organization") or ""
    school = f.get("school") or ""
    series = f.get("series") or ""
    eprinttype = (f.get("eprinttype") or f.get("archiveprefix") or "").strip()
    eprint = (f.get("eprint") or "").strip()

    container = ""
    if et in ("article","articleinpress","incollection","inproceedings","conference"):
        if journal and volume and number and pages:
            container = f"<em>{html.escape(journal)}</em>, <em>{html.escape(volume)}</em>({html.escape(number)}), {html.escape(pages)}."
        elif journal and volume and pages:
            container = f"<em>{html.escape(journal)}</em>, <em>{html.escape(volume)}</em>, {html.escape(pages)}."
        elif journal and pages:
            container = f"<em>{html.escape(journal)}</em>, {html.escape(pages)}."
        elif journal:
            container = f"<em>{html.escape(journal)}</em>."
    elif et in ("book","inbook"):
        if publisher:
            container = f"{html.escape(publisher)}."
    else:
        if journal:
            container = f"<em>{html.escape(journal)}</em>."
        elif howpub:
            container = f"<em>{html.escape(howpub)}</em>."
        elif institution:
            container = f"<em>{html.escape(institution)}</em>."
        elif organization:
            container = f"<em>{html.escape(organization)}</em>."
        elif school:
            container = f"<em>{html.escape(school)}</em>."
        elif series:
            container = f"<em>{html.escape(series)}</em>."
        elif eprinttype:
            label = eprinttype.upper()
            if label == "ARXIV" and eprint:
                container = f"<em>arXiv</em> {html.escape(eprint)}."
            else:
                container = f"<em>{html.escape(label.title())}</em>."
        else:
            host = ""
            if url:
                try:
                    host = urlparse(url).netloc
                except Exception:
                    host = ""
            if host:
                host_simple = host.lower().split(":")[0]
                if host_simple.startswith("www."):
                    host_simple = host_simple[4:]
                base = host_simple.split(".")[0]
                container = f"<em>{html.escape(base.title())}</em>."

    parts_html, parts_plain = [], []
    if full_authors:
        parts_html.append(f"{html.escape(full_authors)} ({html.escape(year)}).")
        parts_plain.append(f"{full_authors} ({year}).")
    else:
        parts_html.append(f"({html.escape(year)}).")
        parts_plain.append(f"({year}).")
    if title:
        parts_html.append(f"{html.escape(title)}."); parts_plain.append(f"{title}.")
    if container:
        # strip tags for plain
        parts_html.append(container); parts_plain.append(re.sub(r"<[^>]+>", "", container))
    if doi:
        doi_url = "https://doi.org/" + doi.lstrip("https://doi.org/")
        parts_html.append(f'<a href="{html.escape(doi_url)}" target="_blank" rel="noopener">{html.escape(doi_url)}</a>')
        parts_plain.append(doi_url)
    elif url:
        parts_html.append(f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(url)}</a>')
        parts_plain.append(url)

    full_html = " ".join(p for p in parts_html if p and p.strip())
    full_plain = " ".join(p for p in parts_plain if p and p.strip())

    # In-text APA style
    intext = f"{in_author} ({year})" if in_author else f"({year})"
    return intext, full_html, full_plain

# ---------------- Citation expansion ----------------
CITE_RE = re.compile(r"(?<![A-Za-z0-9_@])@([A-Za-z0-9_:+./-]+)")

def collect_keys(md: str) -> Set[str]:
    return set(m.group(1) for m in CITE_RE.finditer(md))

def inject_popovers(md: str, citations: Dict[str, Tuple[str,str,str]]) -> str:
    def repl(m):
        key = m.group(1)
        if key not in citations: return m.group(0)
        intext, full_html, plain = citations[key]
        data_ref = html.escape(full_html, quote=True)
        data_plain = html.escape(plain, quote=True)
        return f'<a href="javascript:void(0)" class="cite-pop" role="button" tabindex="0" data-ref="{data_ref}" data-plain="{data_plain}">{intext}</a>'
    md = CITE_RE.sub(repl, md)
    # \cite{K1,K2} style
    def repl_cite(m):
        keys = [kk.strip() for kk in m.group(1).split(",")]
        pieces = []
        for k in keys:
            if k in citations:
                intext, full_html, plain = citations[k]
                data_ref = html.escape(full_html, quote=True)
                data_plain = html.escape(plain, quote=True)
                pieces.append(f'<a href="javascript:void(0)" class="cite-pop" role="button" tabindex="0" data-ref="{data_ref}" data-plain="{data_plain}">{intext}</a>')
            else:
                pieces.append(k)
        return "(" + "; ".join(pieces) + ")"
    md = re.sub(r"\\cite[t|p|year|author]*\\s*\\{([^}]+)\\}", repl_cite, md)
    return md

# ---------------- Date preprocessor ----------------
# Match inline R-style code:
#   `r advdate(lecture, 2)`      (new; Wednesdays)
#   `r advdate(section, 2)`      (new; Mondays)
#

# --- new (lecture/section) ---
DATE_INLINE_LECTURE = re.compile(r"`r\s+advdate\s*\(\s*lecture\s*,\s*(\d+)\s*\)`", re.IGNORECASE)
DATE_BARE_LECTURE   = re.compile(r"\badvdate\s*\(\s*lecture\s*,\s*(\d+)\s*\)", re.IGNORECASE)

DATE_INLINE_SECTION = re.compile(r"`r\s+advdate\s*\(\s*section\s*,\s*(\d+)\s*\)`", re.IGNORECASE)
DATE_BARE_SECTION   = re.compile(r"\badvdate\s*\(\s*section\s*,\s*(\d+)\s*\)", re.IGNORECASE)

# CHANGE: parse lecture/section base dates directly from the markdown when present
BASE_DATE_LECTURE = re.compile(
    r"^\s*lecture\s*<-\s*as\.Date\(\s*\"(\d{4}-\d{2}-\d{2})\"\s*\)",
    re.IGNORECASE | re.MULTILINE,
)
BASE_DATE_SECTION = re.compile(
    r"^\s*section\s*<-\s*as\.Date\(\s*\"(\d{4}-\d{2}-\d{2})\"\s*\)",
    re.IGNORECASE | re.MULTILINE,
)


# CHANGE: new formatters to mirror the Rmd's advdate() helper (mm/dd + fixed weekday labels)
def _format_lecture_from_n(n: int, lecture_dt: datetime) -> str:
    dt = lecture_dt + timedelta(days=7*(n-1))
    return f"Week {n:02d}, Tuesday, {dt.strftime('%m/%d')}"

def _format_section_from_n(n: int, section_dt: datetime) -> str:
    dt = section_dt + timedelta(days=7*(n-1))
    return f"Section: Thursday, {dt.strftime('%m/%d')}"

# CHANGE: extract base dates from markdown (fallbacks preserve old CLI behavior)
def _extract_base_dates(md: str, start_dt: datetime) -> Tuple[datetime, datetime]:
    """Return (lecture_dt, section_dt) datetimes with tzinfo.

    - If lecture/section base dates exist in the markdown (e.g. in an R setup chunk),
      we use them.
    - Otherwise:
        * section_dt falls back to the next Thursday after lecture_dt
          (so Tuesday lecture start -> following Thursday section start)
    """
    lecture_dt = start_dt
    m = BASE_DATE_LECTURE.search(md)
    if m:
        lecture_dt = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=start_dt.tzinfo)

    m2 = BASE_DATE_SECTION.search(md)
    if m2:
        section_dt = datetime.strptime(m2.group(1), "%Y-%m-%d").replace(tzinfo=start_dt.tzinfo)
    else:
        # days until next Monday (weekday 0)
        section_dt = lecture_dt + timedelta(days=(0 - lecture_dt.weekday()) % 7)

    return lecture_dt, section_dt

def preprocess_dates(md: str, start_dt: datetime) -> str:
    lecture_dt, section_dt = _extract_base_dates(md, start_dt)

    # CHANGE: expand new lecture/section shortcodes
    md = DATE_INLINE_LECTURE.sub(lambda m: _format_lecture_from_n(int(m.group(1)), lecture_dt), md)
    md = DATE_BARE_LECTURE.sub(lambda m: _format_lecture_from_n(int(m.group(1)), lecture_dt), md)
    md = DATE_INLINE_SECTION.sub(lambda m: _format_section_from_n(int(m.group(1)), section_dt), md)
    md = DATE_BARE_SECTION.sub(lambda m: _format_section_from_n(int(m.group(1)), section_dt), md)


    return md


# ---------------- Main ----------------
def main(inp: str, outp: str, bib_path: str, tz: str, start: str):
    if not os.path.exists(inp): raise SystemExit(f"[error] input not found: {inp}")
    if not os.path.exists(bib_path): raise SystemExit(f"[error] bib not found: {bib_path}")
    md = open(inp, "r", encoding="utf-8", errors="ignore").read()
    bib = open(bib_path, "r", encoding="utf-8", errors="ignore").read()

    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=ZoneInfo(tz))
    md1 = preprocess_dates(md, start_dt)

    entries = parse_bib(bib)
    keys = collect_keys(md1)
    citations: Dict[str, Tuple[str,str,str]] = {}
    for k in keys:
        e = entries.get(k)
        if not e: continue
        citations[k] = apa_html_and_plain(e)

    md2 = inject_popovers(md1, citations)

    with open(outp, "w", encoding="utf-8") as f:
        f.write(md2)
    print(f"[done] wrote {outp} with {len(citations)} popover references")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build schedule.md from schedule_bib.md by expanding dates and in-text popover citations.")
    ap.add_argument("--in", dest="inp", required=True, help="Path to schedule_bib.md")
    ap.add_argument("--out", dest="outp", required=True, help="Path to output schedule.md")
    ap.add_argument("--bib", required=True, help="Path to .bib (pruned or full)")
    ap.add_argument("--tz", default="America/Chicago", help="IANA timezone (default America/Chicago)")
    ap.add_argument("--start", default="2026-09-01", help="Start Tuesday YYYY-MM-DD (default 2026-09-01)")
    args = ap.parse_args()
    main(args.inp, args.outp, args.bib, args.tz, args.start)
