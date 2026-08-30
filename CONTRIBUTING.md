# Contributing and review policy

This hackathon repository uses pull-request-only development.

1. Create a branch from the latest reviewed `main`.
2. Make one coherent, explainable change and add or update tests.
3. Run `python -m pytest -q` and record the result in the pull request.
4. Push the branch and open a GitHub pull request. Never push substantive code directly to `main`.
5. Wait for Qodo to complete its initial review.
6. Respond to every meaningful finding: implement a fix or document why it is intentionally dismissed.
7. Push the fixes and request or wait for Qodo's follow-up review against the final commit.
8. Merge only after the review trail and checks are complete.
9. Add the representative merged PR and Qodo evidence to `README.md` before submission.

Do not commit secrets, OAuth tokens, browser profiles, private documents, personal messages, generated user artifacts, or production data. Use synthetic data in tests and demonstrations.

AI coding assistants may be used, but contributors must disclose their use, understand the submitted code, verify the behavior, and be able to explain the architecture and decisions.
