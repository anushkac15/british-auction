import os
import uuid

import pytest
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import RedisError

from app.config import DEV_SECRET_KEY, Settings
from app.throttle import MemoryLoginThrottle, RedisLoginThrottle


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@db.internal:5432/auction", "postgresql://u:p@db.internal:5432/auction"],
)
def test_provider_database_urls_use_psycopg_driver(given):
    assert Settings(database_url=given).database_url == "postgresql+psycopg://u:p@db.internal:5432/auction"


def test_explicit_driver_url_is_left_alone():
    url = "postgresql+psycopg://u:p@localhost:5432/auction"
    assert Settings(database_url=url).database_url == url


@pytest.mark.parametrize("key", [DEV_SECRET_KEY, "too-short"])
def test_production_refuses_weak_secret_key(key):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(app_env="production", secret_key=key)


def test_production_accepts_strong_secret_key():
    settings = Settings(app_env="Production", secret_key="x" * 40)
    assert settings.is_production


def test_development_allows_default_secret_key():
    assert not Settings(app_env="development", secret_key=DEV_SECRET_KEY).is_production


def test_throttle_unblocks_after_window():
    now = [1000.0]
    throttle = MemoryLoginThrottle(max_failures=3, window_seconds=60, now=lambda: now[0])
    for _ in range(3):
        throttle.record_failure("a@test")
    assert throttle.retry_after("a@test") == 60

    now[0] += 45
    assert throttle.retry_after("a@test") == 15
    now[0] += 15
    assert throttle.retry_after("a@test") is None


def test_throttle_counts_only_failures_inside_window():
    now = [0.0]
    throttle = MemoryLoginThrottle(max_failures=2, window_seconds=10, now=lambda: now[0])
    throttle.record_failure("a@test")
    now[0] = 11
    throttle.record_failure("a@test")
    assert throttle.retry_after("a@test") is None
    throttle.record_failure("a@test")
    assert throttle.retry_after("a@test") == 10


@pytest.fixture
def redis_throttle():
    client = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), socket_connect_timeout=1)
    try:
        client.ping()
    except RedisError:
        pytest.skip("Redis is not reachable")
    throttle = RedisLoginThrottle(client, max_failures=3, window_seconds=60, prefix=f"test-login-{uuid.uuid4().hex}:")
    yield throttle
    throttle.clear()


def test_redis_throttle_shares_count_between_processes(redis_throttle):
    other_process = RedisLoginThrottle(
        redis_throttle.client, redis_throttle.max_failures, redis_throttle.window_seconds, redis_throttle.prefix
    )
    redis_throttle.record_failure("a@test")
    other_process.record_failure("a@test")
    assert redis_throttle.retry_after("a@test") is None
    other_process.record_failure("a@test")
    assert 55 <= redis_throttle.retry_after("a@test") <= 60
    assert other_process.retry_after("b@test") is None


def test_redis_throttle_reset(redis_throttle):
    for _ in range(3):
        redis_throttle.record_failure("a@test")
    redis_throttle.reset("a@test")
    assert redis_throttle.retry_after("a@test") is None


def test_redis_throttle_allows_logins_when_redis_is_down():
    unreachable = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2, socket_timeout=0.2)
    throttle = RedisLoginThrottle(unreachable, max_failures=1, window_seconds=60)
    throttle.record_failure("a@test")
    assert throttle.retry_after("a@test") is None
