import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "processed" / "harga_beras_provinsi.csv"

BASE_URL = "https://www.bi.go.id/hargapangan"
HALAMAN = f"{BASE_URL}/TabelHarga/PasarTradisionalDaerah"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json",
    "Referer": HALAMAN,
}

PASAR_TRADISIONAL = 1
LAPORAN_BULANAN = 3          # 1 = harian, 2 = mingguan, 3 = bulanan
KATEGORI_BERAS = "cat_1"     # satu permintaan mengembalikan enam kelas mutu sekaligus
MULAI = "2017-01-01"


def bersihkan(nilai):
    """'14,600' -> 14600.0 ; '-' atau kosong -> None."""
    if nilai in (None, "", "-"):
        return None
    return float(str(nilai).replace(",", ""))


def main():
    sesi = requests.Session()
    sesi.headers.update(HEADERS)
    sesi.get(HALAMAN, timeout=60)  # ambil cookie sesi

    api = f"{BASE_URL}/WebSite/TabelHarga"
    provinsi = sesi.get(f"{api}/GetRefProvince", timeout=60).json()["data"]
    selesai = date.today().isoformat()

    baris = []
    for i, prov in enumerate(provinsi, start=1):
        params = {
            "price_type_id": PASAR_TRADISIONAL,
            "comcat_id": KATEGORI_BERAS,
            "province_id": prov["id"],
            "regency_id": "",
            "market_id": "",
            "tipe_laporan": LAPORAN_BULANAN,
            "start_date": MULAI,
            "end_date": selesai,
            "skip": 0,
            "take": 500,
        }
        jawaban = sesi.get(f"{api}/GetGridDataDaerah", params=params, timeout=120)
        if "json" not in jawaban.headers.get("content-type", ""):
            raise RuntimeError(f"PIHPS membalas non-JSON untuk {prov['name']}")

        for item in jawaban.json()["data"]:
            if item["level"] != 2:      # level 1 = baris kategori, bukan kelas mutu
                continue
            for kolom, nilai in item.items():
                if kolom in ("no", "name", "level"):
                    continue
                harga = bersihkan(nilai)
                if harga is not None:
                    baris.append({"bulan": kolom, "provinsi": prov["name"],
                                  "kualitas": item["name"], "harga_rp_kg": harga})
        print(f"[{i:2}/{len(provinsi)}] {prov['name']}")
        time.sleep(0.5)  # jeda karena portal ini milik publik

    df = pd.DataFrame(baris)
    df["tanggal"] = pd.to_datetime(df.pop("bulan"), format="%b %Y")
    df = df[["tanggal", "provinsi", "kualitas", "harga_rp_kg"]]
    df = df.sort_values(["provinsi", "kualitas", "tanggal"]).reset_index(drop=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"\n{len(df)} baris | {df.provinsi.nunique()} provinsi | "
          f"{df.kualitas.nunique()} kelas mutu")
    print(f"{df.tanggal.min():%Y-%m} s.d. {df.tanggal.max():%Y-%m}")
    print(f"Tersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()