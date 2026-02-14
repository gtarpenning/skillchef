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
