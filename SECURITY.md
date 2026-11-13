# Security

## Reporting a problem

Please report security problems **privately**, not as a public issue:
**[Report a vulnerability](https://github.com/syedtaj7/TapShift/security/advisories/new)** (GitHub's private reporting).

Include what an attacker could do, the Deskvert version, and the steps or a sample file that shows it. You'll get a
reply as soon as possible, and a fix is released as a normal update (Deskvert tells people about updates by itself).

## What Deskvert is careful about

- **Your files are only read.** Every result is made in a private work folder, opened again and checked, then moved
  next to the original. Originals are never edited, moved or deleted.
- **No code from your files runs.** Office documents open read-only with macros disabled; e-mails, web pages and
  notebooks are read as data (scripts never run).
- **Untrusted input is bounded.** Archives are checked for paths that escape their folder; downloads have size limits.
- **Updates are checked.** An update is downloaded from this repository's GitHub releases and must match the
  SHA-256 checksum GitHub publishes for it before it's installed.
- **Low impact.** Conversions run in a Windows job object with a processor limit you choose.

## Supported versions

Only the latest release gets fixes. Deskvert updates itself, so staying current is one click.
