# Proton Browser 5.1.0

ProtoOS KDE Edition includes the Linux `amd64` package for **Proton Browser** at the explicit request of its author/repository owner.

| Field | Value |
| --- | --- |
| Upstream release | [`UsmanMusav/Proton-updates` `v5.1.0`](https://github.com/UsmanMusav/Proton-updates/releases/tag/v5.1.0) |
| Asset | `iskatel-linux-amd64.deb` |
| Asset URL | `https://github.com/UsmanMusav/Proton-updates/releases/download/v5.1.0/iskatel-linux-amd64.deb` |
| Architecture | `amd64` |
| GitHub asset SHA-256 | `e7a9c505ec626df0f991450beef7acf8ce6fc3f27f66a01220e9fb1bf0d4fb81` |
| Source availability | Closed source; the upstream repository states that it publishes installers only. |

## Build treatment

The VHD builder downloads only the exact URL above using HTTPS, verifies the pinned SHA-256 before installation, checks that the Debian package declares `amd64`, and requires the installed `iskatel` command to exist. The `.deb` is not committed to the ProtoOS repository.

ProtoOS does not claim ownership of Proton Browser or relicense it. Its upstream license and terms apply. The packaged application is surfaced as **Proton Browser** / **Браузер Proton** with an original ProtoOS Aurora launcher icon.
