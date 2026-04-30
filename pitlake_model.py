# -*- coding: utf-8 -*-
"""
Pit Lake Model Engine (RK4 Monthly)
Updated with P05 and P95 percentiles.
"""

import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
import copy

def _get_flux_rates(
    current_volume, rain_rate, evap_rate,
    stage_mRL, stage_area, stage_volume_lookup, stage_mRL_lookup,
    pit_crest_area, pitwall_runoff_coeff, external_catchment_area,
    catchment_runoff_coeff, regional_gw_level, k_bulk, pumping_rate
):
    """ Helper: Calculates all flux rates (m3/day) at a specific state. """
    current_level = np.interp(current_volume, stage_volume_lookup, stage_mRL_lookup)
    current_area = np.interp(current_level, stage_mRL, stage_area)
    dynamic_conductance = k_bulk * current_area

    in_direct_rain = current_area * rain_rate
    exposed_pitwall = max(0.0, pit_crest_area - current_area)
    in_pitwall_runoff = exposed_pitwall * rain_rate * pitwall_runoff_coeff
    in_catchment_runoff = external_catchment_area * rain_rate * catchment_runoff_coeff
    
    gw_diff = regional_gw_level - current_level
    in_gw = max(0.0, dynamic_conductance * gw_diff)
    out_gw = max(0.0, -dynamic_conductance * gw_diff)
    
    out_evap = current_area * evap_rate
    
    net_rate = (in_direct_rain + in_pitwall_runoff + in_catchment_runoff + in_gw) - (out_evap + out_gw + pumping_rate)
    
    return (net_rate, in_direct_rain, in_pitwall_runoff, in_catchment_runoff, in_gw, out_evap, out_gw, pumping_rate)

def _run_core_loop_rk4(
    rainfall_m_day, evaporation_m_day, days_in_step,
    stage_mRL, stage_area, stage_volume_from_mRL, stage_volume_lookup, stage_mRL_lookup,
    initial_level, pit_crest_area, pitwall_runoff_coeff, external_catchment_area,
    catchment_runoff_coeff, regional_gw_level, lake_conductance, pumping_rate,
    min_volume, max_volume
):
    n_steps = len(rainfall_m_day)
    
    # Result Arrays
    out_level = np.empty(n_steps, dtype=np.float64)
    out_volume = np.empty(n_steps, dtype=np.float64)
    out_net_flow = np.empty(n_steps, dtype=np.float64)
    
    # Flux Arrays (Volumes in m3)
    out_in_direct_rain = np.empty(n_steps, dtype=np.float64)
    out_in_pitwall_runoff = np.empty(n_steps, dtype=np.float64)
    out_in_catchment_runoff = np.empty(n_steps, dtype=np.float64)
    out_in_groundwater = np.empty(n_steps, dtype=np.float64)
    out_out_evaporation = np.empty(n_steps, dtype=np.float64)
    out_out_groundwater = np.empty(n_steps, dtype=np.float64)
    out_out_pumping = np.empty(n_steps, dtype=np.float64)
    out_out_overflow = np.empty(n_steps, dtype=np.float64)

    current_level = float(initial_level)
    current_volume = np.interp(current_level, stage_mRL, stage_volume_from_mRL)
    current_volume = max(min_volume, min(max_volume, current_volume))

    for i in range(n_steps):
        dt = days_in_step[i]
        rain_rate = float(rainfall_m_day[i])
        evap_rate = float(evaporation_m_day[i])

        out_level[i] = current_level
        out_volume[i] = current_volume

        args = (stage_mRL, stage_area, stage_volume_lookup, stage_mRL_lookup,
                pit_crest_area, pitwall_runoff_coeff, external_catchment_area,
                catchment_runoff_coeff, regional_gw_level, lake_conductance, pumping_rate)

        # RK4 Integration for ALL components
        k1 = _get_flux_rates(current_volume, rain_rate, evap_rate, *args)
        v1 = max(min_volume, min(max_volume, current_volume + k1[0]*dt/2))
        
        k2 = _get_flux_rates(v1, rain_rate, evap_rate, *args)
        v2 = max(min_volume, min(max_volume, current_volume + k2[0]*dt/2))
        
        k3 = _get_flux_rates(v2, rain_rate, evap_rate, *args)
        v3 = max(min_volume, min(max_volume, current_volume + k3[0]*dt))
        
        k4 = _get_flux_rates(v3, rain_rate, evap_rate, *args)

        # Helper to apply the RK4 weighted average to any specific flux index
        def rk4_avg(idx):
            return (k1[idx] + 2*k2[idx] + 2*k3[idx] + k4[idx]) / 6.0

        # Store as VOLUMES (Weighted Rate * dt)
        net_rate = rk4_avg(0)
        out_in_direct_rain[i] = rk4_avg(1) * dt
        out_in_pitwall_runoff[i] = rk4_avg(2) * dt
        out_in_catchment_runoff[i] = rk4_avg(3) * dt
        out_in_groundwater[i] = rk4_avg(4) * dt
        out_out_evaporation[i] = rk4_avg(5) * dt
        out_out_groundwater[i] = rk4_avg(6) * dt
        out_out_pumping[i] = rk4_avg(7) * dt

        # --- NEW: Overflow Logic ---
        raw_new_volume = current_volume + (net_rate * dt)
        if raw_new_volume > max_volume:
            out_out_overflow[i] = raw_new_volume - max_volume
            new_volume = max_volume
        else:
            out_out_overflow[i] = 0.0
            new_volume = max(min_volume, raw_new_volume)

        out_net_flow[i] = net_rate

        current_volume = new_volume
        current_level = np.interp(current_volume, stage_volume_lookup, stage_mRL_lookup)

    return (out_level, out_volume, out_in_direct_rain, out_in_pitwall_runoff, 
            out_in_catchment_runoff, out_in_groundwater, out_out_evaporation, 
            out_out_groundwater, out_out_pumping, out_out_overflow, out_net_flow) # <-- Added Overflow
class PitLakeModel:
    def __init__(self, staging_data, pit_crest_area, external_catchment_area,
                 pitwall_runoff_coeff, catchment_runoff_coeff, regional_gw_level,
                 lake_conductance, monthly_rainfall, monthly_evaporation,
                 pumping_rate=0.0, spillway_level=406.0): # <-- ADDED HERE
        
        # Geometry
        self.staging_data = staging_data.sort_values(by='mRL').drop_duplicates(subset='mRL')
        self.stage_mRL = self.staging_data['mRL'].values.astype(float)
        self.stage_area = self.staging_data['area_m2'].values.astype(float)
        self.stage_volume_from_mRL = self.staging_data['volume_m3'].values.astype(float)
        
        sv = self.staging_data.drop_duplicates(subset='volume_m3').sort_values('volume_m3')
        self.stage_volume_lookup = sv['volume_m3'].values.astype(float)
        self.stage_mRL_lookup = sv['mRL'].values.astype(float)

        # Params
        self.pit_crest_area = float(pit_crest_area)
        self.external_catchment_area = float(external_catchment_area)
        self.pitwall_runoff_coeff = float(pitwall_runoff_coeff)
        self.catchment_runoff_coeff = float(catchment_runoff_coeff)
        self.regional_gw_level = float(regional_gw_level)
        self.lake_conductance = float(lake_conductance)
        self.monthly_rainfall_mm = list(monthly_rainfall)
        self.monthly_evaporation_mm = list(monthly_evaporation)
        self.pumping_rate = float(pumping_rate)
        self.spillway_level = float(spillway_level) # <-- NEW
        
        self.min_volume = float(self.stage_volume_lookup.min())
        
        # --- NEW: Cap the max volume strictly at the Spillway Elevation ---
        self.max_volume = float(np.interp(self.spillway_level, self.stage_mRL, self.stage_volume_from_mRL))

    def run_model(self, start_date, end_date, initial_level_mRL, quiet=True):
        # Prepare Data (Monthly)
        dates = pd.date_range(start_date, end_date, freq='ME')
        
        if len(dates) == 0:
            raise ValueError("Simulation period too short. Must span at least one month end.")

        df = pd.DataFrame(index=dates)
        df['days'] = df.index.days_in_month
        df['idx'] = df.index.month - 1
        
        rain_mm = np.array([self.monthly_rainfall_mm[i] for i in df['idx']])
        evap_mm = np.array([self.monthly_evaporation_mm[i] for i in df['idx']])
        
        # Rates (m/day)
        rain_rates = (rain_mm / 1000.0) / df['days'].values
        evap_rates = (evap_mm / 1000.0) / df['days'].values
        days_in_step = df['days'].values

        res = _run_core_loop_rk4(
            rain_rates, evap_rates, days_in_step,
            self.stage_mRL, self.stage_area, self.stage_volume_from_mRL,
            self.stage_volume_lookup, self.stage_mRL_lookup,
            initial_level_mRL, self.pit_crest_area, self.pitwall_runoff_coeff,
            self.external_catchment_area, self.catchment_runoff_coeff,
            self.regional_gw_level, self.lake_conductance, self.pumping_rate,
            self.min_volume, self.max_volume
        )
        
        cols = ['level_mRL', 'volume_m3', 'in_direct_rain_m3', 'in_pitwall_runoff_m3',
                'in_catchment_runoff_m3', 'in_groundwater_m3', 'out_evaporation_m3',
                'out_groundwater_m3', 'out_pumping_m3', 'out_overflow_m3', 'net_flow_rate_m3_day']
        
        return pd.DataFrame(dict(zip(cols, res)), index=dates)

def run_monte_carlo(base_params, base_rainfall, base_evaporation, params_to_vary, n_runs,
                    start_date, end_date, initial_level_mRL, status_callback=None):
    
    if status_callback: status_callback(f"Starting Monte Carlo ({n_runs} runs, RK4 Monthly)...")
    
    vars_to_track = ['level_mRL', 'volume_m3', 'in_direct_rain_m3', 'in_pitwall_runoff_m3',
                     'in_catchment_runoff_m3', 'in_groundwater_m3', 'out_evaporation_m3',
                     'out_groundwater_m3', 'out_pumping_m3', 'out_overflow_m3', 'net_flow_rate_m3_day']
    all_results = {v: [] for v in vars_to_track}

    for i in range(n_runs):
        if status_callback and (i % 10 == 0): status_callback(f"Running iteration {i+1}/{n_runs}...")
        
        p_params = copy.deepcopy(base_params)
        p_rain = list(base_rainfall)
        p_evap = list(base_evaporation)

        for param, variation in params_to_vary.items():
            factor = np.random.normal(1.0, variation)
            if param == 'rainfall': p_rain = [max(0, x*factor) for x in base_rainfall]
            elif param == 'evaporation': p_evap = [max(0, x*factor) for x in base_evaporation]
            elif param in p_params:
                try:
                    val = float(p_params[param])
                    p_params[param] = max(0, np.random.normal(val, val*variation))
                except: pass

        model = PitLakeModel(monthly_rainfall=p_rain, monthly_evaporation=p_evap, **p_params)
        try:
            res = model.run_model(start_date, end_date, initial_level_mRL)
            for v in vars_to_track:
                all_results[v].append(res[v])
        except Exception as e:
            if status_callback: status_callback(f"Error in run {i+1}: {e}")
            continue

    if status_callback: status_callback("Calculating percentiles...")
    
    percentile_results = {}
    for v, res_list in all_results.items():
        if res_list:
            df = pd.concat(res_list, axis=1)
            # --- UPDATED PERCENTILES (P05 and P95 added) ---
            qs = df.quantile([0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95], axis=1).T
            qs.columns = ['P05', 'P10', 'P25', 'P50', 'P75', 'P90', 'P95']
            percentile_results[v] = qs

    if status_callback: status_callback("Monte Carlo simulation finished.")
    return percentile_results