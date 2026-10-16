#!/usr/bin/env bash
# Decide whether a commit on main gets a release, and its version.
#   .github/scripts/next-version.sh [commit]      (default HEAD; needs the tags fetched)
# Prints release=true|false, version=X.Y.Z and reason=… (also to $GITHUB_OUTPUT in Actions).
#
# The version goes up from the last v* tag: patch by default, or minor / major when a commit
# message since that release says [minor] / [major]. No release when a message says
# [skip release], or when only documentation and CI files changed.
set -euo pipefail

sha="$(git rev-parse "${1:-HEAD}^{commit}")"
out() {
    printf '%s\n' "$@"
    if [ -n "${GITHUB_OUTPUT:-}" ]; then printf '%s\n' "$@" >>"$GITHUB_OUTPUT"; fi
}

last="$(git describe --tags --abbrev=0 --match 'v[0-9]*' "$sha" 2>/dev/null || true)"
if [ -z "$last" ]; then
    out release=true version=0.1.0 "reason=first release"
    exit 0
fi
if [ "$(git rev-list -n 1 "$last")" = "$sha" ]; then
    out release=false version= "reason=$last is already this commit"
    exit 0
fi

messages="$(git log --format=%B "$last..$sha")"
if grep -qiF '[skip release]' <<<"$messages"; then
    out release=false version= "reason=a commit says [skip release]"
    exit 0
fi
if ! git diff --name-only "$last" "$sha" | grep -qvE '^(docs/|\.github/)|\.md$|^LICENSE$'; then
    out release=false version= "reason=only documentation and CI files changed since $last"
    exit 0
fi

IFS=. read -r major minor patch <<<"${last#v}"
prerelease=false
if [ "${patch%%[!0-9]*}" != "$patch" ]; then prerelease=true; fi # v2.0.0-rc1
patch="${patch%%[!0-9]*}"
if grep -qiF '[major]' <<<"$messages"; then
    major=$((major + 1)) minor=0 patch=0 bump=major
elif grep -qiF '[minor]' <<<"$messages"; then
    minor=$((minor + 1)) patch=0 bump=minor
elif [ "$prerelease" = true ]; then
    bump=final # after v2.0.0-rc1 comes 2.0.0
else
    patch=$((patch + 1)) bump=patch
fi
out release=true "version=$major.$minor.$patch" "reason=$bump release after $last"
