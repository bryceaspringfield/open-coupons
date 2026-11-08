#!/bin/bash
# Lists each source's store pages from its sitemap, all sources at once.
cd "${SLURM_SUBMIT_DIR:-$(dirname "$0")/..}"
for s in honey capital_one_shopping coupons_com promocodes_com; do python3 seed/harvest.py $s --list-only & done
wait
