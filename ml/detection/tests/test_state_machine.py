"""La machine à états ne déclenche pas sur un pic isolé et revient à NORMAL après rétablissement."""
from datetime import datetime, timedelta, timezone

from ml.detection.service.state_machine import ANOMALY, NORMAL, RECOVERING, SUSPECT, StateMachine


def run(machine: StateMachine, pattern: str) -> list[str]:
    """'1' = score au-dessus du seuil, '0' = en dessous ; renvoie l'état après chaque fenêtre."""
    t0 = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
    states = []
    for i, char in enumerate(pattern):
        machine.update(char == "1", now=t0 + timedelta(seconds=5 * i))
        states.append(machine.state)
    return states


def test_isolated_spike_does_not_trigger():
    machine = StateMachine(confirm_n=2, confirm_m=3, recover_r=3)
    assert run(machine, "0100000") == [NORMAL, SUSPECT, SUSPECT, SUSPECT, NORMAL, NORMAL, NORMAL]
    assert machine.state == NORMAL


def test_sustained_exceedance_confirms_anomaly_within_two_windows():
    machine = StateMachine(confirm_n=2, confirm_m=3, recover_r=3)
    states = run(machine, "011")
    assert states == [NORMAL, SUSPECT, ANOMALY]


def test_two_out_of_three_with_gap():
    machine = StateMachine(confirm_n=2, confirm_m=3, recover_r=3)
    assert run(machine, "101")[-1] == ANOMALY


def test_recovery_requires_r_windows_and_relapse_returns_to_anomaly():
    machine = StateMachine(confirm_n=2, confirm_m=3, recover_r=3)
    states = run(machine, "1110" + "1" + "000" + "0")
    assert states[3] == RECOVERING
    assert states[4] == ANOMALY            # rechute pendant le rétablissement
    assert states[5] == RECOVERING
    assert states[7] == NORMAL             # 3 fenêtres consécutives sous le seuil
    assert states[8] == NORMAL


def test_transitions_are_reported_with_timestamps():
    machine = StateMachine(confirm_n=2, confirm_m=3, recover_r=2)
    t = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
    assert machine.update(True, now=t).current == SUSPECT
    transition = machine.update(True, now=t + timedelta(seconds=5))
    assert transition.previous == SUSPECT and transition.current == ANOMALY
    assert machine.since == t + timedelta(seconds=5)
    assert machine.update(True, now=t + timedelta(seconds=10)) is None
