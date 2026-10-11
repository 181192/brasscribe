"""Melody-line benchmark: extracted line vs the reference melody part.

Cases: Slakh trumpet (SW "other" stem), URMP track 1, ChoraleBricks soprano.
Candidates are consensus notes of MuScriptor and Basic Pitch at a threshold.
"""
from pathlib import Path
import numpy as np, sys
from brasscribe_eval.score import load_notes, score
from brasscribe_eval.lead_sheet import line
from brasscribe_eval.consensus import load_sources, consensus
D=Path('../data/eval')
cases=[]
for t,part in [('Track00006','S02-Trumpet'),('Track00014','S00-Trumpet')]:
    S=D/'slakh-trumpet'/t; o='mix_(other)_BS-Roformer-SW'
    src={'mus':load_sources({'m':S/'pipeB-sw-muscriptor.mid'},True)[f'm/{o}'],'bp':load_sources({'b':S/'pipeB-sw-basicpitch.mid'},True)[f'b/{o}']}
    cases.append(('slakh',[n for n in load_notes(S/'reference.json') if n['part']==part],src))
for song in sorted((D/'urmp-brass').iterdir()):
    if (song/'reference.json').exists():
        cases.append(('urmp',[n for n in load_notes(song/'reference.json') if n['part'].startswith('1-')],{'mus':load_notes(song/'muscriptor-medium.mid'),'bp':load_notes(song/'basic-pitch.mid')}))
for song in sorted((D/'choralebricks-brass4').iterdir()):
    if (song/'reference.json').exists():
        cases.append(('chorale',[n for n in load_notes(song/'reference.json') if n['part']=='S'],{'mus':load_notes(song/'muscriptor-medium.mid'),'bp':load_notes(song/'basic-pitch.mid')}))
def run(thr):
    fs={}
    for name,ref,src in cases:
        cand,_=consensus(src,{'mus':0.6,'bp':0.4},thr)
        m = line(cand,52,88,top=True)
        fs.setdefault(name,[]).append(score(ref,m)['onset100_f1'])
    r={k:round(float(np.mean(v)),3) for k,v in fs.items()}; r['mean']=round(float(np.mean(list(r.values()))),3); return r


if __name__ == "__main__":
    for thr, label in [(0.0, "union"), (0.5, "muscriptor-supported"), (0.7, "agreement")]:
        print(label, run(thr))
