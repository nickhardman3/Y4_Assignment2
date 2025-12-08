import os
import json
import time

import numpy as np
import matplotlib.pyplot as plt
import pika

from config import (
    samples,
    bin_edges,
    bin_centres,
    step_size,
    xmin,
    xmax,
    lumi,
    AutoMinorLocator,
)
from config import GeV  

QUEUE_NAME = "hzz_partials" #queue for workers to send partial histograms


def make_final_outputs(hist_by_sample, w2_by_sample, fraction, output_prefix):
    data_label = "Data"
    signal_label = r"Signal ($m_H$ = 125 GeV)"

    n_bins = len(bin_edges) - 1

    data_x = hist_by_sample[data_label]
    data_x_errors = np.sqrt(data_x)

    mc_x_tot = np.zeros(n_bins, dtype=float)
    mc_x_err2 = np.zeros(n_bins, dtype=float)
    mc_hists = []
    mc_colors = []
    mc_labels = []

    for s in samples:
        if s in (data_label, signal_label):
            continue
        h = hist_by_sample.get(s)
        if h is None:
            continue
        mc_hists.append(h)
        mc_colors.append(samples[s]["color"])
        mc_labels.append(s)
        mc_x_tot += h
        mc_x_err2 += w2_by_sample.get(s, np.zeros_like(h))

    mc_x_err = np.sqrt(mc_x_err2)

    signal_hist = hist_by_sample[signal_label]
    signal_color = samples[signal_label]["color"]
    signal_tot = mc_x_tot + signal_hist

    N_sig = signal_tot[17:20].sum()
    N_bg = mc_x_tot[17:20].sum()
    signal_significance = N_sig / np.sqrt(N_bg + 0.3 * N_bg ** 2)

    fig, ax = plt.subplots(figsize=(12, 8))

    bottom = np.zeros(n_bins, dtype=float)
    for h, color, label in zip(mc_hists, mc_colors, mc_labels):
        ax.bar(
            bin_centres,
            h,
            bottom=bottom,
            width=step_size,
            color=color,
            label=label,
            align="center",
        )
        bottom += h

    ax.bar(
        bin_centres,
        2 * mc_x_err,
        bottom=mc_x_tot - mc_x_err,
        width=step_size,
        alpha=0.5,
        color="none",
        hatch="////",
        label="Stat. Unc.",
        align="center",
    )

    ax.bar(
        bin_centres,
        signal_hist,
        bottom=mc_x_tot,
        width=step_size,
        color=signal_color,
        label=signal_label,
        align="center",
    )

    ax.errorbar(
        bin_centres,
        data_x,
        yerr=data_x_errors,
        fmt="ko",
        label="Data",
    )

    ax.set_xlim(left=xmin, right=xmax)
    ax.xaxis.set_minor_locator(AutoMinorLocator())

    ax.tick_params(
        which="both",
        direction="in",
        top=True,
        right=True,
    )

    ax.set_xlabel(r"4-lepton invariant mass $m_{4\ell}$ [GeV]", fontsize=16)
    ax.set_ylabel("Events / 2.5 GeV", fontsize=16)

    plt.text(
        0.05,
        0.94,
        "ATLAS Open Data",
        transform=ax.transAxes,
        fontsize=16,
    )
    plt.text(
        0.05,
        0.88,
        "for education",
        transform=ax.transAxes,
        style="italic",
        fontsize=12,
    )

    lumi_used = str(lumi * fraction)
    plt.text(
        0.05,
        0.82,
        r"$\sqrt{s}$=13 TeV,$\int$L dt = " + lumi_used + r" fb$^{-1}$",
        transform=ax.transAxes,
        fontsize=16,
    )
    plt.text(
        0.05,
        0.76,
        r"$H \rightarrow ZZ^* \rightarrow 4\ell$",
        transform=ax.transAxes,
        fontsize=16,
    )

    ax.legend(frameon=False, fontsize=14)

    fig.tight_layout()

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

    print(f"[combiner] Saved plot to {plot_path}")
    print(f"[combiner] Saved data to {npz_path}")
    print(f"[combiner] Saved summary to {summary_path}")


def main():
    rabbitmq_host = os.environ.get("RABBITMQ_HOST", "rabbitmq")
    fraction = float(os.environ.get("JOB_FRACTION", "1.0"))
    output_prefix = os.environ.get("OUTPUT_PREFIX", "/outputs/hzz")

    total_files = sum(len(samples[s]["list"]) for s in samples)
    print(f"[combiner] Expecting {total_files} partial histograms")

    n_bins = len(bin_edges) - 1
    hist_by_sample = {s: np.zeros(n_bins, dtype=float) for s in samples}
    w2_by_sample = {
        s: np.zeros(n_bins, dtype=float) for s in samples if "data" not in s.lower()
    }

    params = pika.ConnectionParameters( #retry loop so the combiner waits for RMQ to become available
        host=rabbitmq_host,
        port=5672,
        heartbeat=600,
        blocked_connection_timeout=300,
    )

    connection = None
    while connection is None:
        try:
            print(f"[combiner] Connecting to RabbitMQ at {rabbitmq_host}:5672 ...")
            connection = pika.BlockingConnection(params)
            print("[combiner] Connected to RabbitMQ")
        except Exception as e:
            print(f"[combiner] Connection failed: {repr(e)}. Retrying in 5 seconds...")
            time.sleep(5)

    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    state = {"received": 0}

    def callback(ch, method, properties, body): #callback to handle each partial histogram message
        data = json.loads(body.decode("utf-8"))
        sample = data["sample"]
        hist = np.array(data["hist"], dtype=float)
        hist_by_sample[sample] += hist

        hist_w2 = data.get("hist_w2")
        if hist_w2 is not None:
            w2_by_sample[sample] += np.array(hist_w2, dtype=float)

        state["received"] += 1
        ch.basic_ack(delivery_tag=method.delivery_tag)

        if state["received"] % 10 == 0 or state["received"] == total_files:
            print(
                f"[combiner] Received {state['received']} / {total_files} partial histograms"
            )

        if state["received"] >= total_files:
            ch.stop_consuming()

    channel.basic_qos(prefetch_count=10)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)

    print("[combiner] Waiting for partial histograms...")
    channel.start_consuming()
    connection.close()

    print("[combiner] All partial histograms received, building final outputs...")
    make_final_outputs(hist_by_sample, w2_by_sample, fraction, output_prefix)


if __name__ == "__main__":
    main()
