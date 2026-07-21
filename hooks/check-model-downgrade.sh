#!/bin/bash
# check-model-downgrade.sh — Fable→Opus fallback watchdog (UserPromptSubmit + PostToolUse).
#
# Fable 5 runs safety classifiers (cyber, bio, reasoning_extraction); a flagged
# request is silently served by Opus 4.8, sticky ~1hr, while the env block still
# claims Fable. Ground truth is the transcript's per-message model field
# (see ~/dotfiles/bin/claude-model). When a downgrade is detected this hook
# injects Max's standing order into model context: delegate substantive work
# cross-family to sol (classifier-immune); Max-voice writing → verified fable
# subagent; tell Max. Fires every user prompt; PostToolUse throttled to 180s.
# Silent for deliberate non-Fable sessions (warns only on claude-opus-* serves
# in sessions that also show Fable turns or a refusal event). Always exits 0.
set -u

INPUT=$(cat 2>/dev/null || true)
TP=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
EV=$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || true)
SID=$(printf '%s' "$INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null || true)
[ -n "$TP" ] && [ -f "$TP" ] || exit 0
[ -n "$EV" ] || EV="UserPromptSubmit"

# Throttle PostToolUse probes; the state file's mtime doubles as a liveness sentinel.
STATE_DIR="$HOME/.cache/claude-model-hook"
mkdir -p "$STATE_DIR" 2>/dev/null || exit 0
STATE="$STATE_DIR/${SID}.last"
if [ "$EV" = "PostToolUse" ] && [ -f "$STATE" ]; then
  NOW=$(date +%s)
  LAST=$(stat -f %m "$STATE" 2>/dev/null || echo 0)
  [ $((NOW - LAST)) -lt 180 ] && exit 0
fi
touch "$STATE" 2>/dev/null || true
# GC stale per-session sentinels so the state dir doesn't grow unbounded.
find "$STATE_DIR" -name '*.last' -mtime +7 -delete 2>/dev/null || true

# Latest served model, from a bounded tail (transcripts reach tens of MB).
# tail -n +2 drops a possibly-truncated first fragment; fromjson? drops bad lines.
recent_models() {
  tail -c 400000 "$TP" 2>/dev/null | tail -n +2 | \
    jq -Rr 'fromjson? | select(.type=="assistant") | .message.model // empty' 2>/dev/null | \
    grep -v '^$' | grep -v '^<' || true
}
LATEST=$(recent_models | tail -1)
case "$LATEST" in
  claude-opus*) ;;
  *) exit 0 ;;
esac

# Downgrade signature: this session also has Fable turns, or a classifier refusal.
# Neither present -> deliberate Opus session; stay silent.
if ! grep -q '"model":"claude-fable' "$TP" 2>/dev/null && \
   ! grep -q '"stop_reason":"refusal"' "$TP" 2>/dev/null; then
  exit 0
fi

OPUS_RECENT=$(recent_models | grep -c '^claude-opus' || true)
REFUSALS=$(grep -c '"stop_reason":"refusal"' "$TP" 2>/dev/null || true)
[ -n "$REFUSALS" ] || REFUSALS=0

CTX="MODEL DOWNGRADE DETECTED: the latest assistant turn was served by ${LATEST}, not Fable (safety-classifier fallback: cyber/bio/reasoning_extraction; sticky ~1hr; ${OPUS_RECENT} Opus turns in the recent tail, ${REFUSALS} refusal events this session — the environment block still claims Fable and is wrong). Max's standing order while downgraded: (1) delegate substantive analysis/review/implementation CROSS-FAMILY to sol via codex-run (gpt-5.6-sol has no Anthropic classifier, immune); (2) Max-voice writing or fable-critical judgment -> model:\"fable\" subagent with defensive audit framing, then verify its transcript with claude-model; (3) tell Max a downgrade occurred; (4) once back on Fable, re-review main-loop judgment made while on Opus. Ref: feedback_stop_if_downgraded_to_opus memory."

jq -cn --arg ev "$EV" --arg ctx "$CTX" \
  '{hookSpecificOutput: {hookEventName: $ev, additionalContext: $ctx}}' 2>/dev/null || true
exit 0
