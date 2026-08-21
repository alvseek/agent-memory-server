#!/usr/bin/env bash
# fixture: author profile markdown at the import source root
# produces: a throwaway markdown source root in one of four user-profile states, ready for
#           the real importer — the end-state the "author the profile file" stage leaves behind
# fidelity: rung 1 reuse-snapshot for `present` and `absent` — every file is copied verbatim
#           from the live store, and absence is absence. `blank-vision` is rung 1 transformed:
#           the same real file with one value emptied. `markerless` is rung 3 — it models an
#           accident (a non-profile file at the profile's path), which no stage produces, so
#           there is nothing upstream to compare it against and nothing to drift from.
# fidelity-checked: 2026-08-21 — ran the real authoring stage,
#           control-files/core-memory/compile-scripts/user-profile-claude.sh, against a
#           sandboxed store with an empty vision answer. Its file and this fixture's
#           blank-vision output both end `- **[USER-AGENT-VISION]** = ` + newline, trailing
#           space included. The blank is in the body, which is what keeps "told us nothing"
#           distinguishable from "never asked".
# teardown: self-cleaning — everything lands under a disposable root (see --clean)
#
# Why this exists: reaching the "no profile", "not a profile" and "blank field" states
# otherwise means editing [AGENT-MEMORY-PATH]/shared-memory/user-profile.md, which is the
# single authored home for the real values. The DB is a rebuildable projection; that file
# is not. This builds an equivalent source instead of touching it.
#
# Usage:
#   bash qa/fixtures/profile-source.sh <mode>      # prints the source root as its last line
#   bash qa/fixtures/profile-source.sh --clean     # remove every root this fixture built
#
# Modes:
#   present      profile file copied verbatim        -> import stores exactly 1 user_profile row
#   absent       profile file not created            -> import succeeds, stores 0
#   markerless   file exists, carries no [USER-NAME] -> import succeeds, stores 0
#   blank-vision profile with an empty vision value  -> import stores 1; the blank is inside the body
#
# Compose with the bench (nothing in qa/scripts/ needs to change):
#   ROOT=$(bash qa/fixtures/profile-source.sh absent | tail -1)
#   bash qa/scripts/reset-db.sh
#   MUNNIN_IMPORT_SOURCE="$ROOT" bash qa/scripts/seed-meta.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

SRC="${MUNNIN_IMPORT_SOURCE:-$HOME/.claude/@agent-memory}"
BASE="${MUNNIN_FIXTURE_ROOT:-${TMPDIR:-/tmp}/munnin-qa-fixtures}"
PROFILE_REL="shared-memory/user-profile.md"

if [ "${1:-}" = "--clean" ]; then
  rm -rf "$BASE"
  echo "fixture: removed $BASE"
  exit 0
fi

MODE="${1:-}"
case "$MODE" in
  present|absent|markerless|blank-vision) ;;
  *) echo "usage: $0 {present|absent|markerless|blank-vision|--clean}" >&2; exit 2 ;;
esac

# The live store is the one thing this must never write into.
case "$BASE" in
  "$SRC"|"$SRC"/*) echo "refusing to build inside the live store ($SRC)" >&2; exit 3 ;;
esac
[ -d "$SRC" ] || { echo "source store not found: $SRC" >&2; exit 4; }

DEST="$BASE/$MODE"
rm -rf "$DEST"                       # idempotent: a re-run never stacks state
mkdir -p "$DEST/shared-memory"

# The importer reads exactly these, for `--agent meta`:
#   shared-memory/core-reasoning-memory.md   (unguarded — absence is a broken store)
#   shared-memory/core-knowledge-memory.md   (unguarded)
#   shared-memory/user-profile.md            (guarded — the mode varies this one)
#   agent-meta/                              (identity, index, knowledge-base/, episodes/)
cp "$SRC/shared-memory/core-reasoning-memory.md" "$DEST/shared-memory/"
cp "$SRC/shared-memory/core-knowledge-memory.md" "$DEST/shared-memory/"
cp -r "$SRC/agent-meta" "$DEST/agent-meta"

case "$MODE" in
  present)
    cp "$SRC/$PROFILE_REL" "$DEST/$PROFILE_REL"
    ;;
  absent)
    : # deliberately nothing — absence is the state under test
    ;;
  markerless)
    # Real content, no [USER-NAME]. parse_shared_profile returns [] on this, so the
    # importer must store nothing rather than noise under a name that promises meaning.
    cat > "$DEST/$PROFILE_REL" <<'MARKERLESS_EOF'
## Notes To Self

Not a profile. No marker here, just prose that happens to sit at the profile's path.
MARKERLESS_EOF
    ;;
  blank-vision)
    # Keep the line and the marker, empty the value: "told us nothing" — which the
    # bootstrap must read as an answer, not as never-having-been-asked.
    sed -E 's/^(- \*\*\[USER-AGENT-VISION\]\*\* =).*/\1 /' \
      "$SRC/$PROFILE_REL" > "$DEST/$PROFILE_REL"
    ;;
esac

echo "fixture: built '$MODE' source root (agent-meta + shared layer)" >&2
if [ -f "$DEST/$PROFILE_REL" ]; then
  echo "fixture: $PROFILE_REL present, $(wc -c < "$DEST/$PROFILE_REL") bytes" >&2
else
  echo "fixture: $PROFILE_REL not present" >&2
fi
echo "$DEST"
