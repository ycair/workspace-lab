from __future__ import annotations

import os
import tempfile
import unittest

from engine.models import ActionResult
from engine.store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "test.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_action_and_reset(self):
        eid = self.store.create_experiment("t", "quote", "mock", "測試企業")
        self.assertEqual(self.store.get_experiment(eid)["company"], "測試企業")
        result = ActionResult(True, "success", "Gmail", "sales", "customer", "sent",
                              payload={"url": "https://docs.google.com/document/d/test"})
        self.store.add_action(eid, "sales", "SALES", result)
        actions = self.store.list_actions(eid)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["payload"]["url"], "https://docs.google.com/document/d/test")
        self.store.reset()
        self.assertIsNone(self.store.latest_experiment())
        self.assertEqual(self.store.list_actions(eid), [])


if __name__ == "__main__":
    unittest.main()
