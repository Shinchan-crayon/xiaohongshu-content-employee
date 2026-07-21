import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


RUNTIME_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "xiaohongshu-content-employee"
    / "scripts"
    / "工作流工具"
    / "workflow_runtime.py"
)
SPEC = importlib.util.spec_from_file_location("workflow_runtime", RUNTIME_PATH)
workflow_runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(workflow_runtime)


class WorkflowRuntimeRegressionTests(unittest.TestCase):
    def test_canonical_identity_protects_forbidden_substring(self):
        identity = {
            "exact_page_title": "Apple iPhone 15 Pro Max",
            "identifying_terms": ["iPhone 15 Pro Max"],
            "locked_terms": ["iPhone 15 Pro Max"],
            "forbidden_replacements": ["iPhone 15 Pro"],
        }

        workflow_runtime._reject_forbidden_replacements(
            [("post", "这次选择的是 iPhone 15 Pro Max。")],
            identity,
        )

        with self.assertRaisesRegex(ValueError, "iPhone 15 Pro"):
            workflow_runtime._reject_forbidden_replacements(
                [("post", "这次选择的是 iPhone 15 Pro。")],
                identity,
            )

    def test_public_product_identity_visual_page_validates(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            material = {
                "reference_image_strategy": "public_product_identity",
                "product_identity": {"locked_terms": ["iPhone 15 Pro Max"]},
                "product_reference_pack": [],
                "selling_points": [{"id": "sp-1"}],
            }
            evidence = {"claims": [{"id": "claim-1"}]}
            (run_dir / "material.json").write_text(
                json.dumps(material), encoding="utf-8"
            )
            (run_dir / "evidence.json").write_text(
                json.dumps(evidence), encoding="utf-8"
            )
            payload = {
                "style_anchor": {"tone": "warm"},
                "pages": [
                    {
                        "id": "page-1",
                        "page_role": "cover",
                        "shot_type": "hero",
                        "subject_position": "center",
                        "subject_scale": "55%",
                        "background_scene": "cafe",
                        "text_zone": "top-third",
                        "information_task": "identity",
                        "prompt": "iPhone 15 Pro Max 咖啡馆手持实景",
                        "product_subject": True,
                        "product_view": "identity-only",
                        "reference_image_ids": [],
                        "reference_image_paths": [],
                        "selling_point_ids": ["sp-1"],
                        "claim_ids": ["claim-1"],
                    }
                ],
            }

            workflow_runtime._validate_visual(
                payload,
                workflow_runtime.load_contracts(),
                run_dir,
            )

    def test_failed_worker_transition_keeps_stage_retryable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            output_paths = [run_dir / "material.json", run_dir / "evidence.json"]
            for path in output_paths:
                path.write_text("{}", encoding="utf-8")
            runtime = {
                "schema_version": 1,
                "run_id": "xhs-20260721T000000000000Z-deadbeef",
                "task_summary": "test",
                "stage": "created",
                "approval_status": "not_requested",
                "default_image_provider": None,
                "default_image_model": None,
                "created_at": "2026-07-21T00:00:00Z",
                "plugin_root": str(run_dir),
                "delivery_root": str(run_dir / "delivery"),
                "artifacts": {},
                "worker_sessions": {"research-worker": "research-test"},
                "delivery_paths": {"html_path": None, "runtime_log_path": None},
                "transitions": [],
                "stage_metrics": {
                    "research-worker": {
                        "started_at": "2026-07-21T00:00:00Z",
                        "finished_at": None,
                        "loaded_skills": [
                            "product-material-intake",
                            "xhs-research-strategy",
                        ],
                        "input_paths": [],
                        "output_paths": [],
                        "input_bytes": 0,
                        "output_bytes": 0,
                        "token_count": None,
                        "model_calls": 0,
                        "tool_calls": 0,
                        "retries": 0,
                        "paid_requests": 0,
                        "cost_amount": None,
                        "cost_currency": None,
                        "cost_status": "unavailable",
                        "worker_id": "research-worker",
                        "worker_session_id": "research-test",
                    }
                },
            }
            (run_dir / "runtime.json").write_text(
                json.dumps(runtime), encoding="utf-8"
            )

            with mock.patch.object(
                workflow_runtime,
                "transition",
                side_effect=ValueError("artifact invalid"),
            ):
                with self.assertRaisesRegex(ValueError, "artifact invalid"):
                    workflow_runtime.finish_stage(
                        run_dir,
                        "research-worker",
                        output_paths,
                        {"model_calls": 1},
                    )

            rolled_back = workflow_runtime.load_runtime(run_dir)
            self.assertIsNone(
                rolled_back["stage_metrics"]["research-worker"]["finished_at"]
            )
            self.assertEqual(rolled_back["stage"], "created")


if __name__ == "__main__":
    unittest.main()
