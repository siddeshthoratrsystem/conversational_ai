import httpx
import pytest

from app import agent


@pytest.fixture
def mock_agent(monkeypatch):
    """Route agent.call_agent's httpx.Client through a MockTransport; records the Client kwargs."""
    real_client = httpx.Client
    seen = {}

    def install(handler):
        def factory(**kwargs):
            seen.update(kwargs)
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(agent.httpx, "Client", factory)
        return seen

    return install


def test_success_sends_prompt_and_session_with_the_default_timeout(mock_agent, monkeypatch):
    monkeypatch.delenv("AGENT_TIMEOUT_SECONDS", raising=False)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"reply": "Hi!", "intent": "greeting"})

    seen = mock_agent(handler)
    result = agent.call_agent("http://agent/invocations", "s1", "hello")

    assert (result.reply, result.intent) == ("Hi!", "greeting")
    assert seen["timeout"] == 60
    assert requests[0].read() == b'{"prompt":"hello","session_id":"s1"}'


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, content=b"not json"),
        lambda r: httpx.Response(200, json={"intent": "x"}),
        lambda r: httpx.Response(200, json={"reply": "ok", "intent": 5}),
        lambda r: httpx.Response(200, json=["reply"]),
    ],
    ids=["http-500", "not-json", "missing-reply", "bad-intent", "not-object"],
)
def test_bad_responses_raise_agent_error(mock_agent, handler):
    mock_agent(handler)
    with pytest.raises(agent.AgentError):
        agent.call_agent("http://agent/invocations", "s1", "hello")


def test_timeout_raises_agent_error(mock_agent):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    mock_agent(handler)
    with pytest.raises(agent.AgentError, match="ReadTimeout"):
        agent.call_agent("http://agent/invocations", "s1", "hello")


def test_timeout_comes_from_the_environment(mock_agent, monkeypatch):
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "42")
    seen = mock_agent(lambda r: httpx.Response(200, json={"reply": "ok", "intent": None}))
    agent.call_agent("http://agent/invocations", "s1", "hi")
    assert seen["timeout"] == 42


def test_default_agent_timeout_is_60_seconds(monkeypatch):
    monkeypatch.delenv("AGENT_TIMEOUT_SECONDS", raising=False)
    assert agent.agent_timeout_seconds() == 60


@pytest.mark.parametrize("value", ["", "abc", "0", "-5"])
def test_unusable_timeout_values_fall_back_to_the_default_with_a_warning(monkeypatch, caplog, value):
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", value)
    with caplog.at_level("WARNING", logger="app.agent"):
        assert agent.agent_timeout_seconds() == 60
    if value:
        assert any("AGENT_TIMEOUT_SECONDS" in r.getMessage() for r in caplog.records)


def test_start_up_logs_the_timeout_in_use(monkeypatch, caplog):
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "45")
    with caplog.at_level("INFO", logger="app.agent"):
        agent.log_timeout_at_start_up()
    lines = [r.getMessage() for r in caplog.records if "AGENT_TIMEOUT_SECONDS" in r.getMessage()]
    assert len(lines) == 1 and "45" in lines[0]


def test_start_up_logs_the_default_timeout(monkeypatch, caplog):
    monkeypatch.delenv("AGENT_TIMEOUT_SECONDS", raising=False)
    with caplog.at_level("INFO", logger="app.agent"):
        agent.log_timeout_at_start_up()
    assert any("AGENT_TIMEOUT_SECONDS" in r.getMessage() and "60" in r.getMessage() for r in caplog.records)


# --- spec 011: the participant's token is forwarded, and `source` comes back -----------------


def test_token_is_sent_as_a_bearer_header(mock_agent):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"reply": "ok", "intent": None})

    mock_agent(handler)
    agent.call_agent("http://agent/invocations", "s1", "hi", token="t")
    assert requests[0].headers["Authorization"] == "Bearer t"
    assert requests[0].read() == b'{"prompt":"hi","session_id":"s1"}'


def test_no_authorization_header_without_a_token(mock_agent):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"reply": "ok", "intent": None})

    mock_agent(handler)
    agent.call_agent("http://agent/invocations", "s1", "hi", token=None)
    agent.call_agent("http://agent/invocations", "s1", "hi")
    assert all("authorization" not in r.headers for r in requests)


@pytest.mark.parametrize(
    "body, expected",
    [
        ({"reply": "ok", "intent": None, "source": "gate"}, "gate"),
        ({"reply": "ok", "intent": None}, None),
        ({"reply": "ok", "intent": None, "source": None}, None),
    ],
    ids=["gate", "absent", "null"],
)
def test_source_is_gate_or_none(mock_agent, body, expected):
    mock_agent(lambda r: httpx.Response(200, json=body))
    assert agent.call_agent("http://agent/invocations", "s1", "hi").source == expected


@pytest.mark.parametrize("bad", ["agent", "mock", "other", 5, ["gate"], {"gate": 1}])
def test_any_other_source_is_ignored_with_a_warning_and_the_reply_is_kept(mock_agent, caplog, bad):
    mock_agent(lambda r: httpx.Response(200, json={"reply": "ok", "intent": None, "source": bad}))
    with caplog.at_level("WARNING", logger="app.agent"):
        result = agent.call_agent("http://agent/invocations", "s1", "hi")
    assert result.reply == "ok"
    assert result.source is None
    assert any("source" in r.getMessage() for r in caplog.records)


def test_the_token_never_appears_in_logs(mock_agent, caplog):
    mock_agent(lambda r: httpx.Response(200, json={"reply": "ok", "intent": None, "source": "weird"}))
    with caplog.at_level("DEBUG"):
        agent.call_agent("http://agent/invocations", "s1", "hi", token="SECRET-TOKEN-123")
        mock_agent(lambda r: httpx.Response(500))
        with pytest.raises(agent.AgentError):
            agent.call_agent("http://agent/invocations", "s1", "hi", token="SECRET-TOKEN-123")
    assert "SECRET-TOKEN-123" not in caplog.text
