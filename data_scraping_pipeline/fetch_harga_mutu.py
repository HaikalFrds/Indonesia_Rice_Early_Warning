import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DIR_OUT = ROOT / "data" / "processed"

load_dotenv(ROOT / ".env")
API_KEY = os.getenv("BPS_API_KEY")
HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://webapi.bps.go.id/v1/api/list/model"

# Harga beras: 295 grosir nasional, 500 penggilingan per kualitas (lama), 2277 (baru)
VAR_HARGA = {295: "grosir", 500: "penggilingan", 2277: "penggilingan"}

# Mutu gabah: 1034 tingkat petani, 1047 tingkat penggilingan. Urutan vervar sama di keduanya.
VAR_MUTU = {1034: "petani", 1047: "penggilingan"}
KOMPONEN = {
    1: "harga_gkp", 2: "harga_gkg", 3: "harga_luar_kualitas",
    4: "kadar_air_gkp", 5: "kadar_air_gkg", 6: "kadar_air_luar_kualitas",
    7: "kadar_hampa_gkp", 8: "kadar_hampa_gkg", 9: "kadar_hampa_luar_kualitas",
    10: "hpp_gkp", 11: "hpp_gkg", 12: "hpp",
}


def get_json(url: str) -> dict:
    body = requests.get(url, headers=HEADERS, timeout=60).json()
    if body.get("status") != "OK" or body.get("data-availability") != "available":
        raise RuntimeError(f"API BPS gagal: {body.get('message')}")
    return body


def ambil_variabel(var_id: int) -> pd.DataFrame:
    """Tarik satu variabel jadi tabel panjang: tanggal, kode_vervar, label_vervar, nilai."""
    years = get_json(f"{BASE_URL}/th/lang/ind/domain/0000/var/{var_id}/key/{API_KEY}/")["data"][1]
    year_ids = [str(y["th_id"]) for y in years]

    rows = []
    for i in range(0, len(year_ids), 3):  # API membatasi maksimal 3 tahun per request
        body = get_json(f"{BASE_URL}/data/lang/ind/domain/0000/var/{var_id}"
                        f"/th/{';'.join(year_ids[i:i + 3])}/key/{API_KEY}/")
        turvar = body["turvar"][0]["val"]
        labels = {v["val"]: v["label"] for v in body["vervar"]}
        bulan = {t["val"]: n for n, t in enumerate(body["turtahun"], start=1) if n <= 12}
        for kode, label in labels.items():
            for tahun in body["tahun"]:
                for kode_bulan, nomor_bulan in bulan.items():
                    nilai = body["datacontent"].get(
                        f"{kode}{var_id}{turvar}{tahun['val']}{kode_bulan}")
                    if nilai is not None:
                        rows.append({
                            "tanggal": f"{tahun['label']}-{nomor_bulan:02d}-01",
                            "kode_vervar": kode,
                            "label_vervar": label,
                            "nilai": nilai,
                        })
    return pd.DataFrame(rows)


def bersihkan_label(label: str) -> str:
    # ponytail: BPS menyisipkan tag HTML catatan kaki di sebagian label
    return label.split("<")[0].strip().lower().replace("/", "_").replace(" ", "_")


def main():
    if not API_KEY:
        raise SystemExit("BPS_API_KEY belum diisi di file .env")

    harga = []
    for var_id, tingkat in VAR_HARGA.items():
        df = ambil_variabel(var_id)
        df["kualitas"] = tingkat + "_" + df["label_vervar"].map(bersihkan_label)
        df["sumber_var"] = var_id
        harga.append(df[["tanggal", "kualitas", "nilai", "sumber_var"]]
                     .rename(columns={"nilai": "harga_rp_kg"}))
        print(f"var {var_id}: {len(df)} baris, {df.tanggal.min()} s.d. {df.tanggal.max()}")

    df_harga = pd.concat(harga).sort_values(["tanggal", "kualitas"]).reset_index(drop=True)

    mutu = []
    for var_id, tingkat in VAR_MUTU.items():
        df = ambil_variabel(var_id)
        df["tingkat"] = tingkat
        df["komponen"] = df["kode_vervar"].map(KOMPONEN)
        assert df["komponen"].notna().all(), f"kode vervar tak dikenal di var {var_id}"
        mutu.append(df[["tanggal", "tingkat", "komponen", "nilai"]])
        print(f"var {var_id}: {len(df)} baris, {df.tanggal.min()} s.d. {df.tanggal.max()}")

    df_mutu = pd.concat(mutu).sort_values(["tanggal", "tingkat", "komponen"]).reset_index(drop=True)

    DIR_OUT.mkdir(parents=True, exist_ok=True)
    df_harga.to_csv(DIR_OUT / "harga_beras_bulanan.csv", index=False)
    df_mutu.to_csv(DIR_OUT / "mutu_gabah_bulanan.csv", index=False)

    print(f"\nharga_beras_bulanan.csv : {len(df_harga)} baris, seri: "
          f"{sorted(df_harga.kualitas.unique())}")
    print(f"mutu_gabah_bulanan.csv  : {len(df_mutu)} baris, komponen: "
          f"{df_mutu.komponen.nunique()}, tingkat: {sorted(df_mutu.tingkat.unique())}")


if __name__ == "__main__":
    main()