#!/bin/bash
# PreCompact hook: Auto-commit WIP before context compression.
# Context compression often precedes crashes/context exhaustion,
# so this ensures agent work is saved to git before it's lost.
#
# Guards on NEW (untracked) files, added after 2026-08-30, when this hook
# swept 879 lane logs (4.8 GB; five over GitHub's 100 MB push limit) into a
# shared clone and the branch history had to be rewritten:
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
# Bulk sweeps and secret names (added 2026-11-01). The guards above still let
# one session's compaction commit what other sessions had left in a shared
# clone: on 2026-10-31 the hook swept 5,335 and then 349 files that way, a
# key file and private drafts among them. A hook cannot tell whose file it
# sees, so these rules go by what it can measure:
#   5. one auto-commit adds at most MAX_NEW_FILES new paths. When more would
#      enter it, none do: the tracked changes go in alone, and the new files
#      stay where they are, not hashed unless someone had already put them in
#      the index. Files that the commit will not take anyway (rules 1-3,
#      secret names) do not count, and neither does an exact rename of a file
#      the commit deletes.
#   6. a new path whose name looks like a secret (SECRET_NAMES) never enters
#      the index, however few new files there are. One that is already staged
#      is unstaged, and a rename into such a name is left out too.
#   7. a merge, rebase, cherry-pick, revert or bisect in progress stops the
#      hook, with or without conflicts: the new paths in the index then came
#      from that operation, and a commit would finish it or, in a bisect, take
#      the place of the commit under test.
# A check on the index enforces rules 5 and 6 on staged paths as well as scanned
# ones. The commit comes from a private copy of the index, checked after the
# copy, so what another session stages meanwhile stays staged and out of it.
# From a branch, it lands only on the branch and parent the rules judged. If a
# check cannot run, the hook commits no new path; if HEAD moved by its last
# compare, it commits nothing. Files left out stay on disk and the output names
# them, so a session keeps its own work by committing it by path. Tracked
# changes are not filtered (see above).
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
# on disk, so nothing is lost. If git cannot name the branch, the git dir and
# the common dir, or the common dir's worktrees/ cannot be read, the hook commits
# nothing (it fails closed). A linked worktree keeps the
# auto-commit, and so does a feature branch in a repository with no linked
# worktree.

MAX_NEW_FILE_BYTES=$((50 * 1024 * 1024))
EXAMPLES=3   # how many paths to name per category in the summary line
SHARED_CHECKOUTS=(chief-of-staff)   # main checkouts under $HOME, always shared
MAX_NEW_FILES=25   # more new paths than this in one auto-commit and none go in
# Names that never enter the index as new paths: extended regexes, matched
# without regard to case against the path from the repository top, so a folder
# such as secrets/ counts. They are broad on purpose: a false match costs one
# line of output and a commit by hand, a miss puts a key in the branch history.
SECRET_NAMES=(
  '(^|/)\.env(rc)?([-_.]|$)|\.env(\.(bak|backup|dev|development|local|old|orig|prod|production|save|stage|staging|test))?$'
  '(^|/)env\.(dev|development|local|prod|production|stage|staging|test)$'
  '(^|/)(\.ssh|\.gnupg|\.aws|\.docker|\.kube)/|(^|/)\.config/(gh|rclone)/'  # credential folders
  '(^|/)(_netrc|\.netrc|\.npmrc|\.pypirc|\.pgpass|\.htpasswd|\.boto)$'  # credential dotfiles
  '(^|/)(\.my\.cnf|\.mylogin\.cnf|\.yarnrc\.yml|wp-config\.php)$|(^|/)kubeconfig(\.ya?ml)?$|vault[-_.]?pass'
  '(^|/)(\.git-credentials|\.dockercfg|\.s3cfg|auth\.json)$'
  '(^|/)id_(rsa|dsa|ecdsa|ed25519)'                                   # ssh keys
  '\.(pem|key|p8|p12|pfx|jks|keystore|ppk|kdbx)(\.(bak|backup|old|orig|save))?$'  # and their backups
  '\.(tfvars|tfstate)(\.[a-z]+)?$|priv(ate)?\.asc$|secring'
  'secret([-_./kst]|$)|credential|password|passwd|service[-_.]?account|firebase-adminsdk'  # not secretary
  '(access|api|auth|deploy|encryption|master|private|signing|ssh)[-_.]?key'
  '(^|[-_./])(keys?|keyfile|privkey)(\.(b64|bin|der|json|txt))?$'     # deploy-key, gcp-key.json
  '(^|[-_./])token(\.[a-z0-9]+)?$'                                    # bot-token.txt, not tokens.css
  '(access|api|auth|bearer|oauth|refresh|session)[-_.]?tokens?|github_pat|(^|[-_./])creds?([-_.]|$)'
)
# ...unless the name ends as a template or a public key.
NOT_SECRET='[-_.](dist|example|sample|template|tmpl)(\.(cfg|conf|ini|json|md|toml|txt|ya?ml))?$|(^|/)id_[^/]*\.pub$|key[^/]*\.pub$'

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

repo=$(basename "$toplevel")
if ! branch=$(git branch --show-current 2>/dev/null); then
  echo "Not auto-committing in $repo before context compact: git did not name the current branch, so the hook cannot tell whether this is a shared main checkout."
  exit 0
fi
[ -n "$branch" ] || branch="detached"
head_ref=$(git symbolic-ref -q HEAD 2>/dev/null) head_sha=$(git rev-parse -q --verify HEAD 2>/dev/null)

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
  [ ! -e "$common/worktrees" ] || ls "$common/worktrees" >/dev/null 2>&1 ||
    why="the repository's worktrees folder cannot be read" others=1
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
# With no conflicts left it is rule 7: the same bogus commit, and the limits
# below would unstage the operation's own files. sequencer/ is the only sign of
# a range cherry-pick or revert paused between two picks.
note=""
stop() {
  echo "Not auto-committing in $repo on branch $branch: $1. Nothing committed; staged paths stay staged, unless the hook unstaged a new one that breaks its rules.$note"
  exit 0
}
in_progress() {  # names the first sign of an operation in progress
  local f
  for f in MERGE_HEAD SQUASH_MSG CHERRY_PICK_HEAD REVERT_HEAD BISECT_LOG sequencer rebase-merge rebase-apply; do
    if [ -e "$git_dir/$f" ]; then echo "$f"; return 0; fi
  done
  return 1
}
stop_if_started() {
  if op=$(in_progress); then stop "an operation started while the hook ran (found $op)"; fi
}
if op=$(in_progress); then
  echo "Not auto-committing in $repo on branch $branch: a merge, rebase, cherry-pick, revert or bisect is in progress (found $op); finish it first."
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
nuls() { tr -cd '\0' < "$1" | wc -c | tr -d ' '; }   # entries in a NUL list
lines() { wc -l < "$1" | tr -d ' '; }
first_names() {   # the first $EXAMPLES entries of a NUL list, on one line
  n=0 list=""
  while [ "$n" -lt "$EXAMPLES" ] && IFS= read -r -d '' p; do
    list="$list${list:+, }$(clean "$p")"; n=$((n + 1))
  done < "$1"
  printf '%s' "$list"
}
split_flagged() {   # <NUL list> <flags, one per line>: 1s go to <yes>, others to <no>
  while IFS= read -r -d '' p <&3 && IFS= read -r f <&4; do
    if [ "$f" = 1 ]; then printf '%s\0' "$p" >&5; else printf '%s\0' "$p" >&6; fi
  done 3< "$1" 4< "$2" 5> "$3" 6> "$4"
}
split_rec() { reason=${1%%"$tab"*}; rest=${1#*"$tab"}; size=${rest%%"$tab"*}; path=${rest#*"$tab"}; }
secret_re=$(IFS='|'; printf '%s' "${SECRET_NAMES[*]}")
names_grep() { LC_ALL=C grep -z -i -E "$@"; [ $? -le 1 ]; }   # no match is not a failure
split_secrets() {   # <NUL list> <secret-looking names> <the rest>
  names_grep "$secret_re" "$1" > "$tmp/hits" &&
    names_grep -v "$secret_re" "$1" > "$3" &&
    names_grep "$NOT_SECRET" "$tmp/hits" >> "$3" &&
    names_grep -v "$NOT_SECRET" "$tmp/hits" > "$2"
}

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
# Whole records, read in order and written by index: on bash 3.2, reading a[i]
# or appending with += walks the array, which took minutes on 100,000 skipped
# files.
skip_rec=() n_skip=0   # "reason<tab>bytes<tab>path"
unsized=0
add_skip() { skip_rec[n_skip]="$1$tab$2$tab$3"; n_skip=$((n_skip + 1)); }
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
    while IFS= read -r rec; do skip_rec[n_skip]=$rec; n_skip=$((n_skip + 1)); done < "$skips"
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

# --- Rule 6, scan side: secret-looking names never reach the staging below,
# so they are never hashed into the object store ---
if [ -n "$tmp" ]; then : > "$tmp/secret"; fi
if [ "$stage_new" -eq 1 ]; then
  if split_secrets "$keep" "$tmp/secret" "$tmp/kept" && mv "$tmp/kept" "$keep"; then :; else stage_new=0; fi
fi

# --- Stage tracked changes (as before) ---
stop_if_started  # git add -u would mark an operation's conflicts resolved
add_err=$(git add -u --ignore-errors 2>&1 >/dev/null)
if fatal=$(first_line "$add_err" '^fatal:'); then
  echo "Auto-commit FAILED in $repo on branch $branch: $(clean "$fatal") — nothing committed."
  exit 0
fi
unreadable_tracked=$(printf '%s\n' "$add_err" | grep -c 'unable to index file')

# --- Rules 5 and 6 on the index: the scan never sees new paths that someone
# staged before the hook ran. This runs here, so a sum over the limit stops the
# scanned files before they are hashed, and again on what is staged at the end.
# If a check cannot run, nothing is committed. ---
if [ -z "$tmp" ]; then
  if ! git diff --cached --quiet --diff-filter=A 2>/dev/null; then
    echo "Not auto-committing in $repo on branch $branch: new paths are staged and the hook has no temporary folder to check them with. Nothing committed; staged changes stay staged."
    exit 0
  fi
fi
unstage() { git update-index --force-remove -z --stdin < "$1" 2>/dev/null || stop "could not unstage held-back paths"; }
over=0 over_ex=""
n_added=0   # new paths in the index that are not exact renames of a deletion
check_index() {
  git diff --cached --no-renames --diff-filter=A --name-only -z > "$tmp/added" 2>/dev/null || stop "could not list staged new paths"
  split_secrets "$tmp/added" "$tmp/staged_secret" "$tmp/unused" || stop "could not check the names of staged new paths"
  if [ -s "$tmp/staged_secret" ]; then
    unstage "$tmp/staged_secret"
    cat "$tmp/staged_secret" >> "$tmp/secret"
  fi
  git diff --cached --find-renames=100% --diff-filter=A --name-only -z > "$tmp/added" 2>/dev/null || stop "could not list staged new paths"
  n_added=$(nuls "$tmp/added")
  case "$n_added" in '' | *[!0-9]*) stop "could not count staged new paths" ;; esac
  if [ "$n_added" -gt 0 ] && { [ "$over" -gt 0 ] || [ "$n_added" -gt "$MAX_NEW_FILES" ]; }; then
    unstage "$tmp/added"
    over=$((over + n_added))
    [ -n "$over_ex" ] || over_ex=$(first_names "$tmp/added")
    n_added=0
  fi
}
[ -n "$tmp" ] && check_index

# Split a NUL list into $tmp/moved, in the list's order (the content is a blob
# this commit deletes: a rename that git has not seen yet), and $tmp/rest.
# Sizes come first, so only size matches get hashed, and each deleted blob pairs
# with one path. A file that vanishes or cannot be read breaks the pairing of
# names with results; then nothing counts as moved. A moved symlink does not
# match, because hash-object follows it.
find_moved() {
  : > "$tmp/moved"; cp "$1" "$tmp/rest"
  xargs -0 stat -f '%z' -- < "$1" > "$tmp/sizes" 2>/dev/null
  [ "$(lines "$tmp/sizes")" -eq "$(nuls "$1")" ] || return 0
  awk 'NR == FNR { deleted[$1]; next } { print ($1 in deleted) ? 1 : 0 }' "$tmp/delblobs" "$tmp/sizes" > "$tmp/flags"
  split_flagged "$1" "$tmp/flags" "$tmp/same_size" "$tmp/other_size"
  [ -s "$tmp/same_size" ] || return 0
  xargs -0 git hash-object -- < "$tmp/same_size" > "$tmp/shas" 2>/dev/null
  [ "$(lines "$tmp/shas")" -eq "$(nuls "$tmp/same_size")" ] || return 0
  awk 'NR == FNR { left[$2]++; next } { print (left[$1]-- > 0) ? 1 : 0 }' "$tmp/delblobs" "$tmp/shas" > "$tmp/flags"
  split_flagged "$tmp/same_size" "$tmp/flags" "$tmp/moved" "$tmp/fresh_names"
  cat "$tmp/other_size" "$tmp/fresh_names" > "$tmp/rest"
}

# --- Rename exemption: a skipped file whose content is an index entry that was
# just staged as deleted (the user renamed/moved it) is kept, so the commit
# records a rename instead of a deletion. Only runs when there is something to
# exempt; only hashes files whose size matches a deleted blob. Rule 5 runs here
# too, because a directory rename must not count as new files.
renamed=0 renamed_ex=""
n_keep=0
[ "$stage_new" -eq 1 ] && n_keep=$(nuls "$keep")
n_new=$((over + n_added + n_keep))
if [ "$stage_new" -eq 1 ] && { [ "${#skip_rec[@]}" -gt 0 ] || [ "$n_new" -gt "$MAX_NEW_FILES" ]; }; then
  # A symlink's blob holds its target path; a regular file with those bytes is no rename of it.
  git diff --cached --find-renames=100% --diff-filter=D --raw --no-abbrev 2>/dev/null | awk '$1 != ":120000" { print $3 }' |
    git cat-file --batch-check='%(objectsize) %(objectname)' > "$tmp/delblobs" 2>/dev/null
  if [ "$n_new" -gt "$MAX_NEW_FILES" ]; then
    : > "$tmp/moved"; cp "$keep" "$tmp/rest"
    [ -s "$tmp/delblobs" ] && [ -s "$keep" ] && find_moved "$keep"
    n_moved=$(nuls "$tmp/moved")
    if [ "$((n_new - n_moved))" -gt "$MAX_NEW_FILES" ]; then
      over=$((over + n_keep - n_moved))
      [ -n "$over_ex" ] || over_ex=$(first_names "$tmp/rest")
      cp "$tmp/moved" "$keep"
      renamed=$n_moved
      renamed_ex=$(first_names "$tmp/moved")
    fi
  fi
  if [ -s "$tmp/delblobs" ] && [ "${#skip_rec[@]}" -gt 0 ]; then
    for rec in "${skip_rec[@]}"; do
      split_rec "$rec"
      [ "$reason" = nested ] || printf '%s\0' "$path"
    done > "$tmp/skipped"
    : > "$tmp/moved"
    [ -s "$tmp/skipped" ] && find_moved "$tmp/skipped"
    if [ -s "$tmp/moved" ] && split_secrets "$tmp/moved" "$tmp/moved_secret" "$tmp/unused"; then
      # Both lists keep skip_rec's order, so one walk finds each entry.
      exec 3< "$tmp/moved" 4< "$tmp/moved_secret"
      m="" s=""
      IFS= read -r -d '' m <&3
      IFS= read -r -d '' s <&4
      left=() n_left=0
      for rec in "${skip_rec[@]}"; do
        split_rec "$rec"
        if [ "$reason" != nested ] && [ "$path" = "$m" ]; then
          IFS= read -r -d '' m <&3 || m=""
          if [ "$path" = "$s" ]; then
            IFS= read -r -d '' s <&4 || s=""
          else
            printf '%s\0' "$path" >> "$keep"
            renamed=$((renamed + 1))
            [ "$renamed" -le "$EXAMPLES" ] && renamed_ex="$renamed_ex${renamed_ex:+, }$(clean "$path")"
            continue
          fi
        fi
        left[n_left]=$rec; n_left=$((n_left + 1))
      done
      exec 3<&- 4<&-
      skip_rec=("${left[@]}")
    fi
  fi
fi

# --- Stage the approved new files ---
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
  new_note=" New files were NOT staged: the scan could not run (needs a writable TMPDIR, BSD stat, grep -z, and a stable file list)."
fi

# --- Blob-size check on what is actually staged: unstage any NEW blob over the
# limit (it grew after the scan, or was staged earlier in the session), and
# warn about MODIFIED tracked blobs over it (those stay committed, rule 4). An
# exact rename is neither; a rename with new content counts as a new blob.
grown=0 grown_ex="" big_tracked=0 big_tracked_ex=""
check_sizes() {
  big_tracked=0 big_tracked_ex=""
  # Each step goes through a file, so a failure anywhere stops the commit: a
  # pipeline reports only its last stage, and < <(...) reports nothing.
  git diff --cached --find-renames=100% --diff-filter=AM --raw --no-abbrev > "$tmp/staged_raw" 2>/dev/null &&
    awk '{ print $4 }' "$tmp/staged_raw" > "$tmp/staged_shas" &&
    git cat-file --batch-check='%(objectsize) %(objectname)' < "$tmp/staged_shas" > "$tmp/staged_blobs" 2>/dev/null &&
    awk -v max="$MAX_NEW_FILE_BYTES" '$1 + 0 > max + 0 { print $2 }' "$tmp/staged_blobs" > "$tmp/bigshas" ||
    stop "could not size staged blobs"
  [ -s "$tmp/bigshas" ] || return 0
  git diff --cached --find-renames=100% --diff-filter=AM --raw --no-abbrev -z > "$tmp/staged_raw_z" 2>/dev/null ||
    stop "could not size staged blobs"
  bigset=$'\n'$(< "$tmp/bigshas")$'\n'
  while IFS= read -r -d '' meta && IFS= read -r -d '' path; do
    rest=${meta#* * * }; sha=${rest%% *}; status=${rest#* }
    case $bigset in *$'\n'"$sha"$'\n'*) ;; *) continue ;; esac
    if [ "$status" = A ]; then
      # -f: without it git refuses a file that changed again since it was staged.
      git --literal-pathspecs rm --cached -q -f -- "$path" >/dev/null 2>&1 ||
        stop "could not unstage a new file over $(human "$MAX_NEW_FILE_BYTES")"
      grown=$((grown + 1))
      [ "$grown" -le "$EXAMPLES" ] && grown_ex="$grown_ex${grown_ex:+, }$(clean "$path")"
    else
      big_tracked=$((big_tracked + 1))
      [ "$big_tracked" -le "$EXAMPLES" ] && big_tracked_ex="$big_tracked_ex${big_tracked_ex:+, }$(clean "$path")"
    fi
  done < "$tmp/staged_raw_z"
}

# The real index gets these fixes, so the output stays true of it. Then the
# commit comes from a private copy, checked after the copy: another session can
# change the real index until the commit ends, and anything it stages stays
# staged there. Nothing needs merging back, because the real index already
# holds what the commit holds.
if [ -n "$tmp" ]; then
  check_index
  check_sizes
  index=$(git rev-parse --git-path index 2>/dev/null) || stop "could not copy the index"
  # An unborn branch has no index file before the first add.
  if [ -e "$index" ] || [ -n "$head_sha" ]; then
    cp "$index" "$tmp/index" 2>/dev/null || stop "could not copy the index"
  fi
  export GIT_INDEX_FILE=$tmp/index
  check_index
  check_sizes
fi

n_changed=$(git diff --cached --name-only -z 2>/dev/null | tr -cd '\0' | wc -c | tr -d ' ')

# --- Summary line ---
skipped=0 skipped_bytes=0 skipped_big=0 skipped_log=0 nested=0 skip_ex="" nested_ex=""
for rec in "${skip_rec[@]}"; do
  split_rec "$rec"
  case "$reason" in
    big | log)
      skipped=$((skipped + 1)); skipped_bytes=$((skipped_bytes + size))
      if [ "$reason" = big ]; then skipped_big=$((skipped_big + 1)); else skipped_log=$((skipped_log + 1)); fi
      [ "$skipped" -le "$EXAMPLES" ] && skip_ex="$skip_ex${skip_ex:+, }$(clean "$path")" ;;
    nested)
      nested=$((nested + 1))
      [ "$nested" -le "$EXAMPLES" ] && nested_ex="$nested_ex${nested_ex:+, }$(clean "$path")" ;;
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
if [ -n "$tmp" ] && [ -s "$tmp/secret" ]; then
  n_secret=$(nuls "$tmp/secret")
  note="$note Left out $n_secret new file(s) with secret-looking names: $(first_names "$tmp/secret")$(more "$n_secret") — left on disk, not committed."
fi
[ "$over" -gt 0 ] && note="$note Left out $over new file(s), over the limit of $MAX_NEW_FILES for one auto-commit, because they may be other sessions' work: $over_ex$(more "$over") — left on disk, not committed. Commit your own by path (git add -- <paths>; git commit)."
[ "$nested" -gt 0 ] && note="$note Not added: $nested nested git repo(s): $nested_ex$(more "$nested")."
[ "$renamed" -gt 0 ] && note="$note Kept $renamed renamed tracked file(s) whose content was already in the repo: $renamed_ex$(more "$renamed")."
[ "$grown" -gt 0 ] && note="$note Unstaged $grown new file(s) over $(human "$MAX_NEW_FILE_BYTES") by staging time: $grown_ex$(more "$grown")."
[ "$big_tracked" -gt 0 ] && note="$note WARNING: $big_tracked tracked file(s) over $(human "$MAX_NEW_FILE_BYTES") modified: $big_tracked_ex$(more "$big_tracked") — GitHub rejects pushes with blobs over 100 MB."
[ "$unreadable_tracked" -gt 0 ] && note="$note $unreadable_tracked tracked file(s) could not be read and were not committed."
[ "$unsized" -gt 0 ] && note="$note $unsized untracked file(s) could not be sized (vanished or unreadable) and were not staged."
note="$note$new_note"

if [ "$n_changed" -eq 0 ]; then
  echo "Nothing to auto-commit in $repo on branch $branch before context compact.$note"
  exit 0
fi

# The branch must be the one the rules above were judged on.
if [ "$(git symbolic-ref -q HEAD 2>/dev/null)" != "$head_ref" ] ||
   [ "$(git rev-parse -q --verify HEAD 2>/dev/null)" != "$head_sha" ]; then
  stop "HEAD moved while the hook ran"
fi
stop_if_started

# Auto-commit the index as staged above, on the branch and parent the rules were
# judged on. The tree comes from the private copy, so on any other parent it
# would reverse what differs there. HEAD resolves wherever a session has just
# taken it, the default branch included, so the update names the judged ref, and
# that ref moves only if it still holds that parent: another commit there fails
# this save, not its own work. A detached HEAD has no ref to name. A fixup!
# subject squashes via rebase --autosquash; an unborn branch has no parent.
# commit-tree would write an empty commit, which git commit refused to, so the
# tree must differ from its parent's, or from the empty tree on an unborn branch.
if [ -n "$head_sha" ]; then
  msg="fixup! $(git log -1 --no-show-signature --format=%s "$head_sha" 2>/dev/null)"
else
  msg="WIP: auto-save before context compact ($n_changed files on $branch)"
fi
if tree=$(git write-tree 2>/dev/null) &&
   [ "$tree" = "$(git rev-parse -q --verify "${head_sha:-$(git hash-object -t tree /dev/null 2>/dev/null)}^{tree}" 2>/dev/null)" ]; then
  echo "Nothing to auto-commit in $repo on branch $branch before context compact.$note"
elif [ -n "$tree" ] &&
   new=$(git commit-tree "$tree" ${head_sha:+-p "$head_sha"} -m "$msg" 2>/dev/null) &&
   git update-ref -m "commit: $msg" "${head_ref:-HEAD}" "$new" "$head_sha" 2>/dev/null; then
  echo "Auto-committed $n_changed file(s) in $repo on branch $branch before context compact.$note"
else
  echo "Auto-commit FAILED in $repo on branch $branch; changes left staged, not committed.$note"
fi
exit 0
