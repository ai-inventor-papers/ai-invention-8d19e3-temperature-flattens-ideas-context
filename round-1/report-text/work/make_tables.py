"""Build every markdown table of the iteration-1 section directly from the artifact's output files.

Usage: python3 work/make_tables.py <artifact_dir> <out_json>
Writes a JSON dict {table_key: markdown_string}; the draft template references them as {{key}}.
"""
import collections
import glob
import json
import os
import sys

A = sys.argv[1]
OUT = sys.argv[2]
R = json.load(open(f"{A}/results/results.json"))
S = R["settings"]
T = {}
TASKN = {"T1": "open path search", "T3": "weighted shortest path"}
SHORT = {"bfs": "BFS", "dfs": "DFS", "dijkstra": "Dijkstra", "astar": "A*", "other": "other", "spfa": "SPFA",
         "bellman_ford": "Bellman-Ford", "floyd_warshall": "Floyd-Warshall", "bidirectional": "bidirectional",
         "greedy_best_first": "greedy best-first search", "iddfs": "iterative deepening", "random_walk": "random walk",
         "syntax_error": "syntax error", "no_code": "no code", "other_known": "other (known)"}


def NM(n):
    """Descriptive row name for a setting code (codes are not shown to the reader)."""
    import re as _re
    ho = n.endswith("__ho")
    b = n[:-4] if ho else n
    fixed = {"baseline": "baseline T=0.7", "crn_rerun": "baseline rerun (noise floor)", "temp1.6_top10": "temperature 1.6, top-k 10",
             "prompt_new": "new-algorithm prompt", "prompt_novel2000": "2000-word novelty prompt", "prompt_ban3": "top-3 ban",
             "gts": "generate-then-select", "temp0.7": "temperature 0.7"}
    if b in fixed:
        out = fixed[b]
    elif b.startswith("temp"):
        out = "temperature " + b[4:]
    else:
        m = _re.match(r"(Hprobe_x|Hdim_x|Hprobe|Hdim|A4|A3leace|A3proj_r1|Radd|Rproj_r1)_a([0-9.]+)(?:_d(\d))?$", b)
        fam, a, d = m.group(1), m.group(2), m.group(3)
        base = {"Hprobe": "probe-weight direction α=", "Hdim": "difference-in-means direction α=", "Hprobe_x": "probe-weight direction α=",
                "Hdim_x": "difference-in-means direction α=", "A4": "novelty direction α=", "A3leace": "LEACE erasure a=",
                "A3proj_r1": "rank-1 projection a=", "Radd": "random direction α=", "Rproj_r1": "random projection a="}[fam]
        out = base + a + (" (post hoc)" if fam.endswith("_x") else "") + (f", draw {d}" if d is not None else "")
    return out + (", held-out" if ho else "")


def f3(x):
    return "–" if x is None or x != x else f"{(0.0 if abs(x) < 5e-4 else x):.3f}"


def labs(d):
    return ", ".join(f"{SHORT.get(k, k)} {v}" for k, v in d.items())


# ---------------- baseline n=300 per task, from scored rows
rows = []
for t in ("T1", "T3"):
    rs = [json.loads(l) for l in open(f"{A}/scored/{t}/baseline.jsonl")]
    c = collections.defaultdict(lambda: [0, 0])
    for r in rs:
        c[r["label"]][0] += 1
        c[r["label"]][1] += int(r["pass"])
    tot_pass = sum(v[1] for v in c.values())
    for k, v in sorted(c.items(), key=lambda x: -x[1][0]):
        rows.append(f"| {TASKN[t]} | {SHORT.get(k, k)} | {v[0]} | {v[0] / len(rs):.3f} | {v[1]} | {v[1] / v[0]:.3f} |")
    rows.append(f"| {TASKN[t]} | **all** | {len(rs)} | 1.000 | {tot_pass} | {tot_pass / len(rs):.3f} |")
T["baseline300"] = ("| task | idea class | count | share | passing | pass rate within class |\n|---|---|---|---|---|---|\n"
                    + "\n".join(rows))

# ---------------- classifier audit confusion matrix
ca = R["classifier_audit"]
M = ca["matrix_rule_rows_judge_cols"]
cols = list(next(iter(M.values())).keys())
hdr = "| rule \\ judge | " + " | ".join(SHORT.get(c, c) for c in cols) + " | row total |"
sep = "|---" * (len(cols) + 2) + "|"
body = []
for rk, row in M.items():
    body.append(f"| **{SHORT.get(rk, rk)}** | " + " | ".join(str(row[c]) if row[c] else "·" for c in cols)
                + f" | {sum(row.values())} |")
T["audit"] = hdr + "\n" + sep + "\n" + "\n".join(body)
T["audit_stats"] = f"n = {ca['n']}, agreement = {ca['agreement']:.3f}, Cohen's kappa = {ca['cohen_kappa']:.3f}"

# ---------------- probe curve
pr = ["| layer | C | bal. acc. mean(gen1..32), pooled | open path search | weighted shortest path | shuffled-label pooled (mean ± sd, 5 perms) | gen1 only | gen8 only | mean(gen1..8) |",
      "|---|---|---|---|---|---|---|---|---|"]
for r in R["probe_curve"]["layers"]:
    pp = r["per_position_bal_acc"]
    pr.append(f"| {r['layer']} | {r['C']} | {r['bal_acc_pooled']:.3f} | {r['bal_acc_T1']:.3f} | {r['bal_acc_T3']:.3f} | "
              f"{r['shuf_bal_acc_pooled']:.3f} ± {r['shuf_bal_acc_pooled_sd']:.3f} | {pp['gen1']:.3f} | {pp['gen8']:.3f} | {pp['mean_gen1_8']:.3f} |")
T["probe"] = "\n".join(pr)

# ---------------- name mention position
cp = R["commitment_point"]
m = ["| task | generations | with an algorithm name | median token of first mention | quartiles (25/50/75) | share within 8 tokens | within 32 | within 64 |",
     "|---|---|---|---|---|---|---|---|"]
for t in ("T1", "T3"):
    c = cp[t]
    m.append(f"| {TASKN[t]} | {c['n']} | {c['mentions']} | {c['median_token']} | {' / '.join(str(q) for q in c['quartiles'])} | "
             f"{c['share_within_8']:.3f} | {c['share_within_32']:.3f} | {c['share_within_64']:.3f} |")
T["mention"] = "\n".join(m)

# ---------------- vector checks
vc = R["vector_checks"]
lc = ["| task, layer | probe bal. acc. before | after LEACE | after rank-1 projection | chance | majority share |",
      "|---|---|---|---|---|---|"]
for k, v in vc["leace_offline"].items():
    t, l = k.split("_")
    lc.append(f"| {TASKN[t]}, layer {l[1:]} | {v['bal_acc_before']:.3f} | {v['bal_acc_after']:.3f} | {v['bal_acc_after_proj_rk-1']:.3f} | "
              f"{v['chance_bal_acc']:.3f} | {v['majority_share']:.3f} |")
T["leace"] = "\n".join(lc)
sv = ["| task, layer | singular value 1 | singular value 2 |", "|---|---|---|"]
for k, v in vc["A3_rank"].items():
    t, l = k.split("_")
    sv.append(f"| {TASKN[t]}, layer {l[1:]} | {v['singular_values'][0]:.3f} | {v['singular_values'][1]:.3f} |")
T["svd"] = "\n".join(sv)
cs = ["| layer | cos(probe-weight dir., diff-in-means dir.) open path search | weighted shortest path |", "|---|---|---|"]
for l in (29, 30, 31):
    cs.append(f"| layer {l} | {vc['cos'][f'Hprobe_vs_Hdim_T1_L{l}']:.3f} | {vc['cos'][f'Hprobe_vs_Hdim_T3_L{l}']:.3f} |")
T["hcos"] = "\n".join(cs)
a4 = vc["A4"]
ar = ["| layer | leave-one-task-out cosine: sorting | substring | primality | compression | matmul | held-out AUROC open path search | weighted shortest path | cos with probe-weight dir. (path / weighted) | cos with diff-in-means dir. (path / weighted) | cos with erasure subspace (path / weighted) |",
      "|---|---|---|---|---|---|---|---|---|---|---|"]
for l in (29, 30, 31):
    L = f"L{l}"
    ar.append(f"| layer {l} | " + " | ".join(f"{a4['loto_cos'][f'{L}_{n}']:.3f}" for n in ("sorting", "substring", "primality", "compression", "matmul"))
              + f" | {a4['heldout_auroc'][f'{L}_T1_path']:.1f} | {a4['heldout_auroc'][f'{L}_T3_wsp']:.1f} | "
              f"{a4['cos_with_H'][f'{L}_T1_Hprobe']:.3f} / {a4['cos_with_H'][f'{L}_T3_Hprobe']:.3f} | "
              f"{a4['cos_with_H'][f'{L}_T1_Hdim']:.3f} / {a4['cos_with_H'][f'{L}_T3_Hdim']:.3f} | "
              f"{a4['cos_with_A3_subspace'][f'{L}_T1']:.3f} / {a4['cos_with_A3_subspace'][f'{L}_T3']:.3f} |")
T["a4vec"] = "\n".join(ar)

# ---------------- calibration
cal = R["calibration"]
KN = {"Hprobe": "probe-weight direction", "Hdim": "difference-in-means direction", "A4": "novelty direction"}
cr = ["| knob | strength α | pass (n=20) | degenerate share | idea labels |", "|---|---|---|---|---|"]
for k, v in cal["knobs"].items():
    for r in v["rows"]:
        cr.append(f"| {KN[k]} | {r['alpha']} | {r['pass']:.2f} | {r['degenerate']:.2f} | {labs(r['labels'])} |")
    cr.append(f"| {KN[k]} | **chosen** | α_lo = {v['alpha_lo']}, α_hi = {v['alpha_hi']} | | {', '.join(str(a) for a in v['chosen'])} |")
T["calib"] = "\n".join(cr)

# ---------------- settings tables
def setting_rows(names):
    out = ["| setting | n per task | path: pass | path: idea entropy | path: idea labels | weighted: pass | weighted: idea entropy | weighted: idea labels | pooled pass | pooled idea entropy | eligible (path / weighted / pooled) |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        v = S[n]
        a, b, p = v["tasks"]["T1"], v["tasks"]["T3"], v["pooled"]
        e = v["eligible"]
        out.append(f"| {NM(n)} | {a['n']} | {a['pass']:.3f} | {abs(a['entropy']):.3f} | {labs(a['label_counts'])} | {b['pass']:.3f} | {abs(b['entropy']):.3f} | "
                   f"{labs(b['label_counts'])} | {p['pass']:.3f} | {abs(p['entropy']):.3f} | {'y' if e['T1'] else 'n'} / {'y' if e['T3'] else 'n'} / {'y' if v.get('eligible_pooled') else 'n'} |")
    return "\n".join(out)


def ext_rows(names):
    out = ["| setting | path: off-menu correct | path: atypicality | path: degeneration | path: flip rate vs baseline | path: Hill-1 | path: entropy among passing | path: phrasing diversity (modal idea) | weighted: off-menu correct | weighted: atypicality | weighted: degeneration | weighted: flip rate | weighted: Hill-1 | weighted: entropy among passing | weighted: phrasing diversity |",
           "|---" * 15 + "|"]
    for n in names:
        v = S[n]
        cells = [NM(n)]
        for t in ("T1", "T3"):
            x = v["tasks"][t]
            cells += [f3(x["offmenu_correct_share"]), f3(x["atypicality"]), f3(x["degeneration"]), f3(x["flip_rate_vs_baseline"]),
                      f3(x["hill1"]), f3(x["entropy_pass"]), f3(x["phrasing_diversity_modal_idea"])]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


PRACT = ["baseline", "crn_rerun", "temp1.0", "temp1.3", "temp1.6", "temp1.6_top10", "temp2.0", "prompt_new",
         "prompt_novel2000", "prompt_ban3", "gts"]
HSET = [f"Hprobe_a{a}" for a in ("0.75", "0.892", "1.06", "1.26", "1.5")] + [f"Hdim_a{a}" for a in ("0.05", "0.106", "0.224", "0.473", "1")] \
    + [f"Hprobe_x_a{a}" for a in ("0.1", "0.2", "0.35", "0.5")] + ["Hdim_x_a0.075"]
A3SET = ["A3proj_r1_a0.25", "A3proj_r1_a0.5", "A3proj_r1_a0.75", "A3proj_r1_a1", "A3leace_a0.5", "A3leace_a1"]
A4SET = [f"A4_a{a}" for a in ("0.2", "0.356", "0.632", "1.12", "2")]
CTRL = sorted([n for n in S if (n.startswith("Radd") or n.startswith("Rproj")) and not n.endswith("__ho")],
              key=lambda n: (n[:5], float(n.split("_a")[1].split("_")[0]), n))
HO = [n for n in S if n.endswith("__ho")]
T["s_pract"] = setting_rows(PRACT)
T["s_H"] = setting_rows(HSET)
T["s_A3"] = setting_rows(A3SET)
T["s_A4"] = setting_rows(A4SET)
T["s_ctrl"] = setting_rows(CTRL)
T["s_ho"] = setting_rows(["temp0.7__ho", "prompt_new__ho", "prompt_novel2000__ho", "prompt_ban3__ho", "Hdim_a0.05__ho",
                          "Radd_a0.05_d0__ho", "A3proj_r1_a0.25__ho", "Rproj_r1_a0.25_d0__ho", "A3leace_a0.5__ho", "Rproj_r1_a0.5_d0__ho"])
T["x_main"] = ext_rows(PRACT + HSET + A3SET + A4SET)
T["x_ctrl"] = ext_rows(CTRL + HO)

# ---------------- survival
sv = R["survival"]
hd = sv["H-dim"]
sr = ["| knob family | selected setting (indices 0..99) | rule | held-out numbers | verdict |", "|---|---|---|---|---|"]
sr.append(f"| probe-weight flattening | none | entropy ≥ 2× best eligible temperature and CI vs random direction excludes 0 | {sv['H-probe']['reason']} | fails |")
sr.append(f"| difference-in-means flattening | {NM(hd['setting'])} | same | path: entropy {hd['T1']['entropy_H']:.3f} vs {hd['T1']['entropy_best_temp']:.3f} (ratio {hd['T1']['ratio']:.3f}), "
          f"diff vs random {hd['T1']['vs_control']['diff']:.3f} [{hd['T1']['vs_control']['ci'][0]:.3f}, {hd['T1']['vs_control']['ci'][1]:.3f}], pass {hd['T1']['pass_H']:.2f}; "
          f"weighted: {hd['T3']['entropy_H']:.3f} vs {hd['T3']['entropy_best_temp']:.3f} (ratio {hd['T3']['ratio']:.3f}), diff {hd['T3']['vs_control']['diff']:.3f} "
          f"[{hd['T3']['vs_control']['ci'][0]:.3f}, {hd['T3']['vs_control']['ci'][1]:.3f}], pass {hd['T3']['pass_H']:.2f}; pooled {hd['pooled']['entropy_H']:.3f} vs {hd['pooled']['entropy_best_temp']:.3f}, "
          f"diff {hd['pooled']['vs_control']['diff']:.3f} [{hd['pooled']['vs_control']['ci'][0]:.3f}, {hd['pooled']['vs_control']['ci'][1]:.3f}] | fails |")
for fam, nm in (("A3-proj", "menu erasure, rank-1 projection"), ("A3-leace", "menu erasure, LEACE")):
    x = sv[fam]
    sr.append(f"| {nm} | {NM(x['setting'])} | judge-confirmed novel-and-correct share ≥ 3× best of temperature/prompts/ban, ≥ 0.05 absolute, CI vs random projection excludes 0 | "
              f"share {x['share_A3_pooled']:.3f} (comparators all {x['max_comparator']:.3f}); rule-only upper bound {x['rule_only_upper_bound_A3']:.3f}; pass {x['pass_A3']:.3f} | fails |")
a = sv["A4"]["tasks"]
sr.append(f"| cross-task novelty direction | all 5 strengths (no selection) | Spearman(α, atypicality) ≥ 0.8 on both tasks and top strength beats random | "
          f"Spearman path {a['T1']['spearman']:.3f} [{a['T1']['spearman_ci'][0]:.3f}, {a['T1']['spearman_ci'][1]:.3f}], weighted {a['T3']['spearman']:.3f} "
          f"[{a['T3']['spearman_ci'][0]:.3f}, {a['T3']['spearman_ci'][1]:.3f}]; top vs random path {a['T1']['top_vs_radd']['diff']:.3f} [{a['T1']['top_vs_radd']['ci'][0]:.3f}, {a['T1']['top_vs_radd']['ci'][1]:.3f}], "
          f"weighted {a['T3']['top_vs_radd']['diff']:.3f} [{a['T3']['top_vs_radd']['ci'][0]:.3f}, {a['T3']['top_vs_radd']['ci'][1]:.3f}] | fails |")
T["survival"] = "\n".join(sr)

ad = ["| strength α | path: atypicality | path: pass | weighted: atypicality | weighted: pass |", "|---|---|---|---|---|"]
for i, al in enumerate(sv["A4"]["alphas"]):
    ad.append(f"| {al} | {a['T1']['atypicality'][i]:.3f} | {a['T1']['pass'][i]:.3f} | {a['T3']['atypicality'][i]:.3f} | {a['T3']['pass'][i]:.3f} |")
ad.append(f"| slope of Δlog p vs −log p0 at top strength | {a['T1']['slope_dlogp_vs_neglogp0']:.3f} | | {a['T3']['slope_dlogp_vs_neglogp0']:.3f} | |")
T["a4dose"] = "\n".join(ad)

# ---------------- knob vs random controls
kr = ["| setting | path: Δ entropy vs random [95% CI] | path: Δ pass vs random [95% CI] | weighted: Δ entropy [95% CI] | weighted: Δ pass [95% CI] |", "|---|---|---|---|---|"]
for n, v in R["knob_vs_random_controls"].items():
    cells = [NM(n)]
    for t in ("T1", "T3"):
        for k in ("entropy_vs_radd", "pass_vs_radd"):
            x = v[t][k]
            cells.append(f"{x['diff']:+.3f} [{x['ci'][0]:+.3f}, {x['ci'][1]:+.3f}]{' *' if x['excludes_0'] else ''}")
    kr.append("| " + " | ".join(cells) + " |")
T["knobrand"] = "\n".join(kr)

# ---------------- manipulation checks
mc = R["manipulation_checks"]["settings"]
mr = ["| setting | path, layer 30: probe menu entropy (bits) | path, layer 30: probe decodability | path, layer 33: menu entropy | path, layer 33: decodability | weighted, layer 30: menu entropy | weighted, layer 30: decodability | weighted, layer 33: menu entropy | weighted, layer 33: decodability |",
      "|---|---|---|---|---|---|---|---|---|"]
order = ["crn_rerun", "temp0.7__ho", "temp1.0", "prompt_ban3", "prompt_new", "prompt_novel2000"] + [n for n in HSET if n in mc] + A3SET + A4SET
for n in order:
    if n not in mc:
        continue
    v = mc[n]
    cells = [NM(n)]
    for t in ("T1", "T3"):
        for tag in ("band_mid", "downstream"):
            x = v[t][tag]
            cells += [f"{x['menu_entropy_bits']:.3f}", f"{x['decod_bal_acc']:.3f}"]
    mr.append("| " + " | ".join(cells) + " |")
T["manip"] = "\n".join(mr)

# ---------------- pareto
pa = R["pareto"]
OBJ = {"entropy": "idea entropy", "offmenu_correct_share": "off-menu correct share", "outside_menu_correct_share": "judge-confirmed novel-and-correct share", "entropy_pass": "idea entropy among passing programs"}
pt = ["| objective (pooled, vs pass rate) | Pareto front (methods only) | random controls that would join the front | best prompt or temperature | best internal knob |", "|---|---|---|---|---|"]
for k, v in pa.items():
    front = "; ".join(f"{NM(p['setting'])} ({p['pass']:.3f}, {p[k]:.3f})" for p in v["pareto_front"])
    pt.append(f"| {OBJ[k]} | {front} | {', '.join(NM(c) for c in v['controls_on_front_if_included'])} | {NM(v['best_prompt_or_temperature'][0])} ({v['best_prompt_or_temperature'][1]:.3f}) | "
              f"{NM(v['best_internal_knob'][0])} ({v['best_internal_knob'][1]:.3f}) |")
T["pareto"] = "\n".join(pt)
rk = ["| rank | setting | pooled idea entropy |", "|---|---|---|"]
for i, x in enumerate(pa["entropy"]["eligible_ranking_top10"]):
    rk.append(f"| {i + 1} | {NM(x['setting'])} | {x['entropy']:.3f} |")
T["entrank"] = "\n".join(rk)

# ---------------- judge verdicts on passing rule-'other' programs (recomputed from rows)
jm = {}
for l in open(f"{A}/judge/verdicts.jsonl"):
    r = json.loads(l)
    jm[r["key"]] = r
keys = set()
for t in ("T1", "T3"):
    for fpath in glob.glob(f"{A}/scored/{t}/*.jsonl"):
        if os.path.basename(fpath).startswith("calib"):
            continue
        for l in open(fpath):
            r = json.loads(l)
            if r["pass"] and r["label"] == "other":
                keys.add(f"{t}:{r['code_hash']}")
cnt = collections.Counter((k.split(":")[0], jm.get(k, {}).get("verdict", "unjudged")) for k in keys)
verds = sorted({v for _, v in cnt})
jr = ["| judge verdict | open path search | weighted shortest path | total |", "|---|---|---|---|"]
for vv in sorted(verds, key=lambda x: -(cnt[('T1', x)] + cnt[('T3', x)])):
    jr.append(f"| {SHORT.get(vv, vv)} | {cnt[('T1', vv)]} | {cnt[('T3', vv)]} | {cnt[('T1', vv)] + cnt[('T3', vv)]} |")
jr.append(f"| distinct novel algorithm | 0 | 0 | 0 |")
jr.append(f"| **all** | {sum(c for (t, _), c in cnt.items() if t == 'T1')} | {sum(c for (t, _), c in cnt.items() if t == 'T3')} | {len(keys)} |")
T["judge"] = "\n".join(jr)
allv = collections.Counter(r["verdict"] for r in jm.values())
T["judge_all"] = ", ".join(f"{SHORT.get(k, k)} {v}" for k, v in allv.most_common())
T["judge_n"] = str(len(jm))

# ---------------- generate-then-select picks
g = R["gen_then_select"]
gr = ["| task | stage-1 lists parsed | mean items listed | 15 most frequent picked items (count) |", "|---|---|---|---|"]
for t in ("T1", "T3"):
    x = g[t]
    gr.append(f"| {TASKN[t]} | {x['n'] - x['parse_failed']}/{x['n']} | {x['mean_items_listed']:.2f} | "
              + "; ".join(f"{it.replace(chr(39) + 's', '')} ({c})" for it, c in x["top_picked_items"]) + " |")
T["gts"] = "\n".join(gr)

# ---------------- verification
vh = json.load(open(f"{A}/results/verify_headline.json"))
pl = vh["placebo"]
VK = {"baseline_vs_crn_rerun": "baseline vs noise-floor rerun (placebo)", "ban3_vs_baseline_real": "top-3 ban vs baseline (real effect)"}
vr = ["| check | result |", "|---|---|",
      f"| independent oracle runner vs stored pass/fail | {vh['independent_oracle_agreement']['agreement']:.3f} agreement on {vh['independent_oracle_agreement']['n']} programs |",
      f"| coarse independent classifier vs AST classifier | {vh['coarse_vs_ast_agreement']:.3f} agreement |"]
for k in ("T1_baseline_vs_crn_rerun", "T3_baseline_vs_crn_rerun", "T1_ban3_vs_baseline_real", "T3_ban3_vs_baseline_real"):
    t = k[:2]
    vr.append(f"| entropy difference, {TASKN[t]}, {VK[k[3:]]} | 95% CI [{pl[k]['ci'][0]:.3f}, {pl[k]['ci'][1]:.3f}], excludes 0: {pl[k]['excludes_0']} |")
vr.append(f"| rate at which a random split of the baseline yields a CI excluding 0 | path {pl['T1_permuted_split_excludes0_rate']:.2f}, weighted {pl['T3_permuted_split_excludes0_rate']:.2f} (nominal 0.05) |")
T["verify"] = "\n".join(vr)

json.dump(T, open(OUT, "w"), indent=0)
print("tables:", len(T))
