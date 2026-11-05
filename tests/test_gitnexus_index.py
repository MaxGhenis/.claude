"""Tests for hooks/gitnexus/gitnexus-index, which keeps one GitNexus build and one index per repo.

Run: uv run --no-project --with pytest --with hypothesis pytest tests/test_gitnexus_index.py -q -p no:cacheprovider

The command-line tests run the real script against real git repositories under the pytest temp
folder. $HOME and GITNEXUS_HOME point there, so nothing of the user's is read or written. A fake
`node` stands in for GitNexus in CI; `TestRealBuild` runs the same flow against the pinned install
when this machine has one, which keeps the fake honest.

Invariants of the prune plan, for every registry:
  P1  the plan holds only rows from the registry, each at most once;
  P2  a canonical row never enters the plan;
  P3  every other row that stays exists, has a database the engine can open, and neither carries a
      managed name nor comes from a managed repository;
  P4  applying the plan leaves nothing more to prune (idempotence);
  P5  a row's reason depends only on that row: adding rows never changes another row's fate;
  P6  the plan names rows in registry order.

Invariants of a refresh, for every run:
  R1  the source checkout keeps its branch, HEAD and working files;
  R2  the index worktree ends detached at origin's commit, and locked against worktree sweeps;
  R3  the registry ends with one row for the repository, at the canonical path;
  R4  unrelated rows and all storage on disk survive;
  R5  a failed analyze, an unreadable database or a wrong commit exits 1, never 0.
"""

from __future__ import annotations

import fcntl
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import textwrap

from hypothesis import given, strategies as st
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "hooks/gitnexus/gitnexus-index"
HOOK = Path(__file__).resolve().parents[1] / "hooks/gitnexus/gitnexus-hook.cjs"
REAL_CURRENT = Path.home() / ".local/share/gitnexus-current"
REAL_NODE = shutil.which("node")
GIT_DIRECTORY = os.path.dirname(shutil.which("git") or "/usr/bin/git")
TIMEOUT_SECONDS = 300
LOAD_CEILING = "1000000"


def load_tool():
    loader = importlib.machinery.SourceFileLoader("gitnexus_index", str(SCRIPT))
    spec = importlib.util.spec_from_loader("gitnexus_index", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gitnexus_index"] = module
    loader.exec_module(module)
    return module


tool = load_tool()


# Pure rules
MANAGED = frozenset({"repo-a", "repo-b"})
CANONICAL = frozenset({"/index/repo-a", "/index/repo-b"})
READABLE = frozenset({40, 42})

rows_strategy = st.builds(
    tool.Row,
    name=st.sampled_from(["repo-a", "repo-b", "other", "slug-1234"]),
    path=st.sampled_from(["/index/repo-a", "/index/repo-b", "/x/1", "/x/2", "/x/3", "/x/4"]),
    exists=st.booleans(),
    storage_version=st.sampled_from([None, 0, 40, 42, 43]),
    repo=st.sampled_from(["repo-a", "repo-b", "other", None]),
)


def plan(rows):
    return tool.plan_prune(rows, managed=MANAGED, canonical=CANONICAL, readable=READABLE)


@given(st.lists(rows_strategy, max_size=8))
def test_prune_plan_invariants(rows):
    planned = [row for row, _reason in plan(rows)]

    # P1 and P6: a subsequence of the registry, in registry order.
    remaining = iter(rows)
    assert all(any(row is candidate for candidate in remaining) for row in planned)

    # P2
    assert not [row for row in planned if row.path in CANONICAL]

    # P3
    kept = [row for row in rows if not any(row is other for other in planned)]
    for row in kept:
        if row.path in CANONICAL:
            continue
        assert row.exists
        assert row.storage_version in READABLE
        assert row.name not in MANAGED
        assert row.repo not in MANAGED

    # P4
    assert plan(kept) == []


@given(st.lists(rows_strategy, max_size=6), st.lists(rows_strategy, max_size=6))
def test_a_rows_reason_ignores_other_rows(rows, extra):
    # P5
    assert plan(rows + extra)[: len(plan(rows))] == plan(rows)


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (tool.Row("x", "/x/1", False, 42, None), "missing-directory"),
        (tool.Row("x", "/x/1", True, None, None), "no-database"),
        (tool.Row("x", "/x/1", True, 43, None), "unreadable-database"),
        (tool.Row("x", "/x/1", True, 0, None), "unreadable-database"),
        (tool.Row("repo-a", "/x/1", True, 42, "fork"), "duplicate-of-canonical"),
        (tool.Row("slug-1234", "/x/1", True, 40, "repo-b"), "worktree-of-managed-repo"),
        (tool.Row("other", "/x/1", True, 42, "other"), None),
        (tool.Row("repo-a", "/index/repo-a", False, None, None), None),
    ],
)
def test_prune_reasons(row, reason):
    assert tool.prune_reason(row, managed=MANAGED, canonical=CANONICAL, readable=READABLE) == reason


@given(st.integers(min_value=0, max_value=2**64 - 1))
def test_storage_version_reads_any_header(version):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        (path / "lbug").write_bytes(b"LBUG" + struct.pack("<Q", version) + b"rest of the file")
        assert tool.storage_version(path) == version


@pytest.mark.parametrize(
    ("content", "expected"),
    [(None, None), (b"", 0), (b"LBUG\x01", 0), (b"KUZU" + struct.pack("<Q", 40), 0)],
)
def test_storage_version_without_a_valid_header(tmp_path, content, expected):
    if content is not None:
        (tmp_path / "lbug").write_bytes(content)
    assert tool.storage_version(tmp_path) == expected


names_strategy = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,30}", fullmatch=True).filter(
    lambda name: not name.endswith(".git")
)


@given(names_strategy)
def test_repo_from_url_reads_https_and_ssh_alike(name):
    assert tool.repo_from_url(f"https://github.com/owner/{name}.git") == name
    assert tool.repo_from_url(f"https://github.com/owner/{name}") == name
    assert tool.repo_from_url(f"https://github.com/owner/{name}/") == name
    assert tool.repo_from_url(f"git@github.com:owner/{name}.git") == name


@pytest.mark.parametrize("url", [None, ""])
def test_repo_from_url_without_a_url(url):
    assert tool.repo_from_url(url) is None


@given(st.lists(st.sampled_from(["a", "b", "c", "d"]), max_size=8))
def test_duplicate_names_match_a_count(names):
    rows = [tool.Row(name, f"/x/{index}", True, 42, None) for index, name in enumerate(names)]
    assert tool.duplicate_names(rows) == sorted({name for name in names if names.count(name) > 1})


@pytest.mark.parametrize(
    ("text", "succeeded", "expected"),
    [
        ("Runtime exception: Trying to read a database file with a different version.", False, False),
        ('Repository "mirror-wf" not found. Available: a, b', False, False),
        ("LadybugDB not found at /x/lbug", False, False),
        ('Multiple registered repos match "x"', False, False),
        ('{"error":"Target \'__gitnexus_index_doctor_probe__\' not found"}', True, True),
        ("Target '__gitnexus_index_doctor_probe__' not found", False, True),
        ("Some other failure", False, False),
    ],
)
def test_probe_classification(text, succeeded, expected):
    assert tool.probe_healthy(succeeded, text) == expected


# Command-line behaviour against real git, with a fake node
FAKE_NODE = """\
# Stands in for node: it models the two things gitnexus-index asks of the pinned build.
import json, os, struct, subprocess, sys
from pathlib import Path

registry = Path(os.environ["GITNEXUS_HOME"]) / "registry.json"


def read():
    return json.loads(registry.read_text()) if registry.exists() else []


arguments = sys.argv[1:]
if "--input-type=module" in arguments:
    gone = {os.path.realpath(path) for path in json.loads(os.environ["GITNEXUS_INDEX_PATHS"])}
    registry.write_text(json.dumps([e for e in read() if os.path.realpath(e["path"]) not in gone]))
    sys.exit(0)

assert arguments[1] == "analyze", arguments
with open(os.environ["FAKE_NODE_LOG"], "a") as log:
    log.write(json.dumps(arguments[1:]) + "\\n")
mode = os.environ.get("FAKE_NODE_MODE", "ok")
if mode == "crash":
    sys.exit(3)
path = arguments[-1]
name = arguments[arguments.index("--name") + 1]
storage = Path(path) / ".gitnexus"
storage.mkdir(exist_ok=True)
version = 43 if mode == "newer-engine" else 42
(storage / "lbug").write_bytes(b"LBUG" + struct.pack("<Q", version))
if mode == "dirty" or (mode == "write-block" and "--index-only" not in arguments):
    (Path(path) / "tracked.txt").write_text("generated block\\n")
if mode == "skip-register":
    sys.exit(0)
commit = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
if mode == "wrong-commit":
    commit = "0" * 40
rows = [e for e in read() if os.path.realpath(e["path"]) != os.path.realpath(path)]
rows.append({"name": name, "path": path, "storagePath": str(storage), "lastCommit": commit})
registry.write_text(json.dumps(rows))
"""

FAKE_MCP_SERVER = """\
# Answers MCP over stdio the way the real server does: one JSON message per line.
import json, os, sys

failing = set(json.loads(os.environ.get("FAKE_MCP_FAILING", "[]")))
for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    if message["method"] == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "fake"}}
    else:
        repo = message["params"]["arguments"]["repo"]
        if repo in failing:
            text = "Runtime exception: Trying to read a database file with a different version."
        else:
            text = json.dumps({"error": "Target '__gitnexus_index_doctor_probe__' not found"})
        result = {"content": [{"type": "text", "text": text}], "isError": repo in failing}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""


def make_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def make_python_executable(path: Path, body: str) -> None:
    make_executable(path, f"#!{sys.executable}\n{body}")


class Machine:
    """A temp home with a fake pinned install, an origin, and a source checkout on another branch."""

    def __init__(self, root: Path):
        self.root = root
        self.home = root / "home"
        self.home.mkdir()
        self.gitnexus_home = self.home / ".gitnexus"
        self.gitnexus_home.mkdir()
        self.current = self.home / ".local/share/gitnexus-current"
        self.index_root = root / "index"
        self.source_root = root / "sources"
        self.source_root.mkdir()
        self.bin = root / "bin"
        self.log = root / "analyze.log"
        self.install_build()
        make_python_executable(self.bin / "node", FAKE_NODE)
        (root / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n")
        self.environment = {
            "HOME": str(self.home),
            "PATH": os.pathsep.join([str(self.bin), GIT_DIRECTORY, "/usr/bin", "/bin"]),
            "GITNEXUS_HOME": str(self.gitnexus_home),
            "GITNEXUS_INDEX_CURRENT": str(self.current),
            "GITNEXUS_INDEX_ROOT": str(self.index_root),
            "GITNEXUS_INDEX_SOURCE_ROOT": str(self.source_root),
            "GITNEXUS_INDEX_NODE": str(self.bin / "node"),
            "FAKE_NODE_LOG": str(self.log),
            "GIT_CONFIG_GLOBAL": str(root / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }

    def install_build(self, version="1.6.12", engine="0.18.3", pinned=None):
        build = self.current.parent / f"gitnexus-{version}"
        cli = build / "node_modules/gitnexus/dist/cli/index.js"
        make_executable(cli, "#!/usr/bin/env node\n")
        (build / "node_modules/gitnexus/package.json").write_text(json.dumps({"version": version}))
        core = build / "node_modules/@ladybugdb/core"
        core.mkdir(parents=True, exist_ok=True)
        (core / "package.json").write_text(json.dumps({"version": engine}))
        (build / "package.json").write_text(json.dumps({"dependencies": {"gitnexus": pinned or version}}))
        launcher = build / "node_modules/.bin/gitnexus"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        if not launcher.is_symlink():
            launcher.symlink_to("../gitnexus/dist/cli/index.js")
        if self.current.is_symlink():
            self.current.unlink()
        self.current.symlink_to(build.name)

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env=self.environment,
        ).stdout.strip()

    def make_repo(self, repo: str) -> Path:
        """Create an origin plus a source checkout parked on a feature branch with dirty work."""
        origin = self.root / "origins" / f"{repo}.git"
        origin.mkdir(parents=True)
        self.git(origin, "init", "--quiet", "--bare", "--initial-branch=main")
        seed = self.root / "seeds" / repo
        seed.mkdir(parents=True)
        self.git(seed, "init", "--quiet", "--initial-branch=main")
        (seed / "tracked.txt").write_text("v1\n")
        (seed / ".gitignore").write_text(".gitnexus\n")
        self.git(seed, "add", "-A")
        self.git(seed, "commit", "--quiet", "-m", "first")
        self.git(seed, "remote", "add", "origin", str(origin))
        self.git(seed, "push", "--quiet", "origin", "main")
        source = self.source_root / repo
        self.git(self.root, "clone", "--quiet", str(origin), str(source))
        self.git(source, "checkout", "--quiet", "-b", "feature")
        (source / "tracked.txt").write_text("uncommitted work\n")
        (source / "untracked.txt").write_text("also mine\n")
        return source

    def push_commit(self, repo: str, message: str) -> str:
        seed = self.root / "seeds" / repo
        (seed / "tracked.txt").write_text(f"{message}\n")
        self.git(seed, "commit", "--quiet", "-am", message)
        self.git(seed, "push", "--quiet", "origin", "main")
        return self.git(seed, "rev-parse", "HEAD")

    def origin_head(self, repo: str) -> str:
        return self.git(self.root / "seeds" / repo, "rev-parse", "HEAD")

    def registry(self) -> list[dict]:
        path = self.gitnexus_home / "registry.json"
        return json.loads(path.read_text()) if path.exists() else []

    def write_registry(self, rows: list[dict]) -> None:
        (self.gitnexus_home / "registry.json").write_text(json.dumps(rows))

    def add_row(self, name: str, *, version: int | None = 42, remote: str | None = None, exists=True) -> dict:
        path = self.root / "rows" / f"{name}-{len(self.registry())}"
        storage = path / ".gitnexus"
        if exists:
            storage.mkdir(parents=True)
            if version is not None:
                (storage / "lbug").write_bytes(b"LBUG" + struct.pack("<Q", version))
        row = {"name": name, "path": str(path), "storagePath": str(storage)}
        if remote:
            row["remoteUrl"] = remote
        self.write_registry([*self.registry(), row])
        return row

    def run(self, *arguments: str, **overrides: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env={**self.environment, **overrides},
            check=False,
        )

    def refresh(self, repo: str, *flags: str, **overrides: str) -> subprocess.CompletedProcess:
        return self.run("refresh", repo, "--max-load", LOAD_CEILING, *flags, **overrides)

    def analyze_calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def write_healthy_configs(self) -> None:
        launcher = str(self.current / "node_modules/.bin/gitnexus")
        config = {"mcpServers": {"gitnexus": {"command": "node", "args": [launcher, "mcp"]}}}
        (self.home / ".mcp.json").write_text(json.dumps(config))
        (self.home / ".cursor").mkdir(exist_ok=True)
        (self.home / ".cursor/mcp.json").write_text(json.dumps(config))
        (self.bin / "gitnexus").symlink_to(launcher)
        hook = self.home / ".claude/hooks/gitnexus/gitnexus-hook.cjs"
        hook.parent.mkdir(parents=True)
        hook.write_text(f'const cliPath = "{self.current}/node_modules/gitnexus/dist/cli/index.js";\n')


@pytest.fixture
def machine(tmp_path):
    return Machine(tmp_path)


def assert_source_untouched(machine, source):
    # R1
    assert machine.git(source, "symbolic-ref", "--short", "HEAD") == "feature"
    assert (source / "tracked.txt").read_text() == "uncommitted work\n"
    assert (source / "untracked.txt").read_text() == "also mine\n"


def test_refresh_builds_a_locked_detached_worktree_and_leaves_the_source_alone(machine):
    source = machine.make_repo("repo-a")
    result = machine.refresh("repo-a")
    assert result.returncode == 0, result.stderr
    worktree = machine.index_root / "repo-a"

    assert_source_untouched(machine, source)

    # R2
    assert machine.git(worktree, "rev-parse", "HEAD") == machine.origin_head("repo-a")
    with pytest.raises(subprocess.CalledProcessError):
        machine.git(worktree, "symbolic-ref", "-q", "HEAD")
    assert "locked GitNexus canonical index" in machine.git(source, "worktree", "list", "--porcelain")

    # R3
    rows = machine.registry()
    assert [(row["name"], os.path.realpath(row["path"])) for row in rows] == [
        ("repo-a", os.path.realpath(worktree))
    ]


def test_refresh_passes_the_flags_the_shared_host_needs(machine):
    machine.make_repo("repo-a")
    assert machine.refresh("repo-a").returncode == 0
    call = machine.analyze_calls()[-1]
    assert call[0] == "analyze"
    assert call[call.index("--name") + 1] == "repo-a"
    assert call[call.index("--workers") + 1] == "4"
    assert call[call.index("--worker-timeout") + 1] == "120"
    assert call[call.index("--default-branch") + 1] == "main"
    assert "--no-stats" in call
    assert "--skip-skills" in call
    assert "--index-only" in call


def test_write_block_keeps_the_generated_diff_and_the_next_refresh_refuses_it(machine):
    machine.make_repo("repo-a")
    result = machine.refresh("repo-a", "--write-block", FAKE_NODE_MODE="write-block")
    assert result.returncode == 0, result.stderr
    assert "--index-only" not in machine.analyze_calls()[-1]
    assert (machine.index_root / "repo-a/tracked.txt").read_text() == "generated block\n"

    before = len(machine.analyze_calls())
    second = machine.refresh("repo-a")
    assert second.returncode == 1
    assert "holds local changes" in second.stderr
    assert len(machine.analyze_calls()) == before


def test_a_second_refresh_follows_origin(machine):
    source = machine.make_repo("repo-a")
    assert machine.refresh("repo-a").returncode == 0
    commit = machine.push_commit("repo-a", "second")
    result = machine.refresh("repo-a")
    assert result.returncode == 0, result.stderr
    assert machine.git(machine.index_root / "repo-a", "rev-parse", "HEAD") == commit
    assert machine.registry()[0]["lastCommit"] == commit
    assert_source_untouched(machine, source)


def test_refresh_clears_this_repos_other_rows_and_keeps_the_rest(machine):
    machine.make_repo("repo-a")
    same_name = machine.add_row("repo-a", version=43)
    same_origin = machine.add_row("slug-1", version=40, remote="https://github.com/o/repo-a.git")
    unrelated = machine.add_row("other", version=42, remote="https://github.com/o/other.git")
    result = machine.refresh("repo-a")
    assert result.returncode == 0, result.stderr

    # R3 and R4
    assert sorted(row["name"] for row in machine.registry()) == ["other", "repo-a"]
    for row in (same_name, same_origin, unrelated):
        assert Path(row["storagePath"], "lbug").exists()
    ledger = (machine.gitnexus_home / "gitnexus-index-pruned.jsonl").read_text().splitlines()
    assert {json.loads(line)["path"] for line in ledger} == {same_name["path"], same_origin["path"]}


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("crash", "analyze failed"),
        ("newer-engine", "cannot open"),
        ("wrong-commit", "records commit"),
        ("skip-register", "expected one registry row"),
        ("dirty", "local changes after indexing"),
    ],
)
def test_refresh_fails_when_the_index_is_not_what_it_asked_for(machine, mode, message):
    # R5
    machine.make_repo("repo-a")
    result = machine.refresh("repo-a", FAKE_NODE_MODE=mode)
    assert result.returncode == 1
    assert message in result.stderr


def test_refresh_waits_for_a_quieter_host(machine):
    machine.make_repo("repo-a")
    result = machine.run("refresh", "repo-a", "--max-load", "-1")
    assert result.returncode == 75
    assert "exceeds" in result.stderr
    assert machine.analyze_calls() == []
    assert not (machine.index_root / "repo-a").exists()


def test_refresh_runs_one_at_a_time(machine):
    machine.make_repo("repo-a")
    with open(machine.gitnexus_home / "gitnexus-index.lock", "a+") as handle:
        handle.write("4242")
        handle.flush()
        fcntl.flock(handle, fcntl.LOCK_EX)
        result = machine.refresh("repo-a")
    assert result.returncode == 75
    assert "pid 4242" in result.stderr
    assert machine.analyze_calls() == []


def test_a_held_lock_ends_with_its_holder(machine):
    machine.make_repo("repo-a")
    holder = subprocess.run(
        [
            sys.executable,
            "-c",
            "import fcntl,os,sys; f=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR); fcntl.flock(f,fcntl.LOCK_EX)",
            str(machine.gitnexus_home / "gitnexus-index.lock"),
        ],
        check=False,
        timeout=TIMEOUT_SECONDS,
    )
    assert holder.returncode == 0
    assert machine.refresh("repo-a").returncode == 0


def test_refresh_refuses_a_worktree_from_another_repository(machine):
    machine.make_repo("repo-a")
    other = machine.make_repo("repo-b")
    machine.git(other, "worktree", "add", "--quiet", "--detach", str(machine.index_root / "repo-a"))
    result = machine.refresh("repo-a")
    assert result.returncode == 1
    assert "another repository" in result.stderr


def test_refresh_needs_a_checkout(machine):
    result = machine.refresh("missing")
    assert result.returncode == 1
    assert "no checkout" in result.stderr


def test_refresh_stops_on_an_unmeasured_engine(machine):
    machine.make_repo("repo-a")
    machine.install_build(version="1.7.0", engine="0.22.0")
    result = machine.refresh("repo-a")
    assert result.returncode == 1
    assert "no measured storage versions" in result.stderr
    assert machine.analyze_calls() == []


# Doctor
@pytest.fixture
def healthy(machine):
    machine.make_repo("axiom-corpus")
    machine.make_repo("axiom-api")
    assert machine.refresh("axiom-corpus").returncode == 0
    assert machine.refresh("axiom-api").returncode == 0
    machine.write_healthy_configs()
    return machine


def fail_lines(result):
    return [line for line in result.stdout.splitlines() if line.startswith("FAIL")]


def test_doctor_passes_a_healthy_machine(healthy):
    result = healthy.run("doctor")
    assert result.returncode == 0, result.stdout
    assert result.stdout.strip().endswith("healthy")


def test_doctor_catches_a_stale_mcp_launch_path(healthy):
    config = json.loads((healthy.home / ".mcp.json").read_text())
    config["mcpServers"]["gitnexus"]["args"][0] = str(
        healthy.home / ".local/share/gitnexus/node_modules/.bin/gitnexus"
    )
    (healthy.home / ".mcp.json").write_text(json.dumps(config))
    result = healthy.run("doctor")
    assert result.returncode == 1
    assert any("launch:claude" in line for line in fail_lines(result))


def test_doctor_catches_a_floating_cursor_launcher(healthy):
    floating = {"mcpServers": {"gitnexus": {"command": "bunx", "args": ["-y", "gitnexus@latest", "mcp"]}}}
    (healthy.home / ".cursor/mcp.json").write_text(json.dumps(floating))
    result = healthy.run("doctor")
    assert result.returncode == 1
    assert any("launch:cursor" in line for line in fail_lines(result))


def test_doctor_rejects_a_launch_path_that_skips_the_stable_symlink(healthy):
    versioned = str(healthy.current.parent / "gitnexus-1.6.12/node_modules/.bin/gitnexus")
    config = {"mcpServers": {"gitnexus": {"command": "node", "args": [versioned, "mcp"]}}}
    (healthy.home / ".mcp.json").write_text(json.dumps(config))
    result = healthy.run("doctor")
    assert any("launch:claude" in line for line in fail_lines(result))


def test_doctor_catches_an_older_build_on_path(healthy):
    older = healthy.root / "older-bin"
    make_executable(older / "gitnexus", "#!/bin/sh\n")
    result = healthy.run("doctor", PATH=f"{older}:{healthy.environment['PATH']}")
    assert result.returncode == 1
    assert any(f"path:{older}/gitnexus" in line for line in fail_lines(result))


def test_doctor_needs_gitnexus_on_path(healthy):
    (healthy.bin / "gitnexus").unlink()
    result = healthy.run("doctor")
    assert any(line.startswith("FAIL path:") for line in fail_lines(result))


def test_doctor_catches_a_hook_on_the_old_install(healthy):
    hook = healthy.home / ".claude/hooks/gitnexus/gitnexus-hook.cjs"
    hook.write_text('let cliPath = "/somewhere/gitnexus/node_modules/gitnexus/dist/cli/index.js";\n')
    result = healthy.run("doctor")
    assert any(line.startswith("FAIL hook") for line in fail_lines(result))


def test_doctor_catches_a_pin_the_install_does_not_match(healthy):
    healthy.install_build(version="1.6.12", pinned="1.6.11")
    result = healthy.run("doctor")
    assert any(line.startswith("FAIL build") for line in fail_lines(result))


def test_doctor_reports_a_missing_canonical_index(machine):
    machine.write_healthy_configs()
    result = machine.run("doctor")
    assert any("index:axiom-corpus" in line for line in fail_lines(result))
    assert any("index:axiom-api" in line for line in fail_lines(result))


def test_doctor_reports_unmanaged_duplicates_it_cannot_settle(healthy):
    healthy.add_row("twin", version=42, remote="https://github.com/o/twin.git")
    healthy.add_row("twin", version=42, remote="https://github.com/o/twin.git")
    result = healthy.run("doctor", "--fix")
    assert result.returncode == 1
    assert any("duplicates: twin" in line for line in fail_lines(result))
    assert sum(row["name"] == "twin" for row in healthy.registry()) == 2


def test_doctor_only_reports_until_asked_to_fix(healthy):
    healthy.add_row("dead", version=43)
    before = healthy.registry()
    result = healthy.run("doctor")
    assert result.returncode == 1
    assert any("unreadable-database" in line for line in fail_lines(result))
    assert healthy.registry() == before


def test_doctor_fix_removes_rows_and_keeps_storage(healthy):
    dead = healthy.add_row("dead", version=43)
    empty = healthy.add_row("empty", version=None)
    gone = healthy.add_row("gone", exists=False)
    copy = healthy.add_row("slug-9", version=40, remote="git@github.com:o/axiom-api.git")
    keep = healthy.add_row("keeper", version=40, remote="https://github.com/o/keeper.git")

    result = healthy.run("doctor", "--fix")
    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(row["name"] for row in healthy.registry()) == ["axiom-api", "axiom-corpus", "keeper"]
    for row in (dead, copy, keep):
        assert Path(row["storagePath"], "lbug").exists()

    ledger = [
        json.loads(line)
        for line in (healthy.gitnexus_home / "gitnexus-index-pruned.jsonl").read_text().splitlines()
    ]
    assert {(row["path"], row["reason"]) for row in ledger} == {
        (dead["path"], "unreadable-database"),
        (empty["path"], "no-database"),
        (gone["path"], "missing-directory"),
        (copy["path"], "worktree-of-managed-repo"),
    }

    # P4 at the command line: a second fix changes nothing.
    before = healthy.registry()
    assert healthy.run("doctor", "--fix").returncode == 0
    assert healthy.registry() == before


def test_doctor_fix_never_prunes_under_an_unmeasured_engine(healthy):
    # An unmeasured engine reads no versions we know of; pruning then would empty the registry.
    healthy.add_row("keeper", version=40, remote="https://github.com/o/keeper.git")
    before = healthy.registry()
    healthy.install_build(version="1.7.0", engine="0.22.0")
    result = healthy.run("doctor", "--fix")
    assert result.returncode == 1
    assert healthy.registry() == before
    report = healthy.run("doctor")
    assert any(line.startswith("FAIL engine") for line in fail_lines(report))
    assert any(line.startswith("FAIL registry") for line in fail_lines(report))
    assert healthy.registry() == before


def write_probe_config(machine, server: Path) -> None:
    # The launcher path stays in args so the launch check passes; the fake server answers.
    launcher = str(machine.current / "node_modules/.bin/gitnexus")
    config = {"mcpServers": {"gitnexus": {"command": str(server), "args": [launcher, "mcp"]}}}
    (machine.home / ".mcp.json").write_text(json.dumps(config))


def test_doctor_probe_opens_every_index_through_the_configured_server(healthy):
    server = healthy.bin / "fake-mcp"
    make_python_executable(server, FAKE_MCP_SERVER)
    write_probe_config(healthy, server)
    result = healthy.run("doctor", "--probe")
    assert result.returncode == 0, result.stdout
    assert "ok   probe:axiom-corpus" in result.stdout
    assert "ok   probe:axiom-api" in result.stdout

    failing = healthy.run("doctor", "--probe", FAKE_MCP_FAILING='["axiom-api"]')
    assert failing.returncode == 1
    assert any("probe:axiom-api" in line and "different version" in line for line in fail_lines(failing))


def test_doctor_probe_reports_a_server_that_exits(healthy):
    server = healthy.bin / "dead-mcp"
    make_executable(server, "#!/bin/sh\nexit 0\n")
    write_probe_config(healthy, server)
    result = healthy.run("doctor", "--probe")
    assert result.returncode == 1
    assert any(line.startswith("FAIL probe:") and "exited" in line for line in fail_lines(result))


# The Grep and Glob hook
@pytest.mark.skipif(REAL_NODE is None, reason="no node on this machine")
class TestHook:
    def run_hook(self, home: Path, cwd: Path, path_prefix: Path) -> subprocess.CompletedProcess:
        payload = {
            "hook_event_name": "PreToolUse",
            "cwd": str(cwd),
            "tool_name": "Grep",
            "tool_input": {"pattern": "some_symbol"},
        }
        return subprocess.run(
            [REAL_NODE, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=60,
            env={"HOME": str(home), "PATH": f"{path_prefix}:/usr/bin:/bin"},
            check=False,
        )

    def make_cwd(self, root: Path) -> Path:
        cwd = root / "repo"
        (cwd / ".gitnexus").mkdir(parents=True)
        return cwd

    def make_floating_runners(self, root: Path) -> tuple[Path, Path]:
        """Put recording stand-ins for every floating runner on PATH."""
        runners = root / "runners"
        marker = root / "floating-runner-ran"
        for runner in ("npx", "bunx", "pnpm", "yarn"):
            make_executable(runners / runner, f'#!/bin/sh\ntouch "{marker}"\n')
        return runners, marker

    def test_hook_adds_nothing_and_fetches_nothing_without_the_pinned_build(self, tmp_path):
        runners, marker = self.make_floating_runners(tmp_path)
        result = self.run_hook(tmp_path / "home", self.make_cwd(tmp_path), runners)
        assert result.returncode == 0
        assert result.stdout == ""
        assert not marker.exists()

    def test_hook_runs_the_pinned_build(self, tmp_path):
        runners, marker = self.make_floating_runners(tmp_path)
        home = tmp_path / "home"
        cli = home / ".local/share/gitnexus-current/node_modules/gitnexus/dist/cli/index.js"
        make_executable(cli, 'process.stderr.write("graph context for " + process.argv.slice(2).join(" "));\n')
        result = self.run_hook(home, self.make_cwd(tmp_path), runners)
        assert result.returncode == 0, result.stderr
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        assert context == "graph context for augment -- some_symbol"
        assert not marker.exists()


# The real build, when this machine has it
@pytest.mark.skipif(
    not (REAL_CURRENT / "node_modules/gitnexus/dist/cli/index.js").exists() or REAL_NODE is None,
    reason="no pinned GitNexus install on this machine",
)
class TestRealBuild:
    """The same flow against the pinned build, with a throwaway registry."""

    @pytest.fixture
    def real(self, tmp_path):
        machine = Machine(tmp_path)
        machine.current = REAL_CURRENT
        node_directory = os.path.dirname(REAL_NODE)
        machine.environment.update(
            GITNEXUS_INDEX_CURRENT=str(REAL_CURRENT),
            GITNEXUS_INDEX_NODE=REAL_NODE,
            PATH=os.pathsep.join([node_directory, GIT_DIRECTORY, "/usr/bin", "/bin"]),
        )
        return machine

    def make_python_repo(self, machine, repo):
        source = machine.make_repo(repo)
        seed = machine.root / "seeds" / repo
        (seed / "app.py").write_text(
            textwrap.dedent(
                """\
                def helper():
                    return 1


                def caller():
                    return helper()
                """
            )
        )
        (seed / "CLAUDE.md").write_text(
            "Human section above.\n\n<!-- gitnexus:start -->\nindexed by GitNexus as **wrong** old.\n"
            "<!-- gitnexus:end -->\n\nHuman section below.\n"
        )
        machine.git(seed, "add", "-A")
        machine.git(seed, "commit", "--quiet", "-m", "code")
        machine.git(seed, "push", "--quiet", "origin", "main")
        return source

    def test_real_build_refresh_unregister_and_probe(self, real):
        source = self.make_python_repo(real, "axiom-api")
        stale = real.add_row("axiom-api", version=43)

        result = real.refresh("axiom-api")
        assert result.returncode == 0, result.stdout + result.stderr
        worktree = real.index_root / "axiom-api"
        assert_source_untouched(real, source)
        assert [row["name"] for row in real.registry()] == ["axiom-api"]
        assert os.path.realpath(real.registry()[0]["path"]) == os.path.realpath(worktree)
        assert Path(stale["storagePath"], "lbug").exists()
        assert real.git(worktree, "status", "--porcelain") == ""

        # An up-to-date refresh stays healthy, and so does one that follows a new commit.
        assert real.refresh("axiom-api").returncode == 0
        commit = real.push_commit("axiom-api", "more")
        again = real.refresh("axiom-api")
        assert again.returncode == 0, again.stdout + again.stderr
        assert real.registry()[0]["lastCommit"] == commit

        launcher = str(REAL_CURRENT / "node_modules/.bin/gitnexus")
        (real.home / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"gitnexus": {"command": REAL_NODE, "args": [launcher, "mcp"]}}})
        )
        doctor = real.run("doctor", "--probe")
        assert "ok   probe:axiom-api" in doctor.stdout, doctor.stdout

    def test_real_build_probe_catches_a_database_it_cannot_open(self, real):
        self.make_python_repo(real, "axiom-api")
        assert real.refresh("axiom-api").returncode == 0
        lbug = real.index_root / "axiom-api/.gitnexus/lbug"
        header = bytearray(lbug.read_bytes())
        header[4:12] = struct.pack("<Q", 43)
        lbug.write_bytes(bytes(header))
        launcher = str(REAL_CURRENT / "node_modules/.bin/gitnexus")
        (real.home / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"gitnexus": {"command": REAL_NODE, "args": [launcher, "mcp"]}}})
        )
        doctor = real.run("doctor", "--probe")
        assert any(line.startswith("FAIL probe:axiom-api") for line in fail_lines(doctor)), doctor.stdout

    def test_real_build_write_block_regenerates_the_block_in_place(self, real):
        self.make_python_repo(real, "axiom-api")
        result = real.refresh("axiom-api", "--write-block")
        assert result.returncode == 0, result.stdout + result.stderr
        text = (real.index_root / "axiom-api/CLAUDE.md").read_text()
        assert "indexed by GitNexus as **axiom-api**" in text
        assert "**wrong**" not in text
        assert "Human section above." in text
        assert "Human section below." in text
