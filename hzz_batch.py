import argparse
import json
import os

import numpy as np # for numerical calculations such as histogramming
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt # for plotting
#matplotlib_inline.backend_inline.set_matplotlib_formats('pdf', 'svg') # to make plots in pdf (vector) format
from matplotlib.ticker import AutoMinorLocator # for minor ticks
import uproot # for reading .root files
import awkward as ak # to represent nested data in columnar format
import vector # for 4-momentum calculations
import time # for printing time stamps
import requests # for file gathering, if needed

MeV = 0.001
GeV = 1.0

import atlasopenmagic as atom
atom.available_releases()
atom.set_release('2025e-13tev-beta')

parser = argparse.ArgumentParser(description="H->ZZ*->4l ATLAS open data analysis")
parser.add_argument("--fraction", type=float, default=1.0, help="Fraction of events to process (0<f<=1)")
parser.add_argument("--output-prefix", type=str, default="hzz_output", help="Prefix for output files (path/prefix)")
args = parser.parse_args()

skim = "exactly4lep"

defs = {
    r'Data':{'dids':['data']},
    r'Background $Z,t\bar{t},t\bar{t}+V,VVV$':{'dids': [410470,410155,410218,
                                                        410219,412043,364243,
                                                        364242,364246,364248,
                                                        700320,700321,700322,
                                                        700323,700324,700325],
                                               'color': "#6b59d3" },  # purple
    r'Background $ZZ^{*}$':     {'dids': [700600],'color': "#ff0000" },  # red
    r'Signal ($m_H$ = 125 GeV)':  {'dids': [345060, 346228, 346310, 346311, 346312,
                                            346340, 346341, 346342],'color': "#00cdff" },  # light blue
}

samples = atom.build_dataset(defs, skim=skim, protocol='https', cache=True)

variables = ['lep_pt','lep_eta','lep_phi','lep_e','lep_charge','lep_type',
             'trigE','trigM','lep_isTrigMatched',
             'lep_isLooseID','lep_isMediumID','lep_isLooseIso','lep_type']

weight_variables = ["filteff","kfac","xsec","mcWeight",
                    "ScaleFactor_PILEUP", "ScaleFactor_ELE",
                    "ScaleFactor_MUON", "ScaleFactor_LepTRIGGER"]

def cut_lep_type(lep_type):
    sum_lep_type = lep_type[:, 0] + lep_type[:, 1] + lep_type[:, 2] + lep_type[:, 3]
    lep_type_cut_bool = (sum_lep_type != 44) & (sum_lep_type != 48) & (sum_lep_type != 52)
    return lep_type_cut_bool

def cut_lep_charge(lep_charge):
    sum_lep_charge = (lep_charge[:, 0] + lep_charge[:, 1] +
                      lep_charge[:, 2] + lep_charge[:, 3] != 0)
    return sum_lep_charge

def calc_mass(lep_pt, lep_eta, lep_phi, lep_e):
    p4 = vector.zip({"pt": lep_pt, "eta": lep_eta, "phi": lep_phi, "E": lep_e})
    invariant_mass = (p4[:, 0] + p4[:, 1] + p4[:, 2] + p4[:, 3]).M
    return invariant_mass

def cut_trig_match(lep_trigmatch):
    trigmatch = lep_trigmatch
    cut1 = ak.sum(trigmatch, axis=1) >= 1
    return cut1

def cut_trig(trigE, trigM):
    return trigE | trigM

def ID_iso_cut(IDel, IDmu, isoel, isomu, pid):
    thispid = pid
    return (ak.sum(
        ((thispid == 13) & IDmu & isomu) |
        ((thispid == 11) & IDel & isoel),
        axis=1
    ) == 4)

xmin = 80 * GeV
xmax = 250 * GeV

step_size = 2.5 * GeV
bin_edges = np.arange(start=xmin,
                      stop=xmax + step_size,
                      step=step_size)
bin_centres = np.arange(start=xmin + step_size/2,
                        stop=xmax + step_size/2,
                        step=step_size)

def calc_weight(weight_variables, events):
    total_weight = lumi * 1000 / events["sum_of_weights"]
    for variable in weight_variables:
        total_weight = total_weight * abs(events[variable])
    return total_weight

lumi = 36.6

fraction = args.fraction

output_prefix = args.output_prefix
output_dir = os.path.dirname(output_prefix) or "."
os.makedirs(output_dir, exist_ok=True)

all_data = {}

for s in samples:
    print('Processing '+s+' samples')
    frames = []

    for val in samples[s]['list']:
        fileString = val

        start = time.time()
        print("\t"+val+":")

        tree = uproot.open(fileString + ":analysis")

        sample_data = []

        for data in tree.iterate(variables + weight_variables + ["sum_of_weights", "lep_n"],
                                 library="ak",
                                 entry_stop=tree.num_entries*fraction):

            nIn = len(data)

            data = data[cut_trig(data.trigE, data.trigM)]
            data = data[cut_trig_match(data.lep_isTrigMatched)]

            data['leading_lep_pt'] = data['lep_pt'][:,0]
            data['sub_leading_lep_pt'] = data['lep_pt'][:,1]
            data['third_leading_lep_pt'] = data['lep_pt'][:,2]
            data['last_lep_pt'] = data['lep_pt'][:,3]

            data = data[data['leading_lep_pt'] > 20]
            data = data[data['sub_leading_lep_pt'] > 15]
            data = data[data['third_leading_lep_pt'] > 10]

            data = data[ID_iso_cut(data.lep_isLooseID,
                                   data.lep_isMediumID,
                                   data.lep_isLooseIso,
                                   data.lep_isLooseIso,
                                   data.lep_type)]

            lep_type = data['lep_type']
            data = data[~cut_lep_type(lep_type)]
            lep_charge = data['lep_charge']
            data = data[~cut_lep_charge(lep_charge)]

            data['mass'] = calc_mass(data['lep_pt'], data['lep_eta'], data['lep_phi'], data['lep_e'])

            if 'data' not in s:
                data['totalWeight'] = calc_weight(weight_variables, data)

            if len(data) == 0:
                continue

            sample_data.append(data)

            if not 'data' in val:
                nOut = sum(data['totalWeight'])
            else:
                nOut = len(data)

            elapsed = time.time() - start
            print("\t\t nIn: "+str(nIn)+",\t nOut: \t"+str(nOut)+"\t in "+str(round(elapsed,1))+"s")

        if len(sample_data) == 0:
            print("\t\t no events passed selection for this file, skipping concatenate")
        else:
            frames.append(ak.concatenate(sample_data))

    if len(frames) == 0:
        print("No frames for "+s+", skipping sample")
        continue

    all_data[s] = ak.concatenate(frames)

data_x,_ = np.histogram(ak.to_numpy(all_data['Data']['mass']),
                        bins=bin_edges )
data_x_errors = np.sqrt( data_x )

signal_x = ak.to_numpy(all_data[r'Signal ($m_H$ = 125 GeV)']['mass'])
signal_weights = ak.to_numpy(all_data[r'Signal ($m_H$ = 125 GeV)'].totalWeight)
signal_color = samples[r'Signal ($m_H$ = 125 GeV)']['color']

mc_x = []
mc_weights = []
mc_colors = []
mc_labels = []

for s in samples:
    if s not in ['Data', r'Signal ($m_H$ = 125 GeV)'] and s in all_data:
        mc_x.append( ak.to_numpy(all_data[s]['mass']) )
        mc_weights.append( ak.to_numpy(all_data[s].totalWeight) )
        mc_colors.append( samples[s]['color'] )
        mc_labels.append( s )

fig, main_axes = plt.subplots(figsize=(12, 8))

main_axes.errorbar(x=bin_centres, y=data_x, yerr=data_x_errors,
                    fmt='ko',
                    label='Data')

mc_heights = main_axes.hist(mc_x, bins=bin_edges,
                            weights=mc_weights, stacked=True,
                            color=mc_colors, label=mc_labels )

mc_x_tot = mc_heights[0][-1]

mc_x_err = np.sqrt(np.histogram(np.hstack(mc_x), bins=bin_edges, weights=np.hstack(mc_weights)**2)[0])

signal_heights = main_axes.hist(signal_x, bins=bin_edges, bottom=mc_x_tot,
                weights=signal_weights, color=signal_color,
                label=r'Signal ($m_H$ = 125 GeV)')

main_axes.bar(bin_centres,
                2*mc_x_err,
                alpha=0.5,
                bottom=mc_x_tot-mc_x_err, color='none',
                hatch="////", width=step_size, label='Stat. Unc.' )

main_axes.set_xlim( left=xmin, right=xmax )

main_axes.xaxis.set_minor_locator( AutoMinorLocator() )

main_axes.tick_params(which='both',
                        direction='in',
                        top=True,
                        right=True )

main_axes.set_xlabel(r'4-lepton invariant mass $\mathrm{m_{4l}}$ [GeV]',
                    fontsize=13, x=1, horizontalalignment='right' )

main_axes.set_ylabel('Events / '+str(step_size)+' GeV',
                        y=1, horizontalalignment='right')

main_axes.set_ylim( bottom=0, top=np.amax(data_x)*2.0 )

main_axes.yaxis.set_minor_locator( AutoMinorLocator() )

plt.text(0.1,
            0.93,
            'ATLAS Open Data',
            transform=main_axes.transAxes,
            fontsize=16 )

plt.text(0.1,
            0.88,
            'for education',
            transform=main_axes.transAxes,
            style='italic',
            fontsize=12 )

lumi_used = str(lumi*fraction)
plt.text(0.1,
            0.82,
            r'$\sqrt{s}$=13 TeV,$\int$L dt = '+lumi_used+' fb$^{-1}$',
            transform=main_axes.transAxes,fontsize=16 )

plt.text(0.1,
            0.76,
            r'$H \rightarrow ZZ^* \rightarrow 4\ell$',
            transform=main_axes.transAxes,fontsize=16 )

my_legend = main_axes.legend( frameon=False, fontsize=16 )

signal_tot = signal_heights[0] + mc_x_tot

print(signal_tot[18])

print(signal_tot[17:20])

N_sig = signal_tot[17:20].sum()
N_bg = mc_x_tot[17:20].sum()

signal_significance = N_sig/np.sqrt(N_bg + 0.3 * N_bg**2)

plot_path = f"{output_prefix}_histogram.png"
plt.savefig(plot_path, dpi=200)

npz_path = f"{output_prefix}_data.npz"
np.savez(
    npz_path,
    bin_edges=bin_edges,
    bin_centres=bin_centres,
    data_x=data_x,
    data_x_errors=data_x_errors,
    mc_x_tot=mc_x_tot,
    mc_x_err=mc_x_err,
    signal_tot=signal_tot,
)

summary_path = f"{output_prefix}_summary.json"
summary = {
    "N_sig": float(N_sig),
    "N_bg": float(N_bg),
    "signal_significance": float(signal_significance),
    "fraction": float(fraction),
    "lumi_fb_inv": float(lumi),
}
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)

print(f"\nResults:\n{N_sig = }\n{N_bg = }\n{signal_significance = }\n")
print(f"Saved plot to {plot_path}")
print(f"Saved data to {npz_path}")
print(f"Saved summary to {summary_path}")
