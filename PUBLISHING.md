# Publishing to TestPyPI

## One-time setup

1. Register at <https://test.pypi.org/account/register/> (separate account from PyPI).
2. Create an API token at <https://test.pypi.org/manage/account/token/>, scope "Entire account"
   for the first upload.
3. Export it:

```bash
export UV_PUBLISH_TOKEN=pypi-...
```

## Release

```bash
uv run pytest && uv run ruff check .
rm -rf dist/
uv build
uv run --with twine twine check dist/*
uv publish --publish-url https://test.pypi.org/legacy/
```

## Verify the published artefact

Install from TestPyPI in a throwaway environment. Dependencies come from real PyPI, since
TestPyPI does not mirror them:

```bash
uv run --isolated --no-project \
  --with redcap2hdcat \
  --index https://test.pypi.org/simple/ \
  --index-strategy unsafe-best-match \
  redcap2hdcat --version
```

## Notes

- **A version can never be re-uploaded**, on TestPyPI or PyPI. Bump `version` in
  `pyproject.toml` for every attempt. Use `0.1.0.dev1`, `0.1.0.dev2`, … while iterating, and
  keep `0.1.0` clean for the real release.
- The name `redcap2hdcat` is unclaimed on both indexes as of writing. Claiming it on TestPyPI
  does **not** reserve it on PyPI — do a `0.1.0.dev0` upload to PyPI early if the name matters.
- Once the tool is real, publish a container image too: the IMPaCT-Data software catalogue has a
  container image column. **Pin by digest, never `latest`** — pinning to `latest` is exactly the
  defect visible in that catalogue.
- Archive each release in Zenodo for a citable DOI. That is one of the four maturity signals
  that do not depend on having users.
