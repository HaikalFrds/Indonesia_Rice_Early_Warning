import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw" / "bps_publikasi"
TABLE_LIST_PATH = ROOT / "data" / "interim" / "daftar_tabel_bps.csv"
OUTPUT_PATH = ROOT / "data" / "interim" / "bps_tabel_bulanan.csv"
REPORT_PATH = ROOT / "data" / "interim" / "bps_validasi.csv"

MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]
COLUMNS = MONTHS + ["Total"]
HEADER_TYPOS = {"Apeil": "April"}  # salah ketik di PDF edisi 2019

# Urutan penting: kata kunci yang lebih spesifik dicek lebih dulu
TOPICS = [
    ("perbandingan", None),
    ("luas panen", "luas_panen"),
    ("produksi padi", "produksi_padi"),
    ("produksi beras", "produksi_beras"),
    ("tanaman berdiri", "standing_crop"),
    ("vegetatif awal", "vegetatif_awal"),
    ("vegetatif akhir", "vegetatif_akhir"),
    ("generatif", "generatif"),
    ("persiapan lahan", "persiapan_lahan"),
    ("gagal panen", "potensi_gagal_panen"),
    ("puso", "puso"),
    ("selain padi", "tanaman_selain_padi"),
    ("tidak ditanami padi", "tanaman_selain_padi"),
    ("diberakan", "lahan_bera"),
]

DASHES = "\u2013\u2014\ufffd-"  # "-" di akhir supaya tidak dibaca sebagai rentang di regex
ROW = re.compile(rf"^\s*(?P<name>[A-Za-z][A-Za-z .()']*?)\s+(?P<values>[\d{DASHES}].*)$")


def get_topic(title: str):
    title = title.lower()
    for keyword, topic in TOPICS:
        if keyword in title:
            return topic
    return None


def parse_values(text: str) -> list:
    # Pemisah ribuan bisa titik (1.322.270,78) atau spasi (1 322 270,78)
    sep = r"\." if re.search(r"\d\.\d{3}", text) else " "
    number = rf"\d{{1,3}}(?:{sep}\d{{3}})*(?:,\d+)?"
    tokens = re.findall(rf"{number}|[{DASHES}]", text)
    values = []
    for token in tokens:
        if token in DASHES:
            values.append(0.0)
        else:
            values.append(float(token.replace(".", "").replace(" ", "").replace(",", ".")))
    return values


def merge_broken_lines(lines: list) -> list:
    """'Kep. Bangka Be -' + 'litung  7 991,64 ...' -> 'Kep. Bangka Belitung  7 991,64 ...'"""
    merged = []
    for line in lines:
        if merged and re.match(r"^[a-z]", line):
            merged[-1] = re.sub(r"\s*-\s*$", "", merged[-1]) + line
        else:
            merged.append(line)
    return merged


def parse_page(text: str) -> dict:
    header = None
    rows = {}
    for line in merge_broken_lines(text.splitlines()):
        words = [HEADER_TYPOS.get(word, word).capitalize() for word in line.split()]
        if words and all(word in COLUMNS for word in words):
            header = words
            continue
        match = ROW.match(line)
        if header is None or match is None:
            continue
        values = parse_values(match.group("values"))
        if len(values) != len(header):
            continue
        rows[" ".join(match.group("name").split())] = dict(zip(header, values))
    return rows


def extract_table(reader: PdfReader, first_page: int, last_page: int) -> pd.DataFrame:
    table = {}
    for page_number in range(first_page, last_page + 1):
        for name, values in parse_page(reader.pages[page_number - 1].extract_text()).items():
            table.setdefault(name, {}).update(values)
    df = pd.DataFrame.from_dict(table, orient="index").reindex(columns=COLUMNS)
    df.index.name = "provinsi"
    return df


def validate(df: pd.DataFrame) -> dict:
    national = df.loc[df.index.str.upper() == "INDONESIA"]
    provinces = df.loc[df.index.str.upper() != "INDONESIA"]
    diff_total = (provinces[MONTHS].sum(axis=1) - provinces["Total"]).abs()
    result = {
        "n_provinsi": len(provinces),
        "ada_baris_indonesia": len(national) == 1,
        "sel_kosong": int(provinces[MONTHS].isna().sum().sum()),
        "provinsi_selisih_total": int((diff_total > 1).sum()),
        "ada_kolom_total": provinces["Total"].notna().any(),
    }
    if len(national) == 1:
        diff_national = (provinces[MONTHS].sum() - national.iloc[0][MONTHS]).abs()
        result["maks_selisih_nasional"] = round(float(diff_national.max()), 2)
    return result


def main():
    tables = pd.read_csv(TABLE_LIST_PATH).sort_values(["edisi", "halaman"])
    frames, reports = [], []

    for edition, group in tables.groupby("edisi"):
        reader = PdfReader(PDF_DIR / f"luas_panen_produksi_padi_{edition}.pdf")
        next_pages = group["halaman"].shift(-1).fillna(len(reader.pages) + 1).astype(int)

        for (_, info), next_page in zip(group.iterrows(), next_pages):
            topic = get_topic(info["judul"])
            if topic is None:
                continue
            df = extract_table(reader, info["halaman"], next_page - 1)
            report = {"edisi": edition, "tahun": info["tahun_data"], "topik": topic,
                      "halaman": info["halaman"], **validate(df)}
            reports.append(report)
            df = df.reset_index()
            df.insert(0, "topik", topic)
            df.insert(0, "tahun", info["tahun_data"])
            df.insert(0, "edisi", edition)
            frames.append(df)
        print(f"{edition}: {sum(r['edisi'] == edition for r in reports)} tabel diekstrak")

    pd.concat(frames).to_csv(OUTPUT_PATH, index=False)
    report = pd.DataFrame(reports)
    report.to_csv(REPORT_PATH, index=False)
    print(f"\nTersimpan: {OUTPUT_PATH}\nTersimpan: {REPORT_PATH}")

    problems = report[
        (report["sel_kosong"] > 0)
        | (report["provinsi_selisih_total"] > 0)
        | (report["maks_selisih_nasional"].fillna(1e9) > 1)
    ]
    print(f"\nTabel bermasalah: {len(problems)} dari {len(report)}")
    if len(problems):
        print(problems.to_string(index=False))


if __name__ == "__main__":
    main()