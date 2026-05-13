# 🌿 DELTA Plant Disease Classifier - Model Card

## Model Overview

**Model Name:** DELTA Plant Leaf Disease Stack  
**Version:** 3.2 (Baseline MobileNetV2 + EfficientFormerV2-S1 edge backend)  
**Release Date:** 2026-05-13  
**License:** DELTA PLANT SOFTWARE LICENSE (core proprietario per ricerca non commerciale; componenti OSS ove indicato)  
**Citation:** DELTA Plant v3.2 | PlantVillage Dataset | MobileNetV2 baseline + EfficientFormerV2-S1 hybrid edge backend

---

## Model Details

### Architecture
- **Baseline Backbone:** MobileNetV2 (ImageNet pre-trained weights)
- **Hybrid Backend:** EfficientFormerV2-S1 (optional, PyTorch->ONNX->TFLite)
- **Input Shape:** 224×224×3 (RGB images)
- **Preprocessing:** MobileNetV2 standard — `(x / 127.5) - 1.0` → range [-1, 1]
- **Output:** 33-class softmax (disease classification)
- **Explainability:** LayerCAM overlay (JET/Viridis) via reference PyTorch checkpoint
- **Ensemble:** weighted probability averaging with MobileNetV2 baseline
- **Model Size Baseline:** 14 MB (Keras) / 5.0 MB (TFLite float16)

### Deployment Profiles
- **Profile A - Production Baseline:** MobileNetV2 TFLite float16, benchmark reale pubblicato e stabile
- **Profile B - Advanced Hybrid Edge:** EfficientFormerV2-S1 TFLite int8 di default, fallback float32, ensemble + explainability, attivabile via `MODELS_REGISTRY['efficientformer']`

### Training Configuration
```
Optimizer: Adam (lr=0.001)
Loss: Categorical Crossentropy
Batch Size: 32
Epochs: 10 (with early stopping, patience=10)
Validation Split: 20%
Augmentation: Rotation, shift, zoom, horizontal flip
```

---

## Performance Metrics

### Benchmark Reale Pubblicato — MobileNetV2 Baseline (2026-05-03)
| Metrica | Valore |
|--------|-------|
| **Accuratezza top-1** | **83.9%** (554/660 immagini) |
| **Accuratezza top-3** | **96.1%** (634/660 immagini) |
| **Classi ≥95% top-1** | 17/33 |
| **Classi problematiche (<50%)** | 2/33 (Tomato_Bacterial_spot 15%, Tomato_Early_blight 40%) |
| **Bassa confidenza (<50%)** | 7.6% delle predizioni |
| **Velocità inferenza (TFLite RPi5)** | ~180ms (XNNPACK delegate) |
| **Dataset benchmark** | 660 img PlantVillage (20/classe) |

### EfficientFormerV2-S1 - Risultati Pipeline X (2026-05-13)
- **Repository support:** completo lato software, export, benchmark harness, evaluation pipeline e rigenerazione manuale via Pipeline X
- **Quantizzazione target:** int8 fully quantized di default, float32 fallback runtime, float16 disponibile come variante legacy
- **Runtime validation:** allocazione interpreter e inferenza locale confermate sul dispositivo target
- **Dataset di evaluation:** 7,502 campioni PlantVillage (`datasets/training_33classes/validation`)

| Metrica | Generale | EfficientFormer |
| --- | --- | --- |
| Accuracy top-1 | 91.70% | 29.42% |
| Accuracy top-3 | 99.23% | 90.19% |
| Macro-F1 | 88.97% | 31.68% |
| Mean confidence | 91.71% | 51.71% |
| Avg latency | 41.360 ms | 308.918 ms |
| P95 latency | 54.318 ms | 582.547 ms |
| Max latency | 66.085 ms | 706.852 ms |
| Throughput | 24.178 fps | 3.237 fps |

> I risultati pubblicati dalla Pipeline X confermano che il backend `generale` resta il profilo di riferimento per accuratezza e latenza sul Raspberry Pi 5 target. EfficientFormerV2-S1 rimane disponibile come backend edge avanzato per explainability, ensemble e sperimentazione controllata, ma non viene promosso come default su questa release.

### Bell Pepper Classification (Priority Class)
- **Samples:** 7,425 images (7.8% of training set)
- **Classes:** Bacterial_spot (2,991) + healthy (4,434)
- **Benchmark Precision:** 100% (Bacterial_spot) / 95% (healthy)

---

## Dataset

### PlantVillage Dataset
- **Total Images:** 119,173 high-resolution JPEGs (95% quality)
- **Training Split:** 94,484 images (80%)
- **Validation Split:** 23,609 images (20%)
- **Available Classes:** 38/39 (all major crops covered)

### Class Distribution
```
Tomato (9 classes)      | Potato (3 classes)
Grape (4 classes)       | Corn (4 classes)
Apple (4 classes)       | Strawberry (2 classes)
Bell Pepper (2 classes) | Cherry (2 classes)
Squash (1 class)        | Blueberry (1 class)
Peach (1 class)
```
**Totale: 33 classi** (Wheat escluso — non presente nel modello)

### Data Preprocessing
- Rescaling MobileNetV2: `(x / 127.5) - 1.0` (range [-1, 1])
- Rotation: ±20°
- Width/Height Shift: ±20%
- Zoom: ±20%
- Horizontal Flip: Enabled

---

## Hardware Requirements

### Minimum (Inference)
- **CPU:** ARM Cortex-A76 (4+ cores @ 2.4GHz)
- **RAM:** 4GB (for real-time inference)
- **Storage:** 3GB (model + dependencies)
- **Platform:** Raspberry Pi 5 (tested ✓)

### Recommended (Training)
- **CPU:** 8+ cores @ 2.5GHz+
- **RAM:** 16GB
- **Storage:** 1TB SSD
- **Time:** ~24 hours for 10 epochs on RPi5 4-core

---

## Inference Guide

### Python (Keras Model)
```python
import tensorflow as tf
import numpy as np

model = tf.keras.models.load_model("models/plant_disease_model_39classes.keras")
image = tf.keras.preprocessing.image.load_img("plant.jpg", target_size=(224, 224))
image_array = tf.keras.preprocessing.image.img_to_array(image) / 255.0
predictions = model.predict(np.expand_dims(image_array, axis=0))
class_idx = np.argmax(predictions[0])
confidence = predictions[0][class_idx]
```

### TensorFlow Lite (Optimized for Edge)
```python
import numpy as np
from ai_edge_litert.interpreter import Interpreter

interpreter = Interpreter("models/plant_disease_model_39classes.tflite")
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# Preprocessing MobileNetV2: float32, range [-1, 1]
image = load_image_224x224()  # numpy uint8 HWC
input_image = (image.astype(np.float32) / 127.5) - 1.0
input_image = np.expand_dims(input_image, axis=0)

# Inference
interpreter.set_tensor(input_details[0]['index'], input_image)
interpreter.invoke()
output = interpreter.get_tensor(output_details[0]['index'])  # shape [1, 33]
```

### EfficientFormerV2-S1 via VisionService
```python
from vision.vision_service import VisionService

service = VisionService("efficientformer")
result = service.classify("input_images/sample_leaf.jpg")
explanation = service.explain("input_images/sample_leaf.jpg")

print(result["class"], result["confidence"])
print(explanation.get("target_layer"), explanation.get("summary"))
```

---

## Limitations & Known Issues

1. **Dataset Bias:** PlantVillage images are controlled conditions (limited outdoor variability)
2. **Resolution:** Optimized for 224×224 images (may reduce accuracy on higher resolutions)
3. **Crop Coverage:** 33 classes (Wheat and other PlantVillage classes not included in this model)
4. **Thermal Constraints:** RPi5 thermal throttling may reduce inference speed in hot environments
5. **Lighting Conditions:** Model trained on varied lighting but may struggle with extreme conditions
6. **Inter-class confusion:** Tomato spot diseases (Bacterial_spot, Early_blight, Septoria, Target_Spot) are morphologically similar — top-3 accuracy (96.1%) recommended for clinical use
7. **Explainability dependency:** LayerCAM richiede il checkpoint PyTorch fine-tuned oltre al file TFLite di inferenza
8. **Hybrid backend tradeoff:** EfficientFormerV2-S1 e validato in runtime ed evaluation, ma nella release 3.2 mostra accuracy top-1 e latenza significativamente peggiori rispetto al backend `generale`; usare quindi solo quando servono explainability, export o sperimentazione comparativa

---

## Ethical Considerations

- **Use Case:** Research, agricultural assistance, educational purposes
- **Not for:** Autonomous medical diagnosis, critical decision-making without expert review
- **Fairness:** Dataset covers major agricultural crops; limited representation of rare diseases
- **Transparency:** Model predictions are probabilistic; confidence scores should be considered

---

## Reproduction & Citation

### Environment
```bash
Python 3.12
TensorFlow 2.21.0
PyYAML 6.x
Hardware: Raspberry Pi 5 (4-core, 16GB RAM)
Dataset: PlantVillage v2.0 (spMohanty/PlantVillage-Dataset)
```

### EfficientFormer export / evaluation
```bash
pip install -r requirements-efficientformer.txt

python ai/export_efficientformer_tflite.py \
  --dataset-root datasets/training \
  --output-dir models \
  --mode all --quantization both

python tools/benchmark_vision_models.py \
  --model-keys generale efficientformer \
  --image models/validation_sample.jpg

python ai/evaluate_vision_backends.py \
  --dataset-root datasets/training/validation \
  --model-keys generale efficientformer
```

### Citation
```bibtex
@software{delta2026,
  title={DELTA Plant: AI-Powered Plant Disease Classification System},
  author={Ciccolella, Paolo},
  year={2026},
  url={https://github.com/Proctor81/DELTA-PLANT},
  dataset={PlantVillage Dataset (spMohanty/PlantVillage-Dataset)},
  license={Proprietary (Scientific Research Use)},
  note={33-class MobileNetV2 TFLite float16 baseline; optional EfficientFormerV2-S1 hybrid backend with LayerCAM and ensemble support in repository}
}
```

---

## Contact & Support

- **Repository:** [https://github.com/Proctor81/DELTA-PLANT](https://github.com/Proctor81/DELTA-PLANT)
- **Dataset Source:** [PlantVillage GitHub](https://github.com/spMohanty/PlantVillage-Dataset)
- **License:** Proprietary (Scientific Research Use — see LICENSE)
- **Last Updated:** 2026-05-13 (EfficientFormer int8 executable backend, Pipeline X, manuale e release 3.2)

---

**Status:** ✅ MobileNet baseline production ready | ✅ EfficientFormer int8 runtime validated | 🚀 Edge deployment and documentation pipeline aligned
