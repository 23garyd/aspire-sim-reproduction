# Reproduction and Archive Notes

Prepared on 2026-11-14. This directory supports December technical delivery preparation; it does not claim December acceptance or completion of all final work.

Checked-out source commit: `ccb4a32e2e30e696971f6ee3c3214695d21f10d0`. [archive-manifest.csv](archive-manifest.csv) gives pinned GitHub links, byte counts and SHA-256 for code and existing artifacts. The archive covers all tracked files at that source commit, excluding this newly added dec-m5 directory. [manifest.csv](manifest.csv) records its integrity separately to avoid circular hashes.

```bash
git clone https://github.com/23garyd/aspire-sim-reproduction.git
cd aspire-sim-reproduction
git checkout ccb4a32e2e30e696971f6ee3c3214695d21f10d0
```

Archive CSV paths are relative to the repository root. Verify each SHA-256 after download or checkout; evidence-directory Git attributes preserve file bytes. The repository remains private and uses existing access authorization.

[Test commands and original output from the existing environment](../nov-m4/verification/2026-11-14-tests.txt) establish only that the specified no-hardware subset can run. Prepare complete software dependencies, GPU, vendor SDK, models and raw data separately using the [project overview](../../../README.md) and the original environment lock files.

The completed work checks out code from the existing private source and verifies artifacts and a software subset. A full clean-machine system rebuild and independent third-party startup of real trials have not been completed. Do not run physical robot entry points on unmeasured or uncalibrated hardware; the current software checks do not require powering the arm.

[aspire.run](../../../aspire/run.py) is the model execution entry point and was not run here. The selected runner dry-run check requires Linux /proc, which macOS does not provide. The Git archive does not replace cap-x, model services or external campaign data.
