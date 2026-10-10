"""Automatic HVAC tender generation: deterministic per seed, and every package self-checks."""

import tempfile
import unittest
from pathlib import Path

from equans_bid.tools.scenario_generator import build_and_verify, generate_scenario


class TestScenarioGenerator(unittest.TestCase):
	def test_same_seed_same_scenario(self):
		self.assertEqual(generate_scenario(42), generate_scenario(42))
		self.assertNotEqual(generate_scenario(42), generate_scenario(43))

	def test_scenario_uses_only_catalogue_products_and_trade_systems(self):
		s = generate_scenario(7, systems=4)
		self.assertEqual(len(s["systems"]), 4)
		self.assertTrue(all(sys["code"].startswith("244.") for sys in s["systems"]))
		golden = [
			v for sys in s["systems"] for b in sys["positions"] for v in b["variants"] if v.get("golden")
		]
		self.assertGreater(len(golden), 8)
		self.assertIn("SYNTHETIC", s["project"]["name"])

	def test_generated_packages_pass_the_self_check(self):
		out = Path(tempfile.mkdtemp())
		for seed in range(1, 6):
			with self.subTest(seed=seed):
				manifest = build_and_verify(generate_scenario(seed), out / f"seed{seed}")
				self.assertTrue(manifest["self_check"].startswith(f"{manifest['golden_positions']}/"))
