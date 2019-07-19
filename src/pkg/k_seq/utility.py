"""
This module contains project level utility functions
"""


class PlotPreset:

    def __init__(self):
        pass

    @staticmethod
    def colors(num=5):
        from math import ceil

        full_color_list = ['#FC820D', '#2C73B4', '#1C7725', '#B2112A', '#70C7C7', '#810080', '#AEAEAE']
        color_list = []
        for i in range(ceil(num/7)):
            color_list += full_color_list
        return color_list[:num]

    @staticmethod
    def markers(num=5, with_line=False):
        from math import ceil

        full_marker_list = ['o', '^', 's', '+', 'x', 'D', 'v', '1', 'p', 'H']
        marker_list = []
        for i in range(ceil(num/10)):
            marker_list += full_marker_list
        if with_line:
            return ['-' + marker for marker in marker_list[:num]]
        else:
            return marker_list[:num]


class color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def blue_header(header):
    print(color.BOLD + color.BLUE + header + color.END)

def get_args_params(func, exclude_x=True):
    """
    Utility function to get the number of arguments for a function (callable)
    Args:
        func (`callable`): the function
        exclude_x (`bool`): if exclude the first argument (usually `x`)

    Returns: a tuple of arguments name in order

    """
    from inspect import signature
    arg_tuple = tuple(signature(func).parameters.keys())
    if exclude_x:
        return arg_tuple[1:]
    else:
        return arg_tuple


class FunctionWrapper:

    @staticmethod
    def _wrap_function(func, data):
        from functools import partial, update_wrapper
        wrapped = partial(func, data)
        update_wrapper(wrapped, func)
        return wrapped

    def __init__(self, data, functions):
        if callable(functions):
            functions = [functions]

        from functools import partial, update_wrapper

        self.__dict__.update({
            func.__name__: self._wrap_function(func, data) for func in functions
        })


class Logger:

    def __init__(self):
        import pandas as pd
        self.log = pd.DataFrame(columns=['Timestamp', 'Message'])
        self.log.set_index(['Timestamp'], inplace=True)

    def add_log(self, message):
        from datetime import datetime
        self.log.loc[datetime.now()] = [message]


def get_file_list(file_root, pattern=None):
    """list all files under the given file root, folders are not included

    Args:
        file_root (str): root directory

        pattern (str): optional, only include the files with the substring

        full_directory (bool): return full directory instead of name if True

    Returns:
        list of str: list of file names/full directory
    """

    import glob
    from pathlib import Path

    if not pattern:
        pattern = ''
    if full_directory:
        file_list = [file_name for file_name in glob.glob("{}/*{}*".format(file_root, pattern)) if not '@' in file_name]
    else:
        file_list = [file_name[file_name.rfind('/')+1:]
                     for file_name in glob.glob("{}/*{}*".format(file_root, pattern))
                     if not '@' in file_name]
    file_list.sort()
    return file_list


def extract_metadata(target, pattern):
    """Function to extract metadata info from target given pattern

    Args:

        target (str): string to extract info from, e.g. sample file name

        pattern (str): string indicate the method to extract metadata. Use ``[...]`` to include the region of sample_name,
          use ``{domain_name[, int/float]}`` to indicate region of domain to extract as metadata, including
          ``[,int/float]`` will convert the domain value to float in applicable, otherwise, string

    Return:

        dict: dictionary of all metadata extracted from domains indicated in ``pattern``

    Example:
        Example on metadata extraction from pattern:

        >>> extract_metadata(
                sample_name = "R4B-1250A_S16_counts.txt"
                pattern = "R4[{exp_rep}-{concentration, float}{seq_rep}_S{id, int}]_counts.txt"
            )
        metadata = {
            'name': 'B-1250A_S16',
            'exp_rep': 'B',
            'concentration': 1250.0,
            'seq_rep': 'A',
            'id': 16
            }

    """
    import numpy as np

    def extract_info_from_braces(target, pattern):
        """
        Iterative algorithm to extract metadata info from target and pattern
        """

        def stop(string, ix):
            """stop conditions when finding the rightest index of current domain(s)"""
            if ix == len(string) - 1:
                return True
            if string[ix] == '}' and string[ix + 1] != '{':
                return True
            else:
                return False

        def parse_domain(domain):
            """parse domain name and type"""
            if ',' in domain:
                domain = domain.split(',')
                if 'int' in domain[1] or 'i' in domain[1]:
                    return (domain[0], np.int)
                elif 'float' in domain[1] or 'f' in domain[1]:
                    return (domain[0], np.float32)
                else:
                    return (domain[0], str)
            else:
                return (domain, str)

        def get_domains(pattern):
            """
            inspect pattern and extract domain(s) from it
            multiple domains could be expected because of {}{} structure
            """

            domains = pattern[1:-1].split('}{')
            return [parse_domain(domain) for domain in domains]

        def extract_info(target, prefix, postfix):
            """
            extract substring in target are flanked by pre-fix and post-fix
            prefix: no need to find, always the first len(prefix) character of target
            postfix: the first occurrence of postfix substring after prefix, if not ''
            """
            if postfix == '':
                return target[len(prefix):]
            else:
                return target[len(prefix):target.find(postfix, len(prefix))]

        def divide_string(string):
            """
            split a string into consecutive chunks of digits, letters and upper letters
            """

            def letter_label(letter):
                if letter.isdigit():
                    return 0
                elif letter.isupper():
                    return 1
                else:
                    return 2

            label = [letter_label(letter) for letter in string]
            split_ix = [-1] + [ix for ix in range(len(string) - 1) if label[ix] != label[ix + 1]] + [len(string)]
            return [string[split_ix[i] + 1: split_ix[i + 1] + 1] for i in range(len(split_ix) - 1)]

        # anchor braces in pattern
        brace_left = pattern.find('{')
        if brace_left == -1:
            return {}
        brace_right = brace_left
        while not stop(pattern, brace_right):
            brace_right += 1
        domains = get_domains(pattern[brace_left:brace_right + 1])
        # find prefix and postfix
        prefix = pattern[:brace_left]
        postfix = pattern[brace_right + 1:pattern.find('{', brace_right + 1)
        if pattern.find('{', brace_right + 1) != -1 else len(pattern)]
        # anchor info domain in target from prefix and postfix
        info = extract_info(target, prefix, postfix)
        if len(domains) > 1:
            info = divide_string(info)
            if len(info) > len(domains):
                info[len(domains) - 1] = ''.join(info[len(domains) - 1:])
        else:
            info = [info]
        info_list = dict()
        for ix, domain in enumerate(domains):
            try:
                info_list[domain[0]] = domain[1](info[ix])
            except:
                info_list[domain[0]] = str(info[ix])
        # iteratively calculate the leftover substring
        if postfix != '':
            info_list.update(extract_info_from_braces(target=target[target.find(postfix, len(prefix)):],
                                                      pattern=pattern[brace_right + 1:]))
        return info_list

    metadata = {}  # dict to save extracted values
    # Anchor the position of brackets and curly braces in name_pattern
    brackets = [pattern.find('['), pattern.find(']')]
    metadata = extract_info_from_braces(target=target,
                                        pattern=pattern[:brackets[0]] + '{name}' + pattern[brackets[1] + 1:])
    metadata.update(extract_info_from_braces(target=metadata['name'],
                                             pattern=pattern[brackets[0] + 1: brackets[1]]))

    return metadata