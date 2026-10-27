import unittest

from app.api.workforce import get_copilot_agents_design
from app.services.copilot_agents import build_copilot_agents_package

AGENT_CAPABILITIES = {
    "ai_ceo": {"Portfolio Review", "Strategic Planning", "Business Outcomes", "Risk Review", "Investment Governance"},
    "ai_cto": {"Architecture Review", "Technology Governance", "Platform Health", "Technical Risks"},
    "ai_workforce_director": {"Workforce Planning", "Skill Analysis", "Capacity Planning", "Assignment Readiness"},
    "ai_delivery_director": {"Project Review", "Sprint Review", "Release Governance", "Delivery Risks"},
    "ai_operations_director": {"Hosting Review", "Operations Readiness", "Incident Analysis", "Cost Optimization"},
}


class CopilotAgentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = build_copilot_agents_package()

    def test_five_agents_have_required_capabilities_and_artifacts(self):
        self.assertEqual(set(self.package["agents"]), set(AGENT_CAPABILITIES))
        for agent_id, capabilities in AGENT_CAPABILITIES.items():
            agent = self.package["agents"][agent_id]
            self.assertEqual(set(agent["capabilities"]), capabilities)
            self.assertEqual(len(agent["copilot_studio_topics"]), len(capabilities))
            self.assertEqual(len(agent["conversation_flows"]), len(capabilities))
            self.assertEqual(len(agent["adaptive_cards"]), len(capabilities))
            self.assertTrue(agent["knowledge_sources"] and agent["agent_instructions"])
            for topic in agent["copilot_studio_topics"]:
                self.assertTrue(topic["trigger_phrases"])
            for item in agent["adaptive_cards"]:
                self.assertEqual(item["card"]["type"], "AdaptiveCard")

    def test_agents_cannot_act_and_sources_are_read_only(self):
        for agent in self.package["agents"].values():
            self.assertFalse(agent["autonomous_actions_enabled"])
            self.assertFalse(agent["published"])
            self.assertIn("cannot create, approve", agent["agent_instructions"])
            for source in agent["knowledge_sources"]:
                self.assertEqual(source["type"], "READ_ONLY_API")
                self.assertTrue(source["allowed_roles"])
            for flow in agent["conversation_flows"]:
                self.assertTrue(all(s["type"] != "Approve" for s in flow["steps"]))
        self.assertTrue(any(p["pattern"] == "NO_CHAT_APPROVALS" for p in self.package["approval_patterns"]))
        self.assertIn("authentication", self.package["security_model"])

    def test_safety_flags_and_api(self):
        self.assertEqual(self.package["authority"], "NONE")
        self.assertFalse(self.package["action_allowed"])
        self.assertFalse(self.package["persistence"])
        self.assertFalse(any(self.package["controls"].values()))
        self.assertEqual(get_copilot_agents_design()["status"], "DESIGN_ONLY")


if __name__ == "__main__":
    unittest.main()
