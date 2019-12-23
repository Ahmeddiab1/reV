# -*- coding: utf-8 -*-
"""
PyTest file for offshore aggregation of reV generation results and ORCA econ.

Created on Dec 16 2019

@author: gbuster
"""

import os
import pytest
import numpy as np
import json

from reV.handlers.outputs import Outputs
from reV import TESTDATADIR
from reV.offshore.offshore import Offshore


GEN_FPATH = os.path.join(TESTDATADIR, 'gen_out/ri_wind_gen_profiles_2010.h5')
OFFSHORE_FPATH = os.path.join(
    TESTDATADIR, 'offshore/preliminary_orca_results_09042019_JN.csv')
POINTS = os.path.join(TESTDATADIR, 'offshore/project_points.csv')
SAM_FILES = {'default': os.path.join(TESTDATADIR,
                                     'offshore/6MW_offshore.json')}
OUTPUT_FILE = os.path.join(TESTDATADIR, 'offshore/out.h5')

PURGE_OUT = True


@pytest.fixture
def offshore():
    """Offshore aggregation object for tests and plotting."""
    obj = Offshore.run(GEN_FPATH, OFFSHORE_FPATH, POINTS, SAM_FILES,
                       fpath_out=OUTPUT_FILE, sub_dir=None)
    return obj


def test_offshore_agg(offshore):
    """Run an offshore aggregation test and validate a few outputs against
    the raw gen output."""
    assert len(offshore.out['cf_mean']) == len(offshore.meta_out_offshore)
    assert all(offshore.meta_out['gid'] == sorted(offshore.meta_out['gid']))
    assert len(offshore.meta_out['gid'].unique()) == len(offshore.meta_out)

    with Outputs(GEN_FPATH, mode='r') as source:
        with Outputs(OUTPUT_FILE, mode='r') as out:

            source_meta = source.meta
            source_mean_data = source['cf_mean']
            source_lcoe_data = source['lcoe_fcr']
            source_ws_data = source['ws_mean']
            source_profile_data = source['cf_profile']

            out_meta = out.meta
            out_mean_data = out['cf_mean']
            out_lcoe_data = out['lcoe_fcr']
            out_ws_data = out['ws_mean']
            out_profile_data = out['cf_profile']

    for gid in offshore.onshore_gids:
        source_loc = np.where(source_meta['gid'] == gid)[0][0]
        out_loc = np.where(out_meta['gid'] == gid)[0][0]

        check_lcoe = (source_lcoe_data[source_loc]
                      == out_lcoe_data[out_loc])
        check_ws = (source_ws_data[source_loc]
                    == out_ws_data[out_loc])
        check_mean = (source_mean_data[source_loc]
                      == out_mean_data[out_loc])
        check_profile = np.allclose(source_profile_data[:, source_loc],
                                    out_profile_data[:, out_loc])
        m = ('Source onshore "{}" data for gid {} does not match '
             'output file data.')
        assert check_lcoe, m.format('lcoe', gid)
        assert check_ws, m.format('ws_mean', gid)
        assert check_mean, m.format('cf_mean', gid)
        assert check_profile, m.format('cf_profile', gid)

    for i in range(0, 20):

        agg_gids = offshore.meta_out_offshore.iloc[i]['offshore_res_gids']
        agg_gids = json.loads(agg_gids)
        farm_gid = offshore.meta_out_offshore.iloc[i]['gid']

        mask = np.isin(offshore.meta_source_full['gid'].values, agg_gids)
        gen_gids = np.where(mask)[0]
        if not any(gen_gids):
            raise ValueError('Could not find offshore farm gid {} resource '
                             'gids in meta source: {}'
                             .format(farm_gid, agg_gids))
        ws_mean = source_ws_data[gen_gids]
        lcoe_land = source_lcoe_data[gen_gids]
        cf_mean = source_mean_data[gen_gids]
        cf_profile = source_profile_data[:, gen_gids]

        m = 'Offshore lcoe was average aggregated instead of ORCA!'
        assert offshore.out['lcoe_fcr'][i] != lcoe_land.mean(), m

        m = 'Offshore output data "{}" does not match average source data!'
        check_cf_mean = offshore.out['cf_mean'][i] == cf_mean.mean()
        check_ws_mean = offshore.out['ws_mean'][i] == ws_mean.mean()
        check_profiles = np.allclose(offshore.out['cf_profile'][:, i],
                                     cf_profile.mean(axis=1))
        assert check_cf_mean, m.format('cf_mean')
        assert check_ws_mean, m.format('ws_mean')
        assert check_profiles, m.format('cf_profile')

    for i, gid in enumerate(offshore.offshore_gids):
        out_loc = np.where(out_meta['gid'] == gid)[0][0]
        arr1 = offshore.out['cf_profile'][:, i]
        arr2 = out_profile_data[:, out_loc]
        arr1 = np.round(arr1, decimals=3)
        diff = (arr1 - arr2)
        diff /= arr2
        m = ('Offshore cf profile data does not match output file data '
             'for gid {}'.format(gid))
        assert np.allclose(arr1, arr2), m

    if PURGE_OUT:
        os.remove(OUTPUT_FILE)


def plot_map(offshore):
    """Plot a map of offshore farm aggregation."""
    import matplotlib.pyplot as plt
    plt.scatter(offshore.meta_source_onshore['longitude'],
                offshore.meta_source_onshore['latitude'],
                c=(0.5, 0.5, 0.5), marker='s')

    cs = ['r', 'g', 'c', 'm', 'y', 'b'] * 100
    for ic, i in enumerate(np.unique(offshore._i)):
        if i != -1:
            ilocs = np.where(offshore._i == i)[0]
            plt.scatter(offshore.meta_source_offshore.iloc[ilocs]['longitude'],
                        offshore.meta_source_offshore.iloc[ilocs]['latitude'],
                        c=cs[ic], marker='s')
    plt.scatter(offshore.meta_out_offshore['longitude'],
                offshore.meta_out_offshore['latitude'],
                c='k', marker='x')
    plt.axis('equal')
    plt.show()
    plt.close()


def plot_timeseries(offshore, i=0):
    """Plot a timeseries of aggregated cf profile for offshore"""
    import matplotlib.pyplot as plt

    agg_gids = offshore.meta_out_offshore.iloc[i]['offshore_res_gids']
    agg_gids = json.loads(agg_gids)

    with Outputs(GEN_FPATH) as out:
        mask = np.isin(out.meta['gid'], agg_gids)
        gen_gids = np.where(mask)[0]
        cf_profile = out['cf_profile', :, gen_gids]

    tslice = slice(100, 120)
    a = plt.plot(cf_profile[tslice, :], c=(0.8, 0.8, 0.8))
    b = plt.plot(offshore.out['cf_profile'][tslice, i], c='b')
    plt.legend([a[0], b[0]], ['Resource Pixels', 'Offshore Aggregate'])
    plt.ylabel('Capacity Factor Profile')
    plt.show()
    plt.close()


def execute_pytest(capture='all', flags='-rapP'):
    """Execute module as pytest with detailed summary report.

    Parameters
    ----------
    capture : str
        Log or stdout/stderr capture option. ex: log (only logger),
        all (includes stdout/stderr)
    flags : str
        Which tests to show logs and results for.
    """

    fname = os.path.basename(__file__)
    pytest.main(['-q', '--show-capture={}'.format(capture), fname, flags])


if __name__ == '__main__':
    execute_pytest()