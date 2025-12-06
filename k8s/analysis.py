import os
import time
import json
import numpy as np
import awkward as ak
import matplotlib.pyplot as plt

from config import samples, variables, weight_variables, bin_edges, bin_centres, step_size, xmin, xmax, lumi
from config import AutoMinorLocator, GeV
from selection import cut_trig, cut_trig_match, ID_iso_cut, cut_lep_type, cut_lep_charge, calc_mass, calc_weight
import uproot

def run_analysis(fraction, output_prefix):
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

    return N_sig, N_bg, signal_significance


def process_file_hist(sample_name, file_path, fraction):

    is_data_sample = "data" in sample_name.lower()

    n_bins = len(bin_edges) - 1
    hist = np.zeros(n_bins, dtype=float)
    hist_w2 = np.zeros(n_bins, dtype=float)

    print(f"[worker] Processing file {file_path} for sample '{sample_name}'")

    tree = uproot.open(file_path + ":analysis")

    for data in tree.iterate(
        variables + weight_variables + ["sum_of_weights", "lep_n"],
        library="ak",
        entry_stop=int(tree.num_entries * fraction),
    ):
        data = data[cut_trig(data.trigE, data.trigM)]
        data = data[cut_trig_match(data.lep_isTrigMatched)]

        data["leading_lep_pt"] = data["lep_pt"][:, 0]
        data["sub_leading_lep_pt"] = data["lep_pt"][:, 1]
        data["third_leading_lep_pt"] = data["lep_pt"][:, 2]
        data["last_lep_pt"] = data["lep_pt"][:, 3]

        data = data[data["leading_lep_pt"] > 20]
        data = data[data["sub_leading_lep_pt"] > 15]
        data = data[data["third_leading_lep_pt"] > 10]

        data = data[
            ID_iso_cut(
                data.lep_isLooseID,
                data.lep_isMediumID,
                data.lep_isLooseIso,
                data.lep_isLooseIso,
                data.lep_type,
            )
        ]

        lep_type = data["lep_type"]
        data = data[~cut_lep_type(lep_type)]
        lep_charge = data["lep_charge"]
        data = data[~cut_lep_charge(lep_charge)]

        if len(data) == 0:
            continue

        data["mass"] = calc_mass(
            data["lep_pt"], data["lep_eta"], data["lep_phi"], data["lep_e"]
        )

        if not is_data_sample:
            data["totalWeight"] = calc_weight(weight_variables, data)

        mass = ak.to_numpy(data["mass"])
        if is_data_sample:
            h, _ = np.histogram(mass, bins=bin_edges)
            hist += h
        else:
            w = ak.to_numpy(data["totalWeight"])
            h, _ = np.histogram(mass, bins=bin_edges, weights=w)
            h2, _ = np.histogram(mass, bins=bin_edges, weights=w ** 2)
            hist += h
            hist_w2 += h2

    if is_data_sample:
        return hist, None
    else:
        return hist, hist_w2