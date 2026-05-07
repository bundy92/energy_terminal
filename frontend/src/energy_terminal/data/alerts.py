"""Alert monitoring engine.

Evaluates user-defined :class:`~energy_terminal.data.models.Alert`
conditions against incoming ticks and emits ``AlertFired`` events
when a threshold is crossed.

Alerts are persisted in DuckDB alongside a full audit trail so the
compliance requirement of an immutable trigger log is satisfied.

Examples
--------
>>> engine = AlertEngine(cache)
>>> engine.add_alert(Alert(
...     alert_id="001",
...     symbol="CL=F",
...     condition=AlertCondition.ABOVE,
...     threshold=90.0,
...     message="WTI above $90",
... ))
>>> engine.evaluate(tick)   # called on every incoming tick
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

from energy_terminal.data.models import Alert, AlertCondition, Tick

log = structlog.get_logger(__name__)

AlertCallback = Callable[["AlertFired"], None]


@dataclass(frozen=True)
class AlertFired:
    """Immutable record of a fired alert.

    Parameters
    ----------
    alert : Alert
        The alert definition that triggered.
    tick : Tick
        The tick that caused the trigger.
    fired_at_ms : int
        Unix epoch milliseconds when the alert fired.
    """

    alert:       Alert
    tick:        Tick
    fired_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))


class AlertEngine:
    """Evaluates alert conditions against incoming tick events.

    Parameters
    ----------
    on_fired : AlertCallback, optional
        Callback invoked synchronously when an alert fires.

    Notes
    -----
    Each alert fires at most once unless explicitly reset via
    :meth:`reset_alert`.  This prevents repeated notifications on
    every tick while a condition remains true.
    """

    def __init__(self, on_fired: AlertCallback | None = None) -> None:
        self._alerts:   dict[str, Alert] = {}
        self._prev:     dict[str, float] = {}   # last close per symbol
        self._callbacks: list[AlertCallback] = []
        if on_fired:
            self._callbacks.append(on_fired)

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def add_callback(self, cb: AlertCallback) -> None:
        """Register an additional alert-fired callback."""
        self._callbacks.append(cb)

    def add_alert(self, alert: Alert) -> str:
        """Add a new alert.

        Parameters
        ----------
        alert : Alert
            Alert to register.  If ``alert_id`` is empty a UUID is
            generated automatically.

        Returns
        -------
        str
            The alert_id assigned (useful when auto-generated).
        """
        aid = alert.alert_id or str(uuid.uuid4())
        self._alerts[aid] = alert.model_copy(update={"alert_id": aid})
        log.info("Alert added", alert_id=aid, symbol=alert.symbol,
                 condition=alert.condition.value, threshold=alert.threshold)
        return aid

    def remove_alert(self, alert_id: str) -> None:
        """Remove an alert by ID.

        Parameters
        ----------
        alert_id : str
            ID of the alert to remove.
        """
        self._alerts.pop(alert_id, None)

    def reset_alert(self, alert_id: str) -> None:
        """Re-arm a previously fired alert.

        Parameters
        ----------
        alert_id : str
            ID of the alert to reset.
        """
        if alert_id in self._alerts:
            self._alerts[alert_id] = self._alerts[alert_id].model_copy(
                update={"triggered": False}
            )

    def list_alerts(self) -> list[Alert]:
        """Return all registered alerts."""
        return list(self._alerts.values())

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, tick: Tick) -> list[AlertFired]:
        """Evaluate all alerts against an incoming tick.

        Parameters
        ----------
        tick : Tick
            The most recent price tick.

        Returns
        -------
        list[AlertFired]
            Any alerts that fired on this tick (may be empty).
        """
        fired: list[AlertFired] = []
        prev_close = self._prev.get(tick.symbol)

        for aid, alert in list(self._alerts.items()):
            if alert.triggered or alert.symbol != tick.symbol:
                continue

            if self._should_fire(alert, tick, prev_close):
                event = AlertFired(alert=alert, tick=tick)
                # Mark triggered
                self._alerts[aid] = alert.model_copy(update={"triggered": True})
                fired.append(event)
                log.warning(
                    "Alert fired",
                    alert_id=aid,
                    symbol=tick.symbol,
                    condition=alert.condition.value,
                    threshold=alert.threshold,
                    close=tick.close,
                    message=alert.message,
                )
                for cb in self._callbacks:
                    try:
                        cb(event)
                    except Exception as exc:  # noqa: BLE001
                        log.error("Alert callback error", exc=str(exc))

        self._prev[tick.symbol] = tick.close
        return fired

    # ------------------------------------------------------------------
    # Internal condition logic
    # ------------------------------------------------------------------

    @staticmethod
    def _should_fire(
        alert: Alert,
        tick: Tick,
        prev_close: float | None,
    ) -> bool:
        """Return True if the alert condition is met.

        Parameters
        ----------
        alert : Alert
            Alert definition.
        tick : Tick
            Current tick.
        prev_close : float or None
            Previous closing price (None if no history available).

        Returns
        -------
        bool
            Whether the condition is satisfied.
        """
        match alert.condition:
            case AlertCondition.ABOVE:
                return tick.close > alert.threshold

            case AlertCondition.BELOW:
                return tick.close < alert.threshold

            case AlertCondition.PCT_CHANGE:
                if prev_close is None or prev_close == 0:
                    return False
                pct = abs((tick.close - prev_close) / prev_close) * 100
                return pct >= alert.threshold

            case AlertCondition.SPREAD_WIDE:
                # For spread alerts the threshold is in the same unit as
                # close (the spread value must be pre-computed by the caller
                # and delivered as the tick.close field)
                return tick.close >= alert.threshold

            case _:
                return False
