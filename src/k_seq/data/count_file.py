"""Module to parse, convert, characterize count files.

Read directly from count file function was added to `data.SeqTable` thus this module is no long required in processing
count files
TODO:
  - clean up this module (after done with other data modules)
"""


def load_Seqtable_from_count_files(cls,
                                   file_root, file_list=None, pattern_filter=None, black_list=None, name_pattern=None, sort_by=None,
                     x_values=None, x_unit=None, input_sample_name=None, sample_metadata=None, note=None,
                     silent=True, dry_run=False, **kwargs):
    """todo: implement the method to generate directly from count files"""
    from ..utility.file_tools import get_file_list, extract_metadata
    import numpy as np
    import pandas as pd

    # parse file metadata
    file_list = get_file_list(file_root=file_root, file_list=file_list,
                              pattern=pattern_filter, black_list=black_list, full_path=True)
    if name_pattern is None:
        samples = {file.name: {'file_path': str(file), 'name':file.name} for file in file_list}
    else:
        samples = {}
        for file in file_list:
            f_meta = extract_metadata(target=file.name, pattern=name_pattern)
            samples[f_meta['name']] = {**f_meta, **{'file_path': str(file)}}
    if sample_metadata is not None:
        for file_name, f_meta in sample_metadata.items():
            samples[file_name].udpate(f_meta)

    # sort file order if applicable
    sample_names = list(samples.keys())
    if sort_by is not None:
        if isinstance(sort_by, str):
            def sort_fn(sample_name):
                return samples[sample_name].get(sort_by, np.nan)
        elif callable(sort_by):
            sort_fn = sort_by
        else:
            raise TypeError('Unknown sort_by format')
        sample_names = sorted(sample_names, key=sort_fn)

    if dry_run:
        return pd.DataFrame(samples)[sample_names].transpose()

    from ..data.count_file import read_count_file
    data_mtx = {sample: read_count_file(file_path=samples[sample]['file_path'], as_dict=True)[2]
                for sample in sample_names}
    data_mtx = pd.DataFrame.from_dict(data_mtx).fillna(0, inplace=False).astype(pd.SparseDtype(dtype='int'))
    if input_sample_name is not None:
        grouper = {'input': [name for name in sample_names if name in input_sample_name],
                   'reacted': [name for name in sample_names if name not in input_sample_name]}
    else:
        grouper = None

    seq_table = cls(data_mtx, data_unit='count', grouper=grouper, sample_metadata=sample_metadata,
                    x_values=x_values, x_unit=x_unit, note=note, silent=silent)

    if 'spike_in_seq' in kwargs.keys():
        seq_table.add_spike_in(**kwargs)

    if 'total_amounts' in kwargs.keys():
        seq_table.add_sample_total_amounts(**kwargs)

    return seq_table
