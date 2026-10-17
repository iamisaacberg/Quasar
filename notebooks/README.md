# Optional notebook workflow

This folder is for the teammate using **Jupyter Notebook**. Everyone else can keep using regular Python, their editor and the application. Jupyter is not an application runtime dependency and is not installed in the IBM Z container.

Start with [01_shared_code_starter.ipynb](01_shared_code_starter.ipynb). Its default run is offline: synthetic Okaloosa fixtures, shared scenario reports, a small score chart, an input experiment and unknown-data behavior. It imports `quasar.analysis`, `quasar.pipeline` and `quasar.scoring` rather than carrying another copy of the scoring logic. An optional, disabled cell can inspect an already imported WeatherNext snapshot. Nothing in the starter queries BigQuery, calls Mapbox, sends notifications or accesses IBM Z.

## For the teammate using Jupyter Notebook

From the repository root, create a local virtual environment. Python 3.12 matches the notebook CI job; the project supports Python 3.11+.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[notebooks]'
python -m notebook notebooks/01_shared_code_starter.ipynb
```

On Windows PowerShell, create the environment with `python -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1`; use the same install and launch commands afterward. If you already have an environment, activate it rather than overwriting it.

The editable install links the notebook to the repository's actual Python files. Launch Jupyter from that activated environment and use its Python kernel. The first cell prints the interpreter and shared-package location so you can confirm them. If imports fail, run the install command in the kernel's environment. Do not add machine-specific `sys.path` edits.

The optional direct-tool versions are pinned in `pyproject.toml`; transitive packages are resolved by pip, so this is not a full environment lock. Add any new research dependencies to that optional extra and document them. GIS/ML packages must be checked separately on IBM Z before they become application dependencies. The notebook itself uses standard-library calculations and IPython display tools without pandas or matplotlib.

Changes to imported `.py` modules are not guaranteed to appear in a running kernel automatically. Restart the kernel and run all cells after changing shared code, and always do that before a handoff.

## For Isaac / anyone not using notebooks

Keep the current workflow:

```sh
python3 -m quasar
python3 -m quasar.analysis --scenario peak
python3 -m quasar.analysis --compare
python3 -m unittest discover -s tests -v
```

The analysis commands print JSON using the same shared functions as the starter notebook. They require no Jupyter installation. `python3 scripts/check_notebooks.py` can also check that committed notebooks have no saved outputs, using only standard-library Python.

## Working together

1. Assign one question and one notebook owner. Create a feature branch; avoid editing the same notebook simultaneously.
2. Copy the starter to a descriptive filename for a distinct experiment. Keep shared source notebooks directly in `notebooks/` so the checker finds them.
3. Explore and explain in cells. Put reusable transformations, source adapters and scoring functions in `quasar/`, with tests in `tests/`.
4. Call those functions from the notebook. The app/editor teammate can import the same functions without learning Jupyter.
5. In the pull request, state the input/output contract, data source/run/time window, units, findings, limitations and any proposed model changes. Research findings do not silently change the baseline model.
6. Open the pull request into `preview`, get teammate review and integrate the shared Python changes. Keep synthetic and actual forecast results clearly labeled.

## Clean, reproducible notebook commits

Restart the kernel and run all cells top to bottom. Then, from the repository root in the notebook environment:

```sh
python scripts/check_notebooks.py --clear
python scripts/check_notebooks.py --execute
```

`--clear` deliberately removes saved cell outputs, execution counts/timing and widget state from source notebooks. Inspect your results before clearing. Keep useful findings in markdown; export larger presentation results under the ignored `notebooks/outputs/` folder when needed. Never save credentials or real opt-in information in cells or results.

`--execute` validates the notebook schema and runs each source notebook in a fresh, temporary kernel using the invoking Python interpreter. It starts in `notebooks/`, which verifies imports do not depend on the repository root being the working directory. It executes in memory without resaving outputs or installing a global kernel. The check disables inherited local WeatherNext snapshot configuration; the starter's opt-in forecast cell remains off. It does not install a security sandbox: only run notebooks whose code you have reviewed.

GitHub Actions installs the optional extra in its own environment and runs this fresh-kernel check. The normal application test job still runs without Jupyter installed. Notebook checkpoint files and exported results are ignored by Git.

## Optional WeatherNext inspection

Use the existing importer in [integration setup](../docs/integrations.md) to prepare a snapshot first. Before launching Jupyter, explicitly set `QUASAR_WEATHERNEXT_FILE` to the snapshot's absolute path in your terminal. The notebook does not load `.env`. Deliberately enable `USE_LOCAL_FORECAST` only for your local investigation, and restore it to `False` before committing the shared starter. Keep source initialization, forecast validity, retrieval time, native resolution and unknown/stale states intact.

References: [Jupyter installation](https://jupyter.org/install), [IPython environments and kernels](https://ipython.readthedocs.io/en/stable/install/kernel_install.html), [programmatic notebook execution](https://nbclient.readthedocs.io/en/latest/).
