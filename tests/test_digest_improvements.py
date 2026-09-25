import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from arxiv_tracker.query import build_search_query
from arxiv_tracker.research_analysis import generate_group_analysis, merge_group_items
from arxiv_tracker.sitegen import generate_site
from scripts.send_feishu_digest import build_markdown


class DigestImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.paper_a = {
            "id": "https://arxiv.org/abs/2609.00001",
            "title": "Learning to Use Tools in Agents",
            "authors": ["A. Researcher"],
            "summary": "We study tool use by language model agents and train them with online reinforcement learning.",
            "html_url": "https://arxiv.org/abs/2609.00001",
            "pdf_url": "https://arxiv.org/pdf/2609.00001",
            "code_urls": ["https://github.com/example/agent-tools"],
            "groups": ["Agentic RL", "代码Agent"],
        }
        self.paper_b = {
            "id": "https://arxiv.org/abs/2609.00002",
            "title": "Robust Agent Training with Verifiable Rewards",
            "authors": ["B. Researcher"],
            "summary": "We compare verifiable reward signals for long-horizon language agent tasks.",
            "html_url": "https://arxiv.org/abs/2609.00002",
            "code_urls": [],
            "groups": ["Agentic RL"],
        }

    def test_config_adds_agentic_rl_and_drops_broad_fim_keyword(self):
        config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
        groups = {group["name"]: group["keywords"] for group in config["groups"]}
        self.assertIn("Agentic RL", groups)
        self.assertTrue(any("reinforcement learning" in keyword.lower() for keyword in groups["Agentic RL"]))
        self.assertNotIn("fill-in-the-middle", groups["代码预训练"])

        query = build_search_query(config["categories"], groups["Agentic RL"], logic=config["logic"])
        self.assertIn('ti:"agentic reinforcement learning"', query)
        self.assertIn('abs:"online reinforcement learning for agents"', query)

    def test_overlapping_group_results_count_each_paper_once(self):
        merged = merge_group_items([
            ("Agentic RL", [self.paper_a, self.paper_b]),
            ("代码Agent", [self.paper_a]),
        ])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["groups"], ["Agentic RL", "代码Agent"])

    @patch("arxiv_tracker.research_analysis._chat_completions_request")
    def test_analysis_checks_citations_and_marks_empty_groups(self, request):
        request.return_value = json.dumps({"groups": {"Agentic RL": {
            "direction": {"text": "本期研究把在线策略更新用于语言模型代理的工具调用。", "paper_ids": [self.paper_a["id"]]},
            "connections": {"text": "两项工作分别关注工具交互与可验证奖励，可在长程任务中互补对照。", "paper_ids": [self.paper_a["id"], self.paper_b["id"]]},
            "bottleneck": {"text": "两项工作的评测任务仍不足以说明奖励信号能否迁移到不同工具环境。", "paper_ids": [self.paper_a["id"], self.paper_b["id"]]},
            "next_steps": [{"question": "在相同长程工具任务上比较在线奖励与可验证奖励的稳定性。", "paper_ids": [self.paper_a["id"], self.paper_b["id"]]}],
        }}})
        analysis = generate_group_analysis(
            ["Agentic RL", "代码预训练"], [self.paper_a, self.paper_b],
            summaries_zh={}, llm_cfg={"api_key": "test-key"},
        )
        request.assert_called_once()
        self.assertEqual(analysis["Agentic RL"]["source"], "llm")
        self.assertTrue(analysis["代码预训练"]["empty"])
        self.assertEqual(analysis["Agentic RL"]["connections"]["paper_ids"], [self.paper_a["id"], self.paper_b["id"]])

    @patch("arxiv_tracker.research_analysis._chat_completions_request")
    def test_placeholder_or_unknown_citations_use_explicit_safe_fallback(self, request):
        request.return_value = json.dumps({"groups": {"Agentic RL": {
            "direction": {"text": "...", "paper_ids": ["https://arxiv.org/abs/9999.99999"]},
        }}})
        analysis = generate_group_analysis(
            ["Agentic RL"], [self.paper_a], llm_cfg={"api_key": "test-key"}
        )["Agentic RL"]
        self.assertEqual(analysis["source"], "fallback")
        self.assertIn("样本不足", analysis["direction"]["text"])
        self.assertEqual(analysis["direction"]["paper_ids"], [self.paper_a["id"]])

    @patch("arxiv_tracker.research_analysis._chat_completions_request", side_effect=RuntimeError("offline"))
    def test_empty_digest_skips_llm_and_synthesis_failure_has_fallback(self, request):
        empty = generate_group_analysis(["Agentic RL"], [], llm_cfg={"api_key": "test-key"})
        request.assert_not_called()
        self.assertTrue(empty["Agentic RL"]["empty"])

        fallback = generate_group_analysis(
            ["Agentic RL"], [self.paper_a], llm_cfg={"api_key": "test-key"}
        )["Agentic RL"]
        self.assertEqual(fallback["source"], "fallback")
        self.assertTrue(fallback["direction"]["text"])
        request.assert_called_once()

    def test_site_and_lark_render_same_linked_trend_data_and_search_controls(self):
        claims = {
            "direction": {"text": "本期工作探索在线策略更新与工具使用训练。", "paper_ids": [self.paper_a["id"]]},
            "connections": {"text": "两项研究可在相同任务上对照交互策略和奖励设计。", "paper_ids": [self.paper_a["id"], self.paper_b["id"]]},
            "bottleneck": {"text": "目前尚需验证训练信号跨工具环境迁移时的稳定性。", "paper_ids": [self.paper_a["id"], self.paper_b["id"]]},
            "next_steps": [{"question": "固定工具集和任务难度后比较两类训练信号的成功率与成本。", "paper_ids": [self.paper_a["id"], self.paper_b["id"]]}],
            "count": 2,
        }
        group_analysis = {"Agentic RL": claims, "代码预训练": {"count": 0, "empty": True}}
        translations = {self.paper_a["id"]: {"title_zh": "代理工具使用强化学习"}}
        summaries_zh = {self.paper_a["id"]: {"digest_zh": "通过在线强化学习提升代理调用工具的能力。"}}
        with tempfile.TemporaryDirectory() as site_dir:
            result = generate_site(
                items=[self.paper_a, self.paper_b], summaries_zh=summaries_zh, summaries_en={},
                translations=translations, site_dir=site_dir, group_names=["Agentic RL", "代码预训练"],
                group_analysis=group_analysis,
            )
            html = Path(result["index_path"]).read_text(encoding="utf-8")

        self.assertIn("今日研究观察", html)
        self.assertIn("去重论文", html)
        self.assertIn('id="paper-search"', html)
        self.assertIn('id="code-only"', html)
        self.assertIn("card.dataset.hasCode === 'true'", html)
        self.assertIn("overflow-x:auto", html)
        self.assertIn("代理工具使用强化学习", html)
        self.assertIn("class=\"code-link\"", html)
        self.assertIn("https://arxiv.org/abs/2609.00002", html)
        self.assertIn("固定工具集和任务难度后比较两类训练信号的成功率与成本。", html)
        self.assertIn("本方向今日无命中", html)

        payload = {
            "items": [{**self.paper_a, "title_zh": "代理工具使用强化学习"}, self.paper_b],
            "group_analysis": group_analysis,
        }
        markdown = build_markdown(payload)
        self.assertIn("今日观察", markdown)
        self.assertIn("[代理工具使用强化学习](https://arxiv.org/abs/2609.00001)", markdown)
        self.assertIn("本期工作探索在线策略更新与工具使用训练。", html)
        self.assertIn("本期工作探索在线策略更新与工具使用训练。", markdown)

    def test_no_hits_have_clear_empty_state_without_invented_trends(self):
        analysis = generate_group_analysis(["Agentic RL"], [], llm_cfg={})
        with tempfile.TemporaryDirectory() as site_dir:
            result = generate_site(
                items=[], summaries_zh={}, summaries_en={}, translations={}, site_dir=site_dir,
                group_names=["Agentic RL"], group_analysis=analysis,
            )
            html = Path(result["index_path"]).read_text(encoding="utf-8")
        self.assertIn("今天没有新增命中", html)
        self.assertIn("本方向今日无命中，暂不生成趋势判断", html)
        lark = build_markdown({"items": [], "group_analysis": analysis})
        self.assertIn("今天没有新的命中", lark)
        self.assertNotIn("今日观察", lark)


if __name__ == "__main__":
    unittest.main()
