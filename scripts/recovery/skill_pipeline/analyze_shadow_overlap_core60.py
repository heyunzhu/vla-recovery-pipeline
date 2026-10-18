"""C4 trigger-only shadow replay on BASELINE, compared with logged C4 diagnostics.

Does not dispatch a skill or execute an environment action. Emits compressed JSON.
"""
import base64
import argparse
import hashlib
import itertools
import json
import statistics
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006')
REPO = ROOT / 'runtime_repo'
PACK = ROOT / 'checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918'


def tri_conjunction(values):
    return False if False in values else (None if None in values else True)


def tri_part(part):
    def val(p):
        return None if p['actual'] is None or p['error'] else bool(p['passed'])
    all_value = tri_conjunction([val(p) for p in part['all']])
    vals = [val(p) for p in part['any']]
    any_value = True if not vals or True in vals else (None if None in vals else False)
    return tri_conjunction([all_value, any_value])


def summarize(episodes, skill_ids):
    skills = {}
    for sid in skill_ids:
        used = [e for e in episodes if any(sid in q['fire'] for q in e['queries'])]
        apps = [e for e in episodes if any(sid in q['applicable'] for q in e['queries'])]
        first = [next(q for q in e['queries'] if sid in q['fire']) for e in used]
        skills[sid] = dict(applicable_queries=sum(sid in q['applicable'] for e in episodes for q in e['queries']),
            applicable_episodes=len(apps), fire_queries=sum(sid in q['fire'] for e in episodes for q in e['queries']),
            fire_episodes=len(used), success_fire_episodes=sum(e['success'] for e in used),
            tasks=sorted({e['task'] for e in used}), first_query_median=statistics.median(q['idx'] for q in first) if first else None,
            first_env_step_median=statistics.median(q['step'] for q in first) if first else None,
            unknown_queries=sum(sid in q.get('unknown', []) for e in episodes for q in e['queries']))
    pairs = []
    for a, b in itertools.combinations(skill_ids, 2):
        app_q = sim_q = both = sim_ep = separate = a_first = b_first = tie = 0
        examples = []
        for e in episodes:
            qa = {q['idx'] for q in e['queries'] if a in q['fire']}
            qb = {q['idx'] for q in e['queries'] if b in q['fire']}
            app_q += sum(a in q['applicable'] and b in q['applicable'] for q in e['queries'])
            sim_q += len(qa & qb)
            if qa and qb:
                both += 1
                sim_ep += bool(qa & qb)
                separate += not bool(qa & qb)
                a_first += min(qa) < min(qb)
                b_first += min(qb) < min(qa)
                tie += min(qa) == min(qb)
                if len(examples) < 5:
                    examples.append(dict(episode=e['key'], a_queries=sorted(qa), b_queries=sorted(qb)))
        pairs.append(dict(a=a, b=b, co_applicable_queries=app_q, simultaneous_queries=sim_q,
            both_fire_episodes=both, simultaneous_episodes=sim_ep, sequential_only_episodes=separate,
            a_first_episodes=a_first, b_first_episodes=b_first, first_tie_episodes=tie, examples=examples))
    return dict(episodes=len(episodes), successes=sum(e['success'] for e in episodes),
        queries=sum(len(e['queries']) for e in episodes),
        applicable_queries=sum(bool(q['applicable']) for e in episodes for q in e['queries']),
        multi_applicable_queries=sum(len(q['applicable']) > 1 for e in episodes for q in e['queries']),
        fire_queries=sum(bool(q['fire']) for e in episodes for q in e['queries']),
        multi_fire_queries=sum(len(q['fire']) > 1 for e in episodes for q in e['queries']),
        fire_episodes=sum(any(q['fire'] for q in e['queries']) for e in episodes),
        multi_skill_episodes=sum(len({s for q in e['queries'] for s in q['fire']}) > 1 for e in episodes),
        simultaneous_episodes=sum(any(len(q['fire']) > 1 for q in e['queries']) for e in episodes),
        sequential_only_episodes=sum(len({s for q in e['queries'] for s in q['fire']}) > 1 and not any(len(q['fire']) > 1 for q in e['queries']) for e in episodes),
        queries_with_unknown_candidate=sum(bool(q.get('unknown')) for e in episodes for q in e['queries']),
        fully_evaluable_queries=sum(not bool(q.get('unknown')) for e in episodes for q in e['queries']),
        multi_fire_fully_evaluable_queries=sum(len(q['fire']) > 1 and not bool(q.get('unknown')) for e in episodes for q in e['queries']),
        skills=skills, pairs=pairs)


def main():
    global ROOT, REPO, PACK
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', default=str(ROOT))
    parser.add_argument('--json-output', default='')
    args = parser.parse_args()
    ROOT = Path(args.run_root)
    REPO = ROOT / 'runtime_repo'
    PACK = ROOT / 'checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918'
    sys.path.insert(0, str(REPO))
    from experiments.robot.libero.skill_pipeline.schema import resolve_mining_skills
    from experiments.robot.libero.skill_pipeline.matcher import diagnose_skills
    from experiments.robot.libero.skill_pipeline.runtime import SkillRuntime
    skills = [s for s in resolve_mining_skills(PACK / 'skills/_index.yaml') if s.kind == 'trigger']
    ids = sorted(s.id for s in skills)
    assert len(ids) == 18
    groups = defaultdict(list)
    missing = Counter()
    errors = Counter()
    mismatches = []
    validation = Counter()
    manifests = []
    null_fields = Counter()
    missing_keys = Counter()
    for line in (ROOT / 'jobs.tsv').read_text().splitlines()[1:]:
        job_id, lane, condition, suite, pack = line.split('\t')
        if condition not in ('BASELINE', 'C4'):
            continue
        run = ROOT / f'lanes/lane{lane}/{job_id}_{condition}_{suite}/run'
        assert (run / 'summary.json').is_file(), str(run)
        eps = sorted(run.glob('task*/ep*/episode.json'))
        assert len(eps) == 50, (str(run), len(eps))
        manifests.append(dict(condition=condition, suite=suite, run=str(run), episodes=len(eps)))
        for epfile in eps:
            meta = json.loads(epfile.read_text())
            task = f'{suite}/{epfile.parent.parent.name}'
            key = f'{task}/{epfile.parent.name}'
            raw = [json.loads(l) for l in (epfile.parent / 'query_trace.jsonl').read_text().splitlines() if l.strip()]
            assert len(raw) == meta['num_queries'], (key, len(raw), meta['num_queries'])
            assert len({q['query_idx'] for q in raw}) == len(raw), key
            runtime = SkillRuntime(skills)
            pre_intervention = True
            queries = []
            for row in raw:
                for field in ('target_name', 'goal_name', 'ee_xyz', 'gripper_aperture', 'holding_status', 'bddl_goal_surfaces'):
                    if field not in row:
                        missing_keys[(condition, field)] += 1
                    elif row[field] is None:
                        null_fields[(condition, field)] += 1
                state = dict(row)
                state['aperture'] = row.get('gripper_aperture')
                state['task_description'] = meta['task_description']
                state['label'] = ''
                merged = runtime._merge(state)
                replay = diagnose_skills(skills, 'after_pi0_query', merged)
                for diag in replay:
                    for part in ('applies_to', 'trigger'):
                        # Audit trigger inputs on applicable tasks, not unrelated rules.
                        if part == 'trigger' and not diag['applies_to']['passed']:
                            continue
                        for pred in diag[part]['all'] + diag[part]['any']:
                            if pred['error']:
                                errors[(condition, diag['skill_id'], pred['predicate'])] += 1
                            if pred['actual'] is None:
                                missing[(condition, diag['skill_id'], pred['predicate'])] += 1
                if condition == 'C4':
                    logged = row['skill_match_diagnostics']
                    assert {d['skill_id'] for d in logged} == set(ids), (key, row['query_idx'])
                    log_map = {d['skill_id']: d for d in logged}
                    for diag in replay:
                        other = log_map[diag['skill_id']]
                        for part, actual, expected in (
                            ('applies_to', diag['applies_to']['passed'], other['applies_to']['passed']),
                            ('would_fire', diag['would_fire'], other['would_fire'])):
                            prefix = 'pre' if pre_intervention else 'post'
                            validation[f'{prefix}_{part}_checks'] += 1
                            if actual != expected:
                                validation[f'{prefix}_{part}_mismatches'] += 1
                                if len(mismatches) < 30:
                                    mismatches.append(dict(episode=key, query=row['query_idx'], skill=diag['skill_id'], part=part, pre=pre_intervention, replay=actual, logged=expected))
                    # C4 post-intervention uses full original diagnostics, not reconstructed history.
                    diags = logged
                else:
                    assert row.get('mode') == 'vla' and not row.get('hook_fired'), (key, row['query_idx'])
                    diags = replay
                applicable = sorted(d['skill_id'] for d in diags if d['applies_to']['passed'])
                fire = sorted(d['skill_id'] for d in diags if d['would_fire'])
                unknown = sorted(d['skill_id'] for d in diags if tri_conjunction([tri_part(d['applies_to']), tri_part(d['trigger'])]) is None)
                winner = next((d['skill_id'] for d in diags if d['would_fire']), '')
                failures = {d['skill_id']: d['trigger']['failed_all'] + d['trigger']['failed_any'] for d in diags if d['applies_to']['passed'] and not d['would_fire']}
                queries.append(dict(idx=row['query_idx'], step=row['env_step'], applicable=applicable,
                    fire=fire, hypothetical_winner=winner, failed_predicates=failures,
                    observed_mode=row.get('mode'), observed_hook_fired=row.get('hook_fired'),
                    observed_skill=row.get('skill_id'), pre_intervention=pre_intervention, unknown=unknown))
                if row.get('mode') == 'recovery':
                    pre_intervention = False
            groups[condition].append(dict(key=key, task=task, seed=meta.get('seed'),
                episode_idx=meta.get('episode_idx'), description=meta['task_description'], success=bool(meta['success']), queries=queries))
    assert len(groups['BASELINE']) == len(groups['C4']) == 300
    bmap = {e['key']: e for e in groups['BASELINE']}
    cmap = {e['key']: e for e in groups['C4']}
    assert set(bmap) == set(cmap)
    assert all(bmap[k]['seed'] == cmap[k]['seed'] and bmap[k]['description'] == cmap[k]['description'] for k in bmap)
    result = dict(run_root=str(ROOT), pack=str(PACK), skill_ids=ids, manifests=manifests,
        code_head=subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
        matcher_sha256=hashlib.sha256((REPO / 'experiments/robot/libero/skill_pipeline/matcher.py').read_bytes()).hexdigest(),
        pack_index_sha256=hashlib.sha256((PACK / 'skills/_index.yaml').read_bytes()).hexdigest(),
        validation=dict(validation), validation_mismatches=mismatches,
        missing_inputs=[dict(condition=k[0], skill=k[1], predicate=k[2], count=n) for k,n in missing.items()],
        predicate_errors=[dict(condition=k[0], skill=k[1], predicate=k[2], count=n) for k,n in errors.items()],
        null_state_fields=[dict(condition=k[0], field=k[1], count=n) for k,n in null_fields.items()],
        absent_state_keys=[dict(condition=k[0], field=k[1], count=n) for k,n in missing_keys.items()],
        summaries={c:summarize(es, ids) for c,es in groups.items()},
        task_summaries={c:{t:summarize([e for e in es if e['task']==t], ids) for t in sorted({e['task'] for e in es})} for c,es in groups.items()},
        episodes=groups)
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('SHADOW_DATA_START')
    print(base64.b64encode(zlib.compress(json.dumps(result, ensure_ascii=False).encode())).decode())
    print('SHADOW_DATA_END')


if __name__ == '__main__':
    main()
