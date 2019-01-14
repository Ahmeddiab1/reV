"""
Classes to handle capacity factor profiles and annual averages
"""
import h5py
import json
import numpy as np
import os
import pandas as pd
import re
from warnings import warn
from reV.utilities.exceptions import (ResourceRuntimeError, ResourceKeyError,
                                      ResourceValueError)
from reV.handlers.resource import Resource, parse_keys
from reV.utilities.exceptions import (HandlerRuntimeError, HandlerKeyError,
                                      HandlerValueError)
from reV.utilities.utilities import parse_year


class Outputs(Resource):
    """
    Base class to handle reV output data in .h5 format
    """
    def __init__(self, h5_file, unscale=True, mode='r'):
        """
        Parameters
        ----------
        h5_file : str
            Path to .h5 resource file
        unscale : bool
            Boolean flag to automatically unscale variables on extraction
        mode : str
            Mode to instantiate h5py.File instance
        """
        self._h5_file = h5_file
        self._h5 = h5py.File(h5_file, mode=mode)
        self._unscale = unscale
        self._mode = mode

    def __len__(self):
        _len = 0
        if 'time_index' in self.dsets:
            _len = super().__len__()

        return _len

    def __getitem__(self, keys):
        ds, ds_slice = parse_keys(keys)
        if ds in self.dsets:
            if ds == 'time_index':
                out = self._time_index(*ds_slice)
            elif ds == 'meta':
                out = self._meta(*ds_slice)
            else:
                out = self._get_ds(ds, *ds_slice)
        else:
            msg = '{} is not a valid Dataset'
            raise HandlerKeyError(msg)

        return out

    def __setitem__(self, keys, arr):
        if self.writable:
            ds, ds_slice = parse_keys(keys)
            slice_test = ds_slice == (slice(None, None, None),)
            if ds == 'meta' and slice_test:
                self.meta = arr
            elif ds == 'time_index' and slice_test:
                self.time_index = arr
            else:
                self._set_ds_array(ds, arr, *ds_slice)

    @property
    def shape(self):
        """
        Variable array shape from time_index and meta

        Returns
        -------
        tuple
            shape of variables arrays == (time, locations)
        """
        _shape = None
        dsets = self.dsets
        if 'time_index' in dsets and 'meta' in dsets:
            _shape = super().shape

        return _shape

    @property
    def writable(self):
        """
        Check to see if h5py.File instance is writable

        Returns
        -------
        bool
            Flag if mode is writable
        """
        mode = ['a', 'w', 'w-', 'x']
        if self._mode not in mode:
            msg = 'mode must be writable: {}'.format(mode)
            raise HandlerRuntimeError(msg)

        return True

    @Resource.meta.setter  # pylint: disable-msg=E1101
    def meta(self, meta):
        """
        Write meta data to disk, convert type if neccessary

        Parameters
        ----------
        meta : pandas.DataFrame | numpy.recarray
            Locational meta data
        """
        if isinstance(meta, pd.DataFrame):
            meta = self.to_records_array(meta)

        if 'meta' in self.dsets:
            ds_slice = slice(None, None, None)
            self._set_ds_array('meta', meta, ds_slice)
        else:
            self.create_ds('meta', meta.shape, meta.dtype, data=meta)

    @Resource.time_index.setter  # pylint: disable-msg=E1101
    def time_index(self, time_index):
        """
        Write time_index to dics, convert type if neccessary

        Parameters
        ----------
        time_index : pandas.DatetimeIndex | ndarray
            Temporal index of timesteps
        """
        if isinstance(time_index, pd.DatetimeIndex):
            time_index = np.array(time_index.astype(str), dtype='S20')

        if 'time_index' in self.dsets:
            ds_slice = slice(None, None, None)
            self._set_ds_array('time_index', time_index, ds_slice)
        else:
            self.create_ds('time_index', time_index.shape, time_index.dtype,
                           data=time_index)

    @property
    def SAM_configs(self):
        """
        SAM configuration JSONs used to create CF profiles

        Returns
        -------
        configs : dict
            Dictionary of SAM configuration JSONs
        """
        if 'meta' in self.dsets:
            configs = {k: json.loads(v)
                       for k, v in self._h5['meta'].attrs.items()}
        else:
            configs = {}

        return configs

    def get_config(self, config_name):
        """
        Get SAM config

        Parameters
        ----------
        config_name : str
            Name of config

        Returns
        -------
        config : dict
            SAM config JSON as a dictionary
        """
        if 'meta' in self.dsets:
            config = json.loads(self._h5['meta'].attrs[config_name])
        else:
            config = None

        return config

    def set_configs(self, SAM_configs):
        """
        Set SAM configuration JSONs as attributes of 'meta'

        Parameters
        ----------
        SAM_configs : dict
            Dictionary of SAM configuration JSONs
        """
        if self.writable:
            for key, config in SAM_configs.items():
                if isinstance(config, dict):
                    config = json.dumps(config)

                if not isinstance(key, str):
                    key = str(key)

                self._h5['meta'].attrs[key] = config

    @staticmethod
    def get_dtype(col):
        """
        Get column dtype for converstion to records array

        Parameters
        ----------
        col : pandas.Series
            Column from pandas DataFrame

        Returns
        -------
        str
            converted dtype for column
            -  float = float32
            -  int = int16 or int32 depending on data range
            -  object/str = U* max length of strings in col
        """
        dtype = col.dtype
        if np.issubdtype(dtype, np.floating):
            out = 'float32'
        elif np.issubdtype(dtype, np.integer):
            if col.max() < 32767:
                out = 'int16'
            else:
                out = 'int32'
        elif np.issubdtype(dtype, np.object_):
            size = int(col.str.len().max())
            out = 'S{:}'.format(size)
        else:
            out = dtype

        return out

    @staticmethod
    def to_records_array(df):
        """
        Convert pandas DataFrame to numpy Records Array

        Parameters
        ----------
        df : pandas.DataFrame
            Pandas DataFrame to be converted

        Returns
        -------
        numpy.rec.array
            Records array of input df
        """
        meta_arrays = []
        dtypes = []
        for c_name, c_data in df.iteritems():
            dtype = Outputs.get_dtype(c_data)
            if np.issubdtype(dtype, np.bytes_):
                data = c_data.str.encode('utf-8').values
            else:
                data = c_data.values

            arr = np.array(data, dtype=dtype)
            meta_arrays.append(arr)
            dtypes.append((c_name, dtype))

        return np.core.records.fromarrays(meta_arrays, dtype=dtypes)

    def _set_ds_array(self, ds_name, arr, *ds_slice):
        """
        Write ds to disk

        Parameters
        ----------
        ds_name : str
            Dataset name
        arr : ndarray
            Dataset data array
        ds_slice : tuple
            Dataset slicing that corresponds to arr
        """
        if ds_name not in self._h5:
            msg = '{} must be initialized!'.format(ds_name)
            raise HandlerRuntimeError(msg)

        self._h5[ds_name][ds_slice] = arr

    def _chunks(self, chunks):
        """
        Convert dataset chunk size into valid tuple based on variable array
        shape

        Parameters
        ----------
        chunks : tuple
            Desired dataset chunk size

        Returns
        -------
        ds_chunks : tuple
            dataset chunk size
        """
        if chunks is not None:
            shape = self.shape
            if chunks[0] is None:
                chunk_0 = shape[0]
            else:
                chunk_0 = np.min((shape[0], chunks[0]))

            if chunks[1] is None:
                chunk_1 = shape[1]
            else:
                chunk_1 = np.min((shape[1], chunks[1]))

            ds_chunks = (chunk_0, chunk_1)
        else:
            ds_chunks = None

        return ds_chunks

    def create_ds(self, ds_name, shape, dtype, chunks=None, attrs=None,
                  data=None):
        """
        Initialize dataset

        Parameters
        ----------
        ds_name : str
            Dataset name
        shape : tuple
            Dataset shape
        dtype : str
            Dataset numpy dtype
        chunks : tuple
            Dataset chunk size
        attrs : dict
            Dataset attributes
        data : ndarray
            Dataset data array
        """
        if self.writable:
            chunks = self._chunks(chunks)
            ds = self._h5.create_dataset(ds_name, shape=shape, dtype=dtype,
                                         chunks=chunks)
            if attrs is not None:
                for key, value in attrs.items():
                    ds.attrs[key] = value

            if data is not None:
                ds[...] = data

    @classmethod
    def write_profiles(cls, h5_file, meta, time_index, dset_name, profiles,
                       attrs, dtype, SAM_configs, year=None,
                       chunks=(None, 100), lcoe=None, **kwargs):
        """
        Write profiles to disk

        Parameters
        ----------
        h5_file : str
            Path to .h5 resource file
        meta : pandas.Dataframe
            Locational meta data
        time_index : pandas.DatetimeIndex
            Temporal timesteps
        dset_name : str
            Name of the target dataset (should identify the profiles).
        profiles : ndarray
            reV output result timeseries profiles
        attrs : dict
            Attributes to be set. May include 'scale_factor'.
        dtype : str
            Intended dataset datatype after scaling.
        SAM_configs : dict
            Dictionary of SAM configuration JSONs used to compute cf profiles
        year : int | str
            Year for which cf means were computed
            If None, inferred from h5_file name
        chunks : tuple
            Chunk size for profiles dataset
        lcoe : ndarray | NoneType
            Optional LCOE scalar array.
        """
        if profiles.shape != (len(time_index), len(meta)):
            msg = 'Profile dimensions does not match time index and meta'
            raise ResourceValueError(msg)

        if year is None:
            # Attempt to parse year from file name
            f_name = os.path.basename(h5_file)
            match = re.match(r'.*([1-3][0-9]{3})', f_name)
            if match:
                year = '_{}'.format(int(match.group(1)))
            else:
                warn('Cannot parse year from {}'.format(f_name))
                year = ''

        with cls(h5_file, mode=kwargs.get('mode', 'w-')) as f:
            # Save time index
            f['time_index'] = time_index
            # Save meta
            f['meta'] = meta
            # Add SAM configurations as attributes to meta
            f.set_configs(SAM_configs)

            # Get scale factor or default to 1 (no scaling)
            scale_factor = 1
            if 'scale_factor' in attrs:
                scale_factor = attrs['scale_factor']

            # apply scale factor and dtype
            profiles = (profiles * scale_factor).astype(dtype)

            f.create_ds(dset_name, profiles.shape, profiles.dtype,
                        chunks=chunks, attrs=attrs,
                        data=profiles)
            if lcoe is not None:
                # create an LCOE dataset if passed to this method
                lcoe_attrs = {'scale_factor': 1, 'units': 'dol/MWh'}
                lcoe = lcoe.astype('float32')

                f.create_ds('lcoe{}'.format(year), lcoe.shape, lcoe.dtype,
                            chunks=None, attrs=lcoe_attrs, data=lcoe)

    @classmethod
    def write_means(cls, h5_file, meta, dset_name, means, attrs, dtype,
                    SAM_configs, year=None, cf_chunks=None, lcoe=None,
                    **kwargs):
        """
        Write means array to disk

        Parameters
        ----------
        h5_file : str
            Path to .h5 resource file
        meta : pandas.Dataframe
            Locational meta data
        dset_name : str
            Name of the target dataset (should identify the means).
        means : ndarray
            reV output means array.
        attrs : dict
            Attributes to be set. May include 'scale_factor'.
        dtype : str
            Intended dataset datatype after scaling.
        SAM_configs : dict
            Dictionary of SAM configuration JSONs used to compute cf means
        year : int | str
            Year for which cf means were computed
            If None, inferred from h5_file name
        cf_chunks : tuple
            Chunk size for capacity factor means dataset
        lcoe : ndarray | NoneType
            Optional LCOE scalar array.
        """
        if len(means) != len(meta):
            msg = 'Number of means does not match meta'
            raise ResourceValueError(msg)

        if year is None:
            # Attempt to parse year from file name
            f_name = os.path.basename(h5_file)
            match = re.match(r'.*([1-3][0-9]{3})', f_name)
            if match:
                year = '_{}'.format(int(match.group(1)))
            else:
                warn('Cannot parse year from {}'.format(f_name))
                year = ''

        with cls(h5_file, mode=kwargs.get('mode', 'w-')) as f:
            # Save meta
            f['meta'] = meta
            # Add SAM configurations as attributes to meta
            f.set_configs(SAM_configs)

            # Get scale factor or default to 1 (no scaling)
            scale_factor = 1
            if 'scale_factor' in attrs:
                scale_factor = attrs['scale_factor']

            # apply scale factor and dtype
            means = (means * scale_factor).astype(dtype)

            f.create_ds('{}{}'.format(dset_name, year), means.shape,
                        means.dtype, chunks=cf_chunks, attrs=attrs,
                        data=means)
            if lcoe is not None:
                # create an LCOE dataset if passed to this method
                # units fixed as per reV SAM outputs
                lcoe_attrs = {'scale_factor': 1, 'units': 'dol/MWh'}
                lcoe = lcoe.astype('float32')

                f.create_ds('lcoe{}'.format(year), lcoe.shape, lcoe.dtype,
                            chunks=cf_chunks, attrs=lcoe_attrs, data=lcoe)
