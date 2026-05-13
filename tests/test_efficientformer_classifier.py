import types
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.export_efficientformer_tflite import _find_direct_tflite_artifact
from vision.efficientformer_classifier import EfficientFormerClassifier, _InterpreterBundle
from vision.vision_service import VisionService


def test_efficientformer_uses_float16_variant_from_registry(monkeypatch, tmp_path):
    import core.config as cfg

    labels_path = tmp_path / "labels.txt"
    labels_path.write_text("Apple_healthy\nTomato_healthy\n", encoding="utf-8")
    float16_model = tmp_path / "efficientformer_float16.tflite"
    int8_model = tmp_path / "efficientformer_int8.tflite"
    float16_model.write_bytes(b"float16")
    int8_model.write_bytes(b"int8")

    monkeypatch.setitem(
        cfg.MODELS_REGISTRY,
        "efficientformer_test",
        {
            "backend": "efficientformer",
            "labels_path": str(labels_path),
            "quantization": "float16",
            "variants": {
                "float16": {"model_path": str(float16_model)},
                "int8": {"model_path": str(int8_model)},
            },
        },
    )
    monkeypatch.setattr(cfg, "ACTIVE_MODEL", "efficientformer_test", raising=False)

    def fake_bundle(self, config, model_key):
        return _InterpreterBundle(
            interpreter=None,
            input_details=[{"shape": [1, 224, 224, 3], "dtype": np.float32}],
            output_details=[{"shape": [1, 2]}],
            runtime_name="fake-runtime",
            model_key=model_key,
            model_path=float16_model,
            quantization="float16",
        )

    monkeypatch.setattr(EfficientFormerClassifier, "_create_interpreter_bundle", fake_bundle)
    monkeypatch.setattr(EfficientFormerClassifier, "_init_explainer", lambda self: None)

    classifier = EfficientFormerClassifier(model_key="efficientformer_test")

    assert classifier.is_ready is True
    assert classifier._cfg["model_path"] == str(float16_model)
    assert classifier._quantization == "float16"


def test_export_int8_selection_ignores_dynamic_range_artifact(tmp_path):
    dynamic_range = tmp_path / "efficientformer_v2_s1_33classes_int8_dynamic_range_quant.tflite"
    dynamic_range.write_bytes(b"dynamic-range")

    assert _find_direct_tflite_artifact(tmp_path, "int8") is None

    full_integer = tmp_path / "efficientformer_v2_s1_33classes_full_integer_quant.tflite"
    full_integer.write_bytes(b"full-int8")

    assert _find_direct_tflite_artifact(tmp_path, "int8") == full_integer


def test_efficientformer_falls_back_from_int8_to_float32(monkeypatch, tmp_path):
    import core.config as cfg

    labels_path = tmp_path / "labels.txt"
    labels_path.write_text("Apple_healthy\nTomato_healthy\n", encoding="utf-8")
    int8_model = tmp_path / "efficientformer_int8.tflite"
    float32_model = tmp_path / "efficientformer_float32.tflite"
    int8_model.write_bytes(b"int8")
    float32_model.write_bytes(b"float32")

    monkeypatch.setitem(
        cfg.MODELS_REGISTRY,
        "efficientformer_test_int8",
        {
            "backend": "efficientformer",
            "labels_path": str(labels_path),
            "quantization": "int8",
            "variants": {
                "int8": {"model_path": str(int8_model)},
                "float32": {"model_path": str(float32_model)},
            },
        },
    )
    monkeypatch.setattr(cfg, "ACTIVE_MODEL", "efficientformer_test_int8", raising=False)

    def fake_bundle(self, config, model_key):
        if config["model_path"] == str(int8_model):
            raise RuntimeError("FlexErf non supportato")
        return _InterpreterBundle(
            interpreter=None,
            input_details=[{"shape": [1, 224, 224, 3], "dtype": np.float32}],
            output_details=[{"shape": [1, 2]}],
            runtime_name="fake-runtime",
            model_key=model_key,
            model_path=float32_model,
            quantization="float32",
        )

    monkeypatch.setattr(EfficientFormerClassifier, "_create_interpreter_bundle", fake_bundle)
    monkeypatch.setattr(EfficientFormerClassifier, "_init_explainer", lambda self: None)

    classifier = EfficientFormerClassifier(model_key="efficientformer_test_int8")

    assert classifier.is_ready is True
    assert classifier._cfg["model_path"] == str(float32_model)
    assert classifier._quantization == "float32"


def test_efficientformer_infer_image_ensembles_probabilities():
    classifier = EfficientFormerClassifier.__new__(EfficientFormerClassifier)
    classifier._cfg = {"display_name": "EfficientFormerV2-S1"}
    classifier._model_key = "efficientformer"
    classifier._primary = _InterpreterBundle(None, [{"dtype": np.float32}], [{"shape": [1, 3]}], "tflite", "efficientformer", None, "float16")
    classifier._ensemble_bundle = _InterpreterBundle(None, [{"dtype": np.float32}], [{"shape": [1, 3]}], "tflite", "generale", None, "float16")
    classifier._ensemble_enabled = True
    classifier._ensemble_weights = (0.75, 0.25)
    classifier._top_k = 3
    classifier._labels = ["Apple_healthy", "Tomato_healthy", "Potato_healthy"]
    classifier._ready = True
    classifier._global_model_cfg = {"confidence_threshold": 0.65}
    classifier._last_result = None
    classifier._last_probabilities = None
    classifier._torch_model = None
    classifier._torch_target_layer = None
    classifier._quantization = "float16"

    def fake_run(bundle, image):
        if bundle.model_key == "efficientformer":
            return np.asarray([0.2, 0.7, 0.1], dtype=np.float32)
        return np.asarray([0.1, 0.8, 0.1], dtype=np.float32)

    classifier._run_tflite = fake_run

    result = classifier.infer_image(np.zeros((8, 8, 3), dtype=np.uint8))

    assert result["class"] == "Tomato_healthy"
    assert result["ensemble"] is True
    assert result["top3"][0]["class"] if False else True
    assert result["top3"][0]["class"] == "Tomato_healthy"
    assert result["fallback"] is False


def test_efficientformer_get_explanation_returns_overlay_payload(monkeypatch):
    classifier = EfficientFormerClassifier.__new__(EfficientFormerClassifier)
    classifier._cfg = {"display_name": "EfficientFormerV2-S1", "explainability_method": "layercam"}
    classifier._model_key = "efficientformer"
    classifier._global_model_cfg = {"confidence_threshold": 0.65}
    classifier._torch_model = object()
    classifier._torch_target_layer = object()
    classifier._torch_target_layer_name = "network.6"
    classifier._explainability_error = None

    monkeypatch.setattr(
        classifier,
        "infer_image",
        lambda image, source=None: {
            "class": "Tomato_Late_blight",
            "class_index": 2,
            "confidence": 0.93,
        },
    )
    monkeypatch.setattr(classifier, "_compute_layercam", lambda image, class_index: np.ones((4, 4), dtype=np.float32))
    monkeypatch.setattr(classifier, "_overlay_heatmap", lambda image, heatmap: np.full((4, 4, 3), 120, dtype=np.uint8))
    monkeypatch.setattr(classifier, "_colorize_heatmap", lambda heatmap: np.full((4, 4, 3), 80, dtype=np.uint8))
    monkeypatch.setattr(classifier, "_encode_png", lambda image: b"png-bytes")

    payload = classifier.get_explanation(np.zeros((4, 4, 3), dtype=np.uint8))

    assert payload["class"] == "Tomato_Late_blight"
    assert payload["method"] == "layercam"
    assert payload["target_layer"] == "network.6"
    assert payload["image_bytes"] == b"png-bytes"
    assert payload["overlay"].shape == (4, 4, 3)


def test_overlay_heatmap_draws_focus_marker(monkeypatch):
    classifier = EfficientFormerClassifier.__new__(EfficientFormerClassifier)
    classifier._cfg = {"overlay_alpha": 0.0}

    monkeypatch.setattr(
        classifier,
        "_colorize_heatmap",
        lambda heatmap: np.zeros((32, 32, 3), dtype=np.uint8),
    )

    base = np.zeros((32, 32, 3), dtype=np.uint8)
    heatmap = np.zeros((32, 32), dtype=np.float32)
    heatmap[10:22, 8:20] = 1.0

    overlay = classifier._overlay_heatmap(base, heatmap)

    assert overlay.shape == (32, 32, 3)
    assert np.count_nonzero(overlay) > 0


def test_vision_service_normalizes_low_confidence_to_fallback():
    service = VisionService.__new__(VisionService)
    service._cfg = {"backend": "efficientformer", "quantization": "float16"}
    service.backend = types.SimpleNamespace(model_name="EfficientFormerV2-S1")

    normalized = VisionService._normalize_result(
        service,
        {
            "class": "Tomato_healthy",
            "confidence": 0.22,
            "top_k": [{"class": "Tomato_healthy", "confidence": 0.22}],
            "model": "EfficientFormerV2-S1",
        },
    )

    assert normalized["class"] == "Classe_NonClassificato"
    assert normalized["fallback"] is True
    assert normalized["raw_prediction"]["class"] == "Tomato_healthy"


def test_vision_service_selects_efficientformer_backend(monkeypatch):
    import vision.vision_service as vision_service

    class FakeEfficientFormer:
        def __init__(self, model_key, quantization=None, ensemble_enabled=None):
            self.model_key = model_key
            self.quantization = quantization
            self.ensemble_enabled = ensemble_enabled
            self.is_ready = True
            self.model_name = "fake-efficientformer"

        def infer(self, image_path):
            return {"class": "Apple_healthy", "confidence": 0.9, "top_k": []}

    monkeypatch.setitem(
        vision_service.MODELS_REGISTRY,
        "efficientformer_test",
        {
            "backend": "efficientformer",
            "quantization": "float16",
            "enable_ensemble": True,
        },
    )
    monkeypatch.setattr(vision_service, "EfficientFormerClassifier", FakeEfficientFormer)

    service = VisionService(model_key="efficientformer_test")

    assert isinstance(service.backend, FakeEfficientFormer)
    assert service.backend.quantization == "float16"
    assert service.backend.ensemble_enabled is True
