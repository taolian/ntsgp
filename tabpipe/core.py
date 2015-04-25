import os
import hashlib

import luigi
import pandas as pd

from util import *


class TableMixin(object):
    """Useful table properties."""

    @property
    def tname(self):
        path = self.table.output().path
        return os.path.basename(os.path.splitext(path)[0])

    @property
    def thash(self):
        return hashlib.sha1(self.tname).hexdigest()


class DataTable(luigi.ExternalTask, TableMixin):
    """Wraps up external source files for data tables."""
    fname = luigi.Parameter(description='filename for data table')

    @property
    def table(self):
        return self

    def output(self):
        return luigi.LocalTarget(self.fname)


class TableBase(luigi.Task, TableMixin):
    """Miscellaneous table manipulation methods."""
    savedir = luigi.Parameter(
        default='',
        description='directory to save data files to; default is cwd')
    colnames = luigi.Parameter(
        description='name of column to scrub is first, then any others')
    outname = luigi.Parameter(
        description='filename to output transformed table to')

    @property
    def multiple_columns(self):
        """True if `colnames` is an interable, else False."""
        return hasattr(self.colnames, '__iter__')

    @property
    def cols(self):
        """Colnames to use as function input; list of 1+ strings."""
        return list(self.colnames) if self.multiple_columns else [self.colnames]

    @property
    def usecols(self):
        """Columns to use for reading data tables. Always assume index."""
        return [0] + self.cols

    @property
    def colname(self):
        """Main colname to use for table output and function input."""
        return self.colnames[0] if self.multiple_columns else self.colnames

    def read_output_table(self):
        """Only index and `colname` are written to output."""
        with self.output().open() as f:
            return pd.read_csv(f, index_col=0)

    def read_input_table(self):
        """Read only the columns which will be used."""
        input = self.input()
        if hasattr(input, 'keys'):
            infile = input['table']
        elif hasattr(input, '__iter__'):
            infile = input[0]
        else:
            infile = input

        with infile.open() as f:
            return pd.read_csv(f, index_col=0, usecols=self.usecols)

    def output(self):
        """Output to`savedir/outname`."""
        return luigi.LocalTarget(os.path.join(self.savedir, self.outname))

    run = NotImplemented


class TableTransform(TableBase):
    """Takes a task that outputs a table, transforms the table, writes it."""
    table = luigi.Parameter(
        description='task that outputs table to transform')

    def requires(self):
        return self.table


class MultipleTableTransform(TableBase):
    """Takes several tables and outputs one table."""
    tables = luigi.Parameter(
        description='collection of tasks that produce the tables to merge')
    read_input_table = None
    colnames = None
    colname = None

    def requires(self):
        return self.tables


class TableFuncApplier(TableTransform):
    func = luigi.Parameter(
        description='function to perform transformation on table')

    def apply_func(self, table):
        if self.multiple_columns:
            othercols = self.cols[1:]
            if len(othercols) == 1:  # extract single additional column name
                othercols = othercols[0]
            self.func(table, self.colname, othercols)
        else:
            self.func(table, self.colname)


class ColumnReplacer(TableTransform):
    """Replace one column in a table with another from another table."""
    replacement = luigi.Parameter(
        description='task that outputs the table with the replacement column')
    outname = luigi.Parameter(
        default=None,
        description='table output filename; default is table/replacement name hash')
    usecols = None  # read all columns from input table

    def requires(self):
        return {'table': self.table,
                'replacement': self.replacement}

    def output(self):
        """Either the outname passed or a sha1 hash of a hash of the source
        table name and a hash of the replacement table name.
        """
        if self.outname:
            path = os.path.join(self.savedir, self.outname)
        else:
            hashes = ''.join((self.table.thash, self.replacement.thash))
            outname = hashlib.sha1(hashes).hexdigest()
            path = os.path.join(self.savedir, outname)
        return luigi.LocalTarget(path)

    def run(self):
        """Load `colname` from the `replacement` table and replace the column
        with `colname` in `table`. The output includes the entire original table
        with the single column replaced.
        """
        inputs = self.input()
        df = self.read_input_table()
        with inputs['replacement'].open() as f:
            col = pd.read_csv(f, index_col=0, usecols=(0, self.colname))

        # Replace column.
        df[self.colname] = col[self.colname]
        with self.output().open('w') as f:
            df.to_csv(f, index=True)


class TableMerger(MultipleTableTransform):
    """Merge multiple DataFrames together."""
    # Each entry in the `tables` dicts should contain at least the task that
    # yields the input table. The colnames are optional; this will read only
    # those columns of the table, in addition to `id` if it is passed. `id`
    # specifies the column name to use for merging; if none is specified, the
    # index is used.
    tables = luigi.Parameter(
        description='List of dict: `table`, `colnames`, `id`')

    def requires(self):
        return [spec['table'] for spec in self.tables]

    def read_table(self, table, colnames=None, id=None):
        tfile = table.output()
        with tfile.open() as f:
            if colnames:
                if id:
                    colnames.append(id)
                colnames.insert(0, 0)  # read index
                usecols = list(set(colnames))
            else:
                usecols=None
            return pd.read_csv(f, usecols=usecols, index_col=0)

    def run(self):
        """Merge all input data frames on the given colname(s)."""
        if len(self.tables) <= 1:
            raise ValueError("Need at least two tables to merge.")

        for spec in self.tables:
            spec['id'] = None if not 'id' in spec else spec['id']

        tables = [(self.read_table(**spec), spec['id'])
                  for spec in self.tables]

        # Replace current table with merge on last table, then replace current
        # list index with merged table.
        for tnum in range(len(tables))[1:]:
            left, lid = tables[tnum-1]
            right, rid = tables[tnum]
            lidx = not bool(lid)  # False if not None
            ridx = not bool(rid)  # False if not None
            merged = left.merge(right, how='outer',
                                left_on=lid, right_on=rid,
                                left_index=lidx, right_index=ridx)
            tables[tnum] = (merged, rid)

        with self.output().open('w') as f:
            merged.to_csv(f, index=True)
