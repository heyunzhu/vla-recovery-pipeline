"""Render readable task-level audit tables from exported hint shadow statistics."""
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'docs/results'


def task_list(tasks):
    return '；'.join(t.replace('libero_', '').replace('/task', ':T') for t in tasks) or '无'


def main():
    d = json.loads((OUT/'libero_pro_c4_hint_shadow_results.json').read_text(encoding='utf-8'))
    full = json.loads(gzip.decompress((OUT/'libero_pro_c4_hint_shadow_full.json.gz').read_bytes()))
    assert len(d['definitions']) == 18
    assert d['validation']['selected_set_checks'] == 594 and d['validation']['selected_set_mismatches'] == 0
    for condition, es in full['episodes'].items():
        assert len(es) == 300
        assert sum(len(e['queries']) for e in es) == d['summaries'][condition]['queries']
        for sid, s in d['summaries'][condition]['skills'].items():
            assert s['match_queries'] == s['match_with_trigger_queries'] + s['match_without_trigger_queries']
            assert s['recovery_queries'] <= s['selected_queries'] <= s['match_queries']
            assert s['recovery_fully_retained_queries'] <= s['recovery_queries']
            assert sum(t[sid]['match_queries'] for t in d['task_stats'][condition].values()) == s['match_queries']
    lines = ['# C4 全 36 条 skill：补齐 recovery hint 的匹配、选择和恢复入口', '',
        '## 先读这一段', '',
        'Trigger 决定“是否请求接管”；recovery hint 决定“若接管，用什么抓取/定位/几何/放置配置”。Hint 没有独立的动态 trigger，因此不能把 hint 条件匹配称为已经触发机器人动作。', '',
        '本次补读 BASELINE 与 C4 各 300 个 episode，共 600 个。用同一个冻结 C4 pack 在每个记录的 VLA query 上旁路匹配，不派发 backend、不执行动作。BASELINE 的匹配仅是假设 C4 pack 在这些状态上会适用，不是 BASELINE 真用了 hint。', '',
        '## 指标是什么意思', '',
        '| 指标 | 简单含义 |', '| --- | --- |',
        '| 匹配 task/episode/query | 至少一次满足该 hint 的 applies_to；query 是一次 VLA 预测检查点 |',
        '| 无 trigger 的匹配 | hint 适用，但这个检查点没有任何 trigger 满足动态条件，因此不会因此接管 |',
        '| 决策选择 | hook 请求接管后，hint ID 被记录在 hint_sources 中 |',
        '| 实际恢复入口 | 上述 hint 被选用，且该 query 的 mode=recovery；不代表抓取或放置阶段一定执行到/成功 |',
        '| 配置保留 | hint 声明的执行字段在最终合并配置中仍保持原值；排除 source、notes、target 元数据，不是物理阶段成功率 |',
        '| 同职责重叠 | 同一个检查点有两个 scope 相同的 hint 匹配，是候选冗余/冲突信号 |',
        '| 跨职责共同匹配 | 例如 grasp+geometry+place 同时匹配，可能是正常组合，不直接视为重复 |', '',
        '## 总体统计', '', '| 项目 | BASELINE 旁路 | C4 |', '| --- | ---: | ---: |']
    names = [('queries','检查点总数'),('hint_match_queries','有 hint 匹配的检查点'),('hint_match_without_trigger_queries','hint 匹配但无 trigger 的检查点'),('multi_hint_queries','多个 hint 共同匹配的检查点'),('same_scope_multi_hint_queries','同职责多个 hint 共同匹配的检查点'),('trigger_queries','至少一个 trigger 满足动态条件的检查点'),('actual_recovery_queries','实际恢复入口数'),('actual_recovery_episodes','实际进入恢复的 episode 数'),('unknown_candidate_queries','至少一个 hint 条件不可判定的检查点')]
    for k,n in names:
        lines.append(f"| {n} | {d['summaries']['BASELINE'][k]} | {d['summaries']['C4'][k]} |")
    lines += ['', '次数按检查点计，不是 task 数；同一 hint 可以在一个长 episode 内反复匹配。BASELINE/C4 轨迹长度不同，不把两组原始 query 数之差解释为能力变化。', '',
        '## 当前能得到的结论', '',
        '1. Hint 的适用并不等于接管：C4 的 3,704 个有 hint 匹配的检查点中，3,174 个（85.7%）没有 trigger 满足动态条件。这些可能只是正常运行状态，不能据此说触发机制漏救。',
        '2. Hint 的范围窄不只是 trigger 不放行：两组轨迹上，18 条 hint 都是 1 条零匹配、9 条只匹配一个 task、8 条匹配多个 task；C4 每条 hint 的匹配 task 集合与选择/实际恢复 task 集合相同。现有数据中未发现“匹配了新 task，但只因 trigger 未触发而完全没用到”的 task 级落差。',
        '3. 检查全部 153 对 hint，两组都是 0 对同职责共同匹配、17 对跨职责共同匹配。条件有分区、职责有组合，是本次观察；不证明语义无重复，也不证明 profile 具有强泛化。',
        '4. 宽范围例子：grasp_bowl_plate_hollow_rim_topdown 匹配 21 个 task，C4 有 2,265 次匹配、458 次决策选择、145 次实际恢复入口（103 个 episode）；不能把 458 当作物理恢复次数。窄范围例子：cream-cheese→bowl 的四条 hint 都只匹配 goal_swap/task07，90 次匹配、5 次选择/恢复入口；四条分属 grasp/grounding/geometry/place，是同任务的配置组合。',
        '5. 所有实际恢复入口中被选用的 hint，其声明的执行字段均保持在合并配置中，未发现字段覆盖；尚不能证明每个字段对应的动作阶段真正执行到了。',
        '6. 不可判定只涉及 grasp_carton_upright_body_side，在 goal_swap/task01（Open the middle layer of the drawer）上两组各 300 个 query（5 个 episode）；目标物体相关信息缺失，不将此情况当成确定不匹配。其余 hint 在这些检查点为确定不匹配，因此未制造潜在的同职责双匹配。', '',
        '## 18 条 hint 完整表（零使用也保留）', '',
        '| Hint 完整 ID | 职责 | B 匹配 task 数 | C4 匹配 task 数 | C4 匹配 query | C4 匹配但无 trigger | C4 决策选择 | C4 实际恢复入口 | 恢复 episode | 恢复 task 数 | 配置完整保留入口 |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for sid,definition in sorted(d['definitions'].items()):
        b=d['summaries']['BASELINE']['skills'][sid]; c=d['summaries']['C4']['skills'][sid]
        values = [len(b['match_tasks']),len(c['match_tasks']),c['match_queries'],c['match_without_trigger_queries'],c['selected_queries'],c['recovery_queries'],c['recovery_episodes'],len(c['recovery_tasks']),c['recovery_fully_retained_queries']]
        lines.append('| '+sid+' | '+definition['scope']+' | '+' | '.join(map(str,values))+' |')
    lines += ['', '## Hint 之间共同匹配：同职责与跨职责分开看', '']
    for condition in ('BASELINE','C4'):
        pairs=d['summaries'][condition]['pairs']
        same=[p for p in pairs if p['same_scope']]
        cross=[p for p in pairs if not p['same_scope']]
        lines += [f'### {condition}', '', f'检查了全部 153 对 hint：有共同匹配的同职责组合 {len(same)} 对，跨职责组合 {len(cross)} 对。未列出的组合共同匹配为零。', '',
            '| A | B | 同职责？ | 共同匹配 query | 共同匹配 ep | task | 有 trigger | 共同被选用 | 共同实际恢复入口 |',
            '| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: |']
        for p in sorted(pairs,key=lambda p:(not p['same_scope'],-p['queries'],p['a'])):
            lines.append(f"| {p['a']} | {p['b']} | {'是' if p['same_scope'] else '否'} | {p['queries']} | {p['episodes']} | {task_list(p['tasks'])} | {p['with_trigger_queries']} | {p['co_selected_queries']} | {p['co_recovery_queries']} |")
    lines += ['', '## 每条 hint 的具体 task 数据', '',
        'Task 按 suite+ID 计。同一个指令在不同 ID 下仍算两个 task，不等于两个不同语义；匹配跨度是适用范围，不是成功泛化的直接证据。每个 task 有 5 个 episode。仅省略 B/C4 均零匹配、零选择且无不可判定条件的 task；JSON 包含全部 60×18 格。', '']
    for sid in sorted(d['definitions']):
        definition=d['definitions'][sid]
        profiles=[str(v) for k,v in definition['execution_fields'].items() if k.endswith('profile')]
        lines += [f'### {sid}', '', f"职责：{definition['scope']}；声明 profile：{', '.join(profiles) or '无命名 profile，直接提供参数'}。", '',
            '声明的执行配置：`'+json.dumps(definition['execution_fields'],ensure_ascii=False,separators=(',',':'))+'`。', '',
            '| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |', '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        nonzero=0
        for task,skills in d['task_stats']['C4'].items():
            c=skills[sid]; b=d['task_stats']['BASELINE'][task][sid]
            if not (c['match_queries'] or b['match_queries'] or c['selected_queries'] or c['unknown_queries'] or b['unknown_queries']):
                continue
            nonzero+=1
            desc=d['task_descriptions'][task].replace('|','\\|')
            lines.append(f"| {task} | {desc} | {b['match_episodes']}/{b['match_queries']} | {c['match_episodes']}/{c['match_queries']} | {c['match_without_trigger_queries']} | {c['selected_queries']} | {c['recovery_episodes']}/{c['recovery_queries']} | {c['recovery_success_episodes']}/{c['recovery_episodes']} | {b['unknown_queries']}/{c['unknown_queries']} |")
        if not nonzero:
            lines.append('| 全部 60 个 task | 均未匹配/选用 | 0/0 | 0/0 | 0 | 0 | 0/0 | — | 0/0 |')
    lines += ['', '## 全 36 条 skill 一张表', '',
        '全部在 C4 原始轨迹上统计。Trigger 的“选择”是 winner；hint 的“选择”是合并配置。恢复入口数是 mode=recovery，与过去只统计 hook 决策的表不同。', '',
        '| 完整 skill ID | 类型 | 条件匹配 task 数 | 被选用 task 数 | 被选用 query | 实际恢复入口数 | 实际恢复 task 数 |', '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    trigger=json.loads(gzip.decompress((OUT/'libero_pro_c4_shadow_overlap_full.json.gz').read_bytes()))
    es=trigger['episodes']['C4']
    for sid in trigger['skill_ids']:
        matches={e['task'] for e in es for q in e['queries'] if sid in q['applicable']}
        selected=[(e,q) for e in es for q in e['queries'] if q['observed_hook_fired'] and q['observed_skill']==sid]
        actual=[(e,q) for e,q in selected if q['observed_mode']=='recovery']
        lines.append(f"| {sid} | Trigger | {len(matches)} | {len({e['task'] for e,q in selected})} | {len(selected)} | {len(actual)} | {len({e['task'] for e,q in actual})} |")
    for sid,c in sorted(d['summaries']['C4']['skills'].items()):
        lines.append(f"| {sid} | Hint | {len(c['match_tasks'])} | {len(c['selected_tasks'])} | {c['selected_queries']} | {c['recovery_queries']} | {len(c['recovery_tasks'])} |")
    lines += ['', '## 验证与可复现边界', '',
        f"冻结运行代码 commit：`{d['code_head']}`；matcher SHA256：`{d['matcher_sha256']}`。", '',
        f"在 C4 的 {d['validation']['selected_set_checks']} 个 hook 决策检查点上，旁路匹配集合与原始 hint_sources 集合不一致 {d['validation']['selected_set_mismatches']} 次。谓词执行错误 {len(d['predicate_errors'])} 类。", '',
        '恢复入口、字段保留不等于每个 profile 的物理阶段真的执行完；本次没有对 recovery_trace 内每种动作阶段做逐条归因，因此不能报告单 hint 成功率。Episode 最终成功也不能归因于某一条 hint。', '',
        '完整结构化数据：libero_pro_c4_hint_shadow_results.json；逐检查点匹配、trigger 集合、选择集合、字段保留/覆盖数据：libero_pro_c4_hint_shadow_full.json.gz。']
    (OUT/'libero_pro_c4_hint_shadow_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'report_rows':len(lines),'hint_count':len(d['definitions']),'validation':d['validation']}))


if __name__=='__main__':
    main()
