import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw" / "bps_publikasi"
OUTPUT_PATH = ROOT / "data" / "interim" / "daftar_tabel_bps.csv"

# Edisi 2019–2022 memakai "Tabel 1.", edisi 2023–2025 memakai "Lampiran 1"
TITLE_START = re.compile(r"^\s*(Lampiran|Tabel)\s+(\d+)\.?\s")
YEAR = re.compile(r"\b(20\d{2})\*?")


def find_title(lines):
    for i, line in enumerate(lines):
        if TITLE_START.match(line):
            title = line.strip()
            # judul panjang bisa terpotong ke 1–2 baris berikutnya
            for extra in lines[i + 1:i + 3]:
                if YEAR.search(title):
                    break
                title += " " + extra.strip()
            if ".." in title:  # baris daftar isi, bukan tabel
                return None
            return " ".join(title.replace("- ", "").split())
    return None


def main():
    rows = []
    for pdf_path in sorted(PDF_DIR.glob("luas_panen_produksi_padi_*.pdf")):
        edition = int(pdf_path.stem.split("_")[-1])
        reader = PdfReader(pdf_path)

        for page_number, page in enumerate(reader.pages, start=1):
            lines = (page.extract_text() or "").splitlines()
            title = find_title(lines)
            if title is None:
                continue

            years = YEAR.findall(title)
            rows.append({
                "edisi": edition,
                "halaman": page_number,
                "nomor": int(TITLE_START.match(title).group(2)),
                "judul": title,
                "tahun_data": int(years[-1]) if years else None,
            })

        n_tables = sum(row["edisi"] == edition for row in rows)
        print(f"{edition}: {len(reader.pages)} halaman, {n_tables} tabel")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_PATH, index=False)
    print(f"Tersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()