#!/bin/bash
#SBATCH -J coupons_ext_test
#SBATCH -c 2
#SBATCH --mem=4G
#SBATCH -t 20
#SBATCH -o .temp/logs/%x_%j.out
# The browser profile lives on the node's own disk, since /home is near its file-count cap.
S=/tmp/coupons_test_$SLURM_JOB_ID
~/.conda/envs/browser/bin/python tests/run_tests.py extension "$S"
rc=$?
rm -rf "$S"
exit $rc
