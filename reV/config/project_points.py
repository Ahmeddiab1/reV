"""
reV Project Points Configuration
"""
import logging
import pandas as pd
import numpy as np
from warnings import warn
from math import ceil

from reV.utilities.exceptions import ConfigWarning
from reV.handlers.resource import Resource
from reV.config.sam_config import SAMConfig


logger = logging.getLogger(__name__)


class PointsControl:
    """Class to manage and split ProjectPoints."""
    def __init__(self, project_points, sites_per_split=100):
        """Initialize points control object.

        Parameters
        ----------
        project_points : reV.config.ProjectPoints
            ProjectPoints instance to be split between execution workers.
        sites_per_split : int
            Sites per project points split instance returned in the __next__
            iterator function.
        """

        self._project_points = project_points
        self._sites_per_split = sites_per_split
        self._split_range = []

    def __iter__(self):
        """Initialize the iterator by pre-splitting into a list attribute."""
        self._i = 0

        # _last_site attribute is the starting index of the next
        # iteration. This is taken from the first index of the pp dataframe.
        self._last_site = self.project_points.df.index[0]

        # _ilim is the maximum index value
        self._ilim = self.project_points.df.index[-1] + 1

        logger.debug('PointsControl iterator initializing with site indices '
                     '{} through {}'
                     .format(self._last_site, self._ilim))

        # pre-initialize all iter objects
        self._iter_list = []
        while True:
            i0 = self._last_site
            i1 = np.min([i0 + self.sites_per_split, self._ilim])
            self._last_site = i1

            new = PointsControl.split(i0, i1, self.project_points,
                                      sites_per_split=self.sites_per_split)
            new._split_range = [i0, i1]

            if not new.project_points.sites:
                # no sites in new project points. Stop iterator.
                break
            else:
                self._iter_list.append(new)
        # pre-init iter limit as length of iter list
        self._N = len(self._iter_list)
        logger.debug('PointsControl stopped iteration at attempted '
                     'index of {}. Length of iterator is: {}'
                     .format(i1, len(self)))
        return self

    def __next__(self):
        """Iterate through and return next site resource data.

        Returns
        -------
        next_pc : config.PointsControl
            Split instance of this class with a subset of project points based
            on the number of sites per split.
        """
        if self._i < self._N:
            # Get next PointsControl from the iter list
            next_pc = self._iter_list[self._i]
        else:
            # No more points controllers left in initialized list
            raise StopIteration

        logger.debug('PointsControl passing site project points '
                     'with indices {} to {} on iteration #{} '
                     .format(next_pc.split_range[0],
                             next_pc.split_range[1], self._i))
        self._i += 1
        return next_pc

    def __repr__(self):
        msg = ("{} for sites {} through {}"
               .format(self.__class__.__name__, self.sites[0], self.sites[-1]))
        return msg

    def __len__(self):
        """Len is the number of possible iterations aka splits."""
        return ceil(len(self.project_points) / self.sites_per_split)

    @property
    def sites_per_split(self):
        """Get the iterator increment: number of sites per split.

        Returns
        -------
        _sites_per_split : int
            Sites per split iter object.
        """
        return self._sites_per_split

    @property
    def project_points(self):
        """Get the project points property.

        Returns
        -------
        _project_points : reV.config.project_points.ProjectPoints
            ProjectPoints instance corresponding to this PointsControl
            instance.
        """
        return self._project_points

    @property
    def sites(self):
        """Get the project points sites for this instance.

        Returns
        -------
        sites : list
            List of sites belonging to the _project_points attribute.
        """
        return self._project_points.sites

    @property
    def split_range(self):
        """Get the current split range property.

        Returns
        -------
        _split_range : list
            Two-entry list that indicates the starting and finishing
            (inclusive, exclusive, respectively) indices of a split instance
            of the PointsControl object. This is set in the iterator dunder
            methods of PointsControl.
        """
        return self._split_range

    @classmethod
    def split(cls, i0, i1, project_points, sites_per_split=100):
        """Split this execution by splitting the project points attribute.

        Parameters
        ----------
        i0/i1 : int
            Beginning/end (inclusive/exclusive, respectively) index split
            parameters for ProjectPoints.split.
        project_points : reV.config.ProjectPoints
            Project points instance that will be split.
        sites_per_split : int
            Sites per project points split instance returned in the __next__
            iterator function.

        Returns
        -------
        sub : PointsControl
            New instance of PointsControl with a subset of the original
            project points.
        """
        i0 = int(i0)
        i1 = int(i1)
        new_points = ProjectPoints.split(i0, i1,
                                         project_points.df,
                                         project_points.sam_files,
                                         project_points.tech,
                                         project_points.res_file)
        sub = cls(new_points, sites_per_split=sites_per_split)
        return sub


class ProjectPoints:
    """Class to manage site and SAM input configuration requests.

    Use Cases
    ---------
    config_id@site0, SAM_config_dict@site0 = ProjectPoints[0]
    site_list_or_slice = ProjectPoints.sites
    site_list_or_slice = ProjectPoints.get_sites_from_config(config_id)
    ProjectPoints_sub = ProjectPoints.split(0, 10, ...)
    h_list = ProjectPoints.h
    """

    def __init__(self, points, sam_files, tech, res_file=None):
        """Init project points containing sites and corresponding SAM configs.

        Parameters
        ----------
        points : slice | str | pd.DataFrame
            Slice specifying project points, string pointing to a project
            points csv, or a dataframe containing the effective csv contents.
        sam_files : dict | str | list
            SAM input configuration ID(s) and file path(s). Keys are the SAM
            config ID(s), top level value is the SAM path. Can also be a single
            config file str. If it's a list, it is mapped to the sorted list
            of unique configs requested by points csv.
        tech : str
            reV technology being executed.
        res_file : str | NoneType
            Optional resource file to find maximum length of project points if
            points slice stop is None.
        """

        # set protected attributes
        self._points = points
        self._res_file = res_file
        self._tech = tech

        # if sam files is a dict or string, set first.
        if isinstance(sam_files, (dict, str)):
            self.sam_files = sam_files

        # create the project points from the raw configuration dict
        self.parse_project_points(points)

        # If the sam files is a list, set last
        if isinstance(sam_files, list):
            self.sam_files = sam_files

    def __getitem__(self, site):
        """Get the SAM config ID and dictionary for the requested site.

        Parameters
        ----------
        site : int | str
            Site number of interest.

        Returns
        -------
        config_id : str
            Configuration ID (variable name) specified in the sam_generation
            config section.
        config : dict
            Actual SAM input values in a single level dictionary with variable
            names (keys) and values.
        """

        site_bool = (self.df['gid'] == site)
        try:
            config_id = self.df.loc[site_bool, 'config'].values[0]
        except KeyError:
            raise KeyError('Site {} not found in this instance of '
                           'ProjectPoints. Available sites include: {}'
                           .format(site, self.sites))
        return config_id, self.sam_configs[config_id]

    def __repr__(self):
        msg = ("{} for sites {} through {}"
               .format(self.__class__.__name__, self.sites[0], self.sites[-1]))
        return msg

    def __len__(self):
        """Length of this object is the number of sites."""
        return len(self.sites)

    @property
    def df(self):
        """Get the project points dataframe property.

        Returns
        -------
        _df : pd.DataFrame
            Table of sites and corresponding SAM configuration IDs.
            Has columns 'gid' and 'config'.
        """
        return self._df

    @df.setter
    def df(self, data):
        """Set the project points dataframe property.

        Parameters
        ----------
        data : str | dict | pd.DataFrame
            Either a csv filename, dict with sites and configs keys, or full
            dataframe.
        """

        if isinstance(data, str):
            if data.endswith('.csv'):
                self._df = pd.read_csv(data)
            else:
                raise TypeError('Project points file must be csv but received:'
                                ' {}'.format(data))
        elif isinstance(data, dict):
            if 'gid' in data.keys() and 'config' in data.keys():
                self._df = pd.DataFrame(data)
            else:
                raise KeyError('Project points data must contain sites and '
                               'configs column headers.')
        elif isinstance(data, pd.DataFrame):
            if ('gid' in data.columns.values and
                    'config' in data.columns.values):
                self._df = data
            else:
                raise KeyError('Project points data must contain "gid" and '
                               '"config" column headers.')
        else:
            raise TypeError('Project points data must be csv filename or '
                            'dictionary but received: {}'.format(type(data)))

    def join_df(self, df2, key='gid'):
        """Join new df2 to the _df attribute using the _df's gid as pkey.

        This can be used to add site-specific data to the project_points,
        taking advantage of the points_control iterator/split functions such
        that only the relevant site data is passed to the analysis functions.

        Parameters
        ----------
        df2 : pd.DataFrame
            Dataframe to be joined to the _df attribute. This likely contains
            site-specific inputs that are to be passed to parallel workers.
        key : str | pd.DataFrame.index
            Primary key of df2 to be joined to the _df attribute. Primary key
            of the _df attribute is fixed as the gid column.
        """

        self._df = pd.merge(self._df, df2, how='left', left_on='gid',
                            right_on=key, copy=False, validate='1:1')

    @property
    def h(self):
        """Get the hub heights corresponding to the site list.

        Returns
        -------
        _h : list | NoneType
            Hub heights corresponding to each site, taken from the sam config
            for each site. This is None if the technology is not wind.
        """
        h_var = 'wind_turbine_hub_ht'
        if not hasattr(self, '_h') and 'wind' in self.tech:
            # wind technology, get a list of h values
            self._h = [self[site][1][h_var] for site in self.sites]

        elif not hasattr(self, '_h') and 'wind' not in self.tech:
            # not a wind tech, return None
            self._h = None

        return self._h

    @property
    def points(self):
        """Get the original points input.

        Returns
        -------
        points : slice | str | pd.DataFrame
            Slice specifying project points, string pointing to a project
            points csv, or a dataframe containing the effective csv contents.
        """
        return self._points

    @property
    def sam_files(self):
        """Get the SAM files dictionary property.

        Returns
        -------
        _sam_files: dict
            Multi-level dictionary containing multiple SAM input config files.
            The top level key is the SAM config ID, top level value is the SAM
            config file path
        """
        return self._sam_files

    @sam_files.setter
    def sam_files(self, files):
        """Set the SAM files dictionary.

        Parameters
        ----------
        files : dict | str | list
            SAM input configuration ID(s) and file path(s). Keys are the SAM
            config ID(s), top level value is the SAM path. Can also be a single
            config file str. If it's a list, it is mapped to the sorted list
            of unique configs requested by points csv.
        """

        if isinstance(files, dict):
            self._sam_files = files
        elif isinstance(files, str):
            self._sam_files = {0: files}
        elif isinstance(files, list):
            files = sorted(files)
            ids = pd.unique(self.df['config'])
            self._sam_files = {}
            for i, config_id in enumerate(sorted(ids)):
                try:
                    logger.debug('Mapping project points config ID #{} "{}" '
                                 'to {}'
                                 .format(i, config_id, files[i]))
                    self._sam_files[config_id] = files[i]
                except IndexError:
                    raise IndexError('Setting project points SAM configs with '
                                     'a list raised an error. Project points '
                                     'has the following unique configs: {}, '
                                     'while the following list of SAM configs '
                                     'were input: {}'
                                     .format(ids, files))

    @property
    def sam_config_obj(self):
        """Get the SAM config object.

        Returns
        -------
        _sam_config_obj : reV.config.sam_config.SAMConfig
            SAM configuration object.
        """

        if not hasattr(self, '_sam_config_obj'):
            self._sam_config_obj = SAMConfig(self.sam_files)
        return self._sam_config_obj

    @property
    def sam_configs(self):
        """Get the SAM configs dictionary property.

        Returns
        -------
        _sam_configs : dict
            Multi-level dictionary containing multiple SAM input
            configurations. The top level key is the SAM config ID, top level
            value is the SAM config. Each SAM config is a dictionary with keys
            equal to input names, values equal to the actual inputs.
        """

        return self.sam_config_obj.inputs

    @property
    def sites(self):
        """Get the sites belonging to this instance of ProjectPoints.

        Returns
        -------
        _sites : list | slice
            List of sites belonging to this instance of ProjectPoints. The type
            is list if possible. Will be a slice only if slice stop is None.
        """
        return self._sites

    @sites.setter
    def sites(self, sites):
        """Set the sites property.

        Parameters
        ----------
        sites : list | tuple | slice
            Data to be interpreted as the site list. Can be an explicit site
            list (list or tuple) or a slice that will be converted to a list.
            If slice stop is None, the length of the first resource meta
            dataset is taken as the stop value.
        """

        if isinstance(sites, (list, tuple)):
            # explicit site list, set directly
            self._sites = sites
        elif isinstance(sites, slice):
            if sites.stop:
                # there is an end point, can store as list
                self._sites = list(range(*sites.indices(sites.stop)))
            else:
                # no end point, find one from the length of the meta data
                res = Resource(self.res_file)
                stop = res.shape[1]
                self._sites = list(range(*sites.indices(stop)))
        else:
            raise TypeError('Project Points sites needs to be set as a list, '
                            'tuple, or slice, but was set as: {}'
                            .format(type(sites)))

    @property
    def sites_as_slice(self):
        """Get the sites in slice format.

        Returns
        -------
        _sites_as_slice : list | slice
            Sites slice belonging to this instance of ProjectPoints.
            The type is slice if possible. Will be a list only if sites are
            non-sequential.
        """

        if not hasattr(self, '_sites_as_slice'):
            if isinstance(self.sites, slice):
                self._sites_as_slice = self.sites
            else:
                # try_slice is what the sites list would be if it is sequential
                if len(self.sites) > 1:
                    try_step = self.sites[1] - self.sites[0]
                else:
                    try_step = 1
                try_slice = slice(self.sites[0], self.sites[-1] + 1, try_step)
                try_list = list(range(*try_slice.indices(try_slice.stop)))

                if self.sites == try_list:
                    # try_slice is equivelant to the site list
                    self._sites_as_slice = try_slice
                else:
                    # cannot be converted to a sequential slice, return list
                    self._sites_as_slice = self.sites

        return self._sites_as_slice

    @property
    def res_file(self):
        """Get the resource file (only used for getting number of sites).

        Returns
        -------
        _res_file : str | NoneType
            Optional resource file to find maximum length of project points if
            points slice stop is None.
        """
        return self._res_file

    @property
    def tech(self):
        """Get the tech property from the config.

        Returns
        -------
        _tech : str
            reV technology being executed.
        """
        return self._tech

    def get_sites_from_config(self, config):
        """Get a site list that corresponds to a config key.

        Parameters
        ----------
        config : str
            SAM configuration ID associated with sites.

        Returns
        -------
        sites : list
            List of sites associated with the requested configuration ID. If
            the configuration ID is not recognized, an empty list is returned.
        """

        sites = self.df.loc[(self.df['config'] == config), 'gid'].values
        return list(sites)

    def parse_project_points(self, points):
        """Parse points and set the project points attributes.

        Parameters
        ----------
        points : slice | str | pd.DataFrame
            Slice specifying project points, string pointing to a project
            points csv, or a dataframe containing the effective csv contents.
        """
        if isinstance(points, pd.DataFrame):
            self.df = points
            self.sites = list(self.df['gid'].values)
        elif isinstance(points, str):
            self.csv_project_points(points)
        elif isinstance(points, slice):
            if points.stop is None and self.res_file is None:
                raise ValueError('If a project points slice stop is not '
                                 'specified, a resource file must be '
                                 'input to find the number of sites to '
                                 'analyze.')
            self.slice_project_points(points)
        else:
            raise TypeError('Unacceptable project points input type: {}'
                            .format(type(points)))

    def csv_project_points(self, fname):
        """Set the project points using the target csv.

        Parameters
        ----------
        fname : str
            Project points .csv file (with path). Must have 'gid' and 'config'
            column names.
        """
        if fname.endswith('.csv'):
            self.df = fname
            self.sites = list(self.df['gid'].values)
        else:
            raise ValueError('Config project points file must be '
                             '.csv, but received: {}'
                             .format(fname))

    def slice_project_points(self, points):
        """Set the project points using slice parameters.

        Parameters
        ----------
        points : slice
            Project points slice specifying points to run.
        """
        self.sites = points

        # get the sorted list of available SAM configurations and use the first
        avail_configs = sorted(list(self.sam_configs.keys()))
        self.default_config_id = avail_configs[0]

        if len(avail_configs) > 1:
            warn('Multiple SAM input configurations detected '
                 'for a slice-based site project points. '
                 'Defaulting to: "{}"'
                 .format(avail_configs[0]), ConfigWarning)

        # Make a site-to-config dataframe using the default config
        site_config_dict = {'gid': self.sites,
                            'config': [self.default_config_id
                                       for s in self.sites]}
        self.df = site_config_dict

    @classmethod
    def split(cls, i0, i1, points_df, sam_files, tech, res_file):
        """Return split instance of this ProjectPoints w/ site subset.

        Parameters
        ----------
        i0 : int
            Starting INDEX (not site number) (inclusive) of the site property
            attribute to include in the split instance. This is not necessarily
            the same as the starting site number, for instance if ProjectPoints
            is sites 20:100, i0=0 i1=10 will result in sites 20:30.
        i1 : int
            Ending INDEX (not site number) (exclusive) of the site property
            attribute to include in the split instance. This is not necessarily
            the same as the final site number, for instance if ProjectPoints is
            sites 20:100, i0=0 i1=10 will result in sites 20:30.
        points_df : pd.DataFrame
            Upstream project points dataframe to be split.
        sam_files : dict | str
            SAM input configuration ID(s) and file path(s). Keys are the SAM
            config ID(s), top level value is the SAM path. Can also be a single
            config file str.
        tech : str
            reV technology being executed.
        res_file : str
            Optional resource file to find maximum length of project points if
            points slice stop is None.

        Returns
        -------
        sub : ProjectPoints
            New instance of ProjectPoints with a subset of the following
            attributes: sites, project points df, and the self dictionary data
            struct.
        """
        # Extract DF subset with only index values between i0 and i1
        points_df = points_df[points_df.index.isin(list(range(i0, i1)))]

        # make a new instance of ProjectPoints with subset DF
        sub = cls(points_df, sam_files, tech, res_file=res_file)

        return sub