"""Privacy boundary tests. All cloud transports are mocked; no student DB access."""
import json
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from apps.graduate import llm, privacy


@override_settings(PRIVACY_DEMO_MIN_GROUP_SIZE=5, PRIVACY_DEMO_ALLOW_CLOUD=False)
class PrivacyBoundaryTests(SimpleTestCase):
    def test_individual_and_small_group_never_release_a_payload(self):
        for scenario in ("individual", "small"):
            for identity in (True, False):
                with self.subTest(scenario=scenario, identity=identity):
                    plan = privacy.inspect_task(scenario, identity)
                    self.assertEqual(plan["route"], "local")
                    self.assertIsNone(plan["cloudPayload"])
                    self.assertEqual(plan["approvedFieldCount"], 0)

    def test_policy_rebuilds_question_and_drops_identity_and_notes(self):
        plan = privacy.inspect_task("policy", True)
        original = json.dumps(plan["sourceData"], ensure_ascii=False)
        approved = json.dumps(plan["cloudPayload"], ensure_ascii=False)
        self.assertIn("DEMO-001", original)
        self.assertNotIn("DEMO-001", approved)
        self.assertNotIn("演示学生甲", approved)
        self.assertNotIn("supportNote", approved)
        self.assertEqual(plan["cloudPayload"]["question"], privacy.POLICY_QUESTION)
        self.assertEqual(next(row["action"] for row in plan["decisions"] if row["field"] == "question"), "generalize")

    def test_cohort_releases_only_three_counts_and_digest_is_stable(self):
        identified = privacy.inspect_task("cohort", True)
        minimal = privacy.inspect_task("cohort", False)
        self.assertEqual(identified["cloudPayload"], {"studentCount": 42, "overdueCount": 11, "completedCount": 31})
        self.assertEqual(identified["payloadDigest"], minimal["payloadDigest"])
        self.assertGreater(identified["protectedFieldCount"], minimal["protectedFieldCount"])

    @override_settings(PRIVACY_DEMO_MIN_GROUP_SIZE=12)
    def test_small_nonzero_cell_is_protected_even_when_total_is_large(self):
        plan = privacy.inspect_task("cohort", False)
        self.assertEqual(plan["route"], "local")
        self.assertIsNone(plan["cloudPayload"])

    @override_settings(PRIVACY_DEMO_MIN_GROUP_SIZE=1)
    def test_group_threshold_cannot_be_lowered_below_five(self):
        self.assertEqual(privacy.minimum_group_size(), 5)

    @mock.patch.object(llm, "invoke_prediction_chat_completion")
    def test_local_execution_does_not_touch_model_even_for_eligible_tasks(self, invoke):
        for scenario in ("individual", "policy", "cohort", "small"):
            result = privacy.execute_task(scenario)
            self.assertFalse(result["audit"]["cloudAttempted"])
            self.assertFalse(result["audit"]["cloudUsed"])
            self.assertEqual(result["audit"]["payloadDigest"], "")
            self.assertTrue(result["answer"]["directAnswer"])
        invoke.assert_not_called()

    @override_settings(PRIVACY_DEMO_ALLOW_CLOUD=True)
    @mock.patch.object(llm, "invoke_prediction_chat_completion")
    def test_client_cannot_force_a_blocked_task_to_the_cloud(self, invoke):
        for scenario in ("individual", "small"):
            result = privacy.execute_task(scenario, True, "cloud")
            self.assertEqual(result["audit"]["executionMode"], "local")
            self.assertFalse(result["audit"]["cloudAttempted"])
        invoke.assert_not_called()

    def test_unknown_scenario_and_mode_are_rejected(self):
        with self.assertRaises(ValueError):
            privacy.inspect_task("custom")
        with self.assertRaises(ValueError):
            privacy.execute_task("policy", execution_mode="unchecked")


@override_settings(PRIVACY_DEMO_ALLOW_CLOUD=True, PREDICTION_LLM_ENABLED=True,
                   PREDICTION_LLM_API_KEY="test-only-key", PREDICTION_LLM_MODEL="test-model",
                   PREDICTION_LLM_API_STYLE="chat_completions", PRIVACY_DEMO_MIN_GROUP_SIZE=5)
class PrivacyCloudTests(SimpleTestCase):
    def test_actual_transport_body_contains_only_approved_business_input(self):
        answer = {"directAnswer": "演示政策答复", "reasoning": ["公开材料"], "actionPlan": ["核对正式制度"], "citations": []}
        response = {"choices": [{"message": {"content": json.dumps(answer, ensure_ascii=False)}}]}
        with mock.patch.object(llm, "post_json", return_value=(response, None)) as transport:
            result = privacy.execute_task("policy", True, "cloud")
        self.assertTrue(result["audit"]["cloudUsed"])
        transport.assert_called_once()
        body = json.dumps(transport.call_args.args[1], ensure_ascii=False)
        for forbidden in ("DEMO-001", "演示学生甲", "supportNote", "wellbeingScore"):
            self.assertNotIn(forbidden, body)
        self.assertIn(privacy.POLICY_QUESTION, body)

    @mock.patch.object(llm, "invoke_prediction_chat_completion", side_effect=RuntimeError("private provider body"))
    def test_provider_exception_returns_local_answer_without_error_body(self, invoke):
        result = privacy.execute_task("cohort", True, "cloud")
        self.assertEqual(result["audit"]["executionMode"], "fallback")
        self.assertTrue(result["audit"]["cloudAttempted"])
        self.assertFalse(result["audit"]["cloudUsed"])
        self.assertNotIn("private provider body", json.dumps(result))

    @mock.patch.object(llm, "invoke_prediction_chat_completion", return_value={"used": False, "reason": "timeout"})
    def test_model_failure_is_not_reported_as_cloud_success(self, invoke):
        result = privacy.execute_task("policy", True, "cloud")
        self.assertEqual(result["audit"]["executionMode"], "fallback")
        self.assertFalse(result["audit"]["cloudUsed"])

    @mock.patch.object(llm, "invoke_prediction_chat_completion", return_value={
        "used": True, "answer": {"directAnswer": "演示学生甲的学号是DEMO-001", "reasoning": [], "actionPlan": [], "citations": []},
    })
    def test_cloud_output_is_checked_before_display(self, invoke):
        result = privacy.execute_task("policy", True, "cloud")
        self.assertEqual(result["audit"]["executionMode"], "fallback")
        self.assertNotIn("DEMO-001", json.dumps(result["answer"], ensure_ascii=False))


@override_settings(PRIVACY_DEMO_ALLOW_CLOUD=False, PRIVACY_DEMO_MIN_GROUP_SIZE=5)
class PrivacyApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.base = "/api/v1/privacy-collaboration/"

    def test_catalog_is_synthetic_only_and_not_cached(self):
        response = self.client.get(self.base + "scenarios/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.data["dataSource"], "synthetic")
        self.assertEqual(len(response.data["scenarios"]), 4)
        self.assertFalse(response.data["cloudAvailable"])

    def test_arbitrary_payloads_prompts_and_client_thresholds_are_rejected(self):
        for field, value in (("cloudPayload", {"name": "private"}), ("studentId", "real-id"),
                             ("question", "custom prompt"), ("minimumGroupSize", 1)):
            with self.subTest(field=field):
                response = self.client.post(self.base + "execute/", {"scenario": "policy", field: value}, format="json")
                self.assertEqual(response.status_code, 400)

    def test_execute_rechecks_instead_of_requiring_or_trusting_a_preview(self):
        response = self.client.post(self.base + "execute/", {"scenario": "small", "executionMode": "cloud"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["plan"]["route"], "local")
        self.assertFalse(response.data["audit"]["cloudAttempted"])

    def test_disabled_cloud_cannot_be_enabled_by_browser(self):
        response = self.client.post(self.base + "execute/", {"scenario": "policy", "executionMode": "cloud"}, format="json")
        self.assertEqual(response.status_code, 409)

    def test_audit_has_no_raw_source_or_answer(self):
        response = self.client.post(self.base + "execute/", {"scenario": "individual"}, format="json")
        self.assertEqual(response.status_code, 200)
        audit = json.dumps(response.data["audit"], ensure_ascii=False)
        for forbidden in ("DEMO-001", "演示学生甲", "supportNote", "wellbeingScore", "sourceData", "answer"):
            self.assertNotIn(forbidden, audit)

    def test_invalid_scenarios_are_bad_requests(self):
        for payload in ({}, {"scenario": "custom"}, {"scenario": "policy", "executionMode": "bypass"}):
            self.assertEqual(self.client.post(self.base + "inspect/", payload, format="json").status_code, 400)

    def test_rate_limit_prevents_unbounded_demo_requests(self):
        for _ in range(30):
            self.assertEqual(self.client.get(self.base + "scenarios/").status_code, 200)
        self.assertEqual(self.client.get(self.base + "scenarios/").status_code, 429)
