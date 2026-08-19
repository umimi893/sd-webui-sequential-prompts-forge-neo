import copy, unittest
from types import SimpleNamespace
from seqprompt.lifecycle import *

def make(total=5,batch=3):
    p=SimpleNamespace(batch_size=batch,all_prompts=['p']*total,all_negative_prompts=['n']*total,all_seeds=list(range(total)),all_subseeds=list(range(total)),enable_hr=False,prompts=[],negative_prompts=[],seeds=[],subseeds=[],iteration=0,batch_index=0,extra_generation_params={},init=lambda *a:None,parse_extra_network_prompts=lambda:'ok')
    return p

def slice_batch(p,n):
    s=n*p.batch_size;e=(n+1)*p.batch_size;p.iteration=n;p.prompts=p.all_prompts[s:e];p.negative_prompts=p.all_negative_prompts[s:e];p.seeds=p.all_seeds[s:e];p.subseeds=p.all_subseeds[s:e]

class LifecycleTests(unittest.TestCase):
    def test_freeze_and_partial_tail(self):
        p=make(); f=freeze_layout_after_init(p); self.assertEqual((f.batch_size,f.total),(3,5)); self.assertEqual(expected_batch_bounds(f,1),(3,2))
    def test_validate_normal_batch(self):
        p=make(); freeze_layout_after_init(p); slice_batch(p,0); self.assertEqual(validate_live_batch(p,batch_number=0),(0,3))
    def test_validate_partial_batch(self):
        p=make(); freeze_layout_after_init(p); slice_batch(p,1); self.assertEqual(validate_live_batch(p,batch_number=1),(3,2))
    def test_batch_size_change_rejected(self):
        p=make(); freeze_layout_after_init(p); slice_batch(p,0); p.batch_size=2; self.assertRaises(LifecycleInvariantError,validate_live_batch,p,batch_number=0)
    def test_seed_misalignment_rejected(self):
        p=make(); p.all_seeds=p.all_seeds[:-1]; self.assertRaises(LifecycleInvariantError,freeze_layout_after_init,p)
    def test_init_gate_runs_after_original(self):
        calls=[]; p=make(total=1,batch=1); p.init=lambda *a:calls.append('init'); install_init_gate(p,after_init=lambda x:calls.append('after')); p.init([],[],[]); self.assertEqual(calls,['init','after'])
    def test_init_gate_hard_abort(self):
        p=make(total=1,batch=1); install_init_gate(p,abort_reason='bad'); self.assertRaisesRegex(LifecycleInvariantError,'bad',p.init,[],[],[])
    def test_preparse_guard_blocks_reason(self):
        p=make(total=1,batch=1); freeze_layout_after_init(p); slice_batch(p,0); p._seqprompt_blocked_reason='bad'; install_one_shot_preparse_guard(p); self.assertRaisesRegex(LifecycleInvariantError,'bad',p.parse_extra_network_prompts)
    def test_shallow_copy_detaches_metadata(self):
        p=make(total=1,batch=1); seed_setup_owner(p); child=copy.copy(p); self.assertTrue(begin_run_state(child)); child.extra_generation_params['x']=1; self.assertNotIn('x',p.extra_generation_params)
    def test_save_index_uses_frozen_layout(self):
        p=make(); freeze_layout_after_init(p); p.iteration=1;p.batch_index=1; self.assertEqual(save_global_index(p),4)
    def test_bool_indices_rejected(self):
        self.assertRaises(LifecycleInvariantError,expected_batch_bounds,FrozenLayout(1,1),True)

if __name__=='__main__': unittest.main()
