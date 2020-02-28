"""Grouper slice tables into pre-defined groups. E.g. input samples, reacted samples, different concentrations
"""

from .seq_table import slice_table
from yutility import logging

# TODO: formalize grouper to allow (1) apply same grouper to different name, (2) return a generator of groups


class Grouper(object):
    """Grouper of samples/sequences

    Two types of grouper accepted:
        Type 0: initialize with group as list-like. This defines a single set of samples/sequences
        Type 1: initialzed with group as dict. This defines a collection of groups of samples/sequences


    Attributes:
        target (pd.DataFrame): accessor for table to group
        axis (0 or 1): axis to apply grouping (0 for index, 1 for columns)
        group (list or dict): dictionary with structure {group_name: group_members}
        type (0 or 1): type of the grouper
    """

    def __repr__(self):
        if self.type == 0:
            return f'Group: {self.group}'
        else:
            return f'Groups on:\n' + '\n'.join(f'{key}: {list(value)}' for key, value in self.group.items())

    def __init__(self, group, target=None, axis=1):
        import numpy as np
        import pandas as pd

        if isinstance(group, (list, np.ndarray, pd.Series, str)):
            self.type = 0
            self.group = list(group)
        elif isinstance(group, dict):
            self.type = 1
            self.group = {key: list(members) for key, members in group.items()}
        else:
            logging.error('group should be list-like or dictionary')
        self.target = target
        self.axis = axis

    def __call__(self, target=None, axis=1, group=None, remove_zero=False):
        """Call self.get_table"""
        return self.get_table(group=group, target=target, axis=axis, remove_zero=remove_zero)

    def __iter__(self):
        """Group iterator to return a generator of subtables"""
        if self.target is None:
            logging.error('self.target is None, please assign before iteration', error_type=ValueError)

        if self.type == 0:
            if self.axis == 0:
                return (self.target.loc[ix] for ix in self.group)
            else:
                return (self.target[ix] for ix in self.group)
        else:
            return (self.get_table(group) for group in self.group.keys())

    def __getitem__(self, group=None):
        """Index-like access to return a sub-table with indicated group name; type 1 table will just return the subtable"""
        return self.get_table(group=group)

    def get_table(self, group=None, target=None, axis=None, remove_zero=False):
        """Return a sub-table from target given group"""
        if target is None:
            target = self.target
        if target is None:
            logging.error("Please indicate target table to group")
        if axis is None:
            axis = self.axis
        if self.type == 0:
            # ignore group argument
            return slice_table(table=target, keys=self.group, axis=axis, remove_zero=remove_zero)
        else:
            if group is None:
                logging.error('Please indicate the group')
            return slice_table(table=target, keys=self.group[group], axis=axis, remove_zero=remove_zero)

    def split(self, target=None, remove_zero=False):
        if target is None:
            target = self.target
        if target is None:
            logging.error("Please indicate target table to group")
        if self.type == 0:
            return self.get_table(target=target, remove_zero=remove_zero)
        else:
            return {group: self.get_table(target=target, group=group, remove_zero=remove_zero)
                    for group in self.group.keys()}

