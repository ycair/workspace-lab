from __future__ import annotations

import threading
import time
from typing import Any

from .models import ActionResult, now
from .personas import PERSONAS, persona_for
from .scenarios import get_scenario
from .store import Store


class Simulator:
    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.experiment_id: int | None = None
        self.scenario_key = "quote"
        self.mode = "mock"
        self.status = "idle"
        self.step_index = 0
        self.delay = 1.2
        self.error = ""
        self.started_monotonic = 0.0
        self.persona_status = {p.id: "standby" for p in PERSONAS}

    # ---------- lifecycle ----------
    def load_latest(self) -> None:
        exp = self.store.latest_experiment()
        if not exp:
            return
        self.experiment_id = int(exp["id"])
        self.scenario_key = exp.get("scenario", "quote")
        self.mode = exp.get("mode", "mock")
        self.status = exp.get("status", "done")
        actions = self.store.list_actions(self.experiment_id)
        self.step_index = min(len(actions), len(get_scenario(self.scenario_key)["steps"]))
        for p in PERSONAS:
            related = [a for a in actions if a["actor"] == p.id]
            if related:
                self.persona_status[p.id] = "error" if any(a["status"] == "error" for a in related) else "done"
        if self.status == "running":
            self.status = "paused"
            self.store.update_experiment(self.experiment_id, status="paused")

    def start(self, scenario_key: str, mode: str, adapter: Any, delay: float = 1.2) -> dict[str, Any]:
        self.stop()
        self.scenario_key = scenario_key if scenario_key in ("quote", "schedule", "quality") else "quote"
        self.mode = mode
        self.delay = max(0.2, min(delay, 5.0))
        self.step_index = 0
        self.error = ""
        self.status = "running"
        self.persona_status = {p.id: "standby" for p in PERSONAS}
        self.stop_event.clear()
        self.started_monotonic = time.monotonic()
        self.experiment_id = self.store.create_experiment(
            f"{get_scenario(self.scenario_key)['name']} · {time.strftime('%H:%M:%S')}",
            self.scenario_key, mode,
        )
        self.thread = threading.Thread(target=self._run, args=(adapter,), daemon=True)
        self.thread.start()
        return self.state()

    def pause(self) -> dict[str, Any]:
        if self.status == "running":
            self.status = "paused"
            self.store.update_experiment(self.experiment_id, status="paused")
        return self.state()

    def resume(self) -> dict[str, Any]:
        if self.status == "paused":
            self.status = "running"
            self.store.update_experiment(self.experiment_id, status="running")
        return self.state()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None
        if self.status == "running":
            self.status = "paused"

    def reset(self) -> dict[str, Any]:
        self.stop()
        self.store.reset()
        self.experiment_id = None
        self.status = "idle"
        self.step_index = 0
        self.error = ""
        self.persona_status = {p.id: "standby" for p in PERSONAS}
        return self.state()

    # ---------- execution ----------
    def _run(self, adapter: Any) -> None:
        scenario = get_scenario(self.scenario_key)
        steps = scenario["steps"]
        errors = 0
        while not self.stop_event.is_set():
            if self.status == "paused":
                time.sleep(0.2)
                continue
            if self.step_index >= len(steps):
                break
            step = steps[self.step_index]
            persona = persona_for(step.get("actor", "admin"))
            with self.lock:
                self.persona_status[persona.id] = "running"
            payload = dict(step)
            payload["actor"] = persona.id
            payload["actor_email"] = persona.email
            try:
                result = adapter.run(payload)
            except Exception as exc:  # noqa: BLE001
                result = ActionResult(False, "error", step.get("tool", "Workspace"), persona.id,
                                      step.get("target", ""), step.get("summary", ""), error=str(exc))
            if not result.ok:
                errors += 1
            self.store.add_action(
                self.experiment_id, persona.id, step.get("agent", "DIRECTOR"), result
            )
            with self.lock:
                self.persona_status[persona.id] = "done" if result.ok else "error"
            self.step_index += 1
            time.sleep(self.delay)
        if self.stop_event.is_set():
            return
        # finish
        duration = max(0.1, time.monotonic() - self.started_monotonic)
        for key, value, unit in scenario.get("metrics", []):
            self.store.add_metric(self.experiment_id, key, value, unit)
        self.store.add_metric(self.experiment_id, "actions_total", self.step_index, "count")
        self.store.add_metric(self.experiment_id, "errors_total", errors, "count")
        self.store.add_metric(self.experiment_id, "duration_seconds", round(duration, 1), "s")
        ok = errors == 0
        self.status = "done" if ok else "error"
        self.store.update_experiment(
            self.experiment_id, status=self.status,
            ended_at=now(),
            error="" if ok else f"{errors} 個動作失敗",
        )

    # ---------- events ----------
    def inject_event(self, type_: str, payload: str) -> dict[str, Any]:
        if not self.experiment_id:
            return self.state()
        self.store.add_event(self.experiment_id, type_, payload)
        result = ActionResult(
            True, "success", "Event", "director", type_,
            f"事件注入：{type_} — {payload}", external_id=f"event-{type_}"
        )
        self.store.add_action(self.experiment_id, "admin", "DIRECTOR", result)
        return self.state()

    # ---------- state ----------
    def state(self) -> dict[str, Any]:
        scenario = get_scenario(self.scenario_key)
        experiment = self.store.get_experiment(self.experiment_id) if self.experiment_id else None
        actions = self.store.list_actions(self.experiment_id) if self.experiment_id else []
        metrics = self.store.list_metrics(self.experiment_id) if self.experiment_id else []
        events = self.store.list_events(self.experiment_id) if self.experiment_id else []
        personas = []
        for p in PERSONAS:
            d = p.as_dict()
            d["status"] = self.persona_status.get(p.id, "standby")
            personas.append(d)
        return {
            "experiment": experiment,
            "status": self.status,
            "mode": self.mode,
            "scenario": {
                "id": scenario["id"], "name": scenario["name"],
                "pain": scenario["pain"], "gain": scenario["gain"],
                "description": scenario["description"],
                "total_steps": len(scenario["steps"]),
            },
            "step_index": self.step_index,
            "total_steps": len(scenario["steps"]),
            "actions": actions,
            "metrics": metrics,
            "events": events,
            "personas": personas,
            "error": self.error,
        }
