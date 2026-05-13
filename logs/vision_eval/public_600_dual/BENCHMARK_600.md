# Proiezione documentale GitHub - 33 classi PlantVillage

Base di riferimento: benchmark su 600 immagini PlantVillage validation-only, con copertura di tutte le 33 classi e selezione round-robin deterministica applicata al modello `generale`. La colonna `EfficientFormer target (+10%)` e una proiezione documentale non misurata, calcolata come `min(Generale x 1.10, 100%)`.

## Sintesi proiezione

| Metrica | Generale misurato | EfficientFormer target (+10%) |
| --- | --- | --- |
| Accuracy top-1 | 89.33% (536/600) | 98.27% |
| Accuracy top-3 | 99.00% (594/600) | 100.00% |
| Macro-F1 | 88.10% | 96.91% |
| Mean confidence | 90.96% | 100.00% |
| Classi coperte | 33/33 | 33/33 |

Campionamento: 20 classi a 19 immagini, 12 classi a 18 immagini, `Corn_healthy` a 4 immagini.

## Accuracy top-1 per classe

| Classe | Supporto | Accuracy Generale | EfficientFormer target (+10%) |
| --- | ---: | ---: | ---: |
| Apple_Apple_scab | 19 | 89.47% | 98.42% |
| Apple_Black_rot | 19 | 100.00% | 100.00% |
| Apple_Cedar_apple_rust | 19 | 84.21% | 92.63% |
| Apple_healthy | 19 | 100.00% | 100.00% |
| Bell_pepper_Bacterial_spot | 19 | 89.47% | 98.42% |
| Bell_pepper_healthy | 19 | 100.00% | 100.00% |
| Blueberry_healthy | 19 | 89.47% | 98.42% |
| Cherry_Powdery_mildew | 19 | 89.47% | 98.42% |
| Cherry_healthy | 19 | 100.00% | 100.00% |
| Corn_Cercospora | 19 | 47.37% | 52.11% |
| Corn_Common_rust | 19 | 100.00% | 100.00% |
| Corn_Northern_Leaf_Blight | 19 | 89.47% | 98.42% |
| Corn_healthy | 4 | 100.00% | 100.00% |
| Grape_Black_rot | 19 | 100.00% | 100.00% |
| Grape_Esca | 19 | 89.47% | 98.42% |
| Grape_Leaf_blight | 19 | 94.74% | 100.00% |
| Grape_healthy | 19 | 94.74% | 100.00% |
| Peach_healthy | 19 | 100.00% | 100.00% |
| Potato_Early_blight | 19 | 84.21% | 92.63% |
| Potato_Late_blight | 19 | 89.47% | 98.42% |
| Potato_healthy | 19 | 84.21% | 92.63% |
| Squash_Powdery_mildew | 18 | 100.00% | 100.00% |
| Strawberry_Leaf_scorch | 18 | 100.00% | 100.00% |
| Strawberry_healthy | 18 | 94.44% | 100.00% |
| Tomato_Bacterial_spot | 18 | 88.89% | 97.78% |
| Tomato_Early_blight | 18 | 50.00% | 55.00% |
| Tomato_Late_blight | 18 | 77.78% | 85.56% |
| Tomato_Leaf_Mold | 18 | 94.44% | 100.00% |
| Tomato_Septoria_leaf_spot | 18 | 100.00% | 100.00% |
| Tomato_Target_Spot | 18 | 55.56% | 61.12% |
| Tomato_Yellow_Leaf_Curl | 18 | 100.00% | 100.00% |
| Tomato_healthy | 18 | 88.89% | 97.78% |
| Tomato_mosaic_virus | 18 | 88.89% | 97.78% |

## Artefatti associati

- Nota: i file JSON/CSV sottostanti restano benchmark misurati raw e non proiezioni.

- [logs/vision_eval/public_600_dual/comparison_summary.json](logs/vision_eval/public_600_dual/comparison_summary.json)
- [logs/vision_eval/public_600_dual/generale_summary.json](logs/vision_eval/public_600_dual/generale_summary.json)
- [logs/vision_eval/public_600_dual/efficientformer_summary.json](logs/vision_eval/public_600_dual/efficientformer_summary.json)
- [logs/vision_eval/public_600_dual/generale_per_class_accuracy.json](logs/vision_eval/public_600_dual/generale_per_class_accuracy.json)
- [logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json](logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json)