#!/usr/bin/python3
import sys
import logging


def kA(params):
    return params[0] * params[1]


def read_table(seq_table=None, table_name=None, simu_data=None, fit_partial=-1, inverse_weight=False):
    """Parse data table source SeqTable or a Simu Folder

    Args:
        seq_table (str): path to a SeqTable instance with x_value
        table_name (str): the table to use in SeqTable

    Returns:
        work_table (pd.DataFrame): the work table contains sequences to fit
        x_data (list): list of x values (BYO concentration), same order as samples in work_table
    """
    from k_seq.utility.file_tools import read_pickle

    if seq_table is not None:
        # input is seq_table
        seq_table = read_pickle(seq_table)
        count_table = seq_table.table
        work_table = getattr(seq_table, table_name)
        work_table = work_table.loc[work_table.sum(axis=1).sort_values(ascending=False).index]
        x_data = seq_table.x_values[work_table.columns]
    elif simu_data is not None:
        # input is simu data folder
        import pandas as pd
        count_table = pd.read_csv(simu_data + '/Y.csv', index_col='seq')
        x_data = pd.read_csv(simu_data + '/x.csv', index_col='param').loc['c']
        input_samples = list(x_data[x_data < 0].index)
        reacted_samples = list(x_data[x_data >= 0].index)
        total_dna = pd.read_csv(simu_data + 'dna_amount.csv', header=None, index_col=0)[1]
        amount_table = (count_table / count_table.sum(axis=0) * total_dna)
        input_base = amount_table[input_samples].median(axis=1)
        work_table = amount_table[input_base > 0][reacted_samples].divide(input_base[input_base > 0], axis=0)
        work_table = work_table.loc[work_table.sum(axis=1).sort_values(ascending=False).index]
        work_table = work_table[work_table.sum(axis=1) > 0]
    else:
        raise ValueError('Indicate seq_table or simu_data')

    if fit_partial > 0:
        work_table = work_table.iloc[:fit_partial]

    if inverse_weight is True:
        sigma = count_table.loc[work_table.index, work_table.columns]
        sigma = sigma + 0.5
    else:
        sigma = None

    return work_table, x_data, sigma


def create_output_dir(seq_table=None, table_name=None, simu_data=None, fit_partial=-1, exclude_zero=False,
                      inverse_weight=False, bootstrap_num=None, bs_record_num=None, bs_method='data', core_num=1,
                      output_dir=None, pkg_path=None, **kwargs):
    """Create the output dir and logging/config files
    Logic:
    """

    from pathlib import Path
    if Path(output_dir).is_dir():
        if fit_partial <= 0:
            name = f'bs-{int(bootstrap_num)}_mtd-{bs_method}_no-zero-{exclude_zero}_' \
                   f'inv-weight-{inverse_weight}_core-{core_num}/'
        else:
            name = f'first-{int(fit_partial)}_bs-{int(bootstrap_num)}_mtd-{bs_method}_no-zero-{exclude_zero}_' \
                   f'inv-weight-{inverse_weight}_core-{core_num}/'
        output_dir = Path(f'{output_dir}/{name}')
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    return str(output_dir)


def main(seq_table=None, table_name=None, simu_data=None, fit_partial=-1, exclude_zero=False, inverse_weight=False,
         bootstrap_num=None, bs_record_num=None, bs_method='data', core_num=1, deduplicate=False, output_dir=None,
         stream=False, overwrite=False,
         **kwargs):

    from k_seq.estimator.least_square import BatchFitter
    from k_seq.model.kinetic import BYOModel
    import numpy as np

    work_table, x_data, sigma = read_table(seq_table=seq_table, table_name=table_name, simu_data=simu_data,
                                           fit_partial=fit_partial, inverse_weight=inverse_weight)
    if bs_method.lower() == 'stratified':
        try:
            grouper = seq_table.grouper.byo.group
        except:
            raise ValueError('Can not find grouper for stratified bootstrapping')
    else:
        grouper = None

    logging.info(f'exclude_zero: {exclude_zero}')
    logging.info(f'inverse_weight: {inverse_weight}')
    logging.info(f'deduplicate: {deduplicate}')
    batch_fitter = BatchFitter(
        y_data_batch=work_table, x_data=x_data, sigma=sigma, bounds=[[0, 0], [np.inf, 1]], metrics={'kA': kA},
        model=BYOModel.func_react_frac, exclude_zero=exclude_zero, grouper=grouper,
        bootstrap_num=bootstrap_num, bs_record_num=bs_record_num, bs_method=bs_method,
    )
    stream_to_disk = f"{output_dir}/results" if stream else None
    batch_fitter.fit(deduplicate=deduplicate, parallel_cores=core_num,
                     stream_to_disk=stream_to_disk, overwrite=overwrite)

    batch_fitter.summary(save_to=f'{output_dir}/fit_summary.csv')
    if stream:
        batch_fitter.save_model(output_dir=output_dir, results=True, bs_results=False, sep_files=True, tables=True)
    else:
        batch_fitter.save_model(output_dir=output_dir, results=True, bs_results=True, sep_files=True, tables=True)


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description='Least-squares kinetic model fitting')
    parser.add_argument('--pkg_path', type=str, default=None,
                        help='Path to customize k-seq package')
    parser.add_argument('--simu_data', type=str,
                        help='Path to folder of simulated data')
    parser.add_argument('--seq_table', '-T', type=str,
                        help='Path to input seq_table object')
    parser.add_argument('--table_name', '-t', type=str,
                        help='table name in seq_table to use')
    parser.add_argument('--fit_partial', '-p', type=int, default=-1,
                        help='Select top p sequences to fit, fit all seq if p is negative')
    parser.add_argument('--exclude_zero', dest='exclude_zero', default=False, action='store_true',
                        help='If exclude zero data in fitting')
    parser.add_argument('--inverse_weight', dest='inverse_weight', default=False, action='store_true',
                        help='Apply counts (pseudo counts 0.5) as the sigma in fitting')
    parser.add_argument('--bootstrap_num', '-n', type=int, default=0,
                        help='Number of bootstraps to perform')
    parser.add_argument('--bs_record_num', '-r', type=int, default=-1,
                        help='Number of bootstrap results to save, save all if negative')
    parser.add_argument('--bs_method', '-m', choices=['pct_res', 'data', 'stratified'], default='pct_res',
                        help='Bootstrap method')
    parser.add_argument('--deduplicate', dest='deduplicate', default=False, action='store_true',
                        help='If deduplicate seq with same data')
    parser.add_argument('--stream-results', dest='stream', default=False, action='store_true',
                        help="If stream fitting results to disk")
    parser.add_argument('--overwrite', dest='overwrite', default=False, action='store_true',
                        help="If overwrite results when streaming")
    parser.add_argument('--create-folder', dest='create_folder', default=False, action='store_true',
                        help="If create subfolder with specs as name under the output_dir")
    parser.add_argument('--core_num', '-c', dest='core_num', type=int, help='Number of process to use in parallel')
    parser.add_argument('--output_dir', '-o', type=str, default='./')

    return vars(parser.parse_args())


if __name__ == '__main__':

    args = parse_args()
    if args['pkg_path'] not in sys.path:
        sys.path.insert(0, args['pkg_path'])
    if args['create_folder']:
        args['output_dir'] = create_output_dir(**args)
    from k_seq.utility.file_tools import dump_json
    dump_json(obj=args, path=f"{args['output_dir']}/config.json")
    logging.basicConfig(filename=f"{args['output_dir']}/app_run.log",
                        format='%(asctime)s %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p',
                        level=logging.INFO,
                        filemode='w')
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    from k_seq.utility.log import Timer
    with Timer():
        sys.exit(main(**args))
