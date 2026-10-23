"""Tests for hooks/auto-commit-wip.sh, the PreCompact hook that commits work in progress.

Run: uv run --with pytest --with hypothesis pytest tests/test_auto_commit_wip.py -q -p no:cacheprovider

They run the real script with /bin/bash against real git repositories under the pytest temp folder.
$HOME, $TMPDIR and git's global config point into that folder, so nothing of the user's is read or
written. AUTO_COMMIT_WIP_HOOK names another copy of the script to test.

Invariants, for every repository layout and every dirty tree:
  S1  in a shared main checkout (the git dir is the common dir, and the repository has a linked
      worktree, or the branch is main, master or origin/HEAD's, or the checkout is ~/chief-of-staff)
      the hook changes no ref, does not write the index, and changes no working file; it prints one
      "Not auto-committing" line naming the rules that held when there are changes, and nothing
      when there are none;
  S2  anywhere else (a linked worktree, a feature branch in a repository with no linked worktree)
      it commits the work in progress as before: one new commit on the current branch, whose parent
      is the old HEAD, and no other ref moves;
  S3  it never changes, moves or removes a working file, and another worktree's index and files
      are never touched;
  S4  it exits 0 with nothing on stderr.
The property test checks S1-S4 against a model of the rules (`shared_reasons`), so the bash
script and its stated rules are tested against each other."""
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


def env_for(home: Path, **extra) -> dict:
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(home / "tmp"), "LC_ALL": "C",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    env.update({k: str(v) for k, v in extra.items()})
    return env


def git(where: Path, *args: str, home: Path, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(where), *args], capture_output=True, env=env_for(home))
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


def hook(where: Path, home: Path) -> str:
    r = subprocess.run(["/bin/bash", str(HOOK)], cwd=where, capture_output=True, env=env_for(home))
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


def snapshot(home: Path, *tops: Path) -> tuple:
    return tuple((refs(t, home), index_state(t, home), disk(t)) for t in tops)


def checkout_state(home: Path, *tops: Path) -> tuple:
    """What belongs to each checkout alone: its HEAD (and branch), index and files. Refs are shared
    by all worktrees of a repository, so another worktree's own commit is not a change here."""
    return tuple((git(t, "rev-parse", "HEAD", home=home), git(t, "branch", "--show-current", home=home),
                  index_state(t, home), disk(t)) for t in tops)


def dirty(top: Path, home: Path) -> None:
    """Another session's work: a tracked edit, a staged edit, a deletion and a new file."""
    write(top, {"src/app.py": b"print('theirs')\n", "notes.txt": b"staged by someone\n", "drafts/email.md": b"draft\n"})
    git(top, "add", "notes.txt", home=home)
    (top / "README.md").unlink()


# --- S1: a shared main checkout is left alone ------------------------------------------------------

def test_a_main_checkout_with_a_linked_worktree_is_left_alone(tmp_path):
    repo = make_repo(tmp_path)
    add_worktree(repo, tmp_path)
    dirty(repo, tmp_path)
    before = snapshot(tmp_path, repo)
    out = hook(repo, tmp_path)
    assert out.startswith("Not auto-committing in repo on branch work before context compact: it is a shared "
                          "main checkout (the repository has 1 linked worktree(s)).")
    assert "Left 3 changed tracked and 1 untracked path(s) as they are, on disk" in out
    assert snapshot(tmp_path, repo) == before
    assert commits(repo, tmp_path) == ["base"]
    assert git(repo, "diff", "--cached", "--name-only", home=tmp_path) == "notes.txt\n"   # still staged, as left


def test_it_is_left_alone_from_a_subfolder_too(tmp_path):
    repo = make_repo(tmp_path)
    add_worktree(repo, tmp_path)
    dirty(repo, tmp_path)
    before = snapshot(tmp_path, repo)
    out = hook(repo / "src", tmp_path)
    assert "shared main checkout (the repository has 1 linked worktree(s))" in out
    assert snapshot(tmp_path, repo) == before


def test_a_prunable_linked_worktree_still_counts(tmp_path):
    repo = make_repo(tmp_path)
    wt = add_worktree(repo, tmp_path)
    shutil.rmtree(wt)                                              # folder gone, metadata not pruned
    dirty(repo, tmp_path)
    before = snapshot(tmp_path, repo)
    assert "the repository has 1 linked worktree(s)" in hook(repo, tmp_path)
    assert snapshot(tmp_path, repo) == before


@pytest.mark.parametrize("branch", ["main", "master"])
def test_the_default_branch_of_a_main_checkout_is_left_alone(tmp_path, branch):
    repo = make_repo(tmp_path, branch=branch)
    dirty(repo, tmp_path)
    before = snapshot(tmp_path, repo)
    out = hook(repo, tmp_path)
    assert f"shared main checkout ({branch} is the default branch)" in out
    assert snapshot(tmp_path, repo) == before


def test_origin_head_names_the_default_branch(tmp_path):
    seed = make_repo(tmp_path, name="seed", branch="trunk")
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(tmp_path / "origin.git"), home=tmp_path)
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(tmp_path / "clone"), home=tmp_path)
    clone = tmp_path / "clone"
    assert git(clone, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", home=tmp_path).strip() == "origin/trunk"
    dirty(clone, tmp_path)
    before = snapshot(tmp_path, clone)
    assert "shared main checkout (trunk is the default branch)" in hook(clone, tmp_path)
    assert snapshot(tmp_path, clone) == before
    git(clone, "checkout", "-q", "-b", "feature", home=tmp_path)    # a feature branch is not
    assert "Auto-committed" in hook(clone, tmp_path)
    assert commits(clone, tmp_path)[:2] == ["fixup! base", "base"]


def test_an_unborn_default_branch_is_left_alone(tmp_path):
    repo = make_repo(tmp_path, branch="main", commit=False)
    write(repo, {"a.md": b"a\n"})
    out = hook(repo, tmp_path)
    assert "shared main checkout (main is the default branch). Left 0 changed tracked and 1 untracked" in out
    assert git(repo, "rev-parse", "-q", "--verify", "HEAD", home=tmp_path, check=False) == ""


def test_chief_of_staff_is_on_the_list_on_any_branch(tmp_path):
    cos = make_repo(tmp_path, name="chief-of-staff", branch="side-branch")
    dirty(cos, tmp_path)
    before = snapshot(tmp_path, cos)
    out = hook(cos, tmp_path)
    assert "shared main checkout (~/chief-of-staff is on this hook's list of shared checkouts)" in out
    assert snapshot(tmp_path, cos) == before
    (tmp_path / "cos-link").symlink_to(cos)                        # reached through a symlink: same checkout
    assert "~/chief-of-staff is on this hook's list" in hook(tmp_path / "cos-link", tmp_path)
    assert snapshot(tmp_path, cos) == before


def test_every_rule_that_holds_is_named(tmp_path):
    cos = make_repo(tmp_path, name="chief-of-staff", branch="master")
    add_worktree(cos, tmp_path)
    add_worktree(cos, tmp_path, name="wt2", branch="side2")
    dirty(cos, tmp_path)
    assert ("(the repository has 2 linked worktree(s); master is the default branch; "
            "~/chief-of-staff is on this hook's list of shared checkouts)") in hook(cos, tmp_path)


def test_a_clean_shared_checkout_prints_nothing(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    add_worktree(repo, tmp_path)
    before = snapshot(tmp_path, repo)
    assert hook(repo, tmp_path) == ""
    assert snapshot(tmp_path, repo) == before


def test_a_name_with_a_newline_counts_once(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    write(repo, {"two\nlines.md": b"x\n", "plain.md": b"y\n"})
    assert "Left 0 changed tracked and 2 untracked path(s)" in hook(repo, tmp_path)


def test_an_index_lock_held_by_another_session_does_not_matter(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    dirty(repo, tmp_path)
    lock = repo / ".git" / "index.lock"
    lock.write_bytes(b"")                                          # someone else's git command is mid-write
    out = hook(repo, tmp_path)
    assert "Left 3 changed tracked and 1 untracked path(s)" in out and lock.exists()


# --- S2: a linked worktree keeps the auto-commit -----------------------------------------------------

def test_a_linked_worktree_still_commits_its_own_work_only(tmp_path):
    repo = make_repo(tmp_path, branch="main")
    wt = add_worktree(repo, tmp_path)
    dirty(repo, tmp_path)                                          # other sessions' files in the main checkout
    main_before = snapshot(tmp_path, repo)[0][1:]                  # its index and files
    main_ref = git(repo, "rev-parse", "main", home=tmp_path)
    write(wt, {"src/app.py": b"print('mine')\n", "src/mine.py": b"x = 1\n"})
    out = hook(wt, tmp_path)
    assert "Auto-committed 2 file(s) in wt on branch side before context compact." in out
    assert commits(wt, tmp_path) == ["fixup! base", "base"]
    assert tracked(wt, tmp_path) == {"README.md", "src/app.py", "notes.txt", "src/mine.py"}
    assert git(repo, "rev-parse", "main", home=tmp_path) == main_ref
    assert snapshot(tmp_path, repo)[0][1:] == main_before


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


# --- S1-S4 for any layout and any dirty tree, against a model of the rules ---------------------------

LAYOUTS = ["plain", "with_worktree", "with_prunable_worktree", "in_linked_worktree", "chief_of_staff",
           "in_chief_of_staff_worktree"]
EDITS = st.lists(st.sampled_from(["edit", "delete", "new", "new_log", "stage_edit", "stage_new", "subdir_new"]),
                 max_size=6)


def shared_reasons(layout: str, branch: str) -> list[str]:
    """The rules of the header (a-c), for a main checkout; a linked worktree is never shared."""
    if layout.startswith("in_"):
        return []
    reasons = []
    if layout in ("with_worktree", "with_prunable_worktree"):
        reasons.append("the repository has 1 linked worktree(s)")
    if branch in ("main", "master"):
        reasons.append(f"{branch} is the default branch")
    if layout == "chief_of_staff":
        reasons.append("~/chief-of-staff is on this hook's list of shared checkouts")
    return reasons


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
    home = Path(tempfile.mkdtemp(prefix="acw-", dir=os.environ.get("PYTEST_TMP")))
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
        refs_before, index_before = refs(top, home), index_state(top, home)
        head_before = git(top, "rev-parse", "HEAD", home=home).strip()
        cur = git(top, "branch", "--show-current", home=home).strip()

        out = hook(top / "src" if from_subdir else top, home)      # S4 inside

        assert disk(top) == files_before                           # S3
        assert checkout_state(home, *others) == others_before      # S3
        reasons = shared_reasons(layout, branch)
        if reasons:                                                # S1
            assert refs(top, home) == refs_before and index_state(top, home) == index_before
            if had_changes:
                assert out.startswith(f"Not auto-committing in {name} on branch {branch} before context compact: "
                                      f"it is a shared main checkout ({'; '.join(reasons)}).")
            else:
                assert out == ""
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
