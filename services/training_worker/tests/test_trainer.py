"""Tests for trainer warm-start fallback behaviour.

Covers VT-LEO-AI-106-TC-004.
"""

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestFetchWarmStartModel(unittest.TestCase):
    """VT-106-TC-004: warm-start falls back to cold init on error."""

    def _run_fetch(self, version: str, raises: bool):
        """Import and call _fetch_warm_start_model with a mocked ModelStore."""
        log_messages = []

        def _log(msg: str) -> None:
            log_messages.append(msg)

        if raises:
            mock_store = MagicMock()
            mock_store.download.side_effect = Exception("blob not found")
        else:
            mock_store = MagicMock()
            from pathlib import Path

            mock_store.download.return_value = Path("/tmp/mock_model")

        with patch.dict(
            "sys.modules",
            {"libs.model_store": MagicMock(ModelStore=lambda: mock_store)},
        ):
            from app.trainer import _fetch_warm_start_model

            result = _fetch_warm_start_model(version, _log)

        return result, log_messages

    def test_fallback_returns_none_on_exception(self):
        result, logs = self._run_fetch("v1.0.0", raises=True)
        self.assertIsNone(result)

    def test_fallback_logs_warning(self):
        result, logs = self._run_fetch("v1.0.0", raises=True)
        warning_logs = [m for m in logs if "warm-start" in m.lower() or "WARNING" in m]
        self.assertTrue(
            len(warning_logs) > 0, "Expected warning log from failed warm-start"
        )

    def test_success_returns_path(self):
        from pathlib import Path

        result, logs = self._run_fetch("v1.0.0", raises=False)
        self.assertIsInstance(result, Path)

    def test_no_exception_propagated(self):
        try:
            self._run_fetch("v1.0.0", raises=True)
        except Exception as exc:
            self.fail(f"_fetch_warm_start_model should not propagate exception: {exc}")


class TestFrozenComponentsWriteThrough(unittest.TestCase):
    """Wave 0 / F1 regression: frozen_components must survive to train.cfg.

    The previous trainer silently stripped 'transformer' from the frozen
    list before writing train.cfg.  The leo_training.TransformerListener.v1
    architecture now handles the frozen-init dimension issue explicitly, so
    the frozen list must be written through verbatim.
    """

    def test_transformer_remains_frozen_in_written_config(self):
        from app.trainer import _write_filled_config

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "train.cfg"
            _write_filled_config(
                out_path,
                train_path=Path("/tmp/train.spacy"),
                dev_path=Path("/tmp/dev.spacy"),
                frozen_components=["transformer"],
                use_gpu=False,
            )
            text = out_path.read_text(encoding="utf-8")

        match = re.search(r"frozen_components\s*=\s*\[(.*?)\]", text)
        self.assertIsNotNone(match, "frozen_components key missing from written config")
        assert match is not None
        self.assertIn("transformer", match.group(1))

        # annotating_components must also include transformer so TransformerListener
        # layers still see forward-pass outputs even when the pipe is frozen.
        ann_match = re.search(r"annotating_components\s*=\s*\[(.*?)\]", text)
        self.assertIsNotNone(ann_match, "annotating_components missing from config")
        assert ann_match is not None
        self.assertIn("transformer", ann_match.group(1))

    def test_empty_frozen_components_writes_empty_list(self):
        from app.trainer import _write_filled_config

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "train.cfg"
            _write_filled_config(
                out_path,
                train_path=Path("/tmp/train.spacy"),
                dev_path=Path("/tmp/dev.spacy"),
                frozen_components=[],
                use_gpu=False,
            )
            text = out_path.read_text(encoding="utf-8")

        self.assertIn("frozen_components = []", text)
        self.assertIn("annotating_components = []", text)


class TestConfigHygieneOverrides(unittest.TestCase):
    """Wave 1 regression: env-driven overrides land in the written config."""

    def _write(self, **kwargs) -> str:
        from app.trainer import _write_filled_config

        defaults = dict(
            train_path=Path("/tmp/train.spacy"),
            dev_path=Path("/tmp/dev.spacy"),
            frozen_components=["transformer"],
            use_gpu=False,
            accelerator_resolved="cpu",
        )
        defaults.update(kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "train.cfg"
            _write_filled_config(out_path, **defaults)
            return out_path.read_text(encoding="utf-8")

    def test_window_and_stride_overrides(self):
        import os

        with patch.dict(
            os.environ,
            {"TRAINING_WINDOW_TOKENS": "384", "TRAINING_STRIDE_TOKENS": "256"},
        ):
            text = self._write()
        self.assertRegex(text, r"(?m)^window\s*=\s*384$")
        self.assertRegex(text, r"(?m)^stride\s*=\s*256$")

    def test_window_override_ignores_non_integer(self):
        import os

        with patch.dict(os.environ, {"TRAINING_WINDOW_TOKENS": "not-an-int"}):
            text = self._write()
        self.assertRegex(text, r"(?m)^window\s*=\s*256$")

    def test_max_steps_override_updates_training_and_lr_schedule(self):
        import os

        with patch.dict(os.environ, {"TRAINING_MAX_STEPS": "4000"}):
            text = self._write()
        self.assertRegex(text, r"(?m)^max_steps\s*=\s*4000$")
        self.assertRegex(text, r"(?m)^total_steps\s*=\s*4000$")

    def test_mixed_precision_only_flips_on_cuda(self):
        text_cpu = self._write(accelerator_resolved="cpu")
        self.assertRegex(text_cpu, r"(?m)^mixed_precision\s*=\s*false$")
        text_mps = self._write(accelerator_resolved="mps")
        self.assertRegex(text_mps, r"(?m)^mixed_precision\s*=\s*false$")
        text_cuda = self._write(accelerator_resolved="cuda")
        self.assertRegex(text_cuda, r"(?m)^mixed_precision\s*=\s*true$")

    def test_warmup_linear_is_default(self):
        import os

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRAINING_LR_SCHEDULE", None)
            default = self._write()
        self.assertIn('@schedules = "warmup_linear.v1"', default)

    def test_cosine_written_when_available(self):
        """cosine is written to the config only when thinc has warmup_cosine.v1."""
        import os
        from unittest.mock import patch as _patch
        # Must patch via the same import path _write_filled_config uses (app.trainer).
        with _patch("app.trainer._is_cosine_available", return_value=True):
            with patch.dict(os.environ, {"TRAINING_LR_SCHEDULE": "cosine"}):
                text = self._write()
        self.assertIn('@schedules = "warmup_cosine.v1"', text)

    def test_cosine_falls_back_to_linear_when_unavailable(self):
        """If warmup_cosine.v1 is not registered, silently use warmup_linear."""
        import os
        from unittest.mock import patch as _patch
        with _patch("app.trainer._is_cosine_available", return_value=False):
            with patch.dict(os.environ, {"TRAINING_LR_SCHEDULE": "cosine"}):
                text = self._write()
        self.assertIn('@schedules = "warmup_linear.v1"', text)

    def test_lr_schedule_invalid_falls_back_to_linear(self):
        import os

        with patch.dict(os.environ, {"TRAINING_LR_SCHEDULE": "bogus"}):
            text = self._write()
        self.assertIn('@schedules = "warmup_linear.v1"', text)

    def test_gpu_allocator_set_when_use_gpu(self):
        text = self._write(use_gpu=True)
        self.assertIn('gpu_allocator = "pytorch"', text)
        self.assertNotIn("gpu_allocator = null", text)

    def test_wave1_defaults_are_written(self):
        """Baseline values land in the rendered config — guards F3/F4/F10/F11."""
        text = self._write()
        self.assertRegex(text, r"(?m)^accumulate_gradient\s*=\s*4$")
        self.assertRegex(text, r"(?m)^use_averages\s*=\s*true$")
        self.assertRegex(text, r"(?m)^hidden_size\s*=\s*384$")
        self.assertRegex(text, r"(?m)^start\s*=\s*256$")
        self.assertRegex(text, r"(?m)^stop\s*=\s*1024$")
        # Window/stride match the plan's Wave 1 bundle.
        self.assertRegex(text, r"(?m)^window\s*=\s*256$")
        self.assertRegex(text, r"(?m)^stride\s*=\s*192$")

    def test_pre_e313_dynamics_profile_restores_training_values(self):
        import os

        with patch.dict(
            os.environ,
            {
                "TRAINING_ABLATION_PROFILE": "pre_e313_dynamics",
                "TRAINING_MAX_STEPS": "",
                "TRAINING_WINDOW_TOKENS": "",
                "TRAINING_STRIDE_TOKENS": "",
            },
        ):
            text = self._write()

        self.assertRegex(text, r"(?m)^hidden_size\s*=\s*128$")
        self.assertRegex(text, r"(?m)^dropout\s*=\s*0.1$")
        self.assertRegex(text, r"(?m)^accumulate_gradient\s*=\s*1$")
        self.assertRegex(text, r"(?m)^patience\s*=\s*1600$")
        self.assertRegex(text, r"(?m)^max_steps\s*=\s*20000$")
        self.assertRegex(text, r"(?m)^initial_rate\s*=\s*0.00005$")
        self.assertIn("frozen_components = [\"transformer\"]", text)


class TestTrainingWallTimeout(unittest.TestCase):
    """TRAINING_JOB_TIMEOUT_S parsing keeps local runs uncapped by default."""

    def test_unset_timeout_disables_wall_cap(self):
        import os

        from app.trainer import _parse_training_wall_timeout_s

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TRAINING_JOB_TIMEOUT_S", None)
            self.assertEqual(_parse_training_wall_timeout_s(), 0)

    def test_zero_timeout_disables_wall_cap(self):
        import os

        from app.trainer import _parse_training_wall_timeout_s

        with patch.dict(os.environ, {"TRAINING_JOB_TIMEOUT_S": "0"}):
            self.assertEqual(_parse_training_wall_timeout_s(), 0)

    def test_positive_timeout_is_used(self):
        import os

        from app.trainer import _parse_training_wall_timeout_s

        with patch.dict(os.environ, {"TRAINING_JOB_TIMEOUT_S": "43200"}):
            self.assertEqual(_parse_training_wall_timeout_s(), 43200)

    def test_timeout_recovery_accepts_saved_model_best(self):
        from app.trainer import _recover_saved_model

        logs = []
        with tempfile.TemporaryDirectory() as tmp:
            model_best = Path(tmp) / "model-best"
            model_best.mkdir()
            (model_best / "meta.json").write_text("{}", encoding="utf-8")

            recovered = _recover_saved_model(
                Path(tmp),
                ["Training exceeded wall-clock training timeout"],
                logs.append,
            )

        self.assertEqual(recovered, model_best)
        self.assertTrue(any("recovering model-best" in line for line in logs))
