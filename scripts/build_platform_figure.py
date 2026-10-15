"""Answer-first figure using every predeclared cost/era/provider comparison."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root/'results/2026-10-14/platform-stress'
    cost = pd.read_csv(folder/'fixed-path-cost-overlays.csv')
    periods = pd.read_csv(folder/'periods.csv')
    factors = json.loads((folder/'factor-regressions.json').read_text(encoding='utf-8'))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'figure.facecolor':'#faf9f6','axes.facecolor':'#faf9f6',
        'text.color':'#18333d','axes.labelcolor':'#18333d','svg.fonttype':'none','svg.hashsalt':'platform-stress-v1'})
    fig,axes = plt.subplots(1,3,figsize=(13.2,5.5))
    colors = ['#087b78','#b07c44','#7c8b91']
    for borrow,color in zip([0,.01,.03],colors):
        rows = cost[(cost.source=='crsp_nominal') & (cost.annual_borrow_rate==borrow)]
        axes[0].plot(rows.fee_bps,rows.cagr*100,marker='o',color=color,label=f'{borrow:.0%} annual borrow')
    axes[0].set_title('Thin cost budget',loc='left',weight='bold')
    axes[0].set_xlabel('One-way trading cost (bp)')
    axes[0].set_ylabel('Fixed-path CAGR (%)')
    axes[0].set_xticks([.6,2,5,10])
    axes[0].axhline(0,color='#6a7e86',lw=.8)
    axes[0].legend(frameon=False,loc='lower left',fontsize=9)
    names = ['crsp_nominal','crsp_split','yahoo_matched']
    labels = ['CRSP nominal','CRSP split-adj.','Yahoo matched']
    for i,(name,label,color) in enumerate(zip(names,labels,colors)):
        v = factors[name]['FF5_MOM_HAC20']
        point = v['annual_intercept_arithmetic']*100
        low,high = v['annual_intercept_lower_95']*100,v['annual_intercept_upper_95']*100
        axes[1].errorbar(point,i,xerr=[[point-low],[high-point]],fmt='o',color=color,capsize=4)
    axes[1].set_yticks(range(3),labels,fontsize=9)
    axes[1].invert_yaxis()
    axes[1].axvline(0,color='#6a7e86',lw=.8)
    axes[1].set_ylim(2.65,-.65)
    axes[1].set_title('Alpha remains uncertain',loc='left',weight='bold')
    axes[1].set_xlabel('Annual regression intercept (%)\nFF5 + momentum · 95% HAC(20) interval')
    eras = ['2010-2014','2015-2019','2020-2024']
    for i,(name,label,color) in enumerate(zip(names,labels,colors)):
        rows = periods[(periods.source==name)&(periods.kind=='era')].set_index('period').loc[eras]
        axes[2].bar(np.arange(3)+(i-1)*.25,rows.sharpe,width=.23,label=label,color=color)
    axes[2].set_xticks(range(3),['2010–14','2015–19','2020–24'])
    axes[2].set_ylabel('Net Sharpe · zero risk-free rate')
    axes[2].set_title('Weaker recent periods',loc='left',weight='bold')
    axes[2].legend(frameon=False,fontsize=8.5)
    for ax in axes:
        ax.grid(axis='y' if ax!=axes[1] else 'x',alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle('The reconstruction leaves little room for implementation costs',x=.025,y=.98,ha='left',fontsize=17,weight='bold')
    fig.text(.025,.865,'2010–2024 annual restarts · 3,774 sessions · current-member universe · retrospective diagnostics',fontsize=10)
    fig.text(.025,.065,'Cost panel: CRSP nominal, fixed recorded decisions; not a full cost/stops rerun. Borrow rates are illustrative.\nFactor intervals are conditional and unadjusted for selection. Quote freezes are modeled; historical membership and actual borrow access remain unavailable.',fontsize=9,linespacing=1.5)
    fig.subplots_adjust(left=.065,right=.985,top=.75,bottom=.25,wspace=.65)
    for suffix in ['png','svg']:
        kwargs = {'dpi':180} if suffix=='png' else {'metadata':{'Date':None}}
        fig.savefig(root/f'docs/figures/platform-stress.{suffix}',bbox_inches='tight',**kwargs)
    plt.close(fig)


if __name__ == '__main__':
    main()
