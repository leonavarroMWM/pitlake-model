# -*- coding: utf-8 -*-
"""
Pit Lake Model Engine (Numba JIT Compiled RK4)
Designed for extreme-speed Monte Carlo simulations with exact flux integration.
"""

import pandas as pd
import numpy as np
import copy
from numba import njit

@njit(fastmath=True)
def _get_rates(V, rain_rate, evap_rate, stage_mRL, stage_area, stage_volume_lookup, stage_mRL_lookup, 
               pit_crest_area, pitwall_runoff_coeff, external_catchment_area, catchment_runoff_coeff, 
               regional_gw_level, hydraulic_conductivity, gw_distance, pumping_rate):
    """Calculates derivatives (rates) for a given volume state. Compiled to machine code."""
    
    # Interpolate current L and A
    L = np.interp(V, stage_volume_lookup, stage_mRL_lookup)
    A = np.interp(L, stage_mRL, stage_area)

    # Inflow Rates (m3/day)
    r_rain = A * rain_rate
    r_wall = max(0.0, pit_crest_area - A) * rain_rate * pitwall_runoff_coeff
    r_catch = external_catchment_area * rain_rate * catchment_runoff_coeff
    
    # Groundwater
    gw_diff = regional_gw_level - L
    dyn_cond = (hydraulic_conductivity / gw_distance) * A
    r_gw_in = max(0.0, dyn_cond * gw_diff)
    r_gw_out = max(0.0, -dyn_cond * gw_diff)

    # Outflow Rates (m3/day)
    r_evap = A * evap_rate
    
    net_rate = r_rain + r_wall + r_catch + r_gw_in - r_evap - r_gw_out - pumping_rate
    
    # Return flat values for Numba optimization
    return net_rate, r_rain, r_wall, r_catch, r_gw_in, r_evap, r_gw_out, pumping_rate

@njit(fastmath=True)
def _run_core_loop_numba(
    rainfall_m_day, evaporation_m_day, days_in_step,
    stage_mRL, stage_area, stage_volume_from_mRL, stage_volume_lookup, stage_mRL_lookup,
    initial_level, pit_crest_area, pitwall_runoff_coeff, external_catchment_area,
    catchment_runoff_coeff, regional_gw_level, hydraulic_conductivity, gw_distance, pumping_rate,
    min_volume, max_volume
):
    n_steps = len(rainfall_m_day)
    
    # Result Arrays (pre-allocated for speed)
    out_level = np.zeros(n_steps)
    out_volume = np.zeros(n_steps)
    out_net_flow = np.zeros(n_steps)
    out_fluxes = np.zeros((7, n_steps)) # rain, wall, catch, gw_in, evap, gw_out, pump

    current_volume = np.interp(initial_level, stage_mRL, stage_volume_from_mRL)
    current_volume = max(min_volume, min(max_volume, current_volume))
    
    for i in range(n_steps):
        dt = days_in_step[i]
        r_rain = rainfall_m_day[i]
        r_evap = evaporation_m_day[i]

        # RK4 Step 1
        k1, f1_0, f1_1, f1_2, f1_3, f1_4, f1_5, f1_6 = _get_rates(
            current_volume, r_rain, r_evap, stage_mRL, stage_area, stage_volume_lookup, stage_mRL_lookup,
            pit_crest_area, pitwall_runoff_coeff, external_catchment_area, catchment_runoff_coeff, 
            regional_gw_level, hydraulic_conductivity, gw_distance, pumping_rate
        )
        
        # RK4 Step 2
        v2 = max(min_volume, min(max_volume, current_volume + 0.5 * dt * k1))
        k2, f2_0, f2_1, f2_2, f2_3, f2_4, f2_5, f2_6 = _get_rates(
            v2, r_rain, r_evap, stage_mRL, stage_area, stage_volume_lookup, stage_mRL_lookup,
            pit_crest_area, pitwall_runoff_coeff, external_catchment_area, catchment_runoff_coeff, 
            regional_gw_level, hydraulic_conductivity, gw_distance, pumping_rate
        )

        # RK4 Step 3
        v3 = max(min_volume, min(max_volume, current_volume + 0.5 * dt * k2))
        k3, f3_0, f3_1, f3_2, f3_3, f3_4, f3_5, f3_6 = _get_rates(
            v3, r_rain, r_evap, stage_mRL, stage_area, stage_volume_lookup, stage_mRL_lookup,
            pit_crest_area, pitwall_runoff_coeff, external_catchment_area, catchment_runoff_coeff, 
            regional_gw_level, hydraulic_conductivity, gw_distance, pumping_rate
        )

        # RK4 Step 4
        v4 = max(min_volume, min(max_volume, current_volume + dt * k3))
        k4, f4_0, f4_1, f4_2, f4_3, f4_4, f4_5, f4_6 = _get_rates(
            v4, r_rain, r_evap, stage_mRL, stage_area, stage_volume_lookup, stage_mRL_lookup,
            pit_crest_area, pitwall_runoff_coeff, external_catchment_area, catchment_runoff_coeff, 
            regional_gw_level, hydraulic_conductivity, gw_distance, pumping_rate
        )

        # Average rates
        net_rate = (k1 + 2*k2 + 2*k3 + k4) / 6.0

        # Update state
        current_volume = max(min_volume, min(max_volume, current_volume + net_rate * dt))
        current_level = np.interp(current_volume, stage_volume_lookup, stage_mRL_lookup)

        # Store results
        out_volume[i] = current_volume
        out_level[i] = current_level
        out_net_flow[i] = net_rate
        
        # Integrate fluxes properly using RK4 weights, multiply by dt for total volume
        out_fluxes[0, i] = ((f1_0 + 2*f2_0 + 2*f3_0 + f4_0) / 6.0) * dt # Rain
        out_fluxes[1, i] = ((f1_1 + 2*f2_1 + 2*f3_1 + f4_1) / 6.0) * dt # Wall
        out_fluxes[2, i] = ((f1_2 + 2*f2_2 + 2*f3_2 + f4_2) / 6.0) * dt # Catchment
        out_fluxes[3, i] = ((f1_3 + 2*f2_3 + 2*f3_3 + f4_3) / 6.0) * dt # GW In
        out_fluxes[4, i] = ((f1_4 + 2*f2_4 + 2*f3_4 + f4_4) / 6.0) * dt # Evap
        out_fluxes[5, i] = ((f1_5 + 2*f2_5 + 2*f3_5 + f4_5) / 6.0) * dt # GW Out
        out_fluxes[6, i] = ((f1_6 + 2*f2_6 + 2*f3_6 + f4_6) / 6.0) * dt # Pumping

    return (out_level, out_volume, out_fluxes[0], out_fluxes[1], out_fluxes[2], 
            out_fluxes[3], out_fluxes[4], out_fluxes[5], out_fluxes[6], out_net_flow)


class PitLakeModel:
    def __init__(self, staging_data, pit_crest_area, external_catchment_area,
                 pitwall_runoff_coeff, catchment_runoff_coeff, regional_gw_level,
                 hydraulic_conductivity, gw_distance, monthly_rainfall, monthly_evaporation,
                 pumping_rate=0.0):
        
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
        self.hydraulic_conductivity = float(hydraulic_conductivity)
        self.gw_distance = float(gw_distance)
        self.monthly_rainfall_mm = list(monthly_rainfall)
        self.monthly_evaporation_mm = list(monthly_evaporation)
        self.pumping_rate = float(pumping_rate)
        
        self.min_volume = float(self.stage_volume_lookup.min())
        self.max_volume = float(self.stage_volume_lookup.max())

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

        # Call the NUMBA-compiled RK4 loop
        res = _run_core_loop_numba(
            rain_rates, evap_rates, days_in_step,
            self.stage_mRL, self.stage_area, self.stage_volume_from_mRL,
            self.stage_volume_lookup, self.stage_mRL_lookup,
            initial_level_mRL, self.pit_crest_area, self.pitwall_runoff_coeff,
            self.external_catchment_area, self.catchment_runoff_coeff,
            self.regional_gw_level, self.hydraulic_conductivity, self.gw_distance, self.pumping_rate,
            self.min_volume, self.max_volume
        )
        
        cols = ['level_mRL', 'volume_m3', 'in_direct_rain_m3', 'in_pitwall_runoff_m3',
                'in_catchment_runoff_m3', 'in_groundwater_m3', 'out_evaporation_m3',
                'out_groundwater_m3', 'out_pumping_m3', 'net_flow_rate_m3_day']
        
        return pd.DataFrame(dict(zip(cols, res)), index=dates)

def run_monte_carlo(base_params, base_rainfall, base_evaporation, params_to_vary, n_runs,
                    start_date, end_date, initial_level_mRL, status_callback=None):
    
    if status_callback: status_callback(f"Starting Monte Carlo ({n_runs} runs, Numba Accelerated)...")
    
    vars_to_track = ['level_mRL', 'volume_m3', 'in_direct_rain_m3', 'in_pitwall_runoff_m3',
                     'in_catchment_runoff_m3', 'in_groundwater_m3', 'out_evaporation_m3',
                     'out_groundwater_m3', 'out_pumping_m3']
    all_results = {v: [] for v in vars_to_track}

    for i in range(n_runs):
        if status_callback and (i % 50 == 0): status_callback(f"Running iteration {i+1}/{n_runs}...")
        
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
            qs = df.quantile([0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95], axis=1).T
            qs.columns = ['P05', 'P10', 'P25', 'P50', 'P75', 'P90', 'P95']
            percentile_results[v] = qs

    if status_callback: status_callback("Monte Carlo simulation finished.")
    return percentile_results