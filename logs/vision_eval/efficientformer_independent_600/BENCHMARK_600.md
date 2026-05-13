# EfficientFormerV2-S1 - Accuracy Benchmark GitHub (600 immagini indipendenti)

EfficientFormerV2-S1 e la stack vision preminente della release DELTA Plant v3.2 per benchmark pubblico, export, explainability e pipeline edge.

## Sintesi benchmark

| Metrica | Valore |
| --- | --- |
| Accuracy top-1 | 31.50% (189/600) |
| Accuracy top-3 | 91.83% (551/600) |
| Macro-F1 | 33.16% |
| Mean confidence | 52.78% |
| Classi coperte | 33/33 |

Campionamento: validation-only PlantVillage (`datasets/training_33classes/validation`), selezione round-robin deterministica, 20 classi a 19 immagini, 12 classi a 18 immagini, `Corn_healthy` a 4 immagini.

## Accuracy top-1 per classe

| Classe | Supporto | Corrette | Accuracy top-1 |
| --- | ---: | ---: | ---: |
| Apple_Apple_scab | 19 | 0 | 0.00% |
| Apple_Black_rot | 19 | 0 | 0.00% |
| Apple_Cedar_apple_rust | 19 | 0 | 0.00% |
| Apple_healthy | 19 | 12 | 63.16% |
| Bell_pepper_Bacterial_spot | 19 | 4 | 21.05% |
| Bell_pepper_healthy | 19 | 1 | 5.26% |
| Blueberry_healthy | 19 | 15 | 78.95% |
| Cherry_Powdery_mildew | 19 | 0 | 0.00% |
| Cherry_healthy | 19 | 5 | 26.32% |
| Corn_Cercospora | 19 | 14 | 73.68% |
| Corn_Common_rust | 19 | 12 | 63.16% |
| Corn_Northern_Leaf_Blight | 19 | 10 | 52.63% |
| Corn_healthy | 4 | 4 | 100.00% |
| Grape_Black_rot | 19 | 19 | 100.00% |
| Grape_Esca | 19 | 19 | 100.00% |
| Grape_Leaf_blight | 19 | 2 | 10.53% |
| Grape_healthy | 19 | 1 | 5.26% |
| Peach_healthy | 19 | 17 | 89.47% |
| Potato_Early_blight | 19 | 5 | 26.32% |
| Potato_Late_blight | 19 | 1 | 5.26% |
| Potato_healthy | 19 | 14 | 73.68% |
| Squash_Powdery_mildew | 18 | 3 | 16.67% |
| Strawberry_Leaf_scorch | 18 | 8 | 44.44% |
| Strawberry_healthy | 18 | 0 | 0.00% |
| Tomato_Bacterial_spot | 18 | 0 | 0.00% |
| Tomato_Early_blight | 18 | 4 | 22.22% |
| Tomato_Late_blight | 18 | 3 | 16.67% |
| Tomato_Leaf_Mold | 18 | 1 | 5.56% |
| Tomato_Septoria_leaf_spot | 18 | 1 | 5.56% |
| Tomato_Target_Spot | 18 | 0 | 0.00% |
| Tomato_Yellow_Leaf_Curl | 18 | 2 | 11.11% |
| Tomato_healthy | 18 | 11 | 61.11% |
| Tomato_mosaic_virus | 18 | 1 | 5.56% |

## Artefatti associati

- [logs/vision_eval/efficientformer_independent_600/efficientformer_summary.json](logs/vision_eval/efficientformer_independent_600/efficientformer_summary.json)
- [logs/vision_eval/efficientformer_independent_600/efficientformer_per_class_accuracy.json](logs/vision_eval/efficientformer_independent_600/efficientformer_per_class_accuracy.json)
- [logs/vision_eval/efficientformer_independent_600/efficientformer_per_class_accuracy.csv](logs/vision_eval/efficientformer_independent_600/efficientformer_per_class_accuracy.csv)
- [logs/vision_eval/efficientformer_independent_600/comparison_summary.json](logs/vision_eval/efficientformer_independent_600/comparison_summary.json)