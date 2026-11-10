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


def test_success_sends_prompt_and_session_with_10s_timeout(mock_agent):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"reply": "Hi!", "intent": "greeting"})

    seen = mock_agent(handler)
    result = agent.call_agent("http://agent/invocations", "s1", "hello")

    assert (result.reply, result.intent) == ("Hi!", "greeting")
    assert seen["timeout"] == 10
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


# --- spec 011: the optional `action` in the agent's response ---------------------------------

ACTION = {"type": "contribution_change", "params": {"new_rate_pct": 8}}


def test_action_is_returned_when_valid(mock_agent):
    mock_agent(lambda r: httpx.Response(200, json={"reply": "ok", "intent": None, "action": ACTION}))
    result = agent.call_agent("http://agent/invocations", "s1", "change it to 8%")
    assert result.action == ACTION


@pytest.mark.parametrize(
    "body",
    [{"reply": "ok", "intent": None}, {"reply": "ok", "intent": None, "action": None}],
    ids=["absent", "null"],
)
def test_action_is_none_when_absent_or_null(mock_agent, body):
    mock_agent(lambda r: httpx.Response(200, json=body))
    assert agent.call_agent("http://agent/invocations", "s1", "hi").action is None


@pytest.mark.parametrize(
    "bad_action",
    [
        "contribution_change",
        ["contribution_change"],
        {"type": 5, "params": {}},
        {"type": "contribution_change", "params": "8"},
        {"type": "contribution_change"},
        {"params": {"new_rate_pct": 8}},
    ],
    ids=["string", "list", "type-not-string", "params-not-object", "no-params", "no-type"],
)
def test_malformed_action_is_ignored_with_a_warning_and_reply_is_kept(mock_agent, caplog, bad_action):
    mock_agent(lambda r: httpx.Response(200, json={"reply": "ok", "intent": None, "action": bad_action}))
    with caplog.at_level("WARNING", logger="app.agent"):
        result = agent.call_agent("http://agent/invocations", "s1", "hi")
    assert result.reply == "ok"
    assert result.action is None
    assert any("action" in rec.message for rec in caplog.records)


def test_request_body_is_unchanged_by_the_action_field(mock_agent):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"reply": "ok", "intent": None})

    mock_agent(handler)
    agent.call_agent("http://agent/invocations", "s1", "hello")
    assert requests[0].read() == b'{"prompt":"hello","session_id":"s1"}'
