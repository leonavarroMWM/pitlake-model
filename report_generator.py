# -*- coding: utf-8 -*-
"""
Created on Tue Aug 25 14:37:35 2026

@author: LeoNavarro
"""

# -*- coding: utf-8 -*-
"""
report_generator.py (HTML Version)
Includes:
- Base64 Logo Embedding
- LaTeX Equations (MathJax) - Fixed for f-strings
- RK4 Methodology
- Hydrogeochem Group Company Profile & Authorship
"""

from io import BytesIO
import datetime
import pandas as pd
import plotly.io as pio
import base64
import os

def get_base64_image(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error loading image {filename}: {e}")
    return None

def get_logo_html():
    b64_str = get_base64_image("logo.png")
    if b64_str:
        return f'<img src="data:image/png;base64,{b64_str}" alt="Hydrogeochem Group" style="max-height: 90px; max-width: 100%;">'
    return "<h2 style='color:#0056b3; font-weight:700;'>Hydrogeochem Group</h2>"

def get_favicon_tag():
    b64_str = get_base64_image("logo_favicon.png")
    if b64_str:
        return f'<link rel="icon" type="image/png" href="data:image/png;base64,{b64_str}">'
    return ""

def generate_html_report(base_params, params_to_vary, n_runs, start_date, end_date,
                         fig_level, fig_inflow, fig_outflow, 
                         annual_tables_dict, df_prob_summary,
                         staging_df, met_df):
    
    timestamp = datetime.datetime.now().strftime("%d %B %Y, %H:%M")
    logo_html = get_logo_html()
    favicon_tag = get_favicon_tag()

    # 1. Convert Figures
    html_level = pio.to_html(fig_level, full_html=False, include_plotlyjs='cdn')
    html_inflow = pio.to_html(fig_inflow, full_html=False, include_plotlyjs=False)
    html_outflow = pio.to_html(fig_outflow, full_html=False, include_plotlyjs=False)

    # 2. Format Tables
    inputs_html = """
    <table class="table table-hover table-sm">
        <thead class="table-light"><tr><th>Parameter</th><th>Value</th></tr></thead>
        <tbody>
            <tr><td>Pit Crest Area</td><td>{:,.0f} m²</td></tr>
            <tr><td>Catchment Area</td><td>{:,.0f} m²</td></tr>
            <tr><td>Pitwall Runoff Coeff</td><td>{:.2f}</td></tr>
            <tr><td>Catchment Runoff Coeff</td><td>{:.2f}</td></tr>
            <tr><td>Regional GW Level</td><td>{:.1f} mRL</td></tr>
            <tr><td>Hydraulic Conductivity (K)</td><td>{:.4f} m/day</td></tr>
            <tr><td>Distance to GW (L)</td><td>{:.1f} m</td></tr>
            <tr><td>Pumping Rate</td><td>{:.1f} m³/day</td></tr>
        </tbody>
    </table>
    """.format(
        base_params['pit_crest_area'], base_params['external_catchment_area'],
        base_params['pitwall_runoff_coeff'], base_params['catchment_runoff_coeff'],
        base_params['regional_gw_level'], base_params['hydraulic_conductivity'],
        base_params['gw_distance'], base_params['pumping_rate']
    )

    mc_html = """
    <table class="table table-hover table-sm">
        <thead class="table-light"><tr><th>Variable</th><th>StDev (%)</th></tr></thead>
        <tbody>
    """
    for k, v in params_to_vary.items():
        mc_html += f"<tr><td>{k.replace('_', ' ').title()}</td><td>{v*100:.1f}%</td></tr>"
    mc_html += "</tbody></table>"

    met_html = met_df.to_html(index=False, classes='table table-sm table-hover', border=0, float_format="%.1f")

    if len(staging_df) > 15:
        geo_display = staging_df.iloc[::int(len(staging_df)/15)]
    else:
        geo_display = staging_df
    geo_html = geo_display.to_html(index=False, classes='table table-sm table-hover', border=0, float_format="%.0f")

    # Generate Multiple Annual Tables (P05, P25, P50, P75, P95)
    annual_tables_html = ""
    percentiles_ordered = ['P05', 'P25', 'P50', 'P75', 'P95']
    
    header_colors = {
        'P05': '#fff3cd', 'P25': '#e2e3e5', 'P50': '#cce5ff', 
        'P75': '#e2e3e5', 'P95': '#d1e7dd'
    }

    for p in percentiles_ordered:
        if p in annual_tables_dict:
            tbl_html = annual_tables_dict[p].reset_index().to_html(
                index=False, classes='table table-hover table-bordered table-sm mb-0', border=0, float_format="%.0f"
            )
            bg_color = header_colors.get(p, '#f8f9fa')
            annual_tables_html += f"""
            <div class="card mb-4" style="border:1px solid #dee2e6; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div class="card-header" style="background-color: {bg_color}; font-weight: bold; color: #495057;">
                    {p} Annual Water Balance (m³)
                </div>
                <div class="card-body p-0">
                    {tbl_html}
                </div>
            </div>
            """

    # Format Probability Summary Table
    prob_html = df_prob_summary.reset_index().to_html(
        index=False, classes='table table-striped table-bordered table-sm', border=0, float_format="{:,.0f}".format
    )

    # 3. Assemble HTML
    full_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Pit Lake Model Report</title>
        {favicon_tag}
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        
        <script>
        MathJax = {{
          tex: {{
            inlineMath: [['$', '$']]
          }}
        }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>

        <style>
            body {{ background-color: #f0f2f5; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; color: #343a40; }}
            .report-container {{ background-color: #ffffff; margin: 40px auto; padding: 50px; border-radius: 8px; box-shadow: 0 12px 24px rgba(0,0,0,0.08); max-width: 1100px; }}
            .header-row {{ display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 2px solid #e9ecef; margin-bottom: 30px; }}
            .report-title h1 {{ font-weight: 800; color: #0d6efd; margin-bottom: 0; }}
            .report-meta {{ text-align: right; color: #6c757d; font-size: 0.9rem; }}
            .auth-box {{ background: #f8f9fa; border-left: 5px solid #0d6efd; padding: 15px 20px; border-radius: 4px; margin-bottom: 30px; }}
            .auth-box p {{ margin: 0; font-size: 1rem; color: #495057; }}
            .hgg-box {{ background-color: #ffffff; padding: 25px; border-radius: 8px; margin-bottom: 40px; border: 1px solid #e9ecef; box-shadow: 0 4px 6px rgba(0,0,0,0.02); }}
            .hgg-title {{ color: #0056b3; font-weight: 700; margin-bottom: 10px; font-size: 1.1rem; }}
            .hgg-text {{ font-size: 0.95rem; line-height: 1.6; color: #555; text-align: justify; }}
            .hgg-link {{ color: #0056b3; font-weight: 600; text-decoration: none; }}
            h2 {{ color: #2c3e50; font-weight: 700; font-size: 1.5rem; margin-top: 50px; margin-bottom: 20px; border-bottom: 1px solid #dee2e6; padding-bottom: 10px; }}
            h3 {{ color: #495057; font-weight: 600; font-size: 1.2rem; margin-top: 30px; margin-bottom: 15px; }}
            .math-box {{ background: #fff; padding: 20px; border-radius: 6px; border: 1px solid #e0e0e0; margin-bottom: 20px; }}
            .plot-container {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px; background: white; margin-bottom: 30px; }}
            .footer {{ margin-top: 80px; padding-top: 20px; border-top: 1px solid #dee2e6; text-align: center; color: #aaa; font-size: 0.85rem; }}
        </style>
    </head>
    <body>
        <div class="report-container">
            
            <div class="header-row">
                <div>{logo_html}</div>
                <div class="report-meta">
                    <h1 class="display-6">Water Balance Report</h1>
                    <strong>Generated:</strong> {timestamp}<br>
                    <strong>Period:</strong> {start_date} to {end_date}
                </div>
            </div>

            <div class="auth-box">
                <p>
                    This report was generated automatically by the <strong>Pit Lake Water Balance Model</strong>. 
                    All computational codes, algorithms, and simulation scripts were developed by 
                    <strong>Leonardo Navarro and Ryan Burgess</strong> (Mine Waste Management and Hydrogeochem Group).
                </p>
            </div>

            <div class="hgg-box">
                <div class="hgg-title">About Hydrogeochem Group (HGG)</div>
                <div class="hgg-text">
                    <p>HGG was founded to assist clients assess and manage water quality considerations associated with their operations and legacy assets. In doing so we support the responsible management of water resources through the provision of practical technical expertise in the fields of hydrogeochemistry and hydrogeology.</p>
                    <p>HGG provides an internationally experienced team having worked extensively throughout Australia, New Zealand, Africa and Asia. Consulting services have been provided for a diverse range of commodities including base metals, coal, copper, diamonds, gold, lithium, iron ore and uranium. For the oil and gas sector, consulting services have been provided for upstream, midstream and downstream developments and this experience extends to unconventional resources (i.e. shale/coal seam gas).</p>
                </div>
                <div style="margin-top: 10px;">
                    <a href="https://www.hydrogeochem.com.au/" target="_blank" class="hgg-link">Visit www.hydrogeochem.com.au &rarr;</a>
                </div>
            </div>

            <h2>1. Methodology & Mathematical Basis</h2>
            <div class="math-box">
                <p>The model employs a <strong>Runge-Kutta 4 (RK4)</strong> numerical integration scheme operating on a <strong>monthly timestep</strong>. This method provides stability and accuracy for long-term simulations.</p>
                
                <p><strong>Governing Equation:</strong><br>
                The volume of the lake at the next timestep $V_{{t+1}}$ is estimated using a weighted average of four slope increments:</p>
                $$ V_{{t+1}} = V_t + \\frac{{\\Delta t}}{{6}} (k_1 + 2k_2 + 2k_3 + k_4) $$
                <p>Where $\\Delta t$ is the timestep (days in month), and $k_n$ represents the net flow rate ($Q_{{in}} - Q_{{out}}$) evaluated at intermediate states.</p>

                <hr style="margin: 20px 0; border-top: 1px dashed #ccc;">

                <div class="row">
                    <div class="col-md-6">
                        <h5>Inflow Components</h5>
                        <ul>
                            <li><strong>Direct Rainfall:</strong> $$ Q_{{rain}} = A(L_t) \\cdot P_{{monthly}} $$</li>
                            <li><strong>Pit Wall Runoff:</strong> $$ Q_{{wall}} = (A_{{crest}} - A(L_t)) \\cdot P_{{monthly}} \\cdot C_{{wall}} $$</li>
                            <li><strong>Catchment Runoff:</strong> $$ Q_{{catch}} = A_{{catch}} \\cdot P_{{monthly}} \\cdot C_{{catch}} $$</li>
                            <li><strong>Groundwater Inflow:</strong> <br><small>If $H_{{gw}} > L_t$:</small>
                                $$ Q_{{gw,in}} = K \\cdot A(L_t) \\cdot \\frac{{H_{{gw}} - L_t}}{{L_{{dist}}}} $$</li>
                        </ul>
                    </div>
                    <div class="col-md-6">
                        <h5>Outflow Components</h5>
                        <ul>
                            <li><strong>Evaporation:</strong> $$ Q_{{evap}} = A(L_t) \\cdot E_{{monthly}} \\cdot C_{{pan}} $$</li>
                            <li><strong>Groundwater Outflow:</strong> <br><small>If $L_t > H_{{gw}}$:</small>
                                $$ Q_{{gw,out}} = K \\cdot A(L_t) \\cdot \\frac{{L_t - H_{{gw}}}}{{L_{{dist}}}} $$</li>
                            <li><strong>Pumping:</strong> Fixed rate $Q_{{pump}}$</li>
                        </ul>
                    </div>
                </div>
            </div>

            <h2>2. Model Inputs</h2>
            <div class="row">
                <div class="col-md-4">
                    <div class="card mb-3">
                        <div class="card-header bg-light"><strong>Scalar Parameters</strong></div>
                        <div class="card-body p-0">{inputs_html}</div>
                    </div>
                    <div class="card mb-3">
                        <div class="card-header bg-light"><strong>Monte Carlo (N={n_runs})</strong></div>
                        <div class="card-body p-0">{mc_html}</div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card mb-3">
                        <div class="card-header bg-light"><strong>Meteorology (Monthly)</strong></div>
                        <div class="card-body p-0" style="max-height: 300px; overflow-y: auto;">{met_html}</div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card mb-3">
                        <div class="card-header bg-light"><strong>Geometry (Sample)</strong></div>
                        <div class="card-body p-0" style="max-height: 300px; overflow-y: auto;">{geo_html}</div>
                    </div>
                </div>
            </div>

            <h2>3. Simulation Results (Probabilistic)</h2>
            <p><i>The plots below show the P05-P95 (Light Shading) and P25-P75 (Dark Shading) confidence intervals.</i></p>
            
            <h3>Lake Level Forecast</h3>
            <div class="plot-container">{html_level}</div>

            <h3>Inflows</h3>
            <div class="plot-container">{html_inflow}</div>

            <h3>Outflows</h3>
            <div class="plot-container">{html_outflow}</div>

            <h2>4. Probabilistic Water Balance (Total Volume)</h2>
            <div class="table-responsive">{prob_html}</div>

            <h2>5. Annual Water Balance (Detailed Percentiles)</h2>
            <div class="table-responsive">
                {annual_tables_html}
            </div>

            <div class="footer">
                <p><strong>Pit Lake Model v2.0</strong> | Generated Automatically</p>
                <p class="credits">Code created by <strong>Leonardo Navarro</strong> (Hydrogeochem Group).</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return BytesIO(full_html.encode('utf-8'))