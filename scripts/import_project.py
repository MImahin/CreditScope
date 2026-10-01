"""Import local research assets without executing notebook code or altering sources."""
import base64
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
SOURCE = Path(os.getenv('CREDITSCOPE_SOURCE', ROOT.parent / 'home-credit-default-risk')).resolve()
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
(DATA / 'eda').mkdir(exist_ok=True)
(DATA / 'research').mkdir(exist_ok=True)
(ROOT / 'storage' / 'models').mkdir(parents=True, exist_ok=True)

def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')

print('Importing Power BI applicant data...', flush=True)
frame = pd.read_csv(SOURCE / 'forpowebi' / 'fact_applicants.csv', low_memory=False)
frame.to_pickle(DATA / 'applicants.pkl')
for f in (SOURCE / 'forpowebi').glob('*.csv'):
    if f.stat().st_size < 1_000_000:
        shutil.copy2(f, DATA / 'research' / f.name)

print('Computing training-only defaults...', flush=True)
train = pd.read_csv(SOURCE / 'processed' / 'X_train.csv')
defaults, methods = {}, {}
for col in train:
    discrete = train[col].nunique() <= 12
    defaults[col] = float(train[col].mode().iloc[0] if discrete else train[col].median())
    methods[col] = 'Training mode' if discrete else 'Training median'
raw = pd.read_csv(SOURCE / 'application_train.csv', usecols=['AMT_INCOME_TOTAL', 'AMT_CREDIT'])
bins = {c: pd.qcut(raw[c], q=5, duplicates='drop', retbins=True)[1].tolist() for c in raw}
# The notebook fits debt quantiles before clipping negative debt. Recover those
# exact group boundaries from the exported interval labels, not a new quantile fit.
# Export labels are rounded. Use original aggregate debt to reconstruct exact bins.
bureau = pd.read_csv(SOURCE / 'bureau.csv', usecols=['SK_ID_CURR', 'AMT_CREDIT_SUM_DEBT'])
debt = bureau.groupby('SK_ID_CURR')['AMT_CREDIT_SUM_DEBT'].sum()
ratio = frame['SK_ID_CURR'].map(debt).fillna(0) / frame['AMT_INCOME_TOTAL']
bins['BUREAU_DEBT_INCOME_RATIO'] = pd.qcut(ratio, q=5, duplicates='drop', retbins=True)[1].tolist()
write(DATA / 'schema.json', {'features': list(train.columns), 'defaults': defaults, 'methods': methods, 'bins': bins,
                           'training_rows': len(train), 'source': 'Notebook processed/X_train.csv'})

if '--include-models' in sys.argv:
    print('Importing saved models...', flush=True)
    mlp_dir = ROOT / 'storage/models/mlp'
    mlp_dir.mkdir(exist_ok=True)
    shutil.copy2(SOURCE / 'model/mlp/mlp_pipeline.joblib', mlp_dir / 'model.joblib')
    meta = json.loads((SOURCE / 'model/mlp/metadata.json').read_text())
    meta.update(id='mlp', name='MLP', kind='sklearn', artifact='model.joblib', status='ready',
                description='Multilayer perceptron · 128 / 64 / 32 · balanced sample weights',
                threshold=meta['recommended_threshold'], provenance='Original saved notebook model', calibrated=False)
    write(mlp_dir / 'metadata.json', meta)
    dcn_dir = ROOT / 'storage/models/dcn'
    dcn_dir.mkdir(exist_ok=True)
    shutil.copy2(SOURCE / 'model/dcn/credit_dcn.pth', dcn_dir / 'model.pth')
    shutil.copy2(SOURCE / 'model/dcn/preprocessor.joblib', dcn_dir / 'preprocessor.joblib')
    write(dcn_dir / 'metadata.json', {
        'id':'dcn', 'name':'DCN', 'kind':'pytorch_dcn', 'artifact':'model.pth', 'preprocessor':'preprocessor.joblib',
        'feature_columns':list(train.columns), 'threshold':0.6852558255195618, 'status':'ready', 'calibrated':False,
        'description':'Deep & Cross Network · 3 cross layers · weighted loss',
        'provenance':'Original saved checkpoint; architecture and metrics from notebook cell 124',
        'validation_metrics':{'roc_auc':0.7562217438657678, 'pr_auc':0.24930560357202514, 'recall':0.3812688821752266, 'f1':0.3130736789878442},
    })
notebook = ROOT.parent / 'DA_Project_Organized_End_to_End.ipynb'
nb = json.loads(notebook.read_text(encoding='utf-8'))
gallery, sections, section = [], [], 'Project overview'
summary_cell_index = next((index for index, cell in enumerate(nb['cells'])
                           if 'COMPLETE MODEL PERFORMANCE SUMMARY + ALL COMPARISON PLOTS'
                           in ''.join(cell.get('source', []))), -1)
specific_titles = {
    (21,1): 'Default rate across income quintiles',
    (24,2): 'Default rate across credit-amount quintiles',
    (24,3): 'Default rate across credit-to-income quintiles',
    (27,4): 'Default rate by age group',
    (34,1): 'Default rate by bureau history',
    (34,3): 'Default rate by previous bureau overdue',
    (34,5): 'Default rate by overdue severity',
    (34,7): 'Default rate by bureau credit count',
    (34,9): 'Default rate by debt-to-income group',
    (40,1): 'Current repayment difficulty by previous application status',
    (summary_cell_index,2): 'ROC-AUC comparison of all models',
    (summary_cell_index,3): 'PR-AUC comparison of all models',
    (summary_cell_index,4): 'Precision comparison of all models',
    (summary_cell_index,5): 'Recall comparison of all models',
    (summary_cell_index,6): 'F1 score comparison of all models',
    (summary_cell_index,7): 'Accuracy comparison of all models',
    (summary_cell_index,8): 'ROC curves - all trained models',
    (summary_cell_index,9): 'Precision-recall curves - all trained models',
    (summary_cell_index,10): 'ROC-AUC before vs after SMOTE',
    (summary_cell_index,11): 'PR-AUC before vs after SMOTE',
    (summary_cell_index,12): 'F1 score before vs after SMOTE',
    (summary_cell_index,13): 'Precision before vs after SMOTE',
    (summary_cell_index,14): 'Recall before vs after SMOTE',
}
comparison_models = [
    'Logistic Regression (Top 40)', 'Random Forest (Top 40)',
    'Logistic Regression (107)', 'LightGBM', 'CatBoost', 'XGBoost',
    'MLP', 'DCN', 'Logistic Regression + SMOTE', 'MLP + SMOTE',
    'DCN + SMOTE',
]
for output_index, model_name in enumerate(comparison_models, start=15):
    specific_titles[(summary_cell_index, output_index)] = f'{model_name} confusion matrix'
for i, cell in enumerate(nb['cells']):
    src = ''.join(cell.get('source', []))
    if cell['cell_type'] == 'markdown':
        sections.append({'cell': i, 'text':src})
        heading = re.search(r'^#{1,3}\s+(.+)', src, re.M)
        if heading: section = heading.group(1)
    for j, output in enumerate(cell.get('outputs', [])):
        payload = output.get('data', {}).get('image/png')
        if payload:
            filename = f'cell-{i}-{j}.png'
            (DATA / 'eda' / filename).write_bytes(base64.b64decode(''.join(payload)))
            titles = re.findall(r'(?:set_title|plt.title)\([f]?\s*[\'"]([^\'"\n]+)', src)
            title = titles[min(j, len(titles)-1)] if titles else section
            title = specific_titles.get((i,j),title)
            category = 'Model evaluation' if i >= 80 else 'Exploratory analysis'
            if category == 'Model evaluation':
                lower = title.lower()
                plot_group = ('Confusion matrices' if 'confusion matrix' in lower else
                              'Curves' if 'curve' in lower else
                              'Feature importance' if 'importance' in lower else 'Comparisons')
            else:
                plot_group = 'Exploratory analysis'
            plot_section = 'Complete model performance summary' if i == summary_cell_index else section
            gallery.append({'id':filename, 'title':title, 'section':plot_section, 'cell':i,
                            'category':category, 'group':plot_group,
                            'url':'/assets/eda/' + filename})

# The final notebook cell displays the complete model leaderboard as HTML. Export
# it to a small CSV so the web app can render the same values as a sortable table.
for cell in reversed(nb['cells']):
    for output in cell.get('outputs', []):
        table_html = ''.join(output.get('data', {}).get('text/html', []))
        if 'ROC-AUC' not in table_html or 'PR-AUC' not in table_html or '>Group<' not in table_html:
            continue
        rows = []
        for row_html in re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.S):
            values = [html.unescape(re.sub(r'<[^>]+>', '', value)).strip()
                      for value in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.S)]
            if len(values) == 8:
                rows.append(values)
        if rows:
            columns = ['Model','Group','Accuracy','Precision','Recall','F1','ROC_AUC','PR_AUC']
            metrics = pd.DataFrame(rows, columns=columns)
            for column in columns[2:]:
                metrics[column] = pd.to_numeric(metrics[column])
            metrics.to_csv(DATA / 'research' / 'model_metrics.csv', index=False)
            break
    else:
        continue
    break
write(DATA / 'gallery.json', gallery)
write(DATA / 'notebook_context.json', sections)
write(DATA / 'provenance.json', {'notebook':notebook.name, 'dataset':'Home Credit Default Risk',
    'applicants':len(frame), 'defaults':int(frame.TARGET.sum()), 'feature_count':len(train.columns),
    'charts':len(gallery), 'dashboard_source':'Power BI fact_applicants.csv (full dataset)',
    'notes':['TARGET means recorded repayment difficulty in the source dataset.',
             'SMOTE models were evaluated in the notebook but their weights were not found.',
             'The notebook DCN + SMOTE experiment is a deeper MLP, distinct from the saved Deep & Cross Network.']})
print(f'Imported {len(frame):,} applicants, {len(gallery)} original charts, with model import optional (--include-models).', flush=True)
