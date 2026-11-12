#!/bin/bash
#SBATCH -J coupons_stress
#SBATCH -c 2
#SBATCH --mem=8G
#SBATCH -t 20
#SBATCH -o .temp/logs/%x_%j.out
cd "$SLURM_SUBMIT_DIR"; S=/tmp/coupons_stress_$SLURM_JOB_ID
~/.conda/envs/browser/bin/python 20_extension/code/tests/stress.py 20_extension/code/extension "$S"; rc=$?; rm -rf "$S"; exit $rc
