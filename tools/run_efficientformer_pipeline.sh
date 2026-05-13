#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PIPELINE_DIR="logs/pipeline/efficientformer_${TIMESTAMP}"
mkdir -p "$PIPELINE_DIR"

LOG_FILE="$PIPELINE_DIR/pipeline.log"
SUMMARY_FILE="$PIPELINE_DIR/summary.json"
EVAL_DIR="$PIPELINE_DIR/vision_eval"
BENCHMARK_FILE="$PIPELINE_DIR/vision_benchmark.json"

DATASET_ROOT="datasets/training_33classes"
VALIDATION_ROOT="$DATASET_ROOT/validation"
OUTPUT_DIR="models"

mapfile -t benchmark_candidates < <(
  find "$VALIDATION_ROOT" -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) | sort
)
benchmark_image="${benchmark_candidates[0]:-}"
if [[ -z "$benchmark_image" ]]; then
  echo "Nessuna immagine trovata per il benchmark in $VALIDATION_ROOT" | tee -a "$LOG_FILE"
  exit 1
fi

log_step() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG_FILE"
}

run_step() {
  log_step "$1"
  shift
  "$@" 2>&1 | tee -a "$LOG_FILE"
}

log_step "Avvio pipeline EfficientFormer 33 classi"
printf '{\n' > "$SUMMARY_FILE"
printf '  "timestamp": "%s",\n' "$TIMESTAMP" >> "$SUMMARY_FILE"
printf '  "dataset_root": "%s",\n' "$DATASET_ROOT" >> "$SUMMARY_FILE"
printf '  "validation_root": "%s",\n' "$VALIDATION_ROOT" >> "$SUMMARY_FILE"
printf '  "benchmark_image": "%s",\n' "$benchmark_image" >> "$SUMMARY_FILE"
printf '  "log_file": "%s",\n' "$LOG_FILE" >> "$SUMMARY_FILE"

run_step \
  "Training + export EfficientFormerV2-S1 -> ONNX/TFLite" \
  ./.venv/bin/python ai/export_efficientformer_tflite.py \
    --dataset-root "$DATASET_ROOT" \
    --output-dir "$OUTPUT_DIR" \
    --num-classes 33 \
    --mode all \
    --quantization both \
    --representative-data "$DATASET_ROOT" \
    --log-level INFO

run_step \
  "Valutazione backend generale vs efficientformer" \
  ./.venv/bin/python ai/evaluate_vision_backends.py \
    --dataset-root "$VALIDATION_ROOT" \
    --model-keys generale efficientformer \
    --output-dir "$EVAL_DIR" \
    --log-level INFO

run_step \
  "Benchmark edge backend generale vs efficientformer" \
  ./.venv/bin/python tools/benchmark_vision_models.py \
    --model-keys generale efficientformer \
    --image "$benchmark_image" \
    --runs 50 \
    --warmup 5 \
    --output "$BENCHMARK_FILE" \
    --log-level INFO

printf '  "checkpoint": "%s",\n' "$OUTPUT_DIR/efficientformer_v2_s1_33classes.pth" >> "$SUMMARY_FILE"
printf '  "float16_tflite": "%s",\n' "$OUTPUT_DIR/efficientformer_v2_s1_33classes_float16.tflite" >> "$SUMMARY_FILE"
printf '  "int8_tflite": "%s",\n' "$OUTPUT_DIR/efficientformer_v2_s1_33classes_int8.tflite" >> "$SUMMARY_FILE"
printf '  "labels": "%s",\n' "$OUTPUT_DIR/labels_33classes_correct.txt" >> "$SUMMARY_FILE"
printf '  "evaluation_dir": "%s",\n' "$EVAL_DIR" >> "$SUMMARY_FILE"
printf '  "benchmark_file": "%s"\n' "$BENCHMARK_FILE" >> "$SUMMARY_FILE"
printf '}\n' >> "$SUMMARY_FILE"

log_step "Pipeline completata con successo"
echo "Summary: $SUMMARY_FILE" | tee -a "$LOG_FILE"