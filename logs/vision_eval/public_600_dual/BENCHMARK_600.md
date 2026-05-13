# Benchmark GitHub pubblico - 33 classi PlantVillage (600 immagini indipendenti)

Benchmark su 600 immagini PlantVillage validation-only, con copertura di tutte le 33 classi e selezione round-robin deterministica applicata allo stesso campione per i modelli `generale` ed `efficientformer`.

## Sintesi benchmark

| Metrica | Generale | EfficientFormer |
| --- | --- | --- |
| Accuracy top-1 | 89.33% (536/600) | 31.50% (189/600) |
| Accuracy top-3 | 99.00% (594/600) | 91.83% (551/600) |
| Macro-F1 | 88.10% | 33.16% |
| Mean confidence | 90.96% | 52.78% |
| Classi coperte | 33/33 | 33/33 |

Campionamento: 20 classi a 19 immagini, 12 classi a 18 immagini, `Corn_healthy` a 4 immagini.

## Accuracy top-1 per classe

| Classe | Supporto | Accuracy Generale | Accuracy EfficientFormer |
| --- | ---: | ---: | ---: |
| Apple_Apple_scab | 19 | 89.47% | 0.00% |
| Apple_Black_rot | 19 | 100.00% | 0.00% |
| Apple_Cedar_apple_rust | 19 | 84.21% | 0.00% |
| Apple_healthy | 19 | 100.00% | 63.16% |
| Bell_pepper_Bacterial_spot | 19 | 89.47% | 21.05% |
| Bell_pepper_healthy | 19 | 100.00% | 5.26% |
| Blueberry_healthy | 19 | 89.47% | 78.95% |
| Cherry_Powdery_mildew | 19 | 89.47% | 0.00% |
| Cherry_healthy | 19 | 100.00% | 26.32% |
| Corn_Cercospora | 19 | 47.37% | 73.68% |
| Corn_Common_rust | 19 | 100.00% | 63.16% |
| Corn_Northern_Leaf_Blight | 19 | 89.47% | 52.63% |
| Corn_healthy | 4 | 100.00% | 100.00% |
| Grape_Black_rot | 19 | 100.00% | 100.00% |
| Grape_Esca | 19 | 89.47% | 100.00% |
| Grape_Leaf_blight | 19 | 94.74% | 10.53% |
| Grape_healthy | 19 | 94.74% | 5.26% |
| Peach_healthy | 19 | 100.00% | 89.47% |
| Potato_Early_blight | 19 | 84.21% | 26.32% |
| Potato_Late_blight | 19 | 89.47% | 5.26% |
| Potato_healthy | 19 | 84.21% | 73.68% |
| Squash_Powdery_mildew | 18 | 100.00% | 16.67% |
| Strawberry_Leaf_scorch | 18 | 100.00% | 44.44% |
| Strawberry_healthy | 18 | 94.44% | 0.00% |
| Tomato_Bacterial_spot | 18 | 88.89% | 0.00% |
| Tomato_Early_blight | 18 | 50.00% | 22.22% |
| Tomato_Late_blight | 18 | 77.78% | 16.67% |
| Tomato_Leaf_Mold | 18 | 94.44% | 5.56% |
| Tomato_Septoria_leaf_spot | 18 | 100.00% | 5.56% |
| Tomato_Target_Spot | 18 | 55.56% | 0.00% |
| Tomato_Yellow_Leaf_Curl | 18 | 100.00% | 11.11% |
| Tomato_healthy | 18 | 88.89% | 61.11% |
| Tomato_mosaic_virus | 18 | 88.89% | 5.56% |

## Artefatti associati

- [logs/vision_eval/public_600_dual/comparison_summary.json](logs/vision_eval/public_600_dual/comparison_summary.json)
- [logs/vision_eval/public_600_dual/generale_summary.json](logs/vision_eval/public_600_dual/generale_summary.json)
- [logs/vision_eval/public_600_dual/efficientformer_summary.json](logs/vision_eval/public_600_dual/efficientformer_summary.json)
- [logs/vision_eval/public_600_dual/generale_per_class_accuracy.json](logs/vision_eval/public_600_dual/generale_per_class_accuracy.json)
- [logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json](logs/vision_eval/public_600_dual/efficientformer_per_class_accuracy.json)