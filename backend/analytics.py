from functools import lru_cache
import json

import pandas as pd

from .features import ROOT

FILTERS = {
    'age_group':('AGE_GROUP_LABEL','Age group'),
    'gender':('CODE_GENDER','Gender'),
    'education':('NAME_EDUCATION_TYPE','Education'),
    'income_type':('NAME_INCOME_TYPE','Income type'),
    'overdue':('HAS_BUREAU_OVERDUE_LABEL','Bureau overdue'),
    'debt_group':('DEBT_INCOME_GROUP','Debt / income'),
}

@lru_cache(maxsize=1)
def applicants():
    return pd.read_pickle(ROOT / 'data/applicants.pkl')

def records(df):
    return json.loads(df.to_json(orient='records'))

def research(name):
    return records(pd.read_csv(ROOT / 'data/research' / (name+'.csv')))

def group(df, column):
    out = df.groupby(column,dropna=False,observed=True).TARGET.agg(['count','sum','mean']).reset_index()
    out.columns = ['group','applicants','defaults','rate']
    out['group'] = out['group'].fillna('Missing').astype(str)
    return records(out)

@lru_cache(maxsize=128)
def dashboard(filters_tuple=()):
    df = applicants()
    for key,value in filters_tuple:
        if key not in FILTERS: raise ValueError('Unknown filter: '+key)
        if value:
            df = df[df[FILTERS[key][0]].fillna('Missing').astype(str)==value]
    n = len(df)
    def mean(c): return float(df[c].mean()) if n and df[c].notna().any() else None
    matrix = df.groupby(['AGE_GROUP_LABEL','INCOME_QUINTILE'],observed=True).TARGET.agg(['count','sum','mean']).reset_index()
    matrix.columns=['age','income','applicants','defaults','rate']
    return {'applicants':n, 'defaults':int(df.TARGET.sum()), 'default_rate':mean('TARGET'),
            'average_income':mean('AMT_INCOME_TOTAL'), 'average_credit':mean('AMT_CREDIT'),
            'total_exposure':float(df.AMT_CREDIT.sum()) if n else 0,
            'difficulty_exposure':float(df.loc[df.TARGET==1,'AMT_CREDIT'].sum()) if n else 0,
            'average_age':mean('AGE_YEARS'), 'average_ratio':mean('CREDIT_INCOME_RATIO'),
            'age':group(df,'AGE_GROUP_LABEL'), 'debt':group(df,'DEBT_INCOME_GROUP'),
            'income':group(df,'NAME_INCOME_TYPE'), 'education':group(df,'NAME_EDUCATION_TYPE'),
            'matrix':records(matrix), 'filtered':bool(filters_tuple),
            'source':'Full Power BI applicant export · 307,511 records',
            'population':len(applicants())}

def filter_options():
    return [{'key':k,'label':label,'options':sorted(applicants()[c].dropna().astype(str).unique().tolist())}
            for k,(c,label) in FILTERS.items()]
