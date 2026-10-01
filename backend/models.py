"""Local trusted-artifact registry. Arbitrary pickle files are executable code."""
import hashlib
import json
from pathlib import Path
import threading

import joblib
import numpy as np

from .features import ROOT, Applicant, LABELS, make_features, make_model_features, reference_case, schema

MODEL_DIR = ROOT / 'storage/models'
ARCHIVE_DIR = ROOT / 'storage/archived'
MODEL_DIR.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
CACHE = {}


def read_metadata(folder):
    return json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))


def registry():
    with LOCK:
        result = []
        for folder in MODEL_DIR.iterdir():
            try:
                if folder.is_dir() and (folder / 'metadata.json').exists():
                    result.append(read_metadata(folder))
            except (OSError, ValueError, json.JSONDecodeError):
                # An incomplete or inaccessible upload must not prevent the app
                # from listing the remaining deployable models.
                continue
        return sorted(result, key=lambda m:m['name'])


def model_folder(model_id):
    if not model_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in model_id):
        raise ValueError('Invalid model ID.')
    folder = MODEL_DIR / model_id
    if not (folder / 'metadata.json').exists(): raise FileNotFoundError('Model not found.')
    return folder


def load(folder, meta):
    key = str(folder)
    if key in CACHE: return CACHE[key]
    artifact = folder / meta['artifact']
    if meta['kind'] == 'sklearn':
        model = joblib.load(artifact)
        if not hasattr(model,'predict_proba'): raise ValueError('Model must provide predict_proba.')
        if list(getattr(model,'classes_',[])) != [0,1]: raise ValueError('Expected binary classes [0, 1].')
        columns = meta['feature_columns']
        if getattr(model,'n_features_in_',len(columns)) != len(columns): raise ValueError('Feature count does not match model.')
        if hasattr(model,'feature_names_in_') and list(model.feature_names_in_) != columns:
            raise ValueError('Feature order differs from the trained pipeline.')
        preprocessor = joblib.load(folder / meta['preprocessor']) if meta.get('preprocessor') else None
        has_preprocessing = hasattr(model, 'steps') and len(model.steps) > 1
        if preprocessor is None and not has_preprocessing and meta.get('preprocessing') != 'none':
            raise ValueError('A bare estimator requires its fitted preprocessor. If training used unscaled numeric features, declare preprocessing: "none" in metadata.')
        def predict(x):
            if preprocessor is not None: x = transform(preprocessor,x)
            return model.predict_proba(x)[:,1]
    elif meta['kind'] == 'pytorch_dcn':
        import torch
        from .dcn import DeepCrossNetwork
        torch.set_num_threads(2)
        checkpoint = torch.load(artifact, map_location='cpu', weights_only=True)
        if list(checkpoint['feature_columns']) != meta['feature_columns']: raise ValueError('Checkpoint feature order differs from metadata.')
        model = DeepCrossNetwork(checkpoint['input_dim'], checkpoint.get('cross_layers',3))
        model.load_state_dict(checkpoint['model_state_dict'])
        model.eval()
        prep = joblib.load(folder / meta['preprocessor'])
        def predict(x):
            with torch.no_grad():
                return torch.sigmoid(model(torch.tensor(transform(prep,x),dtype=torch.float32))).numpy().ravel()
    elif meta['kind'] == 'torchscript':
        import torch
        torch.set_num_threads(2)
        model = torch.jit.load(str(artifact), map_location='cpu')
        model.eval()
        prep = joblib.load(folder / meta['preprocessor'])
        def predict(x):
            with torch.no_grad():
                output = model(torch.tensor(transform(prep,x), dtype=torch.float32))
                return np.asarray(torch.sigmoid(output).detach().numpy()).ravel()
    elif meta['kind'] == 'lightgbm':
        import lightgbm as lgb
        model = lgb.Booster(model_file=str(artifact))
        if model.num_feature() != len(meta['feature_columns']): raise ValueError('LightGBM feature count does not match metadata.')
        def predict(x): return model.predict(x)
    elif meta['kind'] == 'catboost':
        from catboost import CatBoostClassifier
        model = CatBoostClassifier()
        model.load_model(str(artifact))
        if model.feature_names_ and list(model.feature_names_) != meta['feature_columns']:
            raise ValueError('CatBoost feature order differs from metadata.')
        def predict(x): return model.predict_proba(x)[:,1]
    elif meta['kind'] == 'keras':
        try: import tensorflow as tf
        except ImportError as exc: raise ValueError('Keras requires the optional TensorFlow runtime. Install requirements-keras.txt, then restart.') from exc
        model = tf.keras.models.load_model(artifact, compile=False, safe_mode=True)
        if model.input_shape[-1] != len(meta['feature_columns']): raise ValueError('Keras input shape differs from feature count.')
        prep = joblib.load(folder / meta['preprocessor']) if meta.get('preprocessor') else None
        def predict(x):
            x = transform(prep,x) if prep is not None else x.to_numpy(dtype=float)
            output = np.asarray(model.predict(x,verbose=0))
            if output.ndim == 2 and output.shape[1] == 2: return output[:,1]
            return output.ravel()
    else: raise ValueError('Unsupported model type.')
    def checked(x):
        result = np.asarray(predict(x), dtype=float)
        if result.shape != (len(x),) or not np.isfinite(result).all() or ((result<0)|(result>1)).any():
            raise ValueError('Model must return finite default probabilities between 0 and 1.')
        return result
    # Deployment is conditional on a successful inference, never just an upload.
    checked(make_model_features(reference_case(), meta['feature_columns'], meta.get('categorical_features'))[0])
    CACHE[key] = checked
    return checked


def transform(prep, x):
    if isinstance(prep,dict): return prep['scaler'].transform(prep['imputer'].transform(x))
    return prep.transform(x)


def predict_case(model_id, case: Applicant, explain=True, supplied=None):
    with LOCK:
        folder = model_folder(model_id)
        meta = read_metadata(folder)
        predict = load(folder,meta)
        row, assumptions = make_model_features(case,meta['feature_columns'],meta.get('categorical_features'),supplied)
        probability = float(predict(row)[0])
        contributions = []
        if explain:
            baseline = reference_case()
            if supplied:
                import pandas as pd
                reference, _ = make_model_features(baseline,meta['feature_columns'],meta.get('categorical_features'))
                changes=[]
                for feature in meta['feature_columns']:
                    if feature not in supplied or row.iloc[0][feature] == reference.iloc[0][feature]: continue
                    counter=row.copy()
                    counter.at[0,feature]=reference.at[0,feature]
                    changes.append((feature,counter))
                # Each effect is a separate one-feature counterfactual against
                # the model's own reference value, never a causal explanation.
                altered_probs=predict(pd.concat([counter for _,counter in changes],ignore_index=True)) if changes else []
                for (feature,_),altered in zip(changes,altered_probs):
                    contributions.append({'field':feature,'label':feature.replace('_',' ').title(),
                        'value':row.at[0,feature], 'reference':reference.at[0,feature],
                        'change':probability-altered,'reference_score':altered})
            else:
            # Replace one user input at a time, recomputing dependent features.
            # These are local sensitivities, not additive or causal SHAP values.
                rows, entries = [], []
                for field,label in LABELS.items():
                    if getattr(case,field) == getattr(baseline,field): continue
                    counter = case.model_copy(update={field:getattr(baseline,field)})
                    rows.append(make_model_features(counter,meta['feature_columns'],meta.get('categorical_features'))[0])
                    entries.append((field,label,getattr(case,field),getattr(baseline,field)))
                if rows:
                    import pandas as pd
                    counter_probs = predict(pd.concat(rows,ignore_index=True))
                    for (field,label,value,reference), p in zip(entries,counter_probs):
                        contributions.append({'field':field,'label':label,'value':value,'reference':reference,
                                              'change':probability-float(p),'reference_score':float(p)})
            contributions.sort(key=lambda c:abs(c['change']), reverse=True)
        default = probability >= meta['threshold']
        filled = sum(a['source'].startswith('Training') for a in assumptions)
        return {'model_id':model_id,'model_name':meta['name'], 'probability':probability,
                'threshold':meta['threshold'],'prediction':int(default),
                'label':'Default risk flagged' if default else 'Default risk not flagged',
                'feature_count':len(assumptions),'assumed_features':filled, 'assumptions':assumptions,
                'contributions':contributions,'calibrated':meta.get('calibrated',False),
                'explanation_method':('One-feature-at-a-time replacement against reference values.' if supplied else
                                      'One-input-at-a-time replacement against training reference values; dependent features recomputed.')+
                                      ' Effects are not additive and do not establish causation.',
                'caveat':'This is a model score, not a calibrated real-world default rate. Unknown history uses training defaults. Research use only; not a lending decision.',
                'inputs':case.model_dump()}
