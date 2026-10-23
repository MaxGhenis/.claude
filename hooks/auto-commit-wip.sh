#!/bin/bash
# PreCompact hook: Auto-commit WIP before context compression.
# Context compression often precedes crashes/context exhaustion,
# so this ensures agent work is saved to git before it's lost.
#
# Guards on NEW (untracked) files, added after 2026-08-30, when this hook
# swept 879 lane logs (4.8 GB; five over GitHub's 100 MB push limit) into
# ~/TheAxiomFoundation/ops and the branch history had to be rewritten:
#   1. never commit a new blob larger than MAX_NEW_FILE_BYTES (50 MB: GitHub
#      warns at 50 MB and rejects pushes at 100 MB) — checked at scan time and
#      again on the staged blobs, so a file that grows while the hook runs is
#      unstaged before the commit
#   2. never stage an untracked *.log (case-insensitive; includes *.err.log)
#   3. never stage a nested git repository as a gitlink
#   4. say what was skipped (count + total size) in the hook output
# Already-tracked files keep the old behaviour: every modification and
# deletion is committed regardless of size or name (with a WARNING in the
# output when a modified tracked blob is over the limit). A tracked file that
# was renamed into a skipped name is still staged as a rename: its content is
# already in the repo, so the guard has nothing to protect.
#
# Staging is scan-then-add: only files the scan approved are added, by exact
# path, so a file created after the scan is never swept in blind. When the
# scan itself cannot run, the hook fails closed: tracked changes are still
# committed, no new file is staged, and the output says so.
#
# Shared main checkouts are left alone (added 2026-10-23). The hook fired six
# times in ~/chief-of-staff, the main checkout of a repository that many
# sessions and launchd tools write to, and each time committed everyone's
# uncommitted files onto master as a fixup of whatever HEAD was (c01141053
# on 9/27 to 60db0a798 on 10/22; 307,379 files in eb87245bb, other sessions'
# email drafts in 60db0a798). From 8/1 to 10/23 it made at least 39
# auto-commits in the main checkouts of 21 repositories (their HEAD
# reflogs): 35 where the repository had linked worktrees, the other 4 onto
# local main or master.
# So in a main checkout (its git dir is the common dir) it commits nothing,
# stages nothing and does not write the index when any of these holds:
#   a. the repository has a linked worktree: sessions work in their own, and
#      the main checkout is the common base that others write to;
#   b. the branch is the default branch (main, master, or origin/HEAD's), or
#      a rebase of it is in progress: local main takes deliberate commits only;
#   c. the checkout is on SHARED_CHECKOUTS.
# The output says which held and how many paths were left. The files stay
# on disk, so nothing is lost. If git cannot name the git dir and common dir,
# the hook commits nothing (it fails closed). A linked worktree keeps the
# auto-commit, and so does a feature branch in a repository with no linked
# worktree.

MAX_NEW_FILE_BYTES=$((50 * 1024 * 1024))
EXAMPLES=3   # how many paths to name per category in the summary line
SHARED_CHECKOUTS=(chief-of-staff)   # main checkouts under $HOME, always shared

# Only run in git repos
git rev-parse --is-inside-work-tree &>/dev/null || exit 0

# ~/.claude is a public config repo (github.com/MaxGhenis/.claude) —
# it only gets deliberate commits, never auto-WIP sweeps. Matches the main
# checkout and any linked worktree of it, with or without $HOME in the env.
home=$HOME
if [ -z "$home" ]; then
  case $(id -un) in *[!A-Za-z0-9._-]*) ;; *) home=$(eval printf '%s' "~$(id -un)") ;; esac
fi
real() { [ -n "$1" ] && (cd "$1" 2>/dev/null && pwd -P); }   # path -> physical path, or nothing
claude_dir=$(real "$home/.claude")
toplevel=$(git rev-parse --show-toplevel 2>/dev/null)
[ -n "$toplevel" ] || exit 0
common=$(real "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")
if [ -n "$claude_dir" ]; then
  [ "$(real "$toplevel")" = "$claude_dir" ] && exit 0
  [ -n "$common" ] && [ "$common" = "$claude_dir/.git" ] && exit 0
fi

# `git add -A` / `commit -a` always acted on the whole tree even when the
# session sat in a subdirectory; the untracked-file scan must see the same tree.
cd "$toplevel" || exit 0

branch=$(git branch --show-current 2>/dev/null)
[ -n "$branch" ] || branch="detached"
repo=$(basename "$toplevel")

# --- Shared main checkout: leave it alone (rules a-c in the header) ---
# This path is read-only: no add, no commit, and the change count runs with
# --no-optional-locks so git status does not refresh the index.
git_dir=$(real "$(git rev-parse --path-format=absolute --git-dir 2>/dev/null)")
if [ -z "$git_dir" ] || [ -z "$common" ]; then
  echo "Not auto-committing in $repo on branch $branch before context compact: git did not name its git dir and common dir, so the hook cannot tell whether this is a shared main checkout."
  exit 0
fi
if [ "$git_dir" = "$common" ]; then
  why="" others=0
  # A linked worktree is a folder in the common dir's worktrees/, which is
  # what git worktree list reads; a prunable one counts too.
  linked=0
  for w in "$common"/worktrees/*/; do [ -d "$w" ] && linked=$((linked + 1)); done
  [ "$linked" -gt 0 ] && why="the repository has $linked linked worktree(s)" others=1
  # Mid-rebase there is no current branch: the branch being rebased, which
  # gets every commit made now, is in head-name.
  onto=$branch rebasing=""
  if [ "$branch" = detached ]; then
    for f in rebase-merge/head-name rebase-apply/head-name; do
      [ -f "$git_dir/$f" ] || continue
      h=$(cat "$git_dir/$f" 2>/dev/null)
      case "$h" in refs/heads/?*) onto=${h#refs/heads/} rebasing=", being rebased," ;; esac
      break
    done
  fi
  default=$(git symbolic-ref -q refs/remotes/origin/HEAD 2>/dev/null)
  default=${default#refs/remotes/origin/}
  case "$onto" in
    main | master | "${default:-main}") why="$why${why:+; }$onto$rebasing is the default branch" ;;
  esac
  top=$(real "$toplevel")
  for s in "${SHARED_CHECKOUTS[@]}"; do
    [ -n "$home" ] && [ "$top" = "$(real "$home/$s")" ] &&
      why="$why${why:+; }~/$s is on this hook's list of shared checkouts" others=1
  done
  if [ -n "$why" ]; then
    # One NUL-ended record per path (--no-renames: no second path), held with
    # \001 in place of NUL so a name with a newline still counts once.
    porcelain=$(git --no-optional-locks status --porcelain --no-renames -z 2>/dev/null | tr '\0' '\001')
    [ -z "$porcelain" ] && exit 0
    n_new=$(printf '%s' "$porcelain" | tr '\001' '\0' | grep -z -c '^?? ')
    n_mod=$(( $(printf '%s' "$porcelain" | tr -cd '\001' | wc -c) - n_new ))
    left="Left $n_mod changed tracked path(s) and $n_new untracked path(s) (a new folder counts once) as they are, on disk"
    if [ "$others" -eq 1 ]; then
      echo "Not auto-committing in $repo on branch $branch before context compact: it is a shared main checkout ($why). $left; other sessions' work may be among them. Commit only your own files, by path (git add -- <paths>; git commit), or work in a linked worktree of your own."
    else
      echo "Not auto-committing in $repo on branch $branch before context compact: it is the main checkout and $why, which takes deliberate commits only. $left. Commit what you mean to keep, by path (git add -- <paths>; git commit), or work on a branch of your own."
    fi
    exit 0
  fi
fi

# Check for uncommitted changes
changes=$(git status --porcelain 2>/dev/null)
[ -z "$changes" ] && exit 0

# A merge/rebase/cherry-pick with conflicts: committing would bake conflict
# markers into a bogus commit and finalise the merge. Leave it alone.
if [ -n "$(git diff --name-only --diff-filter=U 2>/dev/null | head -1)" ]; then
  echo "Not auto-committing in $repo on branch $branch: unmerged paths (merge/rebase in progress); resolve them first."
  exit 0
fi

human() {  # bytes -> "4.8 GB"
  awk -v b="$1" 'BEGIN {
    split("B KB MB GB TB", u, " "); i = 1
    while (b >= 1024 && i < 5) { b /= 1024; i++ }
    s = (b == int(b)) ? sprintf("%d", b) : sprintf("%.1f", b)
    if (s == "1024.0" && i < 5) { s = "1"; i++ }
    printf "%s %s", s, u[i]
  }'
}
clean() { printf '%s' "$1" | tr '\001-\037\177' ' '; }   # one line, no control bytes
first_line() { printf '%s\n' "$1" | grep -m1 "$2"; }

# --- Scan untracked files (honours .gitignore) into keep + skip lists ---
# One `git ls-files` plus one batched `stat` — no `find`, no per-file forks —
# so 50,000 untracked files scan in about a second. If mktemp fails the hook
# commits tracked changes only.
stage_new=1
tmp=""
if tmp=$(mktemp -d "${TMPDIR:-/tmp}/auto-commit-wip.XXXXXX" 2>/dev/null) && [ -n "$tmp" ]; then
  trap 'rm -rf "$tmp"' EXIT
else
  stage_new=0; tmp=""
fi
names=$tmp/names keep=$tmp/keep skips=$tmp/skips sizes=$tmp/sizes
tab=$'\t'
skip_reason=() skip_size=() skip_path=()
unsized=0
add_skip() { skip_reason+=("$1"); skip_size+=("$2"); skip_path+=("$3"); }
[ -n "$tmp" ] && : > "$keep"

if [ "$stage_new" -eq 1 ] && stat -f '%z' . >/dev/null 2>&1 &&
   git ls-files --others --exclude-standard -z > "$names" 2>/dev/null; then
  if [ "$(tr -cd '\n' < "$names" | wc -c | tr -d ' ')" -eq 0 ]; then
    # Fast path (no path contains a newline): one "<bytes>\t<path>" line per
    # file, so a file stat could not see (vanished, unreadable directory) just
    # has no line and is not staged. Skip records: "reason\tbytes\tpath".
    xargs -0 stat -f '%z%t%N' -- < "$names" 2>/dev/null |
      KEEP=$keep awk -F'\t' -v max="$MAX_NEW_FILE_BYTES" '{
        size = $1; path = substr($0, length($1) + 2)
        if (path == "") next
        if (path ~ /\/$/)                   print "nested\t" size "\t" path
        else if (tolower(path) ~ /\.log$/)  print "log\t" size "\t" path
        else if (size + 0 > max + 0)        print "big\t" size "\t" path
        else                                print path > ENVIRON["KEEP"]
      }' > "$skips"
    tr '\n' '\0' < "$keep" > "$keep.nul" && mv "$keep.nul" "$keep"
    while IFS= read -r rec; do
      reason=${rec%%"$tab"*}; rest=${rec#*"$tab"}
      add_skip "$reason" "${rest%%"$tab"*}" "${rest#*"$tab"}"
    done < "$skips"
    # Listed by ls-files but not sized by stat: vanished or unreadable. Report.
    unsized=$(( $(tr -cd '\0' < "$names" | wc -c) - $(tr -cd '\0' < "$keep" | wc -c) - $(wc -l < "$skips") ))
    [ "$unsized" -gt 0 ] || unsized=0
  else
    # Slow path (some path contains a newline): sizes come one per line in
    # argument order, paired with the NUL name list; a file that vanishes
    # mid-scan breaks the pairing, which the count check catches (retry once,
    # then fail closed for new files).
    pair() {
      xargs -0 stat -f '%z' -- < "$names" > "$sizes" 2>/dev/null
      [ "$(tr -cd '\0' < "$names" | wc -c | tr -d ' ')" -eq "$(wc -l < "$sizes" | tr -d ' ')" ]
    }
    if pair || { git ls-files --others --exclude-standard -z > "$names" 2>/dev/null && pair; }; then
      while IFS= read -r -d '' path <&3 && IFS= read -r size <&4; do
        case "$size" in '' | *[!0-9]*) continue ;; esac
        case "$path" in
          */)               add_skip nested "$size" "$path" ;;
          *.[lL][oO][gG])   add_skip log "$size" "$path" ;;
          *) if [ "$size" -gt "$MAX_NEW_FILE_BYTES" ]; then add_skip big "$size" "$path"
             else printf '%s\0' "$path"; fi ;;
        esac
      done 3< "$names" 4< "$sizes" > "$keep"
    else
      stage_new=0
    fi
  fi
else
  stage_new=0
fi

# --- Rename exemption: a skipped file whose content is an index entry that is
# about to be staged as deleted (the user renamed/moved it) is kept, so the
# commit records a rename instead of a deletion. Only runs when both lists are
# non-empty; only hashes skipped files whose size matches a deleted blob.
renamed=0 renamed_ex=""
if [ "$stage_new" -eq 1 ] && [ "${#skip_path[@]}" -gt 0 ] &&
   git diff --name-only --diff-filter=D -z > "$tmp/deleted" 2>/dev/null && [ -s "$tmp/deleted" ]; then
  : > "$tmp/delblobs"
  while IFS= read -r -d '' dp; do
    sha=$(git --literal-pathspecs ls-files -s -- "$dp" 2>/dev/null | awk 'NR == 1 { print $2 }')
    [ -n "$sha" ] && echo "$(git cat-file -s "$sha" 2>/dev/null) $sha" >> "$tmp/delblobs"
  done < "$tmp/deleted"
  for i in "${!skip_path[@]}"; do
    [ "${skip_reason[$i]}" = nested ] && continue
    grep -q "^${skip_size[$i]} " "$tmp/delblobs" || continue
    h=$(git hash-object -- "${skip_path[$i]}" 2>/dev/null)
    if [ -n "$h" ] && grep -q " $h\$" "$tmp/delblobs"; then
      printf '%s\0' "${skip_path[$i]}" >> "$keep"
      skip_reason[$i]=renamed
      renamed=$((renamed + 1))
      [ "$renamed" -le "$EXAMPLES" ] && renamed_ex="$renamed_ex${renamed_ex:+, }$(clean "${skip_path[$i]}")"
    fi
  done
fi

# --- Stage tracked changes (as before), then the approved new files ---
add_err=$(git add -u --ignore-errors 2>&1 >/dev/null)
if fatal=$(first_line "$add_err" '^fatal:'); then
  echo "Auto-commit FAILED in $repo on branch $branch: $(clean "$fatal") — nothing committed."
  exit 0
fi
unreadable_tracked=$(printf '%s\n' "$add_err" | grep -c 'unable to index file')

new_note=""
if [ "$stage_new" -eq 1 ] && [ -s "$keep" ]; then
  # update-index takes exact paths (no glob expansion) and, with --remove,
  # shrugs off a path that vanished since the scan instead of aborting.
  if ! new_err=$(git update-index --add --remove -z --stdin < "$keep" 2>&1 >/dev/null); then
    # One unreadable file aborts update-index; `git add --ignore-errors` skips
    # it and adds the rest (but aborts if a path vanished — then report).
    new_err=$(while IFS= read -r -d '' p; do printf ':(literal)%s\0' "$p"; done < "$keep" |
              git add --ignore-errors --pathspec-from-file=- --pathspec-file-nul 2>&1 >/dev/null)
    if fatal=$(first_line "$new_err" '^fatal:'); then
      new_note=" New files were NOT staged: $(clean "$fatal")."
    else
      n=$(printf '%s\n' "$new_err" | grep -c 'unable to index file')
      [ "$n" -gt 0 ] && new_note=" $n new file(s) could not be read and were not staged."
    fi
  fi
elif [ "$stage_new" -eq 0 ]; then
  new_note=" New files were NOT staged: the size scan could not run (needs a writable TMPDIR, BSD stat, and a stable file list)."
fi

# --- Blob-size check on what is actually staged: unstage any NEW blob over the
# limit (it grew after the scan, or was staged earlier in the session), and
# warn about MODIFIED tracked blobs over it (those stay committed, rule 4).
grown=0 grown_ex="" big_tracked=0 big_tracked_ex=""
if [ -n "$tmp" ]; then
  git diff --cached --diff-filter=AM --raw --no-abbrev 2>/dev/null | awk '{ print $4 }' |
    git cat-file --batch-check='%(objectsize) %(objectname)' 2>/dev/null |
    awk -v max="$MAX_NEW_FILE_BYTES" '$1 + 0 > max + 0 { print $2 }' > "$tmp/bigshas"
  if [ -s "$tmp/bigshas" ]; then
    while IFS= read -r -d '' meta && IFS= read -r -d '' path; do
      rest=${meta#* * * }; sha=${rest%% *}; status=${rest#* }
      grep -q "^$sha\$" "$tmp/bigshas" || continue
      if [ "$status" = A ]; then
        if git --literal-pathspecs rm --cached -q -- "$path" >/dev/null 2>&1; then
          grown=$((grown + 1))
          [ "$grown" -le "$EXAMPLES" ] && grown_ex="$grown_ex${grown_ex:+, }$(clean "$path")"
        fi
      else
        big_tracked=$((big_tracked + 1))
        [ "$big_tracked" -le "$EXAMPLES" ] && big_tracked_ex="$big_tracked_ex${big_tracked_ex:+, }$(clean "$path")"
      fi
    done < <(git diff --cached --diff-filter=AM --raw --no-abbrev -z 2>/dev/null)
  fi
fi

n_changed=$(git diff --cached --name-only -z 2>/dev/null | tr -cd '\0' | wc -c | tr -d ' ')

# --- Summary line ---
skipped=0 skipped_bytes=0 skipped_big=0 skipped_log=0 nested=0 skip_ex="" nested_ex=""
for i in "${!skip_path[@]}"; do
  case "${skip_reason[$i]}" in
    big | log)
      skipped=$((skipped + 1)); skipped_bytes=$((skipped_bytes + skip_size[i]))
      if [ "${skip_reason[$i]}" = big ]; then skipped_big=$((skipped_big + 1)); else skipped_log=$((skipped_log + 1)); fi
      [ "$skipped" -le "$EXAMPLES" ] && skip_ex="$skip_ex${skip_ex:+, }$(clean "${skip_path[$i]}")" ;;
    nested)
      nested=$((nested + 1))
      [ "$nested" -le "$EXAMPLES" ] && nested_ex="$nested_ex${nested_ex:+, }$(clean "${skip_path[$i]}")" ;;
  esac
done
more() { [ "$1" -gt "$EXAMPLES" ] && printf ', +%d more' "$(( $1 - EXAMPLES ))"; }
note=""
if [ "$skipped" -gt 0 ]; then
  why=""
  [ "$skipped_big" -gt 0 ] && why="$skipped_big over $(human "$MAX_NEW_FILE_BYTES")"
  [ "$skipped_log" -gt 0 ] && why="$why${why:+, }$skipped_log *.log"
  note="$note Skipped $skipped untracked file(s) totalling $(human "$skipped_bytes") ($why): $skip_ex$(more "$skipped") — left untracked, not committed."
fi
[ "$nested" -gt 0 ] && note="$note Not added: $nested nested git repo(s): $nested_ex$(more "$nested")."
[ "$renamed" -gt 0 ] && note="$note Kept $renamed renamed tracked file(s) whose content was already in the repo: $renamed_ex$(more "$renamed")."
[ "$grown" -gt 0 ] && note="$note Unstaged $grown new file(s) over $(human "$MAX_NEW_FILE_BYTES") by staging time: $grown_ex$(more "$grown")."
[ "$big_tracked" -gt 0 ] && note="$note WARNING: $big_tracked tracked file(s) over $(human "$MAX_NEW_FILE_BYTES") modified in this commit: $big_tracked_ex$(more "$big_tracked") — GitHub rejects pushes with blobs over 100 MB."
[ "$unreadable_tracked" -gt 0 ] && note="$note $unreadable_tracked tracked file(s) could not be read and were not committed."
[ "$unsized" -gt 0 ] && note="$note $unsized untracked file(s) could not be sized (vanished or unreadable) and were not staged."
note="$note$new_note"

if [ "$n_changed" -eq 0 ]; then
  echo "Nothing to auto-commit in $repo on branch $branch before context compact.$note"
  exit 0
fi

# Auto-commit the index as staged above (prefer --fixup=HEAD for easier
# squashing via rebase --autosquash; the -m form covers an unborn branch).
if git commit -q --fixup=HEAD --no-verify >/dev/null 2>&1 ||
   git commit -q -m "WIP: auto-save before context compact ($n_changed files on $branch)" --no-verify >/dev/null 2>&1; then
  echo "Auto-committed $n_changed file(s) in $repo on branch $branch before context compact.$note"
else
  echo "Auto-commit FAILED in $repo on branch $branch; changes left staged, not committed.$note"
fi
exit 0
