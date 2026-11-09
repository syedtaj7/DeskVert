"""Ctrl+Shift tap detection (pure logic, no keyboard needed)."""

import pytest

from app.hotkey import VK_CONTROL as C, VK_SHIFT as S, TapDetector, is_modifier_tap

T, A = 0x54, 0x41


def _fires(events) -> bool:
    d = TapDetector()
    fired = False
    for vk, down, t in events:
        if vk == "mouse":
            d.mouse_pressed()
        elif d.key(vk, bool(down), t):
            fired = True
    return fired


@pytest.mark.parametrize("events,expected", [
    ([(C, 1, 0), (S, 1, .05), (S, 0, .15), (C, 0, .2)], True),
    ([(S, 1, 0), (C, 1, .05), (C, 0, .15), (S, 0, .2)], True),
    ([(C, 1, 0), (S, 1, .05), (C, 1, .3), (S, 1, .3), (S, 0, .4), (C, 0, .45)], True),  # key repeat
    ([(C, 1, 0), (S, 1, .05), (T, 1, .1), (T, 0, .15), (S, 0, .2), (C, 0, .25)], False),  # Ctrl+Shift+T
    ([(C, 1, 0), (S, 1, .05), ("mouse", 0, .1), (S, 0, .3), (C, 0, .35)], False),  # Ctrl+Shift+click
    ([(C, 1, 0), (S, 1, .05), (S, 0, 2.0), (C, 0, 2.1)], False),  # held too long
    ([(C, 1, 0), (C, 0, .1)], False),
    ([(S, 1, 0), (A, 1, .05), (A, 0, .1), (S, 0, .15)], False),  # typing a capital letter
])
def test_tap(events, expected):
    assert _fires(events) is expected


def test_combo_parsing():
    assert is_modifier_tap("Ctrl+Shift") and is_modifier_tap("shift + ctrl")
    assert not is_modifier_tap("Ctrl+Shift+Space")
