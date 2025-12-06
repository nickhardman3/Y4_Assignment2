import argparse
from analysis import run_analysis

parser = argparse.ArgumentParser(description="H->ZZ*->4l ATLAS open data analysis")
parser.add_argument("--fraction", type=float, default=1.0, help="Fraction of events to process (0<f<=1)")
parser.add_argument("--output-prefix", type=str, default="hzz_output", help="Prefix for output files (path/prefix)")
args = parser.parse_args()

fraction = args.fraction
output_prefix = args.output_prefix

run_analysis(fraction, output_prefix)
