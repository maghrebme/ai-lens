#!/bin/sh
# Ai-Lens — merge one weekly-milestones pull request, and nothing else.
#
#   ./tools/merge-weekly-pr.sh <pull-request-number>
#
# Refuses unless the pull request is open, targets main, comes from a weekly/
# branch of this repository, and changes only the timeline data and README.md.
# It squash-merges at the commit it checked, deletes the branch, and closes any
# older open weekly pull requests (their entries are expected to be included).
# Uses the maghrebme GitHub account for this command only.
set -eu

REPO="maghrebme/ai-lens"
API="https://api.github.com/repos/$REPO"
ALLOWED="assets/data/milestones.json assets/data/investments.json README.md"

n="${1:-}"
case "$n" in ''|*[!0-9]*) echo "usage: $0 <pull-request-number>" >&2; exit 2 ;; esac

TOKEN=$(gh auth token --user maghrebme)
api() { curl -sS -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$@"; }

pr=$(api "$API/pulls/$n")
read -r state base head head_repo sha <<EOF
$(printf '%s' "$pr" | python3 -c 'import json,sys; p=json.load(sys.stdin); print(p["state"], p["base"]["ref"], p["head"]["ref"], (p["head"]["repo"] or {}).get("full_name","-"), p["head"]["sha"])')
EOF

[ "$state" = "open" ] || { echo "refused: #$n is $state" >&2; exit 1; }
[ "$base" = "main" ] || { echo "refused: #$n targets $base, not main" >&2; exit 1; }
[ "$head_repo" = "$REPO" ] || { echo "refused: #$n comes from $head_repo" >&2; exit 1; }
case "$head" in weekly/*) ;; *) echo "refused: branch $head is not a weekly/ branch" >&2; exit 1 ;; esac

files=$(api "$API/pulls/$n/files?per_page=100" | python3 -c 'import json,sys; print(" ".join(f["filename"] for f in json.load(sys.stdin)))')
for f in $files; do
  case " $ALLOWED " in *" $f "*) ;; *) echo "refused: #$n changes $f" >&2; exit 1 ;; esac
done
echo "checked #$n ($head): changes only $files"

# Merge exactly the commit that was checked; GitHub rejects it if the branch moved.
result=$(api -X PUT "$API/pulls/$n/merge" -d "{\"merge_method\":\"squash\",\"sha\":\"$sha\"}")
printf '%s' "$result" | python3 -c 'import json,sys; r=json.load(sys.stdin); print("merged", r.get("sha","")[:7]) if r.get("merged") else sys.exit("merge failed: " + str(r.get("message")))'
api -X DELETE "$API/git/refs/heads/$head" -o /dev/null

# Close older open weekly pull requests, now superseded.
api "$API/pulls?state=open&base=main&per_page=100" | python3 -c '
import json,sys
n=int(sys.argv[1])
for p in json.load(sys.stdin):
    if p["number"] < n and p["head"]["ref"].startswith("weekly/") and (p["head"]["repo"] or {}).get("full_name")==sys.argv[2]:
        print(p["number"], p["head"]["ref"])' "$n" "$REPO" | while read -r old ref; do
  api -X POST "$API/issues/$old/comments" -d "{\"body\":\"Superseded by #$n, which has been merged.\"}" -o /dev/null
  api -X PATCH "$API/pulls/$old" -d '{"state":"closed"}' -o /dev/null
  api -X DELETE "$API/git/refs/heads/$ref" -o /dev/null
  echo "closed #$old ($ref)"
done
