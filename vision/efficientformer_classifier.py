"""
DELTA - vision/efficientformer_classifier.py
Backend EfficientFormerV2-S1 per inferenza TFLite edge + explainability LayerCAM.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
import importlib
import logging
import math
import os
import time

import numpy as np

from ai.tflite_inference_runner import decode_prediction
from .vision_backend import VisionBackend

LOGGER = logging.getLogger("delta.vision.efficientformer")


@dataclass
class _InterpreterBundle:
    """Container minimale per interprete TFLite e metadati runtime."""

    interpreter: Any
    input_details: list[dict[str, Any]]
    output_details: list[dict[str, Any]]
    runtime_name: str
    model_key: str
    model_path: Path
    quantization: str


class EfficientFormerClassifier(VisionBackend):
    """
    Backend vision per EfficientFormerV2-S1 con supporto edge-first.

    Caratteristiche principali / Main features:
    - TFLite float16 di default con fallback/int8 opzionale
    - preprocessing RGB 224x224 quasi identico a MobileNetV2: [0,255] -> [-1, 1]
    - ensemble probabilistico con MobileNetV2 tramite media pesata
    - explainability LayerCAM tramite reference model PyTorch opzionale
    - output compatibile con il contratto DELTA: class, confidence, top_k, model, error
    """

    def __init__(
        self,
        model_key: str = "efficientformer",
        quantization: Optional[str] = None,
        ensemble_enabled: Optional[bool] = None,
    ):
        from core.config import ACTIVE_MODEL, DEFAULT_LABELS, MODEL_CONFIG, MODELS_REGISTRY

        requested_key = model_key if model_key in MODELS_REGISTRY else ACTIVE_MODEL
        if requested_key not in MODELS_REGISTRY:
            requested_key = next(iter(MODELS_REGISTRY), "generale")

        self._registry = MODELS_REGISTRY
        self._default_labels = list(DEFAULT_LABELS)
        self._global_model_cfg = MODEL_CONFIG
        self._model_key = requested_key
        self._base_cfg = dict(MODELS_REGISTRY.get(self._model_key, {}))
        self._quantization = (quantization or self._base_cfg.get("quantization") or "float16").lower()
        self._cfg = self._resolve_variant_config(self._base_cfg, self._quantization)
        self._ensemble_enabled = (
            self._cfg.get("enable_ensemble", False)
            if ensemble_enabled is None
            else bool(ensemble_enabled)
        )
        self._ensemble_weights = self._normalize_weights(self._cfg.get("ensemble_weights", [0.65, 0.35]))
        self._top_k = int(self._cfg.get("top_k", 3))
        self._threads = int(self._cfg.get("num_threads", self._global_model_cfg.get("num_threads", 4)))

        self._labels: list[str] = self._load_labels(self._cfg)
        self._primary: Optional[_InterpreterBundle] = None
        self._ensemble_bundle: Optional[_InterpreterBundle] = None
        self._ensemble_model_key: Optional[str] = None
        self._ready = False
        self._error: Optional[str] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._last_probabilities: Optional[np.ndarray] = None

        self._torch = None
        self._torch_model = None
        self._torch_target_layer = None
        self._torch_target_layer_name: Optional[str] = None
        self._explainability_error: Optional[str] = None

        self._init_classifier()
        self._init_explainer()

    @property
    def model_name(self) -> str:
        return self._cfg.get("display_name") or self._model_key

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def can_explain(self) -> bool:
        return self._torch_model is not None and self._torch_target_layer is not None

    def infer(self, image_path: str | Path) -> Dict[str, Any]:
        image = self._read_bgr_image(image_path)
        return self.infer_image(image, source=image_path)

    def infer_image(self, image: np.ndarray, source: Optional[str | Path] = None) -> Dict[str, Any]:
        """Inferenza diretta su array BGR gia in memoria / in-memory BGR inference."""
        if not self._ready or self._primary is None:
            return self._error_payload(self._error or "EfficientFormer non inizializzato")

        try:
            started = time.perf_counter()
            primary_probs = self._run_tflite(self._primary, image)
            probabilities = primary_probs
            ensemble_meta: Optional[Dict[str, Any]] = None

            if self._ensemble_enabled and self._ensemble_bundle is not None:
                secondary_probs = self._run_tflite(self._ensemble_bundle, image)
                probabilities = self._average_probabilities(primary_probs, secondary_probs)
                ensemble_meta = {
                    "enabled": True,
                    "weights": list(self._ensemble_weights),
                    "members": [self._primary.model_key, self._ensemble_bundle.model_key],
                }

            result = decode_prediction(probabilities, self._labels, top_k=self._top_k)
            latency_ms = (time.perf_counter() - started) * 1000.0

            result.update({
                "model": self.model_name,
                "backend": self._primary.runtime_name,
                "quantization": self._quantization,
                "ensemble": bool(ensemble_meta),
                "latency_ms": round(latency_ms, 2),
                "explainability_available": self.can_explain,
                "top3": list(result.get("top_k", []))[:3],
                "simulated": False,
                "fallback": False,
                "above_threshold": float(result.get("confidence", 0.0)) >= float(
                    self._global_model_cfg.get("confidence_threshold", 0.65)
                ),
            })
            if source is not None:
                result["source"] = str(source)
            if ensemble_meta is not None:
                result["ensemble_details"] = ensemble_meta

            self._last_result = result
            self._last_probabilities = probabilities
            return result
        except Exception as exc:
            LOGGER.error("Errore inferenza EfficientFormer: %s", exc, exc_info=True)
            return self._error_payload(str(exc))

    def generate_heatmap(self, image: str | Path | np.ndarray) -> Dict[str, Any]:
        """Alias operativo richiesto dal bot / convenience alias for Telegram."""
        return self.get_explanation(image)

    def get_explanation(
        self,
        image: str | Path | np.ndarray,
        target_class_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Genera overlay LayerCAM pronto per Telegram.

        Ritorna un dizionario con:
        - original: immagine BGR originale
        - heatmap: heatmap colorata BGR
        - overlay: overlay BGR pronto per invio
        - image_bytes: PNG bytes del solo overlay
        """
        if isinstance(image, (str, Path)):
            original = self._read_bgr_image(image)
            source = str(image)
        else:
            original = self._ensure_bgr(image)
            source = None

        prediction = self.infer_image(original, source=source)
        if prediction.get("error"):
            return {
                "model": self.model_name,
                "method": self._cfg.get("explainability_method", "layercam"),
                "error": prediction["error"],
            }

        if not self.can_explain:
            message = self._explainability_error or "Explainability non disponibile: backend PyTorch assente"
            LOGGER.warning(message)
            return {
                "model": self.model_name,
                "method": self._cfg.get("explainability_method", "layercam"),
                "class": prediction.get("class"),
                "confidence": prediction.get("confidence"),
                "error": message,
            }

        try:
            class_index = target_class_index
            if class_index is None:
                class_index = int(prediction.get("class_index", 0))

            heatmap = self._compute_layercam(original, class_index)
            overlay = self._overlay_heatmap(original, heatmap)
            explanation = {
                "model": self.model_name,
                "method": self._cfg.get("explainability_method", "layercam"),
                "target_layer": self._torch_target_layer_name,
                "class": prediction.get("class"),
                "class_index": class_index,
                "confidence": prediction.get("confidence"),
                "original": original,
                "heatmap": self._colorize_heatmap(heatmap),
                "overlay": overlay,
                "image_bytes": self._encode_png(overlay),
                "mime_type": "image/png",
                "summary": self._build_explanation_summary(prediction),
            }
            if source is not None:
                explanation["source"] = source
            return explanation
        except Exception as exc:
            LOGGER.error("Errore generate_heatmap/get_explanation: %s", exc, exc_info=True)
            return {
                "model": self.model_name,
                "method": self._cfg.get("explainability_method", "layercam"),
                "class": prediction.get("class"),
                "confidence": prediction.get("confidence"),
                "error": str(exc),
            }

    def _init_classifier(self) -> None:
        if not self._cfg:
            self._error = "Configurazione EfficientFormer assente nel MODELS_REGISTRY"
            LOGGER.warning(self._error)
            return

        try:
            self._primary = self._create_interpreter_bundle(self._cfg, self._model_key)
            self._align_labels_with_output(self._labels, self._primary.output_details)
        except Exception as exc:
            fallback_cfg = self._resolve_primary_fallback_config(exc)
            if fallback_cfg is None:
                self._error = str(exc)
                LOGGER.warning("EfficientFormer primario non disponibile: %s", exc)
                return

            try:
                self._primary = self._create_interpreter_bundle(fallback_cfg, self._model_key)
                self._cfg = fallback_cfg
                self._quantization = str(fallback_cfg.get("quantization", self._quantization)).lower()
                self._align_labels_with_output(self._labels, self._primary.output_details)
            except Exception as fallback_exc:
                self._error = str(fallback_exc)
                LOGGER.warning("EfficientFormer primario non disponibile: %s", fallback_exc)
                return

        if self._ensemble_enabled:
            try:
                self._ensemble_model_key = str(self._cfg.get("ensemble_model_key", "generale"))
                ensemble_cfg = self._registry.get(self._ensemble_model_key, {})
                if not ensemble_cfg:
                    raise RuntimeError(f"Config ensemble non trovata: {self._ensemble_model_key}")
                ensemble_quant = str(ensemble_cfg.get("quantization", self._quantization)).lower()
                ensemble_cfg = self._resolve_variant_config(ensemble_cfg, ensemble_quant)
                self._ensemble_bundle = self._create_interpreter_bundle(ensemble_cfg, self._ensemble_model_key)
                if self._output_size(self._primary.output_details) != self._output_size(self._ensemble_bundle.output_details):
                    LOGGER.warning(
                        "Disabilito ensemble: output dimension mismatch primary=%s secondary=%s",
                        self._output_size(self._primary.output_details),
                        self._output_size(self._ensemble_bundle.output_details),
                    )
                    self._ensemble_bundle = None
            except Exception as exc:
                LOGGER.warning("Ensemble MobileNet disabilitato: %s", exc)
                self._ensemble_bundle = None

        self._ready = self._primary is not None
        if self._ready:
            LOGGER.info(
                "EfficientFormerClassifier pronto: model=%s quant=%s threads=%d ensemble=%s",
                self._model_key,
                self._quantization,
                self._threads,
                bool(self._ensemble_bundle),
            )

    def _resolve_primary_fallback_config(self, primary_exc: Exception) -> Optional[Dict[str, Any]]:
        if self._quantization not in {"float16", "int8"}:
            return None

        fallback_cfg = self._resolve_variant_config(self._base_cfg, "float32")
        fallback_path = fallback_cfg.get("model_path")
        if not fallback_path or fallback_path == self._cfg.get("model_path"):
            return None

        try:
            resolved_path = self._resolve_model_path(fallback_cfg)
        except Exception:
            return None

        LOGGER.warning(
            "EfficientFormer %s non disponibile (%s), provo fallback float32: %s",
            self._quantization,
            primary_exc,
            resolved_path,
        )
        return fallback_cfg

    def _init_explainer(self) -> None:
        if not self._cfg.get("enable_explainability", True):
            self._explainability_error = "Explainability disabilitata da configurazione"
            return

        checkpoint_path_raw = (
            self._cfg.get("explainability_checkpoint")
            or self._cfg.get("pytorch_checkpoint")
            or self._cfg.get("checkpoint_path")
        )
        if not checkpoint_path_raw:
            self._explainability_error = "Checkpoint PyTorch per LayerCAM non configurato"
            return

        checkpoint_path = self._resolve_path(str(checkpoint_path_raw))
        if not checkpoint_path.exists():
            self._explainability_error = f"Checkpoint LayerCAM non trovato: {checkpoint_path}"
            return

        try:
            torch = importlib.import_module("torch")
            timm = importlib.import_module("timm")
        except ImportError as exc:
            self._explainability_error = f"Dipendenza explainability mancante: {exc}"
            LOGGER.warning(self._explainability_error)
            return

        torch_model_name = str(self._cfg.get("torch_model_name", "efficientformerv2_s1"))
        num_classes = int(self._cfg.get("num_classes", len(self._labels) or 33))

        try:
            model = timm.create_model(torch_model_name, pretrained=False, num_classes=num_classes)
            state = torch.load(str(checkpoint_path), map_location="cpu")
            if isinstance(state, dict) and "state_dict" in state:
                state = state["state_dict"]
            if isinstance(state, dict):
                state = {str(k).replace("module.", ""): v for k, v in state.items()}
            missing, unexpected = model.load_state_dict(state, strict=False)
            model.eval()

            self._torch = torch
            self._torch_model = model
            self._torch_target_layer_name = str(
                self._cfg.get("explainability_target_layer") or self._auto_select_target_layer(model)
            )
            self._torch_target_layer = self._resolve_module_by_name(model, self._torch_target_layer_name)

            if missing:
                LOGGER.warning("EfficientFormer LayerCAM: missing keys=%s", list(missing)[:8])
            if unexpected:
                LOGGER.warning("EfficientFormer LayerCAM: unexpected keys=%s", list(unexpected)[:8])

            LOGGER.info(
                "Explainability pronta: method=%s target_layer=%s",
                self._cfg.get("explainability_method", "layercam"),
                self._torch_target_layer_name,
            )
        except Exception as exc:
            self._explainability_error = str(exc)
            self._torch = None
            self._torch_model = None
            self._torch_target_layer = None
            LOGGER.warning("Explainability EfficientFormer non disponibile: %s", exc)

    def _create_interpreter_bundle(self, cfg: Dict[str, Any], model_key: str) -> _InterpreterBundle:
        model_path = self._resolve_model_path(cfg)
        tflite_module, runtime_name = self._import_tflite_runtime()
        delegates = self._load_delegates(tflite_module, cfg)

        kwargs: Dict[str, Any] = {
            "model_path": str(model_path),
            "num_threads": int(cfg.get("num_threads", self._threads)),
        }
        if delegates:
            kwargs["experimental_delegates"] = delegates

        interpreter = tflite_module.Interpreter(**kwargs)
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        LOGGER.info(
            "Loaded TFLite bundle model=%s runtime=%s input=%s output=%s",
            model_key,
            runtime_name,
            tuple(input_details[0].get("shape", [])),
            tuple(output_details[0].get("shape", [])),
        )

        return _InterpreterBundle(
            interpreter=interpreter,
            input_details=input_details,
            output_details=output_details,
            runtime_name=runtime_name,
            model_key=model_key,
            model_path=model_path,
            quantization=str(cfg.get("quantization", self._quantization)).lower(),
        )

    def _run_tflite(self, bundle: _InterpreterBundle, image_bgr: np.ndarray) -> np.ndarray:
        input_tensor = self._preprocess_for_tflite(image_bgr, bundle.input_details)
        in0 = bundle.input_details[0]
        out0 = bundle.output_details[0]

        input_dtype = in0.get("dtype")
        if input_dtype is None:
            raise RuntimeError("Input dtype TFLite assente")

        if np.issubdtype(input_dtype, np.integer):
            scale, zero_point = in0.get("quantization", (1.0, 0))
            if not scale:
                raise RuntimeError("Input quantization invalida: scale=0")
            quantized = np.rint(input_tensor / scale + zero_point).astype(input_dtype)
            bundle.interpreter.set_tensor(in0["index"], quantized)
        elif np.dtype(input_dtype) == np.float16:
            bundle.interpreter.set_tensor(in0["index"], input_tensor.astype(np.float16))
        else:
            bundle.interpreter.set_tensor(in0["index"], input_tensor.astype(np.float32))

        bundle.interpreter.invoke()
        raw_output = bundle.interpreter.get_tensor(out0["index"])

        out_scale, out_zero = out0.get("quantization", (1.0, 0))
        if out_scale and out_scale != 0:
            logits = (raw_output.astype(np.float32) - out_zero) * out_scale
        else:
            logits = raw_output.astype(np.float32)

        vector = logits[0]
        if float(np.min(vector)) >= 0.0 and abs(float(np.sum(vector)) - 1.0) < 0.05:
            return vector.astype(np.float32)
        return self._softmax(vector)

    def _preprocess_for_tflite(self, image_bgr: np.ndarray, input_details: list[dict[str, Any]]) -> np.ndarray:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per EfficientFormerClassifier") from exc

        image = self._ensure_bgr(image_bgr)
        target_w, target_h = self._cfg.get("input_size", (224, 224))
        interpolation = cv2.INTER_AREA if image.shape[0] > target_h else cv2.INTER_LINEAR
        resized = cv2.resize(image, (int(target_w), int(target_h)), interpolation=interpolation)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        float_tensor = (rgb.astype(np.float32) / 127.5) - 1.0
        batched = np.expand_dims(float_tensor, axis=0)

        input_dtype = input_details[0].get("dtype")
        if input_dtype is not None and np.dtype(input_dtype) == np.float16:
            return batched.astype(np.float16)
        return batched.astype(np.float32)

    def _compute_layercam(self, image_bgr: np.ndarray, class_index: int) -> np.ndarray:
        if not self.can_explain:
            raise RuntimeError(self._explainability_error or "LayerCAM non disponibile")

        torch = self._torch
        model = self._torch_model
        layer = self._torch_target_layer

        activations: Dict[str, Any] = {}
        gradients: Dict[str, Any] = {}

        def _forward_hook(_module, _inputs, output):
            activations["value"] = output

        def _backward_hook(_module, _grad_input, grad_output):
            gradients["value"] = grad_output[0]

        forward_handle = layer.register_forward_hook(_forward_hook)
        backward_handle = layer.register_full_backward_hook(_backward_hook)

        try:
            tensor = self._preprocess_for_torch(image_bgr)
            tensor.requires_grad_(True)
            model.zero_grad(set_to_none=True)
            logits = model(tensor)
            if isinstance(logits, (tuple, list)):
                logits = logits[0]
            score = logits[:, int(class_index)].sum()
            score.backward()

            if "value" not in activations or "value" not in gradients:
                raise RuntimeError("Hook LayerCAM non ha catturato attivazioni/gradienti")

            act = self._to_spatial_tensor(activations["value"].detach())
            grad = self._to_spatial_tensor(gradients["value"].detach())

            if tuple(act.shape[-2:]) != tuple(grad.shape[-2:]):
                grad = torch.nn.functional.interpolate(
                    grad,
                    size=tuple(act.shape[-2:]),
                    mode="bilinear",
                    align_corners=False,
                )

            cam = torch.relu((torch.relu(grad) * act).sum(dim=1))[0]
            cam = cam - cam.min()
            if float(cam.max()) > 0.0:
                cam = cam / cam.max()

            cam_np = cam.detach().cpu().numpy().astype(np.float32)
            try:
                import cv2  # type: ignore
            except ImportError as exc:
                raise RuntimeError("OpenCV richiesto per resize LayerCAM") from exc
            resized = cv2.resize(cam_np, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
            return np.clip(resized, 0.0, 1.0)
        finally:
            forward_handle.remove()
            backward_handle.remove()

    def _preprocess_for_torch(self, image_bgr: np.ndarray):
        torch = self._torch
        if torch is None:
            raise RuntimeError("PyTorch non disponibile")

        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per preprocessing LayerCAM") from exc

        target_w, target_h = self._cfg.get("input_size", (224, 224))
        rgb = cv2.cvtColor(self._ensure_bgr(image_bgr), cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (int(target_w), int(target_h)), interpolation=cv2.INTER_LINEAR)
        tensor = resized.astype(np.float32) / 255.0

        mean = np.asarray(self._cfg.get("torch_input_mean", [0.5, 0.5, 0.5]), dtype=np.float32)
        std = np.asarray(self._cfg.get("torch_input_std", [0.5, 0.5, 0.5]), dtype=np.float32)
        tensor = (tensor - mean) / std
        tensor = np.transpose(tensor, (2, 0, 1))
        return torch.from_numpy(tensor).unsqueeze(0)

    def _to_spatial_tensor(self, tensor: Any):
        torch = self._torch
        if torch is None:
            raise RuntimeError("PyTorch non disponibile")
        if not hasattr(tensor, "dim"):
            raise RuntimeError("Tensore LayerCAM non valido")

        if tensor.dim() == 4:
            return tensor

        if tensor.dim() != 3:
            raise RuntimeError(f"Shape LayerCAM non supportata: {tuple(tensor.shape)}")

        b, dim1, dim2 = tensor.shape
        if self._is_square(dim1):
            side = int(math.sqrt(dim1))
            return tensor.transpose(1, 2).reshape(b, dim2, side, side)
        if self._is_square(dim2):
            side = int(math.sqrt(dim2))
            return tensor.reshape(b, dim1, side, side)
        raise RuntimeError(f"Impossibile ricostruire mappa spaziale da shape {tuple(tensor.shape)}")

    def _auto_select_target_layer(self, model: Any) -> str:
        torch = self._torch
        if torch is None:
            raise RuntimeError("PyTorch non disponibile")

        candidates: list[str] = []
        hooks = []

        def _capture(name: str):
            def _hook(_module, _inputs, output):
                if hasattr(output, "dim") and output.dim() in (3, 4):
                    shape = tuple(int(v) for v in output.shape)
                    if self._is_spatial_shape(shape):
                        candidates.append(name)
            return _hook

        for name, module in model.named_modules():
            if not name:
                continue
            if any(True for _ in module.children()):
                continue
            hooks.append(module.register_forward_hook(_capture(name)))

        try:
            with torch.no_grad():
                dummy = torch.zeros(1, 3, int(self._cfg.get("input_size", (224, 224))[1]), int(self._cfg.get("input_size", (224, 224))[0]))
                _ = model(dummy)
        finally:
            for handle in hooks:
                handle.remove()

        if not candidates:
            raise RuntimeError("Nessun layer spaziale trovato per LayerCAM")

        preferred = [
            name for name in candidates
            if any(token in name.lower() for token in ("network", "stage", "block", "conv"))
        ]
        return (preferred or candidates)[-1]

    def _overlay_heatmap(self, image_bgr: np.ndarray, heatmap: np.ndarray) -> np.ndarray:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per overlay explainability") from exc

        colored = self._colorize_heatmap(heatmap)
        alpha = float(self._cfg.get("overlay_alpha", 0.40))
        base = self._ensure_bgr(image_bgr)
        overlay = cv2.addWeighted(base, 1.0 - alpha, colored, alpha, 0.0)
        return self._annotate_focus_region(overlay, heatmap)

    def _annotate_focus_region(self, overlay_bgr: np.ndarray, heatmap: np.ndarray) -> np.ndarray:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per annotazione focus explainability") from exc

        normalized = np.clip(np.asarray(heatmap, dtype=np.float32), 0.0, 1.0)
        if normalized.size == 0:
            return overlay_bgr

        peak_value = float(np.max(normalized))
        if peak_value <= 0.0:
            return overlay_bgr

        annotated = overlay_bgr.copy()
        image_h, image_w = normalized.shape[:2]
        min_area = max(32.0, float(image_h * image_w) * 0.001)
        smoothed = cv2.GaussianBlur(normalized, (0, 0), sigmaX=6.0, sigmaY=6.0)
        peak_ratio = float(self._cfg.get("focus_peak_ratio", 0.70))
        min_threshold = float(self._cfg.get("focus_min_threshold", 0.50))
        threshold = max(min_threshold, peak_value * peak_ratio)

        mask = np.uint8(smoothed >= threshold) * 255
        kernel = np.ones((5, 5), dtype=np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = [contour for contour in contours if cv2.contourArea(contour) >= min_area]

        if contours:
            contour = max(contours, key=cv2.contourArea)
            if len(contour) >= 5:
                (focus_x, focus_y), axes, angle = cv2.fitEllipse(contour)
                center = (int(round(focus_x)), int(round(focus_y)))
                expanded_axes = (
                    max(20, int(round(axes[0] * 0.56))),
                    max(20, int(round(axes[1] * 0.56))),
                )
                cv2.ellipse(
                    annotated,
                    center,
                    expanded_axes,
                    float(angle),
                    0,
                    360,
                    (0, 0, 0),
                    8,
                    lineType=cv2.LINE_AA,
                )
                cv2.ellipse(
                    annotated,
                    center,
                    expanded_axes,
                    float(angle),
                    0,
                    360,
                    (0, 255, 255),
                    4,
                    lineType=cv2.LINE_AA,
                )
                marker_radius = max(10, int(round(min(expanded_axes) * 0.24)))
            else:
                (focus_x, focus_y), radius = cv2.minEnclosingCircle(contour)
                center = (int(round(focus_x)), int(round(focus_y)))
                marker_radius = max(18, int(round(radius * 1.10)))
                cv2.circle(annotated, center, marker_radius, (0, 0, 0), 8, lineType=cv2.LINE_AA)
                cv2.circle(annotated, center, marker_radius, (0, 255, 255), 4, lineType=cv2.LINE_AA)
        else:
            peak_y, peak_x = np.unravel_index(int(np.argmax(normalized)), normalized.shape)
            center = (int(peak_x), int(peak_y))
            marker_radius = max(18, min(image_h, image_w) // 10)
            cv2.circle(annotated, center, marker_radius, (0, 0, 0), 8, lineType=cv2.LINE_AA)
            cv2.circle(annotated, center, marker_radius, (0, 255, 255), 4, lineType=cv2.LINE_AA)

        cv2.circle(annotated, center, max(3, marker_radius // 6), (0, 0, 0), -1, lineType=cv2.LINE_AA)
        cv2.circle(annotated, center, max(2, marker_radius // 8), (255, 255, 255), -1, lineType=cv2.LINE_AA)
        return annotated

    def _colorize_heatmap(self, heatmap: np.ndarray) -> np.ndarray:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per colorize heatmap") from exc

        normalized = np.uint8(np.clip(heatmap, 0.0, 1.0) * 255.0)
        colormap_name = str(self._cfg.get("colormap", "jet")).strip().lower()
        colormap = cv2.COLORMAP_VIRIDIS if colormap_name == "viridis" else cv2.COLORMAP_JET
        return cv2.applyColorMap(normalized, colormap)

    def _encode_png(self, image_bgr: np.ndarray) -> bytes:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per export PNG") from exc

        ok, encoded = cv2.imencode(".png", image_bgr)
        if not ok:
            raise RuntimeError("Impossibile serializzare overlay PNG")
        return bytes(encoded.tobytes())

    def _import_tflite_runtime(self):
        for module_name in (
            "tflite_runtime.interpreter",
            "ai_edge_litert.interpreter",
            "tensorflow.lite",
        ):
            try:
                module = importlib.import_module(module_name)
                return module, module_name
            except ImportError:
                continue
        raise RuntimeError("Nessun runtime TFLite disponibile per EfficientFormer")

    def _load_delegates(self, tflite_module: Any, cfg: Dict[str, Any]) -> list[Any]:
        if not cfg.get("enable_delegate", True):
            return []

        delegate_library = cfg.get("delegate_library") or os.environ.get("DELTA_TFLITE_DELEGATE")
        if not delegate_library:
            LOGGER.debug("Uso delegate CPU/XNNPACK builtin con num_threads=%d", self._threads)
            return []

        if not hasattr(tflite_module, "load_delegate"):
            LOGGER.warning("Runtime TFLite corrente non supporta load_delegate(%s)", delegate_library)
            return []

        try:
            options = dict(cfg.get("delegate_options", {}))
            return [tflite_module.load_delegate(str(delegate_library), options)]
        except Exception as exc:
            LOGGER.warning("Delegate esterno non caricato (%s): %s", delegate_library, exc)
            return []

    def _resolve_variant_config(self, cfg: Dict[str, Any], quantization: str) -> Dict[str, Any]:
        merged = dict(cfg)
        variants = cfg.get("variants") or {}
        if isinstance(variants, dict) and quantization in variants:
            merged.update(dict(variants[quantization]))
        else:
            alt_key = f"model_path_{quantization}"
            if alt_key in cfg:
                merged["model_path"] = cfg[alt_key]
        merged["quantization"] = quantization
        return merged

    def _resolve_model_path(self, cfg: Dict[str, Any]) -> Path:
        model_path = cfg.get("model_path")
        if not model_path:
            raise RuntimeError(f"model_path mancante per modello {self._model_key}")
        resolved = self._resolve_path(str(model_path))
        if not resolved.exists():
            raise RuntimeError(f"Modello TFLite non trovato: {resolved}")
        return resolved

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(os.path.expandvars(os.path.expanduser(raw_path)))
        if candidate.is_absolute():
            return candidate.resolve(strict=False)

        cwd_candidate = (Path.cwd() / candidate).resolve(strict=False)
        if cwd_candidate.exists():
            return cwd_candidate

        from core.config import BASE_DIR
        return (BASE_DIR / candidate).resolve(strict=False)

    def _load_labels(self, cfg: Dict[str, Any]) -> list[str]:
        labels_path_raw = cfg.get("labels_path")
        if labels_path_raw:
            labels_path = self._resolve_path(str(labels_path_raw))
            if labels_path.exists():
                labels = [
                    line.strip()
                    for line in labels_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                if labels:
                    return labels

        classes = cfg.get("classes")
        if classes:
            return [str(item).strip() for item in classes if str(item).strip()]
        return list(self._default_labels)

    def _align_labels_with_output(self, labels: list[str], output_details: list[dict[str, Any]]) -> None:
        output_size = self._output_size(output_details)
        if output_size <= 0:
            return
        if len(labels) > output_size:
            LOGGER.warning("Labels > output classes (%d > %d): tronco le labels extra", len(labels), output_size)
            del labels[output_size:]
            return
        if len(labels) < output_size:
            LOGGER.warning("Labels < output classes (%d < %d): aggiungo placeholder", len(labels), output_size)
            labels.extend(f"class_{index}" for index in range(len(labels), output_size))

    def _average_probabilities(self, primary: np.ndarray, secondary: np.ndarray) -> np.ndarray:
        w_primary, w_secondary = self._ensemble_weights
        combined = (primary * w_primary) + (secondary * w_secondary)
        total = float(np.sum(combined))
        if total <= 0.0:
            return combined.astype(np.float32)
        return (combined / total).astype(np.float32)

    def _build_explanation_summary(self, prediction: Dict[str, Any]) -> str:
        return (
            "LayerCAM evidenzia le regioni fogliari che hanno contribuito maggiormente "
            f"alla predizione {prediction.get('class', 'N/A')} "
            f"({float(prediction.get('confidence', 0.0)) * 100:.1f}%)."
        )

    def _error_payload(self, message: str) -> Dict[str, Any]:
        return {
            "class": "errore",
            "confidence": 0.0,
            "top_k": [],
            "error": message,
            "model": self.model_name,
        }

    def _read_bgr_image(self, image_path: str | Path) -> np.ndarray:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per EfficientFormerClassifier") from exc

        path = self._resolve_path(str(image_path))
        if not path.exists():
            raise FileNotFoundError(f"Immagine non trovata: {path}")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Impossibile leggere immagine: {path}")
        return image

    def _ensure_bgr(self, image: np.ndarray) -> np.ndarray:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV richiesto per EfficientFormerClassifier") from exc

        if image is None or getattr(image, "size", 0) == 0:
            raise ValueError("Immagine vuota per inferenza EfficientFormer")
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"Formato immagine non supportato: shape={getattr(image, 'shape', None)}")
        return image.copy()

    def _resolve_module_by_name(self, model: Any, name: str) -> Any:
        module = model
        for chunk in name.split("."):
            if chunk.isdigit():
                module = module[int(chunk)]
            else:
                module = getattr(module, chunk)
        return module

    def _is_spatial_shape(self, shape: Sequence[int]) -> bool:
        if len(shape) == 4:
            return int(shape[-1]) > 1 and int(shape[-2]) > 1
        if len(shape) == 3:
            return self._is_square(int(shape[1])) or self._is_square(int(shape[2]))
        return False

    @staticmethod
    def _output_size(output_details: list[dict[str, Any]]) -> int:
        if not output_details:
            return 0
        shape = output_details[0].get("shape")
        if shape is None or len(shape) == 0:
            return 0
        return int(shape[-1])

    @staticmethod
    def _normalize_weights(weights: Sequence[float]) -> tuple[float, float]:
        if len(weights) < 2:
            return 0.5, 0.5
        total = float(weights[0]) + float(weights[1])
        if total <= 0:
            return 0.5, 0.5
        return float(weights[0]) / total, float(weights[1]) / total

    @staticmethod
    def _is_square(value: int) -> bool:
        if value <= 0:
            return False
        root = int(math.sqrt(value))
        return root * root == value

    @staticmethod
    def _softmax(vector: np.ndarray) -> np.ndarray:
        shifted = vector - np.max(vector)
        exp = np.exp(shifted)
        return (exp / np.sum(exp)).astype(np.float32)