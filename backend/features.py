import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[1]


class Applicant(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    age: float = Field(44, ge=19, le=100)
    income: float = Field(157500, ge=1000, le=100_000_000)
    credit: float = Field(513531, ge=1000, le=100_000_000)
    annuity: float = Field(24903, ge=1, le=10_000_000)
    employment_years: float = Field(4.5, ge=0, le=85)
    education: Literal['Lower secondary', 'Secondary / secondary special', 'Incomplete higher', 'Higher education', 'Academic degree'] = 'Secondary / secondary special'
    income_type: Literal['Working', 'Commercial associate', 'Pensioner', 'State servant', 'Other'] = 'Working'
    contract_type: Literal['Cash loans', 'Revolving loans'] = 'Cash loans'
    own_car: bool = False
    external_score_2: float | None = Field(None, ge=0, le=1)
    external_score_3: float | None = Field(None, ge=0, le=1)
    late_payment_rate: float | None = Field(None, ge=0, le=1)

    @model_validator(mode='after')
    def employment_check(self):
        if self.employment_years > self.age - 14:
            raise ValueError('Employment duration cannot start before age 14.')
        return self


def schema():
    return json.loads((ROOT / 'data/schema.json').read_text(encoding='utf-8'))


def bucket(value, edges):
    # pandas cut semantics: right-closed bins; clamp new out-of-range values.
    return int(np.clip(np.searchsorted(edges[1:-1], value, side='left'), 0, len(edges)-2))


def make_features(case: Applicant, columns: list[str]):
    spec = schema()
    values = spec['defaults'].copy()
    sources = {c: spec['methods'][c] for c in values}
    def put(key, value, source='Entered'):
        values[key] = float(value)
        sources[key] = source
    direct = {'AGE_YEARS': case.age, 'AMT_INCOME_TOTAL': case.income,
              'AMT_CREDIT': case.credit, 'AMT_ANNUITY': case.annuity,
              'DAYS_EMPLOYED': -case.employment_years * 365,
              'NAME_EDUCATION_TYPE': ['Lower secondary','Secondary / secondary special','Incomplete higher','Higher education','Academic degree'].index(case.education)+1,
              'NAME_CONTRACT_TYPE': int(case.contract_type == 'Revolving loans'), 'FLAG_OWN_CAR': int(case.own_car)}
    for c,v in direct.items(): put(c,v)
    for c,v in [('EXT_SOURCE_2',case.external_score_2), ('EXT_SOURCE_3',case.external_score_3), ('LATE_PAYMENT_RATE',case.late_payment_rate)]:
        if v is not None: put(c,v)
    for suffix in ['Other','Pensioner','State servant','Working']:
        put('NAME_INCOME_TYPE_'+suffix, int(case.income_type == suffix))
    put('CREDIT_INCOME_RATIO', case.credit/case.income, 'Derived from entered amounts')
    put('AGE_GROUP', bucket(case.age, [18,25,35,45,55,65,100]), 'Derived from age')
    put('INCOME_GROUP', bucket(case.income,spec['bins']['AMT_INCOME_TOTAL']), 'Derived using notebook quantiles')
    put('CREDIT_GROUP', bucket(case.credit,spec['bins']['AMT_CREDIT']), 'Derived using notebook quantiles')
    debt_ratio = values['BUREAU_TOTAL_DEBT'] / case.income
    put('BUREAU_DEBT_INCOME_RATIO', debt_ratio, 'Derived from assumed debt and entered income')
    put('BUREAU_DEBT_INCOME_GROUP', bucket(debt_ratio,spec['bins']['BUREAU_DEBT_INCOME_RATIO']), 'Derived using notebook quantiles')
    put('DEBT_INCOME_GROUP', bucket(debt_ratio, [-.001,0,1,2,4,8,float('inf')]), 'Derived from assumed debt and entered income')
    unknown = set(columns) - set(values)
    if unknown: raise ValueError('Unsupported features: ' + ', '.join(sorted(unknown)))
    frame = pd.DataFrame([[values[c] for c in columns]], columns=columns)
    assumptions = [{'feature':c, 'value':values[c], 'source':sources[c]} for c in columns]
    return frame, assumptions


FEATURE_ALIASES = {
    'NAME_INCOME_TYPE_State_servant': 'NAME_INCOME_TYPE_State servant',
    'WALLSMATERIAL_MODE_Stone_brick': 'WALLSMATERIAL_MODE_Stone, brick',
}


@lru_cache(maxsize=32)
def category_mode(name):
    from .analytics import applicants
    cohort = applicants()
    series = cohort[name].dropna().astype(str) if name in cohort else pd.Series(dtype=str)
    return series.mode().iloc[0] if len(series) else 'Missing'


@lru_cache(maxsize=4)
def category_frequency(name):
    from .analytics import applicants
    return applicants()[name].value_counts(normalize=True).to_dict()


def make_model_features(case: Applicant, columns: list[str], categorical: list[str] | None = None,
                        supplied: dict | None = None):
    """Build the exact ordered input for numeric and native-categorical exports."""
    categorical = set(categorical or [])
    spec = schema()
    supplied = supplied or {}
    numerical = [FEATURE_ALIASES.get(c, c) for c in columns if c not in categorical]
    frame, assumptions = make_features(case, numerical)
    values = dict(zip(numerical, frame.iloc[0].tolist()))
    origins = {a['feature']: a['source'] for a in assumptions}
    for name in columns:
        source_name = FEATURE_ALIASES.get(name, name)
        if name in categorical:
            if name in supplied and pd.notna(supplied[name]) and str(supplied[name]).strip():
                value, origin = str(supplied[name]), 'CSV'
            elif name == 'NAME_INCOME_TYPE':
                value, origin = case.income_type, 'Entered'
            elif name == 'NAME_EDUCATION_TYPE':
                value, origin = case.education, 'Entered'
            else:
                value, origin = category_mode(name), 'Training category mode'
            values[name], origins[name] = value, origin
        elif name in supplied and pd.notna(supplied[name]) and str(supplied[name]).strip():
            try:
                number = float(supplied[name])
            except (TypeError, ValueError) as exc:
                raise ValueError(f'{name} must be numeric.') from exc
            if not np.isfinite(number): raise ValueError(f'{name} must be finite.')
            values[source_name], origins[source_name] = number, 'CSV'
    ordered = [values[FEATURE_ALIASES.get(name, name)] for name in columns]
    result = pd.DataFrame([ordered], columns=columns)
    info = [{'feature':name, 'value':ordered[i],
             'source':origins.get(FEATURE_ALIASES.get(name, name), 'Training default')}
            for i, name in enumerate(columns)]
    return result, info


LABELS = {'age':'Age', 'income':'Annual income', 'credit':'Credit amount', 'annuity':'Loan annuity',
          'employment_years':'Employment duration', 'education':'Education', 'income_type':'Income type',
          'contract_type':'Contract type', 'own_car':'Car ownership', 'external_score_2':'External score 2',
          'external_score_3':'External score 3', 'late_payment_rate':'Late payment rate'}


def reference_case():
    d = schema()['defaults']
    return Applicant(age=d['AGE_YEARS'], income=d['AMT_INCOME_TOTAL'], credit=d['AMT_CREDIT'],
                     annuity=d['AMT_ANNUITY'], employment_years=max(0,min(-d['DAYS_EMPLOYED']/365,20)),
                     external_score_2=d['EXT_SOURCE_2'], external_score_3=d['EXT_SOURCE_3'],
                     late_payment_rate=d['LATE_PAYMENT_RATE'])
