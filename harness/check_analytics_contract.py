#!/usr/bin/env python3
"""Offline conformance examples for the frozen design, NOT production Analytics tests."""
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'query/contracts/analytics-skew-v1.json'
FIXTURES=ROOT/'harness/fixtures/analytics-skew-v1.json'
BASELINE_WITHOUT_GENERATOR_SHA256='4ae593379952b70006fb977c906dec29909a48423f7e492f98283513d6c46b56'


def near(actual, expected, tolerance, label):
    if not math.isfinite(actual) or abs(actual-expected)>tolerance:
        raise AssertionError(f'{label}: {actual} != {expected} (tolerance {tolerance})')


def price(side,f,k,t,d,sigma):
    w=sigma*math.sqrt(t)
    d1=math.log(f/k)/w+w/2
    d2=d1-w
    n=lambda x: .5*math.erfc(-x/math.sqrt(2))
    return d*(f*n(d1)-k*n(d2)) if side=='C' else d*(k*n(-d2)-f*n(-d1))


def solve(side,f,k,t,d,mid,policy):
    s=policy['solver']
    lower=d*max(f-k if side=='C' else k-f,0)
    upper=d*(f if side=='C' else k)
    if not lower<mid<upper:
        raise ValueError('PRICE_OUT_OF_BOUNDS')
    if mid-lower<=s['min_time_value_points_exclusive']:
        raise ValueError('TIME_VALUE_TOO_SMALL')
    lo,hi=s['sigma_min'],s['sigma_max']
    if not price(side,f,k,t,d,lo)<=mid<=price(side,f,k,t,d,hi):
        raise ValueError('IV_OUT_OF_RANGE')
    tol=max(s['price_absolute_tolerance'],s['price_scale_tolerance']*max(f,k))
    for _ in range(s['max_iterations']):
        sigma=(lo+hi)/2
        value=price(side,f,k,t,d,sigma)
        if hi-lo<=s['sigma_bracket_tolerance'] and abs(value-mid)<=tol:
            d1=math.log(f/k)/(sigma*math.sqrt(t))+sigma*math.sqrt(t)/2
            vega=d*f*math.exp(-d1*d1/2)/math.sqrt(2*math.pi)*math.sqrt(t)
            if vega<s['min_vega_per_unit_sigma']:
                raise ValueError('LOW_VEGA')
            return sigma
        if value<mid:
            lo=sigma
        else:
            hi=sigma
    raise ValueError('IV_NOT_CONVERGED')


def eligible(row,p):
    q=p['quotes']
    b,a=row['bid'],row['ask']
    tick=p['reference']['tick_size']
    if not (math.isfinite(b) and math.isfinite(a) and 0<b<=a):
        return False
    if not (0<=row['age_us']<=q['max_age_us']):
        return False
    if any(type(row[name]) is not int or row[name]<q['min_bid_ask_volume'] for name in ('bid_volume','ask_volume')):
        return False
    if any(abs(v-round(v/tick)*tick)>q['tick_tolerance_points'] for v in (b,a)):
        return False
    mid=(b+a)/2
    return mid>=q['min_mid_points'] and (a-b)/mid<=q['max_relative_spread']+q['spread_comparison_tolerance']


def check(policy, fixtures):
    p=policy
    assert p['contract_id']==fixtures['contract_id']=='mo-skew-25d-v1'
    assert p['status']=='FROZEN'
    assert p['skew']['formula']=='100*(put_iv_25-call_iv_25)'
    assert p['skew']['target_abs_delta']==.25
    assert p['skew']['delta_convention']=='UNDISCOUNTED_UNADJUSTED_FORWARD'
    assert p['pricing']['model']=='BLACK_76'
    assert p['forward']['source']=='SAME_EXPIRY_OPTION_PUT_CALL_PARITY'
    assert p['reference']['discount_convention']=='SHIBOR_3M_FLAT_SIMPLE_ACT360'
    assert set(p['decisions'])=={'skew_definition','pricing_model','underlying_semantics','reference_parameters','quote_synchronization','iv_solver_contract','independent_validation'}
    assert set(p['decisions'].values())=={'FROZEN'}
    assert fixtures['source']=='SYNTHETIC_NOT_LIVE'
    assert len(fixtures['vectors'])>=12 and len(fixtures['chains'])>=2
    assert p['validation']['oracle_version']==fixtures['oracle']['QuantLib']=='1.40'
    v=p['validation']
    for row in fixtures['vectors']:
        name=row['name']
        t=row['days_to_expiry']*86400/p['pricing']['year_seconds']
        d=1/(1+row['rate_decimal']*row['days_to_expiry']/360)
        near(t,row['t_years'],1e-15,name+' T')
        near(d,row['discount'],1e-15,name+' D')
        f,k=row['forward'],row['strike']
        value=price(row['side'],f,k,t,d,row['input_sigma'])
        near(value,float(row['high_precision_price']),max(1e-10,abs(value)*1e-12),name+' high precision')
        near(value,row['expected_price'],max(1e-10,abs(value)*1e-12),name+' QL price')
        sigma=solve(row['side'],f,k,t,d,row['expected_price'],p)
        near(sigma,row['expected_iv'],v['iv_abs_tolerance'],name+' IV')
        d1=math.log(f/k)/(sigma*math.sqrt(t))+sigma*math.sqrt(t)/2
        delta=.5*math.erfc(-d1/math.sqrt(2))-(row['side']=='P')
        near(delta,row['expected_delta'],v['delta_abs_tolerance'],name+' delta')
        opposite='P' if row['side']=='C' else 'C'
        parity=(value-price(opposite,f,k,t,d,row['input_sigma']))*(1 if row['side']=='C' else -1)
        near(parity,d*(f-k),max(1e-9,abs(d*(f-k))*1e-12),name+' parity')
    for chain in fixtures['chains']:
        rows=[dict(r,mid=(r['bid']+r['ask'])/2) for r in chain['rows'] if eligible(r,p)]
        grouped={}
        for r in rows:
            grouped.setdefault(r['strike'],{})[r['side']]=r
        pairs=[(abs(cp['C']['mid']-cp['P']['mid']),k,cp) for k,cp in grouped.items()
               if set(cp)=={'C','P'} and abs(cp['C']['age_us']-cp['P']['age_us'])<=p['quotes']['max_pair_span_us']]
        selected=sorted(pairs,key=lambda x:(x[0],x[1],x[2]['C']['instrument'],x[2]['P']['instrument']))[:p['forward']['pairs']]
        assert len(selected)==3
        ages=[r['age_us'] for _,_,cp in selected for r in cp.values()]
        assert max(ages)-min(ages)<=p['quotes']['max_input_span_us']
        d,t=chain['discount'],chain['t_years']
        fvalues=[k+(cp['C']['mid']-cp['P']['mid'])/d for _,k,cp in selected]
        f=sorted(fvalues)[1]
        near(f,chain['expected_forward'],v['forward_abs_tolerance_points'],chain['name']+' F')
        for (_,k,cp),expected,fi in zip(selected,chain['expected_forward_pairs'],fvalues):
            assert (k,cp['C']['id'],cp['P']['id'])==(expected['strike'],expected['call_id'],expected['put_id'])
            near(fi,expected['forward'],v['forward_abs_tolerance_points'],'pair F')
        assert max(abs(fi-f)/f for fi in fvalues)<=p['forward']['max_relative_deviation']
        wing_ivs={}
        forward_ages=list(ages)
        for side in ('P','C'):
            nodes=[]
            for r in rows:
                k=r['strike']
                if r['side']!=side or (side=='P' and k>=f) or (side=='C' and k<=f):
                    continue
                if max(forward_ages+[r['age_us']])-min(forward_ages+[r['age_us']])>p['quotes']['max_input_span_us']:
                    continue
                try:
                    sigma=solve(side,f,k,t,d,r['mid'],p)
                except ValueError:
                    continue
                d1=math.log(f/k)/(sigma*math.sqrt(t))+sigma*math.sqrt(t)/2
                x=abs(.5*math.erfc(-d1/math.sqrt(2))-(side=='P'))
                if .10-1e-10<=x<=.40+1e-10:
                    nodes.append(dict(r,x=x,sigma=sigma))
            ordered=sorted(nodes,key=lambda n:n['strike'])
            for a,b in zip(ordered,ordered[1:]):
                assert b['x']-a['x']>=-1e-10 if side=='P' else b['x']-a['x']<=1e-10
            lo=max((r for r in nodes if r['x']<.25),key=lambda r:r['x'])
            hi=min((r for r in nodes if r['x']>.25),key=lambda r:r['x'])
            assert hi['x']-lo['x']<=p['skew']['max_delta_gap']+1e-10
            expected=chain['expected_wings'][side]
            assert (lo['id'],hi['id'])==(expected['lo']['id'],expected['hi']['id'])
            alpha=(.25-lo['x'])/(hi['x']-lo['x'])
            iv=(1-alpha)*lo['sigma']+alpha*hi['sigma']
            near(iv,expected['iv'],v['wing_iv_abs_tolerance'],'wing IV')
            wing_ivs[side]=iv
            ages.extend([lo['age_us'],hi['age_us']])
        assert max(ages)-min(ages)<=p['quotes']['max_input_span_us']
        near(100*(wing_ivs['P']-wing_ivs['C']),chain['expected_skew_vp'],v['skew_abs_tolerance_vp'],'Skew')
    for example in fixtures['interpolation_examples']:
        ivs=[]
        for side in ('put','call'):
            (x0,s0),(x1,s1)=example[side+'_nodes']
            iv=s0+(.25-x0)/(x1-x0)*(s1-s0)
            near(iv,example[side+'_iv'],1e-12,'linear delta interpolation')
            ivs.append(iv)
        near(100*(ivs[0]-ivs[1]),example['skew_vp'],1e-10,'sign and units')


def main():
    p=json.loads(POLICY.read_text())
    fixture=json.loads(FIXTURES.read_text())
    baseline_payload={key:value for key,value in fixture.items() if key!='generator_sha256'}
    baseline_bytes=json.dumps(baseline_payload,sort_keys=True,separators=(',',':')).encode()
    assert hashlib.sha256(baseline_bytes).hexdigest()==BASELINE_WITHOUT_GENERATOR_SHA256, \
        'Frozen fixture changed outside generator provenance'
    assert hashlib.sha256(POLICY.read_bytes()).hexdigest()==fixture['policy_sha256'],'Frozen policy differs from oracle input'
    generator=ROOT/'harness/analytics_oracle.py'
    assert hashlib.sha256(generator.read_bytes()).hexdigest()==fixture['generator_sha256'],'Oracle generator changed'
    check(p,fixture)
    print('PASS: seven frozen decisions; independent goldens versus float64 formula/bisection, forward selection, wings, delta/sign/units')
    print('Scope: design conformance examples only; no production Analytics or live market acceptance claim.')


if __name__=='__main__':
    main()
