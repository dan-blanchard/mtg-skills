"""The corpus clone (its manifest and commit) and the private state file.

The manifest entry is the corpus's own format (``smoke-corpus-manifest.toml``):
the file name without ``.gz``, and the sha256 and size of the UNCOMPRESSED
scrubbed log, as its ``harvest-log`` command records them. The state file maps
each archived session to the name it was exported as; it names the account, so
it lives outside the repo and the corpus, in a mode-700 folder.
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mtg_utils._arena_corpus.verify import Term

__all__ = [
    "MANIFEST",
    "NOREPLY",
    "CommitRefusedError",
    "ManifestEntry",
    "State",
    "append_manifest",
    "check_commit_identity",
    "check_corpus",
    "commit",
    "export_message",
    "load_pool",
    "manifest_entries",
    "private_dir",
    "save_pool",
]

MANIFEST = "smoke-corpus-manifest.toml"


@dataclass(frozen=True)
class ManifestEntry:
    filename: str
    sha256: str
    size_bytes: int
    date_captured: str

    def toml(self) -> str:
        return (
            "[[files]]\n"
            f'filename      = "{self.filename}"\n'
            f'sha256        = "{self.sha256}"\n'
            f"size_bytes    = {self.size_bytes}\n"
            f'date_captured = "{self.date_captured}"\n'
        )


def check_corpus(corpus: Path) -> None:
    """Refuse a folder that isn't a corpus clone."""
    if not (corpus / "corpus").is_dir() or not (corpus / MANIFEST).is_file():
        raise ValueError(f"{corpus} is not a corpus clone (no corpus/ or {MANIFEST})")


def manifest_entries(corpus: Path) -> list[ManifestEntry]:
    data = tomllib.loads((corpus / MANIFEST).read_text())
    return [ManifestEntry(**f) for f in data.get("files", [])]


def append_manifest(corpus: Path, entries: Sequence[ManifestEntry]) -> None:
    """Add ``entries`` at the end, one blank line before each, as the file does."""
    path = corpus / MANIFEST
    text = path.read_text()
    text = text.rstrip("\n") + "\n"
    for entry in entries:
        text += "\n" + entry.toml()
    path.write_text(text)


def private_dir(path: Path) -> Path:
    """``path``, created mode 700 (and made 700 if it exists)."""
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


@dataclass
class State:
    """Which archived sessions were exported, and as what (private)."""

    path: Path
    exported: dict[str, dict]

    @classmethod
    def load(cls, path: Path) -> State:
        if not path.is_file():
            return cls(path, {})
        return cls(path, json.loads(path.read_text()).get("exported", {}))

    def save(self) -> None:
        private_dir(self.path.parent)
        tmp = self.path.with_suffix(".tmp")
        body = {"schema": 1, "exported": self.exported}
        tmp.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n")
        tmp.chmod(0o600)
        tmp.replace(self.path)


#: The pooled harvest: every identifier read off every session exported, kept so
#: a later run still searches for names earlier sessions stated. In the clear in
#: a 600 file in the 700 private folder: the substring and piece searches need
#: the values themselves (a salted hash could only match whole tokens), and the
#: archive beside it holds the raw logs in the clear anyway.
POOL = "harvest.json"
#: Kinds read off this machine at run time, never pooled.
_MACHINE_KINDS = ("local-user", "host-name", "real-name")


def load_pool(private: Path) -> list[Term]:
    path = private / POOL
    if not path.is_file():
        return []
    rows = json.loads(path.read_text()).get("terms", [])
    return [Term(*row) for row in rows]


def save_pool(private: Path, terms: Sequence[Term]) -> None:
    rows = sorted(
        {
            (t.kind, t.value, t.fold, t.bounded, t.quoted)
            for t in terms
            if not t.kind.startswith(_MACHINE_KINDS)
        }
    )
    private_dir(private)
    tmp = private / (POOL + ".tmp")
    tmp.write_text(json.dumps({"schema": 1, "terms": rows}, indent=0) + "\n")
    tmp.chmod(0o600)
    tmp.replace(private / POOL)


#: Commits in the corpus clone carry the owner's GitHub no-reply address, never a
#: personal one (the owner's decision, 2026-11-26).
NOREPLY = "@users.noreply.github.com"
#: The only address shape accepted: GitHub's ``<id>+<login>@users.noreply.github.com``.
NOREPLY_SHAPE = re.compile(r"\d+\+[A-Za-z0-9-]+@users\.noreply\.github\.com")
#: Every commit is unsigned: a signature would tie the corpus to a key whose
#: identity (its UIDs) this tool cannot vet.
UNSIGNED = ("-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false")


class CommitRefusedError(ValueError):
    """The corpus clone would commit under an address that isn't a no-reply one,
    or the commit it made carries a signature or another address (undone)."""


def _git_out(corpus: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *UNSIGNED, "-C", str(corpus), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _email(ident: str) -> str:
    return ident[ident.find("<") + 1 : ident.find(">")] if "<" in ident else ""


def check_commit_identity(corpus: Path) -> str:
    """Refuse unless the clone's ``user.email`` and the author and committer git
    would actually use (environment overrides included) are all GitHub no-reply
    addresses of the ``<id>+<login>`` shape. Never writes git config. The
    identity it would commit under, ``user.name <user.email>`` (the name is the
    owner's public GitHub name: shown, not checked)."""
    email = _git_out(corpus, "config", "user.email")
    used = [
        _email(_git_out(corpus, "var", v))
        for v in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT")
    ]
    if all(NOREPLY_SHAPE.fullmatch(e) for e in (email, *used)):
        return f"{_git_out(corpus, 'config', 'user.name')} <{email}>"
    raise CommitRefusedError(
        "refusing to commit: the corpus clone's author e-mail is not a GitHub "
        f"no-reply address (<id>+<login>{NOREPLY}). Set it for that clone only: "
        f"git -C {corpus} config user.email <id>+<login>{NOREPLY} "
        "(and unset GIT_AUTHOR_EMAIL / GIT_COMMITTER_EMAIL / EMAIL if set)"
    )


def _check_head(corpus: Path) -> list[str]:
    """What is wrong with the commit just made: a signature, or an author or
    committer address that isn't the no-reply shape."""
    raw = _git_out(corpus, "cat-file", "commit", "HEAD")
    header = raw.split("\n\n", 1)[0].splitlines()
    wrong = ["it is signed (gpgsig)" for line in header if line.startswith("gpgsig")]
    for role in ("author", "committer"):
        line = next((h for h in header if h.startswith(role + " ")), "")
        if not NOREPLY_SHAPE.fullmatch(_email(line)):
            wrong.append(f"its {role} e-mail is not a no-reply address")
    return wrong


def commit(corpus: Path, files: Sequence[str], message: str) -> str:
    """One local, unsigned commit of ``files`` (paths in the clone); never pushes.
    Checked afterwards: a signature or another address undoes it
    (``reset --soft HEAD~1``) and raises. The commit's id."""
    check_commit_identity(corpus)
    git = ["git", *UNSIGNED, "-C", str(corpus)]
    subprocess.run([*git, "add", "-f", "--", *files], check=True)
    subprocess.run([*git, "commit", "-q", "-m", message, "--", *files], check=True)
    wrong = _check_head(corpus)
    if wrong:
        subprocess.run([*git, "reset", "-q", "--soft", "HEAD~1"], check=True)
        raise CommitRefusedError(
            "the commit was undone (reset --soft HEAD~1): "
            + "; ".join(wrong)
            + ". The files stay written and staged in the clone."
        )
    return _git_out(corpus, "rev-parse", "--short", "HEAD")


def export_message(names: Sequence[str]) -> str:
    return f"Add {len(names)} MTG Arena session(s) to corpus\n\n" + "".join(
        f"- {n}\n" for n in names
    )
