#!/usr/bin/env python3
###############################################################################
#
# Name:          time_series.py
# Contact(s):    Marcel Caron
# Developed:     Oct. 14, 2021 by Marcel Caron 
# Last Modified: Dec. 01, 2022 by Marcel Caron             
# Title:         Line plot of verification metric as a function of 
#                valid or init time
# Abstract:      Plots METplus output (e.g., BCRMSE) as a line plot, 
#                varying by valid or init time, which represents the x-axis. 
#                Line colors and styles are unique for each model, and several
#                models can be plotted at once.
#
###############################################################################

import os
import sys
import numpy as np
import math
import pandas as pd
import logging
from functools import reduce
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.image as mpimg
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from datetime import datetime, timedelta as td
import shutil

SETTINGS_DIR = os.environ['USH_DIR']
sys.path.insert(0, os.path.abspath(SETTINGS_DIR))
from settings import Toggle, Templates, Paths, Presets, ModelSpecs, Reference
from plotter import Plotter
from prune_stat_files import prune_data
import plot_util
import df_preprocessing
from check_variables import *

# ================ GLOBALS AND CONSTANTS ================

plotter = Plotter()
plotter.set_up_plots()
toggle = Toggle()
templates = Templates()
paths = Paths()
presets = Presets()
model_colors = ModelSpecs()
reference = Reference()


# =================== FUNCTIONS =========================


def plot_time_series(df: pd.DataFrame, logger: logging.Logger, 
                     date_range: tuple, model_list: list, num: int = 0, 
                     level: str = '500', flead='all', thresh: list = ['<20'], 
                     metric1_name: str = 'BCRMSE', metric2_name: str = 'BIAS',
                     y_min_limit: float = -10., y_max_limit: float = 10., 
                     y_lim_lock: bool = False,
                     xlabel: str = 'Valid Date', date_type: str = 'VALID', 
                     date_hours: list = [0,6,12,18], verif_type: str = 'pres', 
                     save_dir: str = '.', restart_dir: str = '.', 
                     requested_var: str = 'HGT', 
                     line_type: str = 'SL1L2', dpi: int = 100, 
                     confidence_intervals: bool = False, interp_pts: list = [],
                     bs_nrep: int = 5000, bs_method: str = 'MATCHED_PAIRS',
                     ci_lev: float = .95, bs_min_samp: int = 30,
                     eval_period: str = 'TEST', save_header='', 
                     display_averages: bool = True, 
                     keep_shared_events_only: bool = False,
                     plot_group: str = 'sfc_upper',
                     sample_equalization: bool = True,
                     plot_logo_left: bool = False,
                     plot_logo_right: bool = False, path_logo_left: str = '.',
                     path_logo_right: str = '.', zoom_logo_left: float = 1.,
                     zoom_logo_right: float = 1., aggregate_dates_by: str = '',
                     running_mean: str = ''):

    logger.info("========================================")
    logger.info(f"Creating Plot {num} ...")
   
    if df.empty:
        logger.warning(f"Empty Dataframe. Continuing onto next plot...")
        logger.info("========================================")
        return None

    fig, ax = plotter.get_plots(num)  
    variable_translator = reference.variable_translator
    domain_translator = reference.domain_translator
    model_settings = model_colors.model_settings

    # filter by level
    df = df[df['FCST_LEV'].astype(str).eq(str(level))]

    if df.empty:
        logger.warning(f"Empty Dataframe. Continuing onto next plot...")
        plt.close(num)
        logger.info("========================================")
        return None

    # filter by forecast lead times
    df, frange_string, frange_save_string = plot_util.filter_by_lead(
        logger, df, flead
    )

    # Remove from date_hours the valid/init hours that don't exist in the 
    # dataframe
    date_hours = np.array(date_hours)[[
        str(x) in df[str(date_type).upper()].dt.hour.astype(str).tolist() 
        for x in date_hours
    ]]

    if df.empty:
        logger.warning(f"Empty Dataframe. Continuing onto next plot...")
        plt.close(num)
        logger.info("========================================")
        return None

    # Filter by interpolation width
    df, interp_pts_string, interp_pts_save_string = plot_util.filter_by_width(
        logger, df, interp_pts
    )

    # Process thresholds
    df, opt, opt_letter, requested_thresh_value = plot_util.process_thresh(
        logger, df, thresh
    )

    # Remove from model_list the models that don't exist in the dataframe
    df, model_list = plot_util.process_models(logger, df, model_list)

    if df.empty:
        logger.warning(f"Empty Dataframe. Continuing onto next plot...")
        plt.close(num)
        logger.info("========================================")
        return None

    # Equalize Samples
    # Note: groups are used for equalization, not as axes for plotting
    group_by = ['MODEL',str(date_type).upper()]
    if sample_equalization:
        df, bool_success = plot_util.equalize_samples(logger, df, group_by)
        if not bool_success:
            sample_equalization = False
        if df.empty:
            logger.warning(f"Empty Dataframe. Continuing onto next plot...")
            plt.close(num)
            logger.info("========================================")
            return None

    # Aggregate unit statistics and calculate metrics
    df_groups = df.groupby(group_by)
    metrics_using_var_units = [
        'BCRMSE','RMSE','BIAS','ME','FBAR','OBAR','MAE','FBAR_OBAR',
        'SPEED_ERR','DIR_ERR','RMSVE','VDIFF_SPEED','VDIF_DIR',
        'FBAR_OBAR_SPEED','FBAR_OBAR_DIR','FBAR_SPEED','FBAR_DIR'
    ]
    df_aggregated, metric_long_names, units, unit_convert = plot_util.process_stats(
        logger, df, df_groups, model_list, metric1_name, metric2_name, 
        metrics_using_var_units, confidence_intervals, date_type, line_type,
        'timeseries', bs_method, bs_nrep, bs_min_samp, ci_lev, reference, 
        sample_equalization=sample_equalization,
        keep_shared_events_only=keep_shared_events_only,

    )
    
    # Make pivot tables for plotting
    pivot_tables = plot_util.get_pivot_tables(
        df_aggregated, metric1_name, metric2_name, sample_equalization, 
        keep_shared_events_only, date_type, confidence_intervals, 
        'timeseries', aggregate_dates_by=aggregate_dates_by, colname='MODEL'
    )
    pivot_metric1, pivot_metric2 = pivot_tables[:2]
    pivot_ci_lower1, pivot_ci_upper1 = pivot_tables[2:4]
    pivot_ci_lower2, pivot_ci_upper2 = pivot_tables[4:]

    # Reindex pivot table with full list of dates, introducing NaNs 
    pivot_tables, incr = reindex_pivot_tables(
        pivot_metric2, pivot_metric2, pivot_counts, pivot_ci_lower1, 
        pivot_ci_upper2, pivot_ci_lower2, pivot_ci_upper2, 'timeseries', 
        date_hours, metric2_name, sample_equalization, confidence_intervals
    )
    pivot_metric1, pivot_metric2, pivot_counts = pivot_tables[:3]
    pivot_ci_lower1, pivot_ci_upper1 = pivot_tables[3:5]
    pivot_ci_lower2, pivot_ci_upper2 = pivot_tables[5:]
    if (metric2_name and (pivot_metric1.empty or pivot_metric2.empty)):
        print_varname = df['FCST_VAR'].tolist()[0]
        logger.warning(
            f"Could not find (and cannot plot) {metric1_name} and/or"
            + f" {metric2_name} stats for {print_varname} at any level. "
            + f"This often happens when processed data are all NaNs, "
            + f" which are removed.  Check for seasonal cases where critical "
            + f" threshold is not reached. Continuing ..."
        )
        plt.close(num)
        logger.info("========================================")
        return None
    elif not metric2_name and pivot_metric1.empty:
        print_varname = df['FCST_VAR'].tolist()[0]
        logger.warning(
            f"Could not find (and cannot plot) {metric1_name}"
            + f" stats for {print_varname} at any level. "
            + f"This often happens when processed data are all NaNs, "
            + f" which are removed.  Check for seasonal cases where critical "
            + f" threshold is not reached. Continuing ..."
        )
        plt.close(num)
        logger.info("========================================")
        return None
    
    # Get plot settings for models
    mod_setting_dicts = plot_util.get_model_settings(model_list, model_colors)

    # Plot data
    logger.info("Begin plotting ...")
    if confidence_intervals:
        indices_in_common1 = list(set.intersection(*map(
            set, 
            [
                pivot_metric1.index, 
                pivot_ci_lower1.index, 
                pivot_ci_upper1.index
            ]
        )))
        pivot_metric1 = pivot_metric1[pivot_metric1.index.isin(indices_in_common1)]
        pivot_ci_lower1 = pivot_ci_lower1[pivot_ci_lower1.index.isin(indices_in_common1)]
        pivot_ci_upper1 = pivot_ci_upper1[pivot_ci_upper1.index.isin(indices_in_common1)]
        if sample_equalization:
            pivot_counts = pivot_counts[pivot_counts.index.isin(indices_in_common1)]
        if metric2_name is not None:
            indices_in_common2 = list(set.intersection(*map(
                set, 
                [
                    pivot_metric2.index, 
                    pivot_ci_lower2.index, 
                    pivot_ci_upper2.index
                ]
            )))
            pivot_metric2 = pivot_metric2[pivot_metric2.index.isin(indices_in_common2)]
            pivot_ci_lower2 = pivot_ci_lower2[pivot_ci_lower2.index.isin(indices_in_common2)]
            pivot_ci_upper2 = pivot_ci_upper2[pivot_ci_upper2.index.isin(indices_in_common2)]
    x_vals1 = pivot_metric1.index
    if metric2_name is not None:
        x_vals2 = pivot_metric2.index
    else:
        x_vals2 = None
    y_min = y_min_limit
    y_max = y_max_limit
    if thresh and '' not in thresh:
        thresh_labels = np.unique(df['FCST_THRESH_VALUE'])
        thresh_argsort = np.argsort(thresh_labels.astype(float))
        requested_thresh_argsort = np.argsort([
            float(item) for item in requested_thresh_value
        ])
        thresh_labels = [thresh_labels[i] for i in thresh_argsort]
        requested_thresh_labels = [
            requested_thresh_value[i] for i in requested_thresh_argsort
        ]
    plot_reference = [False, False]
    ref_metrics = ['OBAR']
    if str(metric1_name).upper() in ref_metrics:
        plot_reference[0] = True
        pivot_reference1 = pivot_metric1
        reference1 = pivot_reference1.mean(axis=1)
        if confidence_intervals:
            reference_ci_lower1 = pivot_ci_lower1.mean(axis=1)
            reference_ci_upper1 = pivot_ci_upper1.mean(axis=1)
        if not np.any((pivot_reference1.T/reference1).T == 1.):
            logger.warning(
                f"{str(metric1_name).upper()} is requested, but the value "
                + f"varies from model to model. "
                + f"Will plot an individual line for each model. If a "
                + f"single reference line is preferred, set the "
                + f"sample_equalization toggle in ush/settings.py to 'True', "
                + f"and check in the log file if sample equalization "
                + f"completed successfully."
            )
            plot_reference[0] = False
    if metric2_name is not None and str(metric2_name).upper() in ref_metrics:
        plot_reference[1] = True
        pivot_reference2 = pivot_metric2
        reference2 = pivot_reference2.mean(axis=1)
        if confidence_intervals:
            reference_ci_lower2 = pivot_ci_lower2.mean(axis=1)
            reference_ci_upper2 = pivot_ci_upper2.mean(axis=1)
        if not np.any((pivot_reference2.T/reference2).T == 1.):
            logger.warning(
                f"{str(metric2_name).upper()} is requested, but the value "
                + f"varies from model to model. "
                + f"Will plot an individual line for each model. If a "
                + f"single reference line is preferred, set the "
                + f"sample_equalization toggle in ush/settings.py to 'True', "
                + f"and check in the log file if sample equalization "
                + f"completed successfully."
            )
            plot_reference[1] = False
    if np.any(plot_reference):
        plotted_reference = [False, False]
        if confidence_intervals:
            plotted_reference_CIs = [False, False]
    f = lambda m,c,ls,lw,ms,mec: plt.plot(
        [], [], marker=m, mec=mec, mew=2., c=c, ls=ls, lw=lw, ms=ms
    )[0]
    if metric2_name is not None:
        if np.any(plot_reference):
            ref_color_dict = model_colors.get_color_dict('obs')
            handles = []
            labels = []
            line_settings = ['solid','dashed']
            metric_names = [metric1_name, metric2_name]
            for p, rbool in enumerate(plot_reference):
                if rbool:
                    handles += [
                        f('', ref_color_dict['color'], line_settings[p], 5., 0, 'white')
                    ]
                else:
                    handles += [
                        f('', 'black', line_settings[p], 5., 0, 'white')
                    ]
                labels += [
                    str(metric_names[p]).upper()
                ]
        else:
            handles = [
                f('', 'black', line_setting, 5., 0, 'white')
                for line_setting in ['solid','dashed']
            ]
            labels = [
                str(metric_name).upper()
                for metric_name in [metric1_name, metric2_name]
            ]
    else:
        handles = []
        labels = []
    n_mods = 0
    for m in range(len(mod_setting_dicts)):
        if model_list[m] in model_colors.model_alias:
            model_plot_name = (
                model_colors.model_alias[model_list[m]]['plot_name']
            )
        else:
            model_plot_name = model_list[m]
        if str(model_list[m]) not in pivot_metric1:
            continue
        y_vals_metric1 = pivot_metric1[str(model_list[m])].values
        y_vals_metric1_mean = np.nanmean(y_vals_metric1)
        if metric2_name is not None:
            y_vals_metric2 = pivot_metric2[str(model_list[m])].values
            y_vals_metric2_mean = np.nanmean(y_vals_metric2)
        if confidence_intervals:
            y_vals_ci_lower1 = pivot_ci_lower1[
                str(model_list[m])
            ].values
            y_vals_ci_upper1 = pivot_ci_upper1[
                str(model_list[m])
            ].values
            if metric2_name is not None:
                y_vals_ci_lower2 = pivot_ci_lower2[
                    str(model_list[m])
                ].values
                y_vals_ci_upper2 = pivot_ci_upper2[
                    str(model_list[m])
                ].values
        if not y_lim_lock:
            if metric2_name is not None:
                y_vals_both_metrics = np.concatenate((y_vals_metric1, y_vals_metric2))
                if np.any(y_vals_both_metrics != np.inf):
                    y_vals_metric_min = np.nanmin(y_vals_both_metrics[y_vals_both_metrics != np.inf])
                    y_vals_metric_max = np.nanmax(y_vals_both_metrics[y_vals_both_metrics != np.inf])
                else:
                    y_vals_metric_min = np.nanmin(y_vals_both_metrics)
                    y_vals_metric_max = np.nanmax(y_vals_both_metrics)
            else:
                if np.any(y_vals_metric1 != np.inf):
                    y_vals_metric_min = np.nanmin(y_vals_metric1[y_vals_metric1 != np.inf])
                    y_vals_metric_max = np.nanmax(y_vals_metric1[y_vals_metric1 != np.inf])
                else:
                    y_vals_metric_min = np.nanmin(y_vals_metric1)
                    y_vals_metric_max = np.nanmax(y_vals_metric1)
            if n_mods == 0:
                y_mod_min = y_vals_metric_min
                y_mod_max = y_vals_metric_max
                counts = pivot_counts[str(model_list[m])].values
                n_mods+=1
            else:
                if math.isinf(y_mod_min):
                    y_mod_min = y_vals_metric_min
                else:
                    y_mod_min = np.nanmin([y_mod_min, y_vals_metric_min])
                if math.isinf(y_mod_max):
                    y_mod_max = y_vals_metric_max
                else:
                    y_mod_max = np.nanmax([y_mod_max, y_vals_metric_max])
            if (y_vals_metric_min > y_min_limit 
                    and y_vals_metric_min <= y_mod_min):
                y_min = y_vals_metric_min
            if (y_vals_metric_max < y_max_limit 
                    and y_vals_metric_max >= y_mod_max):
                y_max = y_vals_metric_max
        if np.abs(y_vals_metric1_mean) < 1E4:
            metric1_mean_fmt_string = f'{y_vals_metric1_mean:.2f}'
        else:
            metric1_mean_fmt_string = f'{y_vals_metric1_mean:.2E}'
        if plot_reference[0]:
            if not plotted_reference[0]:
                ref_color_dict = model_colors.get_color_dict('obs')
                plt.plot(
                    x_vals1.tolist(), reference1,
                    marker=ref_color_dict['marker'],
                    c=ref_color_dict['color'], mew=2., mec='white',
                    figure=fig, ms=ref_color_dict['markersize'], ls='solid',
                    lw=ref_color_dict['linewidth']
                )
                plotted_reference[0] = True
        else:
            plt.plot(
                x_vals1.tolist(), y_vals_metric1, 
                marker=mod_setting_dicts[m]['marker'], 
                c=mod_setting_dicts[m]['color'], mew=2., mec='white', 
                figure=fig, ms=mod_setting_dicts[m]['markersize'], ls='solid', 
                lw=mod_setting_dicts[m]['linewidth']
            )
        if metric2_name is not None:
            if np.abs(y_vals_metric2_mean) < 1E4:
                metric2_mean_fmt_string = f'{y_vals_metric2_mean:.2f}'
            else:
                metric2_mean_fmt_string = f'{y_vals_metric2_mean:.2E}'
            if plot_reference[1]:
                if not plotted_reference[1]:
                    ref_color_dict = model_colors.get_color_dict('obs')
                    plt.plot(
                        x_vals2.tolist(), reference2,
                        marker=ref_color_dict['marker'],
                        c=ref_color_dict['color'], mew=2., mec='white',
                        figure=fig, ms=ref_color_dict['markersize'], ls='dashed',
                        lw=ref_color_dict['linewidth']
                    )
                    plotted_reference[1] = True
            else:
                plt.plot(
                    x_vals2.tolist(), y_vals_metric2, 
                    marker=mod_setting_dicts[m]['marker'], 
                    c=mod_setting_dicts[m]['color'], mew=2., mec='white', 
                    figure=fig, ms=mod_setting_dicts[m]['markersize'], 
                    ls='dashed', lw=mod_setting_dicts[m]['linewidth']
                )
        if confidence_intervals:
            if plot_reference[0]:
                if not plotted_reference_CIs[0]:
                    ref_color_dict = model_colors.get_color_dict('obs')
                    plt.errorbar(
                        x_vals1.tolist(), reference1,
                        yerr=[np.abs(reference_ci_lower1), reference_ci_upper1],
                        fmt='none', ecolor=ref_color_dict['color'],
                        elinewidth=ref_color_dict['linewidth'],
                        capsize=10., capthick=ref_color_dict['linewidth'],
                        alpha=.70, zorder=0
                    )
                    plotted_reference_CIs[0] = True
            else:
                plt.errorbar(
                    x_vals1.tolist(), y_vals_metric1,
                    yerr=[np.abs(y_vals_ci_lower1), y_vals_ci_upper1],
                    fmt='none', ecolor=mod_setting_dicts[m]['color'],
                    elinewidth=mod_setting_dicts[m]['linewidth'],
                    capsize=10., capthick=mod_setting_dicts[m]['linewidth'],
                    alpha=.70, zorder=0
                )
            if metric2_name is not None:
                if plot_reference[1]:
                    if not plotted_reference_CIs[1]:
                        ref_color_dict = model_colors.get_color_dict('obs')
                        plt.errorbar(
                            x_vals2.tolist(), reference2,
                            yerr=[np.abs(reference_ci_lower2), reference_ci_upper2],
                            fmt='none', ecolor=ref_color_dict['color'],
                            elinewidth=ref_color_dict['linewidth'],
                            capsize=10., capthick=ref_color_dict['linewidth'],
                            alpha=.70, zorder=0
                        )
                        plotted_reference_CIs[1] = True
                else:
                    plt.errorbar(
                        x_vals2.tolist(), y_vals_metric2,
                        yerr=[np.abs(y_vals_ci_lower2), y_vals_ci_upper2],
                        fmt='none', ecolor=mod_setting_dicts[m]['color'],
                        elinewidth=mod_setting_dicts[m]['linewidth'],
                        capsize=10., capthick=mod_setting_dicts[m]['linewidth'],
                        alpha=.70, zorder=0
                    )
        handles+=[
            f(
                mod_setting_dicts[m]['marker'], mod_setting_dicts[m]['color'],
                'solid', mod_setting_dicts[m]['linewidth'], 
                mod_setting_dicts[m]['markersize'], 'white'
            )
        ]
        if display_averages:
            if metric2_name is not None:
                labels+=[
                    f'{model_plot_name} ({metric1_mean_fmt_string},'
                    + f' {metric2_mean_fmt_string})'
                ]
            else:
                labels+=[
                    f'{model_plot_name} ({metric1_mean_fmt_string})'
                ]
        else:
            labels+=[f'{model_plot_name}']

    # Plot zero line
    plt.axhline(y=0, color='black', linestyle='--', linewidth=1, zorder=0) 
    
    # Configure x-axis
    x_axis_config = plot_util.configure_dates_axis(
        xvals1, incr
    )
    xticks, xtick_labels_with_blanks = x_axis_config

    # Configure y-axis
    var_long_name_key = df['FCST_VAR'].tolist()[0]
    y_axis_config = plot_util.configure_stats_axis(
        y_min, y_max, y_min_limit, y_max_limit, thresh_labels, thresh, 
        metric1_name, metric2_name, metric_long_names, metrics_using_var_units,
        units, unit_convert, reference, var_long_name_key, variable_translator
    )
    ylim_min, ylim_max, yticks, ytick_labels_with_blanks, ylabel = y_axis_config[:5]
    thresh_labels, metric1_string, metric2_string, units = y_axis_config[5:9]
    var_long_name_key, var_long_name = y_axis_config[9:]
    
    # Set axes
    ax.set_xlim(xticks[0], xticks[-1])
    ax.set_ylim(ylim_min, ylim_max)
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    ax.set_xticklabels(xtick_labels_with_blanks)
    ax.set_yticklabels(ytick_labels_with_blanks)
    ax.set_yticks(yticks)
    ax.set_xticks(xticks)
    ax.tick_params(
        labelleft=True, labelright=False, labelbottom=True, labeltop=False
    )
    ax.tick_params(
        left=False, labelleft=False, labelright=False, labelbottom=False, 
        labeltop=False, which='minor', axis='y', pad=15
    )
    majxticks = [i for i, item in enumerate(xtick_labels_with_blanks) if item]
    for mt in majxticks:
        ax.xaxis.get_major_ticks()[mt].tick1line.set_markersize(8)
    majyticks = [i for i, item in enumerate(ytick_labels_with_blanks) if item]
    for mt in majyticks:
        ax.yaxis.get_major_ticks()[mt].tick1line.set_markersize(8)

    # Set legend
    ax.legend(
        handles, labels, framealpha=1, 
        bbox_to_anchor=(0.5, -0.15), ncol=4, frameon=True, numpoints=2, 
        borderpad=.8, labelspacing=1.) 
    
    # Adjust fig and grid
    fig.subplots_adjust(wspace=0, hspace=0)
    ax.grid(
        visible=True, which='major', axis='both', alpha=.5, linestyle='--', 
        linewidth=.5, zorder=0
    )
    
    # Plot samples
    if sample_equalization:
        counts = pivot_counts.mean(axis=1, skipna=True).fillna('')
        for count, xval in zip(counts, x_vals1.tolist()):
            if not isinstance(count, str):
                count = str(int(count))
            ax.annotate(
                f'{count}', xy=(xval,1.), 
                xycoords=('data','axes fraction'), xytext=(0,12), 
                textcoords='offset points', va='top', fontsize=11, 
                color='dimgrey', ha='center'
            )
        ax.annotate(
            '#SAMPLES', xy=(0.,1.), xycoords='axes fraction', 
            xytext=(-50, 21), textcoords='offset points', va='top', 
            fontsize=11, color='dimgrey', ha='center'
        )
    
    # Variable info
    var_savename = plot_util.get_var_info(df)
    
    # Domain info
    domain_string, domain_save_string = plot_util.get_domain_info(
        df, domain_translator
    )

    # Date info
    date_hours_string = plot_util.get_name_for_listed_items(
        [f'{date_hour:02d}' for date_hour in date_hours],
        ', ', '', 'Z', 'and ', ''
    )
    date_start_string = date_range[0].strftime('%d %b %Y')
    date_end_string = date_range[1].strftime('%d %b %Y')

    # Level info
    level_string, level_savename = plot_util.get_level_info(
        verif_type, level, var_long_name_key, var_savename
    )

    # Set the title
    if metric2_name is not None:
        title1 = f'{metric1_string} and {metric2_string}'
    else:
        title1 = f'{metric1_string}'
    if interp_pts and '' not in interp_pts:
        title1+=f' {interp_pts_string}'
    if thresh and '' not in thresh:
        thresholds_phrase = ', '.join([
            f'{opt}{thresh_label}' for thresh_label in thresh_labels
        ])
        thresholds_save_phrase = ''.join([
            f'{opt_letter}{thresh_label}' 
            for thresh_label in requested_thresh_labels
        ]).replace('.','p')
        if units:
            title2 = (f'{level_string}{var_long_name} ({thresholds_phrase}'
                      + f' {units}), {domain_string}')
        else:
            title2 = (f'{level_string}{var_long_name} ({thresholds_phrase}'
                      + f' unitless), {domain_string}')
    else:
        if units:
            title2 = f'{level_string}{var_long_name} ({units}), {domain_string}'
        else:
            title2 = f'{level_string}{var_long_name} (unitless), {domain_string}'
    title3 = (f'{str(date_type).capitalize()} {date_hours_string} '
              + f'{date_start_string} to {date_end_string}, {frange_string}')
    title_center = '\n'.join([title1, title2, title3])
    if sample_equalization:
        title_pad=23
    else:
        title_pad=None
    ax.set_title(title_center, pad=title_pad) 
    logger.info("... Plotting complete.")

    # Plot logos
    if plot_logo_left:
        if os.path.exists(path_logo_left):
            left_logo_arr = mpimg.imread(path_logo_left)
            left_image_box = OffsetImage(left_logo_arr, zoom=zoom_logo_left)
            ab_left = AnnotationBbox(
                left_image_box, xy=(0.,1.), xycoords='axes fraction',
                xybox=(0, 20), boxcoords='offset points', frameon = False,
                box_alignment=(0,0)
            )
            ax.add_artist(ab_left)
        else:
            logger.warning(
                f"Left logo path ({path_logo_left}) doesn't exist. "
                + f"Left logo will not be plotted."
            )
    if plot_logo_right:
        if os.path.exists(path_logo_right):
            right_logo_arr = mpimg.imread(path_logo_right)
            right_image_box = OffsetImage(right_logo_arr, zoom=zoom_logo_right)
            ab_right = AnnotationBbox(
                right_image_box, xy=(1.,1.), xycoords='axes fraction',
                xybox=(0, 20), boxcoords='offset points', frameon = False,
                box_alignment=(1,0)
            )
            ax.add_artist(ab_right)
        else:
            logger.warning(
                f"Right logo path ({path_logo_right}) doesn't exist. "
                + f"Right logo will not be plotted."
            )

    # Saving
    models_savename = '_'.join([str(model) for model in model_list])
    if len(date_hours) <= 8: 
        date_hours_savename = '_'.join([
            f'{date_hour:02d}Z' for date_hour in date_hours
        ])
    else:
        date_hours_savename = '-'.join([
            f'{date_hour:02d}Z' 
            for date_hour in [date_hours[0], date_hours[-1]]
        ])
    date_start_savename = date_range[0].strftime('%Y%m%d')
    date_end_savename = date_range[1].strftime('%Y%m%d')
    if str(eval_period).upper() == 'TEST':
        time_period_savename = f'{date_start_savename}-{date_end_savename}'
    else:
        time_period_savename = f'{eval_period}'

    plot_info = '_'.join(
        [item for item in [
            f'timeseries',
            f'{str(date_type).lower()}{str(date_hours_savename).lower()}',
            f'{str(frange_save_string).lower()}',
        ] if item]
    )
    save_name = (f'{str(metric1_name).lower()}')
    if metric2_name is not None:
        save_name+=f'_{str(metric2_name).lower()}'
    if thresh and '' not in thresh:
        save_name+=f'_{str(thresholds_save_phrase).lower()}'
    if interp_pts and '' not in interp_pts:
        save_name+=f'_{str(interp_pts_save_string).lower()}'
    save_name+=f'.{str(var_savename).lower()}'
    if level_savename:
        save_name+=f'_{str(level_savename).lower()}'
    save_name+=f'.{str(time_period_savename).lower()}'
    save_name+=f'.{plot_info}'
    save_name+=f'.{str(domain_save_string).lower()}'

    if save_header:
        save_name = f'{save_header}.'+save_name
    save_subdir = os.path.join(
        save_dir, f'{str(plot_group).lower()}', 
        f'{str(time_period_savename).lower()}'
    )
    if not os.path.isdir(save_subdir):
        os.makedirs(save_subdir)
    save_path = os.path.join(save_subdir, save_name+'.png')
    fig.savefig(save_path, dpi=dpi)
    if restart_dir:
        shutil.copy2(
            save_path, 
            os.path.join(
                restart_dir, 
                f'{str(plot_group).lower()}', 
                f'{str(time_period_savename).lower()}', 
                save_name+'.png'
            )
        )
    logger.info(u"\u2713"+f" plot saved successfully as {save_path}")
    plt.close(num)
    logger.info('========================================')


def main():

    # Logging
    log_metplus_dir = '/'
    for subdir in LOG_TEMPLATE.split('/')[:-1]:
        log_metplus_dir = os.path.join(log_metplus_dir, subdir)
    if not os.path.isdir(log_metplus_dir):
        os.makedirs(log_metplus_dir)
    logger = logging.getLogger(LOG_TEMPLATE)
    logger.setLevel(LOG_LEVEL)
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d (%(filename)s:%(lineno)d) %(levelname)s: '
        + '%(message)s',
        '%m/%d %H:%M:%S'
    )
    file_handler = logging.FileHandler(LOG_TEMPLATE, mode='a')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger_info = f"Log file: {LOG_TEMPLATE}"
    print(logger_info)
    logger.info(logger_info)

    if str(EVAL_PERIOD).upper() == 'TEST':
        valid_beg = VALID_BEG
        valid_end = VALID_END
        init_beg = INIT_BEG
        init_end = INIT_END
    else:
        valid_beg = presets.date_presets[EVAL_PERIOD]['valid_beg']
        valid_end = presets.date_presets[EVAL_PERIOD]['valid_end']
        init_beg = presets.date_presets[EVAL_PERIOD]['init_beg']
        init_end = presets.date_presets[EVAL_PERIOD]['init_end']
    if str(DATE_TYPE).upper() == 'VALID':
        date_beg = valid_beg
        date_end = valid_end
        date_hours = VALID_HOURS
        date_type_string = DATE_TYPE
    elif str(DATE_TYPE).upper() == 'INIT':
        date_beg = init_beg
        date_end = init_end
        date_hours = INIT_HOURS
        date_type_string = 'Initialization'
    else:
        e = (f"FATAL ERROR: Invalid DATE_TYPE: {str(date_type).upper()}. Valid values are"
             + f" VALID or INIT")
        logger.error(e)
        raise ValueError(e)

    logger.debug('========================================')
    logger.debug("Config file settings")
    logger.debug(f"LOG_LEVEL: {LOG_LEVEL}")
    logger.debug(f"MET_VERSION: {MET_VERSION}")
    logger.debug(f"IMG_HEADER: {IMG_HEADER if IMG_HEADER else 'No header'}")
    logger.debug(f"STAT_OUTPUT_BASE_DIR: {STAT_OUTPUT_BASE_DIR}")
    logger.debug(f"STATS_DIR: {STATS_DIR}")
    logger.debug(f"PRUNE_DIR: {PRUNE_DIR}")
    logger.debug(f"SAVE_DIR: {SAVE_DIR}")
    logger.debug(f"RESTART_DIR: {RESTART_DIR}")
    logger.debug(f"VERIF_CASETYPE: {VERIF_CASETYPE}")
    logger.debug(f"MODELS: {MODELS}")
    logger.debug(f"VARIABLES: {VARIABLES}")
    logger.debug(f"DOMAINS: {DOMAINS}")
    logger.debug(f"INTERP: {INTERP}")
    logger.debug(f"DATE_TYPE: {DATE_TYPE}")
    logger.debug(
        f"EVAL_PERIOD: {EVAL_PERIOD}"
    )
    logger.debug(
        f"{DATE_TYPE}_BEG: {date_beg}"
    )
    logger.debug(
        f"{DATE_TYPE}_END: {date_end}"
    )
    logger.debug(f"VALID_HOURS: {VALID_HOURS}")
    logger.debug(f"INIT_HOURS: {INIT_HOURS}")
    logger.debug(f"FCST_LEADS: {FLEADS}")
    logger.debug(f"FCST_LEVELS: {FCST_LEVELS}")
    logger.debug(f"OBS_LEVELS: {OBS_LEVELS}")
    logger.debug(
        f"FCST_THRESH: {FCST_THRESH if FCST_THRESH else 'No thresholds'}"
    )
    logger.debug(
        f"OBS_THRESH: {OBS_THRESH if OBS_THRESH else 'No thresholds'}"
    )
    logger.debug(f"LINE_TYPE: {LINE_TYPE}")
    logger.debug(f"METRICS: {METRICS}")
    logger.debug(f"CONFIDENCE_INTERVALS: {CONFIDENCE_INTERVALS}")
    logger.debug(f"INTERP_PNTS: {INTERP_PNTS if INTERP_PNTS else 'No interpolation points'}")

    logger.debug('----------------------------------------')
    logger.debug(f"Advanced settings (configurable in {SETTINGS_DIR}/settings.py)")
    logger.debug(f"Y_MIN_LIMIT: {Y_MIN_LIMIT}")
    logger.debug(f"Y_MAX_LIMIT: {Y_MAX_LIMIT}")
    logger.debug(f"Y_LIM_LOCK: {Y_LIM_LOCK}")
    logger.debug(f"X_MIN_LIMIT: Ignored for time series plots")
    logger.debug(f"X_MAX_LIMIT: Ignored for time series plots")
    logger.debug(f"X_LIM_LOCK: Ignored for time series plots")
    logger.debug(f"Display averages? {'yes' if display_averages else 'no'}")
    logger.debug(
        f"Clear prune directories? {'yes' if clear_prune_dir else 'no'}"
    )
    logger.debug(f"Plot upper-left logo? {'yes' if plot_logo_left else 'no'}")
    logger.debug(
        f"Plot upper-right logo? {'yes' if plot_logo_right else 'no'}"
    )
    logger.debug(f"Upper-left logo path: {path_logo_left}")
    logger.debug(f"Upper-right logo path: {path_logo_right}")
    logger.debug(
        f"Upper-left logo fraction of original size: {zoom_logo_left}"
    )
    logger.debug(
        f"Upper-right logo fraction of original size: {zoom_logo_right}"
    )
    if CONFIDENCE_INTERVALS:
        logger.debug(f"Confidence Level: {int(ci_lev*100)}%")
        logger.debug(f"Bootstrap method: {bs_method}")
        logger.debug(f"Bootstrap repetitions: {bs_nrep}")
        logger.debug(
            f"Minimum sample size for confidence intervals: {bs_min_samp}"
        )
    logger.debug('========================================')

    date_range = (
        datetime.strptime(date_beg, '%Y%m%d'), 
        datetime.strptime(date_end, '%Y%m%d')+td(days=1)-td(milliseconds=1)
    )
    if len(METRICS) == 1:
        metrics = (METRICS[0], None)
    elif len(METRICS) > 1:
        metrics = METRICS[:2]
    else:
        e = (f"FATAL ERROR: Received no list of metrics.  Check that, for the METRICS"
             + f" setting, a comma-separated string of at least one metric is"
             + f" provided")
        logger.error(e)
        raise ValueError(e)
    fcst_thresh_symbol, fcst_thresh_letter = list(
        zip(*[plot_util.format_thresh(thresh) for thresh in FCST_THRESH])
    )
    obs_thresh_symbol, obs_thresh_letter = list(
        zip(*[plot_util.format_thresh(thresh) for thresh in OBS_THRESH])
    )
    num=0
    e = ''
    if str(VERIF_CASETYPE).lower() not in list(reference.case_type.keys()):
        e = (f"FATAL ERROR: The requested verification case/type combination is not valid:"
             + f" {VERIF_CASETYPE}")
    elif str(LINE_TYPE).upper() not in list(
            reference.case_type[str(VERIF_CASETYPE).lower()].keys()):
        e = (f"FATAL ERROR: The requested line_type is not valid for {VERIF_CASETYPE}:"
             + f" {LINE_TYPE}")
    else:
        case_specs = (
            reference.case_type
            [str(VERIF_CASETYPE).lower()]
            [str(LINE_TYPE).upper()]
        )
    if e:
        logger.error(e)
        logger.error("Quitting ...")
        raise ValueError(e+"\nQuitting ...")
    if (str(INTERP).upper()
            not in case_specs['interp'].replace(' ','').split(',')):
        e = (f"FATAL ERROR: The requested interp method is not valid for the"
             + f" requested case type ({VERIF_CASETYPE}) and"
             + f" line_type ({LINE_TYPE}): {INTERP}")
        logger.error(e)
        logger.error("Quitting ...")
        raise ValueError(e+"\nQuitting ...")
    for metric in metrics:
        if metric is not None:
            if (str(metric).lower() 
                    not in case_specs['plot_stats_list']
                    .replace(' ','').split(',')):
                e = (f"The requested metric is not valid for the"
                     + f" requested case type ({VERIF_CASETYPE}) and"
                     + f" line_type ({LINE_TYPE}): {metric}")
                logger.warning(e)
                logger.warning("Continuing ...")
                continue
    for requested_var in VARIABLES:
        if requested_var in list(case_specs['var_dict'].keys()):
            var_specs = case_specs['var_dict'][requested_var]
        else:
            e = (f"The requested variable is not valid for the requested case"
                 + f" type ({VERIF_CASETYPE}) and line_type ({LINE_TYPE}):"
                 + f" {requested_var}")
            logger.warning(e)
            logger.warning("Continuing ...")
            continue
        fcst_var_names = var_specs['fcst_var_names']
        obs_var_names = var_specs['obs_var_names']
        symbol_keep = []
        letter_keep = []
        for fcst_thresh, obs_thresh in list(
                zip(*[fcst_thresh_symbol, obs_thresh_symbol])):
            if (fcst_thresh in var_specs['fcst_var_thresholds']
                    and obs_thresh in var_specs['obs_var_thresholds']):
                symbol_keep.append(True)
            else:
                symbol_keep.append(False)
        for fcst_thresh, obs_thresh in list(
                zip(*[fcst_thresh_letter, obs_thresh_letter])):
            if (fcst_thresh in var_specs['fcst_var_thresholds']
                    and obs_thresh in var_specs['obs_var_thresholds']):
                letter_keep.append(True)
            else:
                letter_keep.append(False)
        keep = np.add(letter_keep, symbol_keep)
        dropped_items = np.array(FCST_THRESH)[~keep].tolist()
        fcst_thresh = np.array(FCST_THRESH)[keep].tolist()
        obs_thresh = np.array(OBS_THRESH)[keep].tolist()
        if dropped_items:
            dropped_items_string = ', '.join(dropped_items)
            e = (f"The requested thresholds are not valid for the requested"
                 + f" case type ({VERIF_CASETYPE}) and line_type"
                 + f" ({LINE_TYPE}): {dropped_items_string}")
            logger.warning(e)
            logger.warning("Continuing ...")
        plot_group = var_specs['plot_group']
        if FCST_LEVELS in presets.level_presets:
            fcst_levels = re.split(r',(?![0*])', presets.level_presets[FCST_LEVELS].replace(' ',''))
        else:
            fcst_levels = re.split(r',(?![0*])', FCST_LEVELS.replace(' ',''))
        if OBS_LEVELS in presets.level_presets:
            obs_levels = re.split(r',(?![0*])', presets.level_presets[OBS_LEVELS].replace(' ',''))
        else:
            obs_levels = re.split(r',(?![0*])', OBS_LEVELS.replace(' ',''))
        for l, fcst_level in enumerate(fcst_levels):
            if len(fcst_levels) != len(obs_levels):
                e = ("FATAL ERROR: FCST_LEVELS and OBS_LEVELS must be lists of the same"
                     + f" size")
                logger.error(e)
                logger.error("Quitting ...")
                raise ValueError(e+"\nQuitting ...")
            if (fcst_levels[l] not in var_specs['fcst_var_levels'] 
                    or obs_levels[l] not in var_specs['obs_var_levels']):
                e = (f"The requested variable/level combination is not valid: "
                     + f"{requested_var}/{level}")
                logger.warning(e)
                continue
            for domain in DOMAINS:
                if str(domain) not in case_specs['vx_mask_list']:
                    e = (f"The requested domain is not valid for the"
                         + f" requested case type ({VERIF_CASETYPE}) and"
                         + f" line_type ({LINE_TYPE}): {domain}")
                    logger.warning(e)
                    logger.warning("Continuing ...")
                    continue
                df = df_preprocessing.get_preprocessed_data(
                    logger, STATS_DIR, PRUNE_DIR, OUTPUT_BASE_TEMPLATE, VERIF_CASE, 
                    VERIF_TYPE, LINE_TYPE, DATE_TYPE, date_range, EVAL_PERIOD, 
                    date_hours, FLEADS, requested_var, fcst_var_names, 
                    obs_var_names, MODELS, domain, INTERP, INTERP_PNTS, MET_VERSION, 
                    clear_prune_dir
                )
                if df is None:
                    continue
                plot_time_series(
                    df, logger, date_range, MODELS, num=num, flead=FLEADS, 
                    level=fcst_level, thresh=fcst_thresh, 
                    metric1_name=metrics[0], metric2_name=metrics[1], 
                    date_type=DATE_TYPE, y_min_limit=Y_MIN_LIMIT, 
                    y_max_limit=Y_MAX_LIMIT, y_lim_lock=Y_LIM_LOCK, 
                    xlabel=f'{str(date_type_string).capitalize()} Date', 
                    verif_type=VERIF_TYPE, date_hours=date_hours, 
                    line_type=LINE_TYPE, save_dir=SAVE_DIR, 
                    restart_dir=RESTART_DIR, eval_period=EVAL_PERIOD, 
                    display_averages=display_averages, 
                    keep_shared_events_only=keep_shared_events_only,
                    save_header=IMG_HEADER, plot_group=plot_group,
                    confidence_intervals=CONFIDENCE_INTERVALS,
                    interp_pts=INTERP_PNTS,
                    bs_nrep=bs_nrep, bs_method=bs_method, ci_lev=ci_lev,
                    bs_min_samp=bs_min_samp,
                    sample_equalization=sample_equalization,
                    plot_logo_left=plot_logo_left,
                    plot_logo_right=plot_logo_right,
                    path_logo_left=path_logo_left,
                    path_logo_right=path_logo_right,
                    zoom_logo_left=zoom_logo_left,
                    zoom_logo_right=zoom_logo_right,
                    aggregate_dates_by=aggregate_dates_by,
                    running_mean=running_mean
                )
                num+=1


# ============ START USER CONFIGURATIONS ================

if __name__ == "__main__":
    print("\n=================== CHECKING CONFIG VARIABLES =====================\n")
    LOG_TEMPLATE = check_LOG_TEMPLATE(os.environ['LOG_TEMPLATE'])
    LOG_LEVEL = check_LOG_LEVEL(os.environ['LOG_LEVEL'])
    MET_VERSION = check_MET_VERSION(os.environ['MET_VERSION'])
    IMG_HEADER = check_IMG_HEADER(os.environ['IMG_HEADER'])
    VERIF_CASE = check_VERIF_CASE(os.environ['VERIF_CASE'])
    VERIF_TYPE = check_VERIF_TYPE(os.environ['VERIF_TYPE'])
    STAT_OUTPUT_BASE_DIR = check_STAT_OUTPUT_BASE_DIR(os.environ['STAT_OUTPUT_BASE_DIR'])
    STATS_DIR = STAT_OUTPUT_BASE_DIR
    PRUNE_DIR = check_PRUNE_DIR(os.environ['PRUNE_DIR'])
    SAVE_DIR = check_SAVE_DIR(os.environ['SAVE_DIR'])
    if 'RESTART_DIR' in os.environ:
        RESTART_DIR = check_RESTART_DIR(os.environ['RESTART_DIR'])
    else:
        RESTART_DIR = ''
    DATE_TYPE = check_DATE_TYPE(os.environ['DATE_TYPE'])
    LINE_TYPE = check_LINE_TYPE(os.environ['LINE_TYPE'])
    INTERP = check_INTERP(os.environ['INTERP'])
    MODELS = check_MODELS(os.environ['MODELS']).replace(' ','').split(',')
    DOMAINS = check_VX_MASK_LIST(os.environ['VX_MASK_LIST']).replace(' ','').split(',')

    # valid hour (each plot will use all available valid_hours listed below)
    VALID_HOURS = check_FCST_VALID_HOUR(os.environ['FCST_VALID_HOUR'], DATE_TYPE).replace(' ','').split(',')
    INIT_HOURS = check_FCST_INIT_HOUR(os.environ['FCST_INIT_HOUR'], DATE_TYPE).replace(' ','').split(',')

    # time period to cover (inclusive)
    EVAL_PERIOD = check_EVAL_PERIOD(os.environ['EVAL_PERIOD'])
    VALID_BEG = check_VALID_BEG(os.environ['VALID_BEG'], DATE_TYPE, EVAL_PERIOD, plot_type='time_series')
    VALID_END = check_VALID_END(os.environ['VALID_END'], DATE_TYPE, EVAL_PERIOD, plot_type='time_series')
    INIT_BEG = check_INIT_BEG(os.environ['INIT_BEG'], DATE_TYPE, EVAL_PERIOD, plot_type='time_series')
    INIT_END = check_INIT_END(os.environ['INIT_END'], DATE_TYPE, EVAL_PERIOD, plot_type='time_series')

    # list of variables
    # Options: {'TMP','HGT','CAPE','RH','DPT','UGRD','VGRD','UGRD_VGRD','TCDC',
    #           'VIS'}
    VARIABLES = check_var_name(os.environ['var_name']).replace(' ','').split(',')

    # list of lead hours
    # Options: {list of lead hours; string, 'all'; tuple, start/stop flead; 
    #           string, single flead}
    FLEADS = check_FCST_LEAD(os.environ['FCST_LEAD']).replace(' ','').split(',')

    # list of levels
    FCST_LEVELS = check_FCST_LEVEL(os.environ['FCST_LEVEL'])
    OBS_LEVELS = check_OBS_LEVEL(os.environ['OBS_LEVEL'])

    FCST_THRESH = check_FCST_THRESH(os.environ['FCST_THRESH'], LINE_TYPE)
    OBS_THRESH = check_OBS_THRESH(os.environ['OBS_THRESH'], FCST_THRESH, LINE_TYPE).replace(' ','').split(',')
    FCST_THRESH = FCST_THRESH.replace(' ','').split(',')
    
    # requires two metrics to plot
    METRICS = list(filter(None, check_STATS(os.environ['STATS']).replace(' ','').split(',')))

    # set the lowest possible lower (and highest possible upper) axis limits. 
    # E.g.: If Y_LIM_LOCK == True, use Y_MIN_LIMIT as the definitive lower 
    # limit (ditto with Y_MAX_LIMIT)
    # If Y_LIM_LOCK == False, then allow lower and upper limits to adjust to 
    # data as long as limits don't overcome Y_MIN_LIMIT or Y_MAX_LIMIT 
    Y_MIN_LIMIT = toggle.plot_settings['y_min_limit']
    Y_MAX_LIMIT = toggle.plot_settings['y_max_limit']
    Y_LIM_LOCK = toggle.plot_settings['y_lim_lock']


    # configure CIs
    CONFIDENCE_INTERVALS = check_CONFIDENCE_INTERVALS(os.environ['CONFIDENCE_INTERVALS']).replace(' ','')
    bs_nrep = toggle.plot_settings['bs_nrep']
    bs_method = toggle.plot_settings['bs_method']
    ci_lev = toggle.plot_settings['ci_lev']
    bs_min_samp = toggle.plot_settings['bs_min_samp']

    # list of points used in interpolation method
    INTERP_PNTS = check_INTERP_PTS(os.environ['INTERP_PNTS']).replace(' ','').split(',')

    # At each value of the independent variable, whether or not to remove
    # samples used to aggregate each statistic if the samples are not shared
    # by all models.  Required to display sample sizes
    sample_equalization = toggle.plot_settings['sample_equalization']

    # Whether or not to display average values beside legend labels
    display_averages = toggle.plot_settings['display_averages']

    # Whether or not to display events shared among some but not all models
    keep_shared_events_only = toggle.plot_settings['keep_shared_events_only']

    # Interval at which dates are aggregated, empty for no aggregation
    aggregate_dates_by = toggle.plot_settings['aggregate_dates_by']

    # Whether or not to display running means, averaged across given period
    running_mean = toggle.plot_settings['running_mean']

    # Whether or not to clear the intermediate directory that stores pruned data
    clear_prune_dir = toggle.plot_settings['clear_prune_directory']

    # Information about logos
    plot_logo_left = toggle.plot_settings['plot_logo_left']
    plot_logo_right = toggle.plot_settings['plot_logo_right']
    zoom_logo_left = toggle.plot_settings['zoom_logo_left']
    zoom_logo_right = toggle.plot_settings['zoom_logo_right']
    path_logo_left = paths.logo_left_path
    path_logo_right = paths.logo_right_path

    OUTPUT_BASE_TEMPLATE = os.environ['STAT_OUTPUT_BASE_TEMPLATE']

    print("\n===================================================================\n")
    # ============= END USER CONFIGURATIONS =================

    LOG_TEMPLATE = str(LOG_TEMPLATE)
    LOG_LEVEL = str(LOG_LEVEL)
    MET_VERSION = float(MET_VERSION)
    VALID_HOURS = [
        int(valid_hour) if valid_hour else None for valid_hour in VALID_HOURS
    ]
    INIT_HOURS = [
        int(init_hour) if init_hour else None for init_hour in INIT_HOURS
    ]
    FLEADS = [int(flead) for flead in FLEADS]
    INTERP_PNTS = [str(pts) for pts in INTERP_PNTS]
    VERIF_CASETYPE = str(VERIF_CASE).lower() + '_' + str(VERIF_TYPE).lower()
    CONFIDENCE_INTERVALS = str(CONFIDENCE_INTERVALS).lower() in [
        'true', '1', 't', 'y', 'yes'
    ]
    main()