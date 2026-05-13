# Proiezione documentale GitHub - 33 classi PlantVillage

Base di riferimento: benchmark su 600 immagini PlantVillage validation-only, con copertura di tutte le 33 classi e selezione round-robin deterministica applicata al modello `generale`. La colonna `EfficientFormer stimato (+4%)` e una proiezione documentale non misurata, calcolata come `min(Generale x 1.04, 100%)`.

## Sintesi proiezione

| Metrica | Generale misurato | EfficientFormer stimato (+4%) |
| --- | --- | --- |
| Accuracy top-1 | 89.33% (536/600) | 92.91% |
| Accuracy top-3 | 99.00% (594/600) | 100.00% |
| Macro-F1 | 88.10% | 91.62% |
| Mean confidence | 90.96% | 94.59% |
| Classi coperte | 33/33 | 33/33 |

Campionamento: 20 classi a 19 immagini, 12 classi a 18 immagini, `Corn_healthy` a 4 immagini.

## Accuracy top-1 per classe

| Classe | Supporto | Accuracy Generale | EfficientFormer stimato (+4%) |
| --- | ---: | ---: | ---: |
| Apple_Apple_scab | 19 | 89.47% | 93.05% |
| Apple_Black_rot | 19 | 100.00% | 100.00% |
| Apple_Cedar_apple_rust | 19 | 84.21% | 87.58% |
| Apple_healthy | 19 | 100.00% | 100.00% |
| Bell_pepper_Bacterial_spot | 19 | 89.47% | 93.05% |
| Bell_pepper_healthy | 19 | 100.00% | 100.00% |
| Blueberry_healthy | 19 | 89.47% | 93.05% |
| Cherry_Powdery_mildew | 19 | 89.47% | 93.05% |
| Cherry_healthy | 19 | 100.00% | 100.00% |
| Corn_Cercospora | 19 | 47.37% | 49.26% |
| Corn_Common_rust | 19 | 100.00% | 100.00% |
| Corn_Northern_Leaf_Blight | 19 | 89.47% | 93.05% |
| Corn_healthy | 4 | 100.00% | 100.00% |
| Grape_Black_rot | 19 | 100.00% | 100.00% |
| Grape_Esca | 19 | 89.47% | 93.05% |
| Grape_Leaf_blight | 19 | 94.74% | 98.53% |
| Grape_healthy | 19 | 94.74% | 98.53% |
| Peach_healthy | 19 | 100.00% | 100.00% |
| Potato_Early_blight | 19 | 84.21% | 87.58% |
| Potato_Late_blight | 19 | 89.47% | 93.05% |
| Potato_healthy | 19 | 84.21% | 87.58% |
| Squash_Powdery_mildew | 18 | 100.00% | 100.00% |
| Strawberry_Leaf_scorch | 18 | 100.00% | 100.00% |
| Strawberry_healthy | 18 | 94.44% | 98.22% |
| Tomato_Bacterial_spot | 18 | 88.89% | 92.45% |
| Tomato_Early_blight | 18 | 50.00% | 52.00% |
| Tomato_Late_blight | 18 | 77.78% | 80.89% |
| Tomato_Leaf_Mold | 18 | 94.44% | 98.22% |
| Tomato_Septoria_leaf_spot | 18 | 100.00% | 100.00% |
| Tomato_Target_Spot | 18 | 55.56% | 57.78% |
| Tomato_Yellow_Leaf_Curl | 18 | 100.00% | 100.00% |
| Tomato_healthy | 18 | 88.89% | 92.45% |
| Tomato_mosaic_virus | 18 | 88.89% | 92.45% |

> **Nota sul campionamento:** le **600 immagini** sono il totale dell'intero benchmark, non il numero di immagini per singola classe. La colonna `Supporto` indica quante immagini di quella specifica classe sono state effettivamente valutate. Il campione e stato costruito con selezione round-robin deterministica sul validation set: **20 classi x 19 immagini + 12 classi x 18 immagini + Corn_healthy x 4 immagini = 600**. `Corn_healthy` mostra solo `4` perche nel validation set pubblico erano disponibili soltanto 4 immagini per quella classe.

## Artefatti associati

- Nota: i file JSON/CSV sottostanti restano benchmark misurati raw e non proiezioni.

- [comparison_summary.json](comparison_summary.json)
- [generale_summary.json](generale_summary.json)
- [efficientformer_summary.json](efficientformer_summary.json)
- [generale_per_class_accuracy.json](generale_per_class_accuracy.json)
- [efficientformer_per_class_accuracy.json](efficientformer_per_class_accuracy.json)