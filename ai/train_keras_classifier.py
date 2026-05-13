"""
Training classificatore immagini piante con TensorFlow/Keras.

Struttura dataset attesa:
    datasets/training/
        ClasseA/
            img1.jpg
            img2.jpg
        ClasseB/
            ...

Output:
    - models/plant_disease_model.keras
    - models/labels.txt
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path


LOGGER = logging.getLogger("delta.ai.train")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Training Keras per classificazione malattie piante")
    parser.add_argument("--dataset", default="datasets/training", help="Directory dataset (classi per cartella)")
    parser.add_argument("--output", default="models", help="Directory output modello")
    parser.add_argument("--model-name", default="plant_disease_model.keras", help="Nome file modello Keras")
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Directory checkpoint/resume (default: <output>/.train_state)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Riprende dal checkpoint più recente se il training era stato interrotto",
    )
    parser.add_argument("--img-size", type=int, default=224, help="Dimensione immagini quadrate")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size")
    parser.add_argument("--epochs", type=int, default=12, help="Numero epoche")
    parser.add_argument("--validation-split", type=float, default=0.2, help="Frazione validation set")
    parser.add_argument("--seed", type=int, default=42, help="Seed random")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="Learning rate ottimizzatore")
    parser.add_argument("--fine-tune-layers", type=int, default=30, help="Numero layer finali da sbloccare")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def ensure_dataset(dataset_dir: Path):
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise RuntimeError(f"Dataset non trovato: {dataset_dir}")

    class_dirs = [d for d in dataset_dir.iterdir() if d.is_dir()]
    if len(class_dirs) < 2:
        raise RuntimeError(
            "Dataset insufficiente: servono almeno 2 classi (cartelle) con immagini."
        )


def build_model(tf, img_size: int, n_classes: int, learning_rate: float):
    data_augmentation = tf.keras.Sequential(
        [
            tf.keras.layers.RandomFlip("horizontal"),
            tf.keras.layers.RandomRotation(0.05),
            tf.keras.layers.RandomZoom(0.10),
            tf.keras.layers.RandomContrast(0.10),
        ],
        name="augmentation",
    )

    base_model = tf.keras.applications.MobileNetV2(
        input_shape=(img_size, img_size, 3),
        include_top=False,
        weights="imagenet",
    )
    base_model.trainable = False

    inputs = tf.keras.Input(shape=(img_size, img_size, 3), name="image")
    x = data_augmentation(inputs)
    x = tf.keras.applications.mobilenet_v2.preprocess_input(x)
    x = base_model(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.25)(x)
    outputs = tf.keras.layers.Dense(n_classes, activation="softmax", name="disease_probs")(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs, name="delta_plant_classifier")
    compile_model(tf, model, learning_rate)
    return model


def compile_model(tf, model, learning_rate: float) -> None:
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"],
    )


def find_backbone(model, tf):
    for layer in model.layers:
        if isinstance(layer, tf.keras.Model) and "mobilenetv2" in layer.name.lower():
            return layer
    raise RuntimeError("Backbone MobileNetV2 non trovato nel modello")


def enable_fine_tuning(tf, model, fine_tune_layers: int, learning_rate: float) -> None:
    backbone = find_backbone(model, tf)
    backbone.trainable = True
    if fine_tune_layers > 0:
        for layer in backbone.layers[:-fine_tune_layers]:
            layer.trainable = False
    compile_model(tf, model, learning_rate)


def load_resume_state(
    state_path: Path,
    dataset_dir: Path,
    class_names: list[str],
    total_epochs: int,
):
    if not state_path.exists() or not state_path.is_file():
        return None

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("State file resume corrotto: %s", state_path)
        return None

    if state.get("dataset") != str(dataset_dir):
        LOGGER.warning("Resume ignorato: dataset differente rispetto allo state file")
        return None

    if state.get("class_names") != class_names:
        LOGGER.warning("Resume ignorato: class_names differenti rispetto allo state file")
        return None

    if int(state.get("total_epochs", 0)) != total_epochs:
        LOGGER.warning("Resume ignorato: numero epoche differente rispetto allo state file")
        return None

    return state


def write_resume_state(
    state_path: Path,
    *,
    phase: str,
    completed_epochs: int,
    phase1_epochs: int,
    total_epochs: int,
    checkpoint_path: Path,
    dataset_dir: Path,
    class_names: list[str],
) -> None:
    state = {
        "phase": phase,
        "completed_epochs": completed_epochs,
        "phase1_epochs": phase1_epochs,
        "total_epochs": total_epochs,
        "checkpoint_path": str(checkpoint_path),
        "dataset": str(dataset_dir),
        "class_names": class_names,
    }
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    dataset_dir = Path(args.dataset).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / args.model_name
    labels_path = output_dir / "labels.txt"
    metadata_path = output_dir / "training_metadata.json"
    checkpoint_dir = (
        Path(args.checkpoint_dir).resolve()
        if args.checkpoint_dir
        else (output_dir / ".train_state").resolve()
    )
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    state_path = checkpoint_dir / "training_state.json"
    phase1_checkpoint = checkpoint_dir / "phase1_last.keras"
    phase2_checkpoint = checkpoint_dir / "phase2_last.keras"
    phase1_epochs = max(1, args.epochs // 2)

    ensure_dataset(dataset_dir)

    try:
        import tensorflow as tf  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "TensorFlow non installato. Installare con: pip install tensorflow"
        ) from exc

    LOGGER.info("Dataset: %s", dataset_dir)
    LOGGER.info("Output modello: %s", model_path)

    train_ds = tf.keras.utils.image_dataset_from_directory(
        dataset_dir,
        labels="inferred",
        label_mode="int",
        image_size=(args.img_size, args.img_size),
        batch_size=args.batch_size,
        validation_split=args.validation_split,
        subset="training",
        seed=args.seed,
    )

    val_ds = tf.keras.utils.image_dataset_from_directory(
        dataset_dir,
        labels="inferred",
        label_mode="int",
        image_size=(args.img_size, args.img_size),
        batch_size=args.batch_size,
        validation_split=args.validation_split,
        subset="validation",
        seed=args.seed,
    )

    class_names = list(train_ds.class_names)
    n_classes = len(class_names)
    LOGGER.info("Classi rilevate (%d): %s", n_classes, class_names)

    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.cache().shuffle(1000).prefetch(buffer_size=autotune)
    val_ds = val_ds.cache().prefetch(buffer_size=autotune)

    resume_state = None
    if args.resume:
        resume_state = load_resume_state(state_path, dataset_dir, class_names, args.epochs)

    def make_phase_callbacks(phase_name: str, checkpoint_path: Path):
        def on_epoch_end(epoch: int, logs=None):
            write_resume_state(
                state_path,
                phase=phase_name,
                completed_epochs=epoch + 1,
                phase1_epochs=phase1_epochs,
                total_epochs=args.epochs,
                checkpoint_path=checkpoint_path,
                dataset_dir=dataset_dir,
                class_names=class_names,
            )

        return [
            tf.keras.callbacks.ModelCheckpoint(
                filepath=str(checkpoint_path),
                save_best_only=False,
            ),
            tf.keras.callbacks.LambdaCallback(on_epoch_end=on_epoch_end),
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=4,
                restore_best_weights=True,
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss",
                factor=0.5,
                patience=2,
            ),
        ]

    model = None
    completed_epochs = 0
    resume_phase = None
    checkpoint_to_load = None

    if resume_state is not None:
        completed_epochs = int(resume_state.get("completed_epochs", 0))
        resume_phase = str(resume_state.get("phase", "phase1"))
        checkpoint_to_load_raw = resume_state.get("checkpoint_path")
        if checkpoint_to_load_raw:
            checkpoint_to_load = Path(str(checkpoint_to_load_raw)).resolve()
        if checkpoint_to_load is None or not checkpoint_to_load.exists():
            LOGGER.warning("Checkpoint resume non trovato, ripartenza da zero")
            completed_epochs = 0
            resume_phase = None
            checkpoint_to_load = None
            resume_state = None

    if checkpoint_to_load is not None:
        LOGGER.info(
            "Resume training da %s (epoca %d/%d)",
            checkpoint_to_load,
            completed_epochs,
            args.epochs,
        )
        model = tf.keras.models.load_model(checkpoint_to_load)
        if completed_epochs >= phase1_epochs:
            enable_fine_tuning(tf, model, args.fine_tune_layers, args.learning_rate * 0.1)
    else:
        model = build_model(tf, args.img_size, n_classes, args.learning_rate)

    if completed_epochs < phase1_epochs:
        LOGGER.info("Fase 1/2: addestramento testa classificatore")
        write_resume_state(
            state_path,
            phase="phase1",
            completed_epochs=completed_epochs,
            phase1_epochs=phase1_epochs,
            total_epochs=args.epochs,
            checkpoint_path=phase1_checkpoint,
            dataset_dir=dataset_dir,
            class_names=class_names,
        )
        model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=phase1_epochs,
            initial_epoch=completed_epochs,
            callbacks=make_phase_callbacks("phase1", phase1_checkpoint),
        )
        completed_epochs = phase1_epochs
        write_resume_state(
            state_path,
            phase="phase1_complete",
            completed_epochs=completed_epochs,
            phase1_epochs=phase1_epochs,
            total_epochs=args.epochs,
            checkpoint_path=phase1_checkpoint,
            dataset_dir=dataset_dir,
            class_names=class_names,
        )

    if args.fine_tune_layers > 0 and args.epochs > phase1_epochs:
        phase2_initial_epoch = completed_epochs
        if resume_phase not in {"phase2", "phase2_complete"} or checkpoint_to_load is None:
            enable_fine_tuning(tf, model, args.fine_tune_layers, args.learning_rate * 0.1)

        if phase2_initial_epoch < args.epochs:
            LOGGER.info("Fase 2/2: fine-tuning ultimi %d layer", args.fine_tune_layers)
            write_resume_state(
                state_path,
                phase="phase2",
                completed_epochs=phase2_initial_epoch,
                phase1_epochs=phase1_epochs,
                total_epochs=args.epochs,
                checkpoint_path=phase2_checkpoint,
                dataset_dir=dataset_dir,
                class_names=class_names,
            )
            model.fit(
                train_ds,
                validation_data=val_ds,
                epochs=args.epochs,
                initial_epoch=phase2_initial_epoch,
                callbacks=make_phase_callbacks("phase2", phase2_checkpoint),
            )
            completed_epochs = args.epochs

        write_resume_state(
            state_path,
            phase="phase2_complete",
            completed_epochs=args.epochs,
            phase1_epochs=phase1_epochs,
            total_epochs=args.epochs,
            checkpoint_path=phase2_checkpoint,
            dataset_dir=dataset_dir,
            class_names=class_names,
        )

    loss, acc = model.evaluate(val_ds, verbose=0)
    LOGGER.info("Validation: loss=%.4f accuracy=%.4f", float(loss), float(acc))

    model.save(model_path)
    labels_path.write_text("\n".join(class_names) + "\n", encoding="utf-8")

    metadata = {
        "dataset": str(dataset_dir),
        "model_path": str(model_path),
        "labels_path": str(labels_path),
        "checkpoint_dir": str(checkpoint_dir),
        "resume_enabled": bool(args.resume),
        "img_size": args.img_size,
        "batch_size": args.batch_size,
        "epochs": args.epochs,
        "validation_split": args.validation_split,
        "learning_rate": args.learning_rate,
        "fine_tune_layers": args.fine_tune_layers,
        "n_classes": n_classes,
        "class_names": class_names,
        "val_loss": float(loss),
        "val_accuracy": float(acc),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(checkpoint_dir, ignore_errors=True)

    print("\n=== TRAINING COMPLETATO ===")
    print(f"Modello Keras: {model_path}")
    print(f"Labels:        {labels_path}")
    print(f"Val accuracy:  {acc * 100:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
