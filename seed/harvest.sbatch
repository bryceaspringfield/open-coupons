#!/bin/bash
#SBATCH -c 1
#SBATCH --mem=2G
#SBATCH -t 12:00:00
#SBATCH -o .temp/logs/%x_%j.out
# One source's harvest (sbatch --export=SOURCE=name). It stops cleanly before the time limit and resubmits itself while pages remain.
cd "$SLURM_SUBMIT_DIR"
python3 seed/harvest.py "$SOURCE" --max-minutes 700 | tee .temp/logs/harvest_${SOURCE}.last
left=$(grep -oP '^remaining \K\d+' .temp/logs/harvest_${SOURCE}.last | tail -1)
if [ "${left:-0}" -gt 0 ]; then sbatch -J "$SLURM_JOB_NAME" --export=SOURCE="$SOURCE" seed/harvest.sbatch; fi
python3 seed/build_db.py > .temp/logs/build_db.last 2>&1
