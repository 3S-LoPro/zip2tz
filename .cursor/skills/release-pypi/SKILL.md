---
name: release-pypi
description: Bump the package version, create a git tag, and push to GitHub to trigger the PyPI release workflow. Use when the user asks to bump the version, release, publish to PyPI, or create a new tag.
---

# Release to PyPI

This project uses a GitHub Action (`.github/workflows/publish.yml`) to automatically build and publish the package to PyPI whenever a new version tag (e.g., `v0.1.2`) is pushed to the repository.

## Release Workflow

Follow these exact steps to release a new version:

1. **Determine the new version**
   - Read `pyproject.toml` to find the current version.
   - If the user didn't specify a new version, increment the patch version (e.g., `0.1.2` -> `0.1.3`).

2. **Update the version file**
   - Modify the `version = "..."` line in `pyproject.toml` to the new version.
   - *Note: The version inside `pyproject.toml` should NOT have the `v` prefix (e.g., `1.0.0`).*

3. **Commit the changes**
   - Stage the changes: `git add pyproject.toml` (and any other modified files the user wants included).
   - Commit: `git commit -m "Bump version to <new_version>"`

4. **Tag and Push**
   - Create an annotated tag: `git tag -a v<new_version> -m "v<new_version>"`
   - Push the commit to main: `git push origin main`
   - Push the tag to trigger the workflow: `git push origin v<new_version>`

## Important Notes

- The git tag **MUST** start with `v` (e.g., `v1.0.0`) because the GitHub Action workflow is configured to trigger only on `tags: - "v*"`.
- Always push `main` before pushing the tag to ensure the remote branch is up to date with the commit that the tag points to.
