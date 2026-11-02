"""Tests for hooks/auto-commit-wip.sh, the PreCompact hook that commits work in progress.

Run: uv run --no-project --with pytest --with hypothesis pytest tests/test_auto_commit_wip.py -q -p no:cacheprovider

They run the real script with /bin/bash against real git repositories under the pytest temp folder.
$HOME, $TMPDIR and git's global config point into that folder, so nothing of the user's is read or
written. AUTO_COMMIT_WIP_HOOK names another copy of the script to test.

Invariants, for every repository layout and every dirty tree:
  S1  in a shared main checkout (the git dir is the common dir, and the repository has a linked
      worktree, or the branch, or the branch being rebased, is main, master or origin/HEAD's, or the
      checkout is ~/chief-of-staff) the hook writes nothing: no file under .git changes (refs,
      index, reflogs, config, locks) and no working file changes. It prints one "Not
      auto-committing" line naming the rules that held when there are changes, and nothing when
      there are none;
  S2  anywhere else (a linked worktree, a feature branch in a repository with no linked worktree)
      it commits the work in progress as before: one new commit on the current branch, whose parent
      is the old HEAD, and no other ref moves;
  S3  it never changes, moves or removes a working file, and another worktree's HEAD, index and
      files are never touched;
  S4  it exits 0 with nothing on stderr.
The property test checks S1-S4 against a model of the rules (`shared_reasons`), so the bash
script and its stated rules are tested against each other.

Invariants of the sweep rules, for every tree where the hook does commit (`new_in_commit` is what a
commit adds, not counting an exact rename of a file the same commit deletes):
  N1  new_in_commit has at most MAX_NEW_FILES paths, and when more than that would enter, it is
      empty: nothing is taken "up to the limit";
  N2  no path added by a commit has a secret-looking name, renames included, whoever staged it;
  N3  tracked changes are committed whatever N1 and N2 left out;
  N4  every file left out stays on disk byte for byte, stays untracked, and the output gives the
      count and never a file's contents;
  N5  a file held back by the limit is not hashed into the object store, unless it was already in
      the index (staged, or added with intent-to-add, which `git add -u` fills in);
  N6  the two scan paths (fast, and slow when a name contains a newline) stage the same files;
  N7  N1 and N2 hold when another process changes the index while the hook runs, and what it stages
      after the hook's last check of the real index stays staged. With no temporary folder the hook
      commits from the real index, so this covers only what it staged before its checks. A hook
      whose HEAD moved by its last compare commits nothing. After that compare a commit lands only on
      the branch and parent the rules judged, so none reverses another session's or reaches another
      branch. A detached start names no ref: a branch at that commit gets the commit, whole.
The property test checks N1-N4 against a model of the rules (`expected_new`)."""
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

HOOK = Path(os.environ.get("AUTO_COMMIT_WIP_HOOK") or Path(__file__).resolve().parents[1] / "hooks" / "auto-commit-wip.sh")
MB = 1024 * 1024
MAX_NEW = 25   # a literal: read from the hook, it would move with any change to the limit
LIST = "~/chief-of-staff is on this hook's list of shared checkouts"


def env_for(home: Path, **extra) -> dict:
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(home / "tmp"), "LC_ALL": "C",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false"}
    env.update({k: str(v) for k, v in extra.items()})
    return env


def git(where: Path, *args: str, home: Path, check: bool = True, **env) -> str:
    r = subprocess.run(["git", "-C", str(where), *args], capture_output=True, env=env_for(home, **env))
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace')}")
    return r.stdout.decode(errors="surrogateescape")


def write(top: Path, files: dict) -> None:
    for path, body in files.items():
        f = top / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)


def make_repo(home: Path, name: str = "repo", branch: str = "work", commit: bool = True) -> Path:
    """A repository at home/name with one commit on `branch` (or none); home is $HOME for the hook."""
    (home / "tmp").mkdir(parents=True, exist_ok=True)
    repo = home / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", branch, home=home)
    if commit:
        write(repo, {"README.md": b"readme\n", "src/app.py": b"print('v1')\n", "notes.txt": b"notes\n"})
        git(repo, "add", "-A", home=home)
        git(repo, "commit", "-q", "-m", "base", home=home)
    return repo


def add_worktree(repo: Path, home: Path, name: str = "wt", branch: str = "side") -> Path:
    wt = home / name
    git(repo, "worktree", "add", "-q", "-b", branch, str(wt), home=home)
    return wt


def hook(where: Path, home: Path, **env) -> str:
    """Run the hook and return its output; checks S4 on every call."""
    r = subprocess.run(["/bin/bash", str(HOOK)], cwd=where, capture_output=True, env=env_for(home, **env))
    assert r.returncode == 0, r.stderr.decode(errors="replace")                                    # S4
    assert r.stderr == b"", r.stderr.decode(errors="replace")                                      # S4
    return r.stdout.decode(errors="replace")


def commits(top: Path, home: Path, rev: str = "HEAD") -> list[str]:
    return git(top, "log", "--format=%s", rev, home=home).splitlines()


def tracked(top: Path, home: Path, rev: str = "HEAD") -> set[str]:
    return set(git(top, "ls-tree", "-r", "-z", "--name-only", rev, home=home).split("\0")) - {""}


def refs(top: Path, home: Path) -> str:
    """Every ref and every worktree's HEAD, so a moved branch or a moved detached HEAD shows."""
    heads = git(top, "worktree", "list", "--porcelain", home=home)
    return git(top, "for-each-ref", "--format=%(refname) %(objectname)", home=home) + heads


def index_state(top: Path, home: Path) -> tuple:
    """(bytes, mtime) of this checkout's index file: a write of any kind changes the mtime."""
    p = Path(git(top, "rev-parse", "--path-format=absolute", "--git-path", "index", home=home).strip())
    if not p.exists():
        return (None, None)
    return (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)


def disk(top: Path) -> dict:
    """Every working file with its bytes, inode and mtime (.git excluded)."""
    out = {}
    for d, dirs, files in os.walk(top):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            p = Path(d) / f
            s = os.lstat(p)
            out[os.path.relpath(p, top)] = (p.read_bytes() if not p.is_symlink() else os.readlink(p), s.st_ino, s.st_mtime_ns)
    return out


def dotgit(top: Path, home: Path) -> dict:
    """Every file and folder under the repository's common git dir, with bytes and mtime: refs,
    index, reflogs, config, FETCH_HEAD, worktree metadata, locks."""
    common = Path(git(top, "rev-parse", "--path-format=absolute", "--git-common-dir", home=home).strip())
    out = {}
    for d, dirs, files in os.walk(common):
        out[os.path.relpath(d, common) + "/"] = os.lstat(d).st_mtime_ns
        for f in files:
            p = Path(d) / f
            out[os.path.relpath(p, common)] = (hashlib.sha256(p.read_bytes()).hexdigest(), os.lstat(p).st_mtime_ns)
    return out


def untouched(home: Path, top: Path) -> tuple:
    """Everything S1 promises not to write."""
    return (refs(top, home), index_state(top, home), disk(top), dotgit(top, home))


def checkout_state(home: Path, *tops: Path) -> tuple:
    """What belongs to each checkout alone: its HEAD (and branch), index and files. Refs are shared
    by all worktrees of a repository, so another worktree's own commit is not a change here."""
    return tuple((git(t, "rev-parse", "HEAD", home=home), git(t, "branch", "--show-current", home=home),
                  index_state(t, home), disk(t)) for t in tops)


def dirty(top: Path, home: Path) -> None:
    """Another session's work: a tracked edit, a staged edit, a deletion and a file in a new folder."""
    write(top, {"src/app.py": b"print('theirs')\n", "notes.txt": b"staged by someone\n", "drafts/email.md": b"draft\n"})
    git(top, "add", "notes.txt", home=home)
    (top / "README.md").unlink()


def shared_line(name: str, branch: str, reasons: str) -> str:
    return (f"Not auto-committing in {name} on branch {branch} before context compact: "
            f"it is a shared main checkout ({reasons}).")


def default_line(name: str, branch: str, reason: str) -> str:
    return (f"Not auto-committing in {name} on branch {branch} before context compact: "
            f"it is the main checkout and {reason}, which takes deliberate commits only.")


# --- S1: a shared main checkout is left alone ------------------------------------------------------

def test_a_main_checkout_with_a_linked_worktree_is_left_alone(tmp_path):
    repo = make_repo(tmp_path)
    add_worktree(repo, tmp_path)
    dirty(repo, tmp_path)
    before = untouched(tmp_path, repo)
    out = hook(repo, tmp_path)
    assert out.startswith(shared_line("repo", "work", "the repository has 1 linked worktree(s)"))
    assert ("Left 3 changed tracked path(s) and 1 untracked path(s) (a new folder counts once) as they are, "
            "on disk; other sessions' work may be among them.") in out
    assert untouched(tmp_path, repo) == before
    assert commits(repo, tmp_path) == ["base"]
    assert git(repo, "diff", "--cached", "--name-only", home=tmp_path) == "notes.txt\n"   # still staged, as left


def test_it_is_left_alone_from_a_subfolder_too(tmp_path):
    repo = make_repo(tmp_path)
    add_worktree(repo, tmp_path)
    dirty(repo, tmp_path)
    before = untouched(tmp_path, repo)
    assert hook(repo / "src", tmp_path).startswith(shared_line("repo", "work", "the repository has 1 linked worktree(s)"))
    assert untouched(tmp_path, repo) == before


def test_a_prunable_linked_worktree_still_counts(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(repo, tmp_path)
    shutil.rmtree(wt)                                              # folder gone, metadata not pruned
    dirty(repo, tmp_path)
    before = untouched(tmp_path, repo)
    assert "the repository has 1 linked worktree(s)" in hook(repo, tmp_path)
    assert untouched(tmp_path, repo) == before


@pytest.mark.parametrize("branch", ["main", "master"])
def test_the_default_branch_of_a_main_checkout_is_left_alone(tmp_path, branch):
    repo = make_repo(tmp_path, branch=branch)
    dirty(repo, tmp_path)
    before = untouched(tmp_path, repo)
    out = hook(repo, tmp_path)
    assert out.startswith(default_line("repo", branch, f"{branch} is the default branch"))
    assert "other sessions' work" not in out and "work on a branch of your own" in out
    assert untouched(tmp_path, repo) == before


def test_origin_head_names_the_default_branch(tmp_path):
    seed = make_repo(tmp_path, name="seed", branch="trunk")
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(tmp_path / "origin.git"), home=tmp_path)
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(tmp_path / "clone"), home=tmp_path)
    clone = tmp_path / "clone"
    assert git(clone, "symbolic-ref", "refs/remotes/origin/HEAD", home=tmp_path).strip() == "refs/remotes/origin/trunk"
    git(clone, "branch", "origin/trunk", home=tmp_path)             # makes `symbolic-ref --short` ambiguous
    dirty(clone, tmp_path)
    before = untouched(tmp_path, clone)
    assert hook(clone, tmp_path).startswith(default_line("clone", "trunk", "trunk is the default branch"))
    assert untouched(tmp_path, clone) == before
    git(clone, "checkout", "-q", "-b", "feature", home=tmp_path)    # a feature branch is not
    assert "Auto-committed" in hook(clone, tmp_path)
    assert commits(clone, tmp_path)[:2] == ["fixup! base", "base"]


def test_a_rebase_of_the_default_branch_is_left_alone(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    for msg in ("c1", "c2"):
        write(repo, {f"{msg}.txt": msg.encode()})
        git(repo, "add", "-A", home=tmp_path)
        git(repo, "commit", "-q", "-m", msg, home=tmp_path)
    git(repo, "rebase", "-q", "-i", "HEAD~2", home=tmp_path, GIT_SEQUENCE_EDITOR="sed -i.bak -e '1s/^pick/edit/'")
    assert git(repo, "branch", "--show-current", home=tmp_path) == ""   # stopped at c1, detached
    write(repo, {"other.txt": b"someone else's\n"})
    before = untouched(tmp_path, repo)
    out = hook(repo, tmp_path)
    assert out.startswith(default_line("repo", "detached", "main, being rebased, is the default branch"))
    assert untouched(tmp_path, repo) == before
    git(repo, "rebase", "--continue", home=tmp_path)
    assert commits(repo, tmp_path, "main") == ["c2", "c1", "base"]


def test_an_unborn_default_branch_is_left_alone(tmp_path):
    repo = make_repo(tmp_path, branch="main", commit=False)
    write(repo, {"a.md": b"a\n"})
    out = hook(repo, tmp_path)
    assert out.startswith(default_line("repo", "main", "main is the default branch"))
    assert "Left 0 changed tracked path(s) and 1 untracked path(s)" in out
    assert git(repo, "rev-parse", "-q", "--verify", "HEAD", home=tmp_path, check=False) == ""


def test_chief_of_staff_is_on_the_list_on_any_branch(tmp_path):
    cos = make_repo(tmp_path, name="chief-of-staff", branch="side-branch")
    dirty(cos, tmp_path)
    before = untouched(tmp_path, cos)
    assert hook(cos, tmp_path).startswith(shared_line("chief-of-staff", "side-branch", LIST))
    assert untouched(tmp_path, cos) == before
    (tmp_path / "cos-link").symlink_to(cos)                        # reached through a symlink: same checkout
    assert LIST in hook(tmp_path / "cos-link", tmp_path)
    assert untouched(tmp_path, cos) == before


def test_chief_of_staff_is_found_when_home_is_a_symlink(tmp_path):
    real_home = tmp_path / "real-home"
    cos = make_repo(real_home, name="chief-of-staff", branch="side-branch")
    (tmp_path / "home-link").symlink_to(real_home)                 # $HOME/chief-of-staff is not a physical path
    dirty(cos, real_home)
    before = untouched(real_home, cos)
    assert LIST in hook(cos, tmp_path / "home-link")
    assert untouched(real_home, cos) == before


def test_every_rule_that_holds_is_named(tmp_path):
    cos = make_repo(tmp_path, name="chief-of-staff", branch="master")
    add_worktree(cos, tmp_path)
    add_worktree(cos, tmp_path, name="wt2", branch="side2")
    dirty(cos, tmp_path)
    assert hook(cos, tmp_path).startswith(shared_line(
        "chief-of-staff", "master", f"the repository has 2 linked worktree(s); master is the default branch; {LIST}"))


def test_a_clean_shared_checkout_prints_nothing_and_writes_nothing(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    add_worktree(repo, tmp_path)
    before = untouched(tmp_path, repo)
    assert hook(repo, tmp_path) == ""
    assert untouched(tmp_path, repo) == before


def test_a_name_with_a_newline_counts_once(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    write(repo, {"two\nlines.md": b"x\n", "plain.md": b"y\n"})
    assert "Left 0 changed tracked path(s) and 2 untracked path(s)" in hook(repo, tmp_path)


def test_an_index_lock_held_by_another_session_does_not_matter(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    dirty(repo, tmp_path)
    lock = repo / ".git" / "index.lock"
    lock.write_bytes(b"")                                          # someone else's git command is mid-write
    before = untouched(tmp_path, repo)
    assert "Left 3 changed tracked path(s) and 1 untracked path(s)" in hook(repo, tmp_path)
    assert untouched(tmp_path, repo) == before


def test_it_commits_nothing_if_git_cannot_name_the_git_dir(tmp_path):
    repo = make_repo(tmp_path)                                     # a feature branch: it would commit
    write(repo, {"src/app.py": b"print('v2')\n"})
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "git").write_text(f'#!/bin/bash\nfor a in "$@"; do [ "$a" = --git-dir ] && exit 128; done\n'
                              f'exec {shutil.which("git")} "$@"\n')
    (shim / "git").chmod(0o755)
    out = hook(repo, tmp_path, PATH=f"{shim}:{os.environ['PATH']}")
    assert "git did not name its git dir and common dir" in out
    assert commits(repo, tmp_path) == ["base"]


# --- S2: a linked worktree keeps the auto-commit -----------------------------------------------------

def test_a_linked_worktree_still_commits_its_own_work_only(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    wt = add_worktree(repo, tmp_path)
    dirty(repo, tmp_path)                                          # other sessions' files in the main checkout
    main_before = checkout_state(tmp_path, repo)                   # its HEAD, branch, index and files
    write(wt, {"src/app.py": b"print('mine')\n", "src/mine.py": b"x = 1\n"})
    out = hook(wt, tmp_path)
    assert "Auto-committed 2 file(s) in wt on branch side before context compact." in out
    assert commits(wt, tmp_path) == ["fixup! base", "base"]
    assert tracked(wt, tmp_path) == {"README.md", "src/app.py", "notes.txt", "src/mine.py"}
    assert checkout_state(tmp_path, repo) == main_before


def test_a_linked_worktree_of_chief_of_staff_still_commits(tmp_path):
    cos = make_repo(tmp_path, name="chief-of-staff", branch="master")
    wt = add_worktree(cos, tmp_path, name="cos-job")
    write(wt, {"bin/tool": b"#!/bin/sh\n"})
    assert "Auto-committed 1 file(s) in cos-job on branch side" in hook(wt, tmp_path)
    assert commits(cos, tmp_path, "master") == ["base"]


def test_a_feature_branch_without_linked_worktrees_still_commits(tmp_path):
    repo = make_repo(tmp_path, branch="work")
    write(repo, {"src/app.py": b"print('v2')\n", "src/new.py": b"x = 1\n"})
    assert "Auto-committed 2 file(s) in repo on branch work before context compact." in hook(repo, tmp_path)
    assert commits(repo, tmp_path) == ["fixup! base", "base"]


def test_an_unborn_feature_branch_gets_a_wip_commit(tmp_path):
    repo = make_repo(tmp_path, branch="scratch", commit=False)
    write(repo, {"a.md": b"a\n"})
    hook(repo, tmp_path)
    assert commits(repo, tmp_path) == ["WIP: auto-save before context compact (1 files on scratch)"]


def test_a_detached_head_without_linked_worktrees_still_commits(tmp_path):
    repo = make_repo(tmp_path, branch="work")
    git(repo, "checkout", "-q", "--detach", home=tmp_path)
    write(repo, {"src/app.py": b"v2\n"})
    assert "on branch detached" in hook(repo, tmp_path)
    assert git(repo, "rev-parse", "work", home=tmp_path) != git(repo, "rev-parse", "HEAD", home=tmp_path)


# --- the guards from before still hold ---------------------------------------------------------------

def test_logs_big_files_ignored_files_and_nested_repos_are_not_staged(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {".gitignore": b"out/\n", "out/gen.bin": b"ignored\n", "run.log": b"", "deep/Run.ERR.LOG": b"",
                 "ok.md": b"ok\n"})
    with open(repo / "big.bin", "wb") as f:                        # sparse: 60 MB apparent, no real bytes
        f.truncate(60 * MB)
    inner = repo / "vendor" / "inner"
    inner.mkdir(parents=True)
    git(inner, "init", "-q", home=tmp_path)
    out = hook(repo, tmp_path)
    assert tracked(repo, tmp_path) == {"README.md", "src/app.py", "notes.txt", ".gitignore", "ok.md"}
    assert "Skipped 3 untracked file(s) totalling 60 MB (1 over 50 MB, 2 *.log)" in out
    assert "Not added: 1 nested git repo(s): vendor/inner/." in out
    assert (repo / "run.log").exists() and (repo / "big.bin").exists() and (repo / "out" / "gen.bin").exists()


def test_a_tracked_file_renamed_into_a_skipped_name_is_kept_as_a_rename(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "notes.txt").rename(repo / "notes.log")
    out = hook(repo, tmp_path)
    assert "Kept 1 renamed tracked file(s) whose content was already in the repo: notes.log." in out
    assert "notes.log" in tracked(repo, tmp_path) and "notes.txt" not in tracked(repo, tmp_path)


def test_a_nested_repo_the_size_of_a_deleted_file_does_not_cost_the_rename(tmp_path):
    """git hash-object fails on a directory, and one failure means nothing counts as moved."""
    repo = make_repo(tmp_path)
    inner = repo / "inner"
    inner.mkdir()
    git(inner, "init", "-q", home=tmp_path)
    write(repo, {"sized.txt": b"x" * inner.stat().st_size})
    git(repo, "add", "sized.txt", home=tmp_path)
    git(repo, "commit", "-qm", "sized", home=tmp_path)
    (repo / "sized.txt").rename(repo / "sized.log")
    out = hook(repo, tmp_path)
    assert "Kept 1 renamed tracked file(s) whose content was already in the repo: sized.log." in out
    assert "sized.log" in tracked(repo, tmp_path) and "sized.txt" not in tracked(repo, tmp_path)
    assert "Not added: 1 nested git repo(s): inner/." in out


def test_unmerged_paths_stop_it(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "other", home=tmp_path)
    write(repo, {"notes.txt": b"other\n"})
    git(repo, "commit", "-q", "-am", "other", home=tmp_path)
    git(repo, "checkout", "-q", "work", home=tmp_path)
    write(repo, {"notes.txt": b"work\n"})
    git(repo, "commit", "-q", "-am", "work", home=tmp_path)
    git(repo, "merge", "other", home=tmp_path, check=False)
    assert "unmerged paths" in hook(repo, tmp_path)
    assert commits(repo, tmp_path)[0] == "work"


def test_the_public_config_repo_and_its_worktrees_are_never_swept(tmp_path):
    claude = make_repo(tmp_path, name=".claude", branch="work")
    wt = add_worktree(claude, tmp_path, name="claude-wt")
    for where in (claude, wt):
        write(where, {"new.json": b"{}\n"})
        assert hook(where, tmp_path) == ""
    assert git(claude, "rev-list", "--all", "--count", home=tmp_path).strip() == "1"


# --- N1-N6: bulk sweeps and secret names --------------------------------------------------------------

def added_in_commit(top: Path, home: Path) -> set[str]:
    """Paths the last commit added, with renames counted as adds."""
    out = git(top, "diff-tree", "-r", "--root", "--no-commit-id", "--no-renames", "--diff-filter=A", "--name-only", "-z", "HEAD", home=home)
    return set(out.split("\0")) - {""}


def new_in_commit(top: Path, home: Path) -> set[str]:
    """Paths the last commit added that are not exact renames of a file it deleted."""
    out = git(top, "diff-tree", "-r", "--root", "--no-commit-id", "--find-renames=100%", "--diff-filter=A", "--name-only", "-z", "HEAD", home=home)
    return set(out.split("\0")) - {""}


def blob_stored(top: Path, home: Path, path: str) -> bool:
    """Whether the object store holds this working file's content (hash-object alone writes nothing)."""
    sha = git(top, "hash-object", "--", path, home=home).strip()
    return subprocess.run(["git", "-C", str(top), "cat-file", "-e", sha], env=env_for(home), capture_output=True).returncode == 0


def loose_objects(top: Path) -> int:
    return sum(len(f) for d, _, f in os.walk(top / ".git" / "objects"))


SECRET_NAMES = [".env", ".env.local", ".env.production", "config/.ENV", "prod.env", ".envrc", "id_rsa", "id_ed25519",
                "keys/deploy.pem", "server.key", "cert.p12", "app.keystore", "infra/prod.tfvars", "secrets.yml",
                "secrets/db.yml", "client_secret.json", "app-credentials.json", "password.txt", "notes/passwords.csv",
                "api_key.txt", "API-KEY", "deploy-signing-key", "conf/private_key", "gcp-key.json", "deploy-key",
                "bot-token.txt", "token", "creds.json", ".npmrc", ".pypirc", ".netrc", ".git-credentials", "auth.json",
                ".ssh/config", ".aws/config", "service-account.json", ".env-prod", ".env_prod", "env.prod",
                ".env.pub", ".env.example.local", ".env.sample.bak", "prod-example.pem", "real-sample.pem",
                "secrets.template.key", "server.key.bak", "id_rsa.old", "keyfile", "keys.txt", "privkey", "secretkey",
                "AuthKey_ABC.p8", "private.asc", "secring.gpg", "prod.tfstate.backup", "terraform.tfvars.json",
                "kubeconfig", ".my.cnf", ".mylogin.cnf", ".boto", ".yarnrc.yml", ".config/gh/hosts.yml",
                ".config/rclone/rclone.conf", ".vault_pass", "gha-creds-abc123.json", "firebase-adminsdk-x1.json",
                "oauth_tokens.json", "refresh-tokens.json", "access_tokens.txt", "prod.env.bak", "app.env.local",
                "app.env.staging", "docker.env.dev", "env.development", "priv.asc", "kubeconfig.yaml", "wp-config.php",
                "github_pat.txt", "api_tokens.txt", "vault_pass.txt", "mysecrettoken.txt"]
PLAIN_NAMES = ["CHANGES.md", "src/app2.py", ".env.example", ".env.sample", "secrets.example.yml", "id_ed25519.pub",
               "deploy-key.pub", "tokenizer.py", "design-tokens.css", "tokens.json", "hotkey.ts", "monkey.py",
               "secretary-of-state.md", "drafts/email.md", "environment.yml", "keyboard.md", "public.txt",
               "report.json.env.json"]


@pytest.mark.parametrize("name", SECRET_NAMES)
def test_a_secret_looking_name_is_never_staged(tmp_path, name):
    repo = make_repo(tmp_path)
    write(repo, {name: b"hunter2\n", "ok.md": b"ok\n"})
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == {"ok.md"}
    assert f"Left out 1 new file(s) with secret-looking names: {name} " in out
    assert "hunter2" not in out                                    # N4
    assert (repo / name).read_bytes() == b"hunter2\n"
    assert git(repo, "status", "--porcelain", home=tmp_path).startswith("?? ")
    assert not blob_stored(repo, tmp_path, name)                   # never hashed, so no copy under .git


@pytest.mark.parametrize("name", PLAIN_NAMES)
def test_an_ordinary_or_template_name_is_committed(tmp_path, name):
    repo = make_repo(tmp_path)
    write(repo, {name: b"plain\n"})
    out = hook(repo, tmp_path)
    assert name in added_in_commit(repo, tmp_path)
    assert "secret-looking" not in out


def test_a_secret_named_file_someone_staged_is_unstaged(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n", "staged.md": b"s\n", "src/app.py": b"print('v2')\n"})
    git(repo, "add", ".env", "staged.md", home=tmp_path)
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == {"staged.md"}
    assert "src/app.py" in tracked(repo, tmp_path)
    assert "Left out 1 new file(s) with secret-looking names: .env " in out
    assert ".env" not in tracked(repo, tmp_path) and (repo / ".env").exists()
    assert git(repo, "status", "--porcelain", home=tmp_path) == "?? .env\n"


@pytest.mark.parametrize("staged", [False, True])
def test_a_rename_into_a_secret_name_is_left_out(tmp_path, staged):
    """N2 has no rename exception: the deletion is committed, the new name stays untracked."""
    repo = make_repo(tmp_path)
    (repo / "notes.txt").rename(repo / ".env")
    if staged:
        git(repo, "add", "-A", home=tmp_path)
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == set()
    assert "notes.txt" not in tracked(repo, tmp_path) and ".env" not in tracked(repo, tmp_path)
    assert "secret-looking names: .env " in out and (repo / ".env").read_bytes() == b"notes\n"


def test_a_5000_file_sweep_commits_the_tracked_change_alone(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"src/app.py": b"print('mine')\n"})
    others = {f"lanes/lane{i % 40:02}/draft{i:04}.md": b"another session's draft %d\n" % i for i in range(5000)}
    write(repo, others)
    files = disk(repo)
    objects = loose_objects(repo)
    out = hook(repo, tmp_path)
    assert "Auto-committed 1 file(s) in repo on branch work before context compact." in out
    assert "Left out 5000 new file(s), over the limit of " in out and ", +4997 more" in out   # N4
    assert added_in_commit(repo, tmp_path) == set()                # N1
    assert git(repo, "show", "HEAD:src/app.py", home=tmp_path) == "print('mine')\n"            # N3
    assert commits(repo, tmp_path) == ["fixup! base", "base"]
    assert disk(repo) == files                                     # N4
    assert git(repo, "diff", "--cached", "--name-only", home=tmp_path) == ""
    assert loose_objects(repo) - objects <= 4                      # N5: a blob, two trees, a commit
    second = hook(repo, tmp_path)                                  # it stays held back on the next compact
    assert "Nothing to auto-commit" in second and "Left out 5000 new file(s)" in second
    assert commits(repo, tmp_path) == ["fixup! base", "base"]


def test_a_sweep_with_nothing_tracked_commits_nothing(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {f"x/{i}.md": b"n\n" for i in range(MAX_NEW + 1)})
    out = hook(repo, tmp_path)
    assert out.startswith("Nothing to auto-commit in repo on branch work")
    assert commits(repo, tmp_path) == ["base"]


@pytest.mark.parametrize("extra,committed", [(0, True), (1, False)])
def test_the_limit_is_exact(tmp_path, extra, committed):
    repo = make_repo(tmp_path)
    names = {f"f{i:03}.md" for i in range(MAX_NEW + extra)}
    write(repo, {n: b"n\n" for n in names})
    write(repo, {"src/app.py": b"print('v2')\n"})
    hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == (names if committed else set())


def test_files_the_commit_would_not_take_do_not_count_toward_the_limit(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {f"logs/{i}.log": b"l\n" for i in range(MAX_NEW + 5)})
    write(repo, {f"keys/{i}.pem": b"k\n" for i in range(MAX_NEW + 5)})
    write(repo, {"mine.md": b"mine\n"})
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == {"mine.md"}
    assert "over the limit" not in out
    assert f"Left out {MAX_NEW + 5} new file(s) with secret-looking names" in out


def test_files_someone_staged_count_toward_the_limit(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {f"staged/{i}.md": b"s\n" for i in range(MAX_NEW)})
    git(repo, "add", "staged", home=tmp_path)
    write(repo, {"one-more.md": b"n\n", "src/app.py": b"print('v2')\n"})
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == set()
    assert f"Left out {MAX_NEW + 1} new file(s), over the limit" in out
    assert git(repo, "diff", "--cached", "--name-only", home=tmp_path) == ""
    assert (repo / "staged" / "0.md").exists()


@pytest.mark.parametrize("n_loose", [MAX_NEW - 2, MAX_NEW + 1])     # under the limit alone, and over it
def test_staged_and_scanned_files_are_held_back_together(tmp_path, n_loose):
    repo = make_repo(tmp_path)
    write(repo, {f"staged/{i}.md": b"s\n" for i in range(3)})
    git(repo, "add", "staged", home=tmp_path)
    write(repo, {f"loose/{i}.md": b"n%d\n" % i for i in range(n_loose)})
    write(repo, {"src/app.py": b"print('v2')\n"})
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == set()                # all of it, not just the scanned part
    assert f"Left out {n_loose + 3} new file(s), over the limit" in out
    assert not blob_stored(repo, tmp_path, "loose/0.md")           # N5: stopped before staging


def test_a_staged_secret_does_not_count_toward_the_limit(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n", "keys/a.pem": b"k\n"})
    git(repo, "add", ".env", "keys/a.pem", home=tmp_path)
    names = {f"f{i:03}.md" for i in range(MAX_NEW)}
    write(repo, {n: b"n\n" for n in names})
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == names
    assert "Left out 2 new file(s) with secret-looking names" in out and "over the limit" not in out


@pytest.mark.parametrize("n", [MAX_NEW + 4, 1500])
def test_a_directory_rename_stays_a_rename_past_the_limit(tmp_path, n):
    repo = make_repo(tmp_path)
    write(repo, {f"old/{i}.md": f"content {i}\n".encode() for i in range(n)})
    git(repo, "add", "-A", home=tmp_path)
    git(repo, "commit", "-q", "-m", "more", home=tmp_path)
    (repo / "old").rename(repo / "new")
    out = hook(repo, tmp_path)
    assert "over the limit" not in out
    assert {f"new/{i}.md" for i in range(n)} <= tracked(repo, tmp_path)
    assert not any(t.startswith("old/") for t in tracked(repo, tmp_path))
    assert new_in_commit(repo, tmp_path) == set()


def test_renames_are_kept_when_new_files_go_over_the_limit(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "notes.txt").rename(repo / "moved.txt")
    write(repo, {f"x/{i}.md": b"n%d\n" % i for i in range(MAX_NEW + 1)})
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == {"moved.txt"}
    assert new_in_commit(repo, tmp_path) == set()
    assert "Kept 1 renamed tracked file(s) whose content was already in the repo: moved.txt." in out
    assert f"Left out {MAX_NEW + 1} new file(s), over the limit" in out and "moved.txt, " not in out
    assert f"work: x/0.md, x/1.md, x/10.md, +{MAX_NEW - 2} more" in out


def test_a_rename_does_not_use_up_the_limit(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "notes.txt").rename(repo / "moved.txt")
    names = {f"f{i:03}.md" for i in range(MAX_NEW)}                # the limit exactly, plus the rename
    write(repo, {n: b"n\n" for n in names})
    out = hook(repo, tmp_path)
    assert new_in_commit(repo, tmp_path) == names
    assert added_in_commit(repo, tmp_path) == names | {"moved.txt"}
    assert "over the limit" not in out


def test_a_new_file_of_the_same_size_as_a_deleted_one_is_not_a_rename(tmp_path):
    """Size only picks what to hash: these are held back, and N5 keeps them out of the object store."""
    repo = make_repo(tmp_path)
    (repo / "notes.txt").unlink()                                  # "notes\n": six bytes
    write(repo, {f"same/{i:03}.md": b"%05d\n" % i for i in range(MAX_NEW + 1)})
    out = hook(repo, tmp_path)
    assert f"Left out {MAX_NEW + 1} new file(s), over the limit" in out
    assert added_in_commit(repo, tmp_path) == set()
    assert not blob_stored(repo, tmp_path, "same/000.md")


def test_many_copies_of_one_deleted_file_are_not_renames(tmp_path):
    """One deletion pairs with one new path: identical copies must not pass as a rename each."""
    repo = make_repo(tmp_path)
    (repo / "notes.txt").unlink()
    write(repo, {f"copy/{i}.txt": b"notes\n" for i in range(MAX_NEW + 5)})
    out = hook(repo, tmp_path)
    assert len(new_in_commit(repo, tmp_path)) == 0
    assert len(added_in_commit(repo, tmp_path)) <= 1
    assert "over the limit" in out


def test_copies_of_a_deleted_file_do_not_make_room_for_fresh_files(tmp_path):
    """Each deletion excuses one path, so 10 copies and 20 fresh files stay 29 new paths, not 20."""
    repo = make_repo(tmp_path)
    (repo / "notes.txt").unlink()
    write(repo, {f"copy/{i}.txt": b"notes\n" for i in range(10)})
    write(repo, {f"fresh{i}.md": f"fresh {i}\n".encode() for i in range(MAX_NEW - 5)})
    out = hook(repo, tmp_path)
    assert new_in_commit(repo, tmp_path) == set()
    assert "Left out 29 new file(s), over the limit" in out
    assert not blob_stored(repo, tmp_path, "fresh1.md")


def test_a_staged_rename_leaves_no_deletion_for_a_copy_to_claim(tmp_path):
    """moved.txt already pairs with the deletion, so copy.txt is a new path and the 26 stay unhashed."""
    repo = make_repo(tmp_path)
    git(repo, "mv", "notes.txt", "moved.txt", home=tmp_path)
    write(repo, {"copy.txt": b"notes\n"})
    write(repo, {f"fresh{i}.md": f"fresh {i}\n".encode() for i in range(MAX_NEW)})
    out = hook(repo, tmp_path)
    assert f"Left out {MAX_NEW + 1} new file(s), over the limit" in out
    assert not blob_stored(repo, tmp_path, "fresh1.md")


def test_a_regular_file_is_no_rename_of_a_symlink_with_the_same_bytes(tmp_path):
    """Git does not pair them, so the deletion must not make room for fresh files."""
    repo = make_repo(tmp_path)
    (repo / "link").symlink_to("target.txt")
    git(repo, "add", "link", home=tmp_path)
    git(repo, "commit", "-q", "-m", "link", home=tmp_path)
    (repo / "link").unlink()
    write(repo, {"plain.txt": b"target.txt"})
    write(repo, {f"fresh{i}.md": f"fresh {i}\n".encode() for i in range(MAX_NEW)})
    out = hook(repo, tmp_path)
    assert f"Left out {MAX_NEW + 1} new file(s), over the limit" in out
    assert not blob_stored(repo, tmp_path, "fresh1.md")


def sweep_with_a_rename(repo: Path, extra: dict) -> None:
    """One rename that the limit depends on, and more fresh files than the limit takes."""
    (repo / "notes.txt").rename(repo / "moved.txt")
    write(repo, extra | {f"fresh{i}.md": f"fresh {i}\n".encode() for i in range(MAX_NEW + 5)})


def test_a_file_that_cannot_be_hashed_means_nothing_counts_as_moved(tmp_path):
    """A dangling link of the deleted size stops the batch after moved.txt; the short list counts for nothing."""
    repo = make_repo(tmp_path)
    sweep_with_a_rename(repo, {})
    (repo / "z-link").symlink_to("nosuch")                         # 6 bytes, like "notes\n"
    out = hook(repo, tmp_path)
    assert f"Left out {MAX_NEW + 7} new file(s), over the limit" in out
    assert added_in_commit(repo, tmp_path) == set()


def test_a_file_that_vanishes_before_the_size_match_means_nothing_counts_as_moved(tmp_path):
    """A size list one short shifts every later result by one, onto the wrong names."""
    repo = make_repo(tmp_path)
    write(repo, {"also.txt": b"also.\n"})
    git(repo, "add", "-A", home=tmp_path)
    git(repo, "commit", "-q", "-m", "also", home=tmp_path)
    (repo / "also.txt").rename(repo / "moved2.txt")
    sweep_with_a_rename(repo, {"a-gone.md": b"g\n"})
    real = shutil.which("stat")
    path = shim(tmp_path, "stat", f"""[ "$2" = %z ] && [ $# -gt 3 ] && rm -f a-gone.md\nexec {real} "$@\"""")
    out = hook(repo, tmp_path, PATH=path)
    assert f"Left out {MAX_NEW + 8} new file(s), over the limit" in out
    assert added_in_commit(repo, tmp_path) == set()


@pytest.mark.parametrize("slow_path", [False, True])
def test_several_skipped_renames_stay_in_step(tmp_path, slow_path):
    repo = make_repo(tmp_path)
    write(repo, {f"old{i}.txt": f"content {i}\n".encode() for i in range(6)})
    git(repo, "add", "-A", home=tmp_path)
    git(repo, "commit", "-q", "-m", "old", home=tmp_path)
    middle = "c\nd.log" if slow_path else "c d.log"
    targets = ["a\tb.log", middle, "e\\f.log", "password.log", "secret.log", "z.log"]
    for i, target in enumerate(targets):
        (repo / f"old{i}.txt").rename(repo / target)
    write(repo, {"b-other.log": b"not a rename\n", "y-other.log": b"nor this\n"})
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == {"a\tb.log", middle, "e\\f.log", "z.log"}
    assert "Kept 4 renamed tracked file(s)" in out
    assert "Skipped 4 untracked file(s)" in out


def test_intent_to_add_entries_count_toward_the_limit(tmp_path):
    """git add -u fills these in, so they are hashed (N5 says so), and then the index check holds them back."""
    repo = make_repo(tmp_path)
    write(repo, {f"new/{i}.md": f"new {i}\n".encode() for i in range(MAX_NEW + 1)})
    git(repo, "add", "-N", "new", home=tmp_path)
    out = hook(repo, tmp_path)
    assert commits(repo, tmp_path) == ["base"]
    assert f"Left out {MAX_NEW + 1} new file(s), over the limit" in out
    assert not git(repo, "diff", "--cached", "--name-only", home=tmp_path)


def test_a_rename_into_a_secret_log_name_is_left_out_and_reported_once(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "notes.txt").rename(repo / "password.log")
    out = hook(repo, tmp_path)
    assert "password.log" not in tracked(repo, tmp_path)
    assert "Skipped 1 untracked file(s)" in out
    assert "Kept" not in out and "Left out" not in out


def test_a_sweep_in_a_linked_worktree_is_held_back_too(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    wt = add_worktree(repo, tmp_path)
    write(wt, {f"x/{i}.md": b"n\n" for i in range(MAX_NEW + 1)})
    write(wt, {".env": b"hunter2\n", "src/app.py": b"print('mine')\n"})
    out = hook(wt, tmp_path)
    assert "Auto-committed 1 file(s) in wt on branch side" in out
    assert added_in_commit(wt, tmp_path) == set()
    assert commits(repo, tmp_path, "main") == ["base"]


def test_a_secret_name_with_a_newline_is_left_out_and_reported_on_one_line(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"odd\nname.key": b"k\n", "plain.md": b"p\n"})
    out = hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == {"plain.md"}
    assert out.count("\n") == 1 and "odd name.key" in out


def test_control_bytes_in_a_held_back_name_do_not_reach_the_output(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"a\x1b[31m.env": b"k\n"})
    assert "\x1b" not in hook(repo, tmp_path)


TREE = st.lists(st.sampled_from(["plain.md", "deep/plain.md", "a.log", ".env", "keys/a.pem", "secrets/b.yml",
                                 "ok-template.env.example", "tokens.css", "z y.md", "é.md"]), unique=True)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(names=TREE, fill=st.sampled_from([0, MAX_NEW - 2, MAX_NEW + 1]))
def test_the_two_scan_paths_stage_the_same_files(names, fill):
    """N6: the same tree, with and without a name that forces the slow path."""
    home = Path(tempfile.mkdtemp(prefix="acw-"))
    try:
        results = []
        files = {n: b"x\n" for n in names} | {f"fill/{i}.md": b"f\n" for i in range(fill)}
        for name, odd in (("fast", {}), ("slow", {"odd\nname.log": b"l\n"})):
            repo = make_repo(home, name=name)
            write(repo, files | odd)
            out = hook(repo, home)
            assert "\n" not in out[:-1]
            committed = commits(repo, home)[0] != "base"
            results.append((added_in_commit(repo, home) if committed else set(), "over the limit" in out,
                            "secret-looking" in out))
        assert results[0] == results[1]
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_the_slow_scan_path_holds_back_secrets_and_sweeps(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"odd\nname.md": b"o\n", ".env": b"hunter2\n", "ok.md": b"ok\n"})
    hook(repo, tmp_path)
    assert added_in_commit(repo, tmp_path) == {"odd\nname.md", "ok.md"}


# --- rule 7: an operation in progress stops the hook ---------------------------------------------------

def two_branches(repo: Path, home: Path, name: str = "theirs.md", same: bool = False) -> None:
    """Branch `other` with one commit that adds `name`, then back on the first branch with a commit
    of its own; with `same` both change notes.txt, so merging them conflicts."""
    first = git(repo, "branch", "--show-current", home=home).strip()
    git(repo, "checkout", "-q", "-b", "other", home=home)
    write(repo, {name: b"from other\n"} | ({"notes.txt": b"other\n"} if same else {}))
    git(repo, "add", "-A", home=home)
    git(repo, "commit", "-q", "-m", "other", home=home)
    git(repo, "checkout", "-q", first, home=home)
    write(repo, {"notes.txt": b"first\n"} if same else {"first.md": b"first\n"})
    git(repo, "add", "-A", home=home)
    git(repo, "commit", "-q", "-m", "first", home=home)


def test_a_merge_with_no_conflicts_left_is_not_finished_by_the_hook(tmp_path):
    repo = make_repo(tmp_path)
    two_branches(repo, tmp_path, name=".env.staged")                # a new path that rule 6 would unstage
    git(repo, "merge", "-q", "--no-commit", "--no-ff", "other", home=tmp_path)
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    out = hook(repo, tmp_path)
    assert "a merge, rebase, cherry-pick, revert or bisect is in progress" in out
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head
    assert (repo / ".git" / "MERGE_HEAD").exists()
    assert ".env.staged" in git(repo, "diff", "--cached", "--name-only", home=tmp_path)


def test_a_merge_in_a_linked_worktree_is_found_in_that_worktrees_git_dir(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    wt = add_worktree(repo, tmp_path)
    two_branches(wt, tmp_path)
    git(wt, "merge", "-q", "--no-commit", "--no-ff", "other", home=tmp_path)
    assert "is in progress" in hook(wt, tmp_path)


@pytest.mark.parametrize("op", ["cherry-pick", "revert"])
def test_a_resolved_cherry_pick_or_revert_is_not_finished_by_the_hook(tmp_path, op):
    repo = make_repo(tmp_path)
    two_branches(repo, tmp_path, same=True)
    if op == "revert":
        git(repo, "merge", "-q", "-X", "ours", "--no-edit", "other", home=tmp_path)
        write(repo, {"notes.txt": b"changed again\n"})
        git(repo, "commit", "-q", "-am", "again", home=tmp_path)
        rev = git(repo, "log", "--format=%H", "--grep=^first$", home=tmp_path).strip()
    else:
        rev = "other"
    git(repo, op, "--no-edit", rev, home=tmp_path, check=False)
    assert "unmerged paths" in hook(repo, tmp_path)
    write(repo, {"notes.txt": b"resolved\n"})
    git(repo, "add", "notes.txt", home=tmp_path)
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    assert "is in progress" in hook(repo, tmp_path)
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head


def test_a_stopped_rebase_of_a_feature_branch_is_left_alone(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"c1.md": b"1\n"})
    git(repo, "add", "-A", home=tmp_path)
    git(repo, "commit", "-q", "-m", "c1", home=tmp_path)
    git(repo, "rebase", "-q", "-i", "HEAD~1", home=tmp_path, GIT_SEQUENCE_EDITOR="sed -i.bak -e '1s/^pick/edit/'")
    write(repo, {"src/app.py": b"print('mid-rebase')\n"})
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    assert "is in progress" in hook(repo, tmp_path)
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head


def test_a_range_cherry_pick_paused_between_picks_is_left_alone(tmp_path):
    """Resolving a pick with git commit clears CHERRY_PICK_HEAD; only sequencer/ shows the rest is pending."""
    repo = make_repo(tmp_path)
    two_branches(repo, tmp_path, same=True)
    git(repo, "checkout", "-q", "other", home=tmp_path)
    write(repo, {"later.md": b"later\n"})
    git(repo, "add", "-A", home=tmp_path)
    git(repo, "commit", "-q", "-m", "later", home=tmp_path)
    git(repo, "checkout", "-q", "work", home=tmp_path)
    git(repo, "cherry-pick", "other~1", "other", home=tmp_path, check=False)
    write(repo, {"notes.txt": b"resolved\n"})
    git(repo, "add", "-A", home=tmp_path)
    git(repo, "commit", "-q", "-m", "resolved", home=tmp_path)
    write(repo, {"mine.md": b"m\n"})
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    assert "is in progress" in hook(repo, tmp_path)
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head


def test_a_squash_merge_waiting_for_its_commit_is_left_alone(tmp_path):
    repo = make_repo(tmp_path)
    two_branches(repo, tmp_path)
    git(repo, "merge", "--squash", "other", home=tmp_path)
    write(repo, {"mine.md": b"m\n"})
    staged = git(repo, "diff", "--cached", "--name-only", home=tmp_path)
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    assert "is in progress (found SQUASH_MSG)" in hook(repo, tmp_path)              # git status names no operation here
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head
    assert git(repo, "diff", "--cached", "--name-only", home=tmp_path) == staged


def test_a_bisect_is_left_alone(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "bisect", "start", home=tmp_path)
    write(repo, {"mine.md": b"m\n"})
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    assert "bisect is in progress" in hook(repo, tmp_path)
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head


def test_a_paused_cherry_pick_n_of_a_range_is_left_alone(tmp_path):
    repo = make_repo(tmp_path)
    two_branches(repo, tmp_path, same=True)
    git(repo, "checkout", "-q", "other", home=tmp_path)
    write(repo, {"later.md": b"later\n"})
    git(repo, "add", "-A", home=tmp_path)
    git(repo, "commit", "-q", "-m", "later", home=tmp_path)
    git(repo, "checkout", "-q", "work", home=tmp_path)
    git(repo, "cherry-pick", "-n", "other~1", "other", home=tmp_path, check=False)
    write(repo, {"notes.txt": b"resolved\n"})
    git(repo, "add", "-A", home=tmp_path)
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    assert "is in progress" in hook(repo, tmp_path)
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head


def test_a_stopped_git_am_is_left_alone(tmp_path):
    """git am keeps the branch checked out and has no head-name, so only rebase-apply/ shows it."""
    repo = make_repo(tmp_path)
    two_branches(repo, tmp_path, same=True)
    (tmp_path / "patch.mbox").write_text(git(repo, "format-patch", "--stdout", "-1", "other", home=tmp_path))
    git(repo, "am", str(tmp_path / "patch.mbox"), home=tmp_path, check=False)
    assert (repo / ".git" / "rebase-apply").is_dir() and not (repo / ".git" / "rebase-apply" / "head-name").exists()
    write(repo, {"src/app.py": b"print('mid-am')\n"})
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    assert "is in progress" in hook(repo, tmp_path)
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head


# --- when a check cannot run, no new path is committed ---------------------------------------------------

def test_no_temporary_folder_keeps_staged_new_paths_out(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n", "src/app.py": b"print('v2')\n"})
    git(repo, "add", ".env", home=tmp_path)
    out = hook(repo, tmp_path, TMPDIR=tmp_path / "missing")
    assert "no temporary folder" in out
    assert commits(repo, tmp_path) == ["base"]


def test_no_temporary_folder_still_commits_tracked_changes(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"new.md": b"n\n", "src/app.py": b"print('v2')\n"})
    out = hook(repo, tmp_path, TMPDIR=tmp_path / "missing")
    assert "New files were NOT staged" in out
    assert added_in_commit(repo, tmp_path) == set() and commits(repo, tmp_path)[0] == "fixup! base"


def shim(tmp_path: Path, name: str, body: str) -> str:
    """A PATH with `name` replaced by a stub script."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    (d / name).write_text(f"#!/bin/bash\n{body}\n")
    (d / name).chmod(0o755)
    return f"{d}:{os.environ['PATH']}"


def test_a_grep_that_cannot_run_keeps_every_new_path_out(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n", "new.md": b"n\n", "staged.md": b"s\n", "src/app.py": b"print('v2')\n"})
    git(repo, "add", "staged.md", home=tmp_path)
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "grep", "exit 2"))
    assert "could not check the names of staged new paths" in out
    assert commits(repo, tmp_path) == ["base"]
    assert ".env" not in git(repo, "ls-files", home=tmp_path)
    assert not blob_stored(repo, tmp_path, ".env")


def test_a_name_check_that_fails_once_keeps_the_scanned_files_out(tmp_path):
    """The scan side has its own failure path, so a passing retry later cannot let unsplit names through."""
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n", "new.md": b"n\n", "src/app.py": b"print('v2')\n"})
    real, mark = shutil.which("grep"), tmp_path / "grep-ran"
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "grep", f'[ -e {mark} ] || {{ touch {mark}; exit 2; }}\nexec {real} "$@"'))
    assert "New files were NOT staged: the scan could not run" in out
    assert added_in_commit(repo, tmp_path) == set()
    assert git(repo, "show", "HEAD:src/app.py", home=tmp_path) == "print('v2')\n"
    assert not blob_stored(repo, tmp_path, ".env")


@pytest.mark.parametrize("flag", ["--no-renames", "--find-renames=100%"])
def test_a_git_diff_that_cannot_list_new_paths_stops_the_commit(tmp_path, flag):
    repo = make_repo(tmp_path)
    write(repo, {"staged.md": b"s\n"})
    git(repo, "add", "staged.md", home=tmp_path)
    real = shutil.which("git")
    path = shim(tmp_path, "git", f'[ "$1 $2 $3" = "diff --cached {flag}" ] && exit 128\nexec {real} "$@"')
    assert "could not list staged new paths" in hook(repo, tmp_path, PATH=path)
    assert commits(repo, tmp_path) == ["base"]


def test_a_count_that_cannot_run_stops_the_commit(tmp_path):
    """An empty count would otherwise read as zero and pass the limit."""
    repo = make_repo(tmp_path)
    write(repo, {"staged.md": b"s\n"})
    git(repo, "add", "staged.md", home=tmp_path)
    r = subprocess.run(["/bin/bash", str(HOOK)], cwd=repo, capture_output=True, text=True,
                       env=env_for(tmp_path, PATH=shim(tmp_path, "wc", "exit 1")))
    assert "could not count staged new paths" in r.stdout
    assert commits(repo, tmp_path) == ["base"]


# --- N7: another process at work while the hook runs -----------------------------------------------

RACED = [".env"] + [f"raced/{i}.md" for i in range(MAX_NEW)]


def another_session(real: str, mark: Path) -> str:
    """Shell that stages `.env` and 25 more files in the real index, once."""
    names = " ".join(RACED)
    return (f'if [ ! -e {mark} ]; then touch {mark}; mkdir -p raced; (unset GIT_INDEX_FILE; '
            f'for f in {names}; do echo "$f" > "$f"; done; {real} add -- {names}); fi')


def test_what_is_staged_after_the_copy_stays_out_of_the_commit(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"own.md": b"mine\n"})
    real = shutil.which("git")
    race = another_session(real, tmp_path / "raced")
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "git", f'[ "$1" = write-tree ] && {{ {race}\n}}\nexec {real} "$@"'))
    assert "Auto-committed 1 file(s)" in out
    assert added_in_commit(repo, tmp_path) == {"own.md"}
    assert set(git(repo, "diff", "--cached", "--name-only", home=tmp_path).split()) == set(RACED)


def test_what_is_staged_before_the_copy_is_checked_on_the_copy(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    real, real_cp = shutil.which("git"), shutil.which("cp")
    race = another_session(real, tmp_path / "raced")
    path = shim(tmp_path, "cp", f'[ "${{2##*/}}" = index ] && {{ {race}\n}}\nexec {real_cp} "$@"')
    out = hook(repo, tmp_path, PATH=path)
    assert "Left out 1 new file(s) with secret-looking names: .env" in out
    assert ".env" not in tracked(repo, tmp_path)
    assert len(new_in_commit(repo, tmp_path)) == MAX_NEW
    assert git(repo, "show", "HEAD:src/app.py", home=tmp_path) == "print('v2')\n"
    assert git(repo, "diff", "--cached", "--name-only", home=tmp_path).split() == [".env"]


def test_a_big_file_staged_before_the_copy_is_checked_on_the_copy(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n", "big.bin": big_lines(51)})
    real, real_cp = shutil.which("git"), shutil.which("cp")
    race = f'(unset GIT_INDEX_FILE; {real} add -- big.bin)'
    path = shim(tmp_path, "cp", f'[ "${{2##*/}}" = index ] && {race}\nexec {real_cp} "$@"')
    assert "Unstaged 1 new file(s)" in hook(repo, tmp_path, PATH=path)
    assert "big.bin" not in tracked(repo, tmp_path)


def test_a_copy_of_the_index_that_cannot_be_made_stops_the_commit(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"new.md": b"n\n"})
    real_cp = shutil.which("cp")
    path = shim(tmp_path, "cp", f'[ "${{2##*/}}" = index ] && exit 1\nexec {real_cp} "$@"')
    assert "could not copy the index" in hook(repo, tmp_path, PATH=path)
    assert commits(repo, tmp_path) == ["base"]


def test_a_stop_after_the_index_checks_says_new_paths_may_have_left_the_index(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n", "src/app.py": b"print('v2')\n"})
    git(repo, "add", ".env", home=tmp_path)
    real_cp = shutil.which("cp")
    path = shim(tmp_path, "cp", f'[ "${{2##*/}}" = index ] && exit 1\nexec {real_cp} "$@"')
    assert "staged paths stay staged, unless the hook unstaged a new one that breaks its rules." in hook(repo, tmp_path, PATH=path)
    assert "?? .env" in git(repo, "status", "--porcelain", home=tmp_path)
    assert "src/app.py" in git(repo, "diff", "--cached", "--name-only", home=tmp_path).split()


@pytest.mark.parametrize("move", ["switch", "commit"])
def test_a_head_that_moves_while_the_hook_runs_stops_the_commit(tmp_path, move):
    repo = make_repo(tmp_path)
    git(repo, "branch", "elsewhere", home=tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    real = shutil.which("git")
    mark = tmp_path / "moved"
    act = f"{real} checkout -q elsewhere" if move == "switch" else f'{real} commit -q --allow-empty -m "their commit"'
    body = f'[ "$1 $2" = "add -u" ] && [ ! -e {mark} ] && {{ touch {mark}; (unset GIT_INDEX_FILE; {act}) >/dev/null 2>&1; }}\nexec {real} "$@"'
    before = {b: git(repo, "rev-parse", b, home=tmp_path) for b in ("work", "elsewhere")}
    assert "HEAD moved while the hook ran" in hook(repo, tmp_path, PATH=shim(tmp_path, "git", body))
    after = {b: git(repo, "rev-parse", b, home=tmp_path) for b in ("work", "elsewhere")}
    assert after["elsewhere"] == before["elsewhere"]
    assert not git(repo, "log", "--format=%s", "--grep=^fixup!", "--all", home=tmp_path).strip()


def their_commit(real: str) -> str:
    """Shell for another session's commit of one new file, leaving the rest of the real index staged."""
    return f"echo theirs > theirs.txt; {real} add -- theirs.txt; {real} commit -q -m theirs -- theirs.txt"


def once_at(step: str, real: str, act: str, mark: Path) -> str:
    """A git stub that runs `act` on the real index just before the first `git <step>`."""
    return (f'[ "$1" = {step} ] && [ ! -e {mark} ] && {{ touch {mark}; (unset GIT_INDEX_FILE; {act}) >/dev/null 2>&1; }}\n'
            f'exec {real} "$@"')


@pytest.mark.parametrize("step", ["write-tree", "commit-tree", "update-ref"])
@pytest.mark.parametrize("detached", [False, True])
def test_another_commit_during_the_commit_reverses_nothing(tmp_path, step, detached):
    """The tree comes from the private copy, so a commit on the new tip would undo what differs there."""
    repo = make_repo(tmp_path)
    if detached:
        git(repo, "checkout", "-q", "--detach", home=tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    real = shutil.which("git")
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "git", once_at(step, real, their_commit(real), tmp_path / "moved")))
    assert "Auto-commit FAILED" in out and "changes left staged, not committed." in out
    assert commits(repo, tmp_path) == ["theirs", "base"]
    assert "theirs.txt" in tracked(repo, tmp_path)
    assert "src/app.py" in git(repo, "diff", "--cached", "--name-only", home=tmp_path).split()


@pytest.mark.parametrize("step", ["write-tree", "update-ref"])
@pytest.mark.parametrize("move", ["elsewhere", "main", "ahead", "--detach"])
def test_a_switch_during_the_commit_leaves_the_save_on_the_judged_branch(tmp_path, step, move):
    """HEAD would resolve wherever the session went, `main` included: only the judged branch moves."""
    repo = make_repo(tmp_path)
    git(repo, "branch", "elsewhere", home=tmp_path)
    git(repo, "branch", "main", home=tmp_path)
    git(repo, "checkout", "-q", "-b", "ahead", home=tmp_path)
    write(repo, {"theirs.txt": b"theirs\n"})
    git(repo, "add", "-A", home=tmp_path)
    git(repo, "commit", "-q", "-m", "theirs", home=tmp_path)
    git(repo, "checkout", "-q", "work", home=tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    others = {b: git(repo, "rev-parse", b, home=tmp_path) for b in ("elsewhere", "main", "ahead")}
    real = shutil.which("git")
    act = f"{real} checkout -q {move}"
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "git", once_at(step, real, act, tmp_path / "moved")))
    assert "Auto-committed 1 file(s) in repo on branch work" in out
    assert commits(repo, tmp_path, "work") == ["fixup! base", "base"]
    assert git(repo, "show", "work:src/app.py", home=tmp_path) == "print('v2')\n"
    assert "theirs.txt" not in tracked(repo, tmp_path, "work")
    assert {b: git(repo, "rev-parse", b, home=tmp_path) for b in others} == others
    assert "src/app.py" in git(repo, "diff", "--cached", "--name-only", home=tmp_path).split()


def test_a_branch_renamed_during_the_commit_fails_the_save(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    real = shutil.which("git")
    act = f"{real} branch -m work renamed"
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "git", once_at("update-ref", real, act, tmp_path / "moved")))
    assert "Auto-commit FAILED" in out
    assert commits(repo, tmp_path, "renamed") == ["base"]


def test_an_orphan_switch_keeps_the_save_on_the_unborn_branch(tmp_path):
    repo = make_repo(tmp_path, commit=False)
    write(repo, {"own.md": b"mine\n"})
    real = shutil.which("git")
    act = f"{real} checkout -q --orphan other"
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "git", once_at("update-ref", real, act, tmp_path / "moved")))
    assert "Auto-committed 1 file(s) in repo on branch work" in out
    assert tracked(repo, tmp_path, "work") == {"own.md"}
    assert git(repo, "symbolic-ref", "HEAD", home=tmp_path).strip() == "refs/heads/other"


def test_a_detached_start_is_the_one_head_move_left_open(tmp_path):
    """Intended: a detached HEAD names no ref, so a branch at the same commit gets the save, whole."""
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "--detach", home=tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    real = shutil.which("git")
    act = f"{real} checkout -q -b fresh"
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "git", once_at("update-ref", real, act, tmp_path / "moved")))
    assert "Auto-committed 1 file(s) in repo on branch detached" in out
    assert commits(repo, tmp_path, "fresh") == ["fixup! base", "base"]
    assert git(repo, "show", "fresh:src/app.py", home=tmp_path) == "print('v2')\n"


def test_a_merge_that_starts_while_the_hook_runs_stops_the_commit(tmp_path):
    repo = make_repo(tmp_path)
    two_branches(repo, tmp_path)
    write(repo, {"own.md": b"mine\n"})
    real = shutil.which("git")
    act = f"{real} merge -q --no-commit --no-ff other"
    head = git(repo, "rev-parse", "HEAD", home=tmp_path)
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "git", once_at("add", real, act, tmp_path / "moved")))
    assert "an operation started while the hook ran (found MERGE_HEAD)" in out
    assert git(repo, "rev-parse", "HEAD", home=tmp_path) == head
    assert (repo / ".git" / "MERGE_HEAD").exists()


def test_a_merge_that_starts_during_the_scan_keeps_its_conflicts(tmp_path):
    """git add -u would mark them resolved and stage the conflict markers."""
    repo = make_repo(tmp_path)
    two_branches(repo, tmp_path, same=True)
    write(repo, {"own.md": b"mine\n"})
    real = shutil.which("git")
    act = f"{real} merge -q --no-commit --no-ff other"
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "git", once_at("ls-files", real, act, tmp_path / "moved")))
    assert "an operation started while the hook ran (found MERGE_HEAD)" in out
    assert git(repo, "ls-files", "-u", home=tmp_path).strip()


def test_a_stop_after_the_checks_still_says_what_it_left_out(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n", "src/app.py": b"print('v2')\n"})
    git(repo, "add", ".env", home=tmp_path)
    real, real_cp = shutil.which("git"), shutil.which("cp")
    act = f"(unset GIT_INDEX_FILE; {real} checkout -q -b moved)"
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "cp", f'[ "${{2##*/}}" = index ] && {act}\nexec {real_cp} "$@"'))
    assert "HEAD moved while the hook ran" in out
    assert "Left out 1 new file(s) with secret-looking names: .env" in out
    assert "?? .env" in git(repo, "status", "--porcelain", home=tmp_path)


def test_another_sessions_first_commit_on_an_unborn_branch_stays(tmp_path):
    repo = make_repo(tmp_path, commit=False)
    write(repo, {"own.md": b"mine\n"})
    real = shutil.which("git")
    path = shim(tmp_path, "git", once_at("update-ref", real, their_commit(real), tmp_path / "moved"))
    assert "Auto-commit FAILED" in hook(repo, tmp_path, PATH=path)
    assert commits(repo, tmp_path) == ["theirs"]
    assert tracked(repo, tmp_path) == {"theirs.txt"}


@pytest.mark.parametrize("subject", ["base", "fixup! base", "two  spaces", 'quote " and $dollar', "na\u00efve"])
def test_the_commit_matches_what_git_commit_fixup_writes(tmp_path, subject):
    repo = make_repo(tmp_path)
    git(repo, "commit", "-q", "--allow-empty", "-m", subject, home=tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    twin = tmp_path / "twin"
    shutil.copytree(repo, twin)
    parent = git(repo, "rev-parse", "HEAD", home=tmp_path).strip()
    assert "Auto-committed 1 file(s)" in hook(repo, tmp_path)
    git(twin, "commit", "-q", "-a", "--fixup=HEAD", "--no-verify", home=tmp_path)
    assert commits(repo, tmp_path)[0] == commits(twin, tmp_path)[0]
    assert git(repo, "rev-parse", "HEAD^{tree}", home=tmp_path) == git(twin, "rev-parse", "HEAD^{tree}", home=tmp_path)
    assert git(repo, "log", "-1", "--format=%P", home=tmp_path).strip() == parent
    entry = " ".join(commits(repo, tmp_path)[0].split())                            # reflogs squeeze spaces
    assert git(repo, "reflog", "-1", "--format=%gs", home=tmp_path).strip() == f"commit: {entry}"
    assert not git(repo, "status", "--porcelain", home=tmp_path).strip()


def test_a_tree_with_nothing_new_makes_no_empty_commit(tmp_path):
    """commit-tree has no refusal of its own, as git commit does. With no temporary folder the commit
    reads the real index, so another session's reset empties it after the hook counted its changes."""
    repo = make_repo(tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    real = shutil.which("git")
    path = shim(tmp_path, "git", once_at("write-tree", real, f"{real} reset -q", tmp_path / "moved"))
    assert "Nothing to auto-commit in repo on branch work" in hook(repo, tmp_path, TMPDIR=tmp_path / "missing", PATH=path)
    assert commits(repo, tmp_path) == ["base"]


def test_an_empty_tree_on_a_new_branch_makes_no_first_commit(tmp_path):
    """A new branch has no parent tree, so the empty tree stands in. The stub empties the hook's own
    copy of the index: a failed count reaches the same state with only a held-back file on disk."""
    repo = make_repo(tmp_path, commit=False)
    write(repo, {"p.md": b"x\n"})
    real = shutil.which("git")
    path = shim(tmp_path, "git", f'[ "$1" = write-tree ] && {real} rm -q --cached p.md >/dev/null 2>&1\nexec {real} "$@"')
    assert "Nothing to auto-commit in repo on branch work" in hook(repo, tmp_path, PATH=path)
    assert git(repo, "rev-list", "--all", home=tmp_path) == ""


def test_a_new_repo_with_no_index_file_still_says_what_it_left_out(tmp_path):
    repo = make_repo(tmp_path, commit=False)
    write(repo, {".env": b"hunter2\n", **{f"n{i}.md": b"n\n" for i in range(MAX_NEW + 1)}})
    assert not (repo / ".git" / "index").exists()
    out = hook(repo, tmp_path)
    assert "could not copy the index" not in out
    assert "Nothing to auto-commit in repo on branch work" in out
    assert f"Left out {MAX_NEW + 1} new file(s), over the limit" in out
    assert "Left out 1 new file(s) with secret-looking names: .env" in out


def test_an_index_that_vanished_on_a_born_branch_stops_the_commit(tmp_path):
    """Git reads a missing index as every tracked file deleted, so a commit from it would empty the tree."""
    repo = make_repo(tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    before = tracked(repo, tmp_path)
    (repo / ".git" / "index").unlink()
    assert "could not copy the index" in hook(repo, tmp_path, PATH=shim(tmp_path, "stat", "exit 1"))
    assert commits(repo, tmp_path) == ["base"]
    assert tracked(repo, tmp_path) == before


def test_an_index_path_git_cannot_name_stops_the_commit(tmp_path):
    """On a new branch a blank path would skip the copy, and an empty copy would read as nothing to commit."""
    repo = make_repo(tmp_path, commit=False)
    write(repo, {"p.md": b"x\n"})
    real = shutil.which("git")
    path = shim(tmp_path, "git", f'[ "$1 $2" = "rev-parse --git-path" ] && exit 1\nexec {real} "$@"')
    assert "could not copy the index" in hook(repo, tmp_path, PATH=path)
    assert git(repo, "rev-list", "--all", home=tmp_path) == ""


def test_a_branch_git_cannot_name_stops_it_on_main(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    write(repo, {"src/app.py": b"print('v2')\n"})
    real = shutil.which("git")
    path = shim(tmp_path, "git", f'[ "$1 $2" = "branch --show-current" ] && exit 128\nexec {real} "$@"')
    assert "did not name the current branch" in hook(repo, tmp_path, PATH=path)
    assert commits(repo, tmp_path) == ["base"]


def test_a_worktrees_folder_that_cannot_be_read_stops_it(tmp_path):
    repo = make_repo(tmp_path)
    add_worktree(repo, tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    (repo / ".git" / "worktrees").chmod(0)
    try:
        out = hook(repo, tmp_path)
    finally:
        (repo / ".git" / "worktrees").chmod(0o755)
    assert "worktrees folder cannot be read" in out
    assert commits(repo, tmp_path) == ["base"]


def test_a_secret_named_intent_to_add_entry_never_reaches_a_commit(tmp_path):
    """git add -u hashes it first, so its blob stays local and unreachable. N2 still holds."""
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n", "src/app.py": b"print('v2')\n"})
    git(repo, "add", "-N", ".env", home=tmp_path)
    out = hook(repo, tmp_path)
    assert "Left out 1 new file(s) with secret-looking names: .env" in out
    assert ".env" not in tracked(repo, tmp_path)


def test_a_utf8_locale_changes_nothing(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"é.env": b"hunter2\n", "ÉTÉ.KEY": b"k\n", "été.md": b"ok\n"})
    out = hook(repo, tmp_path, LC_ALL="en_US.UTF-8")
    assert "Left out 2 new file(s) with secret-looking names" in out
    assert len(added_in_commit(repo, tmp_path)) == 1


def test_a_failed_unstage_stops_the_commit(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {".env": b"hunter2\n"})
    git(repo, "add", ".env", home=tmp_path)
    real = shutil.which("git")
    path = shim(tmp_path, "git", f'[ "$1" = update-index ] && exit 1\nexec {real} "$@"')
    out = hook(repo, tmp_path, PATH=path)
    assert "could not unstage" in out
    assert commits(repo, tmp_path) == ["base"]


def big_lines(n_mb: int) -> bytes:
    return b"same line of text\n" * (n_mb * MB // 18)


def test_a_big_file_someone_staged_is_unstaged(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"big.bin": big_lines(51), "src/app.py": b"print('v2')\n"})
    git(repo, "add", "big.bin", home=tmp_path)
    out = hook(repo, tmp_path)
    assert "Unstaged 1 new file(s) over 50 MB by staging time: big.bin" in out
    assert added_in_commit(repo, tmp_path) == set()
    assert "big.bin" not in tracked(repo, tmp_path)
    assert commits(repo, tmp_path)[0].startswith("fixup!")


def test_a_big_staged_file_that_keeps_changing_is_still_unstaged(tmp_path):
    """git rm --cached refuses a file that differs from both the index and HEAD unless forced."""
    repo = make_repo(tmp_path)
    write(repo, {"big.bin": big_lines(51), "src/app.py": b"print('v2')\n"})
    git(repo, "add", "big.bin", home=tmp_path)
    real = shutil.which("git")
    path = shim(tmp_path, "git", f'[ "$2" = rm ] && echo more >> big.bin\nexec {real} "$@"')
    out = hook(repo, tmp_path, PATH=path)
    assert "Unstaged 1 new file(s)" in out
    assert "big.bin" not in tracked(repo, tmp_path)


def test_a_failed_unstage_of_a_big_file_stops_the_commit(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"big.bin": big_lines(51)})
    git(repo, "add", "big.bin", home=tmp_path)
    real = shutil.which("git")
    path = shim(tmp_path, "git", f'[ "$2" = rm ] && exit 1\nexec {real} "$@"')
    assert "could not unstage a new file over 50 MB" in hook(repo, tmp_path, PATH=path)
    assert commits(repo, tmp_path) == ["base"]


def test_an_exact_rename_of_a_big_tracked_file_stays_a_rename(tmp_path):
    """The content is already in the repository, so the size check has nothing to protect."""
    repo = make_repo(tmp_path)
    write(repo, {"old.bin": big_lines(51)})
    git(repo, "add", "old.bin", home=tmp_path)
    git(repo, "commit", "-q", "-m", "big", home=tmp_path)
    (repo / "old.bin").rename(repo / "new.bin")
    out = hook(repo, tmp_path)
    assert "Unstaged" not in out
    assert "new.bin" in tracked(repo, tmp_path) and "old.bin" not in tracked(repo, tmp_path)


def test_a_big_modified_tracked_file_commits_with_a_warning(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"notes.txt": big_lines(51)})
    out = hook(repo, tmp_path)
    assert "WARNING: 1 tracked file(s) over 50 MB modified: notes.txt" in out


@pytest.mark.parametrize("step", ["diff", "diff -z", "cat-file"])
def test_a_size_check_that_cannot_run_stops_the_commit(tmp_path, step):
    repo = make_repo(tmp_path)
    write(repo, {"big.bin": big_lines(51)})
    git(repo, "add", "big.bin", home=tmp_path)
    real = shutil.which("git")
    fail = {"diff": '[ "$1 $6" = "diff --no-abbrev" ]', "diff -z": '[ "$1 $7" = "diff -z" ] && [ "$5" = --raw ]',
            "cat-file": '[ "$1" = cat-file ]'}[step]
    path = shim(tmp_path, "git", f'{fail} && exit 1\nexec {real} "$@"')
    assert "could not size staged blobs" in hook(repo, tmp_path, PATH=path)
    assert commits(repo, tmp_path) == ["base"]


@pytest.mark.parametrize("program", ["print $4", "max + 0"])
def test_a_size_check_whose_awk_fails_stops_the_commit(tmp_path, program):
    repo = make_repo(tmp_path)
    write(repo, {"big.bin": big_lines(51)})
    git(repo, "add", "big.bin", home=tmp_path)
    real = shutil.which("awk")
    path = shim(tmp_path, "awk", f'case "$*" in *"{program}"*) exit 1 ;; esac\nexec {real} "$@"')
    assert "could not size staged blobs" in hook(repo, tmp_path, PATH=path)
    assert commits(repo, tmp_path) == ["base"]


def test_a_big_new_blob_that_looks_like_a_rename_is_unstaged(tmp_path):
    """Git's default 50% similarity shows this as a rename, which would slip past the size check."""
    repo = make_repo(tmp_path)
    write(repo, {"old.txt": big_lines(30)})
    git(repo, "add", "old.txt", home=tmp_path)
    git(repo, "commit", "-q", "-m", "old", home=tmp_path)
    (repo / "old.txt").unlink()
    write(repo, {"new.txt": big_lines(51)})
    git(repo, "add", "-A", home=tmp_path)
    out = hook(repo, tmp_path)
    assert "Unstaged 1 new file(s)" in out
    assert "new.txt" not in tracked(repo, tmp_path)
    assert "old.txt" not in tracked(repo, tmp_path)


def test_an_unreadable_new_file_is_reported_and_the_rest_commit(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"good.md": b"g\n", "locked.md": b"l\n"})
    (repo / "locked.md").chmod(0)
    out = hook(repo, tmp_path)
    assert "1 new file(s) could not be read and were not staged" in out
    assert added_in_commit(repo, tmp_path) == {"good.md"}


def test_a_fatal_from_both_staging_paths_is_reported(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"new.md": b"n\n", "src/app.py": b"print('v2')\n"})
    real = shutil.which("git")
    path = shim(tmp_path, "git", f"""[ "$1" = update-index ] && [ "$2" = --add ] && exit 1
[ "$1 $2" = "add --ignore-errors" ] && [ "$3" != -u ] && {{ echo 'fatal: stub' >&2; exit 128; }}
exec {real} "$@\"""")
    out = hook(repo, tmp_path, PATH=path)
    assert "New files were NOT staged: fatal: stub." in out
    assert added_in_commit(repo, tmp_path) == set()


def test_a_file_that_vanishes_before_it_is_sized_is_reported(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"gone.md": b"g\n", "new.md": b"n\n"})
    real = shutil.which("stat")
    path = shim(tmp_path, "stat", f"""[ "$2" = '%z%t%N' ] && rm -f gone.md\nexec {real} "$@\"""")
    out = hook(repo, tmp_path, PATH=path)
    assert "1 untracked file(s) could not be sized" in out
    assert added_in_commit(repo, tmp_path) == {"new.md"}


def test_an_unreadable_tracked_file_is_reported(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"notes.txt": b"edited\n", "src/app.py": b"print('v2')\n"})
    (repo / "notes.txt").chmod(0)
    out = hook(repo, tmp_path)
    assert "1 tracked file(s) could not be read and were not committed" in out
    assert git(repo, "show", "HEAD:src/app.py", home=tmp_path) == "print('v2')\n"


def test_a_fatal_from_git_add_commits_nothing(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    (repo / ".git" / "index.lock").touch()
    out = hook(repo, tmp_path)
    assert out.startswith("Auto-commit FAILED in repo on branch work: fatal:")
    assert "nothing committed" in out
    assert commits(repo, tmp_path) == ["base"]


@pytest.mark.parametrize("step", ["write-tree", "commit-tree", "update-ref"])
def test_a_failed_commit_says_so_and_leaves_the_changes_staged(tmp_path, step):
    repo = make_repo(tmp_path)
    write(repo, {"src/app.py": b"print('v2')\n"})
    real = shutil.which("git")
    path = shim(tmp_path, "git", f'[ "$1" = {step} ] && exit 1\nexec {real} "$@"')
    assert "Auto-commit FAILED in repo on branch work; changes left staged, not committed." in hook(repo, tmp_path, PATH=path)
    assert commits(repo, tmp_path) == ["base"]
    assert git(repo, "diff", "--cached", "--name-only", home=tmp_path).strip() == "src/app.py"


@pytest.mark.parametrize("settles", [True, False])
def test_the_slow_scan_path_retries_once_when_a_file_vanishes(tmp_path, settles):
    """A size list one short of the name list breaks the pairing: retry, then keep new files out."""
    repo = make_repo(tmp_path)
    write(repo, {"line\nbreak.md": b"x\n", "other.md": b"y\n", "src/app.py": b"print('v2')\n"})
    real = shutil.which("stat")
    mark = tmp_path / "stat-ran"
    drop = f'[ "$2" = %z ] && [ $# -gt 3 ] && [ ! -e {mark} ] && {{ {"touch " + str(mark) if settles else ":"}; set -- "${{@:1:$#-1}}"; }}'
    out = hook(repo, tmp_path, PATH=shim(tmp_path, "stat", f'{drop}\nexec {real} "$@"'))
    if settles:
        assert added_in_commit(repo, tmp_path) == {"line\nbreak.md", "other.md"}
    else:
        assert added_in_commit(repo, tmp_path) == set()
        assert "New files were NOT staged: the scan could not run" in out
        assert git(repo, "show", "HEAD:src/app.py", home=tmp_path) == "print('v2')\n"


# --- N1-N4 for any tree, against a model of the rules -----------------------------------------------

def expected_new(loose: set[str], staged: set[str]) -> set[str]:
    """The header's rules 5 and 6 as a model: what the commit adds, renames aside."""
    def secret(n: str) -> bool:
        return n in SECRET_NAMES
    wanted = {n for n in loose | staged if not secret(n) and not n.endswith(".log")}
    return wanted if len(wanted) <= MAX_NEW else set()


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(n_loose=st.sampled_from([0, 1, MAX_NEW - 1, MAX_NEW, MAX_NEW + 1, 3 * MAX_NEW]),
       n_staged=st.sampled_from([0, 1, 3, MAX_NEW + 1]),
       secrets_loose=st.lists(st.sampled_from(SECRET_NAMES), unique=True, max_size=3),
       secrets_staged=st.lists(st.sampled_from(SECRET_NAMES), unique=True, max_size=3),
       plain=st.lists(st.sampled_from(PLAIN_NAMES), unique=True, max_size=3),
       logs=st.integers(0, 3), renames=st.sampled_from([0, 1, 2, MAX_NEW + 2]),
       edit=st.booleans(), linked=st.booleans())
def test_the_commit_obeys_the_limits_for_any_tree(n_loose, n_staged, secrets_loose, secrets_staged, plain, logs,
                                                  renames, edit, linked):
    home = Path(tempfile.mkdtemp(prefix="acw-"))
    try:
        repo = make_repo(home, branch="main" if linked else "work")
        write(repo, {f"pool/{i}.txt": f"tracked {i}\n".encode() for i in range(MAX_NEW + 2)})
        git(repo, "add", "-A", home=home)
        git(repo, "commit", "-q", "-m", "pool", home=home)
        top = add_worktree(repo, home) if linked else repo

        loose = {f"loose/{i}.md" for i in range(n_loose)} | set(plain) | {f"logs/{i}.log" for i in range(logs)}
        staged = {f"staged/{i}.md" for i in range(n_staged)}
        secrets = (set(secrets_loose) | set(secrets_staged))
        write(top, {n: f"{n}\n".encode() for n in loose | staged | secrets})
        for i in range(renames):
            (top / "pool" / f"{i}.txt").rename(top / f"moved{i}.txt")
        if edit:
            write(top, {"src/app.py": b"print('edited')\n"})
        to_stage = sorted(staged | set(secrets_staged))
        if to_stage:
            git(top, "add", "--", *to_stage, home=home)
        had_edit_or_rename = edit or renames > 0
        before = disk(top)
        head = git(top, "rev-parse", "HEAD", home=home).strip()

        out = hook(top, home)

        assert disk(top) == before                                 # N4, S3
        want = expected_new(loose, staged)
        moved = {f"moved{i}.txt" for i in range(renames)}
        now = git(top, "rev-parse", "HEAD", home=home).strip()
        left = {n for n in loose | staged if not n.endswith(".log")} - want - secrets
        if left:
            assert f"Left out {len(left)} new file(s), over the limit" in out                  # N4
        if secrets:
            assert f"Left out {len(secrets)} new file(s) with secret-looking names" in out     # N4
        assert not (set(git(top, "ls-files", home=home).splitlines()) & (secrets | left))
        if now == head:
            assert not want and not had_edit_or_rename
            assert "Auto-committed" not in out
            return
        assert git(top, "rev-parse", "HEAD~1", home=home).strip() == head
        assert new_in_commit(top, home) == want                    # N1 and its all-or-nothing rule
        assert added_in_commit(top, home) == want | moved          # N2: nothing secret, renames kept
        if edit:
            assert git(top, "show", "HEAD:src/app.py", home=home) == "print('edited')\n"       # N3
    finally:
        shutil.rmtree(home, ignore_errors=True)


# --- S1-S4 for any layout and any dirty tree, against a model of the rules ---------------------------

LAYOUTS = ["plain", "with_worktree", "with_prunable_worktree", "in_linked_worktree", "chief_of_staff",
           "in_chief_of_staff_worktree"]
EDITS = st.lists(st.sampled_from(["edit", "delete", "new", "new_log", "stage_edit", "stage_new", "subdir_new"]),
                 max_size=6)


def shared_reasons(layout: str, branch: str) -> tuple[list[str], bool]:
    """The rules of the header (a-c) for a main checkout, and whether a or c held (the checkout is
    shared with others, not only on its default branch). A linked worktree is never skipped."""
    if layout.startswith("in_"):
        return [], False
    reasons, others = [], False
    if layout in ("with_worktree", "with_prunable_worktree"):
        reasons.append("the repository has 1 linked worktree(s)")
        others = True
    if branch in ("main", "master"):
        reasons.append(f"{branch} is the default branch")
    if layout == "chief_of_staff":
        reasons.append(LIST)
        others = True
    return reasons, others


def apply_edits(top: Path, home: Path, edits: list[str]) -> None:
    for i, e in enumerate(edits):
        if e == "edit":
            write(top, {"src/app.py": f"print({i})\n".encode()})
        elif e == "delete" and (top / "notes.txt").exists():
            (top / "notes.txt").unlink()
        elif e == "new":
            write(top, {f"new{i}.md": b"n\n"})
        elif e == "new_log":
            write(top, {f"run{i}.log": b"log\n"})
        elif e == "stage_edit":
            write(top, {"README.md": f"r{i}\n".encode()})
            git(top, "add", "README.md", home=home)
        elif e == "stage_new":
            write(top, {f"staged{i}.md": b"s\n"})
            git(top, "add", f"staged{i}.md", home=home)
        elif e == "subdir_new":
            write(top, {f"src/deep/f{i}.py": b"d\n"})


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(layout=st.sampled_from(LAYOUTS), branch=st.sampled_from(["main", "master", "work"]), edits=EDITS,
       from_subdir=st.booleans())
def test_the_hook_follows_the_rules_for_any_layout(layout, branch, edits, from_subdir):
    home = Path(tempfile.mkdtemp(prefix="acw-"))
    try:
        name = "chief-of-staff" if "chief_of_staff" in layout else "repo"
        repo = make_repo(home, name=name, branch=branch)
        others = []                                                # checkouts the hook must not touch
        top = repo
        if layout in ("with_worktree", "with_prunable_worktree"):
            wt = add_worktree(repo, home)
            if layout == "with_prunable_worktree":
                shutil.rmtree(wt)
            else:
                others.append(wt)
        elif layout.startswith("in_"):
            top = add_worktree(repo, home)
            others.append(repo)
            apply_edits(repo, home, ["edit", "new"])               # other sessions' work beside ours
        apply_edits(top, home, edits)
        # --no-optional-locks: a plain git status would refresh the index the test is watching
        had_changes = git(top, "--no-optional-locks", "status", "--porcelain", home=home) != ""
        others_before = checkout_state(home, *others)
        files_before = disk(top)
        all_before = untouched(home, top)
        refs_before = all_before[0]
        head_before = git(top, "rev-parse", "HEAD", home=home).strip()
        cur = git(top, "branch", "--show-current", home=home).strip()

        out = hook(top / "src" if from_subdir else top, home)      # S4 inside

        assert disk(top) == files_before                           # S3
        assert checkout_state(home, *others) == others_before      # S3
        reasons, shared = shared_reasons(layout, branch)
        if reasons:                                                # S1
            assert untouched(home, top) == all_before
            if not had_changes:
                assert out == ""
            elif shared:
                assert out.startswith(shared_line(name, branch, "; ".join(reasons)))
            else:
                assert out.startswith(default_line(name, branch, reasons[0]))
        else:                                                      # S2
            assert "Not auto-committing" not in out
            head = git(top, "rev-parse", "HEAD", home=home).strip()
            if head != head_before:
                assert git(top, "rev-parse", "HEAD~1", home=home).strip() == head_before
                assert out.startswith("Auto-committed")
            moved = {line.split()[0] for line in set(refs(top, home).splitlines()) ^ set(refs_before.splitlines())
                     if line.startswith("refs/")}
            assert moved <= {f"refs/heads/{cur}"}
            if had_changes and not set(edits) <= {"new_log"}:
                assert head != head_before                         # something committable was committed
    finally:
        shutil.rmtree(home, ignore_errors=True)
