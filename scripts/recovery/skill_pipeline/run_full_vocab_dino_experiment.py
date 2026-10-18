"""Collect frozen-suite C4 handoffs, audit grouped labels, train and evaluate.

All mutations stay inside the experiment directories. No benchmark recovery
success is claimed by the data collector, whose handoff callback only labels.
"""
from pathlib import Path
import argparse,collections,hashlib,json,os,signal,subprocess,time,traceback
from concurrent.futures import ThreadPoolExecutor,as_completed


def write(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(path)


def collection_command(root,run,code,record,gpu):
    case=run/'collection'/record['case_id'];case.mkdir(parents=True,exist_ok=True);write(case/'record.json',record)
    frozen=run/'runtime/frozen_runtime';python=root/'envs/rgbd_dino_full_20261018_sim/bin/python'
    env=dict(os.environ,FULL_DINO_RUN=str(run),FULL_DINO_CODE=str(code),FULL_DINO_CASE=str(case),
        FULL_DINO_DATASET=str(root/'datasets/rgbd_dino_full_20261018'),FULL_DINO_RENDER_GPU='1',
        CUDA_VISIBLE_DEVICES=gpu,PYTHONPATH=':'.join(map(str,[frozen,root/'LIBERO-PRO',code])),
        RGBD_POLICY_ENDPOINT=str(run/'policy_endpoint.json'),RGBD_EPISODE_SEED=str(20261018+record['init_id']),
        LIBERO_CONFIG_PATH=str(run/'libero_config'),MUJOCO_GL='egl',PYOPENGL_PLATFORM='egl',MUJOCO_EGL_DEVICE_ID='1',
        HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',
        XLA_PYTHON_CLIENT_PREALLOCATE='false',OPENPI_DATA_HOME=str(root/'.cache/openpi'),XDG_CACHE_HOME=str(root/'.cache/rgbd_dino_full_20261018'),HF_HOME=str(root/'.cache/rgbd_dino/huggingface'),CUDA_CACHE_PATH=str(root/'.cache/rgbd_dino_full_20261018/cuda'),TMPDIR=str(root/'tmp'))
    argv=[python,'-u',code/'scripts/recovery/skill_pipeline/collect_core60_detection_entrypoint.py',
        '--pretrained_path',root/'models/pi0_libero_openpi','--config_name','pi0_libero',
        '--task_suite_name',record['suite'],'--task_ids',str(record['task_1based']),'--num_trials_per_task','1',
        '--episode_index_start',str(record['init_id']),'--episode_seed_start','1','--seed','90','--policy_in_process',
        '--openvla_repo_root',frozen,'--task_language_source','bddl','--engine_language_source','bddl',
        '--max_recovery_calls','2','--max_recovery_steps','200','--max_replans','1',
        '--log_dir',case,'--exp_name','rollout','--enable_mining_skills','--skill_pack',run/'runtime/skill_pack']
    return case,list(map(str,argv)),env


def collect(root,run,code,record,gpu):
    case=run/'collection'/record['case_id']
    if (case/'complete.json').exists():return json.loads((case/'complete.json').read_text())
    if (case/'frames.jsonl').exists():
        archive=run/'interrupted'/f"{record['case_id']}_{time.time_ns()}";archive.parent.mkdir(exist_ok=True);case.rename(archive)
    case,argv,env=collection_command(root,run,code,record,gpu);write(case/'command.json',dict(argv=argv,env={k:v for k,v in env.items() if k not in os.environ or v!=os.environ[k]}))
    with (case/'driver.log').open('wb') as log:
        p=subprocess.Popen(argv,cwd=run/'runtime/frozen_runtime',env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write(case/'status.json',dict(state='running',pid=p.pid,record=record,started=time.time()))
        try:rc=p.wait(timeout=1200)
        except subprocess.TimeoutExpired:rc=124
        finally:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
    frames=[json.loads(line) for line in (case/'frames.jsonl').read_text().splitlines()] if (case/'frames.jsonl').exists() else []
    episode=list(case.glob('rollout/task*/ep*/episode.json'))
    report=dict(case_id=record['case_id'],record=record,returncode=rc,frames=len(frames),handoff_frames=sum(r['phase']=='skill_trigger' for r in frames),episode_complete=bool(episode))
    if rc or not frames or not episode:
        report['error']=(case/'driver.log').read_text(errors='replace')[-6000:];write(case/'failed.json',report);raise RuntimeError(json.dumps(report))
    write(case/'complete.json',report);write(case/'status.json',dict(state='complete',**report));return report


def finalize_dataset(root,run):
    dataset=root/'datasets/rgbd_dino_full_20261018';tax=json.loads((run/'taxonomy.json').read_text());rows=[]
    for p in sorted((run/'collection').glob('*/complete.json')):
        rows.extend(json.loads(line) for line in (p.parent/'frames.jsonl').read_text().splitlines())
    # Identical physical layouts and identical RGB form a union-find group.
    parent={r['layout_group']:r['layout_group'] for r in rows}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    pixels={}
    for r in rows:
        if r['pixel_sha256'] in pixels:
            a,b=find(r['layout_group']),find(pixels[r['pixel_sha256']]);parent[a]=b
        else:pixels[r['pixel_sha256']]=r['layout_group']
    groups=collections.defaultdict(list)
    for r in rows:groups[find(r['layout_group'])].append(r)
    old=root/'datasets/rgbd_dino_20261015/records.jsonl'
    old_layouts=set();old_pixels=set()
    if old.exists():
        for line in old.read_text().splitlines():
            r=json.loads(line);old_layouts.add(r['layout_group']);old_pixels.add(r['pixel_sha256'])
    selected=collections.defaultdict(list);excluded=[]
    # Keep the most protected split and exclude all cross-split siblings.
    priority={'train':0,'val':1,'test':2}
    for key,group in groups.items():
        split=max((r['split'] for r in group),key=priority.get)
        for r in group:
            reason=None
            if r['split']!=split:reason='cross_split_physical_or_rgb_duplicate'
            elif split=='test' and (r['layout_group'] in old_layouts or r['pixel_sha256'] in old_pixels):reason='old_model_data_overlap'
            if reason:excluded.append(dict(episode=r['episode'],id=r['id'],reason=reason));continue
            selected[split].append(r)
    categories=[dict(id=i+1,name=n) for i,n in enumerate(tax['classes'])];counts={};stats={}
    for split in ['train','val','test']:
        images=[];anns=[];seen=set()
        for r in selected[split]:
            if r['id'] in seen:raise ValueError('duplicate COCO image ID')
            seen.add(r['id']);images.append({k:v for k,v in r.items() if k!='annotations'})
            for a in r['annotations']:anns.append(dict(a,id=len(anns)+1,image_id=r['id']))
        counts[split]=dict(collections.Counter(tax['classes'][a['category_id']-1] for a in anns))
        missing=set(tax['classes'])-set(counts[split])
        if missing:raise ValueError('missing labeled classes in '+split+': '+str(missing))
        if not images:raise ValueError('empty split '+split)
        (dataset/'annotations').mkdir(exist_ok=True)
        write(dataset/'annotations'/f'{split}640.json',dict(images=images,annotations=anns,categories=categories))
        stats[split]=dict(images=len(images),episodes=len({r['episode'] for r in images}),phases=dict(collections.Counter(r['phase'] for r in images)),cameras=dict(collections.Counter(r['camera'] for r in images)))
    assert any(r['phase']=='skill_trigger' for r in selected['train']),'no genuine C4 handoff samples collected'
    audit=dict(category_count=len(categories),class_counts=counts,split_statistics=stats,excluded=excluded,physical_and_identical_rgb_groups_disjoint=True,old_model_test_overlap_excluded=True,total_frames=len(rows),annotation_source='offline simulator visible instance masks, no antialiasing',training_source='VLA rollouts and genuine frozen C4 skill trigger captures; no controller execution at handoff')
    write(dataset/'dataset_audit.json',audit);write(dataset/'completed.json',dict(selected_frames=sum(len(v) for v in selected.values()),candidate_frames=len(rows)));return audit


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--gpu',required=True);p.add_argument('--workers',type=int,default=2);p.add_argument('--epochs',type=int,default=12);args=p.parse_args()
    root=args.root;tag='rgbd_dino_full_20261018';run=root/'logs'/tag;code=root/'code_snapshots'/tag;models=root/'models'/tag
    state=dict(started=time.time(),stages=[],args=dict(root=str(root),gpu=args.gpu,workers=args.workers,epochs=args.epochs));write(run/'pipeline_status.json',state)
    def stage(name,argv,env):
        state['current_stage']=name;row=dict(name=name,argv=list(map(str,argv)),started=time.time());state['stages'].append(row);write(run/'pipeline_status.json',state)
        with (run/(name+'.log')).open('wb') as log:r=subprocess.run(row['argv'],cwd=code,env=env,stdout=log,stderr=subprocess.STDOUT)
        row.update(ended=time.time(),returncode=r.returncode);write(run/'pipeline_status.json',state)
        if r.returncode:raise RuntimeError(name+' failed; inspect its log')
    try:
        sim_python=root/'envs'/(tag+'_sim/bin/python');train_python=root/'envs'/(tag+'_train/bin/python')
        sim_env=dict(os.environ,PYTHONPATH=':'.join(map(str,[run/'runtime/frozen_runtime',root/'LIBERO-PRO',code])),CUDA_VISIBLE_DEVICES=args.gpu,XLA_PYTHON_CLIENT_PREALLOCATE='false',XLA_PYTHON_CLIENT_MEM_FRACTION='.3',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OPENPI_DATA_HOME=str(root/'.cache/openpi'),XDG_CACHE_HOME=str(root/'.cache'/tag),HF_HOME=str(root/'.cache/rgbd_dino/huggingface'),CUDA_CACHE_PATH=str(root/'.cache'/tag/'cuda'),TMPDIR=str(root/'tmp'))
        argv=[str(sim_python),str(code/'scripts/recovery/skill_pipeline/shared_benchmark_policy.py'),'--config-name','pi0_libero','--checkpoint-dir',str(root/'models/pi0_libero_openpi'),'--directory',str(run)]
        with (run/'policy_server.log').open('wb') as log:policy=subprocess.Popen(argv,cwd=run/'runtime/frozen_runtime',env=sim_env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write(run/'policy_launch.json',dict(pid=policy.pid,argv=argv))
        for _ in range(600):
            if policy.poll() is not None:raise RuntimeError('policy service exited')
            if (run/'policy_ready.json').exists():break
            time.sleep(1)
        else:raise TimeoutError('policy load timeout')
        records=json.loads((run/'collection_cases.json').read_text());state['current_stage']='collection';write(run/'pipeline_status.json',state)
        # Two startup episodes include object classes and a known skill trigger.
        probes=[r for r in records if r['split']=='train' and r['init_id']==6 and (r['suite'],r['task_1based']) in [('libero_object_task',1),('libero_goal_task',8)]]
        completed={}
        def record_result(r):
            completed[r['case_id']]=r;write(run/'collection_progress.json',dict(requested=len(records),completed=len(completed),frames=sum(x['frames'] for x in completed.values()),handoff_frames=sum(x['handoff_frames'] for x in completed.values())))
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(collect,root,run,code,r,args.gpu) for r in probes]):record_result(future.result())
            write(run/'collection_probe_passed.json',dict(cases=list(completed)))
            pending=[r for r in records if r['case_id'] not in completed]
            for future in as_completed([pool.submit(collect,root,run,code,r,args.gpu) for r in pending]):record_result(future.result())
        os.killpg(policy.pid,signal.SIGTERM);policy.wait(timeout=30)
        audit=finalize_dataset(root,run);state['dataset_audit']=audit;write(run/'pipeline_status.json',state)
        scripts=code/'scripts/recovery/skill_pipeline';mmdet=root/'code_snapshots/mmdetection_rgbd_20261015';dataset=root/'datasets'/tag
        env=dict(os.environ,CUDA_VISIBLE_DEVICES=args.gpu,PYTHONPATH=str(code)+':'+str(mmdet),OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',NLTK_DATA=str(root/'models/rgbd_dino_finetune_20261015/nltk_data'),XDG_CACHE_HOME=str(root/'.cache'/tag),TMPDIR=str(root/'tmp'))
        common=[train_python,scripts/'train_grounding_dino_libero.py','--mmdetection',mmdet,'--dataset',dataset,'--bert',models/'bert_local','--pretrained',models/'groundingdino_swint_ogc_mmdet-822d7e9d.pth','--epochs',str(args.epochs),'--batch-size','2','--accumulation','2','--workers','2','--seed','20261018']
        stage('smoke_train',common+['--output',models/'smoke','--smoke-iterations','12'],env)
        stage('train',common+['--output',models/'training'],env)
        best=list((models/'training').glob('best_coco_bbox_mAP*.pth'));assert len(best)==1
        variants={'pretrained':models/'groundingdino_swint_ogc_mmdet-822d7e9d.pth','old8':root/'models/rgbd_dino_finetune_20261015/training/best_coco_bbox_mAP_epoch_5.pth','full19':best[0]}
        for name,checkpoint in variants.items():
            for split in ['val','test']:
                argv=[train_python,scripts/'evaluate_grounding_dino_libero.py','--config',models/'training/config.py','--checkpoint',checkpoint,'--dataset',dataset,'--output',models/'evaluation'/name/split,'--split',split]
                if split=='test':argv+=['--calibration',models/'evaluation'/name/'val/calibration.json']
                stage('evaluate_'+name+'_'+split,argv,env)
        export=json.loads((root/'logs/rgbd_dino_finetune_20261015/export_hf_best_command.json').read_text())['argv']
        export[0]=str(train_python);export[2]=str(scripts/'export_grounding_dino_libero_hf.py');export[export.index('--checkpoint')+1]=str(best[0]);export[export.index('--output')+1]=str(models/'hf_export_best')
        stage('export_hf',export,env)
        # Deployment is withheld until independent HF output validation passes.
        state.update(complete=True,current_stage='detection_training_and_mmdet_evaluation_complete_hf_validation_pending',best_checkpoint=str(best[0]),ended=time.time(),automatic_benchmark_deployment=False);write(run/'pipeline_status.json',state)
    except Exception:
        state.update(error=traceback.format_exc(),ended=time.time());write(run/'pipeline_status.json',state);raise


if __name__=='__main__':main()
