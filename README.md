# AC Brain Home Assistant distribution

This public repository contains only the distribution metadata and Home Assistant custom
integration for the privately maintained AC Brain controller. It intentionally contains no
controller source code, credentials, database data, or household configuration.

Home Assistant Supervisor installs the pre-built multi-architecture app image from
`ghcr.io/frantic777/climatecontroller`. HACS installs the `kotlin_ac.zip` integration asset from
the matching GitHub release. Both are published only after the private source repository's complete
test and security workflow succeeds.

Do not copy example defaults over an existing installation. Home Assistant retains the installed
app's saved options during a normal update, including the operator-selected HVAC mode, target,
fan, and rooms.

