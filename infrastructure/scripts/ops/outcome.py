"""One outcome contract for the operator command-line tools (`just agent`, `just agent-preflight`, `just mcp`).

Every command prints exactly one JSON document on stdout. The document has a top-level boolean `ok`; a failure
also has `error: {code, message, retryable}`. The codes are one closed set, defined here and nowhere else, each
classed retryable or terminal. `error` refuses a code outside the set and a `retryable` flag that disagrees with
the code's class, so a caller can branch on `error.code` or `error.retryable` and never on prose.

The contract is additive: a tool adds `ok` and `error` to the document it already printed and keeps every other
key and every exit code. See docs/infrastructure/configuration/cli-contract.md.
"""

from __future__ import annotations

import traceback
from pathlib import Path

# code -> retryable. A retryable failure may succeed when the same command is repeated unchanged; a terminal one will not.
CODES: dict[str, bool] = {
    "invalid-arguments": False,
    "validation-failed": False,
    "not-found": False,
    "refused": False,
    "conflict": False,
    "check-failed": False,
    "failed": False,
    "not-confirmed": False,
    "no-consent": True,
    "timeout": True,
    "interrupted": True,
    "unavailable": True,
    "internal": False,
}


def _check_table() -> None:
    """The runtime check on the set itself: every code is a lower-case word string and every class is a real boolean."""
    for code, retryable in CODES.items():
        if not isinstance(code, str) or not code or code != code.lower() or not isinstance(retryable, bool):
            raise RuntimeError(f"outcome code table is malformed at {code!r}")


_check_table()


def usage_message(message: str) -> str:
    """The text of an argument error as it may go into a document: never a value the person typed.

    argparse's "unrecognized arguments: ..." lists the arguments as given, values included, so that message is
    replaced by one that names only the options (words starting with `-`, cut at any `=`). Other messages are kept.
    """
    prefix = "unrecognized arguments: "
    if not message.startswith(prefix):
        return message
    names: list[str] = []
    for word in message[len(prefix) :].split():
        if word.startswith("-"):
            name = word.split("=", 1)[0]
            if name not in names:
                names.append(name)
    shown = f"unrecognized options: {', '.join(names[:10])}" if names else "unrecognized arguments (values are not shown)"
    return f"{shown}; usage is on stderr"


def error(code: str, message: str, *, retryable: bool | None = None, proofs: list | None = None) -> dict:
    """The `error` object of a failure document.

    Refuses a code outside CODES, a `retryable` that disagrees with the code's class, a message that is not
    text, and `proofs` on any code but `check-failed` (which must carry them).
    """
    if code not in CODES:
        raise ValueError(f"unknown outcome code {code!r}; the closed set is {sorted(CODES)}")
    if retryable is not None and retryable is not CODES[code]:
        raise ValueError(f"outcome code {code!r} is {'retryable' if CODES[code] else 'terminal'}; retryable={retryable!r} disagrees")
    if not isinstance(message, str) or not message:
        raise ValueError("an outcome message is a non-empty string")
    if (code == "check-failed") != (proofs is not None):
        raise ValueError("`proofs` belong to check-failed, and check-failed carries them")
    out = {"code": code, "message": message, "retryable": CODES[code]}
    if proofs is not None:
        out["proofs"] = list(proofs)
    return out


class Coded(Exception):
    """An exception that knows which outcome code it ends as. A subclass sets `default_code`; a raise site may override it."""

    default_code = "failed"

    def __init__(self, message: str = "", code: str | None = None):
        super().__init__(message)
        self.code = code or self.default_code
        if self.code not in CODES:
            raise ValueError(f"unknown outcome code {self.code!r}")


def code_of(exc: BaseException, fallback: str = "failed") -> str:
    return exc.code if isinstance(exc, Coded) else fallback


def document(doc: dict, failure: dict | None = None) -> dict:
    """`doc` with `ok` and, on failure, `error` added. Nothing already in `doc` is changed, except that a
    failure document that already carries an `ok` has it set to False (it can only have meant the same)."""
    if failure is None:
        if doc.get("ok") is False:
            raise ValueError("a document with ok false needs an error")
        return {**doc, "ok": True}
    if "error" in doc and doc["error"] is not failure:
        raise ValueError("the document already has an `error` key")
    return {**doc, "ok": False, "error": failure}


def unexpected(exc: BaseException) -> str:
    """Names only the type and the place of an unforeseen exception: its message is not known to be free of what a
    remote answer or a token carried."""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return f"unexpected {type(exc).__name__}"
    frame = frames[-1]
    return f"unexpected {type(exc).__name__} at {Path(frame.filename).name}:{frame.lineno}"
