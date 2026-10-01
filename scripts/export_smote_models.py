r"""Run in the notebook kernel after training; saves only, never retrains.

Example notebook cell:
    import sys
    sys.path.insert(0, r'C:\Mim\6th trimester\Data Analytics\Main project\Credit-scope')
    from scripts.export_smote_models import export_model
    export_model(mlp_smote, scaler_smote, X_train_selected.columns,
                 'MLP + SMOTE', 'model/mlp_smote', threshold=0.5)
    export_model(dcn_smote, scaler_smote, X_train_selected.columns,
                 'DCN + SMOTE', 'model/dcn_smote', threshold=0.5)

Choose thresholds using validation data. 0.5 matches the notebook's .predict.
"""
import json
from pathlib import Path
import joblib


def export_model(model, preprocessor, feature_columns, name, output_dir, threshold):
    directory=Path(output_dir)
    directory.mkdir(parents=True,exist_ok=True)
    columns=list(feature_columns)
    if getattr(model,'n_features_in_',None)!=len(columns):
        raise ValueError('Ordered feature list must match the trained model.')
    if not 0<float(threshold)<1:
        raise ValueError('Threshold must lie between 0 and 1.')
    joblib.dump(model,directory/'model.joblib')
    joblib.dump(preprocessor,directory/'preprocessor.joblib')
    (directory/'metadata.json').write_text(json.dumps({
        'name':name,'kind':'sklearn','feature_columns':columns,'threshold':float(threshold),
        'description':'SMOTE-trained model; separate fitted training preprocessor',
        'input_space':'creditscope_numeric_v1','calibrated':False,
    },indent=2),encoding='utf-8')
    return directory.resolve()
