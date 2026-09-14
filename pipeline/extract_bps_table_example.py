import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw" / "bps_publikasi"
TABLE_LIST_PATH = ROOT / "data" / "interim" / "daftar_tabel_bps.csv"
OUTPUT_PATH = ROOT / "data" / "interim" / "contoh_produksi_padi_2023.csv"

# Tabel yang diambil: data 2023 dari edisi 2024 (angka tetap)
EDITION = 2024
TITLE_KEYWORD = "Produksi Padi Menurut Provinsi"
DATA_YEAR = 2023
PAGES_PER_TABLE = 3  # Jan–Apr, Mei–Agu, Sep–Des + Total

COLUMNS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember", "Total",
]
MONTHS = COLUMNS[:-1]

# Tanda strip (= tidak ada panen) bisa terbaca sebagai "-", "–", "—", atau "�"
DASHES = {"-", "\u2013", "\u2014", "\ufffd"}
# Format angka Indonesia: 1.322.270,78
NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})*,\d+")


def find_start_page() -> int:
    tables = pd.read_csv(TABLE_LIST_PATH)
    match = tables[
        (tables["edisi"] == EDITION)
        & tables["judul"].str.contains(TITLE_KEYWORD)
        & (tables["tahun_data"] == DATA_YEAR)
    ]
    if len(match) != 1:
        raise RuntimeError(f"Harus ketemu tepat 1 tabel, ketemu {len(match)}")
    return int(match["halaman"].iloc[0])


def to_number(token: str) -> float:
    if token in DASHES:
        return 0.0
    return float(token.replace(".", "").replace(",", "."))


def parse_row(line: str):
    """' Jawa Barat  477.312,18  – ' -> ('Jawa Barat', [477312.18, 0.0])"""
    tokens = line.split()
    values = []
    while tokens and (tokens[-1] in DASHES or NUMBER.fullmatch(tokens[-1])):
        values.insert(0, to_number(tokens.pop()))
    name = " ".join(tokens)
    if not values or not re.search(r"[A-Za-z]", name):
        return None
    return name, values


def parse_page(text: str) -> dict:
    header = None
    rows = {}
    for line in text.splitlines():
        words = line.split()
        if words and all(word in COLUMNS for word in words):
            header = words  # mis. ['Januari', 'Februari', 'Maret', 'April']
            continue
        row = parse_row(line)
        if header is None or row is None:
            continue
        name, values = row
        if len(values) != len(header):
            print(f"  PERINGATAN: jumlah kolom tidak cocok, dilewati: {line.strip()}")
            continue
        rows[name] = dict(zip(header, values))
    return rows


def validate(df: pd.DataFrame):
    print(f"Provinsi: {len(df) - 1} (+ baris INDONESIA)")

    # Cek 1: sel kosong = ada baris yang hilang di salah satu halaman
    missing = df[df.isna().any(axis=1)]
    print(f"\n[Cek 1] Baris dengan sel kosong: {len(missing)}")
    for name, row in missing.iterrows():
        print(f"  {name}: kosong di {row[row.isna()].index.tolist()}")

    # Cek 2: jumlah 12 bulan harus sama dengan kolom Total
    diff_total = (df[MONTHS].sum(axis=1) - df["Total"]).abs()
    bad_total = diff_total[diff_total > 1]
    print(f"\n[Cek 2] Provinsi dengan selisih (12 bulan vs Total) > 1 ton: {len(bad_total)}")
    for name, diff in bad_total.items():
        print(f"  {name}: selisih {diff:,.2f} ton")

    # Cek 3: jumlah semua provinsi harus sama dengan baris INDONESIA
    diff_national = (df.drop(index="INDONESIA").sum() - df.loc["INDONESIA"]).abs()
    print("\n[Cek 3] Selisih (jumlah provinsi vs INDONESIA) per kolom:")
    print(diff_national.round(2).to_string())


def main():
    start_page = find_start_page()
    reader = PdfReader(PDF_DIR / f"luas_panen_produksi_padi_{EDITION}.pdf")
    print(f"Edisi {EDITION}, mulai halaman {start_page}\n")

    table = {}
    for page_number in range(start_page, start_page + PAGES_PER_TABLE):
        text = reader.pages[page_number - 1].extract_text()
        for name, values in parse_page(text).items():
            table.setdefault(name, {}).update(values)

    df = pd.DataFrame.from_dict(table, orient="index").reindex(columns=COLUMNS)
    df.index.name = "provinsi"

    validate(df)

    df.to_csv(OUTPUT_PATH)
    print(f"\nTersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()