"""
DELTA - ai/download_dipladenia.py
Scarica ~1000 immagini di Dipladenia/Mandevilla da Bing e Google Images
e le organizza in datasets/DIPLADENIA FIORE/ con sottoclassi per malattia.

Struttura output:
  datasets/DIPLADENIA FIORE/
    Dipladenia_Sano/        (600 img ~ fiori e foglie sani)
    Dipladenia_Malata/      (250 img ~ foglie gialle, macchie, appassimento)
    Dipladenia_Parassiti/   (150 img ~ cocciniglia, ragnetto rosso, afidi)

Uso:
    python ai/download_dipladenia.py
    python ai/download_dipladenia.py --target 1000 --output "datasets/DIPLADENIA FIORE"
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import random
import shutil
import time
from pathlib import Path
from typing import Dict, List

LOGGER = logging.getLogger("delta.ai.download_dipladenia")

# ──────────────────────────────────────────────────────────────────────────────
# Query per classe — termini di ricerca in più lingue per massima copertura
# ──────────────────────────────────────────────────────────────────────────────

SEARCH_QUERIES: Dict[str, List[Dict]] = {
    "Dipladenia_Sano": [
        # Fiori sani — massima varietà di colori e angolazioni
        {"keyword": "Dipladenia flower healthy",           "n": 80},
        {"keyword": "Mandevilla flower blooming",          "n": 80},
        {"keyword": "Dipladenia fiore sano",               "n": 70},
        {"keyword": "Mandevilla pianta sana",              "n": 60},
        {"keyword": "Dipladenia rosa fiore",               "n": 50},
        {"keyword": "Dipladenia rossa fiore",              "n": 50},
        {"keyword": "Mandevilla red flower plant",         "n": 50},
        {"keyword": "Mandevilla pink flower garden",       "n": 50},
        {"keyword": "Dipladenia bianca fiore",             "n": 40},
        {"keyword": "Mandevilla white flower",             "n": 40},
        {"keyword": "Dipladenia foglia verde sana",        "n": 40},
        {"keyword": "Mandevilla leaf healthy green",       "n": 40},
        {"keyword": "Dipladenia pianta vaso balcone",      "n": 30},
        {"keyword": "Mandevilla climbing plant",           "n": 30},
    ],
    "Dipladenia_Malata": [
        # Foglie gialle, macchie, carenze, imbrunimento
        {"keyword": "Dipladenia foglie gialle malattia",   "n": 50},
        {"keyword": "Mandevilla yellow leaves problem",    "n": 50},
        {"keyword": "Dipladenia leaf yellowing",           "n": 40},
        {"keyword": "Mandevilla brown spots leaves",       "n": 40},
        {"keyword": "Dipladenia foglie macchie",           "n": 35},
        {"keyword": "Mandevilla diseased leaves",          "n": 35},
        {"keyword": "Dipladenia malattia fogliare",        "n": 30},
        {"keyword": "Mandevilla leaf blight",              "n": 30},
        {"keyword": "Dipladenia appassita problemi",       "n": 25},
        {"keyword": "Mandevilla wilting plant problem",    "n": 25},
        {"keyword": "Dipladenia clorosi carenza ferro",    "n": 25},
        {"keyword": "Mandevilla chlorosis",                "n": 25},
    ],
    "Dipladenia_Parassiti": [
        # Cocciniglia, ragnetto rosso, afidi, mosca bianca
        {"keyword": "Dipladenia cocciniglia parassiti",    "n": 40},
        {"keyword": "Mandevilla mealybug infestation",     "n": 40},
        {"keyword": "Dipladenia ragnetto rosso",           "n": 35},
        {"keyword": "Mandevilla spider mites leaves",      "n": 35},
        {"keyword": "Dipladenia afidi insetti",            "n": 30},
        {"keyword": "Mandevilla aphids pest",              "n": 30},
        {"keyword": "Dipladenia mosca bianca",             "n": 25},
        {"keyword": "Mandevilla scale insect",             "n": 25},
    ],
}


def _hash_url(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:10]


def _fetch_duckduckgo_urls(keyword: str, max_num: int) -> List[str]:
    """
    Recupera URL immagini da DuckDuckGo Images usando l'API non ufficiale.
    Non richiede API key ed è meno aggressivamente bloccata di Google.
    """
    import urllib.parse
    import urllib.request
    import json as _json

    urls: List[str] = []
    try:
        # Passo 1: ottieni token vqd
        encoded = urllib.parse.quote(keyword)
        req = urllib.request.Request(
            f"https://duckduckgo.com/?q={encoded}&iax=images&ia=images",
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        import re
        m = re.search(r'vqd=([\d-]+)', html)
        if not m:
            return []
        vqd = m.group(1)

        # Passo 2: chiedi immagini
        params = urllib.parse.urlencode({
            "l": "us-en", "o": "json", "q": keyword,
            "vqd": vqd, "f": ",,,,,", "p": "1",
        })
        req2 = urllib.request.Request(
            f"https://duckduckgo.com/i.js?{params}",
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36",
                "Referer": "https://duckduckgo.com/",
            },
        )
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            data = _json.loads(resp2.read().decode("utf-8", errors="ignore"))

        for item in data.get("results", [])[:max_num]:
            img_url = item.get("image") or item.get("thumbnail")
            if img_url:
                urls.append(img_url)
    except Exception as e:
        LOGGER.debug("DuckDuckGo fetch error: %s", e)
    return urls


def _download_url(url: str, dest_dir: Path, class_name: str, index: int) -> bool:
    """Scarica una singola immagine e la valida/salva con Pillow."""
    import urllib.request
    from PIL import Image

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()

        if len(raw) < 2000:
            return False

        h = hashlib.md5(raw).hexdigest()
        # Controlla duplicati globali nella cartella
        fname = f"{class_name}_{index:06d}.jpg"
        out_path = dest_dir / fname
        if out_path.exists():
            return False

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h_img = img.size
        if w < 100 or h_img < 100:
            return False

        img = _letterbox_resize(img, 224)
        img.save(out_path, "JPEG", quality=92)
        return True
    except Exception:
        return False


def download_with_icrawler(
    output_base: Path,
    class_name: str,
    queries: List[Dict],
    skip_existing: bool = True,
) -> int:
    """
    Scarica immagini usando icrawler (Bing) + DuckDuckGo fallback.
    Ritorna il numero di nuove immagini salvate.
    """
    try:
        from icrawler.builtin import BingImageCrawler
    except ImportError:
        LOGGER.error("icrawler non installato: pip install icrawler")
        return 0

    dest_dir = output_base / class_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    existing = sum(1 for _ in dest_dir.glob("*.jpg"))
    start_count = existing
    LOGGER.info("Classe %s: già presenti %d immagini", class_name, start_count)

    total_downloaded = start_count

    for q_info in queries:
        keyword = q_info["keyword"]
        n_target = q_info["n"]

        LOGGER.info("  Query: '%s' → target:%d", keyword, n_target)

        # ── Bing (60%) ──────────────────────────────────────────────────────
        n_bing = max(1, int(n_target * 0.60))
        try:
            tmp_bing = Path("/tmp/icrawler_bing") / class_name
            tmp_bing.mkdir(parents=True, exist_ok=True)
            for f in tmp_bing.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass

            bing = BingImageCrawler(
                feeder_threads=1,
                parser_threads=1,
                downloader_threads=4,
                storage={"root_dir": str(tmp_bing)},
                log_level=logging.ERROR,
            )
            # Nessun filtro "license" — evita il ValueError
            bing.crawl(
                keyword=keyword,
                max_num=n_bing,
                min_size=(150, 150),
                filters={"type": "photo"},
            )
            saved = _move_images(tmp_bing, dest_dir, class_name, total_downloaded)
            total_downloaded += saved
            LOGGER.info("    Bing salvate: %d", saved)
        except Exception as e:
            LOGGER.warning("    Bing errore (%s): %s", keyword, e)

        # ── DuckDuckGo (40%) ────────────────────────────────────────────────
        n_ddg = max(1, int(n_target * 0.40))
        try:
            img_urls = _fetch_duckduckgo_urls(keyword, n_ddg * 2)  # prende il doppio per compensare fallimenti
            ddg_saved = 0
            for url in img_urls:
                if ddg_saved >= n_ddg:
                    break
                ok = _download_url(url, dest_dir, class_name, total_downloaded + ddg_saved)
                if ok:
                    ddg_saved += 1
            total_downloaded += ddg_saved
            LOGGER.info("    DuckDuckGo salvate: %d", ddg_saved)
        except Exception as e:
            LOGGER.warning("    DuckDuckGo errore (%s): %s", keyword, e)

        time.sleep(0.8)  # pausa cortese tra query

    net_new = total_downloaded - start_count
    LOGGER.info("Classe %s: +%d nuove immagini (totale: %d)", class_name, net_new, total_downloaded)
    return net_new


def _move_images(src_dir: Path, dest_dir: Path, class_name: str, offset: int) -> int:
    """
    Sposta immagini da src_dir a dest_dir, rinominandole e validandole con Pillow.
    Salta duplicati tramite hash MD5 del contenuto.
    """
    from PIL import Image

    existing_hashes = set()
    saved = 0

    # Calcola hash delle immagini già presenti per evitare duplicati
    for existing in dest_dir.glob("*.jpg"):
        try:
            h = hashlib.md5(existing.read_bytes()).hexdigest()
            existing_hashes.add(h)
        except Exception:
            pass

    for src in sorted(src_dir.iterdir()):
        if not src.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            continue
        try:
            raw = src.read_bytes()
            h = hashlib.md5(raw).hexdigest()
            if h in existing_hashes:
                continue  # duplicato

            # Valida e normalizza con Pillow
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            w, h_img = img.size
            if w < 100 or h_img < 100:
                continue  # immagine troppo piccola

            # Ridimensiona a 224x224 mantenendo proporzioni con letterbox
            img = _letterbox_resize(img, 224)

            fname = f"{class_name}_{offset + saved:06d}.jpg"
            img.save(dest_dir / fname, "JPEG", quality=92)
            existing_hashes.add(h)
            saved += 1
        except Exception:
            pass  # immagine corrotta, salta

    return saved


def _letterbox_resize(img, size: int):
    """Ridimensiona con padding grigio per preservare le proporzioni."""
    from PIL import Image

    w, h = img.size
    scale = size / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Centra su sfondo grigio
    result = Image.new("RGB", (size, size), (128, 128, 128))
    offset_x = (size - new_w) // 2
    offset_y = (size - new_h) // 2
    result.paste(img, (offset_x, offset_y))
    return result


def augment_class(class_dir: Path, target: int) -> int:
    """
    Genera copie augmentate se la classe ha meno di `target` immagini.
    Trasformazioni: flip, rotazione, luminosità, contrasto, ritaglio leggero.
    """
    from PIL import Image, ImageEnhance, ImageFilter

    imgs = list(class_dir.glob("*.jpg"))
    n = len(imgs)
    if n == 0 or n >= target:
        return 0

    LOGGER.info("Augmentation %s: %d → ~%d", class_dir.name, n, target)
    needed = target - n
    aug_count = 0
    rng = random.Random(42)

    while aug_count < needed:
        for src_path in imgs:
            if aug_count >= needed:
                break
            try:
                img = Image.open(src_path).convert("RGB")

                # Applica trasformazione casuale
                op = rng.randint(0, 6)
                if op == 0:
                    img = img.transpose(Image.FLIP_LEFT_RIGHT)
                elif op == 1:
                    angle = rng.uniform(-20, 20)
                    img = img.rotate(angle, expand=False, fillcolor=(128, 128, 128))
                elif op == 2:
                    factor = rng.uniform(0.70, 1.35)
                    img = ImageEnhance.Brightness(img).enhance(factor)
                elif op == 3:
                    factor = rng.uniform(0.75, 1.30)
                    img = ImageEnhance.Contrast(img).enhance(factor)
                elif op == 4:
                    factor = rng.uniform(0.80, 1.25)
                    img = ImageEnhance.Color(img).enhance(factor)
                elif op == 5:
                    img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.5, 1.2)))
                elif op == 6:
                    # Random crop + resize
                    w, h = img.size
                    margin = int(min(w, h) * 0.10)
                    x0 = rng.randint(0, margin)
                    y0 = rng.randint(0, margin)
                    x1 = w - rng.randint(0, margin)
                    y1 = h - rng.randint(0, margin)
                    img = img.crop((x0, y0, x1, y1)).resize((224, 224), Image.LANCZOS)

                img = img.resize((224, 224))
                fname = f"{class_dir.name}_aug_{aug_count:05d}.jpg"
                img.save(class_dir / fname, "JPEG", quality=88)
                aug_count += 1
            except Exception:
                pass

    LOGGER.info("Augmentation %s: +%d immagini generate", class_dir.name, aug_count)
    return aug_count


def count_images(directory: Path) -> Dict[str, int]:
    counts = {}
    if not directory.exists():
        return counts
    for class_dir in sorted(directory.iterdir()):
        if class_dir.is_dir():
            n = len(list(class_dir.glob("*.jpg"))) + len(list(class_dir.glob("*.png")))
            counts[class_dir.name] = n
    return counts


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scarica ~1000 immagini Dipladenia/Mandevilla per training DELTA"
    )
    p.add_argument(
        "--output",
        default="datasets/DIPLADENIA FIORE",
        help="Cartella output (default: 'datasets/DIPLADENIA FIORE')",
    )
    p.add_argument(
        "--target", type=int, default=1000,
        help="Numero totale immagini target (default: 1000)",
    )
    p.add_argument(
        "--skip-augment", action="store_true",
        help="Salta augmentation automatica",
    )
    p.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("  DELTA — Download Dataset Dipladenia/Mandevilla")
    print(f"  Output: {output_dir}")
    print(f"  Target: ~{args.target} immagini totali")
    print("=" * 65)

    # Distribuzione target: 60% Sano, 25% Malata, 15% Parassiti
    targets = {
        "Dipladenia_Sano":      int(args.target * 0.60),
        "Dipladenia_Malata":    int(args.target * 0.25),
        "Dipladenia_Parassiti": int(args.target * 0.15),
    }
    print(f"\nDistribuzione target:")
    for cls, n in targets.items():
        print(f"  {cls}: {n}")

    # ── Download ────────────────────────────────────────────────────────────
    total_new = 0
    for class_name, queries in SEARCH_QUERIES.items():
        print(f"\n[{'='*3}] Classe: {class_name}")
        new = download_with_icrawler(output_dir, class_name, queries)
        total_new += new

    # ── Augmentation se necessario ──────────────────────────────────────────
    if not args.skip_augment:
        print("\n[AUG] Augmentation classi sotto-target...")
        for class_name, min_n in targets.items():
            class_dir = output_dir / class_name
            if class_dir.exists():
                augment_class(class_dir, min_n)

    # ── Riepilogo finale ─────────────────────────────────────────────────────
    final = count_images(output_dir)
    grand_total = sum(final.values())

    print("\n" + "=" * 65)
    print("  RIEPILOGO DATASET DIPLADENIA FIORE")
    print("=" * 65)
    for cls in sorted(final):
        bar = "█" * min(40, final[cls] // 10)
        print(f"  {cls:<30}  {final[cls]:4d}  {bar}")
    print(f"\n  TOTALE: {grand_total} immagini in {len(final)} classi")
    print(f"  Path:   {output_dir}")

    # Salva manifest
    manifest = {
        "dataset": "DIPLADENIA FIORE",
        "source": "Bing + Google Images (icrawler)",
        "classes": final,
        "total_images": grand_total,
        "output_dir": str(output_dir),
        "training_command": (
            f"python ai/train_keras_classifier.py "
            f"--dataset \"{output_dir}\" "
            f"--output models/dipladenia"
        ),
    }
    manifest_path = output_dir / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\n  Manifest salvato: {manifest_path}")
    print("=" * 65)

    if grand_total < 10:
        LOGGER.error("Download fallito: meno di 10 immagini scaricate.")
        return 1

    print(f"\n✓ Dataset pronto. Avvia training con:")
    print(f"  python ai/train_keras_classifier.py \\")
    print(f"    --dataset \"{output_dir}\" \\")
    print(f"    --output models/dipladenia \\")
    print(f"    --epochs 20")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
