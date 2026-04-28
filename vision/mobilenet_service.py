# Servizio vision che usa VisionBackend
from .vision_backend import CpuMobileNetBackend

class MobileNetService:
    def __init__(self):
        self.backend = CpuMobileNetBackend()

    def classify(self, image_path):
        return self.backend.infer(image_path)
