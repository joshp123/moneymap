"""Written by AI on 2026.10.16 by model gpt-6.1-sol.

Population density in an exponential 40 km neighbourhood. Sum the population
onto a 5 arc-minute grid, convolve along spherical latitude rings, then
interpolate the smooth density field back onto the shared 30 arc-second grid.
"""
import math

import numpy as np

from layers.grid import (EARTH_RADIUS_KM, GRID_HEIGHT, GRID_TRANSFORM, GRID_WIDTH,
                         read_window_zero_filled, tile_row_strips)

COARSE_CELL_SIZE = 10
DENSITY_DISTANCE_KM = 40.
DENSITY_EXPONENT = .25
KERNEL_DISTANCE_KM = 8 * DENSITY_DISTANCE_KM
COARSE_ROWS = math.ceil(GRID_HEIGHT / COARSE_CELL_SIZE)
COARSE_COLUMNS = GRID_WIDTH // COARSE_CELL_SIZE


def coarse_population(population):
    """Preserve the population sum, folding the two dateline-edge cells west."""
    output = np.zeros((COARSE_ROWS, COARSE_COLUMNS), dtype='float64')
    for window in tile_row_strips():
        values = read_window_zero_filled(population, 1, window)
        height = math.ceil(values.shape[0] / COARSE_CELL_SIZE) * COARSE_CELL_SIZE
        values = np.pad(values, ((0, height-values.shape[0]), (0, 0)))
        blocks = values[:, :COARSE_COLUMNS*COARSE_CELL_SIZE].reshape(
            height//COARSE_CELL_SIZE, COARSE_CELL_SIZE, COARSE_COLUMNS, COARSE_CELL_SIZE)
        row = int(window.row_off) // COARSE_CELL_SIZE
        output[row:row+blocks.shape[0]] = blocks.sum(axis=(1, 3), dtype='float64')
        output[row:row+blocks.shape[0], 0] += values[:, COARSE_COLUMNS*COARSE_CELL_SIZE:].reshape(
            height//COARSE_CELL_SIZE, COARSE_CELL_SIZE, -1).sum(axis=(1, 2), dtype='float64')
    return output


def neighbourhood_density(population):
    """People per km² under a normalised exponential great-circle kernel.

    Longitude convolution uses FFTs. Each latitude has its own spherical
    kernel, so a 40 km neighbourhood keeps its size at every latitude.
    Truncation at 320 km drops 0.3% of the kernel before normalisation.
    """
    latitudes = np.radians(GRID_TRANSFORM.f +
                           (np.arange(COARSE_ROWS)+.5)*COARSE_CELL_SIZE*GRID_TRANSFORM.e)
    longitude_offsets = np.arange(COARSE_COLUMNS) * COARSE_CELL_SIZE * GRID_TRANSFORM.a
    longitude_haversine = np.sin(np.radians(longitude_offsets)/2)**2
    row_distance = EARTH_RADIUS_KM * abs(math.radians(COARSE_CELL_SIZE*GRID_TRANSFORM.e))
    row_radius = math.ceil(KERNEL_DISTANCE_KM / row_distance)
    population_spectrum = np.fft.rfft(population, axis=1)
    density = np.zeros_like(population)
    kernel_integral = 2*math.pi*DENSITY_DISTANCE_KM**2 * (1-9*math.exp(-8))
    for row, latitude in enumerate(latitudes):
        start, end = max(0, row-row_radius), min(COARSE_ROWS, row+row_radius+1)
        neighbours = latitudes[start:end, None]
        haversine = (np.sin((neighbours-latitude)/2)**2 +
                     np.cos(latitude)*np.cos(neighbours)*longitude_haversine[None, :])
        distance = 2*EARTH_RADIUS_KM*np.arcsin(np.sqrt(np.clip(haversine, 0, 1)))
        kernel = np.where(distance <= KERNEL_DISTANCE_KM, np.exp(-distance/DENSITY_DISTANCE_KM), 0)
        spectrum = (population_spectrum[start:end] * np.fft.rfft(kernel, axis=1)).sum(axis=0)
        density[row] = np.maximum(np.fft.irfft(spectrum, n=COARSE_COLUMNS), 0) / kernel_integral
        if row % 300 == 0:
            print(f'Neighbourhood density: row {row}/{COARSE_ROWS}', flush=True)
    return density


def interpolate_density(density, window):
    """Bilinear density at each fine cell centre, with periodic longitude."""
    rows = (np.arange(window.row_off, window.row_off+window.height)+.5)/COARSE_CELL_SIZE-.5
    columns = (np.arange(window.col_off, window.col_off+window.width)+.5)/COARSE_CELL_SIZE-.5
    row_floor, column_floor = np.floor(rows).astype(int), np.floor(columns).astype(int)
    row_fraction, column_fraction = rows-row_floor, columns-column_floor
    north, south = np.clip(row_floor, 0, COARSE_ROWS-1), np.clip(row_floor+1, 0, COARSE_ROWS-1)
    west, east = column_floor % COARSE_COLUMNS, (column_floor+1) % COARSE_COLUMNS
    first, last = int(north.min()), int(south.max())+1
    horizontal = (density[first:last, west]*(1-column_fraction) +
                  density[first:last, east]*column_fraction)
    return (horizontal[north-first]*(1-row_fraction[:, None]) +
            horizontal[south-first]*row_fraction[:, None])


def weighted_population(population, density, window):
    return population.astype('float64') * interpolate_density(density, window)**DENSITY_EXPONENT
