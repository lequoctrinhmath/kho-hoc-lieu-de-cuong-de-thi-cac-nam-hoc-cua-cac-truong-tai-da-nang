#!/usr/bin/env python3
"""
Tự động dựng docs.json (danh sách tài liệu cho trang web) từ các file trong thư mục tai-lieu/.

Quy ước đặt tên file (không dấu, nối bằng dấu gạch dưới):
    <Loại đề>_Toan_<Khối>_<Tên trường>_<Năm học>[_<Ghi chú>].pdf / .docx
Ví dụ:
    De_Cuoi_Ki_1_Toan_8_Nguyen_Hue_2025-2026.pdf
    De_Cuong_On_Tap_Cuoi_Ki_1_Toan_9_Tay_Son_2025-2026.docx
    De_Giua_Ki_1_Toan_12_Tran_Phu_2026-2027_Ma_de_426.pdf

- Mỗi đề gồm 1 file .pdf và/hoặc 1 file .docx cùng tên (khác phần đuôi).
- Tên trường có dấu được tra trong schools.json. Trường mới chưa có trong schools.json sẽ được
  tự thêm vào với tên tạm (không dấu) — thầy chỉ cần sửa lại cho đúng trong schools.json.
- Các mục đã có trong docs.json với "auto": false là mục nhập tay, script KHÔNG ghi đè.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "tai-lieu"
DOCS = ROOT / "docs.json"
SCHOOLS = ROOT / "schools.json"

# (tiền tố tên file) -> (loại hiển thị trong ô lọc, cụm đầu tiêu đề)
TYPES = [
    ("De_Cuong_On_Tap_Cuoi_Ki_1", ("Đề cương", "Đề cương ôn tập cuối kì 1")),
    ("De_Cuong_On_Tap_Giua_Ki_1", ("Đề cương", "Đề cương ôn tập giữa kì 1")),
    ("De_Cuong_On_Tap_Cuoi_Ki_2", ("Đề cương", "Đề cương ôn tập cuối kì 2")),
    ("De_Cuong_On_Tap_Giua_Ki_2", ("Đề cương", "Đề cương ôn tập giữa kì 2")),
    ("De_Cuong_On_Tap",           ("Đề cương", "Đề cương ôn tập")),
    ("De_Giua_Ki_1",              ("Giữa kì I", "Đề thi giữa kì 1")),
    ("De_Cuoi_Ki_1",              ("Cuối kì I", "Đề thi cuối kì 1")),
    ("De_Giua_Ki_2",              ("Giữa kì II", "Đề thi giữa kì 2")),
    ("De_Cuoi_Ki_2",              ("Cuối kì II", "Đề thi cuối kì 2")),
    ("De_HSG_Cap_Truong",         ("Học sinh giỏi", "Đề thi học sinh giỏi cấp trường")),
    ("De_HSG",                    ("Học sinh giỏi", "Đề thi học sinh giỏi")),
    ("De_Tuyen_Sinh_10",          ("Tuyển sinh 10", "Đề thi tuyển sinh lớp 10")),
    ("De_Thi_Thu",                ("Thi thử", "Đề thi thử")),
    ("De_Kiem_Tra",               ("Giữa kì I", "Đề kiểm tra")),
]

YEAR = re.compile(r"^\d{4}-\d{4}$")


def parse(stem):
    """Tách tên file thành (loại, đầu tiêu đề, khối, mã trường, năm học, ghi chú). Trả về None nếu sai quy ước."""
    for prefix, (loai, head) in TYPES:
        if stem == prefix or stem.startswith(prefix + "_"):
            rest = stem[len(prefix):].lstrip("_").split("_")
            break
    else:
        return None
    if len(rest) < 4 or rest[0] != "Toan" or not rest[1].isdigit():
        return None
    grade = rest[1]
    yi = next((i for i, t in enumerate(rest) if YEAR.match(t)), None)
    if yi is None or yi < 3:
        return None
    slug = "_".join(rest[2:yi])
    year = rest[yi]
    note = rest[yi + 1:]
    return loai, head, grade, slug, year, note


def note_text(note):
    if not note:
        return ""
    t = " ".join(note)
    m = re.match(r"^Ma de (\w+)$", t, re.I)
    if m:
        return f" – Mã đề {m.group(1)}"
    m = re.match(r"^De (\w+)$", t, re.I)
    if m:
        return f" – Đề {m.group(1)}"
    return " – " + t


def fallback_school(slug, grade="8"):
    level = "THPT" if str(grade).isdigit() and int(grade) >= 10 else "THCS"
    return f"{level} " + slug.replace("_", " ")


def main():
    schools = json.loads(SCHOOLS.read_text(encoding="utf-8")) if SCHOOLS.exists() else {}
    old = json.loads(DOCS.read_text(encoding="utf-8")) if DOCS.exists() else []

    # gom file theo tên gốc
    files = {}
    if FOLDER.exists():
        for p in sorted(FOLDER.iterdir()):
            ext = p.suffix.lower()
            if ext in (".pdf", ".docx"):
                files.setdefault(p.stem, {})[ext] = f"tai-lieu/{p.name}"

    def stem_of(d):
        for k in ("pdf", "file"):
            if d.get(k):
                return Path(d[k]).stem
        return None

    result, seen, warnings = [], set(), []
    for d in old:
        s = stem_of(d)
        if s is None:
            continue
        if s not in files:
            if d.get("auto"):     # mục tự động mà file đã bị xóa -> bỏ khỏi danh sách
                print(f"- Bỏ: {s} (không còn file)")
                continue
            # mục nhập tay: giữ nguyên, chỉ cảnh báo để thầy kiểm tra
            warnings.append(f"Mục '{d.get('ten')}' chưa thấy file trong tai-lieu/ (giữ nguyên trong danh sách).")
            seen.add(s)
            result.append(d)
            continue
        seen.add(s)
        if d.get("auto"):         # mục tự động -> dựng lại để nhận sửa đổi từ schools.json
            parsed = parse(s)
            if parsed:
                d = build_entry(s, parsed, files[s], schools)
        else:                     # mục nhập tay -> chỉ cập nhật đường dẫn file
            d["pdf"] = files[s].get(".pdf", "")
            d["file"] = files[s].get(".docx", "")
        result.append(d)

    added = 0
    for s in sorted(files):
        if s in seen:
            continue
        parsed = parse(s)
        if not parsed:
            warnings.append(f"Tên file không đúng quy ước, bỏ qua: {s}")
            continue
        slug = parsed[3]
        if slug not in schools:
            schools[slug] = fallback_school(slug, parsed[2])
            warnings.append(f"Trường mới '{slug}' chưa có trong schools.json — đang dùng tên tạm '{schools[slug]}', hãy sửa lại cho đúng dấu.")
        result.append(build_entry(s, parsed, files[s], schools))
        added += 1
        print(f"+ Thêm: {s}")

    SCHOOLS.write_text(json.dumps(dict(sorted(schools.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DOCS.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for w in warnings:
        print(f"::warning::{w}")
    print(f"Xong: {len(result)} tài liệu (thêm mới {added}).")


def build_entry(stem, parsed, f, schools):
    loai, head, grade, slug, year, note = parsed
    school = schools.get(slug) or fallback_school(slug, grade)
    return {
        "ten": f"{head} Toán {grade} Trường {school} năm học {year}{note_text(note)}",
        "truong": school,
        "khoi": f"Lớp {grade}",
        "loai": loai,
        "nam": year,
        "pdf": f.get(".pdf", ""),
        "file": f.get(".docx", ""),
        "auto": True,
    }


if __name__ == "__main__":
    sys.exit(main())
