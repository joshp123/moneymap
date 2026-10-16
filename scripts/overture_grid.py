"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Read sparse Overture cell counts as windows of the population grid.
"""
import numpy as np
import pyarrow.parquet as parquet


class OvertureGrid:
    def __init__(self, path, value_columns, width, height):
        self.value_columns = tuple(value_columns)
        table = parquet.read_table(path, columns=['grid_row', 'grid_col', *self.value_columns])
        rows = table['grid_row'].to_numpy()
        columns = table['grid_col'].to_numpy()
        values = [table[name].to_numpy().astype('float64') for name in self.value_columns]
        inside = (rows >= 0) & (rows < height) & (columns >= 0) & (columns < width)
        self.totals = {name: float(value.sum(dtype='float64'))
                       for name, value in zip(self.value_columns, values)}
        self.outside_totals = {name: float(value[~inside].sum(dtype='float64'))
                               for name, value in zip(self.value_columns, values)}
        order = np.argsort(rows[inside], kind='stable')
        self.rows = rows[inside][order]
        self.columns = columns[inside][order]
        self.values = [value[inside][order] for value in values]

    def window(self, window):
        row_start, column_start = int(window.row_off), int(window.col_off)
        height, width = int(window.height), int(window.width)
        start, end = np.searchsorted(self.rows, [row_start, row_start + height])
        rows = self.rows[start:end] - row_start
        columns = self.columns[start:end] - column_start
        inside = (columns >= 0) & (columns < width)
        output = []
        for values in self.values:
            plane = np.zeros((height, width), dtype='float64')
            np.add.at(plane, (rows[inside], columns[inside]), values[start:end][inside])
            output.append(plane)
        return tuple(output)
