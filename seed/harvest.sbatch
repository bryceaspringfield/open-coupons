#!/bin/bash
#SBATCH -c 1
#SBATCH --mem=2G
#SBATCH -t 12:00:00
#SBATCH -o .temp/logs/%x_%j.out
# One source's harvest (sbatch --export=SOURCE=name[,HARVEST_ARGS="--egress E --shard I/N"]). It stops cleanly before the
# time limit and resubmits itself while pages remain.
cd "$SLURM_SUBMIT_DIR"
TAG="${SOURCE}$(echo "$HARVEST_ARGS" | tr -c 'a-z0-9' '_')"
PYTHONPATH=.temp/pylib ~/.conda/envs/browser/bin/python seed/harvest.py "$SOURCE" $HARVEST_ARGS --max-minutes 700 | tee ".temp/logs/harvest_${TAG}.last"
left=$(grep -oP '^remaining \K\d+' ".temp/logs/harvest_${TAG}.last" | tail -1)
# A run ended by refusals waits 2 hours before the next, since resubmitting at once presses an address the site refuses.
BEGIN=now; grep -q "refusals in a row" ".temp/logs/harvest_${TAG}.last" && BEGIN=now+2hours
if [ "${left:-0}" -gt 0 ]; then sbatch -J "$SLURM_JOB_NAME" --begin="$BEGIN" --export=SOURCE="$SOURCE",HARVEST_ARGS="$HARVEST_ARGS" seed/harvest.sbatch; fi
python3 seed/build_db.py > .temp/logs/build_db.last 2>&1
