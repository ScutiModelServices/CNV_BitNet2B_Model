import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conftest import make_engine
from cpp import CppLoaded
from engine import GGUF_MODEL, EngineError


class FakeServer(BaseHTTPRequestHandler):
    """The /tokenize and /completion answers of llama-server that matter here."""

    def log_message(self, *args):
        pass

    def reply(self, body, kind="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.seen.append((self.path, body))
        if self.path == "/tokenize":
            return self.reply(json.dumps({"tokens": list(range(5000 if "too long" in body["content"] else 4))}).encode())
        if body["stream"]:
            lines = [{"content": "Hel", "stop": False}, {"content": "lo", "stop": False},
                     {"content": "", "stop": True, "tokens_evaluated": 4, "tokens_predicted": 2, "stopped_limit": True}]
            return self.reply("".join(f"data: {json.dumps(line)}\n\n" for line in lines).encode(), "text/event-stream")
        self.reply(json.dumps({"content": " Hello ", "tokens_evaluated": 4, "tokens_predicted": 2, "stopped_limit": False}).encode())


@pytest.fixture
def loaded():
    server = HTTPServer(("127.0.0.1", 0), FakeServer)
    server.seen = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    model = CppLoaded.__new__(CppLoaded)  # no child process: the fake server stands in for llama-server
    model.url = f"http://127.0.0.1:{server.server_port}"
    model.seen = server.seen
    yield model
    server.shutdown()


def test_generate_sends_the_turn_and_reads_the_usage(loaded):
    out = loaded.generate([{"role": "user", "content": "hi"}], 0.0, 9, 30.0)
    assert out == {"content": "Hello", "prompt_tokens": 4, "completion_tokens": 2, "finish": "stop"}
    assert loaded.seen[-1] == ("/completion", {"prompt": "User: hi<|eot_id|>Assistant: ", "temperature": 0.0, "n_predict": 9,
                                                "stream": False, "stop": ["<|eot_id|>"]})


def test_stream_gives_the_pieces_then_the_stats(loaded):
    events = list(loaded.stream([{"role": "user", "content": "hi"}], 0.0, 9, 30.0, threading.Event()))
    assert events == [("content", "Hel"), ("content", "lo"), ("done", {"prompt_tokens": 4, "completion_tokens": 2, "finish": "length"})]


def test_stop_ends_the_stream_early(loaded):
    stop = threading.Event()
    stop.set()
    events = list(loaded.stream([{"role": "user", "content": "hi"}], 0.0, 9, 30.0, stop))
    assert [kind for kind, _ in events] == ["done"]


def test_a_conversation_that_does_not_fit_is_a_400(loaded):
    with pytest.raises(EngineError) as error:
        loaded.generate([{"role": "user", "content": "too long"}], 0.0, 9, 30.0)
    assert error.value.status == 400


def test_a_missing_server_binary_is_a_503(tmp_path, monkeypatch):
    monkeypatch.setenv("SERVICE_CPP_SERVER", str(tmp_path / "nope"))
    with pytest.raises(EngineError) as error:
        CppLoaded(tmp_path / "m.gguf", 2)
    assert error.value.status == 503


def test_the_cpp_engine_uses_the_gguf_repo_and_no_project_models(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "config.json").write_text("{}")
    engine = make_engine(engine="bitnet.cpp", projects_dir=str(tmp_path))
    reply = asyncio.run(engine.chat([{"role": "user", "content": "hi"}], project="p", temperature=0.0, max_tokens=5))
    assert engine.loads == [GGUF_MODEL] and reply["model"] == GGUF_MODEL and reply["fallback"] is True
    assert engine.projects() == [] and not engine.has_project("p")


def test_a_thread_change_drops_the_cpp_server_but_not_a_transformers_model():
    for name, dropped in (("bitnet.cpp", True), ("transformers", False)):
        engine = make_engine(engine=name)
        asyncio.run(engine.chat([{"role": "user", "content": "hi"}], project=None, temperature=0.0, max_tokens=5))
        engine.num_thread = 3
        assert engine.ready is not dropped


def test_only_known_engines_are_accepted():
    with pytest.raises(ValueError):
        make_engine(engine="vllm")
