#!/usr/bin/env python3
"""
DELTA-PLANT — Test automatico su tutte le 33 classi PlantVillage
Scarica immagini dal repository GitHub originale (spMohanty/PlantVillage-Dataset)
ed esegue inferenza DIRETTA TFLite (senza agente interattivo), producendo un report completo.
"""
import os, sys, json, time, urllib.request
from pathlib import Path
from collections import Counter

# ── Aggiungi root del progetto al path ──────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Mappatura classe modello → cartella GitHub ──────────────────────────────
CLASS_TO_FOLDER = {
    "Apple_Apple_scab":          "Apple___Apple_scab",
    "Apple_Black_rot":           "Apple___Black_rot",
    "Apple_Cedar_apple_rust":    "Apple___Cedar_apple_rust",
    "Apple_healthy":             "Apple___healthy",
    "Bell_pepper_Bacterial_spot":"Pepper,_bell___Bacterial_spot",
    "Bell_pepper_healthy":       "Pepper,_bell___healthy",
    "Blueberry_healthy":         "Blueberry___healthy",
    "Cherry_Powdery_mildew":     "Cherry_(including_sour)___Powdery_mildew",
    "Cherry_healthy":            "Cherry_(including_sour)___healthy",
    "Corn_Cercospora":           "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot",
    "Corn_Common_rust":          "Corn_(maize)___Common_rust_",
    "Corn_Northern_Leaf_Blight": "Corn_(maize)___Northern_Leaf_Blight",
    "Corn_healthy":              "Corn_(maize)___healthy",
    "Grape_Black_rot":           "Grape___Black_rot",
    "Grape_Esca":                "Grape___Esca_(Black_Measles)",
    "Grape_Leaf_blight":         "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)",
    "Grape_healthy":             "Grape___healthy",
    "Peach_healthy":             "Peach___healthy",
    "Potato_Early_blight":       "Potato___Early_blight",
    "Potato_Late_blight":        "Potato___Late_blight",
    "Potato_healthy":            "Potato___healthy",
    "Squash_Powdery_mildew":     "Squash___Powdery_mildew",
    "Strawberry_Leaf_scorch":    "Strawberry___Leaf_scorch",
    "Strawberry_healthy":        "Strawberry___healthy",
    "Tomato_Bacterial_spot":     "Tomato___Bacterial_spot",
    "Tomato_Early_blight":       "Tomato___Early_blight",
    "Tomato_Late_blight":        "Tomato___Late_blight",
    "Tomato_Leaf_Mold":          "Tomato___Leaf_Mold",
    "Tomato_Septoria_leaf_spot": "Tomato___Septoria_leaf_spot",
    "Tomato_Target_Spot":        "Tomato___Target_Spot",
    "Tomato_Yellow_Leaf_Curl":   "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
    "Tomato_healthy":            "Tomato___healthy",
    "Tomato_mosaic_virus":       "Tomato___Tomato_mosaic_virus",
}

HEADERS = {
    "User-Agent": "DELTA-PLANT-Test/1.0 (educational research; linux)",
    "Accept":     "application/vnd.github.v3+json",
}
GITHUB_API = "https://api.github.com/repos/spMohanty/PlantVillage-Dataset/contents/raw/color/{folder}"
GITHUB_RAW = "https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/master/raw/color/{folder}/{file}"
IMAGES_PER_CLASS = 20
OUT_ROOT    = ROOT / "input_images" / "test_all_classes"
REPORT_FILE = OUT_ROOT / "report_33classi.json"
LOG_FILE    = OUT_ROOT / "progress.log"


def log(msg: str):
    ts   = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def github_list_files(folder: str, n: int = IMAGES_PER_CLASS) -> list:
    url = GITHUB_API.format(folder=urllib.request.quote(folder))
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        items = json.loads(r.read())
    files = [it["name"] for it in items
             if it["type"] == "file" and it["name"].lower().endswith(".jpg")]
    return files[:n]


def download_image(folder: str, fname: str, dest: Path) -> bool:
    url = GITHUB_RAW.format(
        folder=urllib.request.quote(folder),
        file=urllib.request.quote(fname),
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        if len(data) < 1000:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def raw_predict(interpreter, input_details, output_details, labels, img_rgb_224):
    """
    Inferenza diretta TFLite senza soglie/fallback.
    Ritorna (top1_class, top1_conf, top3_list, raw_probs).
    """
    import numpy as np

    # Preprocessing MobileNetV2: float32 [-1, 1]
    tensor = (img_rgb_224.astype(np.float32) / 127.5) - 1.0
    tensor = np.expand_dims(tensor, axis=0)

    in_dtype = input_details[0]["dtype"]
    if in_dtype != np.float32:
        q = input_details[0].get("quantization", (1.0, 0))
        tensor = (tensor / q[0] + q[1]).astype(in_dtype)

    interpreter.set_tensor(input_details[0]["index"], tensor)
    interpreter.invoke()

    raw = interpreter.get_tensor(output_details[0]["index"])[0].astype(np.float32)
    out_q = output_details[0].get("quantization", (1.0, 0))
    if out_q[0] != 0:
        probs = (raw - out_q[1]) * out_q[0]
    else:
        probs = raw

    # Softmax se necessario
    if not (float(probs.min()) >= 0.0 and abs(float(probs.sum()) - 1.0) < 0.05):
        e = np.exp(probs - probs.max())
        probs = e / e.sum()

    top3_idx = probs.argsort()[::-1][:3]
    top3 = [(labels[i] if i < len(labels) else f"Classe_{i}", float(probs[i])) for i in top3_idx]
    return top3[0][0], top3[0][1], top3, probs


def main():
    import cv2
    import numpy as np
    import logging
    logging.disable(logging.CRITICAL)   # silenzia tutti i logger interni

    from core.config import MODEL_CONFIG
    from ai.model_loader import ModelLoader

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("")

    log("=" * 65)
    log("DELTA-PLANT — Test diagnostica 33 classi PlantVillage")
    log("=" * 65)

    # Carica modello TFLite
    loader = ModelLoader()
    if not loader.is_ready():
        log("ERRORE: modello TFLite non caricato. Abort.")
        sys.exit(1)

    interp  = loader.interpreter
    in_det  = loader.input_details
    out_det = loader.output_details
    labels  = loader.labels
    log(f"Modello OK — {len(labels)} classi, input {in_det[0]['shape']}")

    all_results   = {}
    grand_total   = 0
    grand_correct = 0
    grand_top3    = 0
    grand_fallback= 0   # immagini con confidenza <50%
    t_global      = time.time()

    for cls_idx, class_name in enumerate(CLASS_TO_FOLDER.keys()):
        folder  = CLASS_TO_FOLDER[class_name]
        cls_dir = OUT_ROOT / class_name
        cls_dir.mkdir(exist_ok=True)

        log(f"[{cls_idx+1:02d}/33] {class_name}")

        # ── Scarica immagini ──────────────────────────────────────────
        try:
            filenames = github_list_files(folder, IMAGES_PER_CLASS)
            time.sleep(0.4)
        except Exception as e:
            log(f"  WARN API GitHub: {e} — skip")
            all_results[class_name] = []
            continue

        downloaded = []
        for i, fname in enumerate(filenames):
            dest = cls_dir / f"img_{i:02d}.jpg"
            if dest.exists():
                downloaded.append(dest)
                continue
            if download_image(folder, fname, dest):
                downloaded.append(dest)

        log(f"  Immagini: {len(downloaded)}/{len(filenames)}")

        # ── Inferenza ─────────────────────────────────────────────────
        class_results = []
        for img_path in downloaded:
            bgr = cv2.imread(str(img_path))
            if bgr is None:
                class_results.append({"file": img_path.name, "error": True})
                continue
            rgb224 = cv2.cvtColor(
                cv2.resize(bgr, (224, 224), interpolation=cv2.INTER_AREA),
                cv2.COLOR_BGR2RGB,
            )

            pred, conf, top3, _ = raw_predict(interp, in_det, out_det, labels, rgb224)

            # Matching flessibile: i nomi modello usano underscore/snake_case
            def _norm(s):
                return s.lower().replace(" ", "_").replace("-", "_")

            correct = _norm(class_name) == _norm(pred)
            in_top3 = any(_norm(class_name) == _norm(t[0]) for t in top3)
            fallback = conf < 0.50

            class_results.append({
                "file":     img_path.name,
                "gt":       class_name,
                "pred":     pred,
                "conf":     round(conf * 100, 2),
                "correct":  correct,
                "in_top3":  in_top3,
                "fallback": fallback,
                "top3":     [(t[0], round(t[1]*100, 1)) for t in top3],
            })

        tested    = [r for r in class_results if not r.get("error")]
        n_ok      = sum(1 for r in tested if r["correct"])
        n_top3    = sum(1 for r in tested if r["in_top3"])
        n_fb      = sum(1 for r in tested if r["fallback"])
        n_tested  = len(tested)
        acc       = n_ok / n_tested * 100 if n_tested else 0

        log(f"  Risultato: {n_ok}/{n_tested} ({acc:.0f}%)  top3={n_top3}  low_conf={n_fb}")

        all_results[class_name] = class_results
        grand_total    += n_tested
        grand_correct  += n_ok
        grand_top3     += n_top3
        grand_fallback += n_fb

    elapsed   = time.time() - t_global
    grand_acc = grand_correct / grand_total * 100 if grand_total else 0

    log("=" * 65)
    log(f"TOTALE: {grand_correct}/{grand_total} ({grand_acc:.1f}%)"
        f"  top3={grand_top3}  low_conf={grand_fallback}")
    log(f"Tempo: {elapsed/60:.1f} min")
    log("=" * 65)

    # ── Costruzione summary JSON ───────────────────────────────────────────
    summary = {
        "date":           time.strftime("%Y-%m-%d %H:%M:%S"),
        "model":          str(MODEL_CONFIG["model_path"]),
        "labels_file":    str(MODEL_CONFIG["labels_path"]),
        "images_per_class": IMAGES_PER_CLASS,
        "total_tested":   grand_total,
        "total_correct":  grand_correct,
        "accuracy_pct":   round(grand_acc, 2),
        "top3_pct":       round(grand_top3 / grand_total * 100, 2) if grand_total else 0,
        "low_conf_pct":   round(grand_fallback / grand_total * 100, 2) if grand_total else 0,
        "elapsed_sec":    round(elapsed, 1),
        "per_class":      {},
    }

    for cn, cres in all_results.items():
        tested   = [r for r in cres if not r.get("error")]
        n_ok     = sum(1 for r in tested if r["correct"])
        n_top3   = sum(1 for r in tested if r["in_top3"])
        n_fb     = sum(1 for r in tested if r["fallback"])
        confs    = [r["conf"] for r in tested]
        wrong    = [r for r in tested if not r["correct"]]
        confused = Counter(r["pred"] for r in wrong)
        summary["per_class"][cn] = {
            "tested":       len(tested),
            "correct":      n_ok,
            "accuracy_pct": round(n_ok / len(tested) * 100, 1) if tested else 0,
            "in_top3":      n_top3,
            "low_conf":     n_fb,
            "conf_mean":    round(sum(confs)/len(confs), 1) if confs else 0,
            "conf_min":     round(min(confs), 1) if confs else 0,
            "conf_max":     round(max(confs), 1) if confs else 0,
            "confused_with": dict(confused.most_common(3)),
            "raw":          tested,
        }

    REPORT_FILE.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    log(f"Report JSON: {REPORT_FILE}")

    _print_report(summary)


def _print_report(s: dict):
    N = IMAGES_PER_CLASS
    SEP  = "═" * 75
    SEP2 = "─" * 75
    print(f"\n{SEP}")
    print(f"  DELTA-PLANT  ·  REPORT DIAGNOSTICA MODELLO — 33 CLASSI PLANTVILLAGE")
    print(f"  Data     : {s['date']}")
    print(f"  Modello  : {s['model']}")
    print(f"  Fonte    : GitHub spMohanty/PlantVillage-Dataset  ({N} immagini/classe)")
    print(SEP)
    print(f"\n  ▶ RISULTATO GLOBALE")
    print(f"  {SEP2}")
    print(f"  Immagini testate     : {s['total_tested']}")
    print(f"  Corrette (top-1)     : {s['total_correct']}  →  {s['accuracy_pct']:.1f}%")
    print(f"  Corrette (top-3)     : {round(s['top3_pct']*s['total_tested']/100):.0f}  →  {s['top3_pct']:.1f}%")
    print(f"  Bassa confidenza (<50%): {round(s['low_conf_pct']*s['total_tested']/100):.0f}  →  {s['low_conf_pct']:.1f}%")
    print(f"  Tempo totale         : {s['elapsed_sec']/60:.1f} min")
    print()
    print(f"  {'CLASSE':<38} {'N':>3}  {'ACC':>6}  {'TOP3':>5}  {'CONF Ø':>7}  {'STATO'}")
    print(f"  {SEP2}")

    rows = sorted(s["per_class"].items(), key=lambda x: x[1]["accuracy_pct"], reverse=True)
    for cls, d in rows:
        if d["accuracy_pct"] >= 80:
            stato = "✓ OK"
        elif d["accuracy_pct"] >= 50:
            stato = "~ MEDIOCRE"
        else:
            stato = "✗ SCARSO"
        top3_n = d["in_top3"]
        print(f"  {cls:<38} {d['tested']:>3}  {d['accuracy_pct']:>5.0f}%  "
              f"{top3_n:>3}/{d['tested']}  {d['conf_mean']:>6.1f}%  {stato}")

    print(f"\n  ▶ ANALISI CONFUSIONI (classi con accuratezza < 100%)")
    print(f"  {SEP2}")
    for cls, d in rows:
        if d["accuracy_pct"] < 100 and d["confused_with"]:
            n_err = d["tested"] - d["correct"]
            print(f"  {cls}  ({n_err} errori / {d['tested']} test):")
            for pred, cnt in d["confused_with"].items():
                pct = cnt / d["tested"] * 100
                print(f"    → {pred:<52} ×{cnt}  ({pct:.0f}%)")
    print(SEP)
    print()


if __name__ == "__main__":
    main()
