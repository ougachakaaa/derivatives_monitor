#!/usr/bin/env python3
"""Independent frozen-contract oracle; no imports from production or production math.

Install analytics-oracle-requirements.txt in a separate environment.
Default verifies checked-in fixtures. --output writes a NEW file for review.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import QuantLib as ql
import mpmath as mp

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'analytics/contracts/analytics-skew-v1.json'
FIXTURES = Path(__file__).resolve().parent / 'fixtures/analytics-skew-v1.json'


def build():
    assert ql.__version__ == '1.40' and mp.__version__ == '1.3.0'
    mp.mp.dps = 80
    p = json.loads(POLICY.read_text())
    normal = lambda x: mp.erfc(-x / mp.sqrt(2)) / 2
    definitions = [
        ('atm-call', 'C', 6000, 6000, 30, .25, .02),
        ('atm-put', 'P', 6000, 6000, 30, .25, .02),
        ('otm-call', 'C', 6000, 6400, 30, .24, .02),
        ('otm-put', 'P', 6000, 5600, 30, .28, .02),
        ('itm-call', 'C', 6000, 5600, 30, .28, .02),
        ('itm-put', 'P', 6000, 6400, 30, .24, .02),
        ('long-call', 'C', 6000, 6600, 180, .45, .015),
        ('negative-rate-put', 'P', 6000, 5800, 90, .32, -.005),
        ('low-vol-call', 'C', 6000, 6000, 7, .08, 0),
        ('high-vol-put', 'P', 6000, 6200, 365, 1.2, .03),
        ('short-put', 'P', 6000, 6000, 2, .35, .02),
        ('different-scale-call', 'C', 100, 110, 90, .30, .02),
    ]
    vectors = []
    for name, side, forward, strike, days, sigma, rate in definitions:
        t = days / 365
        discount = 1 / (1 + rate * days / 360)
        typ = ql.Option.Call if side == 'C' else ql.Option.Put
        stddev = sigma * math.sqrt(t)
        price = ql.blackFormula(typ, strike, forward, stddev, discount)
        iv = ql.blackFormulaImpliedStdDev(typ, strike, forward, price, discount, 0, .2, 1e-12, 1000) / math.sqrt(t)
        calc = ql.BlackCalculator(ql.PlainVanillaPayoff(typ, strike), forward, stddev, discount)
        f, k, vol, tt, dd = map(mp.mpf, map(str, (forward, strike, sigma, t, discount)))
        d1 = mp.log(f/k)/(vol*mp.sqrt(tt)) + vol*mp.sqrt(tt)/2
        d2 = d1-vol*mp.sqrt(tt)
        high = dd*(f*normal(d1)-k*normal(d2)) if side == 'C' else dd*(k*normal(-d2)-f*normal(-d1))
        assert abs(float(high)-price) <= max(1e-10, abs(price)*1e-12)
        vectors.append(dict(name=name, side=side, forward=forward, strike=strike,
                            days_to_expiry=days, rate_decimal=rate, t_years=t, discount=discount,
                            input_sigma=sigma, expected_price=price,
                            high_precision_price=mp.nstr(high, 70), expected_iv=iv,
                            expected_delta=calc.deltaForward()/discount, expected_vega=calc.vega(t)))

    def chain(name, slope):
        target_f, days, rate = 6000, 30, .02
        t, discount = days / 365, 1/(1+rate*days/360)
        rows = []
        for i, strike in enumerate(range(4500, 7501, 100)):
            sigma = .25 + slope*math.log(strike/target_f)
            for side in ('C', 'P'):
                typ = ql.Option.Call if side == 'C' else ql.Option.Put
                price = ql.blackFormula(typ, strike, target_f, sigma*math.sqrt(t), discount)
                # Synthetic tick rounding only; never applied to real quotes by the contract.
                mid = round(round(price/.2)*.2, 1)
                rows.append(dict(instrument=f'MO2610-{side}-{strike}', id=1000+len(rows),
                                 side=side, strike=strike, bid=round(mid-.2,1), ask=round(mid+.2,1),
                                 bid_volume=10, ask_volume=10, age_us=5000000+(i%3)*1000000+(side=='P')*200000))
        eligible = []
        for row in rows:
            mid = (row['bid']+row['ask'])/2
            if row['bid'] > 0 and mid >= p['quotes']['min_mid_points'] and (row['ask']-row['bid'])/mid <= .2+1e-12:
                eligible.append(dict(row, mid=mid))
        grouped = {}
        for row in eligible:
            grouped.setdefault(row['strike'], {})[row['side']] = row
        pairs = [(abs(cp['C']['mid']-cp['P']['mid']), k, cp) for k,cp in grouped.items() if set(cp)=={'C','P'}]
        pairs.sort(key=lambda pair: (pair[0],pair[1],pair[2]['C']['instrument'],pair[2]['P']['instrument']))
        selected = pairs[:3]
        forward_values = [k+(cp['C']['mid']-cp['P']['mid'])/discount for _,k,cp in selected]
        f = sorted(forward_values)[1]
        assert max(abs(v-f)/f for v in forward_values) <= .001
        wings = {}
        for side in ('P','C'):
            nodes = []
            for row in eligible:
                if row['side'] != side or (side=='P' and row['strike']>=f) or (side=='C' and row['strike']<=f):
                    continue
                typ = ql.Option.Call if side=='C' else ql.Option.Put
                stddev = ql.blackFormulaImpliedStdDev(typ,row['strike'],f,row['mid'],discount,0,.2,1e-12,1000)
                sigma=stddev/math.sqrt(t)
                calc=ql.BlackCalculator(ql.PlainVanillaPayoff(typ,row['strike']),f,stddev,discount)
                delta=calc.deltaForward()/discount
                if .10-1e-10<=abs(delta)<=.40+1e-10 and calc.vega(t)>=1 and .0001<=sigma<=5:
                    nodes.append(dict(instrument=row['instrument'],id=row['id'],strike=row['strike'],
                                      sigma=sigma,delta=delta,x=abs(delta)))
            ordered = sorted(nodes,key=lambda n:n['strike'])
            for a,b in zip(ordered,ordered[1:]):
                assert b['x']-a['x'] >= -1e-10 if side=='P' else b['x']-a['x'] <= 1e-10
            lo=max((n for n in nodes if n['x']<.25),key=lambda n:n['x'])
            hi=min((n for n in nodes if n['x']>.25),key=lambda n:n['x'])
            assert hi['x']-lo['x']<=.10+1e-10
            alpha=(.25-lo['x'])/(hi['x']-lo['x'])
            wings[side]=dict(lo=lo,hi=hi,alpha=alpha,iv=(1-alpha)*lo['sigma']+alpha*hi['sigma'])
        return dict(name=name, source='SYNTHETIC_TICK_ROUNDED', days_to_expiry=days, rate_decimal=rate,
                    discount=discount,t_years=t,rows=rows,
                    expected_forward=f,expected_forward_pairs=[dict(strike=k,call_id=cp['C']['id'],put_id=cp['P']['id'],forward=fi)
                        for (_,k,cp),fi in zip(selected,forward_values)],expected_wings=wings,
                    expected_skew_vp=100*(wings['P']['iv']-wings['C']['iv']))
    return dict(schema_version=1, contract_id=p['contract_id'],source='SYNTHETIC_NOT_LIVE',
                policy_sha256=hashlib.sha256(POLICY.read_bytes()).hexdigest(),
                generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                oracle={'QuantLib':'1.40','mpmath':'1.3.0','decimal_precision':80},
                vectors=vectors,chains=[chain('put-wing-higher',-.12),chain('call-wing-higher',.12)],
                interpolation_examples=[{'put_nodes':[[.20,.30],[.30,.28]],'call_nodes':[[.20,.25],[.30,.23]],'put_iv':.29,'call_iv':.24,'skew_vp':5},
                                        {'put_nodes':[[.20,.25],[.30,.25]],'call_nodes':[[.20,.25],[.30,.25]],'put_iv':.25,'call_iv':.25,'skew_vp':0}])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Write new oracle artifact; refuses to overwrite an existing file')
    args=parser.parse_args()
    generated=build()
    if args.output:
        with args.output.open('x') as stream:
            json.dump(generated,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n')
        print('WROTE independent SYNTHETIC oracle:',args.output)
    else:
        expected=json.loads(FIXTURES.read_text())
        assert generated==expected,'Oracle output differs from frozen fixtures; inspect before versioning changes'
        print('PASS: QuantLib 1.40 + 80-digit mpmath regenerate 12 pricing vectors, 2 tick-rounded chains and interpolation examples')
        print('Contract mathematics only; production Analytics and live acceptance remain unimplemented/unverified.')


if __name__=='__main__':
    main()
