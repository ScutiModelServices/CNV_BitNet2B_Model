"""BitNet b1.58 2B4T run by bitnet.cpp: a `llama-server` child process (built into the Docker image) that holds the
GGUF weights and uses Microsoft's i2_s CPU kernels, which is where the speed of the model card comes from.

`CppLoaded` has the same `stream` and `generate` as `engine.Loaded`, so `BitNetEngine` does not care which one it holds.
The server listens on 127.0.0.1 only, one slot (the engine already runs one generation at a time per replica), and
ends when the last reference to the `CppLoaded` goes, so a call still running when the weights are replaced finishes.

shortcut: `max_time` is the socket read timeout (the wait for the next piece), not a limit on the whole answer."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import weakref
from pathlib import Path
from typing import Any, Iterator

from engine import EngineError

CONTEXT = 4096  # the model reads at most 4096 tokens
END_OF_TURN = "<|eot_id|>"  # the GGUF carries no chat template: the prompt is built here, like the tokenizer_config.json of the Hub model
START_TIMEOUT = 180.0


def server_binary() -> str | None:
    return shutil.which(os.environ.get("SERVICE_CPP_SERVER", "llama-server"))


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()


class CppLoaded:
    """A running `llama-server` that answers chat turns."""

    def __init__(self, gguf: Path, threads: int | None, binary: str | None = None, start_timeout: float = START_TIMEOUT) -> None:
        binary = binary or server_binary()
        if binary is None:
            raise EngineError("bitnet.cpp is not installed here: it is built into the Docker image only", 503)
        self.url = f"http://127.0.0.1:{_free_port()}"
        command = [binary, "-m", str(gguf), "--host", "127.0.0.1", "--port", self.url.rsplit(":", 1)[1],
                   "-c", str(CONTEXT), "-np", "1", "--special", "-t", str(threads or os.cpu_count() or 1)]
        self._process = subprocess.Popen(command, stdout=subprocess.DEVNULL)
        weakref.finalize(self, _stop, self._process)
        self._wait_ready(start_timeout)

    def _wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise EngineError(f"bitnet.cpp server stopped at start (exit code {self._process.returncode})", 503)
            try:
                with urllib.request.urlopen(f"{self.url}/health", timeout=2) as reply:
                    if reply.status == 200:
                        return
            except (urllib.error.URLError, OSError):  # 503 while the weights load, refused before it listens
                time.sleep(0.5)
        _stop(self._process)
        raise EngineError("bitnet.cpp server did not become ready in time", 503)

    def _post(self, path: str, body: dict[str, Any], max_time: float):
        request = urllib.request.Request(f"{self.url}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(request, timeout=max_time)
        except urllib.error.HTTPError as error:
            raise EngineError(f"bitnet.cpp server answered {error.code}: {error.read().decode('utf-8', 'replace')[:200]}", 502) from None
        except (urllib.error.URLError, OSError) as error:
            raise EngineError(f"bitnet.cpp server is not reachable: {error}", 502) from error

    def _open(self, messages: list[dict[str, str]], temperature: float, max_tokens: int, max_time: float, stream: bool):
        """The reply to a /completion call; a conversation that does not fit the context is refused first (the server would cut it)."""
        prompt = render(messages)
        with self._post("/tokenize", {"content": prompt}, max_time) as reply:
            size = len(json.load(reply)["tokens"])
        if size >= CONTEXT:
            raise EngineError(f"The conversation is {size} tokens; the model reads at most {CONTEXT}", 400)
        # `--special` makes the server print <|eot_id|>, so this stop string can end the answer there.
        return self._post("/completion", {"prompt": prompt, "temperature": temperature, "n_predict": min(max_tokens, CONTEXT - size),
                                          "stream": stream, "stop": [END_OF_TURN]}, max_time)

    def generate(self, messages: list[dict[str, str]], temperature: float, max_tokens: int, max_time: float) -> dict[str, Any]:
        with self._open(messages, temperature, max_tokens, max_time, False) as reply:
            data = json.load(reply)
        return {"content": data["content"].strip(), "prompt_tokens": data.get("tokens_evaluated", 0),
                "completion_tokens": data.get("tokens_predicted", 0), "finish": _finish(data)}

    def stream(self, messages: list[dict[str, str]], temperature: float, max_tokens: int, max_time: float,
               stop: threading.Event) -> Iterator[tuple[str, Any]]:
        """("content", text) pieces, then ("done", stats). Setting `stop` closes the connection, which stops the server's work."""
        last: dict[str, Any] = {}
        with self._open(messages, temperature, max_tokens, max_time, True) as reply:
            for line in reply:
                if stop.is_set():
                    break
                line = line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                last = json.loads(line[5:])
                if last.get("content"):
                    yield "content", last["content"]
        yield "done", {"prompt_tokens": last.get("tokens_evaluated", 0), "completion_tokens": last.get("tokens_predicted", 0),
                       "finish": _finish(last)}


def render(messages: list[dict[str, str]]) -> str:
    """`Role: text<|eot_id|>` per message, then `Assistant: ` (the template of microsoft/bitnet-b1.58-2B-4T)."""
    return "".join(f"{m['role'].capitalize()}: {m['content'].strip()}{END_OF_TURN}" for m in messages) + "Assistant: "


def _finish(data: dict[str, Any]) -> str:
    return "length" if data.get("stopped_limit") else "stop"


def load(repo: str, threads: int | None) -> CppLoaded:
    """The server for the downloaded GGUF weights of `repo`; OSError (like `engine.load`) when they are not on disk."""
    from huggingface_hub import snapshot_download

    folder = Path(snapshot_download(repo_id=repo, local_files_only=True, token=False))
    files = sorted(folder.glob("*.gguf"))
    if not files:
        raise FileNotFoundError(f"no .gguf file in {folder}")
    return CppLoaded(next((f for f in files if "i2_s" in f.name), files[0]), threads)
