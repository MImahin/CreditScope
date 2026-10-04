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

## Deploy trained models

Open **Deploy model** in the sidebar. A model is added only after CreditScope loads the submitted files and successfully scores a reference applicant. Upload only files you created or trust: loading serialized joblib and pickle files can execute code.

### What each upload field means

| Screen field | What to provide |
| --- | --- |
| **Model name** | Any clear display name, such as `MLP + SMOTE` or `LightGBM`. |
| **Model format** | The runtime matching the artifact. The exact choices for the supplied packages are listed below. |
| **Trained model file** | The main `.pkl`, `.joblib`, `.pt`, `.pth`, `.txt`, `.cbm`, `.h5`, or `.keras` artifact. |
| **Metadata JSON** | A JSON object containing a classification `threshold` between 0 and 1 and either `feature_columns` or `feature_order`. The supplied `metadata.json` files already contain these values. |
| **Preprocessor** | The fitted `.pkl` or `.joblib` scaler/imputer when it is stored separately. It is mandatory for PyTorch DCN and TorchScript uploads. |
| **Feature columns** | An ordered JSON list of training feature names. Upload `feature_columns.json` when supplied; it overrides the feature list in metadata. |
| **CatBoost categorical columns** | An ordered JSON list naming CatBoost's native categorical features. Leave blank for every format except CatBoost. |
| **Trusted-files checkbox** | Must be checked before deployment. |

Click **Validate & deploy**. A successful model immediately appears in **Individual prediction** and **Batch CSV check**. A rejected upload remains unavailable and the error explains the mismatched file, feature order, preprocessor, or output.

### Exact choices for `Main project/model`

Use files from one folder on each deployment. Do not mix preprocessors or feature lists between folders.

| Folder | Model name suggestion | Select **Model format** | **Trained model file** | **Metadata JSON** | **Preprocessor** | **Feature columns** | **CatBoost categorical columns** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dcn` | `DCN` | **PyTorch TorchScript · pt** | `model.pt` | `metadata.json` | `preprocessor.pkl` | `feature_columns.json` | Leave blank |
| `dcn_smote` | `DCN + SMOTE` | **Scikit-learn · joblib / pkl** | `model.pkl` | `metadata.json` | `preprocessor.pkl` | `feature_columns.json` | Leave blank |
| `mlp_smote` | `MLP + SMOTE` | **Scikit-learn · joblib / pkl** | `model.pkl` | `metadata.json` | `preprocessor.pkl` | `feature_columns.json` | Leave blank |
| `logistic_regression_smote` | `Logistic Regression + SMOTE` | **Scikit-learn · joblib / pkl** | `model.pkl` | `metadata.json` | `preprocessor.pkl` | `feature_columns.json` | Leave blank |
| `lightgbm` | `LightGBM` | **LightGBM · txt** | `model.txt` | `metadata.json` | Leave blank | `feature_columns.json` | Leave blank |
| `catboost` | `CatBoost` | **CatBoost · cbm** | `model.cbm` | `metadata.json` | Leave blank | `feature_columns.json` | `categorical_features.json` |

Files that are present only as alternative exports are not needed by this upload form:

- For `lightgbm`, use `model.txt`; do not upload `model.pkl`.
- For `catboost`, use `model.cbm`; do not upload `model.pkl` or `categorical_feature_indices.json`.
- `dcn_smote` is a scikit-learn neural-network experiment trained with SMOTE. It is not the PyTorch DCN architecture, so select **Scikit-learn**, not **PyTorch DCN checkpoint** or **TorchScript**.
- SMOTE is used during training only. CreditScope never applies SMOTE to a new applicant during prediction.

The supplied DCN, LightGBM, and full numeric packages use 107 ordered features. The three supplied SMOTE packages use their saved 40-feature subsets. CatBoost uses 103 ordered features, including its declared native categorical columns.

### Original notebook MLP and DCN artifacts

These older artifacts use different selections from the packaged folders above:

| Model | Select **Model format** | **Trained model file** | Other files |
| --- | --- | --- | --- |
| Original MLP | **Scikit-learn · joblib / pkl** | `home-credit-default-risk/model/mlp/mlp_pipeline.joblib` | Upload its `metadata.json`. A separate preprocessor is unnecessary because the pipeline contains preprocessing. Its saved threshold is `0.6544190978641563`. |
| Original DCN checkpoint | **PyTorch DCN checkpoint · pth / pt** | `home-credit-default-risk/model/dcn/credit_dcn.pth` | Upload `preprocessor.joblib`. Metadata is optional only when the checkpoint itself contains both the exact `feature_columns` and `threshold`. |

The **PyTorch DCN checkpoint** option accepts the specific architecture implemented in `backend/dcn.py`. Use **PyTorch TorchScript** for an exported `model.pt` such as `Main project/model/dcn/model.pt`.

### Deploying another scikit-learn model

A scikit-learn classifier must provide `predict_proba`, use binary classes `[0, 1]`, and preserve the exact training feature order.

- A fitted pipeline containing preprocessing can be uploaded without a separate preprocessor.
- A bare fitted estimator normally requires its fitted preprocessor as a separate `.pkl` or `.joblib` file.
- If a bare estimator was intentionally trained on unscaled CreditScope numeric features, set `"preprocessing": "none"` in metadata.
- Metadata must include a valid threshold and feature list. You can download a starter metadata template from the **Deploy model** page.

`scripts/export_smote_models.py` can package trained notebook SMOTE estimators. It does not train models or apply resampling during inference.

### Deploying a Keras model

Install the optional TensorFlow runtime and restart CreditScope:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-keras.txt
```

Then select **Keras · h5 / keras** and upload a complete `.keras` or `.h5` model, metadata, the ordered feature list, and its fitted preprocessor when preprocessing is external. Weight-only H5 files and models requiring unavailable custom layers are not supported without a custom adapter.

### Common deployment errors

| Error | Resolution |
| --- | --- |
| `File extension does not match the chosen model type` | Choose the table's exact format for the selected artifact. |
| `Provide an ordered feature_columns array` | Upload `feature_columns.json`, or include `feature_columns`/`feature_order` in metadata. |
| `Provide a classification threshold between 0 and 1` | Add `threshold` to metadata. Do not use 0 or 1. |
| `DCN requires its saved preprocessor` | Upload the matching `preprocessor.pkl` or `preprocessor.joblib`. |
| `A bare estimator requires its fitted preprocessor` | Upload the estimator's fitted preprocessor or correctly declare `"preprocessing": "none"`. |
| `Unsupported model features` | Use the exact feature list generated for CreditScope; do not mix files from another package. |
| `Feature order differs` or `feature count does not match` | Upload the feature list saved with that exact trained artifact. |
| CatBoost categorical-feature error | Upload `categorical_features.json` and ensure every listed categorical name also appears in `feature_columns.json`. |

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
