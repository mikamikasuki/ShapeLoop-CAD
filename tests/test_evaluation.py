"""Evaluation harness output comes from actual durable jobs and STEP reimports."""
import json
from shapeloop.evaluation import run_demo,benchmark


def test_acceptance_demo(tmp_path):
    result=run_demo(tmp_path/'demo')
    assert result['status']=='PASS'
    assert result['conflicts'] and any('≥' in c['inequality'] for c in result['conflicts'])
    assert {'plate','bracket'}==set(result['families'])
    assert (tmp_path/'demo'/'exports'/'assembly.step').is_file()
    assert (tmp_path/'demo'/'independent-rebuild'/'assembly.step').is_file()
    assert json.loads((tmp_path/'demo'/'demo-results.json').read_text())['status']=='PASS'


def test_comparison_policies_preserve_failed_candidate_separately(tmp_path):
    result=benchmark(tmp_path/'benchmark',sequences=1)
    assert len(result['records'])==9
    totals=result['totals']
    assert totals['shapeloop']['accepted_invalid_candidates']==0
    assert totals['full_regeneration']['accepted_invalid_candidates']>=1
    assert totals['sequential_without_acceptance']['accepted_invalid_candidates']>=1
    assert totals['shapeloop']['requested_edits_achieved']<totals['full_regeneration']['requested_edits_achieved']
    assert result['model_tokens']==0
