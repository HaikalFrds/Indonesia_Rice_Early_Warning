import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "raw" / "bps_publikasi"

load_dotenv(ROOT / ".env")
API_KEY = os.getenv("BPS_API_KEY")

# Server BPS memblokir request tanpa User-Agent browser
HEADERS = {"User-Agent": "Mozilla/5.0"}

# edisi (tahun data) -> id publikasi di WebAPI BPS
PUBLICATIONS = {
    2019: "21930121d1e4d09459f7e195",
    2020: "b21ea2ed9524b784187be1ed",
    2021: "c52d5cebe530c363d0ea4198",
    2022: "a78164ccd3ad09bdc88e70a2",
    2023: "cacb2de135ee840211c7e95e",
    2024: "c9aa01258cbe8b4b0b974baf",
    2025: "b40248f696f16d51371d326e",
}


def get_pdf_url(pub_id: str) -> str:
    url = (
        "https://webapi.bps.go.id/v1/api/view/model/publication"
        f"/lang/ind/domain/0000/id/{pub_id}/key/{API_KEY}/"
    )
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") != "OK":
        raise RuntimeError(f"API BPS error: {body.get('message')}")
    return body["data"]["pdf"]


def download(url: str, path: Path):
    tmp_path = path.with_suffix(".part")
    with requests.get(url, headers=HEADERS, timeout=300, stream=True) as resp:
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    tmp_path.rename(path)  # baru dianggap selesai kalau unduhan utuh


def main():
    if not API_KEY:
        raise SystemExit("BPS_API_KEY belum diisi di file .env")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for edition, pub_id in PUBLICATIONS.items():
        path = OUTPUT_DIR / f"luas_panen_produksi_padi_{edition}.pdf"
        if path.exists():
            print(f"{edition}: sudah ada, dilewati")
            continue

        print(f"{edition}: mengunduh...")
        download(get_pdf_url(pub_id), path)
        print(f"{edition}: selesai ({path.stat().st_size / 1e6:.1f} MB)")
        time.sleep(2)  # jeda supaya tidak membebani server BPS


if __name__ == "__main__":
    main()