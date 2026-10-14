# Documentation

The English documentation site uses [Zensical](https://zensical.org/docs/).
User-facing pages live under `docs/`; `zensical.toml` defines navigation and appearance.

## Structure

- `getting-started/`: platform installation and launch troubleshooting.
- `guide/`: document import, taxpayer review, calculations, and local data.
- `reference/`: exact compatibility and limitations.
- `development/`: contributions, CLI, extraction decisions, and build procedures.
- `releases/`: release notes and distribution status.
- `assets/`: screenshots made with synthetic data.

Keep the README concise and link into these guides. Use relative Markdown links
so pages remain readable both in GitHub and in the generated site. Document app
labels in English and add Dutch equivalents only when helpful.

## Preview and build

Documentation requires Python 3.11 or newer and does not add dependencies to the
application or its packaging lock. From the repository root:

```sh
python -m venv .venv-docs
.venv-docs/bin/python -m pip install --require-hashes -r documentation/requirements.lock
.venv-docs/bin/python -m zensical serve
```

On Windows, use `.venv-docs\Scripts\python.exe` for the commands above.
To validate and generate the static site:

```sh
.venv-docs/bin/python -m zensical build --clean --strict
```

The generated `site/` directory is ignored by Git. The build checks Markdown
links and produces a searchable static site, using system fonts without analytics.
Update `documentation/requirements.in` and regenerate the lock with
`uv pip compile --universal --python-version 3.11 --generate-hashes documentation/requirements.in -o documentation/requirements.lock`
when upgrading the documentation toolchain.

## CI and hosting

The Documentation workflow builds the site for documentation pull requests and
pushes, then uploads a static-site artifact for review. GitHub Pages deployment
is available through a manual workflow run with **deploy** selected, from `main`.
Configure the repository's Pages source as **GitHub Actions** before deploying.
The configured Pages URL is the intended hosting location; a successful local
build or uploaded artifact does not mean the documentation is published.

The same `site/` output can be hosted elsewhere. Change `site_url` before building
for another location, such as brouns.tech.
