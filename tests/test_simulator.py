from __future__ import annotations

import os
import tempfile
import time
import unittest

from engine.simulator import Simulator
from engine.store import Store
from engine.workspace import MockAdapter


class SimulatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "lab.db"))
        self.sim = Simulator(self.store)

    def tearDown(self):
        self.sim.stop()
        self.store.close()
        self.tmp.cleanup()

    def test_mock_quote_runs_to_done(self):
        self.sim.start("quote", "mock", MockAdapter(), delay=0.2, company="晟銘金屬")
        for _ in range(60):
            if self.sim.status in ("done", "error"):
                break
            time.sleep(0.1)
        self.assertEqual(self.sim.status, "done")
        self.assertEqual(self.sim.state()["company"], "晟銘金屬")
        actions = self.store.list_actions(self.sim.experiment_id)
        self.assertEqual(len(actions), 10)
        self.assertTrue(all(a["status"] == "success" for a in actions))
        self.assertTrue(any("晟銘金屬" in a["target"] for a in actions))
        self.assertTrue(any(a["tool"] == "Docs" for a in actions))
        self.assertTrue(any(a["tool"] == "Slides" for a in actions))
        self.assertTrue(any("詢價" in a["target"] and "晟銘金屬" in a["target"] for a in actions))
        self.assertTrue(any(a["tool"] == "Drive" and a["status"] == "success" for a in actions))
        metrics = {m["key"]: m["value"] for m in self.store.list_metrics(self.sim.experiment_id)}
        self.assertEqual(metrics["quote_result_hours"], 4.0)
        self.assertEqual(metrics["errors_total"], 0.0)

    def test_scenario_renders_company_name(self):
        from engine.scenarios import get_scenario
        sc = get_scenario("quote", "晟銘金屬")
        titles = [s.get("title", "") for s in sc["steps"] if s.get("title")]
        self.assertTrue(any("晟銘金屬" in t for t in titles))
        self.assertFalse(any("YC-" in t for t in titles))

    def test_inject_event(self):
        self.sim.start("quality", "mock", MockAdapter(), delay=0.2)
        time.sleep(0.3)
        self.sim.inject_event("urgent_order", "急單 300 件")
        events = self.store.list_events(self.sim.experiment_id)
        self.assertEqual(events[0]["type"], "urgent_order")

    def test_reset(self):
        self.sim.start("schedule", "mock", MockAdapter(), delay=0.2)
        time.sleep(0.3)
        self.sim.reset()
        self.assertEqual(self.sim.status, "idle")
        self.assertIsNone(self.store.latest_experiment())


if __name__ == "__main__":
    unittest.main()
