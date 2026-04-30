# Pit Lake Water Balance Model

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Panel](https://img.shields.io/badge/UI-Panel-orange)
![License](https://img.shields.io/badge/License-Proprietary-red.svg)

An interactive, probabilistic numerical model designed to forecast pit lake filling dynamics under climate and hydrogeological uncertainty. This tool couples a rigorous numerical integration scheme with a modern web-based graphical interface, allowing environmental engineers and geochemists to execute complex water balances without interacting directly with the source code.

## ✨ Key Capabilities

* **Runge-Kutta 4 (RK4) Engine:** Replaces standard Euler methods with an RK4 integration scheme operating on a monthly timestep. This ensures high stability and accuracy when calculating dynamically coupled area-volume-flux relationships.
* **Probabilistic Forecasting:** Natively integrates Monte Carlo simulation capabilities to stress-test baseline parameters (precipitation, evaporation, hydraulic leakance, and runoff coefficients), outputting comprehensive statistical confidence intervals (P05, P25, P50, P75, P95).
* **Interactive GUI:** Built on [HoloViz Panel](https://panel.holoviz.org/), offering a reactive dashboard for defining pit shell geometry (Stage-Area-Volume), configuring meteorological arrays, and establishing model parameters.
* **Automated HTML Reporting:** Generates a standalone, fully formatted HTML report featuring interactive Plotly charts, data tables, mathematical documentation (via MathJax), and base64-embedded corporate branding for immediate client or regulatory submission.
* **Zero-Install Deployment:** Features a self-bootstrapping Windows launcher (`run.cmd`) that securely downloads an isolated, portable Python environment. End-users require zero prior software installation to run the dashboard.

---

## 🧮 Mathematical Framework

The model evaluates the changing volume of the pit lake by numerically integrating net fluxes over time using the RK4 method:

$$V_{t+1} = V_t + \frac{\Delta t}{6} (k_1 + 2k_2 + 2k_3 + k_4)$$

Where $\Delta t$ is the timestep (days in the specific month), and $k_n$ represents the evaluated net flow rates at intermediate fractional steps. At each evaluation step, the model calculates the following flux components:

### Inflow Components
* **Direct Rainfall:** $Q_{rain} = A_t \cdot P_{monthly}$
* **Pit Wall Runoff:** $Q_{wall} = (A_{crest} - A_t) \cdot P_{monthly} \cdot C_{wall}$
* **Catchment Runoff:** $Q_{catch} = A_{catch} \cdot P_{monthly} \cdot C_{catch}$
* **Groundwater Inflow:** (Active when $H_{gw} > L_t$)
  $$Q_{gw,in} = K_{bulk} \cdot A_t \cdot (H_{gw} - L_t)$$

### Outflow Components
* **Evaporation:** $Q_{evap} = A_t \cdot E_{monthly}$
* **Groundwater Outflow:** (Active when $L_t > H_{gw}$)
  $$Q_{gw,out} = K_{bulk} \cdot A_t \cdot (L_t - H_{gw})$$
* **Pumping:** Fixed user-defined extraction rate ($Q_{pump}$).

*Note: $K_{bulk}$ represents the Bulk Pit Leakance (or specific conductance) and is dimensioned in $\text{day}^{-1}$.*

---

## 🚀 Getting Started

### For End-Users (Windows Standalone)
You do not need Python, Anaconda, or administrative privileges to run this tool.

1. Clone or download this repository to your local machine.
2. Double-click the **`run.cmd`** executable.
3. *First Run Only:* The script will automatically fetch a portable Python distribution and install the necessary dependencies locally within the project folder. This takes 1-2 minutes.
4. The dashboard will launch automatically in your default web browser.

### For Developers (Standard Python Environment)
If you prefer to run the model in your own environment:

1. Clone the repository.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
