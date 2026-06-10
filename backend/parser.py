"""
Structured-field parser for scanned manufacturing forms.

Currently supports:
  F01009 — 生產入(出)庫單  (production in/out warehouse slip)
"""

from __future__ import annotations
import re


def _fix_num(s: str) -> str:
    """Fix common OCR digit substitutions: > → 2, O → 0, ( → 1."""
    return s.replace(">", "2").replace("O", "0").replace("(", "1").replace("（", "1")


# ---------------------------------------------------------------------------
# F01009 parser
# ---------------------------------------------------------------------------

_CATEGORIES = r"半成品|成品|在製品|原物料|包材|零件"
_UNITS = {"PCS", "pcs", "組", "组", "個", "个", "片", "捲", "卷", "KG", "SET", "箱", "包"}
_SKIP_KEYWORDS = {
    "以下", "流程", "申請", "申请", "品管", "主管", "倉管", "資材", "资材",
    "頁次", "页次", "序號", "序号", "字號", "品名", "庫別", "庫别", "庫区",
    "單位", "数量", "批號", "規格", "备注", "備注", "规格",
    # header / footer lines that leak into the lookback window
    "高登智慧", "高登料技", "股份有限公司", "生產入", "生產出", "庫單",
}


def _parse_item(segment: str, seq: str, category: str, post_anchor: str = "") -> dict:
    item: dict = {
        "seq": seq,
        "category": category,
        "part_no": None,
        "name": None,
        "warehouse": None,
        "unit": None,
        "qty": None,
        "batch_no": None,
        "spec": None,
    }

    # Part number: capital letter + 8-10 digits
    m = re.search(r"\b([A-Z]\d{8,10})\b", segment)
    if m:
        item["part_no"] = m.group(1)

    # Product name: line starting with the category's first char (半/成/在…)
    cat_char = re.escape(category[0])
    m = re.search(rf"({cat_char}[^\n]{{4,}})", segment)
    if m:
        item["name"] = m.group(1).strip()

    # Warehouse: 高登X倉/仓/食
    m = re.search(r"(高登[^\s，,。\n]{1,5}[倉仓食])", segment)
    if m:
        item["warehouse"] = m.group(1)

    # Unit
    m = re.search(
        r"\b(" + "|".join(re.escape(u) for u in _UNITS) + r")\b", segment
    )
    if m:
        item["unit"] = m.group(1)

    # Qty + batch: batch is always 7 digits; qty is the digits before it.
    # Try space-separated first, then concatenated (non-greedy qty).
    m = re.search(r"\b(\d{1,3})\s{1,3}(\d{7})\b", segment)
    if m:
        item["qty"] = int(m.group(1))
        item["batch_no"] = m.group(2)
    else:
        m = re.search(r"\b(\d{1,2})(\d{7})\b", segment)
        if m:
            item["qty"] = int(m.group(1))
            item["batch_no"] = m.group(2)

    # Spec: search only the post-anchor portion so header lines don't bleed in
    matched = {item["part_no"], item["name"], item["warehouse"], item["unit"]}
    batch_str = item["batch_no"] or ""
    spec_source = post_anchor if post_anchor else segment
    for line in spec_source.splitlines():
        line = line.strip()
        if not line or line in matched:
            continue
        if re.match(r"^\d+$", line) or re.match(r"^\d{4}", line):
            continue
        if batch_str and batch_str in line:
            continue
        if any(kw in line for kw in _SKIP_KEYWORDS):
            continue
        if len(line) > 3 and line != item["name"]:
            item["spec"] = line
            break

    return item


def parse_f01009(text: str) -> dict | None:
    """
    Parse F01009 生產入(出)庫單 fields from OCR text.

    Returns a dict of structured fields, or None if the text doesn't
    look like this form.
    """
    if not re.search(r"[生產入出庫]{3,}", text):
        return None

    result: dict = {
        "form": "F01009",
        "document_type": None,
        "document_no": None,
        "date": None,
        "inspection_no": None,
        "mo_no": None,
        "items": [],
    }

    # Document type — look for the standalone label line, not "生產入(出)庫單"
    if re.search(r"(?<!出\()入庫單", text):
        result["document_type"] = "入庫單"
    if re.search(r"出庫單(?!\))", text):
        result["document_type"] = "出庫單"

    # Document number: 13-digit number
    m = re.search(r"\b(\d{13})\b", text)
    if m:
        result["document_no"] = m.group(1)

    # Date
    m = re.search(r"(\d{4}[/\-]\d{2}[/\-]\d{2})", text)
    if m:
        result["date"] = m.group(1)

    # Inspection number QMO-…
    m = re.search(r"(QM[O0]-[\d>()（）]+)", text)
    if m:
        result["inspection_no"] = _fix_num(m.group(1))

    # Manufacturing order MO-… (not preceded by Q)
    m = re.search(r"(?<![QqM])(M[O0]-[\d>]+)", text)
    if m:
        result["mo_no"] = _fix_num(m.group(1)).replace("M0-", "MO-")

    # --- Line items ---
    anchor_re = re.compile(rf"(\d{{4}})({_CATEGORIES})")
    anchors = list(anchor_re.finditer(text))

    for i, anchor in enumerate(anchors):
        # Extend the segment 200 chars before the anchor so we catch
        # pre-anchor fields (column-order varies when table is read left-to-right)
        seg_start = max(0, anchor.start() - 200)
        seg_end = anchors[i + 1].start() if i + 1 < len(anchors) else len(text)
        stop = text.find("以下空白", anchor.start())
        if 0 <= stop < seg_end:
            seg_end = stop

        segment = text[seg_start:seg_end]
        post_anchor = text[anchor.end():seg_end]
        result["items"].append(_parse_item(segment, anchor.group(1), anchor.group(2), post_anchor))

    return result


# ---------------------------------------------------------------------------
# Dispatcher: try each known form parser in order
# ---------------------------------------------------------------------------

def parse_form(text: str) -> dict | None:
    """Try all known form parsers and return the first match, or None."""
    return parse_f01009(text)
