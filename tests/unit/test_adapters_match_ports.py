"""The adapters wired in the composition root implement their ports, signature for signature."""

import inspect
import typing
from dataclasses import fields

import pytest

from app.api.dependencies import get_pipeline
from app.application.pipeline import Pipeline

PORT_FIELDS = typing.get_type_hints(Pipeline)
WIRED = get_pipeline()


def _port_methods(port: type) -> list[str]:
    return [name for name, member in vars(port).items() if inspect.isfunction(member) and not name.startswith("_")]


@pytest.mark.parametrize("field", [f.name for f in fields(Pipeline)])
def test_wired_adapter_implements_its_port(field):
    port = PORT_FIELDS[field]
    adapter = type(getattr(WIRED, field))
    assert port in adapter.__mro__, f"{adapter.__name__} should subclass {port.__name__}"

    for name in _port_methods(port):
        expected, actual = getattr(port, name), getattr(adapter, name)
        assert actual is not expected, f"{adapter.__name__}.{name} is not implemented"
        assert inspect.iscoroutinefunction(actual) == inspect.iscoroutinefunction(expected), (
            f"{adapter.__name__}.{name} must match the port's sync/async"
        )
        assert inspect.signature(actual, eval_str=True) == inspect.signature(expected, eval_str=True), (
            f"{adapter.__name__}.{name}{inspect.signature(actual)} != {port.__name__}.{name}{inspect.signature(expected)}"
        )
