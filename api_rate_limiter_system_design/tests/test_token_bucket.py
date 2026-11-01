import pytest

from app.limiter import token_bucket_decision


def test_consumes_available_token():
    tokens, updated, allowed, retry = token_bucket_decision(
        tokens=2, updated_at=10, now=10, capacity=5, refill_rate=1
    )
    assert allowed is True
    assert tokens == 1
    assert updated == 10
    assert retry == 0


def test_rejects_when_empty_and_calculates_retry():
    tokens, _, allowed, retry = token_bucket_decision(
        tokens=0, updated_at=10, now=10, capacity=5, refill_rate=0.5
    )
    assert allowed is False
    assert tokens == 0
    assert retry == 2


def test_refills_but_does_not_exceed_capacity():
    tokens, _, allowed, _ = token_bucket_decision(
        tokens=1, updated_at=10, now=30, capacity=5, refill_rate=1
    )
    assert allowed is True
    assert tokens == 4


def test_rejects_invalid_refill_rate():
    with pytest.raises(ValueError):
        token_bucket_decision(1, 0, 1, 5, 0)
