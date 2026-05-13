# ATTIVITA' DIVULGATIVE - Pipeline X

Generato il: 2026-05-13 17:13:06

## Obiettivo

Questo pacchetto consolida i risultati di 'quanto e' bravo' e 'quanto e' veloce' per preparare la pubblicazione tecnica e divulgativa su GitHub.

## Quanto e' bravo

| Modello | Accuracy top-1 | Accuracy top-3 | Macro-F1 | Confidenza media |
| --- | --- | --- | --- | --- |
| Generale | 91.70% | 99.23% | 88.97% | 91.71% |
| EfficientFormer | 29.42% | 90.19% | 31.68% | 51.71% |

## Quanto e' veloce

| Modello | Avg latency | P95 latency | Max latency | Throughput |
| --- | --- | --- | --- | --- |
| Generale | 41.360 ms | 54.318 ms | 66.085 ms | 24.178 fps |
| EfficientFormer | 308.918 ms | 582.547 ms | 706.852 ms | 3.237 fps |

## Messaggio per comunita' scientifica

- Pubblicare accuracy top-1, top-3 e macro-F1 con link ai report completi.
- Allegare confusion matrix e classification report come evidenza tecnica.
- Contestualizzare dataset, hardware e limiti sperimentali.

## Messaggio per comunita' finanziaria e industriale

- Evidenziare latenza media, p95 e throughput on-device su Raspberry Pi 5.
- Sottolineare il deploy edge senza cloud obbligatorio e la riproducibilita' locale.
- Distinguere chiaramente baseline stabile e backend EfficientFormer validato.

## Artefatti sorgente

- Evaluation summary: logs/vision_eval/comparison_summary.json
- Benchmark summary: logs/vision_benchmark.json
- Output dir divulgativo: logs/attivita_divulgative
