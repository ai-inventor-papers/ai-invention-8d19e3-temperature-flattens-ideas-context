import json, sys
A = sys.argv[1]
R = json.load(open(f"{A}/results/results.json")); S = R["settings"]
figs = []
# --- probe curve
L = R["probe_curve"]["layers"]
def ser(key, f): return ", ".join(f"{r['layer']}: {f(r):.3f}" for r in L)
d = ("Line chart of linear-probe balanced accuracy for the final idea class against layer index (x-axis 'Layer', 0 to 36; y-axis 'Balanced accuracy (pooled over both tasks)', range 0.2 to 0.8). "
     "Four series. (1) 'Probe on mean of generated tokens 1-32' values by layer: " + ser(0, lambda r: r['bal_acc_pooled']) + ". "
     "(2) 'Shuffled-label control (same feature)' values: " + ser(0, lambda r: r['shuf_bal_acc_pooled']) + "; draw its standard deviation as a light band, sd by layer: " + ser(0, lambda r: r['shuf_bal_acc_pooled_sd']) + ". "
     "(3) 'Probe on mean of generated tokens 1-8 (original plan)': " + ser(0, lambda r: r['per_position_bal_acc']['mean_gen1_8']) + ". "
     "(4) 'Probe on generated token 1 only': " + ser(0, lambda r: r['per_position_bal_acc']['gen1']) + ". "
     "Add a horizontal dashed reference line at 0.433 labelled 'task-identity level (majority idea per task)'. Shade layers 29-31 and label the shading 'intervention band'. "
     "The point to see: the 32-token feature sits about 0.25 above its shuffled control at every depth with no rise across layers, while the early-token features are flat at the task-identity level.")
figs.append({"id": "fig_probe", "title": "Idea probes by layer", "aspect_ratio": "16:9",
  "caption": "Cross-validated balanced accuracy of multinomial probes for the realised idea class, pooled over the open path-search and weighted shortest-path tasks (Qwen2.5-3B-Instruct, 300 baseline samples per task). Probes on the first generated tokens recover only task identity (0.433); the mean over tokens 1-32 is decodable at 0.64-0.71 against 0.39-0.43 for shuffled labels, flatly across depth. Layers 29-31 were used for all interventions.",
  "image_gen_detailed_description": d, "summary": "Early tokens carry no idea information; a 32-token window does, flat across layers."})
# --- temperature
def g(n, t, k): return S[n]["tasks"][t][k]
temps = [("baseline", 0.7), ("temp1.0", 1.0), ("temp1.3", 1.3), ("temp1.6", 1.6), ("temp2.0", 2.0)]
def tline(t, k): return ", ".join(f"T={T}: {abs(g(n, t, k)):.3f}" for n, T in temps)
tn = {"T1": "open path-search task", "T3": "weighted shortest-path task"}
d = ("Two side-by-side panels sharing the x-axis 'Sampling temperature' with ticks 0.7, 1.0, 1.3, 1.6, 2.0. Left panel title 'Open path-search task', right panel 'Weighted shortest-path task'. "
     "In each panel three line series against temperature: 'Oracle pass rate' (left y-axis, 0 to 1), 'Degenerate share (syntax error or no code)' (left y-axis, 0 to 1), and 'Idea entropy (bits)' (right y-axis, 0 to 2). ")
for t in ("T1", "T3"):
    d += (f"{tn[t]}: pass rate {tline(t, 'pass')}; degenerate share {tline(t, 'degeneration')}; idea entropy {tline(t, 'entropy')}; "
          f"plus single unconnected markers at T=1.6 for 'top-k = 10': pass {g('temp1.6_top10', t, 'pass'):.3f}, degenerate {g('temp1.6_top10', t, 'degeneration'):.3f}, entropy {g('temp1.6_top10', t, 'entropy'):.3f}. ")
d += ("Draw a horizontal dotted line on the pass-rate axis at the eligibility threshold: 0.560 in the left panel and 0.299 in the right panel. Note: at T=2.0 idea entropy is 0 because no output (open task) or one output in 150 (weighted task) contains a classifiable program. "
      "The point to see: pass rate falls steeply and degeneration rises from T=1.0 on, while idea entropy gains only a few tenths of a bit before collapsing.")
figs.append({"id": "fig_temp", "title": "Temperature sweep: correctness vs ideas", "aspect_ratio": "16:9",
  "caption": "Temperature sweep in the influence arm (n = 150 per point; T = 0.7 is the baseline draw). Correctness collapses above T = 1.0 while idea entropy rises by at most 0.46 bits; top-k = 10 at T = 1.6 keeps code parseable but not correct. The best temperature that keeps at least 80% of baseline pass rate (pooled) is T = 0.7.",
  "image_gen_detailed_description": d, "summary": "Temperature trades correctness for little idea diversity."})
# --- selection stacked bars
sets = [("baseline", "baseline"), ("Hdim_a0.05", "diff-in-means α=0.05"), ("Hdim_a0.106", "diff-in-means α=0.106"), ("Hdim_a0.224", "diff-in-means α=0.224"), ("Hdim_a0.473", "diff-in-means α=0.473"), ("Hprobe_a0.75", "probe-weight α=0.75")]
NON = {"syntax_error", "no_code"}
def comp(n, t):
    c = S[n]["tasks"][t]["label_counts"]
    bfs, dfs, dij = c.get("bfs", 0), c.get("dfs", 0), c.get("dijkstra", 0)
    non = sum(v for k, v in c.items() if k in NON)
    oth = sum(c.values()) - bfs - dfs - dij - non
    return bfs, dfs, dij, oth, non, S[n]["tasks"][t]["pass"]
d = ("Two panels of stacked bar charts (counts out of 150 samples per bar). Left panel 'Open path-search task', right panel 'Weighted shortest-path task'. Six bars per panel, in this order: " + ", ".join(lab for _, lab in sets) + ". "
     "Stack segments in this order and colours: BFS (blue), DFS (orange), Dijkstra (green), other idea classes (purple), syntax error or no code (grey). Print the oracle pass rate above each bar. ")
for t in ("T1", "T3"):
    d += f"{tn[t]}: " + "; ".join(f"{lab}: BFS {b}, DFS {df}, Dijkstra {dj}, other ideas {o}, syntax error/no code {nn}, pass {p:.3f}" for (n, lab), (b, df, dj, o, nn, p) in [((n, lab), comp(n, t)) for n, lab in sets]) + ". "
d += "The point to see: in the open task the 'flattening' directions convert the distribution to DFS (145 of 150 at α=0.224) with pass rate unchanged; in the weighted task they move mass from Dijkstra to BFS and pass rate drops."
figs.append({"id": "fig_select", "title": "Flattening directions select DFS", "aspect_ratio": "16:9",
  "caption": "Idea composition under the two 'flattening' directions (layers 29-31, prompt-final token plus first 64 generated tokens; n = 150 per bar). Instead of evening out the two menu ideas, the directions select the minority idea: DFS on the open task, BFS on the weighted task, where BFS-style programs are usually incorrect.",
  "image_gen_detailed_description": d, "summary": "Internal steering selects one known idea rather than flattening the choice."})
# --- pareto scatter
fam_of = {}
for n, v in S.items():
    if n.startswith("calib") or n.endswith("__ho"): continue
    fam_of[n] = v["family"]
groups = {}
for n, f in fam_of.items():
    groups.setdefault(f, []).append(n)
nice = {"baseline": "baseline (T=0.7)", "temperature": "temperature", "prompt": "prompts and ban", "gts": "generate-then-select", "H-probe": "probe-weight direction", "H-dim": "diff-in-means direction",
        "H-probe-explore": "probe-weight direction, post hoc", "H-dim-explore": "diff-in-means direction, post hoc", "A3-proj": "menu erasure, projection", "A3-leace": "menu erasure, LEACE", "A4": "cross-task novelty direction",
        "R-add": "random direction (control)", "R-proj": "random projection (control)", "crn": "baseline rerun (noise floor)"}
d = ("Scatter plot. x-axis 'Oracle pass rate (pooled over both tasks)', range 0 to 0.65; y-axis 'Idea entropy, bits (pooled)', range 0 to 2.7. One series per family with a distinct colour; the two control families in light and dark grey. Points (label: pass, entropy): ")
for f, ns in groups.items():
    d += f"[{nice.get(f, f)}] " + "; ".join(f"{n}: {S[n]['pooled']['pass']:.3f}, {abs(S[n]['pooled']['entropy']):.3f}" for n in ns) + ". "
fr = R["pareto"]["entropy"]["pareto_front"]
d += ("Draw a vertical dotted red line at pass = 0.429 labelled 'eligibility (0.8 x baseline pass)'. Connect the Pareto front over methods (controls excluded) with a dashed black line through, sorted by pass: "
      + "; ".join(f"{p['setting']} ({p['pass']:.3f}, {p['entropy']:.3f})" for p in sorted(fr, key=lambda p: p['pass'])) + ". Label those front points and the baseline. "
      "The point to see: above the eligibility line the top-3 ban has the highest entropy; internal knobs sit below it and among the grey random-control points.")
figs.append({"id": "fig_pareto", "title": "Diversity against correctness, all settings", "aspect_ratio": "4:3",
  "caption": "Every sweep setting on pooled pass rate and idea entropy (n = 150 per task for methods, 75 for random controls). The dashed line is the Pareto front over methods; random controls are excluded from it but seven of them would join it. No internal knob reaches the top-3 ban among eligible settings, and generate-then-select reaches the highest entropy at a pass rate of 0.263.",
  "image_gen_detailed_description": d, "summary": "Prompting tops the diversity-correctness front; internal knobs mix with random controls."})
# --- A4 dose
a = R["survival"]["A4"]
d = ("Two-panel line chart, x-axis 'Steering strength α' with points 0, 0.2, 0.356, 0.632, 1.12, 2.0 (use a symlog or categorical axis). Left panel y-axis 'Atypicality: mean −log baseline frequency of the realised idea (nats)', range 0 to 2. Right panel y-axis 'Oracle pass rate', range 0 to 0.8. "
     "Series 'Open path-search task' atypicality: " + ", ".join(f"α={x}: {y:.3f}" for x, y in zip(a['alphas'], a['tasks']['T1']['atypicality'])) +
     "; pass: " + ", ".join(f"α={x}: {y:.3f}" for x, y in zip(a['alphas'], a['tasks']['T1']['pass'])) + ". "
     "Series 'Weighted shortest-path task' atypicality: " + ", ".join(f"α={x}: {y:.3f}" for x, y in zip(a['alphas'], a['tasks']['T3']['atypicality'])) +
     "; pass: " + ", ".join(f"α={x}: {y:.3f}" for x, y in zip(a['alphas'], a['tasks']['T3']['pass'])) + ". "
     f"Annotate the legend with Spearman rho: open task {a['tasks']['T1']['spearman']:.2f}, weighted task {a['tasks']['T3']['spearman']:.2f}; the pre-registered requirement was 0.8 on both. "
     "The point to see: atypicality rises then falls on the open task and never rises consistently on the weighted task.")
figs.append({"id": "fig_a4", "title": "Novelty direction is not a dial", "aspect_ratio": "16:9",
  "caption": "Dose-response of the cross-task novelty direction (extracted from five non-path tasks, added at layers 29-31; n = 150 per point, α = 0 is the baseline). Atypicality of the realised idea is not monotone in strength (Spearman 0.49 and −0.26 against a required 0.8), so the direction fails as a dial even though it detects novelty requests with AUROC 1.0.",
  "image_gen_detailed_description": d, "summary": "The transferable novelty readout does not work as a monotone steering dial."})
json.dump(figs, open("work/figs.json", "w"), indent=1)
print(len(figs)); print(figs[3]["image_gen_detailed_description"][:3000])
