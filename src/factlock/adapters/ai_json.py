"""Ways to get one schema-shaped JSON answer from an AI model.

Three engines: a locally signed-in Claude Code CLI or Codex CLI (the user's subscription), or the Claude
API with a key. The CLIs run in an empty temporary folder without tools, so they can neither read project
files nor change anything.
"""

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import anthropic

from factlock.ports import AiError, JsonModel

TIMEOUT_SECONDS = 300
CLAUDE_API_MODEL = "claude-opus-5-5"


def _run(command: Sequence[str], prompt: str, cwd: Path, code: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    try:
        return subprocess.run(  # fixed argument list, no shell
            list(command),
            input=prompt,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise AiError(f"{code}_timeout") from None
    except OSError:
        raise AiError(f"{code}_not_runnable") from None


class ClaudeCliJson:
    """`claude -p` (Claude Code headless), signed in with a Claude subscription."""

    name = "claude-cli"

    @staticmethod
    def available() -> bool:
        return shutil.which("claude") is not None

    def ask(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        command = [
            "claude", "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config",
            "--system-prompt", system, "--json-schema", json.dumps(schema),
        ]  # fmt: skip
        with tempfile.TemporaryDirectory() as folder:
            done = _run(command, prompt, Path(folder), "claude_cli")
        try:
            envelope = json.loads(done.stdout)
        except ValueError:
            raise AiError("claude_cli_bad_output") from None
        if envelope.get("is_error"):
            signed_out = "authenticate" in str(envelope.get("result", "")).lower()
            raise AiError("claude_cli_signed_out" if signed_out else "claude_cli_error")
        answer = envelope.get("structured_output")
        if not isinstance(answer, dict):
            raise AiError("claude_cli_bad_output")
        return answer


class CodexCliJson:
    """`codex exec`, signed in with a ChatGPT subscription; read-only sandbox, no session files."""

    name = "codex-cli"

    def __init__(self, effort: str = "low") -> None:
        self._effort = effort

    @staticmethod
    def available() -> bool:
        return shutil.which("codex") is not None

    def ask(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as folder:
            cwd = Path(folder)
            (cwd / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
            command = [
                "codex", "exec", "-s", "read-only", "--skip-git-repo-check", "--ephemeral",
                "-c", f'model_reasoning_effort="{self._effort}"',
                "--output-schema", "schema.json", "-o", "out.json", "-",
            ]  # fmt: skip
            full = f"{system}\n\nDo not run commands or read files. Answer with the JSON only.\n\n{prompt}"
            done = _run(command, full, cwd, "codex_cli")
            output = cwd / "out.json"
            if done.returncode != 0 or not output.is_file():
                raise AiError("codex_cli_error")
            try:
                answer = json.loads(output.read_text(encoding="utf-8"))
            except ValueError:
                raise AiError("codex_cli_bad_output") from None
        if not isinstance(answer, dict):
            raise AiError("codex_cli_bad_output")
        return answer


class ClaudeApiJson:
    """Claude API with an API key from the environment."""

    name = "claude-api"

    def __init__(self, client: anthropic.Anthropic, model: str = CLAUDE_API_MODEL) -> None:
        self._client = client
        self._model = model

    def ask(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.AuthenticationError:
            raise AiError("claude_auth_failed") from None
        except anthropic.RateLimitError:
            raise AiError("claude_rate_limited") from None
        except anthropic.APIStatusError:
            raise AiError("claude_api_error") from None
        except anthropic.APIConnectionError:
            raise AiError("claude_unreachable") from None
        if response.stop_reason == "refusal":
            raise AiError("claude_refused")
        if response.stop_reason == "max_tokens":
            raise AiError("claude_truncated")
        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            answer = json.loads(text)
        except ValueError:
            raise AiError("claude_bad_output") from None
        if not isinstance(answer, dict):
            raise AiError("claude_bad_output")
        return answer


class FirstAvailableJson:
    """Tries engines in order; remembers which one answered last."""

    def __init__(self, engines: Sequence[JsonModel]) -> None:
        self._engines = list(engines)
        self.name = "+".join(engine.name for engine in engines)
        self.last_used = ""

    def ask(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        last = AiError("no_ai_engine")
        for engine in self._engines:
            try:
                answer = engine.ask(system, prompt, schema)
            except AiError as error:
                last = error
                continue
            self.last_used = engine.name
            return answer
        raise last
