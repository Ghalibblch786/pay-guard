"""Minimal client for a LOCAL Ollama server. Refuses anything that is not on this machine (complaint text must not leave it)."""
from urllib.parse import urlparse

import httpx

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "llama3.2:3b"
OPTIONS = {"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 350}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class TransportError(RuntimeError):
    """The call itself failed (server down, timeout, HTTP error). Retrying may help."""


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL, url: str = DEFAULT_URL, timeout_s: float = 180.0):
        if urlparse(url).hostname not in LOCAL_HOSTS:
            raise ValueError("only a local model server is allowed")
        if model.endswith("cloud"):
            raise ValueError("cloud-hosted models are not allowed")
        self.model, self.url, self.options = model, url, dict(OPTIONS)
        self._http = httpx.Client(timeout=timeout_s, trust_env=False)      # trust_env=False: ignore proxy settings

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._http.request(method, self.url + path, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TransportError(type(error).__name__) from None

    def digest(self) -> str:
        """Exact model build, for the cache key and the run record."""
        for m in self._request("GET", "/api/tags")["models"]:
            if m["name"] == self.model:
                if m.get("remote_host") or m.get("remote_model"):
                    raise ValueError("this model runs remotely and is not allowed")
                return m["digest"]
        raise ValueError("model is not installed locally")

    def chat(self, messages: list, schema: dict) -> dict:
        """One constrained generation. Returns {content, done_reason, prompt_tokens, output_tokens, latency_s}."""
        body = self._request("POST", "/api/chat", json={"model": self.model, "messages": messages, "format": schema, "stream": False,
                                                       "options": self.options, "keep_alive": "10m"})
        return {"content": body.get("message", {}).get("content", ""), "done_reason": body.get("done_reason"),
                "prompt_tokens": body.get("prompt_eval_count", 0), "output_tokens": body.get("eval_count", 0),
                "latency_s": body.get("total_duration", 0) / 1e9}
