# -*- coding: utf-8 -*-
"""
Pit Lake Model Interactive Dashboard
v15
"""

import pandas as pd
import numpy as np
import traceback
import threading
import time
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import panel as pn
from io import BytesIO

# Initialize extensions (mathjax is required for the equations)
pn.extension('plotly', 'tabulator', 'mathjax')

# --- Import Custom Modules ---
try:
    from pitlake_model import PitLakeModel, run_monte_carlo
    from report_generator import generate_html_report
except Exception as e:
    print(f"FATAL ERROR: Missing modules. {e}")
    raise

# ##################################################################
# --- APP STATE ---
# ##################################################################
class AppState:
    def __init__(self):
        self.results = None
        self.base_params = None
        self.params_to_vary = None
        self.n_runs = 0
        self.start_date = ""
        self.end_date = ""
        self.fig_level = None
        self.fig_inflow = None
        self.fig_outflow = None
        self.annual_tables_dict = {} 
        self.df_prob_summary = None
        self.current_staging_df = None
        self.current_met_df = None

state = AppState()

# ##################################################################
# --- PLOTTING FUNCTIONS (Fixed Hover Labels) ---
# ##################################################################

def create_level_plot_plotly(level_results_df, base_params, staging_df, title_suffix):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    dates = level_results_df.index
    
    # 1. Outer Band (P05 - P95)
    fig.add_trace(go.Scatter(
        x=dates, y=level_results_df['P05'], 
        mode='lines', line=dict(width=0.5, color='rgba(31, 119, 180, 0.3)'), 
        name='P05 (Low)', hovertemplate='%{y:.2f} mRL'
    ), secondary_y=False)
    
    fig.add_trace(go.Scatter(
        x=dates, y=level_results_df['P95'], 
        mode='lines', line=dict(width=0.5, color='rgba(31, 119, 180, 0.3)'), 
        fill='tonexty', fillcolor='rgba(31, 119, 180, 0.1)', 
        name='P95 (High)', hovertemplate='%{y:.2f} mRL'
    ), secondary_y=False)

    # 2. Inner Band (P25 - P75)
    fig.add_trace(go.Scatter(
        x=dates, y=level_results_df['P25'], 
        mode='lines', line=dict(width=1, color='rgba(31, 119, 180, 0.6)'), 
        name='P25', hovertemplate='%{y:.2f} mRL'
    ), secondary_y=False)
    
    fig.add_trace(go.Scatter(
        x=dates, y=level_results_df['P75'], 
        mode='lines', line=dict(width=1, color='rgba(31, 119, 180, 0.6)'), 
        fill='tonexty', fillcolor='rgba(31, 119, 180, 0.2)', 
        name='P75', hovertemplate='%{y:.2f} mRL'
    ), secondary_y=False)

    # 3. Median (P50)
    fig.add_trace(go.Scatter(
        x=dates, y=level_results_df['P50'], 
        mode='lines', line=dict(color='rgb(31, 119, 180)', width=3), 
        name='Median (P50)', hovertemplate='%{y:.2f} mRL'
    ), secondary_y=False)
    
    # 4. GW Reference
    fig.add_trace(go.Scatter(x=[dates[0], dates[-1]], y=[base_params['regional_gw_level'], base_params['regional_gw_level']], mode='lines', line=dict(color='cyan', dash='dash', width=2), name='GW Level'), secondary_y=False)
    
    # 5. Area
    stage_mRL = staging_df['mRL'].values
    stage_area = staging_df['area_m2'].values
    p50_area = np.interp(level_results_df['P50'].values, stage_mRL, stage_area)
    fig.add_trace(go.Scatter(x=dates, y=p50_area, mode='lines', line=dict(color='green', dash='dot', width=1.5), name='Area (P50)', hovertemplate='%{y:,.0f} m²'), secondary_y=True)
    
    fig.update_layout(title=f'Pit Lake Level - {title_suffix}', height=500, margin=dict(l=20, r=20, t=60, b=20), hovermode="x unified")
    fig.update_yaxes(title_text="Level (mRL)", secondary_y=False)
    fig.update_yaxes(title_text="Area (m²)", secondary_y=True, showgrid=False)
    return fig

def create_flux_plot_plotly(percentile_results, var_list, color_rgb, title, title_suffix):
    rows = len(var_list)
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, subplot_titles=[v.replace('_m3', '').replace('_', ' ').title() for v in var_list], vertical_spacing=0.08)
    
    for i, var_name in enumerate(var_list):
        row = i + 1
        df = percentile_results[var_name]
        dates = df.index
        
        # P05-P95
        fig.add_trace(go.Scatter(x=dates, y=df['P05'], mode='lines', line=dict(width=0.5, color=f'rgba({color_rgb}, 0.4)'), name='P05', hovertemplate='%{y:,.0f} m³', showlegend=False), row=row, col=1)
        fig.add_trace(go.Scatter(x=dates, y=df['P95'], mode='lines', line=dict(width=0.5, color=f'rgba({color_rgb}, 0.4)'), fill='tonexty', fillcolor=f'rgba({color_rgb}, 0.1)', name='P95', hovertemplate='%{y:,.0f} m³', showlegend=False), row=row, col=1)
        
        # P25-P75
        fig.add_trace(go.Scatter(x=dates, y=df['P25'], mode='lines', line=dict(width=1, color=f'rgba({color_rgb}, 0.6)'), name='P25', hovertemplate='%{y:,.0f} m³', showlegend=False), row=row, col=1)
        fig.add_trace(go.Scatter(x=dates, y=df['P75'], mode='lines', line=dict(width=1, color=f'rgba({color_rgb}, 0.6)'), fill='tonexty', fillcolor=f'rgba({color_rgb}, 0.25)', name='P75', hovertemplate='%{y:,.0f} m³', showlegend=False), row=row, col=1)
        
        # P50
        fig.add_trace(go.Scatter(x=dates, y=df['P50'], mode='lines', line=dict(color=f'rgb({color_rgb})', width=2), name=f'{var_name} (Median)', hovertemplate='%{y:,.0f} m³', showlegend=False), row=row, col=1)
        
        fig.update_yaxes(title_text="m³", row=row, col=1)
    
    fig.update_layout(title=f'{title} - {title_suffix}', height=300 * rows, margin=dict(l=20, r=20, t=60, b=20), hovermode="x unified")
    return fig

def create_water_balance_table(percentile_results):
    in_rain = percentile_results['in_direct_rain_m3']['P50'].sum()
    in_pitwall = percentile_results['in_pitwall_runoff_m3']['P50'].sum()
    in_catchment = percentile_results['in_catchment_runoff_m3']['P50'].sum()
    in_gw = percentile_results['in_groundwater_m3']['P50'].sum()
    out_evap = percentile_results['out_evaporation_m3']['P50'].sum()
    out_gw = percentile_results['out_groundwater_m3']['P50'].sum()
    out_pump = percentile_results['out_pumping_m3']['P50'].sum()
    total_in = in_rain + in_pitwall + in_catchment + in_gw
    total_out = out_evap + out_gw + out_pump
    net_flux = total_in - total_out
    vol_df = percentile_results['volume_m3']
    delta_storage = vol_df['P50'].iloc[-1] - vol_df['P50'].iloc[0]
    data = {
        "Component": ["IN: Rain", "IN: Pitwall", "IN: Catchment", "IN: GW", "OUT: Evap", "OUT: GW", "OUT: Pump", "---", "Total In", "Total Out", "Net Flux", "Change Storage", "Balance"],
        "Total Volume (m³)": [in_rain, in_pitwall, in_catchment, in_gw, -out_evap, -out_gw, -out_pump, np.nan, total_in, -total_out, net_flux, delta_storage, net_flux - delta_storage]
    }
    return pd.DataFrame(data).set_index("Component")

def create_prob_summary_table(percentile_results):
    vars_map = {
        'Direct Rain': 'in_direct_rain_m3',
        'Pitwall Runoff': 'in_pitwall_runoff_m3',
        'Catchment Runoff': 'in_catchment_runoff_m3',
        'GW Inflow': 'in_groundwater_m3',
        'Evaporation': 'out_evaporation_m3',
        'GW Outflow': 'out_groundwater_m3',
        'Pumping': 'out_pumping_m3'
    }
    data = {}
    for label, var_key in vars_map.items():
        df = percentile_results[var_key]
        data[label] = {
            'P05 (Low)': df['P05'].sum(),
            'P25': df['P25'].sum(),
            'P50 (Median)': df['P50'].sum(),
            'P75': df['P75'].sum(),
            'P95 (High)': df['P95'].sum()
        }
    return pd.DataFrame(data).T

def create_annual_table(percentile_results, p_col='P50'):
    flux_vars = ['in_direct_rain_m3', 'in_pitwall_runoff_m3', 'in_catchment_runoff_m3', 'in_groundwater_m3', 'out_evaporation_m3', 'out_groundwater_m3', 'out_pumping_m3', 'volume_m3']
    annual_dfs = []
    for var in flux_vars:
        if var == 'volume_m3':
            annual_val = percentile_results[var][p_col].resample('A').mean()
        else:
            annual_val = percentile_results[var][p_col].resample('A').sum()
        annual_val.name = var.replace('_m3', '').replace('_', ' ').title()
        annual_dfs.append(annual_val)
    df = pd.concat(annual_dfs, axis=1)
    df.index = df.index.year
    df.index.name = "Year"
    return df

# ##################################################################
# --- WIDGETS ---
# ##################################################################

default_stage_data = {
    'mRL':     [290, 293,   298,   300,    303,    310,317,352,362,406],
    'area_m2':   [0,   8000, 10000, 11200,  13200,18000,23000,58000,70000,120000],
    'volume_m3': [0,   12099, 40287, 57003, 86125, 175837,317807,1790173,2533787,8275415]
}
global_default_staging_df = pd.DataFrame(default_stage_data)

months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
default_rainfall = [212, 168, 172, 195, 209, 218, 183, 204, 248, 277, 230, 248]
default_evap = [130, 101, 76, 37, 17, 7, 11, 25, 45, 71, 98, 119]

df_met_default = pd.DataFrame({
    "Month": months,
    "Rainfall (mm)": default_rainfall,
    "Evaporation (mm)": default_evap
})

header_style = {'font-weight': 'bold', 'font-size': '1.1em', 'margin-top': '15px'}

w_geo_table = pn.widgets.Tabulator(
    global_default_staging_df, show_index=False, sizing_mode='stretch_width',
    disabled=False, configuration={'headerSort': False, 'movableColumns': False} 
)

w_met_table = pn.widgets.Tabulator(
    df_met_default, show_index=False, sizing_mode='stretch_width',
    configuration={'headerSort': False, 'movableColumns': False}, editors={'Month': None}
)

w_crest_area = pn.widgets.FloatInput(name='Pit Crest Area (m²)', value=300000.0)
w_catchment_area = pn.widgets.FloatInput(name='External Catchment Area (m²)', value=1000000.0)
w_pw_coeff = pn.widgets.FloatSlider(name='Pitwall Runoff Coeff (0-1)', start=0, end=1, step=0.01, value=0.6)
w_c_coeff = pn.widgets.FloatSlider(name='Catchment Runoff Coeff (0-1)', start=0, end=1, step=0.01, value=0.3)
w_gw_level = pn.widgets.FloatInput(name='Regional GW Level (mRL)', value=400.0)
w_hyd_conductivity = pn.widgets.FloatInput(name='Hydraulic Conductivity (K, m/day)', value=0.01)
w_gw_distance = pn.widgets.FloatInput(name='Distance to GW Boundary (L, m)', value=100.0)
w_pumping = pn.widgets.FloatInput(name='Pumping Rate (m³/day)', value=0.0)

# Changed from FloatSlider to FloatInput to allow unbounded values (CV > 1)
w_n_runs = pn.widgets.IntInput(name='Number of Runs (N)', value=50, start=1, end=10000, step=10)
w_var_hyd_conductivity = pn.widgets.FloatInput(name='Var: Hyd. Conductivity (CV)', value=0.2, step=0.05)
w_var_pw_coeff = pn.widgets.FloatInput(name='Var: Pitwall Coeff (CV)', value=0.1, step=0.05)
w_var_c_coeff = pn.widgets.FloatInput(name='Var: Catchment Coeff (CV)', value=0.1, step=0.05)
w_var_gw_level = pn.widgets.FloatInput(name='Var: GW Level (CV)', value=0.05, step=0.05)
w_var_rainfall = pn.widgets.FloatInput(name='Var: Rainfall (CV)', value=0.1, step=0.05)
w_var_evap = pn.widgets.FloatInput(name='Var: Evaporation (CV)', value=0.1, step=0.05)

w_start_date = pn.widgets.TextInput(name='Start Date', value='2025-01-01')
w_end_date = pn.widgets.TextInput(name='End Date', value='2030-12-31')
w_initial_level = pn.widgets.FloatInput(name='Initial Level (mRL)', value=290.0)

run_button = pn.widgets.Button(name='1. Run Simulation', button_type='primary', icon='player-play', sizing_mode='stretch_width')
download_button = pn.widgets.FileDownload(
    label='2. Export HTML Report', button_type='success', icon='file-code',
    filename='pit_lake_report.html', disabled=True, sizing_mode='stretch_width'
)
status_text = pn.pane.Alert("Ready to run.", alert_type='info')

plot_pane_level = pn.pane.Plotly(None, sizing_mode='stretch_width', height=500)
plot_pane_inflow = pn.pane.Plotly(None, sizing_mode='stretch_width')
plot_pane_outflow = pn.pane.Plotly(None, sizing_mode='stretch_width')
table_balance = pn.widgets.Tabulator(None, sizing_mode='stretch_width', disabled=True, layout='fit_data')
table_annual = pn.widgets.Tabulator(None, sizing_mode='stretch_width', disabled=True, layout='fit_data')

# ##################################################################
# --- WORKER & LOGIC ---
# ##################################################################

def update_status_safely(doc, msg, alert_type='info'):
    def _update():
        status_text.object = msg
        status_text.alert_type = alert_type
    if doc:
        doc.add_next_tick_callback(_update)

def _simulation_worker(doc, base_params, base_rainfall, base_evap, params_to_vary,
                           n_runs, start_date, end_date, initial_level_mRL,
                           met_df):
    
    def model_progress_callback(msg):
        print(f"STATUS: {msg}")
        update_status_safely(doc, msg, 'info')

    try:
        model_progress_callback("Starting Monte Carlo simulation...")
        
        # RK4 uses monthly steps implicitly
        percentile_results = run_monte_carlo(
            base_params=base_params, base_rainfall=base_rainfall, base_evaporation=base_evap,
            params_to_vary=params_to_vary, n_runs=n_runs, start_date=start_date, end_date=end_date,
            initial_level_mRL=initial_level_mRL, status_callback=model_progress_callback
        )

        model_progress_callback("Generating Plots...")
        active_staging_df = base_params['staging_data']

        title_suffix = f"N={n_runs}, RK4 Monthly"
        fig_level = create_level_plot_plotly(percentile_results['level_mRL'], base_params, active_staging_df, title_suffix)
        fig_inflow = create_flux_plot_plotly(percentile_results, ['in_direct_rain_m3', 'in_pitwall_runoff_m3', 'in_catchment_runoff_m3', 'in_groundwater_m3'], '31, 119, 180', 'Inflows', title_suffix)
        fig_outflow = create_flux_plot_plotly(percentile_results, ['out_evaporation_m3', 'out_groundwater_m3', 'out_pumping_m3'], '214, 39, 40', 'Outflows', title_suffix)
        
        df_balance = create_water_balance_table(percentile_results)
        
        all_annual_tables = {}
        for p_key in ['P05', 'P25', 'P50', 'P75', 'P95']:
            all_annual_tables[p_key] = create_annual_table(percentile_results, p_key)
            
        df_prob = create_prob_summary_table(percentile_results)

        state.results = percentile_results
        state.base_params = base_params
        state.params_to_vary = params_to_vary
        state.n_runs = n_runs
        state.start_date = start_date
        state.end_date = end_date
        state.fig_level = fig_level
        state.fig_inflow = fig_inflow
        state.fig_outflow = fig_outflow
        state.annual_tables_dict = all_annual_tables
        state.df_prob_summary = df_prob 
        state.current_staging_df = active_staging_df
        state.current_met_df = met_df

        def _update_ui():
            plot_pane_level.object = fig_level
            plot_pane_inflow.object = fig_inflow
            plot_pane_outflow.object = fig_outflow
            table_balance.value = df_balance.reset_index().round(2)
            table_annual.value = all_annual_tables['P50'].reset_index().round(2)
            status_text.object = "Simulation Complete. You can now Export HTML."
            status_text.alert_type = 'success'
            run_button.disabled = False
            download_button.disabled = False 
            
        if doc:
            doc.add_next_tick_callback(_update_ui)

    except Exception as e:
        tb = traceback.format_exc()
        print(f"!!! WORKER ERROR !!!\n{tb}")
        update_status_safely(doc, f"Error: {e}", 'danger')
        if doc:
            doc.add_next_tick_callback(lambda: setattr(run_button, 'disabled', False))

def get_html_report():
    if state.results is None: return None
    status_text.object = "Generating HTML... (Instant)"
    status_text.alert_type = 'warning'
    try:
        html_io = generate_html_report(
            state.base_params, state.params_to_vary, state.n_runs,
            state.start_date, state.end_date,
            state.fig_level, state.fig_inflow, state.fig_outflow,
            state.annual_tables_dict,
            state.df_prob_summary,
            state.current_staging_df, state.current_met_df
        )
        status_text.object = "HTML Export Ready!"
        status_text.alert_type = 'success'
        return html_io
    except Exception as e:
        status_text.object = f"Export Error: {e}"
        status_text.alert_type = 'danger'
        traceback.print_exc()
        return None

download_button.callback = get_html_report

def on_click_run(event):
    if run_button.disabled: return
    run_button.disabled = True
    download_button.disabled = True 
    status_text.object = "Initializing..."
    status_text.alert_type = 'info'
    current_doc = pn.state.curdoc

    try:
        staging_df_to_use = w_geo_table.value.copy()
        for col in ['mRL', 'area_m2', 'volume_m3']:
            staging_df_to_use[col] = pd.to_numeric(staging_df_to_use[col], errors='coerce')
        if staging_df_to_use.isnull().values.any(): raise ValueError("Geometry Table contains bad data.")
        staging_df_to_use = staging_df_to_use.sort_values('mRL')

        met_df_to_use = w_met_table.value.copy()
        if len(met_df_to_use) != 12: raise ValueError("Met Table must have 12 months.")
        base_rainfall = pd.to_numeric(met_df_to_use['Rainfall (mm)'], errors='coerce').tolist()
        base_evap = pd.to_numeric(met_df_to_use['Evaporation (mm)'], errors='coerce').tolist()
        if np.isnan(base_rainfall).any() or np.isnan(base_evap).any():
             raise ValueError("Met Table contains non-numeric data.")

        base_params = {
            'staging_data': staging_df_to_use, 
            'pit_crest_area': float(w_crest_area.value),
            'external_catchment_area': float(w_catchment_area.value),
            'pitwall_runoff_coeff': float(w_pw_coeff.value),
            'catchment_runoff_coeff': float(w_c_coeff.value),
            'regional_gw_level': float(w_gw_level.value),
            'hydraulic_conductivity': float(w_hyd_conductivity.value),
            'gw_distance': float(w_gw_distance.value),
            'pumping_rate': float(w_pumping.value)
        }
        params_to_vary = {
            'hydraulic_conductivity': float(w_var_hyd_conductivity.value),
            'pitwall_runoff_coeff': float(w_var_pw_coeff.value),
            'catchment_runoff_coeff': float(w_var_c_coeff.value),
            'regional_gw_level': float(w_var_gw_level.value),
            'rainfall': float(w_var_rainfall.value),
            'evaporation': float(w_var_evap.value)
        }
        
        worker = threading.Thread(
            target=_simulation_worker,
            args=(current_doc, base_params, base_rainfall, base_evap, params_to_vary,
                  int(w_n_runs.value), str(w_start_date.value), str(w_end_date.value),
                  float(w_initial_level.value), met_df_to_use),
            daemon=True
        )
        worker.start()

    except Exception as e:
        status_text.object = f"Input Error: {e}"
        status_text.alert_type = 'danger'
        run_button.disabled = False

run_button.on_click(on_click_run)

# ##################################################################
# --- LAYOUT & MAIN APP ---
# ##################################################################

params_tab = pn.Column(
    pn.pane.Markdown("### Parameters: Baseline", styles=header_style),
    pn.Row(pn.Column(w_crest_area, w_catchment_area), pn.Column(w_gw_level, w_gw_distance)),
    pn.Row(pn.Column(w_pw_coeff, w_c_coeff), pn.Column(w_hyd_conductivity, w_pumping))
)

geometry_tab = pn.Column(
    pn.pane.Markdown("### 📐 Pit Shell Geometry", styles=header_style),
    pn.pane.Markdown("Edit the values below. Rows must be sorted by mRL."),
    w_geo_table
)

met_tab = pn.Column(
    pn.pane.Markdown("### 🌦️ Meteorology", styles=header_style),
    pn.pane.Markdown("Edit Monthly Totals (mm). 'Month' column is fixed."),
    w_met_table
)

settings_tab = pn.Column(
    pn.pane.Markdown("### 🎲 Settings: Monte Carlo", styles=header_style),
    w_n_runs,
    pn.Row(w_var_hyd_conductivity, w_var_gw_level),
    pn.Row(w_var_pw_coeff, w_var_c_coeff),
    pn.Row(w_var_rainfall, w_var_evap),
    pn.pane.Markdown("### ⚙️ Settings: Simulation", styles=header_style),
    pn.Row(w_start_date, w_end_date, w_initial_level),
    pn.Spacer(height=20),
    run_button,
    pn.Spacer(height=10),
    download_button,
    status_text
)

# ### UPDATED: About / Documentation Tab Content (LaTeX Fixed) ###
about_md = r"""
### ℹ️ About this Model

**Credits**
This interactive dashboard and the underlying hydrological model were coded by **Leonardo Navarro** with the assistance of the Gemini LLM.

---

### 📐 Mathematical Basis

**1. Numerical Scheme**
The model uses a **Runge-Kutta 4 (RK4)** integration scheme on a monthly timestep. The volume at the next timestep $V_{t+1}$ is calculated as:

$$ V_{t+1} = V_t + \frac{1}{6}(k_1 + 2k_2 + 2k_3 + k_4) \cdot \Delta t $$

Where $\Delta t$ is the timestep (monthly).

**2. Geometry**
Lake Level ($L$) and Surface Area ($A$) are derived from the current Volume ($V$) using linear interpolation on the provided **Stage-Volume-Area** curve.

$$ L_t = f_{level}(V_t) $$
$$ A_t = f_{area}(L_t) $$

**3. Inflow Components**
* **Direct Rainfall ($Q_{rain}$):**
    $$ Q_{rain} = A_t \cdot P_{monthly} $$
* **Pit Wall Runoff ($Q_{wall}$):**
    $$ Q_{wall} = (A_{crest} - A_t) \cdot P_{monthly} \cdot C_{wall} $$
* **External Catchment ($Q_{catch}$):**
    $$ Q_{catch} = A_{catch} \cdot P_{monthly} \cdot C_{catch} $$
* **Groundwater Inflow ($Q_{gw,in}$):**
    Occurs when Regional GW Level ($H_{gw}$) > Lake Level ($L_t$).
    $$ Q_{gw,in} = K \cdot A_t \cdot \frac{H_{gw} - L_t}{L_{dist}} $$

**4. Outflow Components**
* **Evaporation ($Q_{evap}$):**
    $$ Q_{evap} = A_t \cdot E_{monthly} $$
* **Groundwater Outflow ($Q_{gw,out}$):**
    Occurs when Lake Level ($L_t$) > Regional GW Level ($H_{gw}$).
    $$ Q_{gw,out} = K \cdot A_t \cdot \frac{L_t - H_{gw}}{L_{dist}} $$
* **Pumping ($Q_{pump}$):**
    Fixed user-defined rate.
"""

about_tab = pn.Column(
    pn.pane.Markdown(about_md, styles={'font-size': '14px'}),
    sizing_mode='stretch_width'
)

sidebar_tabs = pn.Tabs(
    ("Parameters", params_tab),
    ("Meteorology", met_tab),
    ("Geometry", geometry_tab),
    ("Settings & Run", settings_tab),
    ("About", about_tab) 
)

dashboard_view = pn.Tabs(
    ("Welcome", pn.pane.Markdown("### Click 'Run Simulation' in the sidebar to begin.")),
    ("📈 Lake Level", plot_pane_level),
    ("📥 Inflows", plot_pane_inflow),
    ("📤 Outflows", plot_pane_outflow),
    ("📊 Data Tables", pn.Column(
        pn.pane.Markdown("### P50 (Median) Water Balance - Total Simulation"),
        table_balance,
        pn.pane.Markdown("### P50 (Median) Annual Volumes (m³)", styles={'margin-top': '20px'}),
        table_annual
    ))
)

# App Template with Favicon
app_template = pn.template.BootstrapTemplate(
    site="Pit Lake Model",
    title="Interactive Water Balance",
    sidebar_width=950,
    favicon="logo_favicon.png"
)

# Directly append the dashboard and sidebar rather than the placeholders
app_template.main.append(dashboard_view)
app_template.sidebar.append(sidebar_tabs)

app_template.servable()