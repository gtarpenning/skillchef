from __future__ import annotations

from skillchef import ui


def test_bind_escape_to_cancel_exits_with_none() -> None:
    calls: dict[str, object] = {}

    class DummyKeyBindings:
        def add(self, key: str, eager: bool = False):
            calls["key"] = key
            calls["eager"] = eager

            def decorator(fn):
                calls["handler"] = fn
                return fn

            return decorator

    class DummyQuestion:
        class DummyApp:
            key_bindings = DummyKeyBindings()

        application = DummyApp()

    class DummyEvent:
        class DummyEventApp:
            def exit(self, result=None):
                calls["result"] = result

        app = DummyEventApp()

    ui._bind_escape_to_cancel(DummyQuestion())

    assert calls["key"] == "escape"
    assert calls["eager"] is True

    handler = calls["handler"]
    handler(DummyEvent())
    assert calls["result"] is None


def test_require_exact_command_accepts_macro(monkeypatch) -> None:
    asked = iter(["chat", "uvx skillchef flavor frontend-design"])
    macro_calls = {"count": 0}
    warnings: list[str] = []

    monkeypatch.setattr(ui, "show_command", lambda *_a, **_k: None)
    monkeypatch.setattr(ui, "ask", lambda *_a, **_k: next(asked))
    monkeypatch.setattr(ui, "warn", lambda msg: warnings.append(msg))

    ui.require_exact_command(
        "uvx skillchef flavor frontend-design",
        macros={"chat": lambda: macro_calls.__setitem__("count", macro_calls["count"] + 1)},
    )

    assert macro_calls["count"] == 1
    assert warnings == []


def test_require_exact_command_still_warns_for_unknown_input(monkeypatch) -> None:
    asked = iter(["oops", "uvx skillchef sync frontend-design --no-ai"])
    warnings: list[str] = []

    monkeypatch.setattr(ui, "show_command", lambda *_a, **_k: None)
    monkeypatch.setattr(ui, "ask", lambda *_a, **_k: next(asked))
    monkeypatch.setattr(ui, "warn", lambda msg: warnings.append(msg))

    ui.require_exact_command("uvx skillchef sync frontend-design --no-ai")

    assert warnings == ["Incorrect command, try again."]
