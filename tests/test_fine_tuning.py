from ai.fine_tuning import FineTuner


def test_get_dataset_stats_counts(tmp_path):
    dataset_dir = tmp_path / "dataset"
    (dataset_dir / "A").mkdir(parents=True)
    (dataset_dir / "B").mkdir(parents=True)
    (dataset_dir / "A" / "a1.jpg").write_bytes(b"a")
    (dataset_dir / "A" / "a2.png").write_bytes(b"a")
    (dataset_dir / "B" / "b1.jpg").write_bytes(b"b")

    tuner = FineTuner(model_loader=None, dataset_dir=dataset_dir)
    stats = tuner.get_dataset_stats()

    assert stats["total"] == 3
    assert stats["classes"]["A"] == 2
    assert stats["classes"]["B"] == 1
