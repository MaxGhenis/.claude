# Iterative review-fix cycle for academic papers

Run referee reviews, fix critical issues, re-run until no critical issues remain, then fix minor issues one last time.

## Arguments
- $ARGUMENTS: Path to the paper directory (e.g., ~/dpa-tax/docs/)

## Workflow

### Phase 1: Review-fix loop (critical issues)

Repeat the following until referees report no critical issues:

1. **Run all referee reviews** using the `academic-referee:run-review` skill on `$ARGUMENTS`
2. **Compile the editorial summary** identifying critical vs minor issues
3. **If critical issues exist**:
   - Fix ALL critical issues in the paper files (misattributions, bugs, missing content, advocacy language, etc.)
   - Commit fixes with a descriptive message
   - Return to step 1
4. **If no critical issues**: proceed to Phase 2

### Phase 2: Final minor fixes

1. Collect all minor issues from the most recent review
2. Fix them all in one pass
3. Commit with message summarizing minor fixes
4. Run one final review to confirm clean

### Guidelines

- Fix issues directly in the source files - don't just plan fixes
- For reference issues: verify via web search before correcting
- For code bugs: fix and run tests to confirm
- For framing/language issues: make targeted edits preserving the author's voice
- For missing content: add concise paragraphs, don't over-expand
- After each fix round, run any available tests to ensure nothing breaks
- Report progress after each cycle: "Cycle N: fixed X critical issues, Y remain"
