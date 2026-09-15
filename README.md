# AV Risk Engine

An autonomous vehicle risk assessment engine designed around [CARLA](https://carla.org/), while remaining fully usable and testable without it.

The engine converts a driving situation into a risk level:

**SAFE → WATCH → DANGER → CRITICAL**

It combines six criticality metrics, applies contextual modifiers such as weather, road-user type and visibility, and produces an interpretable risk assessment. A weighting layer additionally identifies the metric that contributes most to the final assessment.

---

## Overview

The project is designed around a clear separation between the risk engine and its simulation environments.

The core engine is independent of CARLA and can therefore be:

- executed without a 3D simulator;
- tested independently;
- calibrated using predefined reference scenarios;
- used with the 2D kinematic simulator;
- integrated into CARLA for real-time evaluation.

The project provides three main execution modes:

1. **Standalone mode** — risk evaluation without CARLA.
2. **Web mode** — React + FastAPI dashboard.
3. **CARLA mode** — real-time risk evaluation in a 3D simulation environment.

---

## Requirements

### Standalone Mode

- Python 3
- pip

### Web Interface

- Python 3
- Node.js
- npm

### CARLA Integration

- CARLA 0.9.15 or 0.9.16
- Python environment containing the CARLA API
- `pygame`
- `pandas`
- A supported GPU configuration is recommended for CARLA

---

## 1. Standalone Usage

CARLA is not required to run the core engine.

From the project root:

```bash
python3 -m pip install -r requirements.txt
```

The requirements include the dependencies needed for the standalone engine, testing, simulation, plotting and the FastAPI backend.

### Main Commands

#### Risk Evaluation

Launch the Tkinter interface:

```bash
python3 apps/run.py
```

This opens a scenario configuration form and evaluates the resulting driving situation.

#### 2D Simulation

Launch the standalone kinematic simulator:

```bash
python3 apps/simulate.py
```

This allows a scenario to be configured and simulated without CARLA, with the resulting figures displayed after the simulation.

#### Demo Mode

Run a predefined demonstration without opening the scenario form:

```bash
python3 apps/simulate.py --demo --gif --reaction
```

#### Calibration

Run the calibration process on the reference scenarios:

```bash
python3 apps/calibrate.py
```

#### Threshold Optimization

Run the threshold optimization procedure:

```bash
python3 apps/optimize.py
```

The optimization process proposes updated thresholds and compares the results before and after optimization.

#### Tests

Run the complete test suite:

```bash
python3 -m pytest -q
```

The project currently contains 125 tests, including unit tests, invariants and calibration tests.

---

## 2. Web Interface

The web interface consists of a React + TypeScript + Vite frontend and a FastAPI backend.

### Start the Backend

Open a terminal at the project root:

```bash
python3 apps/api.py
```

The API runs on:

```
http://localhost:8000
```

### Start the Frontend

Open a second terminal:

```bash
cd web
npm install
npm run dev
```

The Vite development server runs on port 5173.

The dashboard is organized into three main panels:

**Scenario**
Allows the user to configure a driving scenario. It includes:
- predefined scenarios SC-01 to SC-24;
- automatic consistency checks;
- configurable environmental and traffic parameters.

**Evaluation**
Displays the risk assessment at t = 0. The evaluation includes the risk level, the underlying metrics and the factors contributing to the decision.

**Simulation**
Provides:
- an animated top-down representation of the scenario;
- metric evolution over time;
- expandable plots for detailed analysis.

Additional deployment instructions for Render are available in:
`web/README.md`

The backend is currently deployed at:
https://av-risk-engine.onrender.com

---

## 3. CARLA Integration

CARLA is used as the 3D simulation environment for evaluating the risk engine in dynamic driving scenarios.

The Python scripts do not start CARLA automatically. The CARLA simulator must be started separately before running the integration scripts.

The recommended workflow is:

1. Activate the CARLA Python environment
2. Start the CARLA simulator
3. Wait for the simulator to be fully loaded
4. Run a lightweight script to pre-load the required map
5. Run the desired CARLA script or benchmark

### 3.1 Activate the CARLA Environment

From the root of the repository, activate the dedicated Python virtual environment.

**Windows**
```powershell
.\.venv-carla-12\Scripts\Activate.ps1
```

**Linux / macOS**
```bash
source .venv-carla-12/bin/activate
```

The CARLA environment isolates CARLA-specific dependencies from the standalone Python environment. This is particularly important because the CARLA integration uses additional packages such as:

- `carla`
- `pygame`
- `pandas`

---

## 4. Start the CARLA Simulator

Open a second terminal. Navigate to the directory where CARLA is installed.

For example:

```
C:\CARLA_0.9.16\
```

or:

```
~/CARLA_0.9.16/
```

Start the simulator.

**Windows**
```powershell
.\CarlaUE4.exe
```

**Linux**
```bash
./CarlaUE4.sh
```

Wait until the CARLA window is open and the simulator has finished loading. The Python scripts can then connect to the running CARLA instance.

### 4.1 Running CARLA with Reduced Graphics

CARLA can be relatively demanding, especially when running benchmarks or multiple actors. If the simulation is too slow, use a reduced graphical configuration.

**Windows**
```powershell
.\CarlaUE4.exe -quality-level=Low -windowed -ResX=800 -ResY=600
```

This configuration:
- sets the graphics quality to Low;
- starts CARLA in windowed mode;
- limits the window resolution to 800 × 600.

---

## 5. Connect the Project to CARLA

Once CARLA is running, return to the first terminal, where the CARLA Python environment is activated. The simplest way to verify the connection is to run:

```bash
python3 apps/carla_run.py
```

This starts an interactive CARLA session with the project HUD. The script connects to the running CARLA server, initializes the required actors and starts the corresponding project components.

---

## 6. CARLA Map Pre-Warmup

When a script requests a map that has not yet been loaded, CARLA may need significant time to load the environment, assets and textures.

For example, loading Town03 for the first time can take long enough to cause a connection timeout such as:

```
Timeout of 10000ms
```

This is especially common when launching a benchmark directly. To avoid this, it is recommended to pre-load the map before running a large campaign.

### Recommended Procedure

**Step 1 — Start CARLA**

In the CARLA installation directory:

```bash
.\CarlaUE4.exe
```

or on Linux:

```bash
./CarlaUE4.sh
```

Wait until the simulator is ready.

**Step 2 — Run the Lightweight CARLA Script**

In the project terminal:

```bash
python3 apps/carla_run.py
```

This allows the required CARLA environment to initialize before starting a heavier workload. Wait until the map is fully loaded.

**Step 3 — Run the Benchmark**

Once the map has finished loading:

```bash
python3 apps/carla_benchmark_v8_opt.py --scenario 3 --distance 2000
```

This workflow reduces the probability of a timeout caused by the initial map loading process.

---

## 7. CARLA Scripts

The repository contains several scripts for interacting with CARLA.

**Interactive Session**

```bash
python3 apps/carla_run.py
```

Starts an interactive CARLA session with the project HUD. This is also useful for pre-loading a map before running a benchmark.

**Replay a Single Scenario**

To replay a specific predefined scenario:

```bash
python3 apps/carla_replay.py --preset SC-05 --duree 15
```

For example, the command above replays scenario SC-05 for 15 seconds.

**Replay All Reference Scenarios**

To replay all 24 reference scenarios in headless mode:

```bash
python3 apps/carla_replay.py --all --headless
```

This is useful for batch evaluation without rendering the CARLA interface.

**Run a Benchmark**

The benchmark scripts can be used to evaluate the engine over longer scenarios and parameter configurations. Example:

```bash
python3 apps/carla_benchmark_v8_opt.py --scenario 3 --distance 2000
```

The available options depend on the benchmark version and should be checked directly from the script:

```bash
python3 apps/carla_benchmark_v8_opt.py --help
```

---

## 8. Recommended CARLA Workflow

For reproducible CARLA experiments, use the following procedure.

**Terminal 1 — Project Environment**

```bash
cd av_risk_engine

# Windows
.\.venv-carla-12\Scripts\Activate.ps1

# Linux / macOS
source .venv-carla-12/bin/activate
```

**Terminal 2 — CARLA**

Navigate to the CARLA installation directory:

```bash
cd <CARLA_INSTALLATION_DIRECTORY>
```

Then start CARLA.

**Windows**
```powershell
.\CarlaUE4.exe
```

**Linux**
```bash
./CarlaUE4.sh
```

Wait for CARLA to finish loading.

**Terminal 1 — Pre-Warmup**

```bash
python3 apps/carla_run.py
```

Wait until the map is fully initialized.

**Terminal 1 — Run the Desired Experiment**

For example:

```bash
python3 apps/carla_benchmark_v8_opt.py --scenario 3 --distance 2000
```

Or replay a predefined scenario:

```bash
python3 apps/carla_replay.py --preset SC-05 --duree 15
```

Or replay the complete reference set:

```bash
python3 apps/carla_replay.py --all --headless
```

---

## 9. Risk Engine Architecture

The core decision pipeline is:

```
Context
   ↓
Criticality Metrics
   ↓
Contextual Modifiers
   ↓
Decision Grid
   ↓
Risk Level
   ↓
Recommended Control
```

The final risk level is determined by the most critical level among the six metrics. This max-risk strategy prioritizes safety: a single critical metric can raise the overall risk level even if the other metrics indicate a lower level.

A separate weighting layer identifies which metric has the strongest influence on the assessment.

---

## 10. Risk Levels

| Level | Meaning |
|---|---|
| SAFE | The current situation is considered safe. |
| WATCH | The situation requires increased monitoring. |
| DANGER | The situation presents a significant risk and may require corrective action. |
| CRITICAL | The situation is critical and requires an immediate response. |

---

## 11. Repository Structure

```
av_risk_engine/
│
├── apps/                           # Executable entry points
│   ├── api.py                      # FastAPI backend
│   ├── run.py                      # Tkinter interface → risk evaluation
│   ├── simulate.py                 # 2D simulation + figures
│   ├── calibrate.py                # Calibration on SC-01..24
│   ├── optimize.py                 # Threshold optimization
│   ├── demo.py                     # Minimal console demonstration
│   ├── carla_run.py                # Interactive CARLA session
│   ├── carla_benchmark...          # Evaluation / Grid Search scripts
│   └── carla_replay.py             # Scenario replay in CARLA
│
├── risk_engine/                    # Core engine, independent of CARLA
│   ├── context.py                  # Context management
│   ├── metrics.py                  # Criticality metrics
│   ├── modifiers.py                # Contextual modifiers
│   ├── engine.py                   # Main decision engine
│   ├── weighting.py                # Metric weighting
│   ├── sanitize.py                 # Data validation / sanitization
│   ├── control.py                  # Recommended control
│   ├── lateral.py                  # 2D geometric filtering
│   └── report.py                   # Risk reports
│
├── sim/                            # Standalone 2D kinematic simulator
│
├── scenarios/                      # Scenario definitions and constraints
│
├── calibration/                    # Reference scenarios and labeling method
│
├── world/                          # CARLA integration layer
│   ├── extraction.py               # Shared geometric extraction
│   ├── weather.py                  # Weather → CARLA WeatherParameters
│   ├── carla_bridge.py             # CARLA connection, spawn and tick
│   ├── carla_control.py            # Lateral control + ACC takeover
│   ├── carla_form.py               # CARLA configuration form
│   └── hud/                        # Pygame HUD
│       ├── state.py
│       ├── palette.py
│       └── pygame_hud.py
│
├── web/                            # React + Vite + TypeScript frontend
│
├── tests/                          # Unit, invariant and calibration tests
│
└── docs/                           # Project documentation
    ├── CHANGELOG.md                # Project history, phases A → I
    ├── DECISIONS.md                # Technical decision record
    ├── FILES.md                    # Detailed file reference
    ├── TESTS.md                    # Documentation of the 125 tests
    └── CARLA_DEMARRAGE.md          # CARLA setup and usage guide
```

---

## 12. Documentation

Additional documentation is available in the `docs/` directory.

| Document | Description |
|---|---|
| `docs/FILES.md` | Detailed reference for project files |
| `docs/TESTS.md` | Documentation of the 125 tests |
| `docs/DECISIONS.md` | Technical decisions and design rationale |
| `docs/CHANGELOG.md` | Project development history |
| `docs/CARLA_DEMARRAGE.md` | Detailed CARLA setup and execution guide |
| `web/README.md` | Web interface and deployment documentation |

---

## 13. CARLA Dependency

CARLA is an optional dependency of the project. The core risk engine does not depend on CARLA and can be executed, tested and calibrated independently.

**Components That Do Not Require CARLA**

```
risk_engine/
sim/
scenarios/
calibration/
tests/

apps/run.py
apps/simulate.py
apps/calibrate.py
apps/optimize.py
apps/demo.py
```

**Components Requiring CARLA**

```
world/carla_bridge.py
world/carla_control.py
world/weather.py
world/hud/

apps/carla_*.py
```

---

## 14. Supported CARLA Versions

The project has been developed and tested with:

- CARLA 0.9.15
- CARLA 0.9.16

A Linux environment with a dedicated GPU or a Windows environment is recommended for running the full CARLA integration.

---

## 15. Quick Reference

**Standalone**

```bash
python3 -m pip install -r requirements.txt
python3 apps/run.py
python3 apps/simulate.py
python3 apps/simulate.py --demo --gif --reaction
python3 apps/calibrate.py
python3 apps/optimize.py
python3 -m pytest -q
```

**Web**

```bash
# Terminal 1
python3 apps/api.py

# Terminal 2
cd web
npm install
npm run dev
```

**CARLA**

```
Terminal 1:
    Activate the CARLA virtual environment

Terminal 2:
    Start CARLA

Terminal 1:
    python3 apps/carla_run.py

Terminal 1:
    Run the desired benchmark or replay script
```

For additional CARLA-specific information, refer to:
`docs/CARLA_DEMARRAGE.md`
