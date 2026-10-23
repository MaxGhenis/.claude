"""Tests for hooks/auto-commit-wip.sh, the PreCompact hook that commits work in progress.

Run: uv run --with pytest --with hypothesis pytest tests/test_auto_commit_wip.py -q -p no:cacheprovider

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
LIST = "~/chief-of-staff is on this hook's list of shared checkouts"


def env_for(home: Path, **extra) -> dict:
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(home / "tmp"), "LC_ALL": "C",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
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
