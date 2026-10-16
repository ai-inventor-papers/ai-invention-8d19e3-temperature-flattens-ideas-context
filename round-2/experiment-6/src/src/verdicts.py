#!/usr/bin/env python3
"""Collect every verdict from results/*.json into results/verdicts.json (read by method.py output and README)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, write_json  # noqa: E402


def load(n):
    p = RESULTS / n
    return json.loads(p.read_text()) if p.exists() else {}


def main():
    A, S, G = load("reanalysis_contract.json"), load("selector_tables.json"), load("gemma_bans.json")
    Tm, Tr, Au, D = load("gemma_temperature.json"), load("transplant.json"), load("audit.json"), load("sae_latents.json")
    v = {}
    if A:
        c = A["claim3"]
        v["A_claim3"] = dict(verdict=c["verdict"], counts_primary=c["counts"][c["primary_spec"]]["pooled"],
                             primary_spec=c["primary_spec"],
                             counts_all_specs={k: x["pooled"] for k, x in c["counts"].items()})
        v["A_a4"] = {t: dict(rho=A["a4"][t]["rho"], exact_p_two_sided=A["a4"][t]["exact_p_two_sided"],
                             exact_p_one_sided=A["a4"][t]["exact_p_one_sided_positive"],
                             original_ci=A["a4"][t]["original_ci"], ci_corrected=A["a4"][t]["ci_corrected"])
                     for t in ("T1", "T3")}
        v["A_file_counts"] = {t: [A["file_counts"][t]["n_gens_files"], A["file_counts"][t]["n_scored_files"]]
                              for t in ("T1", "T3")}
    if S:
        v["B_selector"] = {}
        for t, d in S["tasks"].items():
            vr = d["vs_random"]
            v["B_selector"][t] = dict(
                decision=d["decision"], alphas=d["alphas"], predicted_gainers=d["predicted_gainers"],
                observed_top_nonmode={k: (d["cells"][k].get("max_nonmode_idea"), d["cells"][k].get("max_nonmode_share"))
                                      for k in ("away_s1", "away_s2", "away_s1_redraw", "away_s2_redraw", "off_s2")},
                entropy_vs_random_draw_mean={k: dict(diff=x["H_mm"]["diff"], ci=x["H_mm"]["ci"],
                                                     verdict=x["H_mm"]["verdict"]) for k, x in vr.items()},
                nonmode_share_vs_random={k: dict(diff=x["nonmode_share"]["diff"], ci=x["nonmode_share"]["ci"])
                                         for k, x in vr.items()},
                pass_vs_random={k: dict(diff=x["pass"]["diff"], ci=x["pass"]["ci"]) for k, x in vr.items()},
                top_gainer_hits=d["top_gainer_hits"], random_top_gainer_hits=d["random_top_gainer_hits"],
                prompting_ceiling={x: dict(steered=c["steered"]["target_share"], forced=c["forced_prompt"]["target_share"],
                                           steered_correct=c["steered"]["correct_target_share"],
                                           forced_correct=c["forced_prompt"]["correct_target_share"],
                                           ban_of_mode_vllm=c["screen_ban_of_mode"]["target_share"])
                                   for x, c in d["prompting_ceiling"].items()},
                pass_baseline=d["cells"]["baseline"].get("pass_rate"),
                engine_consistency=dict(jsd=d["engine_consistency"]["jsd"], ci=d["engine_consistency"]["jsd_ci"],
                                        chi2_p=d["engine_consistency"]["chi2_p"],
                                        split_half=d["engine_consistency"]["jsd_vllm_split_half"]))
        v["B_C4_qwen"] = dict(passes_incl_builtin=S.get("C4_qwen_passes"),
                              passes_excl_builtin=S.get("C4_qwen_passes_excl_builtin"))
        v["frozen_hashes_qwen"] = S.get("frozen_hashes")
    if G:
        cs = G.get("confirmation", {}).get("summary", {})
        v["C2a_jsd_gain"] = dict(passes=cs.get("C2a_jsd_gain_passes"), mean_gain=cs.get("mean_gain_geom_vs_iia"),
                                 ci=cs.get("gain_ci_over_bans"), mean_jsd=cs.get("mean_jsd"),
                                 beats_ext=cs.get("C2a_beats_ext"), loglik=cs.get("mean_loglik_per_sample"))
        v["C2b_top_substitute"] = dict(passes=cs.get("C2b_top_substitute_passes"),
                                       hit_rate=cs.get("top_substitute_hit_rate"), sign_accuracy=cs.get("sign_accuracy"),
                                       n_sign_cells=cs.get("n_sign_cells"))
        rg = G.get("regularity", {})
        v["C_regularity"] = dict(n_cells=rg.get("n_cells"), n_violations=rg.get("n_violations"),
                                 bans_with_violation={t: rg.get(t, {}).get("bans_with_violation") for t in ("T1", "T2")})
        v["C_screen_noise_floor_pp"] = {t: G["screen"][t]["max_noise_floor_pp"] for t in G.get("screen", {})}
        v["C_frozen"] = G.get("frozen")
        v["C_frozen_sha256"] = G.get("frozen_sha256")
    if Tm:
        v["C1_temperature"] = {t: dict(any_top3_reversal=d.get("any_reversal"), arrhenius={j: dict(slope=a["slope"],
                                       slope_ci=a["slope_ci"], r2=a["r2"]) for j, a in d.get("arrhenius", {}).items()},
                                       hill=d.get("hill"), topk10=d.get("topk10_vs_none_T1"))
                               for t, d in Tm.items()}
    if Tr:
        v["C2c_transplant"] = {t: {k: r.get(k) for k in ("recovery_D", "recovery_D_ci", "recovery_R0", "recovery_R1",
                                                         "recovery_R2", "restoration_minusD", "restoration_minusR0",
                                                         "C2c_passes", "jsd_placebo_ban")}
                               for t, r in Tr.get("tasks", {}).items()}
    if Au:
        v["C1_audit"] = dict(n=Au.get("n_judged"), cost=Au.get("cost_usd"), pooled_kappa=Au.get("pooled_kappa"),
                             tasks={t: {k: d[k] for k in ("n", "agreement", "kappa", "label_limited")}
                                    for t, d in Au.get("tasks", {}).items()})
    v["D_sae"] = (dict(ran=True, fvu=D.get("fvu"), reliable=D.get("reliable"),
                       priming={t: [(b["ban"], b["priming"], b["priming_pct_random"], b["priming_pct_other_bans"])
                                    for b in d["bans"]] for t, d in D.get("tasks", {}).items()})
                  if D else dict(ran=False, reason="not run (time)"))
    write_json(RESULTS / "verdicts.json", v)
    print(json.dumps(v, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
