# -- Settings ------------------------------------------------------------------

# Use latest version of PowerShell on Windows
set windows-shell := ["pwsh.exe", "-NoLogo", "-Command"]

# -- Recipes -------------------------------------------------------------------

# Setup Python environment
[group('setup')]
setup:
	uv venv --allow-existing
	uv sync

# Check code with various linters
[group('lint')]
check: setup
	uv run ruff check

# Run tests
[default]
[group('test')]
test: check
	uv run pytest

# Regenerate the Python and Rust code from the LinkML schema (icoschema/v*/schema/dataset.yaml)
[group('schema')]
generate: setup
	uv run python scripts/generate.py

# Fail if the generated code is stale compared to the LinkML schema
[group('schema')]
check-generated: setup
	uv run python scripts/generate.py --check

# Test the Rust port (needs a stable Rust toolchain); fails if the schema has something it does not handle,
# and checks that Python (libhdf5) reads what the Rust writer wrote
[group('test')]
test-rust: check-generated
	cargo test --workspace
	uv run python rust/tests/interop.py

# Rebuild the Rust test fixtures and their expected values from the Python implementation
[group('test')]
rust-fixtures: setup
	uv run python rust/tests/gen_fixtures.py
	uv run python rust/tests/gen_tdms_fixtures.py
	uv run python rust/tests/gen_malformed_fixtures.py

# Release new package version
[group('release')]
[unix]
release version:
	#!/usr/bin/env sh -e
	uv version {{version}}
	version="$(uv version --short)"
	git commit -a -m "Release: Release version ${version}"
	git tag "${version}"
	git push
	git push --tags

# Release new package version
[group('release')]
[windows]
release version:
	#!pwsh
	uv version {{version}}
	set version "$(uv version --short)"
	git commit -a -m "Release: Release version ${version}"
	git tag "${version}"
	git push
	git push --tags
