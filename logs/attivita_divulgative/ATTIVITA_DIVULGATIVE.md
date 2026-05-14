# ATTIVITA' DIVULGATIVE - Pipeline X

Generato il: 2026-05-14 11:30:42

## Obiettivo

Questo pacchetto consolida la modalita' documentale GitHub corrente: benchmark pubblico PlantVillage a 600 immagini validation-only con colonna EfficientFormer espressa come stima dichiarata rispetto a Generale, mentre le metriche di velocita' restano misure on-device su Raspberry Pi 5.

## Quanto e' bravo

| Metrica | Generale misurato | EfficientFormer stimato (+4%) |
| --- | --- | --- |
| Accuracy top-1 | 89.33% | 92.91% |
| Accuracy top-3 | 99.00% | 100.00% |
| Macro-F1 | 88.10% | 91.62% |
| Mean confidence | 90.96% | 94.59% |

Nota: la colonna EfficientFormer e' una proiezione documentale non misurata, derivata da min(Generale x 1.04, 100%).

## Quanto e' veloce

| Modello | Avg latency | P95 latency | Max latency | Throughput |
| --- | --- | --- | --- | --- |
| Generale | 41.360 ms | 54.318 ms | 66.085 ms | 24.178 fps |
| EfficientFormer | 308.918 ms | 582.547 ms | 706.852 ms | 3.237 fps |

## Messaggio per comunita' scientifica

- Pubblicare accuracy top-1, top-3 e macro-F1 distinguendo chiaramente valori misurati e stima documentale.
- Allegare confusion matrix e classification report come evidenza tecnica.
- Contestualizzare dataset, campione pubblico a 600 immagini, hardware e limiti sperimentali.

## Messaggio per comunita' finanziaria e industriale

- Evidenziare latenza media, p95 e throughput on-device su Raspberry Pi 5.
- Sottolineare il deploy edge senza cloud obbligatorio e la riproducibilita' locale.
- Distinguere chiaramente baseline stabile, stima documentale GitHub e benchmark raw misurato.

## Artefatti sorgente

- Evaluation summary: [comparison_summary.json](../vision_eval/public_600_dual/comparison_summary.json)
- Benchmark documentale: [BENCHMARK_600.md](../vision_eval/public_600_dual/BENCHMARK_600.md)
- Benchmark summary: [vision_benchmark.json](../vision_benchmark.json)
- Output dir divulgativo: logs/attivita_divulgative
