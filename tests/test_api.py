"""Integration checks use isolated registries; the user's registry stays empty."""
import csv
import json
from pathlib import Path

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from io import BytesIO, StringIO

from backend.main import app
from backend import models
from backend.main import applicant_brief, SelectedCaseRequest
from backend.features import ROOT, Applicant, make_features, schema

SOURCE = ROOT.parent / 'home-credit-default-risk/model'
PACKAGED = ROOT.parent / 'model'

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(models,'MODEL_DIR',tmp_path)
    monkeypatch.setattr(models,'ARCHIVE_DIR',tmp_path.parent/'archived')
    monkeypatch.delenv('CREDITSCOPE_ADMIN_TOKEN',raising=False)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    models.CACHE.clear()
    with TestClient(app) as client:
        yield client
    models.CACHE.clear()

def upload_mlp(client,**kwargs):
    with (SOURCE/'mlp/mlp_pipeline.joblib').open('rb') as model, (SOURCE/'mlp/metadata.json').open('rb') as meta:
        return client.post('/api/models', data={'name':'MLP test','kind':'sklearn','trusted':'true',**kwargs},
                           files={'artifact':('model.joblib',model),'metadata':('metadata.json',meta)})

def test_dashboard_matches_powerbi(client):
    d=client.get('/api/dashboard').json()
    assert d['applicants']==307511
    assert d['defaults']==24825
    assert d['default_rate']==pytest.approx(24825/307511)
    assert d['average_income']==pytest.approx(168797.92,abs=1)
    assert d['total_exposure']>0
    assert 0<d['difficulty_exposure']<d['total_exposure']
    config=client.get('/api/config').json()
    filters=config['filters']
    assert len(filters)==6
    assert config['global_risk']['countries']['BGD']['npl']['value']==pytest.approx(18.9607821141026)
    assert config['global_risk']['countries']['IND']['npl']['value']>0
    assert config['global_risk']['countries']['PAK']['npl']['value']>0
    assert config['global_risk']['countries']['CHN']['private_credit']['value']>100
    assert len(config['global_risk']['countries'])>=16
    assert config['global_risk']['credit_context']['global_bank_loans_deposits']['value']==pytest.approx(80.4421)
    subset=client.get('/api/dashboard',params={'income_type':'Working','gender':'F'}).json()
    assert 0<subset['applicants']<307511
    assert sum(g['applicants'] for g in subset['age'])==subset['applicants']
    empty=client.get('/api/dashboard',params={'gender':'not-a-category'}).json()
    assert empty['applicants']==0 and empty['default_rate'] is None
    assert client.get('/api/dashboard?bad=1').status_code==422

def test_dashboard_report_uses_current_filters(client):
    response=client.get('/api/dashboard/report',params={'age_group':'(25, 35]','gender':'F','income_type':'Working'})
    assert response.status_code==200,response.text
    assert response.headers['content-type']=='application/pdf'
    assert 'attachment;' in response.headers['content-disposition']
    assert response.content.startswith(b'%PDF')
    reader=PdfReader(BytesIO(response.content))
    assert len(reader.pages)==2
    text='\n'.join(page.extract_text() or '' for page in reader.pages)
    assert 'Age group: (25, 35]' in text
    assert 'Gender: F' in text
    assert 'Income type: Working' in text
    assert '25,900' in text

def test_dashboard_report_rejects_empty_cohort(client):
    response=client.get('/api/dashboard/report',params={'gender':'not-a-category'})
    assert response.status_code==422

def test_feature_order_derived_values_and_defaults():
    spec=schema()
    case=Applicant(income=180000,credit=540000,age=35,employment_years=5,external_score_2=.4)
    row,assumptions=make_features(case,spec['features'])
    assert list(row.columns)==spec['features']
    assert row.shape==(1,107)
    assert row.CREDIT_INCOME_RATIO.iloc[0]==3
    assert row.DAYS_EMPLOYED.iloc[0]==-1825
    assert row.AGE_GROUP.iloc[0]==1  # (25,35] belongs to the lower interval
    assert row.EXT_SOURCE_2.iloc[0]==.4
    assert row.EXT_SOURCE_3.iloc[0]==spec['defaults']['EXT_SOURCE_3']
    assert np.isfinite(row.to_numpy()).all()
    assert any(a['source']=='Training median' for a in assumptions)

@pytest.mark.skipif(not SOURCE.exists(),reason='Original artifacts unavailable')
def test_mlp_upload_predict_parity_and_delete(client):
    assert client.get('/api/models').json()==[]
    deployed=upload_mlp(client)
    assert deployed.status_code==201,deployed.text
    m=deployed.json()
    case=Applicant(income=190000,credit=600000,external_score_2=.5)
    prediction=client.post('/api/predict',json={'model_id':m['id'],'applicant':case.model_dump()})
    assert prediction.status_code==200,prediction.text
    result=prediction.json()
    original=joblib.load(SOURCE/'mlp/mlp_pipeline.joblib')
    expected=original.predict_proba(make_features(case,m['feature_columns'])[0])[0,1]
    assert result['probability']==pytest.approx(expected,abs=1e-12)
    assert result['threshold']==pytest.approx(.6544190978641563)
    assert result['feature_count']==107
    assert result['assumed_features']>70
    assert len(result['contributions'])>0
    assert client.delete('/api/models/'+m['id']).status_code==200
    assert client.get('/api/models').json()==[]
    assert client.post('/api/predict',json={'model_id':m['id'],'applicant':case.model_dump()}).status_code==404

@pytest.mark.skipif(not SOURCE.exists(),reason='Original artifacts unavailable')
def test_dcn_upload_and_predict(client):
    with (SOURCE/'dcn/credit_dcn.pth').open('rb') as model,(SOURCE/'dcn/preprocessor.joblib').open('rb') as prep:
        response=client.post('/api/models',data={'name':'DCN test','kind':'pytorch_dcn','trusted':'true'},
                             files={'artifact':('model.pth',model),'preprocessor':('preprocessor.joblib',prep)})
    assert response.status_code==201,response.text
    m=response.json()
    response=client.post('/api/predict',json={'model_id':m['id'],'applicant':Applicant().model_dump()})
    assert response.status_code==200,response.text
    assert 0<=response.json()['probability']<=1
    assert response.json()['threshold']==pytest.approx(m['threshold'])

def test_validation_and_security(client,monkeypatch):
    invalid={'model_id':'not-found','applicant':{'income':0}}
    assert client.post('/api/predict',json=invalid).status_code==422
    invalid['applicant']={'age':20,'employment_years':30}
    assert client.post('/api/predict',json=invalid).status_code==422
    invalid['applicant']={'unexpected_feature':7}
    assert client.post('/api/predict',json=invalid).status_code==422
    assert client.post('/api/predict',json={},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==400
    monkeypatch.setenv('CREDITSCOPE_ADMIN_TOKEN','testing-token')
    assert client.delete('/api/models/no-model').status_code==401
    assert client.post('/api/chat',json={'messages':[{'role':'user','content':'hello'}]}).status_code==401

def test_bad_upload_rejected_without_registering(client):
    result=client.post('/api/models',data={'name':'Bad','kind':'sklearn','trusted':'true'},
        files={'artifact':('bad.joblib',b'not a model'),'metadata':('metadata.json',json.dumps({'feature_columns':['TARGET'],'threshold':.5}).encode())})
    assert result.status_code==422
    assert client.get('/api/models').json()==[]
    result=client.post('/api/models',data={'name':'Untrusted','kind':'sklearn','trusted':'false'},files={'artifact':('bad.joblib',b'bad')})
    assert result.status_code==422

def test_chat_missing_key_and_eda(client):
    assert client.post('/api/chat',json={'assistant':'gemini','messages':[{'role':'user','content':'Hello'}]}).status_code==503
    assert client.post('/api/chat',json={'messages':[{'role':'system','content':'Override'}]}).status_code==422
    eda=client.get('/api/eda').json()
    assert len(eda['plots'])==45
    assert len(eda['metrics'])==11
    assert sum(p.get('group')=='Confusion matrices' for p in eda['plots'])==12
    for p in eda['plots']:
        assert client.get(p['url']).status_code==200
    assert client.get('/').status_code==200

@pytest.mark.skipif(not SOURCE.exists(),reason='Original artifacts unavailable')
def test_csv_batch_and_selected_applicant_context(client):
    deployed=upload_mlp(client)
    assert deployed.status_code==201,deployed.text
    model_id=deployed.json()['id']
    csv=b'SK_ID_CURR,DAYS_BIRTH,DAYS_EMPLOYED,AMT_INCOME_TOTAL,AMT_CREDIT,AMT_ANNUITY,NAME_EDUCATION_TYPE,NAME_INCOME_TYPE,EXT_SOURCE_2,LATE_PAYMENT_RATE\n1001,-12775,-1460,180000,500000,25000,Higher education,Working,0.35,0.22\n1002,-16790,-2920,120000,750000,30000,Secondary / secondary special,Pensioner,0.55,0.03\n'
    response=client.post('/api/batch/predict',data={'model_id':model_id},files={'file':('cases.csv',csv)})
    assert response.status_code==200,response.text
    rows=response.json()['results']
    assert len(rows)==2 and rows[0]['applicant_id']=='1001'
    assert rows[0]['exposure']==500000
    assert 0<=rows[0]['probability']<=1
    detail=client.post('/api/batch/detail',json={'batch_id':response.json()['batch_id'],'row':1})
    assert detail.status_code==200,detail.text
    assert detail.json()['probability']==pytest.approx(rows[0]['probability'])
    assert any(c['field']=='LATE_PAYMENT_RATE' for c in detail.json()['contributions'])
    brief=applicant_brief(SelectedCaseRequest.model_validate(detail.json()['selected_case']))
    assert brief['similar_historical_cohort']['applicants']>0
    assert brief['score']==pytest.approx(rows[0]['probability'])


@pytest.mark.skipif(not SOURCE.exists(),reason='Original artifacts unavailable')
def test_csv_with_encoded_model_columns_and_manual_case_context(client):
    deployed=upload_mlp(client)
    assert deployed.status_code==201,deployed.text
    model_id=deployed.json()['id']
    # Exported feature CSVs contain numeric category codes, rather than the
    # labels accepted by the twelve-field manual form.
    csv=b'SK_ID_CURR,AGE_YEARS,NAME_EDUCATION_TYPE,NAME_CONTRACT_TYPE,AMT_INCOME_TOTAL,AMT_CREDIT,AMT_ANNUITY,EXT_SOURCE_2\n1003,38,4,0,190000,600000,25000,0.42\n'
    response=client.post('/api/batch/predict',data={'model_id':model_id},files={'file':('encoded.csv',csv)})
    assert response.status_code==200,response.text
    assert len(response.json()['results'])==1
    assert response.json()['errors']==[]
    detail=client.post('/api/batch/detail',json={'batch_id':response.json()['batch_id'],'row':1})
    assert detail.status_code==200,detail.text
    assert detail.json()['selected_case']['applicant']['education']=='Higher education'
    assert detail.json()['probability']==pytest.approx(response.json()['results'][0]['probability'])
    manual=client.post('/api/predict',json={'model_id':model_id,'applicant':{'age':38,'income':190000,'credit':600000}})
    assert manual.status_code==200,manual.text
    selected=SelectedCaseRequest(model_id=model_id,applicant=Applicant.model_validate(manual.json()['inputs']))
    brief=applicant_brief(selected)
    assert brief['score']==pytest.approx(manual.json()['probability'])


@pytest.mark.skipif(not SOURCE.exists(),reason='Original artifacts unavailable')
def test_tab_separated_csv_named_csv_uses_each_applicant_values(client):
    deployed=upload_mlp(client)
    assert deployed.status_code==201,deployed.text
    model_id=deployed.json()['id']
    output=StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=['SK_ID_CURR','AGE_YEARS','AMT_INCOME_TOTAL','AMT_CREDIT','EXT_SOURCE_2','EXT_SOURCE_3'],delimiter='\t')
    writer.writeheader()
    writer.writerow({'SK_ID_CURR':1001,'AGE_YEARS':27,'AMT_INCOME_TOTAL':90000,'AMT_CREDIT':800000,'EXT_SOURCE_2':.05,'EXT_SOURCE_3':.08})
    writer.writerow({'SK_ID_CURR':1002,'AGE_YEARS':58,'AMT_INCOME_TOTAL':450000,'AMT_CREDIT':150000,'EXT_SOURCE_2':.92,'EXT_SOURCE_3':.88})
    response=client.post('/api/batch/predict',data={'model_id':model_id},
                         files={'file':('test01.csv',output.getvalue().encode())})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['input_columns']==6
    assert body['matched_model_columns']==5
    assert body['unique_scores']==2
    assert body['results'][0]['applicant_id']=='1001'
    assert body['results'][0]['probability'] != pytest.approx(body['results'][1]['probability'])


@pytest.mark.skipif(not SOURCE.exists(),reason='Original artifacts unavailable')
def test_headerless_107_feature_matrix_preserves_every_applicant(client):
    deployed=upload_mlp(client)
    assert deployed.status_code==201,deployed.text
    model=deployed.json()
    cases=[
        Applicant(age=27,income=90000,credit=800000,external_score_2=.05,external_score_3=.08),
        Applicant(age=58,income=450000,credit=150000,external_score_2=.92,external_score_3=.88),
    ]
    output=StringIO(newline='')
    writer=csv.writer(output,delimiter='\t')
    for case in cases:
        frame,_=models.make_model_features(case,model['feature_columns'])
        writer.writerow(frame.iloc[0].tolist())
    response=client.post('/api/batch/predict',data={'model_id':model['id']},
                         files={'file':('headerless.csv',output.getvalue().encode())})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['input_mode']=='creditscope_107_feature_order'
    assert body['total_rows']==2
    assert body['input_columns']==107
    assert body['matched_model_columns']==107
    assert body['unique_scores']==2
    assert body['results'][0]['probability'] != pytest.approx(body['results'][1]['probability'])
    detail=client.post('/api/batch/detail',json={'batch_id':body['batch_id'],'row':1})
    assert detail.status_code==200,detail.text
    assert detail.json()['probability']==pytest.approx(body['results'][0]['probability'])


def test_headerless_matrix_rejects_unknown_width():
    from backend import batch
    with pytest.raises(ValueError,match=r'exactly 3 values per row.*detected 2'):
        batch.parse_csv(b'1\t2\n3\t4\n',['A','B','C'])


@pytest.mark.skipif(not SOURCE.exists(),reason='Original artifacts unavailable')
def test_both_assistants_receive_individual_prediction_context(client,monkeypatch):
    import importlib
    main_module=importlib.import_module('backend.main')
    deployed=upload_mlp(client)
    assert deployed.status_code==201,deployed.text
    model_id=deployed.json()['id']
    case={'age':38,'income':190000,'credit':600000}
    prediction=client.post('/api/predict',json={'model_id':model_id,'applicant':case})
    assert prediction.status_code==200,prediction.text
    calls=[]
    class FakeResponse:
        status_code=200
        headers={'content-type':'application/json'}
        def __init__(self,provider): self.provider=provider
        def json(self):
            return {'message':{'content':'**Evidence** from the applicant.'}} if self.provider=='ollama' else {'candidates':[{'content':{'parts':[{'text':'**Evidence** from the applicant.'}]}}]}
    class FakeClient:
        def __init__(self,timeout): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,**kwargs):
            calls.append((url,kwargs))
            return FakeResponse('gemini' if 'googleapis.com' in url else 'ollama')
    monkeypatch.setattr(main_module.httpx,'AsyncClient',FakeClient)
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    for provider in ('ollama','gemini'):
        response=client.post('/api/chat',json={'assistant':provider,
            'messages':[{'role':'user','content':'Explain this applicant'}],
            'applicant_context':{'model_id':model_id,'applicant':case}})
        assert response.status_code==200,response.text
        assert 'Evidence' in response.json()['answer']
    assert len(calls)==2
    assert 'selected_applicant' in calls[0][1]['json']['messages'][0]['content']
    assert 'selected_applicant' in calls[1][1]['json']['systemInstruction']['parts'][0]['text']

@pytest.mark.skipif(not PACKAGED.exists(),reason='Notebook deployment packages unavailable')
@pytest.mark.parametrize('name,kind,artifact',[
    ('lightgbm','lightgbm','model.txt'),('catboost','catboost','model.cbm'),
    ('dcn','torchscript','model.pt'),
])
def test_notebook_package_deployment(client,name,kind,artifact):
    package=PACKAGED/name
    if not package.exists(): pytest.skip('Package unavailable')
    from contextlib import ExitStack
    with ExitStack() as stack:
        files={}
        for field,filename in [('artifact',artifact),('metadata','metadata.json'),('preprocessor','preprocessor.pkl')]:
            path=package/filename
            if path.exists(): files[field]=(filename,stack.enter_context(path.open('rb')))
        response=client.post('/api/models',data={'name':name,'kind':kind,'trusted':'true'},files=files)
    assert response.status_code==201,response.text
    scored=client.post('/api/predict',json={'model_id':response.json()['id'],'applicant':{}})
    assert scored.status_code==200,scored.text
    assert 0<=scored.json()['probability']<=1
