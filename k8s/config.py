import argparse
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator
import uproot
import awkward as ak
import vector
import time
import requests

MeV = 0.001
GeV = 1.0

import atlasopenmagic as atom
atom.available_releases()
atom.set_release('2025e-13tev-beta')

skim = "exactly4lep"

defs = {
    r'Data':{'dids':['data']},
    r'Background $Z,t\bar{t},t\bar{t}+V,VVV$':{'dids': [410470,410155,410218,
                                                        410219,412043,364243,
                                                        364242,364246,364248,
                                                        700320,700321,700322,
                                                        700323,700324,700325],
                                               'color': "#6b59d3" },
    r'Background $ZZ^{*}$':     {'dids': [700600],'color': "#ff0000" },
    r'Signal ($m_H$ = 125 GeV)':  {'dids': [345060, 346228, 346310, 346311, 346312,
                                            346340, 346341, 346342],'color': "#00cdff" },
}

samples = atom.build_dataset(defs, skim=skim, protocol='https', cache=True)

variables = ['lep_pt','lep_eta','lep_phi','lep_e','lep_charge','lep_type',
             'trigE','trigM','lep_isTrigMatched',
             'lep_isLooseID','lep_isMediumID','lep_isLooseIso','lep_type']

weight_variables = ["filteff","kfac","xsec","mcWeight",
                    "ScaleFactor_PILEUP", "ScaleFactor_ELE",
                    "ScaleFactor_MUON", "ScaleFactor_LepTRIGGER"]

xmin = 80 * GeV
xmax = 250 * GeV

step_size = 2.5 * GeV
bin_edges = np.arange(start=xmin,
                      stop=xmax + step_size,
                      step=step_size)
bin_centres = np.arange(start=xmin + step_size/2,
                        stop=xmax + step_size/2,
                        step=step_size)

lumi = 36.6
