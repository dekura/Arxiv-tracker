import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests
import yaml

from arxiv_tracker.email_template import render_email_html
from arxiv_tracker.insights import analyze_papers, arxiv_base_id, fallback_insight, normalize_training
from arxiv_tracker.output import save_markdown
from arxiv_tracker.query import build_search_query, date_window
from arxiv_tracker.research_analysis import merge_group_items
from arxiv_tracker.sitegen import generate_site
from scripts.send_feishu_digest import MAX_CHARS, build_markdown


def _llm_json(**overrides):
    data = {
        "title_zh": "代理工具使用的在线强化学习",
        "architecture": "LLM + tool harness",
        "training": ["RL"],
        "application": "工具调用",
        "innovation": "用在线 rollout 的工具执行结果作为稀疏奖励",
        "problem": "语言模型代理调用工具时错误累积，长程任务成功率低",
        "challenge": "工具反馈稀疏且延迟，离线数据覆盖不到真实交互分布",
        "solution": "在真实工具环境中在线采样轨迹，用执行成功信号做 PPO 更新",
        "results": "ToolBench 成功率从 41% 提升到 58%",
        "future": "奖励仅覆盖可自动判定的任务",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class DigestImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.paper_a = {
            "id": "https://arxiv.org/abs/2609.00001v2",
            "title": "Learning to Use Tools in Agents",
            "authors": ["A. Researcher"],
            "summary": "We study tool use by language model agents and train them with online reinforcement learning.",
            "html_url": "https://arxiv.org/abs/2609.00001v2",
            "pdf_url": "https://arxiv.org/pdf/2609.00001v2",
            "code_urls": ["https://github.com/example/agent-tools"],
            "groups": ["Agentic RL", "代码Agent"],
        }
        self.paper_b = {
            "id": "https://arxiv.org/abs/2609.00002v1",
            "title": "Robust Agent Training with Verifiable Rewards",
            "authors": ["B. Researcher"],
            "summary": "We compare verifiable reward signals for long-horizon language agent tasks. More text.",
            "html_url": "https://arxiv.org/abs/2609.00002v1",
            "code_urls": [],
            "groups": ["Agentic RL"],
        }
        self.insights = {
            self.paper_a["id"]: {
                "title_zh": "代理工具使用的在线强化学习",
                "tags": {"architecture": "LLM + tool harness", "training": ["RL"],
                         "application": "工具调用", "innovation": "用在线 rollout 的工具执行结果作为稀疏奖励"},
                "problem": "语言模型代理调用工具时错误累积", "challenge": "工具反馈稀疏且延迟",
                "solution": "在真实工具环境中在线采样轨迹做 PPO 更新", "results": "ToolBench 成功率 41% → 58%",
                "future": "奖励仅覆盖可自动判定的任务", "source": "llm",
            },
            self.paper_b["id"]: fallback_insight(self.paper_b),
        }

    # ---- config / query / fetch ----

    def test_config_adds_agentic_rl_and_drops_broad_fim_keyword(self):
        config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
        groups = {group["name"]: group["keywords"] for group in config["groups"]}
        self.assertIn("Agentic RL", groups)
        self.assertTrue(any("reinforcement learning" in keyword.lower() for keyword in groups["Agentic RL"]))
        self.assertNotIn("fill-in-the-middle", groups["代码预训练"])

        query = build_search_query(config["categories"], groups["Agentic RL"], logic=config["logic"])
        self.assertIn('ti:"agentic reinforcement learning"', query)
        self.assertIn('abs:"online reinforcement learning for agents"', query)

    def test_query_carries_server_side_date_window(self):
        window = date_window("lastUpdatedDate", datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc),
                             datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(window, "lastUpdatedDate:[202609250300 TO 202610010000]")
        query = build_search_query(["cs.SE"], ["coding agent"], ["survey"], "AND", window)
        self.assertIn(" AND lastUpdatedDate:[202609250300 TO 202610010000]", query)
        self.assertTrue(query.endswith(")"))
        self.assertLess(query.index("lastUpdatedDate"), query.index("AND NOT"))

    def test_overlapping_group_results_count_each_paper_once(self):
        merged = merge_group_items([
            ("Agentic RL", [self.paper_a, self.paper_b]),
            ("代码Agent", [self.paper_a]),
        ])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["groups"], ["Agentic RL", "代码Agent"])

    def test_freshness_window_covers_weekend_gap(self):
        config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
        self.assertGreaterEqual(int(config["freshness"]["since_days"]), 5)
        self.assertTrue(config["freshness"]["unique_only"])

    @patch("arxiv_tracker.cli.parse_feed")
    @patch("arxiv_tracker.cli.fetch_arxiv_feed")
    def test_stale_first_hit_does_not_drop_later_fresh_paper(self, fetch, parse):
        from arxiv_tracker.cli import _collect_items

        cutoff = datetime(2026, 9, 26, tzinfo=timezone.utc)
        fetch.return_value = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        parse.return_value = [
            {"id": "http://arxiv.org/abs/old", "updated": "2026-09-20T00:00:00+00:00"},
            {"id": "http://arxiv.org/abs/fresh", "updated": "2026-09-28T00:00:00+00:00"},
        ]
        items = _collect_items(
            "q", want_new=15, cutoff=cutoff, seen_ids=set(), unique_only=True,
            sort_by="lastUpdatedDate", sort_order="descending", fallback_when_empty=False,
        )
        self.assertEqual([it["id"] for it in items], ["http://arxiv.org/abs/fresh"])
        fetch.assert_called_once()

    @patch("arxiv_tracker.cli.parse_feed")
    @patch("arxiv_tracker.cli.fetch_arxiv_feed")
    def test_fully_stale_page_does_not_request_the_next_page(self, fetch, parse):
        from arxiv_tracker.cli import _collect_items

        cutoff = datetime(2026, 9, 26, tzinfo=timezone.utc)
        fetch.return_value = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        parse.side_effect = [
            [{"id": f"http://arxiv.org/abs/{i}", "updated": "2026-09-20T00:00:00+00:00"} for i in range(25)],
            [{"id": "http://arxiv.org/abs/fresh", "updated": "2026-09-28T00:00:00+00:00"}],
        ]
        items = _collect_items(
            "q", want_new=15, cutoff=cutoff, seen_ids=set(), unique_only=True,
            sort_by="lastUpdatedDate", sort_order="descending", fallback_when_empty=False,
        )
        self.assertEqual(items, [])
        fetch.assert_called_once()

    @patch("arxiv_tracker.cli.fetch_arxiv_feed")
    def test_non_atom_response_is_not_treated_as_no_papers(self, fetch):
        from arxiv_tracker.cli import _collect_items

        fetch.return_value = "<html>bad gateway</html>"
        with self.assertRaises(RuntimeError):
            _collect_items(
                "q", want_new=15, cutoff=datetime(2026, 9, 26, tzinfo=timezone.utc),
                seen_ids=set(), unique_only=True, sort_by="lastUpdatedDate",
                sort_order="descending", fallback_when_empty=False,
            )

    # ---- insights ----

    def test_training_labels_are_normalized_to_fixed_vocabulary(self):
        self.assertEqual(normalize_training(["SFT", "GRPO reinforcement learning"]), ["SFT", "RL"])
        self.assertEqual(normalize_training("DPO + RLVR"), ["偏好优化", "RLVR"])
        self.assertEqual(normalize_training(["continued pretraining"]), ["继续预训练"])
        self.assertEqual(normalize_training(["new benchmark", "SFT", "RL"]), ["评测基准", "SFT"])
        self.assertEqual(normalize_training(["something odd"]), ["其他"])
        self.assertEqual(arxiv_base_id("http://arxiv.org/abs/2604.08698v3"), "2604.08698")

    @patch("arxiv_tracker.insights._chat_completions_request")
    def test_one_json_call_per_paper_and_cache_survives_new_versions(self, request):
        request.return_value = _llm_json()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"cache_path": os.path.join(tmp, "cache.json"), "workers": 4}
            first = analyze_papers([self.paper_a, self.paper_b], {"api_key": "k"}, cfg, log=lambda _: None)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(request.call_args.kwargs["response_format"], {"type": "json_object"})
            ins = first[self.paper_a["id"]]
            self.assertEqual(ins["source"], "llm")
            self.assertEqual(ins["tags"]["training"], ["RL"])
            self.assertEqual(ins["title_zh"], "代理工具使用的在线强化学习")

            v3 = dict(self.paper_a, id="https://arxiv.org/abs/2609.00001v3")
            second = analyze_papers([v3], {"api_key": "k"}, cfg, log=lambda _: None)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(second[v3["id"]]["source"], "cache")

            bumped = analyze_papers([v3], {"api_key": "k"}, dict(cfg, prompt_version=2), log=lambda _: None)
            self.assertEqual(request.call_count, 3)
            self.assertEqual(bumped[v3["id"]]["source"], "llm")

    @patch("arxiv_tracker.insights.time.sleep")
    @patch("arxiv_tracker.insights._chat_completions_request")
    def test_retry_then_fallback_without_caching_failures(self, request, _sleep):
        error = requests.exceptions.HTTPError(response=type("R", (), {"status_code": 429})())
        request.side_effect = [error, _llm_json(), "not json", "still not json", "{}"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cache.json")
            out = analyze_papers([self.paper_a, self.paper_b], {"api_key": "k"},
                                 {"cache_path": path, "workers": 1}, log=lambda _: None)
            cached = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(out[self.paper_a["id"]]["source"], "llm")
        self.assertEqual(out[self.paper_b["id"]]["source"], "fallback")
        self.assertEqual(out[self.paper_b["id"]]["tags"]["innovation"],
                         "We compare verifiable reward signals for long-horizon language agent tasks.")
        self.assertEqual(list(cached), ["2609.00001@p1"])

    @patch("arxiv_tracker.insights._chat_completions_request")
    def test_without_api_key_no_llm_calls(self, request):
        with patch.dict(os.environ, {}, clear=True):
            out = analyze_papers([self.paper_a], {"api_key_env": "MISSING_KEY"}, {}, log=lambda _: None)
        request.assert_not_called()
        self.assertEqual(out[self.paper_a["id"]]["source"], "fallback")

    # ---- renderers ----

    def test_site_is_one_dense_table_with_english_titles(self):
        with tempfile.TemporaryDirectory() as site_dir:
            result = generate_site(
                items=[self.paper_a, self.paper_b], insights=self.insights, site_dir=site_dir,
                group_names=["Agentic RL", "代码Agent", "代码预训练"], report_date="2026-09-30",
            )
            page = Path(result["index_path"]).read_text(encoding="utf-8")

        self.assertNotIn("今日研究观察", page)
        self.assertIn("max-width:1680px", page)
        for column in ("论文编号", "Title", "模型架构", "训练方法", "应用场景", "核心创新"):
            self.assertIn(f"<th>{column}</th>", page)
        self.assertEqual(page.count('class="paper-row"'), 2)
        self.assertIn('>Learning to Use Tools in Agents</a>', page)
        self.assertIn('<div class="title-zh">代理工具使用的在线强化学习</div>', page)
        self.assertNotIn('>代理工具使用的在线强化学习</a>', page)
        self.assertIn("<span>关键困难</span>工具反馈稀疏且延迟", page)
        self.assertIn('data-training="RL"', page)
        self.assertIn('data-groups="Agentic RL|代码Agent"', page)
        self.assertIn('id="training-filter"', page)
        self.assertIn(">2609.00001</a>", page)
        self.assertEqual(page.count("<summary>Abstract</summary><div>We study tool use"), 1)

    def test_site_empty_state(self):
        with tempfile.TemporaryDirectory() as site_dir:
            result = generate_site(items=[], insights={}, site_dir=site_dir, group_names=["Agentic RL"])
            page = Path(result["index_path"]).read_text(encoding="utf-8")
        self.assertIn("今日暂无新增论文", page)

    def test_email_is_compact_table_without_abstracts(self):
        body = render_email_html([self.paper_a, self.paper_b], self.insights,
                                 groups=["Agentic RL", "代码Agent"], page_url="https://x/", report_date="2026-09-30")
        self.assertIn("<table", body)
        self.assertIn("Learning to Use Tools in Agents", body)
        self.assertIn("用在线 rollout 的工具执行结果作为稀疏奖励", body)
        self.assertIn("困难</b> 工具反馈稀疏且延迟", body)
        self.assertNotIn("We study tool use", body)
        self.assertNotIn("代理工具使用的在线强化学习", body)
        self.assertIn("同时属于「Agentic RL」", body)
        self.assertEqual(body.count("工具反馈稀疏且延迟"), 1)
        self.assertIn("RL 1", body)
        self.assertIn("今日暂无新增命中", render_email_html([], {}))

    def _feishu_payload(self, items=None):
        items = items or [self.paper_a, self.paper_b]
        out = []
        for it in items:
            ins = self.insights.get(it["id"]) or fallback_insight(it)
            out.append({**it, "title_zh": ins["title_zh"], "tags": ins["tags"],
                        **{k: ins[k] for k in ("problem", "challenge", "solution", "results", "future")}})
        return {"report_date": "2026-09-30", "groups": ["Agentic RL", "代码Agent"], "items": out}

    def test_feishu_uses_english_titles_and_structured_fields(self):
        markdown = build_markdown(self._feishu_payload())
        self.assertIn("[Learning to Use Tools in Agents](https://arxiv.org/abs/2609.00001v2)", markdown)
        self.assertNotIn("代理工具使用的在线强化学习", markdown)
        self.assertIn("RL · LLM + tool harness · 工具调用", markdown)
        for label in ("核心问题", "关键困难", "解决方案", "未来方向"):
            self.assertIn(f"**{label}**", markdown)
        self.assertIn("（见「Agentic RL」）", markdown)
        self.assertNotIn("今日观察", markdown)
        self.assertIn("训练方法：RL 1", markdown)

    def test_feishu_degrades_detail_before_truncating(self):
        many = [dict(self.paper_a, id=f"https://arxiv.org/abs/2609.{i:05d}", groups=["Agentic RL"]) for i in range(60)]
        self.insights.update({it["id"]: self.insights[self.paper_a["id"]] for it in many})
        markdown = build_markdown(self._feishu_payload(many))
        self.assertLessEqual(len(markdown), MAX_CHARS)
        self.assertIn("打开完整日报", markdown)
        self.assertEqual(len(re.findall(r"\[Learning to Use Tools in Agents\]", markdown)), 60)

    def test_feishu_empty_digest(self):
        lark = build_markdown({"items": [], "groups": ["Agentic RL"]})
        self.assertIn("今天没有新的命中", lark)

    def test_markdown_attachment_has_table_and_structured_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = save_markdown([self.paper_a], tmp, insights=self.insights)
            text = Path(path).read_text(encoding="utf-8")
        self.assertIn("| 论文编号 | Title | 方向 | 模型架构 | 训练方法 | 应用场景 | 核心创新 |", text)
        self.assertIn("**关键困难**：工具反馈稀疏且延迟", text)


if __name__ == "__main__":
    unittest.main()
