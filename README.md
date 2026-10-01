# CreditScope

A local API-backed application for the Home Credit Default Risk research project. Built with FastAPI, pandas, scikit-learn, PyTorch, and a responsive browser interface.

## Open the application

Double-click `start.bat`, then open **http://127.0.0.1:8000**. The launcher checks the environment and imports the project data if needed. Keep its terminal running while using the app.

The application has seven sections:

- **Executive overview:** all 307,511 applicant records, six Power BI filters, cohort metrics, age/income matrix, and summary export.
- **Worldwide statistics:** interactive country map, World Bank banking and macroeconomic indicators, and a sourced global banking exposure scenario.
- **Individual prediction:** 12 input fields, deployed-model selection, class-1 score, validation threshold, local input sensitivity, full feature provenance, model comparison, and JSON report export.
- **Batch CSV check:** upload up to 50,000 applicants per file, review ranked model scores, export the results, and inspect any row's feature values and local sensitivities. Selected rows remain available in local memory for one hour.
- **Explore the data:** all 45 saved notebook plots, including complete model comparisons and confusion matrices; preprocessing stages and the 11-model leaderboard.
- **AI assistant:** switch between Ollama and Gemini. After scoring a case, **Ask this applicant** supplies its verified score, feature evidence, and a historical peer cohort to either assistant. Assistant Markdown is rendered safely.
- **Deploy model:** trusted model upload, input-schema validation, inference smoke test, immediate prediction availability, and removal with a recoverable local archive.

Models appear after you deploy their saved artifacts. Notebook packages are validated during upload and can then be chosen for individual or CSV prediction.

## Clone and run on another computer

Install **Git**, **Git LFS**, and **Python 3.13** first. Git LFS is required because the repository includes the applicant dataset used by the dashboard. Then run:

```powershell
git lfs install
git clone https://github.com/MImahin/CreditScope.git
cd CreditScope
git lfs pull
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\start.bat
```

Open **http://127.0.0.1:8000** after the launcher reports that startup is complete. Keep the launcher window open while using CreditScope; press **Ctrl+C** in that window to stop it.

If the imported data snapshot is missing or you deliberately want to rebuild it from the original notebook and source dataset, run:

```powershell
.\.venv\Scripts\python.exe scripts/import_project.py
```

The repository includes the current imported data snapshot; `data/applicants.pkl` is tracked with Git LFS. A normal clone followed by `git lfs pull` downloads it automatically. The importer is only needed to rebuild the snapshot from the original notebook and `home-credit-default-risk` folder. Set `CREDITSCOPE_SOURCE` to a different dataset folder if needed. It never executes notebook code or modifies source files. Uploaded models remain local in `storage/models/` and are excluded from version control, so deploy model packages separately on each device through **Deploy model**.

Imported data is a local snapshot, not a live connection to Power BI. Filters recalculate against that snapshot. To reflect new source data, rerun the importer and restart the app. Original amount units are preserved; no BDT/USD conversion is inferred.

## Chatbot choices

### Free local chatbot with Ollama

Ollama is supported directly. It runs the chatbot on your own computer and requires no API key, billing account, or internet connection after the model has been downloaded.

```env
CHAT_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma3:4b
```

Install Ollama, then download a suitable model once with `ollama pull gemma3:4b`. Start CreditScope normally. The AI Assistant will show **LOCAL · gemma3:4b** when it connects. If the assistant says it cannot reach Ollama, open the Ollama application and retry.

### Cloud chatbot with Gemini's free tier

CreditScope also supports **Gemini 3.5 Flash-Lite** as a second, cloud-based assistant. Create a key in [Google AI Studio](https://aistudio.google.com/app/apikey), then add it to `.env`:

```env
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL=gemini-3.5-flash-lite
```

Restart CreditScope. The AI Assistant presents separate **Local assistant** and **Gemini assistant** cards; each keeps its own browser-memory chat history. General chat sends aggregate project context. When **Ask this applicant** is active, the selected applicant details and verified model score are also sent to Gemini. Use **Clear case** to remove the selected context.

## Upload your models

Use **Deploy model** and select the format. A successful upload must pass an actual inference test before it becomes selectable. Upload only your own or trusted artifacts: joblib/pickle deserialization can execute code. The default application binds only to localhost.

### Original MLP

- Name: `MLP`
- Format: Scikit-learn
- Model: `home-credit-default-risk/model/mlp/mlp_pipeline.joblib`
- Metadata: the `metadata.json` in that same folder
- Separate preprocessing/feature files: not required; the pipeline and metadata include them

The original threshold is **0.6544190978641563**, not an arbitrary 0.5.

### Original Deep & Cross Network

- Name: `DCN`
- Format: PyTorch DCN
- Model: `home-credit-default-risk/model/dcn/credit_dcn.pth`
- Preprocessor: `preprocessor.joblib` from the same folder
- Metadata: optional, because this checkpoint contains the ordered features and threshold

The exact notebook architecture is implemented in `backend/dcn.py`; unrelated PyTorch architectures are not accepted. The threshold is read from the uploaded checkpoint.

### SMOTE-trained models

SMOTE is applied during training only. Save the fitted estimator and fitted scaler with the exact selected feature names in metadata. The notebook’s SMOTE experiments use **40 selected features**, while the saved MLP and true DCN use 107. Both are supported by specifying the correct ordered subset.

The experiment named “DCN + SMOTE” in the notebook is a deeper scikit-learn MLP, **not** the PyTorch Deep & Cross Network. Upload that experiment as Scikit-learn.

`scripts/export_smote_models.py` contains a helper to run in the notebook after the relevant models have been trained. It does not train or alter the models.

### Notebook deployment packages in `Main project/model`

All six package folders passed a sample inference check. Upload files from one folder together:

| Folder | Format | Model file | Additional file |
| --- | --- | --- | --- |
| `dcn` | PyTorch TorchScript | `model.pt` | `preprocessor.pkl` |
| `dcn_smote`, `mlp_smote`, `logistic_regression_smote` | Scikit-learn | `model.pkl` | `preprocessor.pkl` |
| `lightgbm` | LightGBM | `model.txt` | none |
| `catboost` | CatBoost | `model.cbm` | `categorical_features.json` |

Each folder also provides `metadata.json` and `feature_columns.json`. Upload both. The app handles the two known LightGBM feature name variants and CatBoost's native categorical columns.

### Other sklearn / Keras models

Download the metadata template from the UI and edit it. Metadata requires `feature_columns` or `feature_order`, plus `threshold`. Numeric models must use supported project features; CatBoost models must declare their categorical columns.

Scikit-learn pipelines should contain all fitted preprocessing. Bare estimators require a separate fitted preprocessor, unless metadata explicitly states `preprocessing: "none"` because training used unscaled project numeric features. Provide classifiers with classes `[0, 1]` and `predict_proba`.

Keras support requires `.venv\Scripts\python.exe -m pip install -r requirements-keras.txt`, followed by a restart. Upload a full `.keras`/`.h5` model and its preprocessing. Weight-only H5 files and custom layers are not supported without an adapter. Keras inference was not exercised because no Keras artifact was supplied.

## Feature assumptions and interpretation

- Numeric defaults are computed from the saved training matrix only. Low-cardinality columns use training modes so binary/ordinal features stay valid; other columns use training medians.
- The form supplies age, annual income, credit, annuity, employment duration, education, income type, contract, car ownership, and optional external scores 2/3 and late-payment rate.
- Encodings, right-closed age bands, and income/credit quantile boundaries follow the notebook. Income dummies, age/income/credit groups, credit-to-income, and debt-to-income derivatives are recomputed for each case.
- Historical details that cannot be known from 12 inputs remain assumptions. Independently filled history fields need not form a realistic joint profile. Every assumed/entered/derived feature is exposed with the result.
- Scores from class-weighted or SMOTE models are **not calibrated population default probabilities**. The UI deliberately calls these model scores. Full-feature validation metrics do not measure performance on median-filled manual cases.
- The explanation replaces each entered input with its reference value and recalculates dependent features. The score difference is a local sensitivity, **not SHAP**, additive attribution, causation, or a guarantee of a different lending outcome.
- TARGET is recorded repayment difficulty as defined by Home Credit, not a forecast over a newly specified time horizon. This application is for research, not automated credit eligibility decisions.

## API and tests

Interactive API reference: **http://127.0.0.1:8000/docs**.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests cover Power BI totals, filtering/empty cohorts, feature ordering and transformations, real MLP inference parity, original DCN loading, upload/removal, bad inputs, cross-origin protections, chat setup errors, and chart assets. Artifact-dependent tests are skipped when original model files are absent. Tests use temporary model registries.

Main endpoints: `GET /api/config`, `GET /api/dashboard`, `GET /api/eda`, `GET/POST /api/models`, `DELETE /api/models/{id}`, `POST /api/predict`, `POST /api/batch/predict`, `POST /api/batch/detail`, `POST /api/compare`, and `POST /api/chat`.

## Deployment boundaries

This is a working **local research application**, not an internet-hardened service. There are no multi-user accounts. It restricts hostnames and cross-origin writes, limits upload sizes, checks model schemas, and optionally requires `CREDITSCOPE_ADMIN_TOKEN` for model mutations and AI use. Before remote hosting, add authentication/authorization, HTTPS, request/rate limits, isolated model-loading workers, monitoring, backups, and a reviewed borrower-data policy. Do not expose the development server or unrestricted serialized-model uploads to the internet.

Deleted models are moved to `storage/archived/` and disappear from prediction immediately. Original model files outside this project are never removed.
