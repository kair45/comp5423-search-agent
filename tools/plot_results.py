"""Plot recorded passage and document coverage using the same 100 questions."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
stats=json.loads((ROOT/"runs/validation-retrieval/coverage-by-depth.json").read_text())
fig,axes=plt.subplots(1,2,figsize=(6.8,3),sharey=True,layout="constrained")
for ax,key,title in zip(axes,["doc","passage"],["Whole document","Returned passage"]):
    for method,name,color,marker in [("bm25","BM25","#b35d21","s"),("e5","E5","#7559a4","^"),("qwen","Qwen","#2872ac","D"),("fusion","Fusion","#00655b","o")]:
        ax.plot([1,3,5],stats["methods"][method][key],label=name,color=color,marker=marker,lw=2.3 if method=="fusion" else 1.45,ms=4)
    ax.set(title=title,xticks=[1,3,5],ylim=(0,30),xlabel="Rank cutoff");ax.grid(axis="y",alpha=.2)
    ax.spines[["right","top"]].set_visible(False)
axes[0].set_ylabel("Questions covered / 100");axes[1].legend(frameon=False,fontsize=8,loc="upper left")
fig.savefig(ROOT/"report/figures/coverage.pdf",bbox_inches="tight");plt.close(fig)
