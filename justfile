# -- Settings ------------------------------------------------------------------

# Use latest version of PowerShell on Windows
set windows-shell := ["pwsh.exe", "-NoLogo", "-Command"]

# -- Recipes -------------------------------------------------------------------

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
