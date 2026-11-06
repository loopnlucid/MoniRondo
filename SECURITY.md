# Security policy

## Supported versions

Only the latest release receives fixes.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Report them privately through GitHub's [private vulnerability reporting](https://github.com/loopnlucid/MoniRondo/security/advisories/new) instead.

Please include the MoniRondo version, your Windows version and steps to reproduce. You will receive an answer as soon as possible; once a fix is available, the advisory will be published together with the release.

## Scope

MoniRondo runs without administrator rights and without network access. It reads window positions, process image paths (for the exclusion list) and display configuration, stores its settings in the user profile and optionally writes one per-user autostart value. Relevant reports include, for example, ways to make MoniRondo execute code, write outside its own profile and autostart value, or leak information through its logs or local instance pipe.
