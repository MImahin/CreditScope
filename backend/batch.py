"""CSV applicant import for local batch inference."""
import csv
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from io import StringIO
import math
import threading
import uuid

from .features import Applicant, category_frequency

MAX_ROWS = 50000
MAX_BYTES = 60 * 1024 * 1024
SESSIONS = OrderedDict()
SESSION_LOCK = threading.RLock()


def remember(model_id, rows):
    token=uuid.uuid4().hex
    with SESSION_LOCK:
        cutoff=datetime.now(timezone.utc)-timedelta(hours=1)
        for key,item in list(SESSIONS.items()):
            if item['created_at']<cutoff: SESSIONS.pop(key,None)
        SESSIONS[token]={'model_id':model_id,'rows':rows,'created_at':datetime.now(timezone.utc)}
        while len(SESSIONS)>2: SESSIONS.popitem(last=False)
    return token


def selected(batch_id, row_number):
    with SESSION_LOCK:
        item=SESSIONS.get(batch_id)
        if not item or item['created_at']<datetime.now(timezone.utc)-timedelta(hours=1):
            raise ValueError('This batch has expired. Upload the CSV again.')
        if row_number<1 or row_number>len(item['rows']): raise ValueError('Applicant row is out of range.')
        return item['model_id'],item['rows'][row_number-1]


def parse_csv(data: bytes, headerless_columns=None):
    if len(data) > MAX_BYTES:
        raise ValueError('CSV exceeds 60 MB. Split very large files into smaller batches.')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('CSV must use UTF-8 encoding.') from exc
    try:
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=',\t;|')
    except csv.Error:
        # Normal CSV is the safest fallback for very small or single-row files.
        dialect = csv.excel
    parsed_rows=[row for row in csv.reader(StringIO(text,newline=''),dialect=dialect)
                 if any(str(value).strip() for value in row)]
    if not parsed_rows: raise ValueError('CSV contains no applicants.')
    width=len(parsed_rows[0])
    if any(len(row)!=width for row in parsed_rows):
        raise ValueError('CSV rows have different numbers of values. Check the delimiter and quoting.')
    def numeric_or_blank(value):
        if not str(value).strip(): return True
        try: return math.isfinite(float(value))
        except (ValueError,TypeError): return False
    headerless=bool(headerless_columns) and all(numeric_or_blank(value) for value in parsed_rows[0])
    if headerless:
        if width!=len(headerless_columns):
            raise ValueError(f'Headerless files must contain exactly {len(headerless_columns)} values per row '
                             f'in CreditScope feature order; detected {width}. Add column headers for another layout.')
        fieldnames=list(headerless_columns)
        data_rows=parsed_rows
        input_mode='creditscope_107_feature_order'
    else:
        original=parsed_rows[0]
        fieldnames=[str(name).strip() for name in original]
        if not fieldnames or any(not name for name in fieldnames) or len(set(fieldnames))!=len(fieldnames):
            raise ValueError('CSV needs unique column headers.')
        data_rows=parsed_rows[1:]
        input_mode='named_columns'
    rows=[dict(zip(fieldnames,row)) for row in data_rows]
    if not rows: raise ValueError('CSV contains no applicants.')
    if len(rows) > MAX_ROWS: raise ValueError(f'CSV contains {len(rows):,} applicants; maximum is {MAX_ROWS:,} per batch.')
    return rows,input_mode


def recognized_columns(row, features):
    """Return uploaded columns that can influence an applicant or model row."""
    profile = {
        'id','SK_ID_CURR','age','AGE_YEARS','DAYS_BIRTH','income','AMT_INCOME_TOTAL',
        'credit','AMT_CREDIT','annuity','AMT_ANNUITY','employment_years','DAYS_EMPLOYED',
        'education','NAME_EDUCATION_TYPE','income_type','NAME_INCOME_TYPE',
        'contract_type','NAME_CONTRACT_TYPE','own_car','FLAG_OWN_CAR',
        'external_score_2','EXT_SOURCE_2','external_score_3','EXT_SOURCE_3',
        'late_payment_rate','LATE_PAYMENT_RATE',
    }
    return sorted(set(row) & (set(features) | profile))


def applicant_from_row(row: dict):
    """Build the human-readable case from form, raw, or encoded feature CSVs."""
    def numeric(*names):
        for name in names:
            value = row.get(name)
            if value is not None and str(value).strip():
                try: result = float(value)
                except (ValueError, TypeError) as exc: raise ValueError(f'{name} must be numeric.') from exc
                if not math.isfinite(result): raise ValueError(f'{name} must be finite.')
                return result
        return None
    data = {}
    fields = {'income':('income','AMT_INCOME_TOTAL'), 'credit':('credit','AMT_CREDIT'),
              'annuity':('annuity','AMT_ANNUITY'), 'external_score_2':('external_score_2','EXT_SOURCE_2'),
              'external_score_3':('external_score_3','EXT_SOURCE_3'),
              'late_payment_rate':('late_payment_rate','LATE_PAYMENT_RATE')}
    for key,names in fields.items():
        value=numeric(*names)
        if value is not None: data[key]=value
    age=numeric('age','AGE_YEARS')
    if age is None:
        birth=numeric('DAYS_BIRTH')
        if birth is not None: age=-birth/365
    if age is not None: data['age']=age
    employment=numeric('employment_years')
    if employment is None:
        days=numeric('DAYS_EMPLOYED')
        if days is not None and days < 0: employment=-days/365
    if employment is not None: data['employment_years']=employment
    allowed = {
        'education': ('Lower secondary','Secondary / secondary special','Incomplete higher','Higher education','Academic degree'),
        'income_type': ('Working','Commercial associate','Pensioner','State servant','Other'),
        'contract_type': ('Cash loans','Revolving loans'),
    }
    for key,names in {'education':('education','NAME_EDUCATION_TYPE'),
                      'income_type':('income_type','NAME_INCOME_TYPE'),
                      'contract_type':('contract_type','NAME_CONTRACT_TYPE')}.items():
        for name in names:
            value=row.get(name)
            if value and str(value).strip():
                value=str(value).strip()
                if value in allowed[key]: data[key]=value
                elif key=='education' and value in {'1','2','3','4','5'}:
                    data[key]=allowed[key][int(value)-1]
                elif key=='contract_type' and value in {'0','1'}:
                    data[key]=allowed[key][int(value)]
                break
    car=row.get('own_car',row.get('FLAG_OWN_CAR'))
    if car is not None and str(car).strip(): data['own_car']=str(car).strip().lower() in {'y','yes','true','1'}
    if data.get('income_type') not in {'Working','Commercial associate','Pensioner','State servant','Other',None}:
        data['income_type']='Other'
    return Applicant.model_validate(data)


def model_values(row, features, categorical=()):
    """Pass through only columns that match the selected model's feature names."""
    out={}
    for name in features:
        if name not in row or row[name] in (None,''): continue
        if name in categorical:
            out[name]=row[name]
        else:
            value=row[name]
            try: out[name]=float(value);continue
            except (ValueError,TypeError): pass
            if name=='CODE_GENDER': out[name]={'F':0,'M':1,'XNA':0}.get(value,0)
            elif name in {'FLAG_OWN_CAR','FLAG_OWN_REALTY'}: out[name]=1 if value=='Y' else 0
            elif name=='NAME_CONTRACT_TYPE': out[name]=1 if value=='Revolving loans' else 0
            elif name=='NAME_EDUCATION_TYPE':
                order=['Lower secondary','Secondary / secondary special','Incomplete higher','Higher education','Academic degree']
                if value in order: out[name]=order.index(value)+1
            elif name in {'OCCUPATION_TYPE','ORGANIZATION_TYPE'}:
                out[name]=category_frequency(name).get(value,0)
    return out
