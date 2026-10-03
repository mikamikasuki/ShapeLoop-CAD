import json
import httpx
from shapeloop.provider import ProviderClient
from shapeloop.scout import SolutionScout,SolutionCard
from shapeloop.scout_reasoning import reason_over_sources

def test_model_hypothesis_is_sourced_and_private_context_is_opt_in(tmp_path):
    scout=SolutionScout(tmp_path/'scout.sqlite',{'model_budget':1})
    url='https://raw.githubusercontent.com/CadQuery/cadquery/master/tests/test_cadquery.py'
    row=scout.store.cache_source(url,'def test_fillet(): pass')
    evidence=SolutionCard(problem='fillet',operation='fillet',status='reproduced',source_urls=[url],mechanism='fixed box',adaptation='only box',fetched_at=row['fetched_at'],applicability='20mm box',source_hashes={url:row['content_hash']}).model_dump(mode='json')
    def responder(request):
        body=json.loads(request.content)
        assert 'private-dimension-888' not in json.dumps(body)
        value={'source_urls':[url],'mechanism':'Use specified vertical edges','adaptation':'Test new local radius explicitly','applicability':'Simple orthogonal boxes','limitations':['Active enclosure untested'],'alternatives':['Chamfer']}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(value)},'finish_reason':'stop'}]})
    provider=ProviderClient({'endpoint':'http://localhost/v1','model':'test'},transport=httpx.MockTransport(responder))
    result=reason_over_sources(scout,{'cards':[evidence]},provider,request={'geometry':'private-dimension-888'})
    assert result['model_calls']==1
    assert result['cards'][-1]['status']=='sourced'
    assert result['cards'][-1]['outcome']['geometry_reproduced'] is False
    assert evidence['status']=='reproduced'

def test_unretrieved_model_citation_rejected_and_budget_zero_no_call(tmp_path):
    scout=SolutionScout(tmp_path/'scout.sqlite',{'model_budget':1})
    url='https://raw.githubusercontent.com/CadQuery/cadquery/master/tests/test_cadquery.py'
    card=SolutionCard(problem='fillet',operation='fillet',source_urls=[url],mechanism='x',adaptation='x',fetched_at='2026-10-02T00:00:00+00:00',applicability='box').model_dump(mode='json')
    def responder(request):
        value={'source_urls':['https://unretrieved.example/source'],'mechanism':'x','adaptation':'x','applicability':'x','limitations':['untested']}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(value)}}]})
    provider=ProviderClient({'endpoint':'http://localhost/v1','model':'test'},transport=httpx.MockTransport(responder))
    result=reason_over_sources(scout,{'cards':[card]},provider,0)
    assert result=={'cards':[card]}
    result=reason_over_sources(scout,{'cards':[card]},provider,1)
    assert 'not retrieved' in result['model_error']
    assert len(result['cards'])==1
