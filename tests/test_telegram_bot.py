import json
import os
from pathlib import Path

import interface.telegram_bot as tg


def test_labels_for_organ_uses_correct_sets(tmp_path, monkeypatch):
    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("Sano\nOidio\n", encoding="utf-8")
    monkeypatch.setitem(tg.MODEL_CONFIG, "labels_path", str(labels_file))

    leaf_labels = tg._labels_for_organ(None, "leaf")
    assert leaf_labels == ["Sano", "Oidio"]
    assert tg._labels_for_organ(None, "flower") == list(tg.FLOWER_LABELS)
    assert tg._labels_for_organ(None, "fruit") == list(tg.FRUIT_LABELS)


def test_resolve_organ_uses_label_sets():
    assert tg._resolve_organ(tg.FLOWER_LABELS[0]) == "flower"
    assert tg._resolve_organ(tg.FRUIT_LABELS[0]) == "fruit"
    assert tg._resolve_organ("Sano") == "leaf"


def test_finetune_target_by_organ():
    assert tg._finetune_target_by_organ("leaf") == tg.FINETUNING_CONFIG
    assert tg._finetune_target_by_organ("flower") == tg.FINETUNING_FLOWER_CONFIG
    assert tg._finetune_target_by_organ("fruit") == tg.FINETUNING_FRUIT_CONFIG


def test_sanitize_label():
    assert tg._sanitize_label("A b/c") == "A_b_c"


def test_store_learning_record_writes_metadata(tmp_path, monkeypatch):
    input_image = tmp_path / "input.jpg"
    input_image.write_bytes(b"fake")
    lbd_dir = tmp_path / "learning"
    monkeypatch.setattr(tg, "LEARNING_BY_DOING_DIR", lbd_dir)

    meta_path = tg._store_learning_record(
        input_image,
        plant_name="Dipladenia",
        label="Fiore_sano",
        organ="flower",
        user_info={"id": 1, "username": "@user"},
    )

    assert meta_path.exists()
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert data["plant_name"] == "Dipladenia"
    assert data["label"] == "Fiore_sano"
    assert data["organ"] == "flower"
    assert Path(data["stored_image"]).exists()
    assert data["training_image"] is None


def test_list_input_images_orders_by_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(tg, "INPUT_IMAGES_DIR", tmp_path)
    monkeypatch.setitem(tg.VISION_CONFIG, "input_image_extensions", [".jpg", ".png"])

    older = tmp_path / "a.jpg"
    newer = tmp_path / "b.png"
    ignored = tmp_path / "c.txt"
    older.write_bytes(b"a")
    newer.write_bytes(b"b")
    ignored.write_bytes(b"c")

    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    images = tg._list_input_images(limit=10)
    assert [img.name for img in images] == ["b.png", "a.jpg"]
    latest = tg._get_latest_input_image()
    assert latest is not None
    assert latest.name == "b.png"
