import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select

from . import database as db
from . import models as pydantic_models
from .db import models as db_models
from .websockets import broadcast_ws


@dataclass
class InactivityState:
    """Tracks the runtime state for a single device_inactivity trigger instance."""

    # Whether the timer is currently running (waiting for inactivity timeout).
    armed: bool = False
    # The asyncio Task running asyncio.sleep(timeout_s). Cancelled on new activity.
    timer_task: asyncio.Task | None = None
    # The asyncio Task running the cooldown sleep. Cancelled on automation delete/update.
    cooldown_task: asyncio.Task | None = None
    # Unix timestamp until which activity is ignored after a cooldown-mode firing.
    cooldown_until: float = 0.0
    # Set to True after the first firing when rearm_mode == "never".
    permanently_disarmed: bool = False


class AutomationManager:
    def __init__(self, db_manager: db.DatabaseManager | None = None):
        self.db_manager = db_manager
        self.automations: list[pydantic_models.IRAutomation] = []
        self.multi_press_state = {}
        self.sequence_state = {}
        self.sequence_last_time = {}
        # Keyed by (automation_id, trigger_index) for device_inactivity triggers.
        self.inactivity_states: dict[tuple[str, int], InactivityState] = {}
        self.queue = asyncio.Queue()
        self.worker_task = None
        self.mqtt_manager = None
        self.running_automations: dict[str, int] = {}
        self.automation_locks: dict[str, asyncio.Lock] = {}
        self.logger = logging.getLogger(__name__)
        self.settings = None
        self.state_manager = None

    def set_mqtt_manager(self, manager):
        self.mqtt_manager = manager

    def set_logger(self, logger):
        if logger is None:
            raise ValueError("logger must not be None")
        self.logger = logger

    def set_state_manager(self, manager):
        self.state_manager = manager

    def _cancel_inactivity_timers_for(self, auto_id: str) -> None:
        """Cancel and remove all inactivity timer state for the given automation ID."""
        keys_to_remove = [k for k in self.inactivity_states if k[0] == auto_id]
        for k in keys_to_remove:
            state = self.inactivity_states.pop(k)
            if state.timer_task and not state.timer_task.done():
                state.timer_task.cancel()
            if state.cooldown_task and not state.cooldown_task.done():
                state.cooldown_task.cancel()

    async def load(self, settings: Any = None):
        async with db.unit_of_work() as uow:
            try:
                stmt = select(db_models.IRAutomation).order_by(db_models.IRAutomation.ordering)
                result = await uow.session.execute(stmt)
                automations = result.scalars().all()
                self.automations = [pydantic_models.IRAutomation.model_validate(a) for a in automations]
                self.logger.info("Loaded %s automations.", len(self.automations))
            except Exception as e:
                self.logger.error("Failed to load automations: %s", e, exc_info=True)
                self.automations = []

        # Start inactivity timers for triggers configured to fire without waiting
        # for the first activity event (require_initial_activity == False).
        for a in self.automations:
            if not a.enabled:
                continue
            for t_idx, t in enumerate(a.triggers):
                if t.type == "device_inactivity" and not t.require_initial_activity:
                    state_key = (a.id, t_idx)
                    state = InactivityState(armed=True)
                    self.inactivity_states[state_key] = state
                    state.timer_task = asyncio.create_task(self._inactivity_timer(a.id, t_idx, t.timeout_s))
                    self.logger.info(
                        "Automation '%s' trigger %s: started inactivity timer on load (no initial activity required).",
                        a.name,
                        t_idx,
                    )

    def save(self):
        pass

    async def add_automation(self, automation: pydantic_models.IRAutomation):
        async with db.unit_of_work() as uow:
            try:
                # Get max ordering
                max_ordering = await uow.session.execute(select(func.max(db_models.IRAutomation.ordering)))
                max_ordering = max_ordering.scalar_one_or_none() or 0

                automation.ordering = max_ordering + 1
                db_auto = db_models.IRAutomation(**automation.model_dump())
                uow.save(db_auto)
                await uow.commit()
                self.automations.append(automation)
            except Exception as e:
                self.logger.error("Failed to add automation: %s", e, exc_info=True)
                raise

    async def update_automation(self, automation: pydantic_models.IRAutomation):
        async with db.unit_of_work() as uow:
            try:
                db_auto = await uow.get_by_id(db_models.IRAutomation, automation.id)
                if not db_auto:
                    raise ValueError(f"Automation with id {automation.id} not found")

                for key, value in automation.model_dump().items():
                    setattr(db_auto, key, value)

                await uow.commit()

                # Update in-memory list
                idx = next((i for i, a in enumerate(self.automations) if a.id == automation.id), -1)
                if idx != -1:
                    self.automations[idx] = automation

                # Cancel all running inactivity timers – trigger config may have changed
                self._cancel_inactivity_timers_for(automation.id)

                # Restart timers for triggers that fire without waiting for first activity,
                # but only if the automation is still enabled after the update.
                if automation.enabled:
                    for t_idx, t in enumerate(automation.triggers):
                        if t.type == "device_inactivity" and not t.require_initial_activity:
                            state = InactivityState(armed=True)
                            self.inactivity_states[(automation.id, t_idx)] = state
                            state.timer_task = asyncio.create_task(self._inactivity_timer(automation.id, t_idx, t.timeout_s))
                            self.logger.info(
                                "Automation '%s' trigger %s: restarted inactivity timer after update.",
                                automation.name,
                                t_idx,
                            )
            except Exception as e:
                self.logger.error("Failed to update automation: %s", e, exc_info=True)
                raise

    async def delete_automation(self, auto_id: str):
        async with db.unit_of_work() as uow:
            try:
                record = await uow.get_by_id(db_models.IRAutomation, auto_id)
                if record:
                    await uow.delete(record)
                    await uow.commit()
                    self.automations = [a for a in self.automations if a.id != auto_id]

                    # Cleanup state
                    self.automation_locks.pop(auto_id, None)
                    self.running_automations.pop(auto_id, None)

                    # Cleanup multi/sequence trigger state
                    for state_dict in [self.multi_press_state, self.sequence_state, self.sequence_last_time]:
                        keys_to_remove = [k for k in state_dict if k.startswith(f"{auto_id}_")]
                        for k in keys_to_remove:
                            state_dict.pop(k, None)

                    # Cancel and remove all inactivity timer tasks for this automation
                    self._cancel_inactivity_timers_for(auto_id)

            except Exception as e:
                self.logger.error("Failed to delete automation: %s", e, exc_info=True)
                raise

    async def reorder(self, new_order_ids: list[str]):
        async with db.unit_of_work() as uow:
            try:
                for i, auto_id in enumerate(new_order_ids):
                    db_auto = await uow.get_by_id(db_models.IRAutomation, auto_id)
                    if db_auto:
                        db_auto.ordering = i

                await uow.commit()

                # Reorder in-memory list
                mapping = {a.id: a for a in self.automations}
                new_list = []
                for i, aid in enumerate(new_order_ids):
                    if aid in mapping:
                        auto = mapping[aid]
                        auto.ordering = i
                        new_list.append(auto)

                existing_ids = set(new_order_ids)
                for a in self.automations:
                    if a.id not in existing_ids:
                        a.ordering = len(new_list)
                        new_list.append(a)

                self.automations = new_list

            except Exception as e:
                self.logger.error("Failed to reorder automations: %s", e, exc_info=True)
                raise

    def start(self):
        if not self.worker_task:
            self.worker_task = asyncio.create_task(self._process_loop())
            self.logger.info("Automation worker started.")

    def stop(self):
        if self.worker_task:
            self.worker_task.cancel()
            self.logger.info("Automation worker stopped.")

        # Cancel all pending inactivity timers and cooldown tasks
        for state in self.inactivity_states.values():
            if state.timer_task and not state.timer_task.done():
                state.timer_task.cancel()
            if state.cooldown_task and not state.cooldown_task.done():
                state.cooldown_task.cancel()
        self.inactivity_states.clear()

    async def process_ir_event(self, matches: list[tuple], state_manager: Any, send_ir_func: Callable):
        self.queue.put_nowait(
            {
                "type": "ir_event",
                "matches": matches,
                "state_manager": state_manager,
                "send_ir_func": send_ir_func,
                "timestamp": time.time(),
            }
        )

    async def trigger_from_ha(self, auto_id: str, source: str = "Home Assistant"):
        self.queue.put_nowait(
            {
                "type": "ha_trigger",
                "auto_id": auto_id,
                "source": source,
                "timestamp": time.time(),
            }
        )

    async def _process_loop(self):
        while True:
            try:
                # Use a base timeout to allow for periodic checks
                timeout = self._get_next_timeout() or 5.0

                try:
                    event = await asyncio.wait_for(self.queue.get(), timeout=timeout)
                    if event["type"] == "ir_event":
                        await self._handle_ir_event(event)
                    elif event["type"] == "ha_trigger":
                        await self._handle_ha_trigger(event)
                    self.queue.task_done()
                except TimeoutError:
                    pass  # Expected timeout for periodic checks

                await self._check_timeouts()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in automation loop: %s", e, exc_info=True)
                await asyncio.sleep(1)

    async def _handle_ha_trigger(self, event):
        auto_id = event["auto_id"]
        source = event.get("source", "Home Assistant")
        automation = next((a for a in self.automations if a.id == auto_id), None)
        if automation and automation.enabled:
            self.logger.info("Triggering automation '%s' from %s.", automation.name, source)
            # We need to get the global send_ir_func
            if self.mqtt_manager and self.state_manager:
                asyncio.create_task(self.run_automation(automation, self.state_manager, self.mqtt_manager.send_ir_code))
        else:
            self.logger.warning("Received trigger for unknown or disabled automation ID: %s", auto_id)

    async def _handle_ir_event(self, event):
        matches_list = event["matches"]
        state_manager = event["state_manager"]
        send_ir_func = event["send_ir_func"]
        now = event["timestamp"]

        matches = []

        for a in self.automations:
            if not a.enabled:
                continue

            triggered = False

            # Helper to check if a specific device/button is in the matches list (OR logic)
            def is_triggered(dev_id, btn_id):
                for m_dev, m_btn in matches_list:
                    if m_dev == dev_id and m_btn == btn_id:
                        return True
                return False

            for t_idx, t in enumerate(a.triggers):
                state_key = f"{a.id}_{t_idx}"

                if t.type == "single":
                    if is_triggered(t.device_id, t.button_id):
                        triggered = True

                elif t.type == "multi":
                    if self._process_multi_trigger(a, t, t_idx, state_key, is_triggered, now):
                        triggered = True

                elif t.type == "sequence":
                    if self._process_sequence_trigger(a, t, t_idx, state_key, is_triggered, now):
                        triggered = True

            if triggered and self.are_conditions_met(a):
                matches.append(a)

        for automation in matches:
            self.logger.info("Triggering automation: %s", automation.name)
            asyncio.create_task(self.run_automation(automation, state_manager, send_ir_func))

    def _process_multi_trigger(self, a, t, t_idx, state_key, is_triggered_func, now) -> bool:
        triggered = False
        is_target = is_triggered_func(t.device_id, t.button_id)

        if is_target:
            history = self.multi_press_state.get(state_key, [])
            # Clean old presses
            window_sec = t.window_ms / 1000.0
            history = [ts for ts in history if now - ts <= window_sec]

            history.append(now)
            self.multi_press_state[state_key] = history

            # Broadcast Progress
            self.logger.info(
                "Automation '%s' trigger %s multi-press: %s/%s",
                a.name,
                t_idx,
                len(history),
                t.count,
            )
            asyncio.create_task(
                broadcast_ws(
                    {
                        "type": "trigger_progress",
                        "id": a.id,
                        "trigger_index": t_idx,
                        "current": len(history),
                        "target": t.count,
                    }
                )
            )

            if len(history) >= t.count:
                triggered = True
                self.multi_press_state[state_key] = []  # Reset after trigger
                # Broadcast Reset with delay
                asyncio.create_task(self._delayed_progress_reset(state_key, t.count, "multi", a.id, t_idx))
        elif t.reset_on_other_input:
            # Received a known code that is NOT the target, and strict mode is on
            if self.multi_press_state.get(state_key):
                self.multi_press_state[state_key] = []
                self.logger.info(
                    "Automation '%s' trigger %s multi-press reset: Other button pressed.",
                    a.name,
                    t_idx,
                )
                asyncio.create_task(
                    broadcast_ws(
                        {
                            "type": "trigger_progress",
                            "id": a.id,
                            "trigger_index": t_idx,
                            "current": 0,
                            "target": t.count,
                        }
                    )
                )
        return triggered

    def _process_sequence_trigger(self, a, t, t_idx, state_key, is_triggered_func, now) -> bool:
        seq = t.sequence
        if not seq:
            return False

        current_idx = self.sequence_state.get(state_key, 0)
        last_time = self.sequence_last_time.get(state_key, 0)

        idx = current_idx

        # Reset sequence if too much time passed between presses
        if idx > 0 and (now - last_time) > (t.window_ms / 1000.0):
            idx = 0

        # Prevent index out of bounds if state is stale or sequence is empty
        if idx >= len(seq):
            idx = 0

        target = seq[idx]
        matched = False

        # Check if ANY matched button corresponds to the target
        if is_triggered_func(target.device_id, target.button_id):
            idx += 1
            matched = True

        if not matched and t.reset_on_other_input:
            # Wrong button, reset. Check if it matches start of sequence to allow immediate restart
            idx = 0
            target = seq[0]

            # Check if ANY matched button corresponds to the start
            if is_triggered_func(target.device_id, target.button_id):
                idx = 1
                matched = True

            if idx == 0 and current_idx > 0:
                self.logger.info(
                    "Automation '%s' trigger %s sequence reset: Wrong button pressed.",
                    a.name,
                    t_idx,
                )

        # Update State
        if idx != current_idx or matched:
            self.sequence_state[state_key] = idx
            self.sequence_last_time[state_key] = now

        # Broadcast if changed
        if idx != current_idx:
            self.logger.info(
                "Automation '%s' trigger %s sequence step: %s/%s",
                a.name,
                t_idx,
                idx,
                len(seq),
            )
            asyncio.create_task(
                broadcast_ws(
                    {
                        "type": "trigger_progress",
                        "id": a.id,
                        "trigger_index": t_idx,
                        "current": idx,
                        "target": len(seq),
                    }
                )
            )

        if idx >= len(seq):
            self.sequence_state[state_key] = 0
            # Broadcast Reset with delay
            asyncio.create_task(self._delayed_progress_reset(state_key, len(seq), "sequence", a.id, t_idx))
            return True
        return False

    async def notify_device_activity(
        self,
        device_id: str,
        button_id: str,
        source: str = "received",
        source_automation_id: str | None = None,
    ) -> None:
        """Called whenever a device button is received or sent.

        Updates the inactivity timer for every device_inactivity trigger that is
        watching the given device.  Each qualifying activity event cancels the
        current sleep and starts a fresh one.

        Args:
            device_id: ID of the device that produced the event.
            button_id: ID of the button that was pressed/sent.
            source: "received" (IR code arrived) or "sent" (IR code transmitted).
            source_automation_id: The automation that caused the send, if any.
                Used to suppress self-generated activity when ignore_own_actions
                is True.
        """
        now = time.time()

        for a in self.automations:
            if not a.enabled:
                continue

            for t_idx, t in enumerate(a.triggers):
                if t.type != "device_inactivity":
                    continue
                if t.device_id != device_id:
                    continue

                # Respect the watch_mode filter
                if t.watch_mode == "received" and source != "received":
                    continue
                if t.watch_mode == "sent" and source != "sent":
                    continue

                # Skip if this automation generated the event itself and the
                # user asked us to ignore its own actions
                if t.ignore_own_actions and source == "sent" and source_automation_id == a.id:
                    self.logger.debug(
                        "Automation '%s' trigger %s: ignoring own ir_send as activity.",
                        a.name,
                        t_idx,
                    )
                    continue

                # Check the button whitelist
                if t.button_filter is not None and button_id not in t.button_filter:
                    continue

                # Check the button blacklist
                if t.button_exclude is not None and button_id in t.button_exclude:
                    continue

                state_key = (a.id, t_idx)
                state = self.inactivity_states.setdefault(state_key, InactivityState())

                # Skip permanently disarmed triggers (rearm_mode == "never" after firing)
                if state.permanently_disarmed:
                    continue

                # Skip if still in cooldown
                if state.cooldown_until > 0 and now < state.cooldown_until:
                    remaining = state.cooldown_until - now
                    self.logger.debug(
                        "Automation '%s' trigger %s: in cooldown (%.1fs remaining), ignoring activity.",
                        a.name,
                        t_idx,
                        remaining,
                    )
                    continue

                # Cancel any running timer so the countdown resets
                if state.timer_task and not state.timer_task.done():
                    state.timer_task.cancel()
                    state.timer_task = None

                # Arm the timer
                state.armed = True
                armed_at = now
                state.timer_task = asyncio.create_task(self._inactivity_timer(a.id, t_idx, t.timeout_s))

                self.logger.debug(
                    "Automation '%s' trigger %s: activity on button '%s' (%s), timer armed for %.1fs.",
                    a.name,
                    t_idx,
                    button_id,
                    source,
                    t.timeout_s,
                )

                # Broadcast the armed state so the UI can show a countdown
                asyncio.create_task(
                    broadcast_ws(
                        {
                            "type": "inactivity_state",
                            "id": a.id,
                            "trigger_index": t_idx,
                            "state": "armed",
                            "timeout_s": t.timeout_s,
                            "armed_at": armed_at,
                        }
                    )
                )

    async def _inactivity_timer(self, auto_id: str, trigger_idx: int, timeout_s: float) -> None:
        """Sleeps for timeout_s then fires the automation.

        If cancelled (because new activity arrived), it exits silently so the
        caller can create a fresh timer.
        """
        try:
            await asyncio.sleep(timeout_s)
        except asyncio.CancelledError:
            # Timer was reset by a new activity event – nothing to do
            return

        automation = next((a for a in self.automations if a.id == auto_id), None)
        if not automation or not automation.enabled:
            return

        if trigger_idx >= len(automation.triggers):
            return
        trigger = automation.triggers[trigger_idx]
        if trigger.type != "device_inactivity":
            return

        state_key = (auto_id, trigger_idx)
        state = self.inactivity_states.get(state_key)
        if not state or not state.armed:
            return

        state.armed = False
        state.timer_task = None

        self.logger.info(
            "Automation '%s' trigger %s: inactivity timeout reached, firing automation.",
            automation.name,
            trigger_idx,
        )

        # Broadcast the fired event so the UI gives immediate feedback
        await broadcast_ws(
            {
                "type": "inactivity_state",
                "id": auto_id,
                "trigger_index": trigger_idx,
                "state": "fired",
            }
        )

        # Execute the automation
        if self.mqtt_manager and self.state_manager:
            asyncio.create_task(self.run_automation(automation, self.state_manager, self.mqtt_manager.send_ir_code))

        # Handle re-arm behaviour
        if trigger.rearm_mode == "never":
            state.permanently_disarmed = True
            await broadcast_ws(
                {
                    "type": "inactivity_state",
                    "id": auto_id,
                    "trigger_index": trigger_idx,
                    "state": "idle",
                }
            )
        elif trigger.rearm_mode == "cooldown" and trigger.cooldown_s > 0:
            state.cooldown_until = time.time() + trigger.cooldown_s
            await broadcast_ws(
                {
                    "type": "inactivity_state",
                    "id": auto_id,
                    "trigger_index": trigger_idx,
                    "state": "cooldown",
                    "cooldown_s": trigger.cooldown_s,
                    "cooldown_until": state.cooldown_until,
                }
            )
            # Schedule a notification when the cooldown window closes and track the
            # task so it can be cancelled if the automation is deleted or updated.
            state.cooldown_task = asyncio.create_task(self._inactivity_cooldown_end(auto_id, trigger_idx, trigger.cooldown_s))
        else:
            # rearm_mode == "always" (or "cooldown" with cooldown_s == 0):
            # go back to idle and wait for the next activity event
            await broadcast_ws(
                {
                    "type": "inactivity_state",
                    "id": auto_id,
                    "trigger_index": trigger_idx,
                    "state": "idle",
                }
            )

    async def _inactivity_cooldown_end(self, auto_id: str, trigger_idx: int, cooldown_s: float) -> None:
        """Waits for the cooldown to expire, then broadcasts idle so the UI updates."""
        await asyncio.sleep(cooldown_s)

        state_key = (auto_id, trigger_idx)
        state = self.inactivity_states.get(state_key)
        if state and time.time() >= state.cooldown_until:
            state.cooldown_until = 0.0
            await broadcast_ws(
                {
                    "type": "inactivity_state",
                    "id": auto_id,
                    "trigger_index": trigger_idx,
                    "state": "idle",
                }
            )

    def are_conditions_met(self, automation: pydantic_models.IRAutomation) -> bool:
        # Future feature: Implement real condition logic.
        # This is a placeholder for future features like time of day, state checks, etc.
        # For now, it's a no-op that allows all triggers.
        self.logger.debug("Condition check for automation '%s' is a stub and always returns True.", automation.name)
        return True

    async def _delayed_progress_reset(self, state_key: str, target: int, trigger_type: str, auto_id: str, t_idx: int):
        await asyncio.sleep(2.0)

        should_reset = False
        if trigger_type == "sequence":
            if self.sequence_state.get(state_key, 0) == 0:
                should_reset = True
        elif trigger_type == "multi":
            if not self.multi_press_state.get(state_key):
                should_reset = True

        if should_reset:
            await broadcast_ws(
                {
                    "type": "trigger_progress",
                    "id": auto_id,
                    "trigger_index": t_idx,
                    "current": 0,
                    "target": target,
                }
            )

    def _get_next_timeout(self) -> float | None:
        now = time.time()
        min_remaining = None

        # Check Multi Press
        for key, history in self.multi_press_state.items():
            if not history:
                continue
            try:
                auto_id, t_idx = key.rsplit("_", 1)
                t_idx = int(t_idx)
            except ValueError:
                continue

            auto = next((a for a in self.automations if a.id == auto_id), None)
            if not auto or t_idx >= len(auto.triggers):
                continue
            trigger = auto.triggers[t_idx]

            # Expiration based on oldest press in window
            expires_at = history[0] + (trigger.window_ms / 1000.0)
            remaining = expires_at - now
            if min_remaining is None or remaining < min_remaining:
                min_remaining = remaining

        # Check Sequence
        for key, idx in self.sequence_state.items():
            if idx == 0:
                continue
            try:
                auto_id, t_idx = key.rsplit("_", 1)
                t_idx = int(t_idx)
            except ValueError:
                continue

            auto = next((a for a in self.automations if a.id == auto_id), None)
            if not auto or t_idx >= len(auto.triggers):
                continue
            trigger = auto.triggers[t_idx]

            last_time = self.sequence_last_time.get(key, 0)
            expires_at = last_time + (trigger.window_ms / 1000.0)
            remaining = expires_at - now
            if min_remaining is None or remaining < min_remaining:
                min_remaining = remaining

        if min_remaining is not None:
            return max(0.1, min_remaining)
        return None

    async def _check_timeouts(self):
        now = time.time()

        # Multi Press Timeouts
        for key, history in list(self.multi_press_state.items()):
            if not history:
                continue
            try:
                auto_id, t_idx = key.rsplit("_", 1)
                t_idx = int(t_idx)
            except ValueError:
                continue

            auto = next((a for a in self.automations if a.id == auto_id), None)
            if not auto or t_idx >= len(auto.triggers):
                continue
            trigger = auto.triggers[t_idx]

            window_sec = trigger.window_ms / 1000.0
            valid_history = [t for t in history if now - t <= window_sec]

            if len(valid_history) != len(history):
                self.multi_press_state[key] = valid_history
                await broadcast_ws(
                    {
                        "type": "trigger_progress",
                        "id": auto_id,
                        "trigger_index": t_idx,
                        "current": len(valid_history),
                        "target": trigger.count,
                    }
                )

        # Sequence Timeouts
        for key, idx in list(self.sequence_state.items()):
            if idx == 0:
                continue
            try:
                auto_id, t_idx = key.rsplit("_", 1)
                t_idx = int(t_idx)
            except ValueError:
                continue

            auto = next((a for a in self.automations if a.id == auto_id), None)
            if not auto or t_idx >= len(auto.triggers):
                continue
            trigger = auto.triggers[t_idx]

            last_time = self.sequence_last_time.get(key, 0)
            if (now - last_time) > (trigger.window_ms / 1000.0):
                self.sequence_state[key] = 0
                self.logger.info(
                    "Automation '%s' trigger %s sequence reset: Timeout.",
                    auto.name,
                    t_idx,
                )
                await broadcast_ws(
                    {
                        "type": "trigger_progress",
                        "id": auto_id,
                        "trigger_index": t_idx,
                        "current": 0,
                        "target": len(trigger.sequence),
                    }
                )

    async def run_automation(self, automation: pydantic_models.IRAutomation, state_manager: Any, send_ir_func: Callable):
        if not automation.allow_parallel:
            if automation.id not in self.automation_locks:
                self.automation_locks[automation.id] = asyncio.Lock()

            async with self.automation_locks[automation.id]:
                await self._execute_automation(automation, state_manager, send_ir_func)
        else:
            await self._execute_automation(automation, state_manager, send_ir_func)

    async def _execute_automation(self, automation: pydantic_models.IRAutomation, state_manager: Any, send_ir_func: Callable):
        self.running_automations[automation.id] = self.running_automations.get(automation.id, 0) + 1

        # Publish Running State ON
        if self.mqtt_manager and self.mqtt_manager.integration:
            self.mqtt_manager.integration.publish_automation_state(automation, "ON", self.mqtt_manager)

        run_id = str(uuid.uuid4())[:8]

        # Notify start
        await broadcast_ws(
            {
                "type": "automation_progress",
                "id": automation.id,
                "run_id": run_id,
                "status": "running",
                "current_action_index": -1,
                "running_count": self.running_automations[automation.id],
            }
        )

        try:
            for idx, action in enumerate(automation.actions):
                # Notify step update
                await broadcast_ws(
                    {
                        "type": "automation_progress",
                        "id": automation.id,
                        "run_id": run_id,
                        "status": "running",
                        "current_action_index": idx,
                        "running_count": self.running_automations[automation.id],
                    }
                )

                if action.type == "delay":
                    ms = action.delay_ms or 0
                    await asyncio.sleep(ms / 1000.0)
                elif action.type == "ir_send":
                    dev = next(
                        (d for d in state_manager.devices if d.id == action.device_id),
                        None,
                    )
                    if not dev:
                        self.logger.warning(
                            "Automation '%s': Device %s not found.",
                            automation.name,
                            action.device_id,
                        )
                        continue

                    btn = next((b for b in dev.buttons if b.id == action.button_id), None)
                    if not btn or not btn.code:
                        self.logger.warning(
                            "Automation '%s': Button %s not found or has no code.",
                            automation.name,
                            action.button_id,
                        )
                        continue

                    code_to_send = btn.code.model_dump(exclude_none=True)

                    # If a specific target is provided in the action, use it.
                    if action.target:
                        await send_ir_func(code_to_send, target=action.target)
                    elif dev.target_bridges:
                        await send_ir_func(code_to_send, target=dev.target_bridges)
                    else:
                        # Fallback to broadcast if no specific bridges are set on the device.
                        await send_ir_func(code_to_send, target=None)

                    # Notify device_inactivity triggers about the sent code so that
                    # watch_mode=="sent" and "both" triggers can react appropriately.
                    # Pass automation.id so ignore_own_actions can suppress self-loops.
                    await self.notify_device_activity(
                        device_id=dev.id,
                        button_id=btn.id,
                        source="sent",
                        source_automation_id=automation.id,
                    )
                elif action.type == "event":
                    if not action.event_name:
                        continue

                    if self.mqtt_manager and self.mqtt_manager.integration:
                        self.mqtt_manager.integration.publish_automation_event(automation, action.event_name, run_id, self.mqtt_manager)

        finally:
            count = self.running_automations.get(automation.id, 0) - 1
            if count <= 0:
                self.running_automations.pop(automation.id, None)
                count = 0
                # Publish Running State OFF
                if self.mqtt_manager and self.mqtt_manager.integration:
                    self.mqtt_manager.integration.publish_automation_state(automation, "OFF", self.mqtt_manager)
            else:
                self.running_automations[automation.id] = count

            # Notify end of this specific run
            await broadcast_ws(
                {
                    "type": "automation_progress",
                    "id": automation.id,
                    "run_id": run_id,
                    "status": "idle",
                    "current_action_index": -1,
                    "running_count": count,
                }
            )
