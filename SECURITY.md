# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub: open the repository's
**Security** tab and choose **Report a vulnerability**. Do not open a public issue.

Include what you found, where (file and line or URL), and the steps to reproduce it.
Please test only against a local copy of the site (see the README), not against
ailens.live or the services it uses.

## Scope

In scope: the code in this repository and the site it publishes, including how news,
timeline and investment data are rendered, the GitHub Actions workflows, and the
Cloudflare Worker in `tools/cron-worker/`.

Out of scope: the content and security of third-party news sources, and the accuracy of
headlines published by other outlets (report factual errors in an ordinary issue).

How the site is protected is described in [md-doc/security.md](md-doc/security.md).
