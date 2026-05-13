import sys
import types
from pathlib import Path

import core.agent as agent_mod


def test_resolve_explainability_service_uses_efficientformer_fallback(monkeypatch):
    class FakePrimaryService:
        can_explain = False
        is_ready = True
        active_model = "generale"

    class FakeFallbackService:
        def __init__(self, model_key=None, ensemble_enabled=None):
            self.model_key = model_key
            self.ensemble_enabled = ensemble_enabled
            self.is_ready = True
            self.can_explain = True
            self.active_model = "EfficientFormerV2-S1"

    monkeypatch.setitem(agent_mod.MODELS_REGISTRY, "efficientformer", {"backend": "efficientformer"})
    monkeypatch.setattr(agent_mod, "VisionService", FakeFallbackService)

    agent = agent_mod.DeltaAgent.__new__(agent_mod.DeltaAgent)
    agent.vision_service = FakePrimaryService()
    agent._explainability_service = None
    agent._explainability_service_attempted = False

    resolved = agent_mod.DeltaAgent._resolve_explainability_service(agent)

    assert isinstance(resolved, FakeFallbackService)
    assert resolved.model_key == "efficientformer"
    assert resolved.ensemble_enabled is False
    assert agent_mod.DeltaAgent._resolve_explainability_service(agent) is resolved


def test_build_explainability_artifact_tracks_classification_model(monkeypatch, tmp_path):
    class FakeExplainabilityService:
        active_model = "EfficientFormerV2-S1"

        def explain_image(self, image):
            return {
                "model": self.active_model,
                "method": "layercam",
                "summary": "lesione evidenziata",
                "class": "Tomato_Early_blight",
                "confidence": 0.91,
                "target_layer": "stages.3.blocks.5.drop_path2",
                "overlay": object(),
                "heatmap": object(),
            }

    class FakeCv2:
        @staticmethod
        def imwrite(path, image):
            Path(path).write_bytes(b"ok")
            return True

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    monkeypatch.setitem(agent_mod.VISION_CONFIG["explainability"], "output_dir", str(tmp_path))

    agent = agent_mod.DeltaAgent.__new__(agent_mod.DeltaAgent)
    agent.vision_service = types.SimpleNamespace(active_model="generale")
    agent._explainability_service = None
    agent._explainability_service_attempted = True

    artifact = agent_mod.DeltaAgent._build_explainability_artifact(
        agent,
        image=object(),
        timestamp="2026-05-13T14:30:00.000000",
        explainability_service=FakeExplainabilityService(),
    )

    assert artifact["available"] is True
    assert artifact["model"] == "EfficientFormerV2-S1"
    assert artifact["classification_model"] == "generale"
    assert Path(artifact["overlay_path"]).exists()
    assert Path(artifact["heatmap_path"]).exists()