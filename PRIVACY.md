# Privacy

**Deskvert has no account, no analytics and no telemetry.** Your files are converted on your PC and never uploaded.

## When Deskvert goes online

Only for these, and only when they happen:

| What | Goes to | Sends |
|---|---|---|
| **Update check** (every few hours; turn it off in Settings → General) | `api.github.com` | Asks for the latest version number. Nothing about you or your files. |
| **Installing an update** (when you click Update) | `github.com` | Downloads the new installer. |
| **Dragging a picture, link or shared file out of a web page** | The website it came from | Fetches that one picture or file (only when the browser doesn't hand it over itself). |
| **Saving a page** (tap Ctrl + Shift on a browser: page as PDF or picture, article, all pictures) | The website of that page | The Edge or Chrome already on your PC opens it in a private, empty profile: no cookies, no sign-ins, no history of yours. |

**Report a problem** sends nothing by itself: it opens a filled-in GitHub issue in your browser (with your name and
folders hidden), and you decide whether to post it.

## What stays on your PC

- **Settings:** `%APPDATA%\Deskvert`. **Logs:** `%LOCALAPPDATA%\Deskvert\logs` (they name the files you convert;
  they never leave your PC unless you share them).
- **Things you drop or tap in a browser** are saved in `Downloads\Deskvert`.
- **Reading a browser selection:** Deskvert copies the selection (as you would with Ctrl + C), reads it, and puts
  your clipboard back exactly as it was.
- **Uninstalling** removes the app, its settings and its logs.
