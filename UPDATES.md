# Beta release and update contract

The application reads the public GitHub releases list, including pre-releases
while RELEASE_CHANNEL is `beta`. Draft releases and non-numeric tags are skipped.
Use numeric `vX.Y.Z` tags and mark each test release as **pre-release** on GitHub.
Do not use a stable/latest release for beta distribution.

Each release contains a `checksums.json` mapping its exact asset names to SHA-256:

- `GasketFit-X.Y.Z-Windows-x64.zip` (portable)
- `GasketFit-X.Y.Z-Windows-x64-Setup.exe` (installed Windows)
- `GasketFit-X.Y.Z-Linux-x64.zip` (when tested)
- Native macOS packages only after their native validation.

Stage releases as drafts, upload all packages and the manifest, verify the assets,
then publish with `prerelease=true`. No credentials belong in the app or repository.

Automatic checks do not auto-install. Windows downloads require HTTPS, a valid
checksum and confirmation. Portable ZIP members are validated against traversal,
duplicate paths, symlinks and excessive extracted size. The previous portable
folder is kept for recovery. Installed copies run the verified Setup instead of
replacing their installation folder; settings remain in the user's data folder.
Linux/macOS display the newer version and open the public release page.

Checksums protect consistency with the GitHub release, not against compromise of
the publishing account. Code signing is a separate future distribution step.
