"""Optional model inference over retrieved evidence; never promotes it as reproduced CAD."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel,Field,ConfigDict
from .provider import ProviderClient,ProviderConfig,ProviderError
from .scout import SolutionCard

class SourceHypothesis(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_urls:list[str]=Field(min_length=1,max_length=6)
    mechanism:str=Field(max_length=3000)
    adaptation:str=Field(max_length=3000)
    applicability:str=Field(max_length=1500)
    limitations:list[str]=Field(min_length=1,max_length=10)
    alternatives:list[str]=Field(default_factory=list,max_length=6)

def reason_over_sources(scout,result:dict,provider:ProviderClient,model_calls:int=1,*,allow_private_context=False,request:dict|None=None):
    """A sourced hypothesis is a separate card from the fixed tested reproduction."""
    evidence=result.get('cards') or []
    budget=min(max(0,model_calls),scout.settings.model_budget,10)
    if not provider.config.configured or budget==0 or not evidence:
        return result
    config=provider.config.model_copy(update={'max_attempts':min(provider.config.max_attempts,budget)})
    client=ProviderClient(config,transport=provider.transport)
    sources={url for card in evidence for url in card.get('source_urls',[])}
    context={'operation':evidence[0].get('operation'),'versions':scout.versions,'source_evidence':[{'urls':c['source_urls'],'excerpt':c.get('source_excerpt',''),'tested_applicability':c.get('applicability'),'outcome':c.get('outcome')} for c in evidence]}
    if allow_private_context and request:
        context['explicitly_authorized_private_context']={k:request.get(k) for k in ['error','feature_graph','geometry','invariants']}
    instruction='Analyze only the supplied retrieved evidence. Propose a narrow CAD mechanism grounded in the listed source URLs, with adaptation instructions, applicability boundaries and counterevidence. Do not treat fixed box reproduction as proof for a different design. Never propose executable code, acceptance decisions, requirement removal or tolerance relaxation. Your output is an untested sourced hypothesis; identify unsupported aspects in limitations.'
    try:
        hypothesis=client.structured(instruction,context,SourceHypothesis,cancel=scout._cancel)
        if not set(hypothesis.source_urls).issubset(sources):
            raise ProviderError('Scout model cited a source that was not retrieved')
        first=evidence[0]
        card=SolutionCard(problem=f"Model hypothesis for {first.get('operation')}",operation=first['operation'],status='sourced',source_urls=hypothesis.source_urls,source_files=first.get('source_files',[]),source_excerpt=first.get('source_excerpt',''),mechanism=hypothesis.mechanism,adaptation=hypothesis.adaptation,applicability=hypothesis.applicability,limitations=['Model inference over retrieved evidence; this proposed mechanism has not been reproduced on the active design.',*hypothesis.limitations],alternatives=hypothesis.alternatives,compatible_versions=scout.versions,fetched_at=first['fetched_at'],source_hashes={url:digest for c in evidence for url,digest in c.get('source_hashes',{}).items() if url in hypothesis.source_urls},license_notes=first.get('license_notes',[]),freshness='Sourced model hypothesis; no local geometry reproduction of this adaptation',retrieval_mode='Retrieved source evidence with configured model inference',outcome={'geometry_reproduced':False,'provider_usage':client.last_call,'private_context_sent':allow_private_context})
        scout.store.put_card(card)
        return {**result,'cards':[*evidence,card.model_dump(mode='json')],'model_calls':client.last_call.get('attempts',1),'retrieval_mode':'Deterministic retrieval plus separately labeled model inference'}
    except ProviderError as error:
        return {**result,'model_calls':client.last_call.get('attempts',budget),'model_error':str(error),'unresolved':[*result.get('unresolved',[]),'Model inference did not produce a source-grounded hypothesis; retrieved cards remain available.']}
