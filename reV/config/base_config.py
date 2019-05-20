"""
reV Base Configuration Frameworks
"""
import json
import logging
import os

from reV.utilities.exceptions import ConfigError
from reV import REVDIR, TESTDATADIR


logger = logging.getLogger(__name__)


class BaseConfig(dict):
    """Base class for configuration frameworks."""

    def __init__(self, config):
        """Initialize configuration object with keyword dict.

        Parameters
        ----------
        config : str | dict
            File path to config json or dictionary with pre-extracted config
        """
        self._logging_level = None
        self._name = None
        self._parse_config(config)

    def _parse_config(self, config):
        """Parse a config input and set appropriate instance attributes.

        Parameters
        ----------
        config : str | dict
            File path to config json or dictionary with pre-extracted config
        """

        # str_rep is a mapping of config strings to replace with real values
        self.str_rep = {'REVDIR': REVDIR,
                        'TESTDATADIR': TESTDATADIR,
                        }

        if isinstance(config, str):
            if not config.endswith('.json'):
                raise ConfigError('Config input string must be a json file '
                                  'but received: "{}"'.format(config))
            # get the directory of the config file
            self.dir = os.path.dirname(os.path.realpath(config)) + '/'
            self.str_rep['./'] = self.dir
            config = self.get_file(config)

        # Get file, Perform string replacement, save config to self instance
        config = self.str_replace(config, self.str_rep)

        self.set_self_dict(config)

    @staticmethod
    def check_files(flist):
        """Make sure all files in the input file list exist.

        Parameters
        ----------
        flist : list
            List of files (with paths) to check existance of.
        """
        for f in flist:
            if os.path.exists(f) is False:
                raise IOError('File does not exist: {}'.format(f))

    @staticmethod
    def load_json(fname):
        """Load json config into config class instance.

        Parameters
        ----------
        fname : str
            JSON filename (with path).

        Returns
        -------
        config : dict
            JSON file contents loaded as a python dictionary.
        """
        with open(fname, 'r') as f:
            # get config file
            config = json.load(f)
        return config

    @staticmethod
    def str_replace(d, strrep):
        """Perform a deep string replacement in d.

        Parameters
        ----------
        d : dict
            Config dictionary potentially containing strings to replace.
        strrep : dict
            Replacement mapping where keys are strings to search for and values
            are the new values.

        Returns
        -------
        d : dict
            Config dictionary with replaced strings.
        """

        if isinstance(d, dict):
            # go through dict keys and values
            for key, val in d.items():
                if isinstance(val, dict):
                    # if the value is also a dict, go one more level deeper
                    d[key] = BaseConfig.str_replace(val, strrep)
                elif isinstance(val, str):
                    # if val is a str, check to see if str replacements apply
                    for old_str, new in strrep.items():
                        # old_str is in the value, replace with new value
                        d[key] = val.replace(old_str, new)
                        val = val.replace(old_str, new)
        # return updated dictionary
        return d

    def set_self_dict(self, dictlike):
        """Save a dict-like variable as object instance dictionary items.

        Parameters
        ----------
        dictlike : dict
            Python namespace object to set to this dictionary-emulating class.
        """
        for key, val in dictlike.items():
            self.__setitem__(key, val)

    def get_file(self, fname):
        """Read the config file.

        Parameters
        ----------
        fname : str
            Full path + filename. Must be a .json file.

        Returns
        -------
        config : dict
            Config data.
        """

        logger.debug('Getting "{}"'.format(fname))
        if os.path.exists(fname) and fname.endswith('.json'):
            config = self.load_json(fname)
        elif os.path.exists(fname) is False:
            raise IOError('Configuration file does not exist: "{}"'
                          .format(fname))
        else:
            raise ConfigError('Unknown error getting configuration file: "{}"'
                              .format(fname))
        return config

    @property
    def logging_level(self):
        """Get user-specified logging level in "project_control" namespace.

        Returns
        -------
        _logging_level : int
            Python logging module level (integer format) corresponding to the
            config-specified logging level string.
        """

        if self._logging_level is None:
            levels = {'DEBUG': logging.DEBUG,
                      'INFO': logging.INFO,
                      'WARNING': logging.WARNING,
                      'ERROR': logging.ERROR,
                      'CRITICAL': logging.CRITICAL,
                      }
            # set default value
            self._logging_level = logging.INFO
            if 'logging_level' in self['project_control']:
                x = self['project_control']['logging_level']
                self._logging_level = levels[x.upper()]
        return self._logging_level

    @property
    def name(self):
        """Get the project name in "project_control" namespace.

        Returns
        -------
        _name : str
            Config-specified project control name.
        """

        if self._name is None:
            # set default value
            self._name = 'rev'
            if 'name' in self['project_control']:
                if self['project_control']['name']:
                    self._name = self['project_control']['name']
        return self._name
