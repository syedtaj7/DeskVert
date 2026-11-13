# Code signing with SignPath (free for open source)

Deskvert's release workflow is ready for [SignPath Foundation](https://signpath.org)'s free code signing. Until it's
set up, releases are built exactly as before, unsigned. Once it's set up, every release tag produces a signed
`Deskvert.exe` (inside the installer and the portable zip) and a signed `Deskvert-Setup-<version>.exe`.

Check SignPath's current terms and steps on their site; this is how the pieces fit together.

## 1. Apply

Apply at [signpath.org](https://signpath.org) with the repository (https://github.com/syedtaj7/TapShift). What
SignPath Foundation asks of projects (from its terms):

- Open source under an OSI-approved license (AGPL-3.0: yes), no proprietary code, actively maintained and already
  released.
- Signed files are built from this repository by GitHub Actions (the release workflow does that).
- Multi-factor authentication on GitHub and SignPath for everyone involved.
- Every release is **approved by hand** in SignPath (you'll get two requests per release: the app, then the
  installer; the workflow waits up to an hour for each).
- Product name and version are set in the files and enforced (both files carry "Deskvert" and the version).
- A **Code signing policy** published on the project page (below).

## 2. Publish the code signing policy

Add this section to README.md (Claude can do it once you're approved):

```markdown
## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).

- Committers and reviewers: [syedtaj7](https://github.com/syedtaj7)
- Approvers: [syedtaj7](https://github.com/syedtaj7)

Only files built from this repository by its GitHub Actions release workflow are signed, and each release is
approved by hand. Privacy: see [PRIVACY.md](PRIVACY.md). Deskvert doesn't send any information to other networked
systems unless you ask it to (the exceptions, such as the update check, are listed there).
```

## 3. Set up the SignPath project

In SignPath (after approval):

1. Link the project to the GitHub repository (trusted build system: GitHub Actions).
2. Create two **artifact configurations** with these slugs, pasting the XML from this repository:
   - `app`: [packaging/signpath/app.xml](../packaging/signpath/app.xml)
   - `installer`: [packaging/signpath/installer.xml](../packaging/signpath/installer.xml)
3. Note the **organization ID**, the **project slug** and the **signing policy slug** (SignPath Foundation's
   release policy).
4. Create an **API token** for a CI user that may submit signing requests to that policy.

## 4. Add them to GitHub

Repository → **Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
|---|---|---|
| Secret | `SIGNPATH_API_TOKEN` | the API token |
| Variable | `SIGNPATH_ORGANIZATION_ID` | the organization ID |
| Variable | `SIGNPATH_PROJECT_SLUG` | the project slug |
| Variable | `SIGNPATH_POLICY_SLUG` | the signing policy slug |

The workflow signs as soon as `SIGNPATH_ORGANIZATION_ID` is set.

## 5. The first signed release

Tag a release as usual. In the workflow run, the "Sign Deskvert.exe" step waits for your approval in SignPath,
then packaging continues, then "Sign the installer" waits again. The workflow checks both signatures
(`Get-AuthenticodeSignature`) before publishing; if signing fails, nothing is published.

SmartScreen trust grows with downloads: the first signed releases may still show a (milder) warning for a while.
