"""
DELTA - ai/fine_tuning.py
Transfer learning leggero su dispositivo (on-device fine-tuning).
Permette di aggiornare il modello con nuove immagini etichettate dall'utente.
Utilizza un classificatore lineare addestrato sulle feature dell'ultimo layer.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

import numpy as np

from core.config import FINETUNING_CONFIG, MODEL_CONFIG, MODELS_DIR

logger = logging.getLogger("delta.ai.fine_tuning")


class FineTuner:
    """
    Gestisce il dataset utente e il fine-tuning del modello.
    Strategia: estrazione feature dall'ultimo layer TFLite + classificatore SVM/lineare.
    Approccio leggero compatibile con Raspberry Pi 5.
    """

    def __init__(
        self,
        model_loader,
        dataset_dir: Optional[Path | str] = None,
        save_path: Optional[Path | str] = None,
        min_samples_per_class: Optional[int] = None,
    ):
        self.model_loader = model_loader
        self.dataset_dir = Path(dataset_dir) if dataset_dir else Path(FINETUNING_CONFIG["dataset_dir"])
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.save_path = str(save_path) if save_path else FINETUNING_CONFIG["model_save_path"]
        self.min_samples_per_class = min_samples_per_class or FINETUNING_CONFIG["min_samples_per_class"]

    # ─────────────────────────────────────────────
    # GESTIONE DATASET
    # ─────────────────────────────────────────────

    def add_sample(self, image: np.ndarray, label: str, label_index: int) -> str:
        """
        Aggiunge un campione annotato al dataset locale.

        Args:
            image: immagine numpy (H, W, 3) uint8
            label: nome della classe
            label_index: indice numerico della classe

        Returns:
            percorso file salvato
        """
        try:
            import cv2  # type: ignore
        except ImportError:
            logger.error("OpenCV non disponibile per salvare campioni.")
            raise

        class_dir = self.dataset_dir / label
        class_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = class_dir / f"{label}_{ts}.jpg"
        cv2.imwrite(str(filename), image)
        logger.info("Campione aggiunto: %s → %s", label, filename)
        return str(filename)

    def get_dataset_stats(self) -> dict:
        """Restituisce statistiche sul dataset locale."""
        stats = {"total": 0, "classes": {}}
        if not self.dataset_dir.exists():
            return stats

        for class_dir in self.dataset_dir.iterdir():
            if class_dir.is_dir():
                count = len(list(class_dir.glob("*.jpg"))) + \
                        len(list(class_dir.glob("*.png")))
                stats["classes"][class_dir.name] = count
                stats["total"] += count
        return stats

    # ─────────────────────────────────────────────
    # FINE-TUNING
    # ─────────────────────────────────────────────

    def run_finetuning(self) -> bool:
        """
        Esegue il fine-tuning sul dataset locale.
        Usa scikit-learn per addestrare un classificatore lineare
        sulle feature estratte dall'encoder del modello TFLite.

        Returns:
            True se il fine-tuning è riuscito.
        """
        stats = self.get_dataset_stats()
        logger.info("Dataset fine-tuning: %d campioni, %d classi.",
                    stats["total"], len(stats["classes"]))

        # Verifica dati sufficienti
        min_samples = self.min_samples_per_class
        insufficient = [
            cls for cls, cnt in stats["classes"].items()
            if cnt < min_samples
        ]
        if insufficient:
            logger.warning(
                "Classi con campioni insufficienti (< %d): %s",
                min_samples, insufficient,
            )

        if stats["total"] < 2:
            logger.error("Dataset insufficiente per fine-tuning (< 2 campioni).")
            return False

        try:
            features, labels_encoded = self._extract_features()
            if len(features) == 0:
                logger.error("Nessuna feature estratta.")
                return False

            classifier = self._train_classifier(features, labels_encoded)
            self._save_classifier(classifier)
            logger.info("Fine-tuning completato con successo.")
            return True

        except Exception as exc:
            logger.error("Errore durante fine-tuning: %s", exc, exc_info=True)
            return False

    def _extract_features(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Carica immagini dal dataset e ne estrae le feature con il modello.
        """
        try:
            import cv2  # type: ignore
        except ImportError:
            raise ImportError("OpenCV richiesto per l'estrazione feature.")

        from vision.preprocessing import Preprocessor
        preprocessor = Preprocessor()

        features_list = []
        labels_list = []
        label_map = {}
        label_counter = 0

        for class_dir in sorted(self.dataset_dir.iterdir()):
            if not class_dir.is_dir():
                continue

            class_name = class_dir.name
            if class_name not in label_map:
                label_map[class_name] = label_counter
                label_counter += 1

            images = list(class_dir.glob("*.jpg")) + list(class_dir.glob("*.png"))
            for img_path in images:
                img = cv2.imread(str(img_path))
                if img is None:
                    continue
                processed = preprocessor.prepare_for_inference(img)
                feat = self._extract_single_feature(processed)
                if feat is not None:
                    features_list.append(feat)
                    labels_list.append(label_map[class_name])

        if not features_list:
            return np.array([]), np.array([])

        return np.array(features_list), np.array(labels_list)

    def _extract_single_feature(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Estrae il vettore feature dall'output penultimo layer."""
        if not self.model_loader.is_ready():
            # Fallback: flatten dell'immagine ridimensionata
            return image.flatten().astype(np.float32)

        try:
            interpreter = self.model_loader.interpreter
            input_details = self.model_loader.input_details
            output_details = self.model_loader.output_details

            scale, zero_point = self.model_loader.get_input_quantization()
            dtype = self.model_loader.get_input_dtype()

            if dtype is not None and np.issubdtype(dtype, np.integer):
                quantized = (image / scale + zero_point).astype(dtype)
                interpreter.set_tensor(input_details[0]["index"], quantized)
            else:
                interpreter.set_tensor(input_details[0]["index"], image.astype(np.float32))

            interpreter.invoke()
            output = interpreter.get_tensor(output_details[0]["index"])
            return output.flatten().astype(np.float32)
        except Exception as exc:
            logger.debug("Errore estrazione feature: %s", exc)
            return None

    def _train_classifier(self, features: np.ndarray, labels: np.ndarray):
        """Addestra un classificatore SVM lineare sulle feature estratte."""
        try:
            from sklearn.svm import LinearSVC  # type: ignore
            from sklearn.preprocessing import StandardScaler  # type: ignore
            from sklearn.pipeline import Pipeline  # type: ignore

            pipeline = Pipeline([
                ("scaler", StandardScaler()),
                ("svm", LinearSVC(max_iter=2000, C=1.0)),
            ])
            pipeline.fit(features, labels)
            logger.info("Classificatore addestrato su %d campioni.", len(features))
            return pipeline
        except ImportError:
            logger.error("scikit-learn non disponibile. Fine-tuning non eseguibile.")
            raise

    def _save_classifier(self, classifier):
        """Salva il classificatore addestrato su disco."""
        try:
            import pickle
            save_path = MODELS_DIR / "delta_classifier.pkl"
            with open(save_path, "wb") as f:
                pickle.dump(classifier, f)
            logger.info("Classificatore salvato in %s.", save_path)
        except Exception as exc:
            logger.error("Errore salvataggio classificatore: %s", exc)

    def interactive_labeling_session(self) -> List[Tuple[str, int]]:
        """
        Guida interattiva per etichettare immagini appena acquisite.
        Restituisce lista di (label, label_index) per i campioni aggiunti.
        """
        labels = self.model_loader.labels
        labeled = []

        print("\n=== SESSIONE ETICHETTATURA MANUALE ===")
        print("Classi disponibili:")
        for i, lbl in enumerate(labels):
            print(f"  [{i}] {lbl}")

        while True:
            risposta = input("\nAggiungi campione? (s/n): ").strip().lower()
            if risposta != "s":
                break

            idx_str = input("Inserisci indice classe: ").strip()
            if not idx_str.isdigit() or int(idx_str) >= len(labels):
                print("Indice non valido.")
                continue

            idx = int(idx_str)
            labeled.append((labels[idx], idx))
            print(f"Campione etichettato come: {labels[idx]}")

        return labeled
