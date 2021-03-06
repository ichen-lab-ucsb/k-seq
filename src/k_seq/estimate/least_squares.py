"""Least-squares fitting to a kinetic model,

Several functions are included:
  - point estimation using `scipy.optimize.curve_fit`
  - option to exclude zero in fitting
  - option to initialize values
  - weighted fitting depends on the customized weights
  - confidence interval estimation using bootstrap
"""

from ._estimator import Estimator
from doc_helper import DocHelper
from ..utility import plot_tools
from ..utility.file_tools import read_json, dump_json, check_dir, load_tar_gz
from yutility import logging
import pandas as pd
import numpy as np
import json


__all__ = ['doc_helper', 'SingleFitter', 'FitResults']


doc_helper = DocHelper(
    x_data=('list', 'list of x values in fitting'),
    y_data=('list, pd.Series', 'y values in fitting'),
    x_label=('str', 'name of x data'),
    y_label=('str', 'name of y data'),
    model=('callable', 'model to fit'),
    name=('str', "Optional. Estimator's name"),
    sigma=('list, pd.Series, or pd.DataFrame', 'Optional, same size as y_data/y_dataframe.'
                                               'Sigma (variance) for data points for weighted fitting'),
    bounds=('2 by m `list` ', 'Optional, [[lower bounds], [higher bounds]] for each parameter'),
    opt_method=('str', "Optimization methods in `scipy.optimize`. Default 'trf'"),

    exclude_zero=('bool', "If exclude zero/missing data in fitting. Default False."),
    init_guess=('list of float or generator', "Initial guess estimate parameters, random value from 0 to 1 "
                                              "will be use if None"),
    metrics=('dict of callable', "Optional. Extra metric/parameters to calculate for each estimation"),
    rnd_seed=('int', "random seed used in fitting for reproducibility"),
    curve_fit_kwargs=('dict', 'other keyword parameters to pass to `scipy.optimize.curve_fit`'),
)

# add replicates/bootstrap related arguments
doc_helper.add(
    estimator=('Estimator', 'estimator for fitting'),
    replicates=('list of list', 'List of list of sample names for each replicates'),
    bootstrap_num=('`int`', 'Number of bootstrap to perform, 0 means no bootstrap'),
    bs_record_num=('`int`', 'Number of bootstrap results to store. Negative number means store all results.'
                            'Not recommended due to memory consumption'),
    bs_method=('`str`', "Bootstrap method, choose from 'pct_res' (resample percent residue),"
                        "'data' (resample data), or 'stratified' (resample within replicates)"),
    grouper=('dict or Grouper', 'Indicate the grouping of samples'),
    bs_stats=('dict of callable', 'a dict of stats functions to input the full record table (pd.DataFrame with '
                                  'parameters and metrics as columns) and return a single value, dict, or pd.Series'),
    record_full=('bool', 'if record the x_value and y_value for each bootstrapped sample; if False, '
                         'only parameters and metrics are recorded. Default False.')
)


# add convergence test related arguments
doc_helper.add(
    conv_reps=('int', 'number of repeated fitting from perturbed initial points for convergence test'),
    conv_init_range=('list of 2-tuple', 'a list of two tuple range (min, max) with same length as model parameters. '
                                        'If None, all parameters are initialized from (0, 1) with random uniform draw'),
    conv_stats=('dict of callable', 'a dict of stats functions to input the full record table (pd.DataFrame with '
                                    'parameters and metrics as columns) and return a single value, dict, or pd.Series'),
)


# add BatchEstimator arguments
doc_helper.add(
    seq_to_fit=('list of str', 'Optional. List of sequences used in batch fitting')
)


@doc_helper.compose("""Use `scipy.optimize.curve_fit` to fit a model for a sequence time/concentration series
It can conduct point estimation, uncertainty estimation for bootstrap, empirical CI estimation

Attributes:
    <<x_data, y_data, model, parameter, silent, name>>
    bootstrap (Bootstrap): proxy to the bootstrap object
    results (FitResult): proxy to the FitResult object
    config (AttrScope): name space for fitting, contains
    <<opt_method, exclude_zero, init_guess, rnd_seed, sigma, bounds, metric, curve_fit_kwargs>>
    bootstrap_config (AttrScope): name space for bootstrap, contains
    <<bootstrap_num, bs_record_num, bs_method>>""")
class SingleFitter(Estimator):

    def __repr__(self):
        return f"Single estimator for {self.name}"\
               f"<{self.__class__.__module__}{self.__class__.__name__} at {hex(id(self))}>"

    @doc_helper.compose("""Initialize a `SingleFitter` instance

    Args:
        <<>>
        save_to (str): optional. If not None, save results to the given path when fitting finishes
        overwrite (bool): if True, overwrite the save_to file if already exists;
            if False, read results and skip estimation. Default False
        verbose (0, 1, 2): set different verbose level. 0: WARNING, 1: INFO, 2: DEBUG
    """)
    def __init__(self, x_data, y_data, model, name=None, x_label=None, y_label=None,
                 sigma=None, bounds=None, init_guess=None,
                 opt_method='trf', exclude_zero=False, metrics=None, rnd_seed=None, curve_fit_kwargs=None,
                 replicates=None,
                 bootstrap_num=0, bs_record_num=0, bs_method='pct_res', bs_stats=None, grouper=None, record_full=False,
                 conv_reps=0, conv_init_range=None, conv_stats=None,
                 save_to=None, overwrite=False, verbose=1):

        from ..utility.func_tools import AttrScope, get_func_params
        from .bootstrap import Bootstrap
        from .convergence import ConvergenceTester
        from .replicates import Replicates

        super().__init__()
        if verbose == 0:
            logging.set_level('warning')
        elif verbose == 1:
            logging.set_level('info')
        elif verbose == 2:
            logging.set_level('debug')
        else:
            logging.error("verbose should be 0, 1, or 2", error_type=ValueError)

        if len(x_data) != len(y_data):
            logging.error('Shapes of x and y do not match', error_type=ValueError)

        self.model = model
        self.parameters = get_func_params(model, required_only=True)[1:]
        self.name = name
        self.config = AttrScope(
            x_label=x_label, y_label=y_label,
            opt_method=opt_method,
            exclude_zero=exclude_zero,
            init_guess=init_guess,
            rnd_seed=rnd_seed,
            curve_fit_kwargs={} if curve_fit_kwargs is None else curve_fit_kwargs
        )

        if isinstance(x_data, list):
            x_data = np.array(x_data)
        if isinstance(y_data, list):
            y_data = np.array(y_data)
        if exclude_zero is True:
            mask = y_data != 0
        else:
            mask = np.repeat(True, x_data.shape[0])

        self.x_data = x_data[mask]
        self.y_data = y_data[mask]
        if sigma is None:
            self.config.sigma = np.ones(len(self.y_data))
        elif isinstance(sigma, list):
            self.config.sigma = np.array(sigma)[mask]
        else:
            self.config.sigma = sigma[mask]

        if bounds is None:
            self.config.bounds = (-np.inf, np.inf)
        else:
            self.config.bounds = bounds

        if replicates is not None:
            self.replicates = Replicates(estimator=self, replicates=replicates)
        self.config.add(replicates=replicates)

        if bootstrap_num > 0 and len(self.x_data) > 1:
            if bs_record_num is None:
                bs_record_num = 0
            self.bootstrap = Bootstrap(estimator=self, bootstrap_num=bootstrap_num, bs_record_num=bs_record_num,
                                       bs_method=bs_method, bs_stats=bs_stats, grouper=grouper, record_full=record_full)
        else:
            self.bootstrap = None
        self.config.add(
            bootstrap_num=bootstrap_num,
            bs_record_num=bs_record_num,
            bs_method=bs_method,
            bs_stats=bs_stats,
            record_full=record_full,
            grouper=grouper
        )

        if conv_reps > 0:
            self.converge_tester = ConvergenceTester(conv_reps=conv_reps, estimator=self,
                                                     conv_init_range=conv_init_range, conv_stats=conv_stats)
        else:
            self.converge_tester = None
        self.config.add(
            conv_reps=conv_reps,
            conv_init_range=conv_init_range,
            conv_stats=conv_stats
        )

        self.config.metrics = metrics
        self.results = FitResults(estimator=self)
        self.save_to = save_to
        self.overwrite = overwrite
        logging.debug(f"{self.__repr__()} initiated")

    @doc_helper.compose("""Fitting using `scipy.optimize.curve_fit`,
    Arguments will be inferred from instance's attributes if not provided

    Args:
        <<model, x_data, y_data, sigma, bounds, metrics, init_guess, curve_fit_kwargs>>

    Returns: A dictionary contains least-squares fitting results
      - params: pd.Series of estimated parameter
      - pcov: `pd.Dataframe` of covariance matrix
      - metrics: None or pd.Series of calculated metrics
    """)
    def _fit(self, model=None, x_data=None, y_data=None, sigma=None, bounds="unspecified",
             metrics=None, init_guess=None, curve_fit_kwargs=None):

        from scipy.optimize import curve_fit
        from ..utility.func_tools import update_none
        from ..utility.func_tools import get_func_params

        model = update_none(model, self.model)
        parameters = get_func_params(model, required_only=True)[1:]
        x_data = update_none(x_data, self.x_data)
        y_data = update_none(y_data, self.y_data)
        sigma = update_none(sigma, self.config.sigma)
        if len(x_data) != len(sigma):
            sigma = None
            logging.debug('Sigma is ignored as it has different length as x_data')
        if bounds == "unspecified":
            bounds = self.config.bounds
        if bounds is None:
            bounds = (-np.inf, np.inf)
        metrics = update_none(metrics, self.config.metrics)

        init_guess = update_none(init_guess, self.config.init_guess)
        curve_fit_kwargs = update_none(curve_fit_kwargs, self.config.curve_fit_kwargs)

        try:
            if not init_guess:
                # by default, use a random guess form (0, 1)
                init_guess = [np.random.random() for _ in parameters]
            if curve_fit_kwargs is None:
                curve_fit_kwargs = {}
            params, pcov = curve_fit(f=model, xdata=x_data, ydata=y_data,
                                     sigma=sigma, bounds=bounds, p0=init_guess, **curve_fit_kwargs)
            if metrics is not None:
                metrics_res = pd.Series({name: fn(params) for name, fn in metrics.items()})
            else:
                metrics_res = None
        except RuntimeError:
            logging.warning(
                f"RuntimeError on \n"
                f'\tx = {x_data}\n'
                f'\ty={y_data}\n'
                f'\tsigma={sigma}'
            )
            params = np.full(fill_value=np.nan, shape=len(parameters))
            pcov = np.full(fill_value=np.nan, shape=(len(parameters), len(parameters)))
            if metrics is not None:
                metrics_res = pd.Series({name: np.nan for name, fn in metrics.items()})
            else:
                metrics_res = None
        except ValueError:
            logging.warning(
                f"ValueError on \n"
                f'\tx={x_data}\n'
                f'\ty={y_data}\n'
                f'\tsigma={sigma}'
            )
            params = np.full(fill_value=np.nan, shape=len(parameters))
            pcov = np.full(fill_value=np.nan, shape=(len(parameters), len(parameters)))
            if metrics is not None:
                metrics_res = pd.Series({name: np.nan for name, fn in metrics.items()})
            else:
                metrics_res = None
        except:
            logging.warning(
                f"Other error observed on\n"
                f'\tx={x_data}\n'
                f'\ty={y_data}\n'
                f'\tsigma={sigma}'
            )
            params = np.full(fill_value=np.nan, shape=len(parameters))
            pcov = np.full(fill_value=np.nan, shape=(len(parameters), len(parameters)))
            if metrics is not None:
                metrics_res = pd.Series({name: np.nan for name, fn in metrics.items()})
            else:
                metrics_res = None

        return {
            'params': pd.Series(data=params, index=parameters),
            'pcov': pd.DataFrame(data=pcov, index=parameters, columns=parameters),
            'metrics': metrics_res
        }

    @doc_helper.compose(_fit.__doc__)
    def point_estimate(self, **kwargs):
        results = self._fit(**kwargs)
        logging.debug(f'Point estimation for {self.__repr__()} finished')
        return results

    @doc_helper.compose("""Use bootstrap to estimate uncertainty
    Args:
        <<bs_method, bootstrap_num, grouper, bs_record_num, bs_stats, record_full>>

    Returns:
        summary: pd.Series
        results: pd.DataFrame subsampled if 0 <= bs_record_num <= bootstrap_num""")
    def run_bootstrap(self, bs_record_num=None, **kwargs):
        if bs_record_num is None:
            bs_record_num = self.config.bs_record_num
        if self.bootstrap is None:
            # if not initialized, enforce a bootstrap
            from .bootstrap import Bootstrap
            self.bootstrap = Bootstrap(estimator=self, **kwargs)
        else:
            # update if new bootstrap config is assigned
            if 'bs_method' in kwargs.keys():
                self.bootstrap.bs_method = kwargs['bs_method']
            if 'bootstrap_num' in kwargs.keys():
                self.bootstrap.bootstrap_num = kwargs['bootstrap_num']
            if 'grouper' in kwargs.keys():
                self.bootstrap.grouper = kwargs['grouper']

        summary, results = self.bootstrap.run()
        if 0 <= bs_record_num <= results.shape[0]:
            results = results.sample(n=bs_record_num, replace=False, axis=0)

        logging.debug(f"Bootstrap using {self.bootstrap.bs_method} for "
                      f"{self.bootstrap.bootstrap_num} and "
                      f"save {self.bootstrap.bs_record_num} records")
        return summary, results

    @doc_helper.compose("""Use replicates to estimate uncertainty
    Args:
        <<replicates>>
        
    Return:
        a pd.Dataframe of results from each replicates
    """)
    def run_replicates(self, replicates=None):
        if replicates is None:
            replicates = self.replicates
        else:
            from .replicates import Replicates
            replicates = Replicates(estimator=self, replicates=replicates)

        summary, results = replicates.run()
        logging.debug("Uncertainty estimation from replicates")
        return summary, results

    @doc_helper.compose("""Empirically estimate convergence by repeated fittings,
    Args:
        <<conv_reps, conv_init_range, conv_stats>>
    Returns:
        summary: pd.Series
        records: pd.DataFrame of full records
    """)
    def convergence_test(self, **kwargs):
        if self.converge_tester is None:
            from .convergence import ConvergenceTester
            self.converge_tester = ConvergenceTester(estimator=self, **kwargs)
        else:
            # update if new convergence test config is assigned
            if 'conv_reps' in kwargs.keys():
                self.converge_tester.conv_reps = kwargs['conv_reps']
            if 'conv_init_range' in kwargs.keys():
                self.converge_tester.conv_init_range = kwargs['conv_init_range']
            if 'conv_stats' in kwargs.keys():
                self.converge_tester.conv_stats = kwargs['conv_stats']

        return self.converge_tester.run()

    def fit(self, point_estimate=True, replicates=False, bootstrap=False, convergence_test=False, **kwargs):
        """Run fitting, configuration are from the object
        Args:
            point_estimate (bool): if do point estimation, default True
            replicates (bool): if use replicate for uncertainty estimation, default False
            bootstrap (bool): if do bootstrap, default False
            convergence_test (bool): if do convergence test, default False
        """

        save_to = kwargs.pop('save_to', self.save_to)
        overwrite = kwargs.pop('overwrite', self.overwrite)
        from pathlib import Path
        if save_to and (overwrite is False) and Path(save_to).exists():
            # result stream to hard drive, check if the result exists
            from json import JSONDecodeError
            try:
                # don't do fitting if can saved result is readable
                logging.debug(f'Try to recover info from {save_to}...')
                self.results = FitResults.from_json(json_path=save_to, estimator=self)
                logging.debug('Found, skip fitting...')
                return None
            except JSONDecodeError:
                # still do the fitting
                logging.debug('Can not parse JSON file, continue fitting...')
        logging.debug('Perform fitting...')
        rnd_seed = kwargs.pop('rnd_seed', self.config.rnd_seed)
        if rnd_seed:
            np.random.seed(rnd_seed)

        if point_estimate:
            results = self.point_estimate(**kwargs)
            self.results.point_estimation.params = results['params']
            if results['metrics'] is not None:
                self.results.point_estimation.params = self.results.point_estimation.params.append(results['metrics'])
            self.results.point_estimation.pcov = results['pcov']

        summary = pd.Series(name=self.name)

        if bootstrap and (len(self.x_data) >= 2):
            bs_summary, self.results.uncertainty.bs_records = self.run_bootstrap(**kwargs)
            summary = pd.concat([summary, bs_summary])

        if replicates:
            rep_summary, self.results.uncertainty.rep_results = self.run_replicates(**kwargs)
            summary = pd.concat([summary, rep_summary])

        if len(summary) > 0:
            self.results.uncertainty.summary = summary

        if convergence_test:
            self.results.convergence.summary, self.results.convergence.records = self.convergence_test(**kwargs)

        if self.save_to:
            # stream to disk as JSON file
            from pathlib import Path
            check_dir(Path(self.save_to).parent)
            self.results.to_json(self.save_to)

    def summary(self):
        """Return a pd.series as fitting summary with flatten info"""
        return self.results.to_series()

    def to_dict(self):
        """Save estimator configuration as a dictionary

        Returns:
            Dict of configurations for the estimator
        """

        config_dict = {
            **{
                'x_data': self.x_data,
                'y_data': self.y_data,
                'model': self.model,
                'name': self.name,
                'silent': self.silent,
            },
            **self.config.__dict__,
        }
        return config_dict

    def to_json(self, save_to_file=None):
        """Save the estimator configuration as a json file, except for `model`, `bs_stats`, `conv_stats` as
         these are not json-able
        """

        config_dict = self.to_dict()
        _ = config_dict.pop('model', None)
        if 'bs_stats' in config_dict.keys():
            config_dict['bs_stats'] = {key: func.__repr__ for key, func in config_dict['bs_stats']}
        if 'conv_stats' in config_dict.keys():
            config_dict['conv_stats'] = {key: func.__repr__ for key, func in config_dict['conv_stats']}
        if 'grouper' in config_dict.keys():
            config_dict['grouper'] = config_dict['grouper'].group

        if save_to_file:
            from pathlib import Path
            path = Path(save_to_file)
            if path.suffix == '.json':
                # its a named json file
                check_dir(path.parent)
                dump_json(obj=config_dict, path=path, indent=2)
            elif path.suffix == '':
                # its a directory
                check_dir(path)
                dump_json(obj=config_dict, path=str(path) + '/config.json', indent=2)
            else:
                logging.error('Unrecognized saving path', error_type=NameError)
        else:
            return dump_json(config_dict, indent=0)

    @classmethod
    def from_json(cls, file_path, model):
        """create a estimator from saved json file

        Args:
            file_path (str): path to saved json file
            model (callable): as callable is not json-able, need to reassign

        Notes:
            bs_stats, conv_stats currently can not be recovered
        """

        config_dict = read_json(file_path)
        return cls(model=model, **config_dict)


class FitResults:
    """A class to store, process, and visualize fitting results for single estimator, contains almost all information
    needed to further analysis

    Attributes:

         estimator (Estimator): proxy to the estimator

         model (callable): model used in fitting

         data (AttrScope): a scope stores the fitting data
             x_data (pd.Series):
             y_data (pd.Series):
             sigma (pd.Series):
             x_label (str): name for x data
             y_label (str): name for y data

         point_estimation (AttrScope): a scope stores point estimation results, includes
             params (pd.Series): stores the parameter estimation, with extra metrics calculation
             pcov (pd.DataFrame): covariance matrix for estimated parameter

         uncertainty (AttrScope): a scope stores uncertainty estimation results, includes
             summary (pd.Series): summary of each parameter or metric from records
             bs_records (pd.DataFrame): records for stored bootstrapping results
             rep_results (pd.DataFrame): results from fitting of replicates

         convergence (AttrScope): a scope stores convergence test results, includes
             summary (pd.DataFrame): summary for each parameter or metric from records
             records (pd.DataFrame): records for repeated fitting results

    """

    def __repr__(self):
        return f"Fitting results for {self.estimator} " \
               f"<{self.__class__.__module__}{self.__class__.__name__} at {hex(id(self))}>"

    def __init__(self, estimator, model=None):
        """
        Args:
            estimator (SingleFitter): estimator used to generate this fitting result

        """
        from ..utility.func_tools import AttrScope

        self.estimator = estimator
        self.model = model if estimator is None else estimator.model
        if estimator is None:
            self.data = AttrScope(keys=['x_data', 'y_data', 'sigma', 'x_label', 'y_label'])
        else:
            self.data = AttrScope(x_data=estimator.x_data.copy(),
                                  y_data=estimator.y_data.copy(),
                                  sigma=estimator.config.sigma.copy(),
                                  x_label=estimator.config.x_label,
                                  y_label=estimator.config.y_label)
        self.point_estimation = AttrScope(keys=['params', 'pcov'])
        self.uncertainty = AttrScope(keys=['summary', 'bs_records', 'rep_results'])
        self.convergence = AttrScope(keys=['summary', 'records'])

    def to_series(self):
        """Convert point_estimation, uncertainty (if possible), and convergence (if possible) to a series include
        flattened info:
        e.g. columns will include [param1, param2, bs_param1_mean, bs_param1_std, bs_param1_2.5%, ..., param1_range]
        """
        from ..utility.func_tools import dict_flatten

        res = pd.Series()
        if self.point_estimation.params is not None:
            res = res.append(self.point_estimation.params)
        if self.uncertainty.summary is not None:
            # uncertainty estimation results exists
            res = res.append(self.uncertainty.summary)

        if self.convergence.summary is not None:
            #  convergence test results exists
            res = res.append(self.convergence.summary)

        if self.estimator is not None:
            res.name = self.estimator.name
        return res

    def to_json(self, path=None):
        """Convert results into a json string/file contains
            {
              point_estimation: { params: jsonfy(pd.Series)
                                  pcov: jsonfy(pd.DataFrame) }
              uncertainty: { summary: jsonfy(pd.Series)
                             bs_records: jsonfy(pd.DataFrame)
                             rep_results: jsonfy(pd.Series) }
              convergence: { summary: jsonfy(pd.DataFrame)
                             records: jsonfy(pd.DataFrame) }
              data: {x_data: jsonfy(pd.Series)
                     y_data: jsonfy(pd.Series),
                     sigma: jsonfy(pd.Series),
                     x_label: str,
                     y_label: str}
            }
        """

        def jsonfy(target):
            try:
                return target.to_json()
            except:
                return None

        data_to_dump = {
            'point_estimation': {
                'params': jsonfy(self.point_estimation.params),
                'pcov': jsonfy(self.point_estimation.pcov)
            },
            'uncertainty': {
                'summary': jsonfy(self.uncertainty.summary),
                'bs_records': jsonfy(self.uncertainty.bs_records),
                'rep_results': jsonfy(self.uncertainty.rep_results)
            },
            'convergence': {
                'summary': jsonfy(self.convergence.summary),
                'records': jsonfy(self.convergence.records)
            },
            'data': {
                'x_data': jsonfy(self.data.x_data),
                'y_data': jsonfy(self.data.y_data),
                'sigma': jsonfy(self.data.sigma),
                'x_label': jsonfy(self.data.x_label),
                'y_label': jsonfy(self.data.y_label),
            }
        }
        if path is None:
            return dump_json(data_to_dump)
        else:
            dump_json(data_to_dump, path=path)

    @classmethod
    def from_json(cls, json_path, tarfile=None, gzip=True, estimator=None, data=None):
        """load fitting results from json records, option to load from tar.gz files
        Note: no estimator info if estimator is None

        Args:
            json_path (str): path to json file, or file name under tarball file if tar_file_name is true tarfile (str):
                if not None, the json file is in a tarfile (.tar/.tar.gz)
            gzip (bool): if True, the tarfile is compressed with gzip (`.tar.gz`); if False, the tarfile is not
                compressed (`.tar`)
            estimator (SingleFitter): optional. Recover the estimator instance.
            data (dict): supplied dictionary to add data info
        """
        if tarfile is None:
            json_data = read_json(json_path)
        else:
            json_data = load_tar_gz(tarfile=tarfile, file_to_extract=json_path, gzip=gzip, load_fn=json.load)

        result = cls(estimator=estimator)

        if 'point_estimation' in json_data.keys():
            if json_data['point_estimation']['params'] is not None:
                result.point_estimation.params = pd.read_json(json_data['point_estimation']['params'], typ='series')
            if json_data['point_estimation']['pcov'] is not None:
                result.point_estimation.pcov = pd.read_json(json_data['point_estimation']['pcov'])
        if 'uncertainty' in json_data.keys():
            if json_data['uncertainty']['summary'] is not None:
                result.uncertainty.summary = pd.read_json(json_data['uncertainty']['summary'], typ='series')
            if 'record' in json_data['uncertainty'].keys():
                label = 'record'
            elif 'records' in json_data['uncertainty'].keys():
                label = 'records'
            elif 'bs_records' in json_data['uncertainty'].keys():
                label = 'bs_records'
            else:
                logging.error("Unknown json tag for bootstrap records", ValueError)
            if json_data['uncertainty'][label] is not None:
                result.uncertainty.bs_records = pd.read_json(json_data['uncertainty'][label])
            if ('rep_results' in json_data['uncertainty'].keys()) and json_data['uncertainty']['rep_results'] is not None:
                result.uncertainty.rep_results = pd.read_json(json_data['uncertainty']['rep_results'])
        if 'convergence' in json_data.keys():
            if json_data['convergence']['summary'] is not None:
                result.convergence.summary = pd.read_json(json_data['convergence']['summary'], typ='series')
            if 'record' in json_data['convergence'].keys():
                label = 'record'
            else:
                label = 'records'
            if json_data['convergence'][label] is not None:
                result.convergence.records = pd.read_json(json_data['convergence'][label])
        if 'data' in json_data.keys():
            if json_data['data']['x_data'] is not None:
                result.data.x_data = pd.read_json(json_data['data']['x_data'], typ='series')
            if json_data['data']['y_data'] is not None:
                result.data.y_data = pd.read_json(json_data['data']['y_data'], typ='series')
            if json_data['data']['sigma'] is not None:
                result.data.sigma = pd.read_json(json_data['data']['sigma'], typ='series')
            if json_data['data']['x_label'] is not None:
                    result.data.x_label = json_data['data']['x_label']
            if json_data['data']['y_label'] is not None:
                result.data.y_label = json_data['data']['y_label']

        elif data is not None:
            from ..utility.func_tools import AttrScope
            result.data = AttrScope(**data)

        return result

    def plot_fitting_curves(self, model=None, plot_on='bootstrap', subsample=20,
                            x_lim=(-0.00003, 0.002), y_lim=None,
                            x_label=None, y_label=None,
                            legend=False, legend_loc='upper left',
                            fontsize=12,
                            params=None, ax=None, **kwargs):
        """plot fitting results for Aminoacylation ribozyme fitting curves
        obj should be a FitResults instance
        """
        from ..utility.func_tools import update_none

        model = update_none(model, self.model)
        x_label, y_label = update_none(x_label, self.data.x_label), update_none(y_label, self.data.y_label)

        if model is None:
            from ..model.kinetic import BYOModel
            model = BYOModel.reacted_frac(broadcast=False)
        if params is None:
            from ..utility.func_tools import get_func_params
            params = get_func_params(model)[1:]

        if plot_on.lower() in ['bootstrap', 'bs']:
            param = self.uncertainty.bs_records[params]
            label = 'Bootstraps'
        elif plot_on.lower() in ['convergence', 'conv']:
            param = self.convergence.records[params]
            label = 'Convergence'
        else:
            param = None
            label = None

        ax = plot_tools.ax_none(ax, figsize=(4, 3))

        plot_tools.plot_curve(
            model=model,
            ax=ax,
            x=self.data.x_data, y=self.data.y_data,
            datapoint_kwargs=dict(color='#F58518'), datapoint_label='Observation',
            param=param, curve_kwargs=dict(color='#7F7F7F', alpha=0.3), curve_label=label,
            major_param=self.point_estimation.params[params],
            major_curve_kwargs=dict(color='#4C78A8'), major_curve_label='Point estimate',
            subsample=subsample,
            x_label=x_label, x_lim=x_lim,
            y_label=y_label, y_lim=y_lim,
            legend=legend, legend_loc=legend_loc, fontsize=fontsize, **kwargs
        )

    def plot_loss_heatmap(self, model=None, plot_on='bootstrap',
                          subsample=20,
                          param1_range=(1e-2, 1e4), param2_range=(1e-3, 1),
                          legend=False, legend_loc='upper left',
                          colorbar=True, resolution=101, fontsize=12,
                          param_name=None, add_lines=None, line_label=True, ax=None, **kwargs):
        """Plot the 2-D heatmap of loss function"""

        if model is None:
            from ..model import kinetic
            model = kinetic.BYOModel.reacted_frac(broadcast=True)

        if param_name is None:
            from ..utility.func_tools import get_func_params
            param_name = get_func_params(model)[1:]

        if plot_on.lower() in ['bootstrap', 'bs']:
            param = self.uncertainty.bs_records[param_name]
            label = 'Bootstraps'
        elif plot_on.lower() in ['convergence', 'conv']:
            param = self.convergence.records[param_name]
            label = 'Convergence'
        else:
            param = None
            label = None

        param = param

        ax = plot_tools.ax_none(ax, figsize=(4, 3))

        plot_tools.plot_loss_heatmap(
            model=model,
            x=self.data.x_data, y=self.data.y_data, param=param, subsample=subsample,
            param_name=param_name, param1_range=param1_range, param2_range=param2_range,
            param_log=True, resolution=resolution,
            fixed_params=None, z_log=True,
            datapoint_color='#E45756', datapoint_label='data', datapoint_kwargs=None,
            legend=legend, legend_loc=legend_loc, colorbar=colorbar, fontsize=fontsize,
            ax=ax, **kwargs
        )

        if add_lines is not None:

            xlims = ax.get_xlim()
            ylims = ax.set_ylim()

            xs = np.logspace(np.log10(param1_range[0]), np.log10(param1_range[1]), 50)
            for prod in add_lines:
                ax.plot(plot_tools.value_to_loc(xs, range=param1_range, resolution=resolution, log=True),
                        plot_tools.value_to_loc(prod / xs, range=param2_range, resolution=resolution, log=True),
                        'w', alpha=0.8, ls='--')
                if line_label:
                    ax.text(s=str(prod),
                            x=plot_tools.value_to_loc(prod / param2_range[1], range=param1_range,
                                                      resolution=resolution, log=True),
                            y=resolution, va='bottom', ha='center', fontsize=fontsize - 2)
            ax.set_xlim(*xlims)
            ax.set_ylim(*ylims)
