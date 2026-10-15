"""Render the matched CRSP diagnostic from frozen aggregate results only."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd


def main():
    root=Path(__file__).resolve().parents[1]
    s=pd.read_csv(root/'results/2026-10-14/crsp-followup/summary.csv').set_index('case')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'figure.facecolor':'#faf9f6','axes.facecolor':'#faf9f6',
        'text.color':'#18333d','axes.labelcolor':'#18333d','svg.fonttype':'none','svg.hashsalt':'crsp-followup-v1'})
    fig,ax=plt.subplots(figsize=(10.5,6.2))
    panels=[('yahoo_close_quote_freeze','Yahoo · matched quotes','#7c8b91'),
            ('crsp_nominal_stale_freeze','CRSP · nominal price','#087b78'),
            ('crsp_split_stale_freeze','CRSP · split-adjusted','#b07c44')]
    for group,(mode,label) in enumerate([('gated_blend','Main blend'),('gated_reversal','Reversal only'),('cost_10bps','Main blend · 10 bp')]):
        for j,(source,name,color) in enumerate(panels):
            y=group*4+j;value=float(s.loc[source+'_'+mode,'sharpe'])
            ax.barh(y,value,height=.65,color=color,label=name if group==0 else None)
            ax.text(value+(.025 if value>=0 else -.025),y,f'{value:.2f}',ha='left' if value>=0 else 'right',va='center')
    ax.set_yticks([1,5,9],['Main blend','Reversal only','Main blend\n10 bp / traded dollar'])
    ax.invert_yaxis();ax.axvline(0,color='#6a7e86',lw=.8);ax.set_xlim(-1.,1.)
    ax.set_xlabel('Annualized mean / volatility · zero cash yield')
    ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    ax.legend(loc='lower center',bbox_to_anchor=(.5,1.02),ncol=3,frameon=False,fontsize=9)
    fig.suptitle('CRSP does not recover the paper’s 13.19 Sharpe',x=.04,y=.98,ha='left',fontsize=16,weight='bold')
    fig.text(.04,.065,'490 reviewed current stocks · test years 2010, 2015, 2020 · 0.6 bp except specified cost check\nCRSP uses explicitly modeled stale valuation with trading frozen during missing quotes. Strict cases remain blocked.\nSame-date execution is optimistic. Current membership is not point-in-time. No alpha or live-performance claim.',fontsize=9,linespacing=1.5)
    fig.subplots_adjust(left=.23,right=.97,top=.79,bottom=.23)
    output=root/'docs/figures/crsp-comparison'
    fig.savefig(output.with_suffix('.png'),dpi=180,bbox_inches='tight')
    fig.savefig(output.with_suffix('.svg'),bbox_inches='tight',metadata={'Date':None})
    plt.close(fig)


if __name__=='__main__':main()
