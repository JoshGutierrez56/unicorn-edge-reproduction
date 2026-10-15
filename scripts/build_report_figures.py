"""Render publication-ready figures from frozen aggregate outputs; no new backtest."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=Path('results/2026-10-14'))
    parser.add_argument('--output',type=Path,default=Path('docs/figures'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.titleweight':'bold','figure.facecolor':'#faf9f6',
                         'axes.facecolor':'#faf9f6','text.color':'#18333d','axes.labelcolor':'#18333d',
                         'svg.fonttype':'none'})
    def save(fig,name):
        fig.savefig(args.output/f'{name}.png',dpi=180,bbox_inches='tight')
        fig.savefig(args.output/f'{name}.svg',bbox_inches='tight')
        plt.close(fig)
    primary=pd.read_csv(args.results/'primary-daily.csv',parse_dates=['date'])
    equal=pd.read_csv(args.results/'equal-weight-universe-daily.csv',parse_dates=['date'])
    fig,axes=plt.subplots(1,3,figsize=(13,4.5))
    for ax,year in zip(axes,(2010,2015,2020)):
        for data,label,color in [(primary,'Unicorn Edge interpretation','#087b78'),(equal,'Equal-weight available current members','#ac7746')]:
            p=data[data.date.dt.year==year]
            ax.plot(np.arange(len(p)),np.cumprod(1+p.net_return),label=label,color=color,lw=1.8)
        ax.axhline(1,color='#83939a',lw=.7);ax.set_title(str(year));ax.set_xlabel('Trading sessions within year');ax.grid(alpha=.15)
    axes[0].set_ylabel('Wealth per $1 at start of each test year')
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.92),ncol=2,frameon=False)
    fig.suptitle('Three separate test years do not establish a 21-year track record',fontsize=16,y=1.04)
    fig.text(.01,-.04,'0.6 bp per traded dollar; primary uses train-frozen scaling and stops. Benchmark is long-only, unscaled, daily rebalanced.\nCurrent membership and current-vintage prices bias both series; risk exposures differ. Each panel restarts at $1.',fontsize=9)
    fig.tight_layout(rect=(0,0,1,.86));save(fig,'separate-test-years')
    s=pd.read_csv(args.results/'summary.csv').set_index('case')
    cases=['primary','ungated_blend','gated_inverse_price','gated_reversal','extra_execution_day','double_cost','cost_10bps','leverage_capped','adjusted_price_rank']
    labels=['Primary interpretation','No drift gate','Gated inverse-price only','Gated reversal only','One extra execution day','1.2 bp trading cost','10 bp trading cost','Leverage capped at 1','Adjusted-price ranking']
    values=s.loc[cases,'sharpe'].to_numpy();fig,ax=plt.subplots(figsize=(10,5.8))
    y=np.arange(len(cases));ax.barh(y,values,color=['#087b78' if v>=0 else '#ae514b' for v in values],height=.62)
    ax.set_yticks(y,labels);ax.invert_yaxis();ax.axvline(0,color='#5c6e75',lw=.8)
    for i,v in enumerate(values):ax.text(v+(.035 if v>=0 else -.035),i,f'{v:.2f}',va='center',ha='left' if v>=0 else 'right')
    ax.set_xlim(-.72,1.12);ax.set_xlabel('Annualized mean / volatility (zero cash yield; not benchmark-adjusted alpha)')
    ax.set_title('The headline 13.19 Sharpe is not reproduced',loc='left',fontsize=16,pad=18)
    fig.text(.01,-.03,'2010, 2015 and 2020 concatenated; selected comparisons shown. All 47 specified cases are accounted for in the public results.\nThese are sensitivity checks, not a search for a replacement winning strategy. No valid specified case reaches Sharpe 2.',fontsize=9)
    fig.tight_layout();save(fig,'robustness')
    annual=pd.read_csv(args.results/'annual-walk-forward.csv')
    fig,ax=plt.subplots(figsize=(11,4.6));vals=annual.total_return
    ax.bar(annual.year,vals,color=['#087b78' if v>=0 else '#ae514b' for v in vals],width=.72)
    ax.axhline(0,color='#5c6e75',lw=.8);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_xticks(annual.year)
    ax.set_ylabel('Calendar-year net return');ax.set_title('Broader retrospective check: 2010–2024',loc='left',fontsize=16,pad=16)
    fig.text(.01,-.03,'Five-year training calibration, year-end liquidation and annual restart. Current-member bias remains.\nThis additional retrospective evaluation is not an untouched holdout or a continuously operated live portfolio.',fontsize=9)
    fig.tight_layout();save(fig,'annual-walk-forward')


if __name__=='__main__':main()
