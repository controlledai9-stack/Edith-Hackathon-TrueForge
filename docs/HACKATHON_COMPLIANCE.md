# TrueForge Hackathon compliance checklist

This document tracks evidence; it does not claim completion where an external link or participant action is still required.

| Rule | Requirement | Current evidence/status |
| --- | --- | --- |
| 1 | Online or San Francisco participation; free entry | Participant/submission-platform item. No code action required. |
| 2 | Solo or team of up to four; one team per participant | Participant must confirm team membership in the submission form. |
| 3 | Agent runs on TrueForge and judges can see real harness work | Implemented: `app/integrations/trueforge/`, `app/services/trueforge_service.py`, MCP bridge, session persistence, streamed activity, approvals, cancellation, and `docs/TRUEFORGE.md`. Demo must show the TrueForge Activity events. |
| 4 | Every substantive change is reviewed by Qodo in a GitHub PR before merge | **Blocking:** this copied folder currently has no Git/PR/Qodo history. Create a public repository and use the workflow in `CONTRIBUTING.md`; do not merge until initial and follow-up Qodo reviews are visible. |
| 5 | Open-ended project | Satisfied by E.D.I.T.H.'s multi-mode agent workspace. |
| 6 | Public source and runnable code | Source and setup docs are prepared locally. **Blocking:** publish the repository publicly before submission. |
| 7 | Authorized tools/data; no private/login-protected information in repo/demo | `.gitignore` excludes all runtime data, tokens, browser profiles, databases, uploads, and artifacts. Use only synthetic/public demo data and dedicated demo accounts. Run the secret scan before every push. |
| 8 | Original coding/design occurs within the hackathon window | Participant must retain truthful commit/PR timestamps and be able to explain that implementation occurred during the event. Do not fabricate or rewrite evidence. |
| 9 | Frameworks/libraries/public assets allowed | Dependencies are documented; original integration and product work are the judged contribution. |
| 10 | Repo, README, video, write-up, TrueForge explanation, Qodo evidence, optional blog | README/setup/write-up prepared. **Blocking:** repository URL, demo video URL, and real Qodo PR/review links remain TODO. |
| 11 | Deadline: August 30, 8:00 PM London | Treat the submission-platform clock as authoritative and submit before it closes. |
| 12 | AI assistants allowed but must be disclosed | Disclosed in README and PR template. |
| 13 | Participant understands code and decisions | Use `docs/TRUEFORGE.md` and `docs/DEMO_SCRIPT.md` to prepare; participant must personally explain the system. |
| 14 | Meaningful participant contribution and verification required | Preserve the participant's requirements, manual test evidence, Qodo decisions, and test results; do not describe the project as autonomous AI output. |
| 15 | Three judged tracks; one prize maximum | Submission-platform item. Demo highlights visible harness use, reviewed code quality, and UI. |

## Required external actions before submission

1. Create the public GitHub repository.
2. Establish `main`, create a feature branch containing the hackathon code, and open a representative pull request.
3. Enable/install Qodo for the repository and wait for its initial review.
4. Resolve or explicitly dismiss findings, push the final fixes, and obtain the follow-up review.
5. Merge through the pull request; do not directly push substantive changes to `main`.
6. Replace every `TODO` in the README with real public links and an accurate Qodo summary.
7. Record and upload the approximately three-minute demo using only synthetic/public data.
8. Run tests and a secret scan against the exact final commit.
9. Submit before the platform deadline.

## Suggested pre-push secret scan

Use a recognized scanner such as Gitleaks against the staged repository, then manually inspect the staged file list. Never paste secrets into issue, PR, or review comments.
