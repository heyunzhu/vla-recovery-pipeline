"""Read-only frozen C4 hint applicability audit on paired BASELINE/C4 logs."""
import base64
import hashlib
import itertools
import json
import subprocess
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006')
REPO = ROOT / 'runtime_repo'
PACK = ROOT / 'checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918'


def leaves(obj, prefix=''):
    result = {}
    for key, value in obj.items():
        path = prefix + key
        if key in ('source', 'notes', 'target'):
            continue
        if isinstance(value, dict):
            result.update(leaves(value, path + '.'))
        else:
            result[path] = value
    return result


def tri(part):
    def value(p):
        return None if p['actual'] is None or p['error'] else bool(p['passed'])
    av = [value(p) for p in part['all']]
    bv = [value(p) for p in part['any']]
    a = False if False in av else (None if None in av else True)
    b = True if not bv or True in bv else (None if None in bv else False)
    return False if a is False or b is False else (None if a is None or b is None else True)


def main():
    sys.path.insert(0, str(REPO))
    from experiments.robot.libero.skill_pipeline.schema import resolve_mining_skills
    from experiments.robot.libero.skill_pipeline.matcher import match_recovery_hints, explain_applies_to, diagnose_skills
    from experiments.robot.libero.skill_pipeline.runtime import SkillRuntime
    skills = resolve_mining_skills(PACK / 'skills/_index.yaml')
    hints = [s for s in skills if s.kind == 'recovery_hint']
    triggers = [s for s in skills if s.kind == 'trigger']
    assert len(hints) == len(triggers) == 18
    defs = {s.id: dict(scope=s.scope, applies_to=s.applies_to, recovery_hints=s.recovery_hints,
                           execution_fields=leaves(s.recovery_hints), priority=s.priority) for s in hints}
    episodes = defaultdict(list)
    validation = Counter()
    errors = Counter()
    for line in (ROOT / 'jobs.tsv').read_text().splitlines()[1:]:
        job, lane, condition, suite, _ = line.split('\t')
        if condition not in ('BASELINE', 'C4'):
            continue
        run = ROOT / f'lanes/lane{lane}/{job}_{condition}_{suite}/run'
        files = sorted(run.glob('task*/ep*/episode.json'))
        assert len(files) == 50
        for path in files:
            meta = json.loads(path.read_text())
            task = suite + '/' + path.parent.parent.name
            key = task + '/' + path.parent.name
            runtime = SkillRuntime(skills)
            queries = []
            raw = [json.loads(l) for l in (path.parent / 'query_trace.jsonl').read_text().splitlines() if l.strip()]
            assert len(raw) == meta['num_queries']
            for row in raw:
                state = dict(row, aperture=row.get('gripper_aperture'), task_description=meta['task_description'], label='')
                merged = runtime._merge(state)
                matched = sorted(m.skill.id for m in match_recovery_hints(hints, merged))
                diagnostics = {s.id: explain_applies_to(s.applies_to, merged, predicate_registry=s.predicate_registry) for s in hints}
                assert matched == sorted(s for s,d in diagnostics.items() if d['passed'])
                unknown = sorted(s for s,d in diagnostics.items() if tri(d) is None)
                for sid, d in diagnostics.items():
                    for p in d['all'] + d['any']:
                        if p['error']:
                            errors[(condition, sid, p['predicate'], p['error'])] += 1
                diags = row['skill_match_diagnostics'] if condition == 'C4' else diagnose_skills(triggers, 'after_pi0_query', merged)
                fire = sorted(d['skill_id'] for d in diags if d['would_fire'])
                config = row.get('recovery_hints') or {}
                sources = (config.get('params') or {}).get('hint_sources') or []
                selected = sorted({s['skill_id'] for s in sources if s.get('skill_id') in defs}) if row.get('hook_fired') else []
                if condition == 'C4' and row.get('hook_fired'):
                    validation['selected_set_checks'] += 1
                    validation['selected_set_mismatches'] += matched != selected
                actual = row.get('mode') == 'recovery'
                flat = leaves(config)
                retained = {sid: [p for p,v in defs[sid]['execution_fields'].items() if flat.get(p) == v] for sid in selected}
                overwritten = {sid: [p for p,v in defs[sid]['execution_fields'].items() if flat.get(p) != v] for sid in selected}
                queries.append(dict(idx=row['query_idx'], step=row['env_step'], matched=matched, unknown=unknown,
                    trigger_fire=fire, selected=selected, actual_recovery=actual, retained=retained, overwritten=overwritten))
            episodes[condition].append(dict(key=key, task=task, description=meta['task_description'],
                seed=meta.get('seed'), success=bool(meta['success']), queries=queries))
    assert all(len(es)==300 for es in episodes.values())
    b = {e['key']: e for e in episodes['BASELINE']}
    c = {e['key']: e for e in episodes['C4']}
    assert b.keys() == c.keys()
    assert all(b[k]['seed']==c[k]['seed'] and b[k]['description']==c[k]['description'] for k in b)

    def stats(es, sid):
        qs = [q for e in es for q in e['queries']]
        matched_es = [e for e in es if any(sid in q['matched'] for q in e['queries'])]
        selected_es = [e for e in es if any(sid in q['selected'] for q in e['queries'])]
        recovery_es = [e for e in es if any(sid in q['selected'] and q['actual_recovery'] for q in e['queries'])]
        return dict(match_queries=sum(sid in q['matched'] for q in qs), match_episodes=len(matched_es),
            match_tasks=sorted({e['task'] for e in matched_es}),
            match_with_trigger_queries=sum(sid in q['matched'] and bool(q['trigger_fire']) for q in qs),
            match_without_trigger_queries=sum(sid in q['matched'] and not q['trigger_fire'] for q in qs),
            selected_queries=sum(sid in q['selected'] for q in qs), selected_episodes=len(selected_es),
            selected_tasks=sorted({e['task'] for e in selected_es}),
            recovery_queries=sum(sid in q['selected'] and q['actual_recovery'] for q in qs),
            recovery_episodes=len(recovery_es), recovery_success_episodes=sum(e['success'] for e in recovery_es),
            recovery_tasks=sorted({e['task'] for e in recovery_es}),
            recovery_fully_retained_queries=sum(sid in q['selected'] and q['actual_recovery'] and not q['overwritten'][sid] for q in qs),
            overwritten_paths=dict(Counter(p for q in qs if sid in q['selected'] for p in q['overwritten'][sid])),
            unknown_queries=sum(sid in q['unknown'] for q in qs))

    summaries = {}
    for condition, es in episodes.items():
        qs = [q for e in es for q in e['queries']]
        pairs = []
        for a, b in itertools.combinations(sorted(defs), 2):
            common = [(e,q) for e in es for q in e['queries'] if a in q['matched'] and b in q['matched']]
            if not common:
                continue
            pairs.append(dict(a=a,b=b,same_scope=defs[a]['scope']==defs[b]['scope'],
                queries=len(common), episodes=len({e['key'] for e,q in common}),tasks=sorted({e['task'] for e,q in common}),
                with_trigger_queries=sum(bool(q['trigger_fire']) for e,q in common),
                co_selected_queries=sum(a in q['selected'] and b in q['selected'] for e,q in common),
                co_recovery_queries=sum(q['actual_recovery'] and a in q['selected'] and b in q['selected'] for e,q in common),
                examples=[dict(episode=e['key'],query=q['idx']) for e,q in common[:3]]))
        summaries[condition] = dict(episodes=len(es),queries=len(qs),
            hint_match_queries=sum(bool(q['matched']) for q in qs),
            hint_match_without_trigger_queries=sum(bool(q['matched']) and not q['trigger_fire'] for q in qs),
            multi_hint_queries=sum(len(q['matched'])>1 for q in qs),
            same_scope_multi_hint_queries=sum(any(defs[a]['scope']==defs[b]['scope'] for a,b in itertools.combinations(q['matched'],2)) for q in qs),
            trigger_queries=sum(bool(q['trigger_fire']) for q in qs),
            actual_recovery_queries=sum(q['actual_recovery'] for q in qs),
            actual_recovery_episodes=sum(any(q['actual_recovery'] for q in e['queries']) for e in es),
            unknown_candidate_queries=sum(bool(q['unknown']) for q in qs),
            skills={sid:stats(es,sid) for sid in sorted(defs)},pairs=pairs)
    result = dict(definitions=defs, summaries=summaries, validation=dict(validation),
        predicate_errors=[dict(condition=k[0],skill=k[1],predicate=k[2],error=k[3],count=n) for k,n in errors.items()],
        task_stats={condition:{t:{sid:stats([e for e in es if e['task']==t],sid) for sid in sorted(defs)} for t in sorted({e['task'] for e in es})} for condition,es in episodes.items()},
        task_descriptions={e['task']:e['description'] for e in episodes['C4']},
        episodes=episodes, run_root=str(ROOT), pack=str(PACK),
        code_head=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
        matcher_sha256=hashlib.sha256((REPO/'experiments/robot/libero/skill_pipeline/matcher.py').read_bytes()).hexdigest())
    print('HINT_DATA_START')
    print(base64.b64encode(zlib.compress(json.dumps(result,ensure_ascii=False).encode())).decode())
    print('HINT_DATA_END')


if __name__ == '__main__':
    main()
