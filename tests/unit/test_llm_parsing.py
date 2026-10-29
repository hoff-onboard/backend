import pytest

from app.infrastructure.llm.factory import parse_json_reply


@pytest.mark.parametrize(
    "reply,expected",
    [
        ('{"description": "x", "steps": []}', {"description": "x", "steps": []}),
        ('```json\n[{"index": 0}]\n```', [{"index": 0}]),
        ('Sure! Here it is: {"a": 1} hope that helps', {"a": 1}),
    ],
)
def test_extracts_json_from_model_replies(reply, expected):
    assert parse_json_reply(reply) == expected


def test_rejects_replies_without_json():
    with pytest.raises(ValueError):
        parse_json_reply("I don't know this product.")
