# Release publication

The **Release** workflow publishes verified Windows and Linux binaries to
[GitHub Releases](https://github.com/brouns-tech/box3-werkelijk-rendement/releases)
when a version tag is pushed. No personal access token is required: only its
publication job receives `contents: write` through GitHub's built-in token.

## Publish a version

1. Set `[project].version` in `pyproject.toml` and add English notes at
   `docs/releases/<version>.md`. Keep platform build dependencies locked.
2. Merge the release-ready changes into `main` and wait for the checks to pass.
3. Create and push an annotated tag matching the package version exactly:

   ```sh
   git switch main
   git pull --ff-only
   git tag -a v0.1.0 -m "Werkelijk Rendement 0.1.0"
   git push origin v0.1.0
   ```

Use the next version for subsequent releases; published versions are not replaced.
Accepted versions are `X.Y.Z`, optionally followed by Python's `aN`, `bN`, `rcN`,
or `.devN` prerelease suffix, for example `0.2.0b1` with tag `v0.2.0b1`.
All `0.x` versions and explicitly suffixed versions are marked as GitHub prereleases.
Stable versions from `1.0.0` are published as regular releases and marked latest.

## What runs automatically

1. Validate the tag against `pyproject.toml` and require version-specific notes.
2. Call the existing Windows and Linux workflows for the same commit. They run
   regressions and verify frozen import/export, launch, reuse, and shutdown;
   Linux also verifies the final AppImage and portable archive.
3. Gather both platforms' artifacts and validate all three binaries and their
   SHA-256 files, including exact filenames and nonempty payloads.
4. Create a draft, upload the complete validated set, then publish it. A failed
   build or checksum check blocks publication. An interrupted upload leaves a
   draft that can be completed by rerunning the workflow.

Downloads are the Windows ZIP, Linux AppImage, Linux `.tar.gz`, their three
checksum files, and `RELEASE-NOTES.md`. The `release-assets` Actions artifact also
contains the complete validated payload for inspection.

## Dry runs and retries

Once the workflow is on the repository's default branch, choose **Actions →
Release → Run workflow**. Select a branch or tag and leave **publish** unchecked
for a dry run. It runs both builds and prepares downloads without creating a release.

To retry publication, rerun a failed tag-push workflow, or select the existing
version tag in the manual workflow and check **publish**. Selecting a branch
with **publish** checked fails validation. Retrying a draft replaces its assets
with the verified set; an already published release is left unchanged.

Pushing a tag is the publication trigger; ordinary commits, pull requests,
individual platform builds, and documentation builds do not publish releases.
A tag pushed by another workflow using its ordinary `GITHUB_TOKEN` does not
trigger this workflow: push it yourself or dispatch Release explicitly. See
[GitHub's workflow event rules](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow).

This publishes GitHub downloads; website download integration, installer signing,
and clean-machine usability review remain separate work.
