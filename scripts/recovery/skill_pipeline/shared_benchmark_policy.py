"""One local GPU policy with isolated per-episode clients for parallel simulations."""
import argparse
import copy
import json
import os
from pathlib import Path
import threading
import traceback
from multiprocessing.connection import Listener,Client


class SharedBenchmarkPolicy:
    def __init__(self,config_name,checkpoint_dir):
        from experiments.robot.libero.skill_pipeline import runner
        endpoint=json.loads(Path(os.environ['RGBD_POLICY_ENDPOINT']).read_text())
        self.connection=Client(tuple(endpoint['address']),authkey=bytes.fromhex(endpoint['authkey']))
        self._model=runner._ModelState()
        self._request('start',dict(config_name=config_name,checkpoint_dir=str(checkpoint_dir),
                                 seed=int(os.environ['RGBD_EPISODE_SEED'])))

    def _request(self,command,payload=None):
        self.connection.send((command,payload))
        if not self.connection.poll(600):raise TimeoutError('shared policy request timed out')
        status,response=self.connection.recv()
        if status!='ok':raise RuntimeError(response)
        return response

    def reset(self):
        self._request('reset');self._model.last_uncertainty_logvar=None

    def infer(self,observation):
        from experiments.robot.libero.skill_pipeline import runner
        response=self._request('infer',observation)
        logvar=response['logvar']
        self._model.last_uncertainty_logvar=runner._ArrayWithNumpy(logvar) if logvar is not None else None
        return response['output']

    def close(self):
        if self.connection is not None:
            self.connection.close();self.connection=None


def serve(config_name,checkpoint_dir,directory):
    import numpy as np
    import jax
    from experiments.robot.libero.skill_pipeline import runner
    runner._patch_torch_load()
    base=runner.JaxOpenPIUncertaintyPolicyAdapter(config_name,checkpoint_dir)
    if not hasattr(base._policy,'_rng'):
        raise RuntimeError('shared policy requires an explicit per-client RNG field')
    lock=threading.Lock();token=os.urandom(32)
    listener=Listener(('127.0.0.1',0),authkey=token)
    endpoint=directory/'policy_endpoint.json'
    endpoint.write_text(json.dumps(dict(address=listener.address,authkey=token.hex())))
    endpoint.chmod(0o600)
    (directory/'policy_ready.json').write_text(json.dumps(dict(address=listener.address,
        config_name=config_name,checkpoint_dir=str(checkpoint_dir),per_episode_rng=True,
        policy_parameters_shared=True)))

    def client(connection):
        policy=None;seed=None
        try:
            while True:
                command,payload=connection.recv()
                try:
                    with lock:
                        if command=='start':
                            if payload['config_name']!=config_name or Path(payload['checkpoint_dir'])!=Path(checkpoint_dir):
                                raise ValueError('policy configuration differs from shared server')
                            seed=payload['seed'];policy=copy.copy(base)
                            policy._policy=copy.copy(base._policy);policy._model=runner._ModelState()
                            policy._policy._rng=jax.random.PRNGKey(seed)
                            output=None
                        elif command=='reset':
                            if policy is None:raise RuntimeError('uninitialized policy session')
                            policy.reset();policy._policy._rng=jax.random.PRNGKey(seed);output=None
                        elif command=='infer':
                            if policy is None:raise RuntimeError('uninitialized policy session')
                            result=policy.infer(payload)
                            output=dict(output={k:np.asarray(v) if hasattr(v,'shape') else v for k,v in result.items()},
                                logvar=getattr(policy._model.last_uncertainty_logvar,'numpy',lambda:None)())
                        else:raise ValueError('unknown shared policy command')
                    connection.send(('ok',output))
                except Exception:connection.send(('error',traceback.format_exc()))
        except (EOFError,ConnectionError,OSError):pass
        finally:connection.close()

    while True:
        connection=listener.accept()
        threading.Thread(target=client,args=(connection,),daemon=True).start()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config-name',required=True)
    p.add_argument('--checkpoint-dir',required=True);p.add_argument('--directory',type=Path,required=True)
    args=p.parse_args();serve(args.config_name,args.checkpoint_dir,args.directory)
