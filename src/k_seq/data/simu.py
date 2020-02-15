"""Module contains code to simulate data"""
from ..utility.log import logging
from ..utility.doc_helper import DocHelper
import numpy as np
import pandas as pd


# TODO: consider if keep DistGenerators
class DistGenerators:
    """A collection of random value generators from commonly used distributions.
    `uniq_seq_num` number of independent draw of distribution are returned

    Available distributions:
        lognormal
        uniform
        compo_lognormal
    """

    def __init__(self):
        pass

    @staticmethod
    def lognormal(size=None, loc=None, scale=None, c95=None, seed=None):
        """Sample from a log-normal distribution
        indicate with `loc` and `scale`, or `c95`

        Args:
            size (`int`): number of values to draw
            loc (`float`): center of log-normal distribution, default 0
            scale (`float`): log variance of the distribution, default 0
            c95 ([`float`, `float`]): 95% percentile of log-normal distribution
            seed: random seed

        Returns:
            a draw from distribution with given uniq_seq_num
        """

        if c95 is None:
            if loc is None:
                loc = 0
            if scale is None:
                scale = 0
        else:
            c95 = np.log(np.array(c95))
            loc = (c95[0] + c95[1]) / 2
            scale = (c95[1] - c95[0]) / 3.92

        if seed is not None:
            np.random.seed(seed)

        if size is None:
            return np.exp(np.random.normal(loc=loc, scale=scale))
        else:
            return np.exp(np.random.normal(loc=loc, scale=scale, size=size))

    @staticmethod
    def uniform(low=None, high=None, size=None, seed=None):
        """Sample from a uniform distribution"""

        if seed is not None:
            np.random.seed(seed)
        if size is None:
            return np.random.uniform(low=low, high=high)
        else:
            return np.random.uniform(low=low, high=high, size=size)

    @staticmethod
    def compo_lognormal(size, loc=None, scale=None, c95=None, seed=None):
        """Sample a pool composition from a log-normal distribution
        indicate with `loc` and `scale`, or `c95`

        Example:
            scale = 0 means an evenly distributed pool with all components have relative abundance 1/uniq_seq_num

        Args:
            size (`int`): uniq_seq_num of the pool
            loc (`float`): center of log-normal distribution
            scale (`float`): log variance of the distribution
            c95 ([`float`, `float`]): 95% percentile of log-normal distribution
            seed: random seed

        """

        if c95 is None:
            if loc is None or scale is None:
                raise ValueError('Please indicate loc/scale or c95')
        else:
            c95 = np.log(np.array(c95))
            loc = (c95[0] + c95[1]) / 2
            scale = (c95[1] - c95[0]) / 3.92
        if seed is not None:
            np.random.seed(seed)

        q = np.exp(np.random.normal(loc=loc, scale=scale, size=size))
        return q / np.sum(q)


simu_args = DocHelper(
    uniq_seq_num=('int', 'Number of unqiue sequences from simulation'),
    p0=('list-like, generator, or callable', 'reserved argument for initial pool composition (fraction)'),
    seed=('int', 'random seed for repeatability'),
    param_generators=('kwargs of list-like, generator, or callable', 'parameter generator depending on the model'),
    x_values=('list-like', 'list of controlled variables in each experiment setup,'
                           'negative value means it is an initial pool'),
    sample_reads=('int or list-like', 'Number of total reads for each sample'),
    kinetic_model=('callable', 'model the amount of sequences in reaction given input variables. '
                               'Default `BYOModel.amount_first_order`'),
    count_model=('callable', 'model the sequencing counts w.r.t. total reads and pool composition.'
                             'Default MultiNomial model.'),
    total_dna_error=('float or callable', 'float as the standard deviation for a fixed Gaussian error, '
                                          'or any error function on the DNA amount'),
    replace=('bool', 'if sample with replacement when sampling from a dataframe'),
    reps=('int', 'number of replicates for each condition in x_values'),
    save_to=('str', 'optional, path to save the simulation results with x, Y, truth csv file '
                    'and a pickled SeqTable object')

)

accepted_gen_type = """
Accepted parameter input:
  - list-like: if uniq_seq_num does not match as expected uniq_seq_num, resample with replacement
  - generator: given generator returns a random parameter
  - callable: if taking `uniq_seq_num` as an argument, needs to return a uniq_seq_num vector of sampled parameter or a
    generator to generate a uniq_seq_num vector; if not taking `uniq_seq_num` as an argument, needs to return single 
    sample"""


class PoolParamGenerator:
    """Functions to generate parameters for a set of sequence in a sequence pool

    Methods:
        - sample_from_iid_dist
        - sample_from_dataframe

    Returns:
        pd.DataFrame with columns of parameters and rows of simulated parameter for each sequence
    """

    @staticmethod
    def sample_from_iid_dist(uniq_seq_num, seed=None, **param_generators):
        f"""Simulate the seq parameters from individual draws of distributions

        Parameter:
          p0: initial fraction for each sequence for uneven pool
          depending on the model. e.g. first-order model needs to include k and A

        {accepted_gen_type}

        Args:
        {simu_args.get(['p0', 'uniq_seq_num', 'seed', 'param_generators'], indent=4)}

        Returns:
            a n_row = uniq_seq_num pd.DataFrame contains generated parameters
        """

        def generate_params(param_input):
            """Parse single distribution input and reformat as generated results
            """

            from types import GeneratorType

            if isinstance(param_input, (list, np.ndarray, pd.Series)):
                if len(param_input) == uniq_seq_num:
                    return param_input
                else:
                    logging.info('Size fo input param list and expected uniq_seq_num does not match, '
                                 'resample to given uniq_seq_num with replacement')
                    return np.random.choice(param_input, replace=True, size=uniq_seq_num)
            elif isinstance(param_input, GeneratorType):
                # assume only generate one realization
                return [next(param_input) for _ in range(uniq_seq_num)]
            elif callable(param_input):
                try:
                    # if there is a uniq_seq_num parameter to pass
                    param_output = param_input(size=uniq_seq_num)
                    if isinstance(param_output, (list, np.ndarray, pd.Series)):
                        return param_output
                    elif isinstance(param_output, GeneratorType):
                        return next(param_output)
                    else:
                        logging.error("Unknown input to draw a distribution value", error_type=TypeError)
                except TypeError:
                    # if can not pass uniq_seq_num, assume generate single samples
                    param_output = param_input()
                    if isinstance(param_output, GeneratorType):
                        return [next(param_output) for _ in range(uniq_seq_num)]
                    elif isinstance(param_output, (float, int)):
                        return [param_input() for _ in range(uniq_seq_num)]
                    else:
                        logging.error("Unknown callable return type for distribution",
                                      error_type=TypeError)
            else:
                logging.error("Unknown input to draw a distribution value", error_type=TypeError)

        if seed is not None:
            np.random.seed(seed)

        results = pd.DataFrame(data={**{param: list(generate_params(gen)) for param, gen in param_generators.items()}})

        if 'p0' in results.columns:
            results['p0'] = results['p0'] / results['p0'].sum()
        else:
            results['p0'] = np.repeat(1 / uniq_seq_num, repeats=uniq_seq_num)

        return results

    @classmethod
    def sample_from_dataframe(cls, df, uniq_seq_num, replace=True, weights=None, seed=None):
        f"""Simulate parameter by resampling rows of a given dataframe

        Args:
            df (pd.DataFrame): dataframe contains parameters as columns to sample from,
              needs to have `p0` as one column for heterogenous pool
            {simu_args.get(['uniq_seq_num'], indent=4)}
        """

        results = df.sample(n=int(uniq_seq_num), replace=replace, weights=weights, random_state=seed)
        if 'p0' in results.columns:
            results['p0'] = results['p0'] / results['p0'].sum()
        else:
            results['p0'] = np.repeat(1 / uniq_seq_num, repeats=uniq_seq_num)

        return results


def simulate_counts(uniq_seq_num, x_values, sample_reads, p0=None,
                    kinetic_model=None, count_model=None, total_dna_error=None,
                    param_sample_from_df=None, weights=None, replace=True,
                    reps=1, seed=None, note=None,
                    save_to=None, **param_generator):
    f"""Simulate count dataset given kinetic and count model

    Procedure:
      1. parameter for each unique sequences were sampled from param_sample_from_df and kwargs
        (param_generators). It is an even pool if p0 is not provided. No repeated parameters.
      2. simulate the reacted amount / fraction of sequences with each controlled variable in x_values
      3. Simulated counts with given total sample_reads were simulated for input pool and reacted pools.

    Args:
    {simu_args.get(['uniq_seq_num', 'x_values', 'sample_reads', 'p0', 'kinetic_model',
                    'count_model'])}
        param_sample_from_df (pd.DataFrame): optional to sample sequences from given table
        weights (list or str): weights/col of weight for sampling from table
    {simu_args.get(['total_dna_error', 'reps', 'seed', 'save_to', 'param_generator'])}

    Returns:
        X (pd.DataFrame): c, n value for samples
        y (pd.DataFrame): sequence counts for sequence samples
        param_table (pd.DataFrame): table list the parameters of simulated pool
        seq_table (data.SeqTable): a SeqTable object stores all the data
    """

    from ..model import pool

    if seed is not None:
        np.random.seed(seed)

    if kinetic_model is None:
        # default use BYO first-order model returns absolute amount
        from ..model import kinetic
        kinetic_model = kinetic.BYOModel.amount_first_order
        logging.info('No kinetic model provided, use BYOModel.amount_first_order')
    if count_model is None:
        # default use MultiNomial
        from ..model import count
        count_model = count.MultiNomial
        logging.info('No count model provided, use MultiNomial')

    # compose sequence parameter from
    # 1. p0
    # 2. param_generator
    # 3. param_sample_from_df
    param_table = pd.DataFrame(index=np.arange(uniq_seq_num))
    if p0 is not None:
        param_table['p0'] = PoolParamGenerator.sample_from_iid_dist(p0=p0,
                                                                    uniq_seq_num=uniq_seq_num)['p0']
    if param_generator != {}:
        temp_table = PoolParamGenerator.sample_from_iid_dist(uniq_seq_num=uniq_seq_num,
                                                             **param_generator)
        col_name = temp_table.index[~temp_table.index.isin(param_table.index)]
        param_table[col_name] = temp_table[col_name]

    if param_sample_from_df is not None:
        temp_table = PoolParamGenerator.sample_from_dataframe(
            df=param_sample_from_df,
            uniq_seq_num=uniq_seq_num,
            replace=replace,
            weights=weights
        )
        col_name = temp_table.index[~temp_table.index.isin(param_table.index)]
        param_table[col_name] = temp_table[col_name]
    param_table.index.name = 'seq'

    # get pool model
    pool_model = pool.PoolModel(count_model=count_model,
                                kinetic_model=kinetic_model,
                                param_table=param_table)
    x = {}
    Y = {}
    dna_amount = {}
    for sample_ix, (c, n) in enumerate(zip(x_values, sample_reads)):
        if reps is None or reps == 1:
            dna_amount[f"s{sample_ix}"], Y[f"s{sample_ix}"] = pool_model.predict(c=c, N=n)
            x[f"s{sample_ix}"] = {'c': c, 'n': n}
        else:
            for rep in range(reps):
                dna_amount[f"s{sample_ix}-{rep}"], Y[f"s{sample_ix}-{rep}"] = pool_model.predict(c=c, N=n)
                x[f"s{sample_ix}-{rep}"] = {'c': c, 'n': n}
    # return x, Y, dna_amount, param_table
    x = pd.DataFrame.from_dict(x, orient='columns')
    Y = pd.DataFrame.from_dict(Y, orient='columns')
    dna_amount = pd.Series(dna_amount)
    if isinstance(dna_amount_error, float):
        dna_amount += np.random.normal(loc=0, scale=dna_amount_error, size=len(dna_amount))
    elif callable(dna_amount_error):
        dna_amount = dna_amount.apply(dna_amount_error)
    x.index.name = 'param'
    Y.index.name = 'seq'
    dna_amount.index.name = 'amount'

    from .seq_table import SeqTable

    input_samples = x.loc['c']
    input_samples = list(input_samples[input_samples < 0].index)
    seq_table = SeqTable(data_mtx=Y, x_values=x.loc['c'].to_dict(), note=note,
                         grouper={'input': input_samples,
                                  'reacted': [sample for sample in x.columns if sample not in input_samples]})
    seq_table.add_total_dna_amount(dna_amount=dna_amount.to_dict())
    seq_table.table_abs_amnt = seq_table.dna_amount.apply(target=seq_table.table)
    from .transform import ReactedFractionNormalizer
    reacted_frac = ReactedFractionNormalizer(input_samples=input_samples,
                                             reduce_method='median',
                                             remove_zero=True)
    seq_table.table_reacted_frac = reacted_frac.apply(seq_table.table_abs_amnt)
    from .filters import DetectedTimesFilter
    seq_table.table_seq_in_all_smpl_reacted_frac = DetectedTimesFilter(
        min_detected_times=seq_table.table_reacted_frac.shape[1]
    )(seq_table.table_reacted_frac)

    if save_to is not None:
        from pathlib import Path
        save_path = Path(save_to)
        if save_path.suffix == '':
            save_path.mkdir(parents=True, exist_ok=True)
            dna_amount.to_csv(f'{save_path}/dna_amount.csv')
            x.to_csv(f'{save_path}/x.csv')
            Y.to_csv(f'{save_path}/Y.csv')
            param_table.to_csv(f'{save_path}/truth.csv')
            seq_table.to_pickle(f"{save_path}/seq_table.pkl")
        else:
            logging.error('save_to should be a directory')
            raise TypeError('save_to should be a directory')

    return x, Y, dna_amount, param_table, seq_table


def simulate_from_distribution(seq_num, depth, p0_loc, p0_scale, k_95, dna_amount_error, save_to=None):
    """
    Preset simulation of pool dataset from random variables
    TODO: add description
    """

    c_list = [-1] + list(np.repeat(
        np.expand_dims([2e-6, 10e-6, 50e-6, 250e-6, 1250e-6], -1), 3
    ))

    N_list = [seq_num * depth if c >= 0 else seq_num * depth * 3 for c in c_list]

    x, Y, dna_amount, truth, seq_table = simulate_counts(
        uniq_seq_num=seq_num,
        x_values=c_list,
        sample_reads=N_list,
        p0=DistGenerators.compo_lognormal(loc=p0_loc, scale=p0_scale, size=seq_num),
        k=DistGenerators.lognormal(c95=k_95, size=seq_num),
        A=DistGenerators.uniform(low=0, high=1, size=seq_num),
        dna_amount_error=dna_amount_error,
        reps=1,
        save_to=save_to,
        seed=23
    )

    if save_to:
        with open(save_to + '/config.txt', 'w') as handle:
            handle.write(
                f'uniq_seq_num: {seq_num}\ndepth: {depth}\np0: loc:{p0_loc} scale: {p0_scale}\n'
                f'k_95: {k_95}\ndna_amount_error:{dna_amount_error}'
            )

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 4, figsize=(16, 3))
    init_pools = Y.loc[:, x.loc['c'] < 0]
    p0 = (init_pools / init_pools.sum(axis=0)).sum(axis=1)
    axes[0].hist(p0, bins=20)
    axes[0].set_xlabel('p0, init count avg', fontsize=14)
    axes[1].hist(truth.A, bins=20)
    axes[1].set_xlabel('a', fontsize=14)
    bins = np.logspace(np.log10(truth.k.min()) - 0.5, np.log10(truth.k.max()) + 0.5, 20)
    axes[2].hist(truth.k, bins=bins)
    axes[2].set_xscale('log')
    axes[2].set_xlabel('k', fontsize=14)
    ka = truth.k * truth.A
    bins = np.logspace(np.log10(ka.min()) - 0.5, np.log10(ka.max()) + 0.5, 20)
    axes[3].hist(ka, bins=bins)
    axes[3].set_xscale('log')
    axes[3].set_xlabel('k * a', fontsize=14)
    plt.show()

    return x, Y, dna_amount, truth, seq_table


def dna_amount_error(amount):
    """For DNA amount, assign a 10 % Gaussian error"""

    return amount + np.random.normal(scale=amount * 0.1)


def get_sample_table(seq_table, estimation):
    """Compose table for simulation by sampling from seq_table (for p0) and estimated results (for k, A)
    """
    from ..estimator.least_square import load_estimation_results

    from .seq_table import SeqTable

    if isinstance(seq_table, str):
        from pathlib import Path
        if Path(seq_table).exists():
            from ..utility.file_tools import read_pickle
            seq_table = read_pickle(seq_table)
        else:
            seq_table = SeqTable.load_dataset(dataset=seq_table)
    if isinstance(estimation, str):
        estimation = pd.read_csv(estimation, index_col=0)

    # survey initial pool composition from byo_doped and add to ls_point_est
    if hasattr(seq_table.grouper, 'input'):
        inputs = seq_table.grouper.input.group
    else:
        inputs = ['R0']  # default
    counts = seq_table.table[inputs].loc[estimation.index]
    counts = counts.sparse.to_dense().mean(axis=1)
    estimation['mean_counts'] = counts
    estimation['p0'] = counts / counts.sum()
    estimation = estimation[~estimation.isna().any(axis=1)]
    estimation['ka'] = estimation['k'] * estimation['A']
    return estimation[['k', 'A', 'p0', 'ka']]


def simulate_from_sample(sample_table, seq_num, depth=40, dna_amount_error=None, plot_dist=False, save_to=None):
    """Simulate k-seq count results from given """

    c_list = [-1] + list(np.repeat(
        np.expand_dims([2e-6, 10e-6, 50e-6, 250e-6, 1250e-6], -1), 3
    ))

    N_list = [seq_num * depth if c >= 0 else seq_num * depth * 3 for c in c_list]

    x, Y, dna_amount, truth, seq_table = simulate_counts(
        uniq_seq_num=seq_num,
        x_values=c_list,
        sample_reads=N_list,
        param_sample_from_df=sample_table,
        dna_amount_error=dna_amount_error,
        weights=None,
        replace=True,
        reps=1,
        save_to=save_to,
        seed=23
    )

    if save_to is not None:
        with open(save_to + '/config.txt', 'w') as handle:
            handle.write(f'uniq_seq_num: {seq_num}\ndepth: {depth}\n')

    init_pools = Y.loc[:, x.loc['c'] < 0]
    truth['p0_from_counts'] = (init_pools / init_pools.sum(axis=0)).sum(axis=1)
    truth['ka'] = truth.k * truth.A

    if plot_dist:
        from ..utility.plot_tools import pairplot
        pairplot(data=truth, vars_name=['p0', 'A', 'k', 'ka'],
                 vars_log=[True, False, True, True], diag_kind='kde')

    return x, Y, dna_amount, truth, seq_table



# def reacted_frac_simulator(x_values, kinetic_model=None, percent_noise=0.2, uniq_seq_num=None,
#                            param_sample_from_df=None, weights=None, replace=True,
#                            reps=1, allow_zero=False, seed=None, save_to=None, **param_generator):
#     """Simulate reacted fraction of a pool of molecules (ribozymes), given substrate concentration, kinetic model
#
#     Args:
#         x_values (list): list of substrate concentration
#         kinetic_model (callable): kinetic model of the reaction
#         percent_noise (float or list): percent variance of Gaussian noise, if list, should have same shape as x_values,
#             default: 0.2
#         param_sample_from_df (pd.DataFrame): optional to sample sequences from given table
#         weights (list or str): weights/col of weight for sampling from table
#         replace (bool): if sample with replacement
#         reps (int): number of replicates for each c, N
#         allow_zero (bool): if allow reacted fraction to be zero after noise. If False, repeated sampling until a
#             positive reacted fraction is achieved, else bottomed by zero
#         seed (int): global random seed to use
#         save_to (path): path to the folder to save simulated results
#         **param_generator: keyword arguments of list, generator or callable returns generator to draw parameters
#
#     Returns:
#         x (pd.Series): x_values with replication
#         Y (pd.DataFrame): a table of reacted fraction
#         param_table (pd.DataFrame): a table of parameter truth
#     """
#
#     def add_noise(mean, noise, allow_zero=False):
#         """Add Gaussian noise on given mean
#         Note:
#             here is absolute noise, to inject percent noise, assign noise = mean * pct_noise
#
#         Args:
#             mean (float or list-like): mean values
#             noise (float or list-list): noise level, variance of Gaussian noise,
#                 if list-like should have same shape as mean
#             allow_zero (bool): if allow zero in noised inject data, if False, repeated sampling until non-negative value
#                 observed
#
#         Returns:
#             data_w_noise (float or np.ndarray): data with injected noise, same shape as mean
#         """
#         import numpy as np
#
#         y = np.random.normal(loc=mean, scale=noise)
#         if isinstance(mean, float):
#             while y < 0 and not allow_zero:
#                 y = np.random.normal(loc=y, scale=y_noise)
#             return max(y, 0)
#         else:
#             while (y < 0).any() and not allow_zero:
#                 y = np.random.normal(loc=y, scale=y_noise)
#             y[y < 0] = 0
#             return y
#
#     if kinetic_model is None:
#         # default use BYO first-order compositional model
#         from k_seq.model import kinetic
#         kinetic_model = kinetic.BYOModel.react_frac
#         print('No kinetic model provided, use BYOModel.amount_first_order')
#
#     if param_sample_from_df is None:
#
#         results = pd.DataFrame(
#             data={**{'p0': list(generate_params(p0))},
#                   **{param: generate_params(gen) for param, gen in param_generators.items()}}
#         )
#
#         return  results
#
#         param_table = sample_from_ind_dist(
#             seed=seed,
#             **param_generator
#         )
#     else:
#         param_table =
#             df=param_sample_from_df,
#             uniq_seq_num=uniq_seq_num,
#             replace=replace,
#             weights=weights,
#             seed=seed
#         )
#
#     param_table.index.name = 'seq'
#
#     x_true = np.array(x_true)
#
#
#     if isinstance(params, list):
#         y_true = model(x_true, *params.values())
#     elif isinstance(params, dict):
#         y_true = model(x_true, **params)
#
#     if type(percent_noise) is float or type(percent_noise) is int:
#         y_noise = [percent_noise * y for y in y_true]
#     else:
#         y_noise = [tmp[0] * tmp[1] for tmp in zip(y_true, percent_noise)]
#
#     y_ = np.array([[add_noise(yt[0], yt[1], y_allow_zero) for yt in zip(y_true, y_noise)] for _ in range(replicates)])
#     if average:
#         return (x_true, np.mean(y_, axis=0))
#     else:
#         x_ = np.array([x_true for _ in range(replicates)])
#         return (x_.reshape(x_.shape[0] * x_.shape[1]), y_.reshape(y_.shape[0] * y_.shape[1]))
#
#
# def data_simulator_convergence_map(A_range, k_range, x, save_dir=None, percent_noise=0.0, func=func_default, replicates=5, A_res=100, k_res=100, A_log=False, k_log=True):
#     """
#
#     :param A_range: param k_range:
#     :param x: param save_dir:  (Default value = None)
#     :param percent_noise: Default value = 0.0)
#     :param func: Default value = func_default)
#     :param replicates: Default value = 5)
#     :param A_res: Default value = 100)
#     :param k_res: Default value = 100)
#     :param A_log: Default value = False)
#     :param k_log: Default value = True)
#     :param k_range:
#     :param save_dir:  (Default value = None)
#
#     """
#
#     if A_log:
#         A_values = np.logspace(np.log10(A_range[0]), np.log10(A_range[1]), A_res)
#     else:
#         A_values = np.linspace(A_range[0], A_range[1], A_res+1)[1:] # avoid A=0
#     if k_log:
#         k_values = np.logspace(np.log10(k_range[0]), np.log10(k_range[0]), k_res)
#     else:
#         k_values = np.linspace(k_range[0], k_range[1], k_res)
#
#     data_tensor = np.zeros((A_res, k_res, replicates, len(x)))
#     for A_ix in range(A_res):
#         for k_ix in range(k_res):
#             for rep in range(replicates):
#                 data_tensor[A_ix, k_ix, rep, :] = y_value_simulator(
#                     params=[A_values[A_ix], k_values[k_ix]],
#                     x_true=x,
#                     func=func,
#                     percent_noise=percent_noise,
#                     y_allow_zero=False,
#                     average=False
#                 )[1]
#     dataset_to_dump = {
#         'x': x,
#         'y_tensor': data_tensor
#     }
#     # if save_dir:
#     #     util.dump_pickle(dataset_to_dump, save_dir,
#     #                      log='Simulated dataset for convergence map of k ({}), A ({}), with x:{} and percent_noise:{}'.format(k_range, A_range, x, percent_noise),
#     #                      overwrite=True)
#     return dataset_to_dum

# def count_simulator(model, params, repeat=1, seed=None):
#     """Function to simulate a pool count with different parameters
#
#     Args:
#         model:
#         params:
#         repeat:
#         seed:
#
#     Returns:
#         pd.DataFrame contains counts table
#
#     """
#     import numpy as np
#     import pandas as pd
#
#     def run_model(param):
#         if isinstance(param, dict):
#             return model(**param)
#         elif isinstance(param, (list, tuple)):
#             return model(*param)
#         else:
#             return model(param)
#
#     # first parse params
#     if isinstance(params, list):
#         params = {f'sample_{int(idx)}': param for idx, param in enumerate(params)}
#
#     if seed is not None:
#         np.random.seed(seed)
#
#     result = {}   # {sample_name: counts}
#     for sample, param in params.items():
#         if repeat is None or repeat == 1:
#             result[sample] = run_model(param)
#         else:
#             for rep in range(repeat):
#                 result[f"{sample}-{rep}"] = run_model(param)
#     return pd.DataFrame.from_dict(result, orient='columns')
#
#
# class CountSimulator(object):
#     """Simulate pool counts given parameters (e.g. p0, k, A), and simulate counts for a given x values
#     """
#
#     def __init__(self, count_model, kinetic_model, count_params=None, kinetic_params=None,
#                  x_values=None, seed=None):
#         """Initialize a simulator with parameter table, count model, and parameters
#
#         Args:
#
#
#             kinetic_model (`Model` or callable): pool kinetic model, whose output is a list of abundance of pool members
#
#             kin_param (`dict`): contains parameter needed for
#
#             c_param:
#
#             c_model:
#             seed:
#         """
#         import numpy as np
#
#         self.k_model = k_model
#         self.k_param = k_param
#         self.c_model = c_model
#         self.c_param = c_param
#         self.seed = seed
#         if seed is not None:
#             np.random.seed(seed)
#
#     def get_data(self, k_param=None, c_param=None, N=1, seed=None):
#         """Return a uniq_seq_num N data for each param set in k_param
#
#         Return: a dict or list of dict of
#             {'data': pd.DataFrame (sparse) of data,
#              'config':
#         """
#
#         def get_one_data(k_param, c_param):
#             comp = self.k_model(**k_param)
#             if np.sum(comp) != 1:
#                 comp = comp / np.sum(comp)
#             return self.c_model(comp, **c_param)
#
#         def get_one_config(k_param, c_param, N):
#             k_p = self.k_param.copy()
#             k_p.update(k_param)
#             c_p = self.c_param.copy()
#             c_p.update(c_param)
#
#             import pandas as pd
#
#             return {'data': pd.DataFrame(pd.SparseArray([get_one_data(k_p, c_p) for _ in range(N)]), dtype=int),
#                     'config': {'k_param': k_p, 'c_param': c_p}}
#
#         import numpy as np
#         if seed is not None:
#             np.random.seed(seed)
#
#         results = []
#
#     def to_pickle(self):
#         pass
#
#     def to_DataFrame(self):
#         pass
#
#     def to_csv(self):
#         pass



