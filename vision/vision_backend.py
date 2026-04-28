# Interfaccia VisionBackend (CPU ora, Hailo in futuro)
from abc import ABC, abstractmethod

class VisionBackend(ABC):
    @abstractmethod
    def infer(self, image_path):
        pass

class CpuMobileNetBackend(VisionBackend):
    def __init__(self):
        # TODO: Inizializzazione MobileNet CPU
        pass

    def infer(self, image_path):
        # TODO: Chiamata MobileNet CPU
        return "[Risposta MobileNet CPU simulata]"

# Placeholder per futuro HailoBackend
class HailoBackend(VisionBackend):
    def infer(self, image_path):
        raise NotImplementedError("Hailo non ancora implementato")
