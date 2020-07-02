
# Copyright (C) 2020 Intel Corporation
#
# SPDX-License-Identifier: MIT

import cv2
import numpy as np


def mean_std(dataset):
    """
    Computes unbiased mean and std. dev. for dataset images, channel-wise.
    """
    # Use an online algorithm to:
    # - handle different image sizes
    # - avoid cancellation problem
    if len(dataset) == 0:
        return [0, 0, 0], [0, 0, 0]

    stats = np.empty((len(dataset), 2, 3), dtype=np.double)
    counts = np.empty(len(dataset), dtype=np.uint32)

    mean = lambda i, s: s[i][0]
    var = lambda i, s: s[i][1]

    for i, item in enumerate(dataset):
        counts[i] = np.prod(item.image.size)

        image = item.image.data
        if len(image.shape) == 2:
            image = image[:, :, np.newaxis]
        else:
            image = image[:, :, :3]
        # opencv is much faster than numpy here
        cv2.meanStdDev(image.astype(np.double) / 255,
            mean=mean(i, stats), stddev=var(i, stats))

    # make variance unbiased
    np.multiply(np.square(stats[:, 1]),
        (counts / (counts - 1))[:, np.newaxis],
        out=stats[:, 1])

    _, mean, var = StatsCounter().compute_stats(stats, counts, mean, var)
    return mean * 255, np.sqrt(var) * 255

class StatsCounter:
    # Implements online parallel computation of sample variance
    # https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Parallel_algorithm

    # Needed do avoid catastrophic cancellation in floating point computations
    @staticmethod
    def pairwise_stats(count_a, mean_a, var_a, count_b, mean_b, var_b):
        delta = mean_b - mean_a
        m_a = var_a * (count_a - 1)
        m_b = var_b * (count_b - 1)
        M2 = m_a + m_b + delta ** 2 * count_a * count_b / (count_a + count_b)
        return (
            count_a + count_b,
            mean_a * 0.5 + mean_b * 0.5,
            M2 / (count_a + count_b - 1)
        )

    # stats = float array of shape N, 2 * d, d = dimensions of values
    # count = integer array of shape N
    # mean_accessor = function(idx, stats) to retrieve element mean
    # variance_accessor = function(idx, stats) to retrieve element variance
    # Recursively computes total count, mean and variance, does O(log(N)) calls
    @staticmethod
    def compute_stats(stats, counts, mean_accessor, variance_accessor):
        m = mean_accessor
        v = variance_accessor
        n = len(stats)
        if n == 1:
            return counts[0], m(0, stats), v(0, stats)
        if n == 2:
            return __class__.pairwise_stats(
                counts[0], m(0, stats), v(0, stats),
                counts[1], m(1, stats), v(1, stats)
                )
        h = n // 2
        return __class__.pairwise_stats(
            *__class__.compute_stats(stats[:h], counts[:h], m, v),
            *__class__.compute_stats(stats[h:], counts[h:], m, v)
            )

def compute_image_statistics(dataset):
    stats = {
        'dataset': {},
        'subsets': {}
    }

    def _extractor_stats(extractor):
        mean, std = mean_std(extractor)
        return {
            'Total images': len(extractor),
            'Image mean': ['%.3f' % n for n in mean],
            'Image std': ['%.3f' % n for n in std],
        }

    stats['dataset'].update(_extractor_stats(dataset))

    subsets = dataset.subsets() or [None]
    if subsets and 0 < len([s for s in subsets if s]):
        for subset_name in subsets:
            stats['subsets'][subset_name] = _extractor_stats(
                dataset.get_subset(subset_name))

    return stats

def compute_ann_statistics(dataset):
    stats = {
        'Total images': len(dataset),
        'Total annotations': 0,
        'Annotations by type': {},
        'Unannotated images': [],
    }
    by_type = stats['Annotations by type']

    for item in dataset:
        if len(item.annotations) == 0:
            stats['Unannotated images'].append(item.id)
        else:
            for ann in item.annotations:
                by_type[ann.type.name] = by_type.get(ann.type.name, 0) + 1

                for name, value in ann.attributes.items():
                    by_val = by_attr.get(name, {})
                    by_val[str(value)] = by_val.get(str(value), 0) + 1
                    by_attr[name] = by_val

    stats['Total annotations'] = sum(stats['Annotations by type'].values())

    return stats